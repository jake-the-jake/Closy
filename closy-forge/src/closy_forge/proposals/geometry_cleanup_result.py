from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import audit_glb, read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3, cross, sub
from closy_forge.geometry.topology_diagnostics import meshset_topology_diagnostics
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

GEOMETRY_CLEANUP_RESULT_VERSION = "closy.geometry_cleanup_result.local_safe_ops.v1"

_POSITION_TOLERANCE = 1e-6
_AREA_TOLERANCE = 1e-12


def build_geometry_cleanup_result(
    *,
    garment_id: str,
    garment_class: str,
    raw_geometry_proposal: dict[str, Any],
    raw_topology_report: dict[str, Any],
    cleanup_plan_report: dict[str, Any],
    source_asset_path: Path,
    output_asset_path: Path,
    output_package_asset_path: str,
) -> dict[str, Any]:
    """Run deterministic local safe mesh cleanup without accepting clean geometry.

    The adapter only performs operations that are safe without garment semantic
    inference: duplicate-position welding and degenerate-triangle filtering. It
    writes a non-canonical preview GLB and records all deferred semantic repair,
    retopology and simulation-binding work explicitly.
    """

    raw_meshset = read_glb_meshset(source_asset_path)
    before_topology = meshset_topology_diagnostics(raw_meshset)
    cleaned_meshset, metrics = cleanup_meshset_for_preview(raw_meshset)
    write_indexed_glb(
        output_asset_path,
        cleaned_meshset,
        "closy_local_cleanup_preview_tshirt_v1",
        (0.72, 0.78, 0.90, 1.0),
    )
    output_topology = meshset_topology_diagnostics(read_glb_meshset(output_asset_path))
    output_audit = audit_glb(output_asset_path)
    raw = raw_geometry_proposal["rawProposal"]
    executed_operations = _executed_operations(cleanup_plan_report, before_topology, metrics)
    deferred_operations = _deferred_operations(cleanup_plan_report, output_topology)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "cleanup_result.raw_manual_tshirt_visual_geometry_v1",
        "stageVersion": GEOMETRY_CLEANUP_RESULT_VERSION,
        "adapterId": "closy.local_mesh_cleanup_adapter.v1",
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceRawProposalId": raw_geometry_proposal["proposalId"],
        "sourceRawProposalHash": raw_geometry_proposal["integrity"]["geometryProposalHash"],
        "sourceRawTopologyReportId": raw_topology_report["reportId"],
        "sourceRawTopologyReportHash": raw_topology_report["integrity"][
            "rawGeometryTopologyReportHash"
        ],
        "sourceGeometryCleanupPlanId": cleanup_plan_report["reportId"],
        "sourceGeometryCleanupPlanHash": cleanup_plan_report["integrity"][
            "geometryCleanupPlanHash"
        ],
        "inputAsset": {
            "path": raw["assetPath"],
            "sourceAssetHash": raw["sourceAssetHash"],
            "byteSize": raw["byteSize"],
        },
        "outputAsset": {
            "path": output_package_asset_path,
            "sourceAssetHash": sha256_file(output_asset_path),
            "byteSize": output_asset_path.stat().st_size,
            "canonicalUseAllowed": False,
            "purpose": "non_canonical_cleanup_preview",
        },
        "topologyBefore": _topology_snapshot(before_topology),
        "topologyAfter": _topology_snapshot(output_topology),
        "outputAudit": output_audit,
        "executedOperations": executed_operations,
        "deferredOperations": deferred_operations,
        "execution": {
            "cleanupRun": True,
            "repairRun": False,
            "retopologyRun": False,
            "semanticTransferRun": False,
            "simulationBindingRun": False,
            "outputAssetPath": output_package_asset_path,
            "outputAssetHash": sha256_file(output_asset_path),
        },
        "readiness": {
            "status": "partial_cleanup_completed",
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": False,
            "nextExecutableStage": "semantic_panel_transfer_and_boundary_classification",
            "blockingReasons": [
                "boundary_loop_classification_pending",
                "semantic_panel_transfer_missing",
                "simulation_binding_missing",
                "canonical_acceptance_gate_not_run",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"geometryCleanupResultHash": ""},
    }
    report["integrity"]["geometryCleanupResultHash"] = hash_geometry_cleanup_result(report)
    return report


def cleanup_meshset_for_preview(meshset: MeshSet) -> tuple[MeshSet, dict[str, Any]]:
    cleaned_meshes: list[Mesh] = []
    removed_duplicate_vertices = 0
    removed_degenerate_triangles = 0
    for mesh in meshset.meshes:
        welded, duplicate_count = _weld_duplicate_positions(mesh)
        cleaned, degenerate_count = _remove_degenerate_triangles(welded)
        cleaned_meshes.append(cleaned)
        removed_duplicate_vertices += duplicate_count
        removed_degenerate_triangles += degenerate_count
    cleaned_meshset = MeshSet(cleaned_meshes)
    return cleaned_meshset, {
        "meshCount": len(cleaned_meshes),
        "verticesBefore": meshset.vertex_count,
        "verticesAfter": cleaned_meshset.vertex_count,
        "trianglesBefore": meshset.triangle_count,
        "trianglesAfter": cleaned_meshset.triangle_count,
        "removedDuplicateVertexCount": removed_duplicate_vertices,
        "removedDegenerateTriangleCount": removed_degenerate_triangles,
    }


