from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import sqrt
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import MeshSet, Vec3
from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.simulation.reference_cloth_solver import flatten_mesh
from closy_forge.simulation.self_collision import seam_exclusion_pairs
from closy_forge.simulation_topology_v2.phy1_seam_support_v3 import load_phy1_v3_inputs
from closy_forge.simulation_topology_v2.seam_support_v3 import measure_seams

PHY_EVALUATOR_V4 = "closy.phy1.corrected_diagnostic_evaluator.v4"


def evaluate_phy1_trajectory_diagnostic_v4(root: Path) -> dict[str, Any]:
    """Re-score persisted PR #43 bytes without executing the cloth solver."""

    lock_path = root / "fixtures/phy1_seam_support_v3/experiment_lock.json"
    neutral_path = root / "docs/evidence/phy1_seam_support_v3/neutral_preflight.json"
    index_path = root / "docs/evidence/phy1_seam_support_v3/trajectory/index.json"
    lock = _object(lock_path)
    neutral = _object(neutral_path)
    index = _object(index_path)
    inputs = load_phy1_v3_inputs(root, lock)
    frames = _open_trajectory(root, index)
    solver = _mapping(_mapping(lock["configuration"])["solver"])
    thresholds = _mapping(lock["thresholds"])
    collision = _mapping(_mapping(lock["configuration"])["collision"])
    tail_window = int(solver["tailWindowFrames"])
    time_step = float(solver["timeStepSeconds"])
    if tail_window != 8 or len(frames) < tail_window + 1:
        raise ValueError("phy_v4_tail_window_invalid")
    masses = _particle_masses(inputs.rest_mesh, float(inputs.material["surfaceDensityKgM2"]))
    tail = frames[-(tail_window + 1) :]
    tail_motion = _tail_motion(tail, masses, time_step)
    centers = [_center_of_mass(frame, masses) for frame in frames]
    displacements = [_distance(center, centers[0]) for center in centers]
    rest_flat = flatten_mesh(inputs.rest_mesh)
    final_flat = flatten_mesh(frames[-1])
    seam_metrics = measure_seams(final_flat.positions, rest_flat.positions, inputs.seam_records)
    seam_metrics["maximumArclengthEaseResidual"] = _deformed_arclength_ease_residual(
        final_flat.positions, inputs.seam_records
    )
    exclusions = seam_exclusion_pairs(inputs.constraints, rest_flat.mesh_offsets)
    exclusion_rings = int(collision["stitchedNeighbourhoodExclusionRings"])
    if exclusion_rings != 1:
        raise ValueError("phy_v4_exclusion_ring_policy_unsupported")
    exclusions = _expand_vertex_exclusions_one_ring(inputs.rest_mesh, exclusions)
    support_history = _mapping(neutral["supports"])["history"]
    if not isinstance(support_history, list):
        raise ValueError("phy_v4_support_history_invalid")
    support_audit = _support_after_projection_audit(support_history)
    temporal = _rotation_invariant_temporal_audit(frames)
    observed = {
        "maximumTailVelocityMetersPerSecond": max(
            item["maximumVelocityMetersPerSecond"] for item in tail_motion
        ),
        "maximumTailKineticEnergyJoules": max(item["kineticEnergyJoules"] for item in tail_motion),
        "maximumCenterOfMassDisplacementMeters": max(displacements),
        "maximumArclengthEaseResidual": seam_metrics["maximumArclengthEaseResidual"],
        "maximumSeamCrackMeters": seam_metrics["maximumSeamCrackMeters"],
        "maximumTangentialSlipMeters": seam_metrics["maximumTangentialSlipMeters"],
        "trueInversionCount": temporal["trueInversionCount"],
    }
    checks = {
        "tailVelocity": observed["maximumTailVelocityMetersPerSecond"]
        <= float(thresholds["maximumTerminalVelocityMetersPerSecond"]),
        "tailKineticEnergy": observed["maximumTailKineticEnergyJoules"]
        <= float(thresholds["maximumTerminalKineticEnergyJoules"]),
        "centerOfMass": observed["maximumCenterOfMassDisplacementMeters"]
        <= float(thresholds["maximumCenterOfMassDisplacementMeters"]),
        "seamCrack": observed["maximumSeamCrackMeters"]
        <= float(thresholds["maximumSeamCrackMeters"]),
        "tangentialSlip": observed["maximumTangentialSlipMeters"]
        <= float(thresholds["maximumTangentialSlipMeters"]),
        "nonInversion": observed["trueInversionCount"] <= int(thresholds["maximumTrueInversions"]),
        "supportPostProjectionTraceAvailable": support_audit["status"] == "pass",
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "schemaVersion": 1,
        "evaluatorVersion": PHY_EVALUATOR_V4,
        "classification": "diagnostic_rescore_of_immutable_pr43_trajectory",
        "sourceAuthority": {
            "neutralPreflightPath": neutral_path.relative_to(root).as_posix(),
            "neutralPreflightSha256": sha256_file(neutral_path),
            "trajectoryIndexPath": index_path.relative_to(root).as_posix(),
            "trajectoryIndexSha256": sha256_file(index_path),
            "experimentLockPath": lock_path.relative_to(root).as_posix(),
            "experimentLockSha256": sha256_file(lock_path),
        },
        "definitions": {
            "terminalMotion": "eight persisted tail transitions; finite-difference velocity",
            "kineticEnergy": "0.5*m*v^2 with rest-area lumped areal-density mass",
            "centerOfMass": "mass-weighted displacement from persisted frame zero",
            "seamEase": "deformed seam frame with authored normalized arclength ease ratio",
            "supportResidual": "post-collision-projection residual only",
            "supportWork": "sum force_newtons * projected_displacement_meters in joules",
            "nonInversion": "rotation-invariant temporal area-degeneracy crossing",
        },
        "consumedFrozenFields": [
            "/configuration/solver/timeStepSeconds",
            "/configuration/solver/tailWindowFrames",
            "/configuration/collision/stitchedNeighbourhoodExclusionRings",
            "/thresholds/maximumTerminalVelocityMetersPerSecond",
            "/thresholds/maximumTerminalKineticEnergyJoules",
            "/thresholds/maximumCenterOfMassDisplacementMeters",
            "/thresholds/maximumTrueInversions",
            "/thresholds/maximumSeamCrackMeters",
            "/thresholds/maximumTangentialSlipMeters",
        ],
        "tailFrameMetrics": tail_motion,
        "centerOfMass": {
            "frameCount": len(centers),
            "maximumDisplacementMeters": _round(max(displacements)),
            "criterion": "maximum_mass_weighted_displacement_from_frame_zero",
        },
        "seam": seam_metrics,
        "collisionExclusions": {
            "stitchedNeighbourhoodExclusionRings": exclusion_rings,
            "excludedVertexPairCount": len(exclusions),
            "consumedByDiagnostic": True,
            "broadPairLabelExclusionsAllowed": False,
        },
        "supports": support_audit,
        "supportRelease": _support_release_audit(lock, support_history),
        "independentRepeat": {
            "status": "historical_only_not_re_evaluable",
            "reason": "pr43_persisted_only_one_trajectory_inventory",
            "copiedTrajectoryRejectedAsIndependentEvidence": True,
            "secondRunInvented": False,
        },
        "temporalNonInversion": temporal,
        "observed": {key: _round(float(value)) for key, value in observed.items()},
        "checks": checks,
        "diagnosticStatus": "pass" if not failed else "fail",
        "failedChecks": failed,
        "historicalOutcomeAuthority": {
            "predecessorOutcome": "A_neutral_preflight_failed_v3",
            "predecessorOutcomeUnchanged": True,
            "diagnosticValuesMayChangeBecauseDefinitionsCorrected": True,
            "physicalCandidateReran": False,
            "budgetConsumed": False,
            "budgetRefunded": False,
            "fullPhy1Executed": False,
            "ccdExecuted": False,
            "z2Executed": False,
            "runtimeV1RemainsSelected": True,
        },
    }


