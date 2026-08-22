from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

GEOMETRY_REPAIR_RETOPOLOGY_PLAN_VERSION = "closy.geometry_repair_retopology_plan.recommendation.v1"


def build_geometry_repair_retopology_plan(
    *,
    garment_id: str,
    garment_class: str,
    raw_topology_report: dict[str, Any],
    cleanup_result_report: dict[str, Any],
    semantic_transfer_report: dict[str, Any],
    binding_candidate_report: dict[str, Any],
    binding_validation_report: dict[str, Any],
) -> dict[str, Any]:
    """Plan the next safe repair stage after proposal binding validation fails.

    This is a deterministic recommendation artifact only. It converts measured
    validation failures into executable repair/retopology tasks without writing
    a clean mesh, a seam-split mesh or a runtime binding file.
    """

    failure_snapshot = _failure_snapshot(
        raw_topology_report,
        cleanup_result_report,
        semantic_transfer_report,
        binding_candidate_report,
        binding_validation_report,
    )
    recommended_operations = _recommended_operations(failure_snapshot)
    aggregate = _aggregate(failure_snapshot, recommended_operations)
    blocking_reasons = _blocking_reasons(binding_validation_report, recommended_operations)

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "repair_retopology_plan.cleanup_preview_tshirt_visual_geometry_v1",
        "stageVersion": GEOMETRY_REPAIR_RETOPOLOGY_PLAN_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceRawTopologyReportId": raw_topology_report["reportId"],
        "sourceRawTopologyReportHash": raw_topology_report["integrity"][
            "rawGeometryTopologyReportHash"
        ],
        "sourceGeometryCleanupResultId": cleanup_result_report["reportId"],
        "sourceGeometryCleanupResultHash": cleanup_result_report["integrity"][
            "geometryCleanupResultHash"
        ],
        "sourceGeometrySemanticTransferId": semantic_transfer_report["reportId"],
        "sourceGeometrySemanticTransferHash": semantic_transfer_report["integrity"][
            "geometrySemanticTransferHash"
        ],
        "sourceGeometryBindingCandidateId": binding_candidate_report["reportId"],
        "sourceGeometryBindingCandidateHash": binding_candidate_report["integrity"][
            "geometryBindingCandidateHash"
        ],
        "sourceGeometryBindingValidationId": binding_validation_report["reportId"],
        "sourceGeometryBindingValidationHash": binding_validation_report["integrity"][
            "geometryBindingValidationHash"
        ],
        "failureSnapshot": failure_snapshot,
        "planningSettings": {
            "acceptanceModel": "plan_only_no_canonical_output",
            "maxAcceptableVertexOffsetMeters": binding_validation_report["validationSettings"][
                "maxAcceptableVertexOffsetMeters"
            ],
            "rmsAcceptableVertexOffsetMeters": binding_validation_report["validationSettings"][
                "rmsAcceptableVertexOffsetMeters"
            ],
            "requireSeamSplitForAmbiguousBoundarySpans": True,
            "requireRetopologyForLargeDeformationOffset": True,
            "requireNormalContinuityValidation": True,
            "requireTangentContinuityValidation": True,
            "requireRuntimeBindingGeneration": True,
        },
        "recommendedOperations": recommended_operations,
        "repairSequence": _repair_sequence(recommended_operations),
        "aggregate": aggregate,
        "execution": {
            "repairRetopologyPlanGenerated": True,
            "repairRun": False,
            "retopologyRun": False,
            "seamSplitRun": False,
            "normalContinuityValidationRun": False,
            "tangentContinuityValidationRun": False,
            "runtimeBindingWritten": False,
            "runtimeBindingAccepted": False,
            "cleanProposalRun": False,
        },
        "readiness": {
            "status": "repair_retopology_plan_generated_execution_pending",
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": False,
            "nextExecutableStage": "execute_repair_retopology_and_seam_split_adapter",
            "blockingReasons": blocking_reasons,
        },
        "quality": {
            "status": "plan_only_rejected",
            "recommendedOperationCount": aggregate["recommendedOperationCount"],
            "requiredOperationCount": aggregate["requiredOperationCount"],
            "failedValidationCheckCount": aggregate["failedValidationCheckCount"],
            "notRunValidationCheckCount": aggregate["notRunValidationCheckCount"],
            "deformationFailedVertexCount": aggregate["deformationFailedVertexCount"],
            "acceptedForCleanProposal": False,
            "warnings": [
                "repair_retopology_plan_not_executed",
                "runtime_binding_not_generated",
                "normal_tangent_continuity_not_validated",
                "clean_geometry_proposal_still_rejected",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"geometryRepairRetopologyPlanHash": ""},
    }
    report["integrity"]["geometryRepairRetopologyPlanHash"] = hash_geometry_repair_retopology_plan(
        report
    )
    return report


