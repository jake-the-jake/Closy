from __future__ import annotations

from copy import deepcopy
from math import sqrt
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3, mesh_bounds
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)

GEOMETRY_REPAIR_RESULT_VERSION = "closy.geometry_repair_result.partial_reprojection.v1"

_MAX_ACCEPTABLE_REPROJECTED_OFFSET_METERS = 0.001


def reproject_cleanup_preview_to_settled_simulation(
    *,
    cleanup_asset_path: Path,
    binding_candidate_report: dict[str, Any],
    settled_simulation_mesh: MeshSet,
) -> MeshSet:
    """Move cleanup-preview vertices onto their mapped settled simulation vertices."""

    cleanup_mesh = read_glb_meshset(cleanup_asset_path)
    target_by_cleanup_vertex = _target_positions_by_cleanup_vertex(
        binding_candidate_report,
        settled_simulation_mesh,
    )
    repaired_meshes: list[Mesh] = []
    for mesh_index, mesh in enumerate(cleanup_mesh.meshes):
        repaired_vertices = [
            target_by_cleanup_vertex.get((mesh_index, vertex_index), vertex)
            for vertex_index, vertex in enumerate(mesh.vertices)
        ]
        repaired_meshes.append(
            Mesh(
                name=f"{mesh.name}.deformation_reprojected",
                panel_id=mesh.panel_id,
                vertices=repaired_vertices,
                panel_uvs=list(mesh.panel_uvs),
                triangles=list(mesh.triangles),
                material_id=mesh.material_id,
            )
        )
    return MeshSet(repaired_meshes)


def build_geometry_repair_result_report(
    *,
    garment_id: str,
    garment_class: str,
    repair_retopology_plan_report: dict[str, Any],
    binding_candidate_report: dict[str, Any],
    binding_validation_report: dict[str, Any],
    cleanup_asset_path: Path,
    output_asset_path: Path,
    output_package_asset_path: str,
    output_mesh: MeshSet,
    settled_simulation_mesh: MeshSet,
    settled_simulation_mesh_path: str,
) -> dict[str, Any]:
    """Report a deterministic partial repair execution without accepting it."""

    repair_metrics = _repair_metrics(
        output_mesh,
        settled_simulation_mesh,
        binding_candidate_report["vertexMappings"],
    )
    plan_required_operations = [
        operation
        for operation in repair_retopology_plan_report["recommendedOperations"]
        if operation["required"]
    ]
    executed_operations = _executed_operations(repair_metrics)
    deferred_operations = _deferred_operations(plan_required_operations, executed_operations)

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "repair_result.cleanup_preview_tshirt_visual_geometry_v1",
        "stageVersion": GEOMETRY_REPAIR_RESULT_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceGeometryRepairRetopologyPlanId": repair_retopology_plan_report["reportId"],
        "sourceGeometryRepairRetopologyPlanHash": repair_retopology_plan_report["integrity"][
            "geometryRepairRetopologyPlanHash"
        ],
        "sourceGeometryBindingCandidateId": binding_candidate_report["reportId"],
        "sourceGeometryBindingCandidateHash": binding_candidate_report["integrity"][
            "geometryBindingCandidateHash"
        ],
        "sourceGeometryBindingValidationId": binding_validation_report["reportId"],
        "sourceGeometryBindingValidationHash": binding_validation_report["integrity"][
            "geometryBindingValidationHash"
        ],
        "inputCleanupAsset": {
            "path": binding_validation_report["inputCleanupAsset"]["path"],
            "sourceAssetHash": sha256_file(cleanup_asset_path),
            "byteSize": cleanup_asset_path.stat().st_size,
            "canonicalUseAllowed": False,
            "purpose": "non_canonical_cleanup_preview",
        },
        "targetSettledSimulation": {
            "path": settled_simulation_mesh_path,
            "topologyHash": topology_hash(settled_simulation_mesh),
            "contentHash": geometry_content_hash(settled_simulation_mesh),
            "meshCount": len(settled_simulation_mesh.meshes),
            "vertexCount": settled_simulation_mesh.vertex_count,
            "triangleCount": settled_simulation_mesh.triangle_count,
            "bounds": mesh_bounds(settled_simulation_mesh),
            "state": "settled_reference_simulation_topology",
        },
        "outputAsset": {
            "path": output_package_asset_path,
            "sourceAssetHash": sha256_file(output_asset_path),
            "byteSize": output_asset_path.stat().st_size,
            "canonicalUseAllowed": False,
            "purpose": "non_canonical_repair_reprojection_preview",
        },
        "outputMesh": {
            "topologyHash": topology_hash(output_mesh),
            "contentHash": geometry_content_hash(output_mesh),
            "meshCount": len(output_mesh.meshes),
            "vertexCount": output_mesh.vertex_count,
            "triangleCount": output_mesh.triangle_count,
            "bounds": mesh_bounds(output_mesh),
        },
        "repairMetrics": repair_metrics,
        "executedOperations": executed_operations,
        "deferredOperations": deferred_operations,
        "aggregate": {
            "plannedRequiredOperationCount": len(plan_required_operations),
            "executedOperationCount": len(executed_operations),
            "deferredOperationCount": len(deferred_operations),
            "movedVertexCount": repair_metrics["movedVertexCount"],
            "unmappedVertexCount": repair_metrics["unmappedVertexCount"],
            "maxOutputToSettledOffsetMeters": repair_metrics["maxOutputToSettledOffsetMeters"],
            "rmsOutputToSettledOffsetMeters": repair_metrics["rmsOutputToSettledOffsetMeters"],
            "deformationOffsetReduced": True,
            "partialRepairCompleteness": _round(
                len(executed_operations) / len(plan_required_operations)
                if plan_required_operations
                else 0.0
            ),
        },
        "execution": {
            "repairResultGenerated": True,
            "deformationReprojectionRun": True,
            "repairRun": True,
            "retopologyRun": False,
            "seamSplitRun": False,
            "componentStitchingRun": False,
            "normalContinuityValidationRun": False,
            "tangentContinuityValidationRun": False,
            "runtimeBindingWritten": False,
            "runtimeBindingAccepted": False,
            "cleanProposalRun": False,
        },
        "readiness": {
            "status": "partial_repair_completed_retopology_pending",
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": False,
            "nextExecutableStage": "execute_seam_split_retopology_and_runtime_binding",
            "blockingReasons": _blocking_reasons(deferred_operations),
        },
        "quality": {
            "status": "partial_repair_rejected",
            "maxOutputToSettledOffsetMeters": repair_metrics["maxOutputToSettledOffsetMeters"],
            "rmsOutputToSettledOffsetMeters": repair_metrics["rmsOutputToSettledOffsetMeters"],
            "acceptedForCleanProposal": False,
            "warnings": [
                "partial_repair_result_not_clean_geometry",
                "seam_split_not_executed",
                "retopology_not_executed",
                "runtime_binding_not_generated",
                "normal_tangent_continuity_not_validated",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"geometryRepairResultHash": ""},
    }
    report["integrity"]["geometryRepairResultHash"] = hash_geometry_repair_result(report)
    return report


