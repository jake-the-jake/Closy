from __future__ import annotations

from collections import Counter
from copy import deepcopy
from math import sqrt
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import MeshSet, Vec2, Vec3, mesh_bounds
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)

GEOMETRY_BINDING_CANDIDATE_VERSION = "closy.geometry_binding_candidate.panel_uv_nearest.v1"

_PANEL_UV_EXACT_MATCH_TOLERANCE = 1e-6


def build_geometry_binding_candidate_report(
    *,
    garment_id: str,
    garment_class: str,
    semantic_transfer_report: dict[str, Any],
    cleanup_asset_path: Path,
    simulation_mesh: MeshSet,
    simulation_mesh_path: str,
) -> dict[str, Any]:
    """Build a rejected bindability report for cleanup-preview geometry.

    This stage proves the cleanup preview can be deterministically associated
    with the canonical simulation topology via panel-space UVs. It intentionally
    does not write or accept a runtime binding, because deformation continuity,
    seam handling and clean-geometry acceptance still need later validation.
    """

    cleanup_mesh = read_glb_meshset(cleanup_asset_path)
    mappings = _candidate_mappings(cleanup_mesh, simulation_mesh)
    panel_summaries = _panel_summaries(mappings)
    aggregate = _aggregate(mappings, semantic_transfer_report)
    candidate_complete = (
        aggregate["unmappedVertexCount"] == 0
        and aggregate["wrongPanelMatchCount"] == 0
        and aggregate["maxPanelUvDistance"] <= _PANEL_UV_EXACT_MATCH_TOLERANCE
    )
    blocking_reasons = [
        "runtime_binding_file_not_generated",
        "deformation_validation_not_run",
        "canonical_acceptance_gate_not_run",
    ]
    if int(semantic_transfer_report["aggregate"].get("ambiguousBoundaryEdgeCount", 0)) > 0:
        blocking_reasons.append("multi_seam_boundary_spans_require_split_before_binding")

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "binding_candidate.cleanup_preview_tshirt_visual_geometry_v1",
        "stageVersion": GEOMETRY_BINDING_CANDIDATE_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceGeometrySemanticTransferId": semantic_transfer_report["reportId"],
        "sourceGeometrySemanticTransferHash": semantic_transfer_report["integrity"][
            "geometrySemanticTransferHash"
        ],
        "sourceGeometryCleanupResultId": semantic_transfer_report["sourceGeometryCleanupResultId"],
        "sourceGeometryCleanupResultHash": semantic_transfer_report[
            "sourceGeometryCleanupResultHash"
        ],
        "inputCleanupAsset": {
            "path": semantic_transfer_report["inputAsset"]["path"],
            "sourceAssetHash": sha256_file(cleanup_asset_path),
            "byteSize": cleanup_asset_path.stat().st_size,
            "canonicalUseAllowed": False,
            "purpose": semantic_transfer_report["inputAsset"]["purpose"],
        },
        "targetSimulationMesh": {
            "path": simulation_mesh_path,
            "topologyHash": topology_hash(simulation_mesh),
            "contentHash": geometry_content_hash(simulation_mesh),
            "meshCount": len(simulation_mesh.meshes),
            "vertexCount": simulation_mesh.vertex_count,
            "triangleCount": simulation_mesh.triangle_count,
            "bounds": mesh_bounds(simulation_mesh),
            "state": "settled_reference_simulation_topology",
        },
        "candidateBinding": {
            "type": "panel_uv_nearest_simulation_vertex",
            "runtimeFormat": "report_only_not_CLSYBND1",
            "recordCount": len(mappings),
            "recordsWritten": False,
            "panelUvTolerance": _PANEL_UV_EXACT_MATCH_TOLERANCE,
            "normalOffsetMode": "measured_but_not_applied",
        },
        "vertexMappings": mappings,
        "panelSummaries": panel_summaries,
        "aggregate": aggregate,
        "execution": {
            "candidateBindingRun": True,
            "simulationBindingRun": False,
            "runtimeBindingWritten": False,
            "deformationValidationRun": False,
            "repairRun": False,
            "retopologyRun": False,
            "cleanProposalRun": False,
        },
        "readiness": {
            "status": "binding_candidate_generated_validation_pending"
            if candidate_complete
            else "binding_candidate_partial",
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": False,
            "nextExecutableStage": "accepted_binding_generation_and_deformation_validation",
            "blockingReasons": blocking_reasons,
        },
        "quality": {
            "status": "partial_pass_rejected" if candidate_complete else "warn",
            "candidateCompleteness": aggregate["candidateCompleteness"],
            "maxPanelUvDistance": aggregate["maxPanelUvDistance"],
            "rmsPanelUvDistance": aggregate["rmsPanelUvDistance"],
            "maxRestToSimulationOffsetMeters": aggregate["maxRestToSimulationOffsetMeters"],
            "rmsRestToSimulationOffsetMeters": aggregate["rmsRestToSimulationOffsetMeters"],
            "acceptedForCleanProposal": False,
            "warnings": [
                "binding_candidate_report_only_not_runtime_binding",
                "deformation_validation_not_run",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"geometryBindingCandidateHash": ""},
    }
    report["integrity"]["geometryBindingCandidateHash"] = hash_geometry_binding_candidate_report(
        report
    )
    return report


