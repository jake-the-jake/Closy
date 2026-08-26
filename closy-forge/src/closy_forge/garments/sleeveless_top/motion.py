from __future__ import annotations

from copy import deepcopy
from math import isfinite, sqrt
from typing import Any

from closy_forge.binding.binary_format import BindingFile
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes
from closy_forge.simulation.material_motion_suite import measure_motion_metrics
from closy_forge.simulation.material_physics import solver_material_payload
from closy_forge.simulation.reference_cloth_solver import (
    SOLVER_VERSION,
    settle_reference_cloth,
    simulate_reference_motion_state,
    simulation_state_json,
)

SLEEVELESS_MOTION_VERSION = "closy.sleeveless_top.motion_suite.d0.v1"
ARMHOLE_IDS = {
    "opening.sleeveless_top.armhole.left",
    "opening.sleeveless_top.armhole.right",
}


def build_sleeveless_motion_suite(
    *,
    rest_mesh: MeshSet,
    constraints: dict[str, Any],
    avatar_contract: dict[str, Any],
    preset_registry: dict[str, Any],
    binding: BindingFile,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], MeshSet]:
    preset_records: list[dict[str, Any]] = []
    states: dict[str, dict[str, Any]] = {}
    selected_settled: MeshSet | None = None
    selected_material: dict[str, Any] | None = None
    for preset_index, descriptor in enumerate(preset_registry["presets"]):
        preset_id = str(descriptor["presetId"])
        material = solver_material_payload(descriptor)
        result = settle_reference_cloth(rest_mesh, constraints, avatar_contract, material)
        settled_mesh = _quantize_mesh(result.settled_mesh)
        diagnostics = _quantize_numbers(result.diagnostics)
        metrics = measure_motion_metrics(rest_mesh, settled_mesh, constraints, diagnostics)
        armholes = _armhole_metrics(metrics)
        reconstructed = reconstruct_vertices(settled_mesh, binding)
        dense = _dense_seam_metrics(settled_mesh, binding, constraints)
        state = simulation_state_json(
            state_id=f"sleeveless_material_settle.{preset_id}",
            meshset=settled_mesh,
            source_mesh=rest_mesh,
            diagnostics=diagnostics,
        )
        state["materialPresetId"] = preset_id
        state["diagnosticsRef"] = (
            f"reports/material_motion_suite.json#/presetRecords/{preset_index}/diagnostics"
        )
        states[preset_id] = state
        preset_records.append(
            {
                "presetId": preset_id,
                "solverVersion": SOLVER_VERSION,
                "actualSolverRun": True,
                "diagnostics": diagnostics,
                "metrics": metrics,
                "armholeMetrics": armholes,
                "denseBinding": dense,
                "reconstructedVertexCount": len(reconstructed),
                "reconstructionFinite": all(
                    isfinite(component) for vertex in reconstructed for component in vertex
                ),
                "simulationContentHash": geometry_content_hash(settled_mesh),
            }
        )
        if preset_id == "material.cotton_jersey_d0_v1":
            selected_settled = settled_mesh
            selected_material = material
    if selected_settled is None or selected_material is None:
        raise ValueError("cotton jersey preset missing from sleeveless motion suite")

    stress = simulate_reference_motion_state(
        selected_settled,
        constraints,
        avatar_contract,
        selected_material,
        "opening_stress",
    )
    stress_mesh = _quantize_mesh(stress.mesh)
    stress_diagnostics = _quantize_numbers(stress.diagnostics)
    stress_metrics = measure_motion_metrics(
        selected_settled,
        stress_mesh,
        constraints,
        stress_diagnostics,
    )
    stress_armholes = _armhole_metrics(stress_metrics)
    stress_dense = _dense_seam_metrics(stress_mesh, binding, constraints)
    states["opening_stress"] = simulation_state_json(
        state_id="sleeveless.opening_stress",
        meshset=stress_mesh,
        source_mesh=selected_settled,
        diagnostics=stress_diagnostics,
    )
    states["opening_stress"]["diagnosticsRef"] = (
        "reports/material_motion_suite.json#/underarmStress/diagnostics"
    )
    content_hashes = {record["simulationContentHash"] for record in preset_records}
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "suiteVersion": SLEEVELESS_MOTION_VERSION,
        "suiteId": "motion.sleeveless_top.public_d0_v1",
        "garmentClass": "sleeveless_top",
        "presetRecords": preset_records,
        "underarmStress": {
            "stateId": stress.state_id,
            "actualSolverRun": True,
            "diagnostics": stress_diagnostics,
            "metrics": stress_metrics,
            "armholeMetrics": stress_armholes,
            "denseBinding": stress_dense,
            "accepted": (
                stress_armholes["collapsedArmholeCount"] == 0
                and stress_dense["maximumSeamCrackMeters"] <= 0.06
                and stress_metrics["invertedOrDegenerateTriangleCount"] == 0
                and stress_metrics["nonFinitePositionCount"] == 0
            ),
        },
        "crossPreset": {
            "allFourPresetsExecuted": len(preset_records) == 4,
            "allPresetStatesDistinct": len(content_hashes) == len(preset_records),
            "materialExtremesExecuted": {
                "lightweight": any(
                    record["presetId"] == "material.lightweight_knit_d0_v1"
                    for record in preset_records
                ),
                "heavy": any(
                    record["presetId"] == "material.heavy_jersey_d0_v1" for record in preset_records
                ),
                "woven": any(
                    record["presetId"] == "material.lightweight_woven_d0_v1"
                    for record in preset_records
                ),
            },
        },
        "readiness": {
            "sleevelessTopD0MotionExecuted": True,
            "armholesNonCollapsed": all(
                record["armholeMetrics"]["collapsedArmholeCount"] == 0 for record in preset_records
            )
            and stress_armholes["collapsedArmholeCount"] == 0,
            "productionGpuMotionAccepted": False,
            "realFabricCalibrationAccepted": False,
        },
        "integrity": {"suiteHash": ""},
    }
    report = _quantize_numbers(report)
    states = {state_id: _quantize_numbers(state) for state_id, state in states.items()}
    report["integrity"]["suiteHash"] = hash_sleeveless_motion_report(report)
    return report, states, selected_settled