def hash_geometry_cleanup_result(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["geometryCleanupResultHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _weld_duplicate_positions(mesh: Mesh) -> tuple[Mesh, int]:
    index_by_key: dict[tuple[int, int, int], int] = {}
    remap: list[int] = []
    vertices: list[Vec3] = []
    panel_uvs: list[tuple[float, float]] = []
    removed = 0
    for index, vertex in enumerate(mesh.vertices):
        key = _vertex_key(vertex)
        existing = index_by_key.get(key)
        if existing is None:
            existing = len(vertices)
            index_by_key[key] = existing
            vertices.append(vertex)
            panel_uvs.append(mesh.panel_uvs[index] if index < len(mesh.panel_uvs) else (0.0, 0.0))
        else:
            removed += 1
        remap.append(existing)
    triangles = [(remap[a], remap[b], remap[c]) for a, b, c in mesh.triangles]
    return (
        Mesh(
            name=mesh.name,
            panel_id=mesh.panel_id,
            vertices=vertices,
            panel_uvs=panel_uvs,
            triangles=triangles,
            material_id=mesh.material_id,
        ),
        removed,
    )


def _remove_degenerate_triangles(mesh: Mesh) -> tuple[Mesh, int]:
    triangles = [
        tri
        for tri in mesh.triangles
        if len(set(tri)) == 3 and _triangle_area2([mesh.vertices[i] for i in tri]) > _AREA_TOLERANCE
    ]
    removed = len(mesh.triangles) - len(triangles)
    return (
        Mesh(
            name=mesh.name,
            panel_id=mesh.panel_id,
            vertices=mesh.vertices,
            panel_uvs=mesh.panel_uvs,
            triangles=triangles,
            material_id=mesh.material_id,
        ),
        removed,
    )


def _executed_operations(
    cleanup_plan: dict[str, Any], topology_before: dict[str, Any], metrics: dict[str, Any]
) -> list[dict[str, Any]]:
    required = _required_operation_map(cleanup_plan)
    return [
        {
            "operationId": "duplicate_position_weld",
            "requiredByPlan": required.get("duplicate_position_weld", False),
            "executed": True,
            "inputEvidenceCount": topology_before["duplicatePositionCount"],
            "removedCount": metrics["removedDuplicateVertexCount"],
            "result": "pass",
        },
        {
            "operationId": "degenerate_triangle_removal",
            "requiredByPlan": required.get("degenerate_triangle_removal", False),
            "executed": True,
            "inputEvidenceCount": topology_before["degenerateTriangleCount"],
            "removedCount": metrics["removedDegenerateTriangleCount"],
            "result": "pass",
        },
    ]


def _deferred_operations(
    cleanup_plan: dict[str, Any], topology_after: dict[str, Any]
) -> list[dict[str, Any]]:
    required = _required_operation_map(cleanup_plan)
    return [
        {
            "operationId": "boundary_loop_classification",
            "requiredByPlan": required.get("boundary_loop_classification", False),
            "executed": False,
            "remainingEvidenceCount": topology_after["boundaryEdgeCount"],
            "reason": "garment_openings_must_be_semantically_classified",
        },
        {
            "operationId": "component_stitching_or_semantic_panel_transfer",
            "requiredByPlan": required.get("component_stitching_or_semantic_panel_transfer", False),
            "executed": False,
            "remainingEvidenceCount": topology_after["componentCount"],
            "reason": "panel_correspondence_required_before_component_stitching",
        },
        {
            "operationId": "non_manifold_edge_repair",
            "requiredByPlan": required.get("non_manifold_edge_repair", False),
            "executed": False,
            "remainingEvidenceCount": topology_after["nonManifoldEdgeCount"],
            "reason": "no_non_manifold_edges_in_current_fixture",
        },
        {
            "operationId": "semantic_panel_transfer",
            "requiredByPlan": required.get("semantic_panel_transfer", False),
            "executed": False,
            "remainingEvidenceCount": topology_after["meshCount"],
            "reason": "stable_panel_seam_opening_ids_not_transferred_to_preview_asset",
        },
        {
            "operationId": "simulation_binding_generation",
            "requiredByPlan": required.get("simulation_binding_generation", False),
            "executed": False,
            "remainingEvidenceCount": topology_after["triangleCount"],
            "reason": "raw_visual_preview_not_bound_to_canonical_simulation_topology",
        },
        {
            "operationId": "canonical_acceptance_validation",
            "requiredByPlan": required.get("canonical_acceptance_validation", False),
            "executed": False,
            "remainingEvidenceCount": 1,
            "reason": "acceptance_gate_requires_semantic_transfer_and_binding",
        },
    ]


def _required_operation_map(cleanup_plan: dict[str, Any]) -> dict[str, bool]:
    return {
        str(operation["operationId"]): bool(operation["required"])
        for operation in cleanup_plan["recommendedOperations"]
    }


def _topology_snapshot(topology: dict[str, Any]) -> dict[str, Any]:
    return {
        "meshCount": topology["meshCount"],
        "vertexCount": topology["vertexCount"],
        "triangleCount": topology["triangleCount"],
        "componentCount": topology["componentCount"],
        "largestComponentTriangleCount": topology["largestComponentTriangleCount"],
        "boundaryEdgeCount": topology["boundaryEdgeCount"],
        "nonManifoldEdgeCount": topology["nonManifoldEdgeCount"],
        "degenerateTriangleCount": topology["degenerateTriangleCount"],
        "duplicatePositionCount": topology["duplicatePositionCount"],
        "manifoldStatus": topology["manifoldStatus"],
    }


def _vertex_key(vertex: Vec3) -> tuple[int, int, int]:
    return (
        round(vertex[0] / _POSITION_TOLERANCE),
        round(vertex[1] / _POSITION_TOLERANCE),
        round(vertex[2] / _POSITION_TOLERANCE),
    )


def _triangle_area2(vertices: list[Vec3]) -> float:
    normal = cross(sub(vertices[1], vertices[0]), sub(vertices[2], vertices[0]))
    return sum(value * value for value in normal)