def evaluate_phy_microfixtures_v4() -> dict[str, Any]:
    stable = [
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [(0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)],
    ]
    collapsed = [
        stable[0],
        [(0.0, 0.0, 0.0), (0.5, 0.0, 0.0), (1.0, 0.0, 0.0)],
    ]
    stable_result = _triangle_sequence_inversion(stable)
    corrupt_result = _triangle_sequence_inversion(collapsed)
    support_pass = _support_after_projection_audit(
        [
            {
                "postProjectionResidualMeters": 0.001,
                "forceNewtons": 2.0,
                "projectedDisplacementMeters": 0.003,
            }
        ]
    )
    support_corrupt = _support_after_projection_audit(
        [{"maximumResidualMeters": 0.001, "supportEnergyJoules": 2.0}]
    )
    checks = {
        "rigidRotationDoesNotInvert": stable_result["trueInversionCount"] == 0,
        "collapsedTransitionDetected": corrupt_result["degenerateTransitionCount"] == 1,
        "supportWorkHasPhysicalUnits": support_pass["workJoules"] == 0.006,
        "preProjectionOnlySupportTraceRejected": support_corrupt["status"] == "not_available",
    }
    return {
        "evaluatorVersion": PHY_EVALUATOR_V4,
        "analytic": {
            "rigidRotation": stable_result,
            "collapsed": corrupt_result,
            "support": support_pass,
        },
        "corruptedTraces": {"preProjectionSupportOnly": support_corrupt},
        "checks": checks,
        "status": "pass" if all(checks.values()) else "fail",
    }


