from __future__ import annotations

from collections import Counter
from copy import deepcopy
from math import sqrt
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import MeshSet, Vec3, mesh_bounds
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)

GEOMETRY_BINDING_VALIDATION_VERSION = "closy.geometry_binding_validation.deformation_gate.v1"

_MAX_ACCEPTABLE_VERTEX_OFFSET_METERS = 0.05
_RMS_ACCEPTABLE_VERTEX_OFFSET_METERS = 0.025
_MAX_ACCEPTABLE_REST_DRIFT_METERS = 0.001
_MAX_ACCEPTABLE_PANEL_UV_DISTANCE = 1e-6


def build_geometry_binding_validation_report(
    *,
    garment_id: str,
    garment_class: str,
    binding_candidate_report: dict[str, Any],
    cleanup_asset_path: Path,
    rest_simulation_mesh: MeshSet,
    settled_simulation_mesh: MeshSet,
    rest_state_path: str,
    settled_simulation_mesh_path: str,
) -> dict[str, Any]:
    """Validate a cleanup-preview binding candidate without accepting runtime use.

    This report is deliberately conservative. It measures whether the candidate
    correspondence can survive the current rest-to-settled deformation, and it
    keeps the result rejected until continuity, seam split handling and a real
    runtime binding file exist.
    """

    cleanup_mesh = read_glb_meshset(cleanup_asset_path)
    validation_records = _validation_records(
        cleanup_mesh,
        rest_simulation_mesh,
        settled_simulation_mesh,
        binding_candidate_report["vertexMappings"],
    )
    aggregate = _aggregate(validation_records, binding_candidate_report)
    checks = _checks(aggregate)
    failed_checks = [check for check in checks if check["status"] == "fail"]
    not_run_checks = [check for check in checks if check["status"] == "not_run"]
    rejected = bool(failed_checks or not_run_checks)
    blocking_reasons = _blocking_reasons(failed_checks, not_run_checks, binding_candidate_report)

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "binding_validation.cleanup_preview_tshirt_visual_geometry_v1",
        "stageVersion": GEOMETRY_BINDING_VALIDATION_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceGeometryBindingCandidateId": binding_candidate_report["reportId"],
        "sourceGeometryBindingCandidateHash": binding_candidate_report["integrity"][
            "geometryBindingCandidateHash"
        ],
        "sourceGeometrySemanticTransferId": binding_candidate_report[
            "sourceGeometrySemanticTransferId"
        ],
        "sourceGeometrySemanticTransferHash": binding_candidate_report[
            "sourceGeometrySemanticTransferHash"
        ],
        "sourceGeometryCleanupResultId": binding_candidate_report["sourceGeometryCleanupResultId"],
        "sourceGeometryCleanupResultHash": binding_candidate_report[
            "sourceGeometryCleanupResultHash"
        ],
        "inputCleanupAsset": {
            "path": binding_candidate_report["inputCleanupAsset"]["path"],
            "sourceAssetHash": sha256_file(cleanup_asset_path),
            "byteSize": cleanup_asset_path.stat().st_size,
            "canonicalUseAllowed": False,
            "purpose": binding_candidate_report["inputCleanupAsset"]["purpose"],
        },
        "sourceRestSimulation": {
            "path": rest_state_path,
            "topologyHash": topology_hash(rest_simulation_mesh),
            "contentHash": geometry_content_hash(rest_simulation_mesh),
            "meshCount": len(rest_simulation_mesh.meshes),
            "vertexCount": rest_simulation_mesh.vertex_count,
            "triangleCount": rest_simulation_mesh.triangle_count,
            "bounds": mesh_bounds(rest_simulation_mesh),
            "state": "rest_analytic_assembly",
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
        "validationSettings": {
            "maxAcceptableVertexOffsetMeters": _MAX_ACCEPTABLE_VERTEX_OFFSET_METERS,
            "rmsAcceptableVertexOffsetMeters": _RMS_ACCEPTABLE_VERTEX_OFFSET_METERS,
            "maxAcceptableRestDriftMeters": _MAX_ACCEPTABLE_REST_DRIFT_METERS,
            "maxAcceptablePanelUvDistance": _MAX_ACCEPTABLE_PANEL_UV_DISTANCE,
            "requireNormalContinuityValidation": True,
            "requireTangentContinuityValidation": True,
            "requireSeamBoundaryContinuityValidation": True,
            "requireRuntimeBindingFile": True,
        },
        "validationRecords": validation_records,
        "aggregate": aggregate,
        "checks": checks,
        "execution": {
            "candidateBindingRun": True,
            "deformationValidationRun": True,
            "simulationBindingRun": False,
            "runtimeBindingWritten": False,
            "runtimeBindingAccepted": False,
            "repairRun": False,
            "retopologyRun": False,
            "cleanProposalRun": False,
        },
        "readiness": {
            "status": "deformation_validation_failed_runtime_binding_rejected"
            if rejected
            else "deformation_validation_passed_runtime_binding_still_missing",
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": False,
            "nextExecutableStage": "repair_or_retopology_before_runtime_binding_generation",
            "blockingReasons": blocking_reasons,
        },
        "quality": {
            "status": "failed_rejected" if rejected else "partial_pass_rejected",
            "candidateCompleteness": aggregate["candidateCompleteness"],
            "maxPanelUvDistance": aggregate["maxPanelUvDistance"],
            "maxCleanupToRestDriftMeters": aggregate["maxCleanupToRestDriftMeters"],
            "maxCleanupToSettledOffsetMeters": aggregate["maxCleanupToSettledOffsetMeters"],
            "rmsCleanupToSettledOffsetMeters": aggregate["rmsCleanupToSettledOffsetMeters"],
            "failedCheckCount": len(failed_checks),
            "notRunCheckCount": len(not_run_checks),
            "acceptedForCleanProposal": False,
            "warnings": [
                "binding_candidate_deformation_validation_rejected",
                "runtime_binding_not_generated",
                "normal_tangent_continuity_not_validated",
                "seam_boundary_continuity_not_validated",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"geometryBindingValidationHash": ""},
    }
    report["integrity"]["geometryBindingValidationHash"] = hash_geometry_binding_validation_report(
        report
    )
    return report


def hash_geometry_binding_validation_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["geometryBindingValidationHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _validation_records(
    cleanup_mesh: MeshSet,
    rest_simulation_mesh: MeshSet,
    settled_simulation_mesh: MeshSet,
    candidate_mappings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for mapping in candidate_mappings:
        cleanup_position = _vertex_at(
            cleanup_mesh,
            int(mapping["cleanupMeshIndex"]),
            int(mapping["cleanupVertexIndex"]),
        )
        simulation_mesh_index = mapping.get("simulationMeshIndex")
        simulation_vertex_index = mapping.get("simulationVertexIndex")
        if simulation_mesh_index is None or simulation_vertex_index is None:
            records.append(
                {
                    "cleanupMeshIndex": int(mapping["cleanupMeshIndex"]),
                    "cleanupVertexIndex": int(mapping["cleanupVertexIndex"]),
                    "panelId": str(mapping["panelId"]),
                    "simulationMeshIndex": None,
                    "simulationVertexIndex": None,
                    "panelUvDistance": mapping.get("panelUvDistance"),
                    "cleanupToRestDriftMeters": None,
                    "cleanupToSettledOffsetMeters": None,
                    "restToSettledDisplacementMeters": None,
                    "status": "unmapped",
                }
            )
            continue
        mesh_index = int(simulation_mesh_index)
        vertex_index = int(simulation_vertex_index)
        rest_position = _vertex_at(rest_simulation_mesh, mesh_index, vertex_index)
        settled_position = _vertex_at(settled_simulation_mesh, mesh_index, vertex_index)
        cleanup_to_rest = _distance3(cleanup_position, rest_position)
        cleanup_to_settled = _distance3(cleanup_position, settled_position)
        rest_to_settled = _distance3(rest_position, settled_position)
        status = "passed_candidate_vertex"
        if float(mapping.get("panelUvDistance") or 0.0) > _MAX_ACCEPTABLE_PANEL_UV_DISTANCE:
            status = "failed_panel_uv_distance"
        elif cleanup_to_rest > _MAX_ACCEPTABLE_REST_DRIFT_METERS:
            status = "failed_cleanup_rest_drift"
        elif cleanup_to_settled > _MAX_ACCEPTABLE_VERTEX_OFFSET_METERS:
            status = "failed_deformation_offset_exceeds_threshold"
        records.append(
            {
                "cleanupMeshIndex": int(mapping["cleanupMeshIndex"]),
                "cleanupVertexIndex": int(mapping["cleanupVertexIndex"]),
                "panelId": str(mapping["panelId"]),
                "simulationMeshIndex": mesh_index,
                "simulationVertexIndex": vertex_index,
                "panelUvDistance": _round(float(mapping.get("panelUvDistance") or 0.0)),
                "cleanupToRestDriftMeters": _round(cleanup_to_rest),
                "cleanupToSettledOffsetMeters": _round(cleanup_to_settled),
                "restToSettledDisplacementMeters": _round(rest_to_settled),
                "status": status,
            }
        )
    return records


def _aggregate(
    records: list[dict[str, Any]], binding_candidate_report: dict[str, Any]
) -> dict[str, Any]:
    mapped = [record for record in records if record["simulationVertexIndex"] is not None]
    panel_uv_distances = [
        float(record["panelUvDistance"])
        for record in mapped
        if record.get("panelUvDistance") is not None
    ]
    cleanup_to_rest = [
        float(record["cleanupToRestDriftMeters"])
        for record in mapped
        if record.get("cleanupToRestDriftMeters") is not None
    ]
    cleanup_to_settled = [
        float(record["cleanupToSettledOffsetMeters"])
        for record in mapped
        if record.get("cleanupToSettledOffsetMeters") is not None
    ]
    rest_to_settled = [
        float(record["restToSettledDisplacementMeters"])
        for record in mapped
        if record.get("restToSettledDisplacementMeters") is not None
    ]
    status_counts = Counter(str(record["status"]) for record in records)
    candidate_aggregate = binding_candidate_report["aggregate"]
    total = len(records)
    return {
        "validationRecordCount": total,
        "cleanupVertexCount": int(candidate_aggregate["cleanupVertexCount"]),
        "mappedVertexCount": len(mapped),
        "unmappedVertexCount": total - len(mapped),
        "candidateCompleteness": _round(len(mapped) / total if total else 0.0),
        "candidateTriangleReferenceCount": int(
            candidate_aggregate["candidateTriangleReferenceCount"]
        ),
        "ambiguousBoundaryEdgeCount": int(candidate_aggregate["ambiguousBoundaryEdgeCount"]),
        "maxPanelUvDistance": _round(max(panel_uv_distances, default=0.0)),
        "rmsPanelUvDistance": _round(_rms(panel_uv_distances)),
        "maxCleanupToRestDriftMeters": _round(max(cleanup_to_rest, default=0.0)),
        "rmsCleanupToRestDriftMeters": _round(_rms(cleanup_to_rest)),
        "maxCleanupToSettledOffsetMeters": _round(max(cleanup_to_settled, default=0.0)),
        "rmsCleanupToSettledOffsetMeters": _round(_rms(cleanup_to_settled)),
        "maxRestToSettledDisplacementMeters": _round(max(rest_to_settled, default=0.0)),
        "rmsRestToSettledDisplacementMeters": _round(_rms(rest_to_settled)),
        "candidateReportedMaxRestToSimulationOffsetMeters": candidate_aggregate[
            "maxRestToSimulationOffsetMeters"
        ],
        "candidateReportedRmsRestToSimulationOffsetMeters": candidate_aggregate[
            "rmsRestToSimulationOffsetMeters"
        ],
        "statusCounts": dict(sorted(status_counts.items())),
    }


def _checks(aggregate: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "checkId": "candidate_mapping_completeness",
            "status": "pass" if aggregate["candidateCompleteness"] == 1.0 else "fail",
            "measured": aggregate["candidateCompleteness"],
            "threshold": 1.0,
        },
        {
            "checkId": "panel_uv_residual",
            "status": "pass"
            if aggregate["maxPanelUvDistance"] <= _MAX_ACCEPTABLE_PANEL_UV_DISTANCE
            else "fail",
            "measured": aggregate["maxPanelUvDistance"],
            "threshold": _MAX_ACCEPTABLE_PANEL_UV_DISTANCE,
        },
        {
            "checkId": "cleanup_rest_alignment",
            "status": "pass"
            if aggregate["maxCleanupToRestDriftMeters"] <= _MAX_ACCEPTABLE_REST_DRIFT_METERS
            else "fail",
            "measured": aggregate["maxCleanupToRestDriftMeters"],
            "threshold": _MAX_ACCEPTABLE_REST_DRIFT_METERS,
        },
        {
            "checkId": "cleanup_settled_deformation_offset",
            "status": "pass"
            if aggregate["maxCleanupToSettledOffsetMeters"] <= _MAX_ACCEPTABLE_VERTEX_OFFSET_METERS
            and aggregate["rmsCleanupToSettledOffsetMeters"] <= _RMS_ACCEPTABLE_VERTEX_OFFSET_METERS
            else "fail",
            "measured": {
                "max": aggregate["maxCleanupToSettledOffsetMeters"],
                "rms": aggregate["rmsCleanupToSettledOffsetMeters"],
            },
            "threshold": {
                "max": _MAX_ACCEPTABLE_VERTEX_OFFSET_METERS,
                "rms": _RMS_ACCEPTABLE_VERTEX_OFFSET_METERS,
            },
        },
        {
            "checkId": "normal_continuity",
            "status": "not_run",
            "reason": "normal_transfer_validation_not_implemented",
        },
        {
            "checkId": "tangent_continuity",
            "status": "not_run",
            "reason": "tangent_transfer_validation_not_implemented",
        },
        {
            "checkId": "seam_boundary_continuity",
            "status": "not_run",
            "reason": "seam_split_and_boundary_continuity_validation_not_implemented",
        },
        {
            "checkId": "runtime_binding_file",
            "status": "not_run",
            "reason": "proposal_runtime_CLSYBND1_file_not_generated",
        },
    ]


def _blocking_reasons(
    failed_checks: list[dict[str, Any]],
    not_run_checks: list[dict[str, Any]],
    binding_candidate_report: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    for check in failed_checks:
        reasons.append(f"{check['checkId']}_failed")
    for check in not_run_checks:
        reasons.append(f"{check['checkId']}_not_run")
    if int(binding_candidate_report["aggregate"].get("ambiguousBoundaryEdgeCount", 0)) > 0:
        reasons.append("multi_seam_boundary_spans_require_split_before_binding")
    reasons.append("canonical_acceptance_gate_not_run")
    return sorted(set(reasons))


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
