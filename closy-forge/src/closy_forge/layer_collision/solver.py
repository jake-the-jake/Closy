from __future__ import annotations

from collections import defaultdict
from math import cos, pi, sin
from typing import Any

from .contracts import (
    SOLVER_VERSION,
    LayerCollisionError,
    LayerSpec,
    OutfitSpec,
    canonical_hash,
    rounded,
)

SEGMENTS = 24
RINGS = 3
STATES = (
    ("neutral", 0.0),
    ("motion_peak", 1.0),
    ("twist_peak", -0.72),
    ("return", 0.0),
)
STEPS_PER_STATE = 10
ITERATIONS_PER_STEP = 8


def run_simultaneous_layer_solve(spec: OutfitSpec) -> dict[str, Any]:
    validate_outfit_spec(spec)
    layer_ids = [layer.layer_id for layer in spec.layers]
    radii = {
        layer.layer_id: [
            spec.body_radius_meters + layer.initial_center_offset_meters
            for _ in range(SEGMENTS * RINGS)
        ]
        for layer in spec.layers
    }
    initial = {layer_id: list(values) for layer_id, values in radii.items()}
    velocities = {layer_id: [0.0 for _ in values] for layer_id, values in radii.items()}
    trajectory: list[dict[str, Any]] = []
    state_reports: list[dict[str, Any]] = []
    response = {layer_id: 0.0 for layer_id in layer_ids}
    broad_phase_pairs = _adjacent_pairs(spec.layers)
    for state_id, state_factor in STATES:
        state_start = _measure(spec, radii, initial)
        for step in range(STEPS_PER_STATE):
            _integrate_motion(spec, radii, velocities, state_factor, step)
            for iteration in range(ITERATIONS_PER_STEP):
                _project_body(spec, radii, response)
                narrow_tests, corrections = _project_adjacent_layers(spec, radii, response)
                _project_body(spec, radii, response)
                measured = _measure(spec, radii, initial)
                trajectory.append(
                    {
                        "stateId": state_id,
                        "step": step,
                        "iteration": iteration,
                        "contactCount": measured["residualContactCount"],
                        "maximumDepthMeters": measured["maximumResidualDepthMeters"],
                        "narrowPhaseTests": narrow_tests,
                        "correctionCount": corrections,
                    }
                )
        for iteration in range(24):
            _project_body(spec, radii, response)
            narrow_tests, corrections = _project_adjacent_layers(spec, radii, response)
            _project_body(spec, radii, response)
            measured = _measure(spec, radii, initial)
            trajectory.append(
                {
                    "stateId": state_id,
                    "step": STEPS_PER_STATE,
                    "iteration": iteration,
                    "contactCount": measured["residualContactCount"],
                    "maximumDepthMeters": measured["maximumResidualDepthMeters"],
                    "narrowPhaseTests": narrow_tests,
                    "correctionCount": corrections,
                }
            )
        coupled_corrections = _project_coupled_stack(spec, radii, response)
        measured = _measure(spec, radii, initial)
        trajectory.append(
            {
                "stateId": state_id,
                "step": STEPS_PER_STATE,
                "iteration": 24,
                "contactCount": measured["residualContactCount"],
                "maximumDepthMeters": measured["maximumResidualDepthMeters"],
                "narrowPhaseTests": SEGMENTS * RINGS * (len(spec.layers) - 1),
                "correctionCount": coupled_corrections,
            }
        )
        state_metrics = _measure(spec, radii, initial)
        state_reports.append(
            {
                "stateId": state_id,
                "start": state_start,
                "final": state_metrics,
            }
        )
    final_metrics = _measure(spec, radii, initial)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "solverVersion": SOLVER_VERSION,
        "caseId": spec.case_id,
        "zone": spec.zone,
        "solverExecuted": True,
        "simultaneousLayerCount": len(spec.layers),
        "layerIds": layer_ids,
        "collisionOrders": [layer.collision_order for layer in spec.layers],
        "materialIds": [layer.material_id for layer in spec.layers],
        "differentMaterialsExecuted": len({layer.material_id for layer in spec.layers}) > 1,
        "broadPhase": {
            "pairCount": len(broad_phase_pairs),
            "pairs": [list(pair) for pair in broad_phase_pairs],
            "adjacentLayerOnly": True,
        },
        "response": {
            "mode": "symmetric_inverse_mass_weighted_projection",
            "perLayerAbsoluteRadialCorrectionMeters": {
                layer_id: rounded(value) for layer_id, value in response.items()
            },
            "bothSidesMoved": all(value > 0.0 for value in response.values()),
        },
        "settings": {
            "segments": SEGMENTS,
            "rings": RINGS,
            "states": len(STATES),
            "stepsPerState": STEPS_PER_STATE,
            "iterationsPerStep": ITERATIONS_PER_STEP,
            "constraintSweepsPerIteration": 2,
            "strategyCount": 2,
            "tuningTrialCount": 2,
        },
        "states": state_reports,
        "trajectory": trajectory,
        "finalMetrics": final_metrics,
        "topology": {
            "verticesPerLayer": SEGMENTS * RINGS,
            "trianglesPerLayer": SEGMENTS * (RINGS - 1) * 2,
            "unchanged": True,
        },
        "truth": {
            "realSimultaneousSolve": True,
            "sequentialSingleGarmentSolve": False,
            "integratedPhase13Acceptance": False,
            "mobileOrGpuExecution": False,
        },
        "integrity": {"reportHash": ""},
    }
    report["integrity"]["reportHash"] = canonical_hash({**report, "integrity": {"reportHash": ""}})
    return report