def _open_trajectory(root: Path, index: Mapping[str, Any]) -> list[MeshSet]:
    records = index.get("frames")
    if not isinstance(records, list) or index.get("frameCount") != len(records):
        raise ValueError("phy_v4_trajectory_index_invalid")
    base = root / "docs/evidence/phy1_seam_support_v3"
    frames: list[MeshSet] = []
    for expected, raw in enumerate(records):
        if not isinstance(raw, dict) or raw.get("frameIndex") != expected:
            raise ValueError("phy_v4_trajectory_order_invalid")
        path = base / str(raw["path"])
        if sha256_file(path) != raw.get("sha256"):
            raise ValueError("phy_v4_trajectory_hash_mismatch")
        frames.append(read_glb_meshset(path))
    return frames


def _tail_motion(frames: list[MeshSet], masses: list[float], dt: float) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for frame_index in range(1, len(frames)):
        previous = flatten_mesh(frames[frame_index - 1]).positions
        current = flatten_mesh(frames[frame_index]).positions
        if len(previous) != len(current) or len(current) != len(masses):
            raise ValueError("phy_v4_trajectory_topology_changed")
        speeds = [_distance(a, b) / dt for a, b in zip(previous, current, strict=True)]
        energy = sum(0.5 * mass * speed * speed for mass, speed in zip(masses, speeds, strict=True))
        records.append(
            {
                "tailOrdinal": frame_index,
                "maximumVelocityMetersPerSecond": _round(max(speeds, default=0.0)),
                "kineticEnergyJoules": _round(energy),
            }
        )
    return records


def _particle_masses(mesh: MeshSet, areal_density: float) -> list[float]:
    flat = flatten_mesh(mesh)
    masses = [0.0] * len(flat.positions)
    for mesh_index, panel in enumerate(mesh.meshes):
        offset = flat.mesh_offsets[mesh_index]
        for triangle in panel.triangles:
            a, b, c = (panel.vertices[index] for index in triangle)
            area = 0.5 * _length(_cross(_sub(b, a), _sub(c, a)))
            contribution = areal_density * area / 3.0
            for local in triangle:
                masses[offset + local] += contribution
    positive = [mass for mass in masses if mass > 0.0]
    minimum = (sum(positive) / len(positive)) * 0.1 if positive else 1e-12
    return [max(mass, minimum) for mass in masses]


def _deformed_arclength_ease_residual(
    positions: Sequence[Vec3], records: Sequence[Mapping[str, Any]]
) -> float:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record["seamId"]), []).append(record)
    residuals: list[float] = []
    for seam_records in grouped.values():
        ordered = sorted(
            seam_records,
            key=lambda item: int(_mapping(item.get("mapping")).get("ordinal", 0)),
        )
        first_points = [_span_position(positions, _mapping(item["first"])) for item in ordered]
        second_points = [_span_position(positions, _mapping(item["second"])) for item in ordered]
        first_length = sum(
            _distance(a, b) for a, b in zip(first_points, first_points[1:], strict=False)
        )
        second_length = sum(
            _distance(a, b) for a, b in zip(second_points, second_points[1:], strict=False)
        )
        expected_ratio = float(ordered[0].get("restEaseRatio", 1.0))
        if first_length <= 1e-12 or second_length <= 1e-12:
            residuals.append(float("inf"))
        else:
            residuals.append(abs(second_length / first_length - expected_ratio))
    return _round(max(residuals, default=0.0))


def _span_position(positions: Sequence[Vec3], span: Mapping[str, Any]) -> Vec3:
    first = positions[int(span["firstVertexIndex"])]
    second = positions[int(span["secondVertexIndex"])]
    weight = float(span["secondWeight"])
    return tuple(first[axis] * (1.0 - weight) + second[axis] * weight for axis in range(3))  # type: ignore[return-value]