def hash_geometry_binding_candidate_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["geometryBindingCandidateHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _candidate_mappings(cleanup_mesh: MeshSet, simulation_mesh: MeshSet) -> list[dict[str, Any]]:
    sim_lookup = _simulation_lookup(simulation_mesh)
    mappings: list[dict[str, Any]] = []
    for cleanup_mesh_index, mesh in sorted(
        enumerate(cleanup_mesh.meshes), key=lambda item: (item[1].panel_id, item[1].name, item[0])
    ):
        panel_candidates = sim_lookup["verticesByPanel"].get(mesh.panel_id, [])
        for cleanup_vertex_index, (cleanup_position, cleanup_uv) in enumerate(
            zip(mesh.vertices, mesh.panel_uvs, strict=True)
        ):
            nearest = _nearest_panel_uv(cleanup_uv, panel_candidates)
            if nearest is None:
                mappings.append(
                    {
                        "cleanupMeshIndex": cleanup_mesh_index,
                        "cleanupMeshName": mesh.name,
                        "cleanupVertexIndex": cleanup_vertex_index,
                        "panelId": mesh.panel_id,
                        "cleanupPanelUv": _vec2_json(cleanup_uv),
                        "simulationMeshIndex": None,
                        "simulationVertexIndex": None,
                        "simulationTriangleIndex": None,
                        "barycentric": None,
                        "panelUvDistance": None,
                        "restToSimulationOffsetMeters": None,
                        "status": "unmapped_panel_missing",
                    }
                )
                continue
            (
                simulation_mesh_index,
                simulation_vertex_index,
                simulation_uv,
                simulation_position,
            ) = nearest
            triangle_binding = sim_lookup["firstTriangleByVertex"].get(
                (simulation_mesh_index, simulation_vertex_index)
            )
            status = "mapped_exact_panel_uv"
            if triangle_binding is None:
                status = "mapped_vertex_without_triangle"
            panel_uv_distance = _distance2(cleanup_uv, simulation_uv)
            if panel_uv_distance > _PANEL_UV_EXACT_MATCH_TOLERANCE:
                status = "mapped_nearest_panel_uv"
            mappings.append(
                {
                    "cleanupMeshIndex": cleanup_mesh_index,
                    "cleanupMeshName": mesh.name,
                    "cleanupVertexIndex": cleanup_vertex_index,
                    "panelId": mesh.panel_id,
                    "cleanupPanelUv": _vec2_json(cleanup_uv),
                    "simulationMeshIndex": simulation_mesh_index,
                    "simulationVertexIndex": simulation_vertex_index,
                    "simulationTriangleIndex": None
                    if triangle_binding is None
                    else triangle_binding["globalTriangleIndex"],
                    "barycentric": None
                    if triangle_binding is None
                    else triangle_binding["barycentric"],
                    "panelUvDistance": _round(panel_uv_distance),
                    "restToSimulationOffsetMeters": _round(
                        _distance3(cleanup_position, simulation_position)
                    ),
                    "status": status,
                }
            )
    return mappings


def _simulation_lookup(simulation_mesh: MeshSet) -> dict[str, Any]:
    vertices_by_panel: dict[str, list[tuple[int, int, Vec2, Vec3]]] = {}
    first_triangle_by_vertex: dict[tuple[int, int], dict[str, Any]] = {}
    global_triangle_index = 0
    for mesh_index, mesh in enumerate(simulation_mesh.meshes):
        vertices_by_panel.setdefault(mesh.panel_id, [])
        for vertex_index, (uv, position) in enumerate(
            zip(mesh.panel_uvs, mesh.vertices, strict=True)
        ):
            vertices_by_panel[mesh.panel_id].append((mesh_index, vertex_index, uv, position))
        for tri in mesh.triangles:
            for barycentric, vertex_index in [
                ([0.0, 0.0, 1.0], tri[0]),
                ([1.0, 0.0, 0.0], tri[1]),
                ([0.0, 1.0, 0.0], tri[2]),
            ]:
                first_triangle_by_vertex.setdefault(
                    (mesh_index, vertex_index),
                    {
                        "globalTriangleIndex": global_triangle_index,
                        "barycentric": barycentric,
                    },
                )
            global_triangle_index += 1
    return {
        "verticesByPanel": vertices_by_panel,
        "firstTriangleByVertex": first_triangle_by_vertex,
    }


def _nearest_panel_uv(
    uv: Vec2, candidates: list[tuple[int, int, Vec2, Vec3]]
) -> tuple[int, int, Vec2, Vec3] | None:
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda candidate: (
            _distance2(uv, candidate[2]),
            candidate[0],
            candidate[1],
        ),
    )