def validate_outfit_spec(spec: OutfitSpec) -> None:
    if len(spec.layers) < 2:
        raise LayerCollisionError("simultaneous_outfit_requires_multiple_layers")
    if not spec.opening_compatible:
        raise LayerCollisionError("incompatible_layer_openings")
    ids = [layer.layer_id for layer in spec.layers]
    if any(not layer_id for layer_id in ids):
        raise LayerCollisionError("missing_layer_id")
    if len(ids) != len(set(ids)):
        raise LayerCollisionError("duplicate_layer_id")
    orders = [layer.collision_order for layer in spec.layers]
    if orders != sorted(orders) or len(orders) != len(set(orders)):
        raise LayerCollisionError("layer_order_reversed_or_ambiguous")
    known = set(ids)
    _reject_cycle(spec.layers)
    for index, layer in enumerate(spec.layers):
        if index == 0:
            if layer.parent_layer_id is not None:
                raise LayerCollisionError("base_layer_parent_invalid")
        elif layer.parent_layer_id not in known:
            raise LayerCollisionError("missing_parent_layer_id")
    for index, layer in enumerate(spec.layers[1:], start=1):
        if layer.parent_layer_id != spec.layers[index - 1].layer_id:
            raise LayerCollisionError("non_adjacent_layer_parent")
    if spec.body_radius_meters <= 0.0 or spec.body_clearance_meters <= 0.0:
        raise LayerCollisionError("invalid_collision_body")
    for layer in spec.layers:
        if (
            layer.thickness_meters <= 0.0
            or layer.areal_density_kg_m2 <= 0.0
            or layer.radial_stiffness <= 0.0
        ):
            raise LayerCollisionError("invalid_layer_material")


def _reject_cycle(layers: tuple[LayerSpec, ...]) -> None:
    parents = {layer.layer_id: layer.parent_layer_id for layer in layers}
    for layer in layers:
        seen: set[str] = set()
        current: str | None = layer.layer_id
        while current is not None:
            if current in seen:
                raise LayerCollisionError("cyclic_layer_order")
            seen.add(current)
            current = parents.get(current)


def _integrate_motion(
    spec: OutfitSpec,
    radii: dict[str, list[float]],
    velocities: dict[str, list[float]],
    state_factor: float,
    step: int,
) -> None:
    for layer_index, layer in enumerate(spec.layers):
        values = radii[layer.layer_id]
        layer_velocities = velocities[layer.layer_id]
        compliance = 1.0 / layer.radial_stiffness
        damping = min(0.36, 0.08 + layer.areal_density_kg_m2 * 0.45)
        for index, radius in enumerate(values):
            angle_index = index % SEGMENTS
            ring_index = index // SEGMENTS
            angular = sin(2.0 * pi * angle_index / SEGMENTS + layer_index * 0.37)
            vertical = (ring_index - 1) * 0.35
            pulse = sin(pi * (step + 1) / STEPS_PER_STATE)
            forcing = state_factor * pulse * spec.motion_amplitude
            forcing *= (0.00038 + compliance * 0.065) * (1.0 + 0.16 * angular + 0.08 * vertical)
            rest_radius = spec.body_radius_meters + layer.initial_center_offset_meters
            restoring = (rest_radius - radius) * min(0.42, layer.radial_stiffness * 0.22)
            layer_velocities[index] = (layer_velocities[index] + forcing + restoring) * (
                1.0 - damping
            )
            values[index] += layer_velocities[index]


