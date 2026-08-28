from __future__ import annotations

from copy import deepcopy
from math import isfinite, sqrt
from typing import Any

from closy_forge.binding.binary_format import BindingFile
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.geometry.mesh_model import MeshSet, Vec3
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, topology_hash
from closy_forge.simulation.material_physics import solver_material_payload
from closy_forge.simulation.reference_cloth_solver import (
    SOLVER_VERSION,
    flatten_mesh,
    settle_reference_cloth,
    simulation_state_json,
)
from closy_forge.simulation.seam_mapping import span_position_flat

MATERIAL_MOTION_SUITE_VERSION = "closy.material_motion_suite.d0.v1"
MATERIAL_MOTION_CANONICAL_POSITION_DIGITS = 9


def build_material_motion_suite(
    *,
    rest_mesh: MeshSet,
    constraints: dict[str, Any],
    avatar_contract: dict[str, Any],
    preset_registry: dict[str, Any],
    binding: BindingFile,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Run the actual CPU cloth settle and dense reconstruction for every D0 preset."""

    records: list[dict[str, Any]] = []
    states: dict[str, dict[str, Any]] = {}
    for descriptor in preset_registry.get("presets", []):
        preset_id = str(descriptor["presetId"])
        material = solver_material_payload(descriptor)
        result = settle_reference_cloth(
            rest_mesh,
            constraints,
            avatar_contract,
            material,
            canonical_position_digits=MATERIAL_MOTION_CANONICAL_POSITION_DIGITS,
        )
        settled = result.settled_mesh
        reconstructed = reconstruct_vertices(settled, binding)
        metrics = measure_motion_metrics(rest_mesh, settled, constraints, result.diagnostics)
        state = simulation_state_json(
            state_id=f"material_settle.{preset_id}",
            meshset=settled,
            source_mesh=rest_mesh,
            diagnostics=result.diagnostics,
        )
        state["materialPresetId"] = preset_id
        state["materialDescriptorHash"] = descriptor["integrity"]["descriptorHash"]
        state["bindingReconstructionHash"] = _hash_positions(reconstructed)
        states[preset_id] = state
        finite_reconstruction = all(
            isfinite(component) for vertex in reconstructed for component in vertex
        )
        execution_accepted = (
            metrics["nonFinitePositionCount"] == 0
            and metrics["invertedOrDegenerateTriangleCount"] == 0
            and finite_reconstruction
            and len(reconstructed) == len(binding.records)
        )
        quality_failures = _quality_failures(metrics)
        records.append(
            {
                "presetId": preset_id,
                "descriptorHash": descriptor["integrity"]["descriptorHash"],
                "execution": {
                    "actualSolverRun": True,
                    "solverVersion": SOLVER_VERSION,
                    "backend": "deterministic_cpu_reference_xpbd",
                    "convergenceState": result.diagnostics["convergenceState"],
                    "acceptedForBoundedExecutionEvidence": execution_accepted,
                    "acceptedForD0MotionQuality": not quality_failures,
                    "motionQualityFailureReasons": quality_failures,
                },
                "settings": result.diagnostics["settings"],
                "metrics": metrics,
                "binding": {
                    "authoritativeDenseBindingRun": True,
                    "reconstructionPath": "persisted_barycentric_dense_binding_only",
                    "reconstructedVertexCount": len(reconstructed),
                    "reconstructionFinite": finite_reconstruction,
                    "reconstructionHash": _hash_positions(reconstructed),
                    "simulationTopologyHash": topology_hash(settled),
                    "simulationContentHash": geometry_content_hash(settled),
                },
                "limitations": {
                    "unresolvedSelfCollisionContacts": metrics["selfCollisionCount"],
                    "continuousCollisionDetection": "unsupported",
                    "productionGpuRun": False,
                    "realFabricCalibrationRun": False,
                },
            }
        )

    execution_accepted = all(
        record["execution"]["acceptedForBoundedExecutionEvidence"] for record in records
    )
    motion_quality_accepted = all(
        record["execution"]["acceptedForD0MotionQuality"] for record in records
    )
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "suiteVersion": MATERIAL_MOTION_SUITE_VERSION,
        "suiteId": "material_motion.fixed_avatar_tshirt_public_d0_v1",
        "presetRegistryVersion": preset_registry.get("registryVersion"),
        "presetRegistryHash": preset_registry.get("integrity", {}).get("registryHash"),
        "sourceTopologyHash": topology_hash(rest_mesh),
        "presets": records,
        "crossPresetEvidence": {
            "allPresetStatesDistinct": len(
                {record["binding"]["simulationContentHash"] for record in records}
            )
            == len(records),
            "actualSolverSettingsDiffer": len(
                {canonical_dumps(record["settings"]) for record in records}
            )
            == len(records),
        },
        "readiness": {
            "executedForD0FixedAvatarTshirt": execution_accepted,
            "acceptedForD0FixedAvatarTshirt": motion_quality_accepted,
            "acceptedAsRealFabricCalibration": False,
            "acceptedForProductionGpuMotion": False,
            "acceptedForPrivateUserMaterialEstimation": False,
        },
        "truth": {
            "fixedPublicAvatarFixture": True,
            "fixedPublicTshirtFixture": True,
            "actualCpuSolverRun": True,
            "actualDenseBindingReconstructionRun": True,
            "realFabricMeasurementRun": False,
            "learnedMaterialInferenceRun": False,
        },
        "integrity": {"suiteHash": ""},
    }
    report["integrity"]["suiteHash"] = _hash_report(report)
    return report, states


def _quality_failures(metrics: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    checks = (
        (not metrics["converged"], "solver_not_converged"),
        (metrics["maximumDisplacementMeters"] > 1.0, "maximum_displacement_above_1m"),
        (metrics["energyDecayProxy"]["decayed"] is not True, "energy_did_not_decay"),
        (metrics["maximumWarpStrain"] > 8.0, "warp_strain_above_d0_bound"),
        (metrics["maximumWeftStrain"] > 8.0, "weft_strain_above_d0_bound"),
        (metrics["maximumShearDiagonalStrain"] > 8.0, "shear_strain_above_d0_bound"),
        (metrics["maximumSeamResidualMeters"] > 0.05, "seam_residual_above_5cm"),
        (
            metrics["openingStability"]["maximumPerimeterDriftMeters"] > 0.08,
            "opening_drift_above_8cm",
        ),
        (metrics["maximumBodyPenetrationMeters"] > 0.012, "body_penetration_above_12mm"),
        (metrics["selfCollisionCount"] > 0, "unresolved_self_collision_contacts"),
        (
            metrics["invertedOrDegenerateTriangleCount"] > 0,
            "inverted_or_degenerate_triangles",
        ),
        (metrics["nonFinitePositionCount"] > 0, "non_finite_positions"),
    )
    for failed, code in checks:
        if failed:
            failures.append(code)
    return failures


def measure_motion_metrics(
    rest_mesh: MeshSet,
    settled_mesh: MeshSet,
    constraints: dict[str, Any],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    rest = flatten_mesh(rest_mesh)
    settled = flatten_mesh(settled_mesh)
    displacement = [_distance(a, b) for a, b in zip(rest.positions, settled.positions, strict=True)]
    directional = _directional_strain(rest_mesh, settled_mesh)
    seam_residuals = _seam_residuals(settled_mesh, constraints)
    opening = _opening_stability(rest_mesh, settled_mesh, constraints)
    energy = [float(value) for value in diagnostics.get("energyHistory", [])]
    initial_energy = energy[0] if energy else 0.0
    final_energy = energy[-1] if energy else 0.0
    return {
        "converged": diagnostics.get("convergenceState") == "converged",
        "maximumDisplacementMeters": _round(max(displacement, default=0.0)),
        "meanDisplacementMeters": _round(sum(displacement) / max(1, len(displacement))),
        "energyDecayProxy": {
            "kind": "final_to_initial_deterministic_energy_ratio",
            "initial": _round(initial_energy),
            "final": _round(final_energy),
            "ratio": _round(final_energy / initial_energy) if initial_energy > 1e-12 else 0.0,
            "decayed": final_energy <= initial_energy,
        },
        "maximumWarpStrain": directional["maximumWarpStrain"],
        "maximumWeftStrain": directional["maximumWeftStrain"],
        "maximumShearDiagonalStrain": directional["maximumShearDiagonalStrain"],
        "maximumSeamResidualMeters": _round(max(seam_residuals, default=0.0)),
        "rmsSeamResidualMeters": _round(_rms(seam_residuals)),
        "openingStability": opening,
        "maximumBodyPenetrationMeters": _round(
            float(diagnostics.get("maximumBodyPenetrationMeters", 0.0))
        ),
        "selfCollisionCount": int(
            diagnostics.get("selfCollision", {}).get("unresolvedContactCount", 0)
        ),
        "invertedOrDegenerateTriangleCount": int(
            diagnostics.get("invertedOrDegenerateElementCount", 0)
        ),
        "nonFinitePositionCount": sum(
            1
            for vertex in settled.positions
            if not all(isfinite(component) for component in vertex)
        ),
    }


def _directional_strain(rest: MeshSet, settled: MeshSet) -> dict[str, float]:
    values: dict[str, list[float]] = {"warp": [], "weft": [], "shear": []}
    for rest_panel, settled_panel in zip(rest.meshes, settled.meshes, strict=True):
        seen: set[tuple[int, int]] = set()
        for triangle in rest_panel.triangles:
            edges = (
                (triangle[0], triangle[1]),
                (triangle[1], triangle[2]),
                (triangle[2], triangle[0]),
            )
            for a, b in edges:
                edge = (min(a, b), max(a, b))
                if edge in seen:
                    continue
                seen.add(edge)
                rest_length = _distance(rest_panel.vertices[a], rest_panel.vertices[b])
                if rest_length <= 1e-12:
                    continue
                current_length = _distance(settled_panel.vertices[a], settled_panel.vertices[b])
                uv_a, uv_b = rest_panel.panel_uvs[a], rest_panel.panel_uvs[b]
                du, dv = abs(uv_b[0] - uv_a[0]), abs(uv_b[1] - uv_a[1])
                largest = max(du, dv)
                kind = (
                    "shear"
                    if largest > 0.0 and min(du, dv) / largest >= 0.22
                    else ("warp" if dv > du else "weft")
                )
                values[kind].append(abs(current_length / rest_length - 1.0))
    return {
        "maximumWarpStrain": _round(max(values["warp"], default=0.0)),
        "maximumWeftStrain": _round(max(values["weft"], default=0.0)),
        "maximumShearDiagonalStrain": _round(max(values["shear"], default=0.0)),
    }


def _seam_residuals(meshset: MeshSet, constraints: dict[str, Any]) -> list[float]:
    offsets = flatten_mesh(meshset).mesh_offsets
    positions = flatten_mesh(meshset).positions
    residuals: list[float] = []
    for constraint in constraints.get("constraints", []):
        span_a = constraint["spanA"]
        span_b = constraint["spanB"]
        residuals.append(
            _distance(
                span_position_flat(positions, offsets, span_a),
                span_position_flat(positions, offsets, span_b),
            )
        )
    return residuals


def _opening_stability(
    rest_mesh: MeshSet, settled_mesh: MeshSet, constraints: dict[str, Any]
) -> dict[str, Any]:
    openings: list[dict[str, Any]] = []
    for opening in constraints.get("openings", []):
        rest_length = _opening_length(rest_mesh, opening)
        settled_length = _opening_length(settled_mesh, opening)
        openings.append(
            {
                "openingId": str(opening["id"]),
                "restPerimeterMeters": _round(rest_length),
                "settledPerimeterMeters": _round(settled_length),
                "driftMeters": _round(abs(settled_length - rest_length)),
                "collapsed": settled_length <= max(1e-6, rest_length * 0.2),
            }
        )
    return {
        "openingCount": len(openings),
        "collapsedOpeningCount": sum(1 for opening in openings if opening["collapsed"]),
        "maximumPerimeterDriftMeters": _round(
            max((float(opening["driftMeters"]) for opening in openings), default=0.0)
        ),
        "openings": openings,
    }


def _opening_length(meshset: MeshSet, opening: dict[str, Any]) -> float:
    total = 0.0
    for edge in opening.get("boundaryEdges", []):
        mesh = meshset.meshes[int(edge["meshIndex"])]
        indices = [int(value) for value in edge.get("vertexIndices", [])]
        total += sum(
            _distance(mesh.vertices[a], mesh.vertices[b])
            for a, b in zip(indices, indices[1:], strict=False)
        )
    return total


def _hash_positions(positions: list[Vec3]) -> str:
    payload = [[_round(component) for component in vertex] for vertex in positions]
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _hash_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    payload["integrity"]["suiteHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _distance(a: Vec3, b: Vec3) -> float:
    return sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def _rms(values: list[float]) -> float:
    return sqrt(sum(value * value for value in values) / len(values)) if values else 0.0


def _round(value: float) -> float:
    return round(float(value), 9)