def hash_sleeveless_motion_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    payload["integrity"]["suiteHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _armhole_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    armholes = [
        opening
        for opening in metrics["openingStability"]["openings"]
        if opening["openingId"] in ARMHOLE_IDS
    ]
    records = []
    for opening in armholes:
        rest = float(opening["restPerimeterMeters"])
        settled = float(opening["settledPerimeterMeters"])
        records.append(
            {
                **opening,
                "retentionRatio": _round(settled / rest) if rest > 1e-12 else 0.0,
            }
        )
    return {
        "armholeCount": len(records),
        "collapsedArmholeCount": sum(
            1 for record in records if record["collapsed"] or float(record["retentionRatio"]) < 0.35
        ),
        "armholes": records,
    }


def _dense_seam_metrics(
    meshset: MeshSet, binding: BindingFile, constraints: dict[str, Any]
) -> dict[str, Any]:
    reconstructed = reconstruct_vertices(meshset, binding)
    panel_points: dict[str, list[Vec3]] = {panel_id: [] for panel_id in binding_panel_ids(binding)}
    for record, point in zip(binding.records, reconstructed, strict=True):
        panel_id = binding_panel_ids(binding)[record.panel_table_index]
        panel_points[panel_id].append(point)
    seam_cracks: list[float] = []
    sliding: list[float] = []
    for constraint in constraints["constraints"]:
        a = _span_position(meshset, constraint["spanA"])
        b = _span_position(meshset, constraint["spanB"])
        panel_a = str(constraint["spanA"]["panelId"])
        panel_b = str(constraint["spanB"]["panelId"])
        dense_a = min(panel_points[panel_a], key=lambda point: _distance(point, a))
        dense_b = min(panel_points[panel_b], key=lambda point: _distance(point, b))
        seam_cracks.append(_distance(dense_a, dense_b))
        sliding.extend([_distance(dense_a, a), _distance(dense_b, b)])
    return {
        "authoritativeDenseBindingRun": True,
        "seamConstraintCount": len(seam_cracks),
        "maximumSeamCrackMeters": _round(max(seam_cracks, default=0.0)),
        "rmsSeamCrackMeters": _round(_rms(seam_cracks)),
        "maximumTangentialSlidingProxyMeters": _round(max(sliding, default=0.0)),
    }


def binding_panel_ids(binding: BindingFile) -> list[str]:
    # The binary stores stable panel-table indices; the family has a fixed lexical table.
    if binding.panel_count != 2:
        raise ValueError("sleeveless binding panel count mismatch")
    return ["panel.sleeveless_top.back", "panel.sleeveless_top.front"]


def _span_position(meshset: MeshSet, span: dict[str, Any]) -> Vec3:
    return meshset.meshes[int(span["meshIndex"])].vertices[int(span["vertexIndex"])]


def _distance(a: Vec3, b: Vec3) -> float:
    return sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def _rms(values: list[float]) -> float:
    return sqrt(sum(value * value for value in values) / len(values)) if values else 0.0


def _round(value: float) -> float:
    return round(float(value), 9)


def _quantize_mesh(meshset: MeshSet) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                name=mesh.name,
                panel_id=mesh.panel_id,
                vertices=[
                    (
                        round(float(vertex[0]), 8),
                        round(float(vertex[1]), 8),
                        round(float(vertex[2]), 8),
                    )
                    for vertex in mesh.vertices
                ],
                panel_uvs=mesh.panel_uvs,
                triangles=mesh.triangles,
                material_id=mesh.material_id,
            )
            for mesh in meshset.meshes
        ]
    )


def _quantize_numbers(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 8)
    if isinstance(value, dict):
        return {key: _quantize_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_quantize_numbers(item) for item in value]
    return value