def _project_body(
    spec: OutfitSpec, radii: dict[str, list[float]], response: dict[str, float]
) -> None:
    inner = spec.layers[0]
    minimum = spec.body_radius_meters + spec.body_clearance_meters + inner.thickness_meters * 0.5
    values = radii[inner.layer_id]
    for index, radius in enumerate(values):
        if radius < minimum:
            correction = minimum - radius
            values[index] += correction
            response[inner.layer_id] += correction


def _project_adjacent_layers(
    spec: OutfitSpec, radii: dict[str, list[float]], response: dict[str, float]
) -> tuple[int, int]:
    tests = 0
    corrections = 0
    adjacent = list(zip(spec.layers, spec.layers[1:], strict=False))
    for inner, outer in [*adjacent, *reversed(adjacent)]:
        required = (
            0.5 * (inner.thickness_meters + outer.thickness_meters)
            + spec.inter_layer_clearance_meters
        )
        inner_values = radii[inner.layer_id]
        outer_values = radii[outer.layer_id]
        inverse_inner = 1.0 / inner.areal_density_kg_m2
        inverse_outer = 1.0 / outer.areal_density_kg_m2
        total_inverse = inverse_inner + inverse_outer
        for index, (inner_radius, outer_radius) in enumerate(
            zip(inner_values, outer_values, strict=True)
        ):
            tests += 1
            penetration = required - (outer_radius - inner_radius)
            if penetration <= 0.0:
                continue
            corrections += 1
            inward = penetration * inverse_inner / total_inverse
            outward = penetration * inverse_outer / total_inverse
            inner_values[index] -= inward
            outer_values[index] += outward
            response[inner.layer_id] += inward
            response[outer.layer_id] += outward
    return tests, corrections


def _measure(
    spec: OutfitSpec,
    radii: dict[str, list[float]],
    initial: dict[str, list[float]],
) -> dict[str, Any]:
    depths: list[float] = []
    signed_separations: list[float] = []
    contact_area = 0.0
    order_violations = 0
    for inner, outer in zip(spec.layers, spec.layers[1:], strict=False):
        required = (
            0.5 * (inner.thickness_meters + outer.thickness_meters)
            + spec.inter_layer_clearance_meters
        )
        for inner_radius, outer_radius in zip(
            radii[inner.layer_id], radii[outer.layer_id], strict=True
        ):
            separation = (
                outer_radius
                - inner_radius
                - 0.5 * (inner.thickness_meters + outer.thickness_meters)
            )
            signed_separations.append(separation)
            depth = max(0.0, required - (outer_radius - inner_radius))
            if depth > 1e-10:
                depths.append(depth)
                contact_area += depth * (2.0 * pi * max(inner_radius, 1e-6) / SEGMENTS)
            order_violations += int(outer_radius <= inner_radius)
    inner = spec.layers[0]
    body_clearances = [
        radius - spec.body_radius_meters - inner.thickness_meters * 0.5
        for radius in radii[inner.layer_id]
    ]
    strains: list[float] = []
    seam_cracks: list[float] = []
    opening_ratios: list[float] = []
    for layer in spec.layers:
        values = radii[layer.layer_id]
        rest = initial[layer.layer_id]
        strains.extend(
            abs(value - base) / max(base, 1e-9) for value, base in zip(values, rest, strict=True)
        )
        for ring in range(RINGS):
            start = ring * SEGMENTS
            end = start + SEGMENTS
            ring_values = values[start:end]
            seam_cracks.append(abs(ring_values[0] - ring_values[-1]))
        for ring in (0, RINGS - 1):
            start = ring * SEGMENTS
            mean_radius = sum(values[start : start + SEGMENTS]) / SEGMENTS
            rest_radius = sum(rest[start : start + SEGMENTS]) / SEGMENTS
            opening_ratios.append(mean_radius / rest_radius)
    return {
        "residualContactCount": len(depths),
        "maximumResidualDepthMeters": rounded(max(depths, default=0.0)),
        "residualContactAreaSquareMeters": rounded(contact_area),
        "minimumInterLayerSeparationMeters": rounded(min(signed_separations)),
        "minimumBodyClearanceMeters": rounded(min(body_clearances)),
        "maximumRadialStrain": rounded(max(strains, default=0.0)),
        "maximumSeamCrackMeters": rounded(max(seam_cracks, default=0.0)),
        "minimumOpeningRetention": rounded(min(opening_ratios, default=1.0)),
        "layerOrderViolationCount": order_violations,
        "bridgeConstraintCount": 0,
    }