def hash_geometry_repair_result(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["geometryRepairResultHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _target_positions_by_cleanup_vertex(
    binding_candidate_report: dict[str, Any],
    settled_simulation_mesh: MeshSet,
) -> dict[tuple[int, int], Vec3]:
    targets: dict[tuple[int, int], Vec3] = {}
    for mapping in binding_candidate_report["vertexMappings"]:
        simulation_mesh_index = mapping.get("simulationMeshIndex")
        simulation_vertex_index = mapping.get("simulationVertexIndex")
        if simulation_mesh_index is None or simulation_vertex_index is None:
            continue
        targets[(int(mapping["cleanupMeshIndex"]), int(mapping["cleanupVertexIndex"]))] = (
            settled_simulation_mesh.meshes[
                int(simulation_mesh_index)
            ].vertices[int(simulation_vertex_index)]
        )
    return targets


def _repair_metrics(
    output_mesh: MeshSet,
    settled_simulation_mesh: MeshSet,
    mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    output_to_settled: list[float] = []
    moved_vertex_count = 0
    unmapped_vertex_count = 0
    for mapping in mappings:
        simulation_mesh_index = mapping.get("simulationMeshIndex")
        simulation_vertex_index = mapping.get("simulationVertexIndex")
        if simulation_mesh_index is None or simulation_vertex_index is None:
            unmapped_vertex_count += 1
            continue
        output_position = _vertex_at(
            output_mesh,
            int(mapping["cleanupMeshIndex"]),
            int(mapping["cleanupVertexIndex"]),
        )
        settled_position = _vertex_at(
            settled_simulation_mesh,
            int(simulation_mesh_index),
            int(simulation_vertex_index),
        )
        distance = _distance3(output_position, settled_position)
        output_to_settled.append(distance)
        if distance <= _MAX_ACCEPTABLE_REPROJECTED_OFFSET_METERS:
            moved_vertex_count += 1
    return {
        "validationRecordCount": len(mappings),
        "movedVertexCount": moved_vertex_count,
        "unmappedVertexCount": unmapped_vertex_count,
        "maxOutputToSettledOffsetMeters": _round(max(output_to_settled, default=0.0)),
        "rmsOutputToSettledOffsetMeters": _round(_rms(output_to_settled)),
        "maxAcceptableReprojectedOffsetMeters": _MAX_ACCEPTABLE_REPROJECTED_OFFSET_METERS,
    }


def _executed_operations(repair_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "operationId": "deformation_offset_reprojection",
            "executed": True,
            "output": "manual_repair_preview_positions_projected_to_settled_simulation",
            "evidenceCount": repair_metrics["movedVertexCount"],
        }
    ]


def _deferred_operations(
    planned_required_operations: list[dict[str, Any]],
    executed_operations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    executed_ids = {operation["operationId"] for operation in executed_operations}
    return [
        {
            "operationId": operation["operationId"],
            "required": True,
            "executed": False,
            "evidenceCount": operation["evidenceCount"],
            "reason": "not_executed_in_partial_deformation_reprojection_pass",
        }
        for operation in planned_required_operations
        if operation["operationId"] not in executed_ids
    ]


def _blocking_reasons(deferred_operations: list[dict[str, Any]]) -> list[str]:
    reasons = {f"{operation['operationId']}_pending" for operation in deferred_operations}
    reasons.add("partial_repair_result_not_clean_geometry")
    reasons.add("canonical_acceptance_gate_not_run")
    return sorted(reasons)


def _vertex_at(meshset: MeshSet, mesh_index: int, vertex_index: int) -> Vec3:
    mesh = meshset.meshes[mesh_index]
    return mesh.vertices[vertex_index]


def _distance3(a: Vec3, b: Vec3) -> float:
    return sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def _rms(values: list[float]) -> float:
    if not values:
        return 0.0
    return sqrt(sum(value * value for value in values) / len(values))


def _round(value: float) -> float:
    return round(float(value), 9)