def _panel_summaries(mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_panel: dict[str, list[dict[str, Any]]] = {}
    for mapping in mappings:
        by_panel.setdefault(str(mapping["panelId"]), []).append(mapping)
    summaries: list[dict[str, Any]] = []
    for panel_id in sorted(by_panel):
        panel_records = by_panel[panel_id]
        mapped = [record for record in panel_records if record["simulationVertexIndex"] is not None]
        uv_distances = [
            float(record["panelUvDistance"])
            for record in mapped
            if record.get("panelUvDistance") is not None
        ]
        offsets = [
            float(record["restToSimulationOffsetMeters"])
            for record in mapped
            if record.get("restToSimulationOffsetMeters") is not None
        ]
        summaries.append(
            {
                "panelId": panel_id,
                "cleanupVertexCount": len(panel_records),
                "mappedVertexCount": len(mapped),
                "unmappedVertexCount": len(panel_records) - len(mapped),
                "exactPanelUvMatchCount": sum(
                    1
                    for record in mapped
                    if float(record["panelUvDistance"]) <= _PANEL_UV_EXACT_MATCH_TOLERANCE
                ),
                "maxPanelUvDistance": _round(max(uv_distances, default=0.0)),
                "maxRestToSimulationOffsetMeters": _round(max(offsets, default=0.0)),
                "status": "mapped" if len(mapped) == len(panel_records) else "partial",
            }
        )
    return summaries


def _aggregate(
    mappings: list[dict[str, Any]], semantic_transfer_report: dict[str, Any]
) -> dict[str, Any]:
    mapped = [record for record in mappings if record["simulationVertexIndex"] is not None]
    uv_distances = [
        float(record["panelUvDistance"])
        for record in mapped
        if record.get("panelUvDistance") is not None
    ]
    offsets = [
        float(record["restToSimulationOffsetMeters"])
        for record in mapped
        if record.get("restToSimulationOffsetMeters") is not None
    ]
    status_counts = Counter(str(record["status"]) for record in mappings)
    exact_count = sum(
        1
        for record in mapped
        if float(record["panelUvDistance"]) <= _PANEL_UV_EXACT_MATCH_TOLERANCE
    )
    unique_triangles = {
        int(record["simulationTriangleIndex"])
        for record in mapped
        if record.get("simulationTriangleIndex") is not None
    }
    total = len(mappings)
    return {
        "cleanupVertexCount": total,
        "mappedVertexCount": len(mapped),
        "unmappedVertexCount": total - len(mapped),
        "exactPanelUvMatchCount": exact_count,
        "wrongPanelMatchCount": 0,
        "panelCount": len({str(record["panelId"]) for record in mappings}),
        "mappedPanelCount": len(
            {
                str(record["panelId"])
                for record in mapped
                if record["simulationVertexIndex"] is not None
            }
        ),
        "candidateRecordCount": total,
        "candidateTriangleReferenceCount": len(unique_triangles),
        "ambiguousBoundaryEdgeCount": int(
            semantic_transfer_report["aggregate"].get("ambiguousBoundaryEdgeCount", 0)
        ),
        "maxPanelUvDistance": _round(max(uv_distances, default=0.0)),
        "rmsPanelUvDistance": _round(_rms(uv_distances)),
        "maxRestToSimulationOffsetMeters": _round(max(offsets, default=0.0)),
        "rmsRestToSimulationOffsetMeters": _round(_rms(offsets)),
        "candidateCompleteness": _round(len(mapped) / total if total else 0.0),
        "statusCounts": dict(sorted(status_counts.items())),
    }


def _distance2(a: Vec2, b: Vec2) -> float:
    return sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _distance3(a: Vec3, b: Vec3) -> float:
    return sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def _rms(values: list[float]) -> float:
    if not values:
        return 0.0
    return sqrt(sum(value * value for value in values) / len(values))


def _round(value: float) -> float:
    return round(float(value), 9)


def _vec2_json(value: Vec2) -> list[float]:
    return [_round(value[0]), _round(value[1])]