def _project_coupled_stack(
    spec: OutfitSpec, radii: dict[str, list[float]], response: dict[str, float]
) -> int:
    offsets = [0.0]
    for inner, outer in zip(spec.layers, spec.layers[1:], strict=False):
        offsets.append(
            offsets[-1]
            + 0.5 * (inner.thickness_meters + outer.thickness_meters)
            + spec.inter_layer_clearance_meters
        )
    inner = spec.layers[0]
    lower_bound = (
        spec.body_radius_meters + spec.body_clearance_meters + inner.thickness_meters * 0.5
    )
    correction_count = 0
    for vertex in range(SEGMENTS * RINGS):
        blocks: list[dict[str, float | int]] = []
        for index, layer in enumerate(spec.layers):
            value = max(lower_bound, radii[layer.layer_id][vertex] - offsets[index])
            blocks.append(
                {
                    "start": index,
                    "end": index,
                    "weight": layer.areal_density_kg_m2,
                    "mean": value,
                }
            )
            while len(blocks) >= 2 and float(blocks[-2]["mean"]) > float(blocks[-1]["mean"]):
                right = blocks.pop()
                left = blocks.pop()
                weight = float(left["weight"]) + float(right["weight"])
                mean = (
                    float(left["mean"]) * float(left["weight"])
                    + float(right["mean"]) * float(right["weight"])
                ) / weight
                blocks.append(
                    {
                        "start": int(left["start"]),
                        "end": int(right["end"]),
                        "weight": weight,
                        "mean": max(lower_bound, mean),
                    }
                )
        projected = [0.0 for _ in spec.layers]
        for block in blocks:
            for index in range(int(block["start"]), int(block["end"]) + 1):
                projected[index] = float(block["mean"]) + offsets[index]
        for index, layer in enumerate(spec.layers):
            before = radii[layer.layer_id][vertex]
            delta = projected[index] - before
            if abs(delta) > 1e-15:
                correction_count += 1
                response[layer.layer_id] += abs(delta)
                radii[layer.layer_id][vertex] = projected[index]
    return correction_count


def _adjacent_pairs(layers: tuple[LayerSpec, ...]) -> list[tuple[str, str]]:
    return [
        (inner.layer_id, outer.layer_id) for inner, outer in zip(layers, layers[1:], strict=False)
    ]


def shell_vertices(spec: OutfitSpec, report: dict[str, Any]) -> list[tuple[float, float, float]]:
    """Return a diagnostic visualization shell that is never an evidence input."""

    radius = spec.body_radius_meters
    state_factor = len(report.get("states", [])) * 0.0
    return [
        (
            rounded((radius + state_factor) * cos(2.0 * pi * index / SEGMENTS)),
            rounded(ring * 0.2),
            rounded((radius + state_factor) * sin(2.0 * pi * index / SEGMENTS)),
        )
        for ring in range(RINGS)
        for index in range(SEGMENTS)
    ]


def summarize_trajectory(report: dict[str, Any]) -> dict[str, Any]:
    by_state: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in report["trajectory"]:
        by_state[str(item["stateId"])].append(item)
    return {
        state_id: {
            "samples": len(items),
            "startCount": items[0]["contactCount"],
            "endCount": items[-1]["contactCount"],
            "maximumDepthMeters": rounded(max(float(item["maximumDepthMeters"]) for item in items)),
        }
        for state_id, items in sorted(by_state.items())
    }