def hash_geometry_repair_retopology_plan(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["geometryRepairRetopologyPlanHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _failure_snapshot(
    raw_topology_report: dict[str, Any],
    cleanup_result_report: dict[str, Any],
    semantic_transfer_report: dict[str, Any],
    binding_candidate_report: dict[str, Any],
    binding_validation_report: dict[str, Any],
) -> dict[str, Any]:
    validation_aggregate = binding_validation_report["aggregate"]
    status_counts = validation_aggregate.get("statusCounts", {})
    semantic_aggregate = semantic_transfer_report["aggregate"]
    topology_before = cleanup_result_report["topologyBefore"]
    topology_after = cleanup_result_report["topologyAfter"]
    failed_checks = [
        check["checkId"]
        for check in binding_validation_report["checks"]
        if check.get("status") == "fail"
    ]
    not_run_checks = [
        check["checkId"]
        for check in binding_validation_report["checks"]
        if check.get("status") == "not_run"
    ]
    return {
        "rawTopologyStatus": raw_topology_report["topology"]["manifoldStatus"],
        "validationStatus": binding_validation_report["readiness"]["status"],
        "cleanupResultStatus": cleanup_result_report["readiness"]["status"],
        "semanticTransferStatus": semantic_transfer_report["readiness"]["status"],
        "bindingCandidateStatus": binding_candidate_report["readiness"]["status"],
        "cleanupVertexCount": validation_aggregate["cleanupVertexCount"],
        "mappedVertexCount": validation_aggregate["mappedVertexCount"],
        "unmappedVertexCount": validation_aggregate["unmappedVertexCount"],
        "candidateCompleteness": validation_aggregate["candidateCompleteness"],
        "failedValidationChecks": failed_checks,
        "notRunValidationChecks": not_run_checks,
        "failedValidationCheckCount": len(failed_checks),
        "notRunValidationCheckCount": len(not_run_checks),
        "deformationFailedVertexCount": int(
            status_counts.get("failed_deformation_offset_exceeds_threshold", 0)
        ),
        "passedCandidateVertexCount": int(status_counts.get("passed_candidate_vertex", 0)),
        "maxCleanupToSettledOffsetMeters": validation_aggregate["maxCleanupToSettledOffsetMeters"],
        "rmsCleanupToSettledOffsetMeters": validation_aggregate["rmsCleanupToSettledOffsetMeters"],
        "maxCleanupToRestDriftMeters": validation_aggregate["maxCleanupToRestDriftMeters"],
        "ambiguousBoundaryEdgeCount": semantic_aggregate["ambiguousBoundaryEdgeCount"],
        "classifiedBoundaryEdgeCount": semantic_aggregate["classifiedBoundaryEdgeCount"],
        "unclassifiedBoundaryEdgeCount": semantic_aggregate["unclassifiedBoundaryEdgeCount"],
        "postCleanupComponentCount": topology_after["componentCount"],
        "postCleanupBoundaryEdgeCount": topology_after["boundaryEdgeCount"],
        "postCleanupDuplicatePositionCount": topology_after["duplicatePositionCount"],
        "rawComponentCount": topology_before["componentCount"],
        "rawBoundaryEdgeCount": topology_before["boundaryEdgeCount"],
    }


def _recommended_operations(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _operation(
            "deformation_offset_reprojection",
            "retopology",
            int(snapshot["deformationFailedVertexCount"]) > 0,
            int(snapshot["deformationFailedVertexCount"]),
            (
                "Reproject or rebuild cleanup-preview vertices against settled simulation "
                "before runtime binding."
            ),
            "cleanup_preview_positions_reconciled_to_settled_simulation",
            "cleanup_settled_deformation_offset",
            10,
        ),
        _operation(
            "seam_boundary_split",
            "semantic_boundary",
            int(snapshot["ambiguousBoundaryEdgeCount"]) > 0,
            int(snapshot["ambiguousBoundaryEdgeCount"]),
            (
                "Split multi-seam boundary spans so seam, cuff, hem and neckline edges bind "
                "independently."
            ),
            "single_semantic_boundary_per_edge",
            "seam_boundary_continuity",
            20,
        ),
        _operation(
            "component_stitching_or_shell_unification",
            "topology",
            int(snapshot["postCleanupComponentCount"]) > 1,
            int(snapshot["postCleanupComponentCount"]),
            (
                "Unify or explicitly stitch disconnected visual shell components before "
                "clean proposal acceptance."
            ),
            "connected_or_semantically_stitched_panel_shells",
            "component_continuity",
            30,
        ),
        _operation(
            "canonical_panel_retopology",
            "topology",
            True,
            int(snapshot["cleanupVertexCount"]),
            (
                "Generate topology that preserves Closy panel IDs while supporting stable "
                "simulation/render binding."
            ),
            "candidate_clean_panel_topology_with_stable_ids",
            "topology_and_semantic_ids",
            40,
        ),
        _operation(
            "normal_continuity_validation",
            "quality_gate",
            "normal_continuity" in snapshot["notRunValidationChecks"],
            1 if "normal_continuity" in snapshot["notRunValidationChecks"] else 0,
            "Validate transferred normals across repaired panels and seam boundaries.",
            "normal_continuity_report",
            "normal_continuity",
            50,
        ),
        _operation(
            "tangent_continuity_validation",
            "quality_gate",
            "tangent_continuity" in snapshot["notRunValidationChecks"],
            1 if "tangent_continuity" in snapshot["notRunValidationChecks"] else 0,
            "Validate tangent-space continuity before mobile/runtime rendering acceptance.",
            "tangent_continuity_report",
            "tangent_continuity",
            60,
        ),
        _operation(
            "runtime_binding_generation",
            "binding",
            "runtime_binding_file" in snapshot["notRunValidationChecks"],
            int(snapshot["cleanupVertexCount"]),
            "Write and validate a proposal-specific CLSYBND1 runtime binding file.",
            "proposal_simulation_to_render_CLSYBND1_binding",
            "runtime_binding_file",
            70,
        ),
        _operation(
            "clean_proposal_acceptance_gate",
            "quality_gate",
            True,
            1,
            (
                "Run the clean proposal acceptance gate only after repair, retopology and "
                "runtime binding pass."
            ),
            "accepted_or_rejected_clean_geometry_proposal",
            "canonical_acceptance",
            80,
        ),
    ]


def _operation(
    operation_id: str,
    category: str,
    required: bool,
    evidence_count: int,
    rationale: str,
    expected_output: str,
    acceptance_gate: str,
    priority: int,
) -> dict[str, Any]:
    return {
        "operationId": operation_id,
        "category": category,
        "priority": priority,
        "required": required,
        "executed": False,
        "evidenceCount": evidence_count,
        "rationale": rationale,
        "expectedOutput": expected_output,
        "acceptanceGate": acceptance_gate,
    }


def _repair_sequence(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required = [operation for operation in operations if operation["required"]]
    return [
        {
            "step": index + 1,
            "operationId": operation["operationId"],
            "category": operation["category"],
            "inputState": "cleanup_preview_with_semantic_and_binding_validation_evidence",
            "outputState": operation["expectedOutput"],
            "acceptanceGate": operation["acceptanceGate"],
        }
        for index, operation in enumerate(required)
    ]


def _aggregate(snapshot: dict[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    required = [operation for operation in operations if operation["required"]]
    complexity = "runtime_binding_generation_required"
    if int(snapshot["deformationFailedVertexCount"]) > 0:
        complexity = "retopology_required"
    elif int(snapshot["ambiguousBoundaryEdgeCount"]) > 0:
        complexity = "seam_split_required"
    elif int(snapshot["postCleanupComponentCount"]) > 1:
        complexity = "component_stitching_required"
    return {
        "recommendedOperationCount": len(operations),
        "requiredOperationCount": len(required),
        "repairSequenceStepCount": len(required),
        "failedValidationCheckCount": snapshot["failedValidationCheckCount"],
        "notRunValidationCheckCount": snapshot["notRunValidationCheckCount"],
        "deformationFailedVertexCount": snapshot["deformationFailedVertexCount"],
        "passedCandidateVertexCount": snapshot["passedCandidateVertexCount"],
        "cleanupVertexCount": snapshot["cleanupVertexCount"],
        "ambiguousBoundaryEdgeCount": snapshot["ambiguousBoundaryEdgeCount"],
        "postCleanupComponentCount": snapshot["postCleanupComponentCount"],
        "postCleanupBoundaryEdgeCount": snapshot["postCleanupBoundaryEdgeCount"],
        "maxCleanupToSettledOffsetMeters": snapshot["maxCleanupToSettledOffsetMeters"],
        "rmsCleanupToSettledOffsetMeters": snapshot["rmsCleanupToSettledOffsetMeters"],
        "estimatedRepairComplexity": complexity,
        "planCompleteness": 1.0,
    }


def _blocking_reasons(
    binding_validation_report: dict[str, Any], operations: list[dict[str, Any]]
) -> list[str]:
    reasons = set(binding_validation_report["readiness"].get("blockingReasons", []))
    for operation in operations:
        if operation["required"] and not operation["executed"]:
            reasons.add(f"{operation['operationId']}_pending")
    reasons.add("repair_retopology_plan_not_executed")
    reasons.add("canonical_acceptance_gate_not_run")
    return sorted(reasons)
