from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, cast

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

CANONICAL_POSITION_DIGITS = 6


@dataclass(frozen=True)
class MotionSuiteSpec:
    suite_version: str
    suite_id: str
    garment_class: str
    state_prefix: str
    stress_state_id: str
    panel_ids: tuple[str, ...]
    tracked_opening_ids: frozenset[str]
    preset_opening_key: str
    stress_report_key: str
    opening_count_key: str
    collapsed_count_key: str
    opening_records_key: str
    readiness_execution_key: str
    readiness_openings_key: str
    missing_preset_message: str
    normalize_signed_zero: bool = False


def build_material_motion_suite(
    *,
    spec: MotionSuiteSpec,
    rest_mesh: MeshSet,
    constraints: dict[str, Any],
    avatar_contract: dict[str, Any],
    preset_registry: dict[str, Any],
    binding: BindingFile,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], MeshSet]:
    panel_ids = binding_panel_ids(binding, spec.panel_ids)
    preset_records: list[dict[str, Any]] = []
    states: dict[str, dict[str, Any]] = {}
    selected_settled: MeshSet | None = None
    selected_material: dict[str, Any] | None = None
    for preset_index, descriptor in enumerate(preset_registry["presets"]):
        preset_id = str(descriptor["presetId"])
        material = solver_material_payload(descriptor)
        result = settle_reference_cloth(
            rest_mesh,
            constraints,
            avatar_contract,
            material,
            canonical_position_digits=CANONICAL_POSITION_DIGITS,
        )
        settled_mesh = quantize_mesh(
            result.settled_mesh, normalize_signed_zero=spec.normalize_signed_zero
        )
        diagnostics = canonicalize_diagnostics(result.diagnostics)
        metrics = measure_motion_metrics(rest_mesh, settled_mesh, constraints, diagnostics)
        openings = tracked_opening_metrics(metrics, spec)
        reconstructed = reconstruct_vertices(settled_mesh, binding)
        dense = dense_seam_metrics(settled_mesh, binding, constraints, panel_ids)
        state = simulation_state_json(
            state_id=f"{spec.state_prefix}_material_settle.{preset_id}",
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
                spec.preset_opening_key: openings,
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
        raise ValueError(spec.missing_preset_message)

    stress = simulate_reference_motion_state(
        selected_settled,
        constraints,
        avatar_contract,
        selected_material,
        "opening_stress",
        canonical_position_digits=CANONICAL_POSITION_DIGITS,
    )
    stress_mesh = quantize_mesh(stress.mesh, normalize_signed_zero=spec.normalize_signed_zero)
    stress_diagnostics = canonicalize_diagnostics(stress.diagnostics)
    stress_metrics = measure_motion_metrics(
        selected_settled,
        stress_mesh,
        constraints,
        stress_diagnostics,
    )
    stress_openings = tracked_opening_metrics(stress_metrics, spec)
    stress_dense = dense_seam_metrics(stress_mesh, binding, constraints, panel_ids)
    states["opening_stress"] = simulation_state_json(
        state_id=spec.stress_state_id,
        meshset=stress_mesh,
        source_mesh=selected_settled,
        diagnostics=stress_diagnostics,
    )
    states["opening_stress"]["diagnosticsRef"] = (
        f"reports/material_motion_suite.json#/{spec.stress_report_key}/diagnostics"
    )
    content_hashes = {record["simulationContentHash"] for record in preset_records}
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "suiteVersion": spec.suite_version,
        "suiteId": spec.suite_id,
        "garmentClass": spec.garment_class,
        "presetRecords": preset_records,
        spec.stress_report_key: {
            "stateId": stress.state_id,
            "actualSolverRun": True,
            "diagnostics": stress_diagnostics,
            "metrics": stress_metrics,
            spec.preset_opening_key: stress_openings,
            "denseBinding": stress_dense,
            "accepted": (
                stress_openings[spec.collapsed_count_key] == 0
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
            spec.readiness_execution_key: True,
            spec.readiness_openings_key: all(
                record[spec.preset_opening_key][spec.collapsed_count_key] == 0
                for record in preset_records
            )
            and stress_openings[spec.collapsed_count_key] == 0,
            "productionGpuMotionAccepted": False,
            "realFabricCalibrationAccepted": False,
        },
        "integrity": {"suiteHash": ""},
    }
    report = quantize_numbers(report)
    states = {state_id: quantize_numbers(state) for state_id, state in states.items()}
    report["integrity"]["suiteHash"] = hash_motion_report(report)
    return report, states, selected_settled


def hash_motion_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    payload["integrity"]["suiteHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def tracked_opening_metrics(metrics: dict[str, Any], spec: MotionSuiteSpec) -> dict[str, Any]:
    openings = [
        opening
        for opening in metrics["openingStability"]["openings"]
        if opening["openingId"] in spec.tracked_opening_ids
    ]
    records = []
    for opening in openings:
        rest = float(opening["restPerimeterMeters"])
        settled = float(opening["settledPerimeterMeters"])
        records.append(
            {
                **opening,
                "retentionRatio": round_metric(settled / rest) if rest > 1e-12 else 0.0,
            }
        )
    return {
        spec.opening_count_key: len(records),
        spec.collapsed_count_key: sum(
            1 for record in records if record["collapsed"] or float(record["retentionRatio"]) < 0.35
        ),
        spec.opening_records_key: records,
    }


def dense_seam_metrics(
    meshset: MeshSet,
    binding: BindingFile,
    constraints: dict[str, Any],
    panel_ids: tuple[str, ...],
) -> dict[str, Any]:
    reconstructed = reconstruct_vertices(meshset, binding)
    panel_points: dict[str, list[Vec3]] = {panel_id: [] for panel_id in panel_ids}
    for record, point in zip(binding.records, reconstructed, strict=True):
        panel_id = panel_ids[record.panel_table_index]
        panel_points[panel_id].append(point)
    seam_cracks: list[float] = []
    sliding: list[float] = []
    for constraint in constraints["constraints"]:
        a = span_position(meshset, constraint["spanA"])
        b = span_position(meshset, constraint["spanB"])
        panel_a = str(constraint["spanA"]["panelId"])
        panel_b = str(constraint["spanB"]["panelId"])
        dense_a = min(panel_points[panel_a], key=lambda point: distance(point, a))
        dense_b = min(panel_points[panel_b], key=lambda point: distance(point, b))
        seam_cracks.append(distance(dense_a, dense_b))
        sliding.extend([distance(dense_a, a), distance(dense_b, b)])
    return {
        "authoritativeDenseBindingRun": True,
        "seamConstraintCount": len(seam_cracks),
        "maximumSeamCrackMeters": round_metric(max(seam_cracks, default=0.0)),
        "rmsSeamCrackMeters": round_metric(rms(seam_cracks)),
        "maximumTangentialSlidingProxyMeters": round_metric(max(sliding, default=0.0)),
    }


def binding_panel_ids(binding: BindingFile, panel_ids: tuple[str, ...]) -> tuple[str, ...]:
    if binding.panel_count != len(panel_ids):
        raise ValueError("binding panel count does not match garment family specification")
    return panel_ids


def span_position(meshset: MeshSet, span: dict[str, Any]) -> Vec3:
    return meshset.meshes[int(span["meshIndex"])].vertices[int(span["vertexIndex"])]


def distance(a: Vec3, b: Vec3) -> float:
    return sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def rms(values: list[float]) -> float:
    return sqrt(sum(value * value for value in values) / len(values)) if values else 0.0


def round_metric(value: float) -> float:
    return round(float(value), 9)


def quantize_mesh(meshset: MeshSet, *, normalize_signed_zero: bool = False) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                name=mesh.name,
                panel_id=mesh.panel_id,
                vertices=[
                    (
                        canonical_number(vertex[0], 8, normalize_signed_zero),
                        canonical_number(vertex[1], 8, normalize_signed_zero),
                        canonical_number(vertex[2], 8, normalize_signed_zero),
                    )
                    for vertex in mesh.vertices
                ],
                panel_uvs=[
                    (
                        canonical_number(uv[0], CANONICAL_POSITION_DIGITS, normalize_signed_zero),
                        canonical_number(uv[1], CANONICAL_POSITION_DIGITS, normalize_signed_zero),
                    )
                    for uv in mesh.panel_uvs
                ],
                triangles=mesh.triangles,
                material_id=mesh.material_id,
            )
            for mesh in meshset.meshes
        ]
    )


def canonical_number(value: float, digits: int, normalize_signed_zero: bool) -> float:
    canonical = round(float(value), digits)
    return 0.0 if normalize_signed_zero and canonical == 0.0 else canonical


def quantize_numbers(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 8)
    if isinstance(value, dict):
        return {key: quantize_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [quantize_numbers(item) for item in value]
    return value


def canonicalize_diagnostics(diagnostics: dict[str, Any]) -> dict[str, Any]:
    canonical = cast(dict[str, Any], quantize_numbers(diagnostics))
    energy_history = canonical.get("energyHistory")
    if isinstance(energy_history, list):
        canonical["energyHistory"] = [round(float(value), 6) for value in energy_history]
    return canonical