def _expand_vertex_exclusions_one_ring(
    mesh: MeshSet, base: set[tuple[int, int]]
) -> set[tuple[int, int]]:
    flat = flatten_mesh(mesh)
    neighbours: dict[int, set[int]] = {index: {index} for index in range(len(flat.positions))}
    for mesh_index, panel in enumerate(mesh.meshes):
        offset = flat.mesh_offsets[mesh_index]
        for triangle in panel.triangles:
            absolute = [offset + value for value in triangle]
            for first in absolute:
                neighbours[first].update(absolute)
    expanded = set(base)
    for first, second in base:
        for near_first in neighbours[first]:
            for near_second in neighbours[second]:
                if near_first != near_second:
                    expanded.add((min(near_first, near_second), max(near_first, near_second)))
    return expanded


def _support_release_audit(
    lock: Mapping[str, Any], history: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    settings = _mapping(_mapping(lock["configuration"])["supports"])
    released = int(settings["fullyReleasedAtSubstep"])
    scored = int(settings["scoredMotionStartsAfterSubstep"])
    at_release = [record for record in history if int(record.get("substep", -1)) == released]
    checks = {
        "releaseFramePresent": len(at_release) == 1,
        "zeroStrengthAtReleaseFrame": len(at_release) == 1
        and float(at_release[0].get("strength", -1.0)) == 0.0,
        "zeroActiveSupportsAtReleaseFrame": len(at_release) == 1
        and int(at_release[0].get("activeSupportCount", -1)) == 0,
        "releasedNoLaterThanScoredMotion": released <= scored,
    }
    return {
        "fullyReleasedAtSubstep": released,
        "scoredMotionStartsAfterSubstep": scored,
        "checks": checks,
        "offByOneResolved": all(checks.values()),
        "status": "pass" if all(checks.values()) else "fail",
    }


def _center_of_mass(mesh: MeshSet, masses: list[float]) -> Vec3:
    positions = flatten_mesh(mesh).positions
    total = sum(masses)
    if len(positions) != len(masses) or total <= 0.0:
        raise ValueError("phy_v4_mass_inventory_invalid")
    return tuple(
        sum(mass * point[axis] for mass, point in zip(masses, positions, strict=True)) / total
        for axis in range(3)
    )  # type: ignore[return-value]


def _support_after_projection_audit(history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    required = {"postProjectionResidualMeters", "forceNewtons", "projectedDisplacementMeters"}
    if not history or any(not required <= set(record) for record in history):
        return {
            "status": "not_available",
            "reason": "historical_trace_lacks_post_projection_force_displacement_samples",
            "preProjectionResidualNotSubstituted": True,
            "workJoules": None,
        }
    maximum = max(float(record["postProjectionResidualMeters"]) for record in history)
    work = sum(
        float(record["forceNewtons"]) * float(record["projectedDisplacementMeters"])
        for record in history
    )
    return {
        "status": "pass",
        "maximumPostProjectionResidualMeters": _round(maximum),
        "workJoules": _round(work),
        "workUnit": "joule",
        "preProjectionResidualNotSubstituted": True,
    }


def _rotation_invariant_temporal_audit(frames: list[MeshSet]) -> dict[str, Any]:
    sequences: list[list[list[Vec3]]] = []
    for mesh_index, panel in enumerate(frames[0].meshes):
        for triangle in panel.triangles:
            sequences.append(
                [
                    [frame.meshes[mesh_index].vertices[index] for index in triangle]
                    for frame in frames
                ]
            )
    results = [_triangle_sequence_inversion(sequence) for sequence in sequences]
    return {
        "metric": "rotation_invariant_temporal_area_degeneracy_crossing",
        "triangleCount": len(results),
        "trueInversionCount": sum(int(result["trueInversionCount"]) for result in results),
        "degenerateTransitionCount": sum(
            int(result["degenerateTransitionCount"]) for result in results
        ),
        "fixedWorldNormalUsed": False,
    }


def _triangle_sequence_inversion(sequence: Sequence[Sequence[Vec3]]) -> dict[str, int]:
    areas = [0.5 * _length(_cross(_sub(tri[1], tri[0]), _sub(tri[2], tri[0]))) for tri in sequence]
    degenerate = sum(area <= 1e-12 for area in areas[1:])
    # A labelled 3-D material triangle can reverse only through zero area. This
    # criterion is invariant to arbitrary rigid rotation of the whole triangle.
    return {"trueInversionCount": degenerate, "degenerateTransitionCount": degenerate}


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError("phy_v4_object_required")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("phy_v4_mapping_required")
    return value


def _distance(a: Vec3, b: Vec3) -> float:
    return _length(_sub(a, b))


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(value: Vec3) -> float:
    return sqrt(sum(component * component for component in value))


def _round(value: float) -> float:
    return round(float(value), 12)
