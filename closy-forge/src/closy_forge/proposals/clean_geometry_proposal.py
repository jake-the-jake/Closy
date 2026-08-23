from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.contracts.common import COORDINATE_CONVENTION, FIXED_TIMESTAMP
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.proposals.geometry_clean_acceptance_gate import (
    CLEAN_ACCEPTANCE_GATE_REJECTION_REASONS,
)

CLEAN_GEOMETRY_PROPOSAL_VERSION = "closy.clean_geometry_proposal.rejection_report.v1"

REQUIRED_CLEAN_REJECTION_REASONS = [
    "cleanup_not_run",
    "repair_not_run",
    "semantic_transfer_missing",
    "simulation_binding_missing",
    "provider_output_not_canonical_garment_truth",
]

PARTIAL_CLEANUP_REJECTION_REASONS = [
    "cleanup_incomplete",
    "repair_not_run",
    "semantic_transfer_missing",
    "simulation_binding_missing",
    "provider_output_not_canonical_garment_truth",
]

PARTIAL_SEMANTIC_TRANSFER_REJECTION_REASONS = [
    "cleanup_incomplete",
    "repair_not_run",
    "simulation_binding_missing",
    "provider_output_not_canonical_garment_truth",
]

PARTIAL_BINDING_VALIDATION_REJECTION_REASONS = [
    "cleanup_incomplete",
    "repair_not_run",
    "simulation_binding_failed_deformation_validation",
    "simulation_binding_missing",
    "provider_output_not_canonical_garment_truth",
]

PARTIAL_REPAIR_RETOPOLOGY_PLAN_REJECTION_REASONS = [
    "cleanup_incomplete",
    "repair_plan_not_executed",
    "retopology_not_run",
    "simulation_binding_missing",
    "provider_output_not_canonical_garment_truth",
]

PARTIAL_REPAIR_RESULT_REJECTION_REASONS = [
    "cleanup_incomplete",
    "partial_repair_incomplete",
    "retopology_not_run",
    "simulation_binding_missing",
    "provider_output_not_canonical_garment_truth",
]

PARTIAL_RUNTIME_BINDING_RESULT_REJECTION_REASONS = [
    "cleanup_incomplete",
    "clean_acceptance_gate_not_run",
    "provider_visual_fidelity_not_accepted",
    "provider_output_not_canonical_garment_truth",
]


def build_clean_geometry_proposal_rejection(
    *,
    garment_id: str,
    garment_class: str,
    raw_geometry_proposal: dict[str, Any],
    provider_registry: dict[str, Any],
    raw_topology_report: dict[str, Any] | None = None,
    cleanup_plan_report: dict[str, Any] | None = None,
    cleanup_result_report: dict[str, Any] | None = None,
    semantic_transfer_report: dict[str, Any] | None = None,
    binding_candidate_report: dict[str, Any] | None = None,
    binding_validation_report: dict[str, Any] | None = None,
    repair_retopology_plan_report: dict[str, Any] | None = None,
    repair_result_report: dict[str, Any] | None = None,
    runtime_binding_result_report: dict[str, Any] | None = None,
    material_uv_transfer_report: dict[str, Any] | None = None,
    visual_shell_review_report: dict[str, Any] | None = None,
    clean_acceptance_gate_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record why a raw visual proposal is not yet a clean canonical mesh.

    This report is intentionally a rejection artifact. It keeps the Phase 5
    provider path inspectable without pretending that raw visual geometry has
    passed topology repair, semantic transfer, simulation binding or canonical
    garment acceptance.
    """

    raw_proposal = raw_geometry_proposal["rawProposal"]
    if raw_topology_report is None:
        topology_available = False
        topology: dict[str, Any] = {}
        topology_report_id = None
        topology_report_hash = None
    else:
        topology_available = True
        topology = raw_topology_report["topology"]
        topology_report_id = raw_topology_report["reportId"]
        topology_report_hash = raw_topology_report["integrity"]["rawGeometryTopologyReportHash"]
    if cleanup_plan_report is None:
        cleanup_plan_available = False
        cleanup_plan_id = None
        cleanup_plan_hash = None
        cleanup_plan_status = None
    else:
        cleanup_plan_available = True
        cleanup_plan_id = cleanup_plan_report["reportId"]
        cleanup_plan_hash = cleanup_plan_report["integrity"]["geometryCleanupPlanHash"]
        cleanup_plan_status = cleanup_plan_report["readiness"]["status"]
    if cleanup_result_report is None:
        cleanup_result_available = False
        cleanup_result_id = None
        cleanup_result_hash = None
        cleanup_result_status = None
        cleanup_result_execution: dict[str, Any] = {}
        cleanup_result_output: dict[str, Any] = {}
        cleanup_result_topology_after: dict[str, Any] = {}
    else:
        cleanup_result_available = True
        cleanup_result_id = cleanup_result_report["reportId"]
        cleanup_result_hash = cleanup_result_report["integrity"]["geometryCleanupResultHash"]
        cleanup_result_status = cleanup_result_report["readiness"]["status"]
        cleanup_result_execution = cleanup_result_report["execution"]
        cleanup_result_output = cleanup_result_report["outputAsset"]
        cleanup_result_topology_after = cleanup_result_report["topologyAfter"]
    if semantic_transfer_report is None:
        semantic_transfer_available = False
        semantic_transfer_id = None
        semantic_transfer_hash = None
        semantic_transfer_status = None
        semantic_transfer_execution: dict[str, Any] = {}
        semantic_transfer_aggregate: dict[str, Any] = {}
    else:
        semantic_transfer_available = True
        semantic_transfer_id = semantic_transfer_report["reportId"]
        semantic_transfer_hash = semantic_transfer_report["integrity"][
            "geometrySemanticTransferHash"
        ]
        semantic_transfer_status = semantic_transfer_report["readiness"]["status"]
        semantic_transfer_execution = semantic_transfer_report["execution"]
        semantic_transfer_aggregate = semantic_transfer_report["aggregate"]
    if binding_candidate_report is None:
        binding_candidate_available = False
        binding_candidate_id = None
        binding_candidate_hash = None
        binding_candidate_status = None
        binding_candidate_execution: dict[str, Any] = {}
        binding_candidate_aggregate: dict[str, Any] = {}
    else:
        binding_candidate_available = True
        binding_candidate_id = binding_candidate_report["reportId"]
        binding_candidate_hash = binding_candidate_report["integrity"][
            "geometryBindingCandidateHash"
        ]
        binding_candidate_status = binding_candidate_report["readiness"]["status"]
        binding_candidate_execution = binding_candidate_report["execution"]
        binding_candidate_aggregate = binding_candidate_report["aggregate"]
    if binding_validation_report is None:
        binding_validation_available = False
        binding_validation_id = None
        binding_validation_hash = None
        binding_validation_status = None
        binding_validation_execution: dict[str, Any] = {}
        binding_validation_aggregate: dict[str, Any] = {}
        binding_validation_quality: dict[str, Any] = {}
    else:
        binding_validation_available = True
        binding_validation_id = binding_validation_report["reportId"]
        binding_validation_hash = binding_validation_report["integrity"][
            "geometryBindingValidationHash"
        ]
        binding_validation_status = binding_validation_report["readiness"]["status"]
        binding_validation_execution = binding_validation_report["execution"]
        binding_validation_aggregate = binding_validation_report["aggregate"]
        binding_validation_quality = binding_validation_report["quality"]
    if repair_retopology_plan_report is None:
        repair_retopology_plan_available = False
        repair_retopology_plan_id = None
        repair_retopology_plan_hash = None
        repair_retopology_plan_status = None
        repair_retopology_plan_execution: dict[str, Any] = {}
        repair_retopology_plan_aggregate: dict[str, Any] = {}
    else:
        repair_retopology_plan_available = True
        repair_retopology_plan_id = repair_retopology_plan_report["reportId"]
        repair_retopology_plan_hash = repair_retopology_plan_report["integrity"][
            "geometryRepairRetopologyPlanHash"
        ]
        repair_retopology_plan_status = repair_retopology_plan_report["readiness"]["status"]
        repair_retopology_plan_execution = repair_retopology_plan_report["execution"]
        repair_retopology_plan_aggregate = repair_retopology_plan_report["aggregate"]
    if repair_result_report is None:
        repair_result_available = False
        repair_result_id = None
        repair_result_hash = None
        repair_result_status = None
        repair_result_execution: dict[str, Any] = {}
        repair_result_aggregate: dict[str, Any] = {}
    else:
        repair_result_available = True
        repair_result_id = repair_result_report["reportId"]
        repair_result_hash = repair_result_report["integrity"]["geometryRepairResultHash"]
        repair_result_status = repair_result_report["readiness"]["status"]
        repair_result_execution = repair_result_report["execution"]
        repair_result_aggregate = repair_result_report["aggregate"]
    if runtime_binding_result_report is None:
        runtime_binding_result_available = False
        runtime_binding_result_id = None
        runtime_binding_result_hash = None
        runtime_binding_result_status = None
        runtime_binding_result_execution: dict[str, Any] = {}
        runtime_binding_result_aggregate: dict[str, Any] = {}
        runtime_binding_result_quality: dict[str, Any] = {}
    else:
        runtime_binding_result_available = True
        runtime_binding_result_id = runtime_binding_result_report["reportId"]
        runtime_binding_result_hash = runtime_binding_result_report["integrity"][
            "geometryRuntimeBindingResultHash"
        ]
        runtime_binding_result_status = runtime_binding_result_report["readiness"]["status"]
        runtime_binding_result_execution = runtime_binding_result_report["execution"]
        runtime_binding_result_aggregate = runtime_binding_result_report["aggregate"]
        runtime_binding_result_quality = runtime_binding_result_report["quality"]
    if material_uv_transfer_report is None:
        material_uv_transfer_available = False
        material_uv_transfer_id = None
        material_uv_transfer_hash = None
        material_uv_transfer_status = None
        material_uv_transfer_execution: dict[str, Any] = {}
        material_uv_transfer_aggregate: dict[str, Any] = {}
        material_uv_transfer_readiness: dict[str, Any] = {}
    else:
        material_uv_transfer_available = True
        material_uv_transfer_id = material_uv_transfer_report["reportId"]
        material_uv_transfer_hash = material_uv_transfer_report["integrity"][
            "geometryMaterialUvTransferHash"
        ]
        material_uv_transfer_status = material_uv_transfer_report["readiness"]["status"]
        material_uv_transfer_execution = material_uv_transfer_report["execution"]
        material_uv_transfer_aggregate = material_uv_transfer_report["aggregate"]
        material_uv_transfer_readiness = material_uv_transfer_report["readiness"]
    if visual_shell_review_report is None:
        visual_shell_review_available = False
        visual_shell_review_id = None
        visual_shell_review_hash = None
        visual_shell_review_status = None
        visual_shell_review_execution: dict[str, Any] = {}
        visual_shell_review_aggregate: dict[str, Any] = {}
        visual_shell_review_readiness: dict[str, Any] = {}
        visual_shell_review_quality: dict[str, Any] = {}
    else:
        visual_shell_review_available = True
        visual_shell_review_id = visual_shell_review_report["reportId"]
        visual_shell_review_hash = visual_shell_review_report["integrity"][
            "geometryVisualShellReviewHash"
        ]
        visual_shell_review_status = visual_shell_review_report["readiness"]["status"]
        visual_shell_review_execution = visual_shell_review_report["execution"]
        visual_shell_review_aggregate = visual_shell_review_report["aggregate"]
        visual_shell_review_readiness = visual_shell_review_report["readiness"]
        visual_shell_review_quality = visual_shell_review_report["quality"]
    if clean_acceptance_gate_report is None:
        clean_acceptance_gate_available = False
        clean_acceptance_gate_id = None
        clean_acceptance_gate_hash = None
        clean_acceptance_gate_status = None
        clean_acceptance_gate_execution: dict[str, Any] = {}
        clean_acceptance_gate_aggregate: dict[str, Any] = {}
        clean_acceptance_gate_quality: dict[str, Any] = {}
    else:
        clean_acceptance_gate_available = True
        clean_acceptance_gate_id = clean_acceptance_gate_report["reportId"]
        clean_acceptance_gate_hash = clean_acceptance_gate_report["integrity"][
            "geometryCleanAcceptanceGateHash"
        ]
        clean_acceptance_gate_status = clean_acceptance_gate_report["readiness"]["status"]
        clean_acceptance_gate_execution = clean_acceptance_gate_report["execution"]
        clean_acceptance_gate_aggregate = clean_acceptance_gate_report["aggregate"]
        clean_acceptance_gate_quality = clean_acceptance_gate_report["quality"]
    cleanup_run = bool(cleanup_result_execution.get("cleanupRun", False))
    semantic_transfer_run = bool(semantic_transfer_execution.get("semanticTransferRun", False))
    candidate_binding_run = bool(binding_candidate_execution.get("candidateBindingRun", False))
    deformation_validation_run = bool(
        binding_validation_execution.get("deformationValidationRun", False)
    )
    repair_retopology_plan_generated = bool(
        repair_retopology_plan_execution.get("repairRetopologyPlanGenerated", False)
    )
    partial_repair_result_generated = bool(
        repair_result_execution.get("repairResultGenerated", False)
    )
    runtime_binding_result_generated = bool(
        runtime_binding_result_execution.get("runtimeBindingResultGenerated", False)
    )
    runtime_binding_written = bool(
        runtime_binding_result_execution.get("runtimeBindingWritten", False)
    )
    runtime_binding_accepted = bool(
        runtime_binding_result_execution.get("runtimeBindingAccepted", False)
    )
    clean_acceptance_gate_run = bool(
        clean_acceptance_gate_execution.get("cleanAcceptanceGateRun", False)
    )
    clean_acceptance_gate_accepted = bool(
        clean_acceptance_gate_aggregate.get("acceptedForCleanProposal", False)
    )
    material_transfer_run = bool(material_uv_transfer_execution.get("materialTransferRun", False))
    uv_transfer_run = bool(material_uv_transfer_execution.get("uvTransferRun", False))
    material_transfer_accepted = bool(
        material_uv_transfer_readiness.get("acceptedForMaterialPreview", False)
    )
    visual_fidelity_review_run = bool(
        visual_shell_review_execution.get("visualFidelityReviewRun", False)
    )
    visual_fidelity_accepted = bool(
        visual_shell_review_readiness.get("acceptedForVisualFidelity", False)
    )
    single_shell_weld_proof_run = bool(
        visual_shell_review_execution.get("singleShellWeldProofRun", False)
    )
    single_shell_weld_proven = bool(
        visual_shell_review_readiness.get("singleShellWeldProven", False)
    )
    validation_accepted = bool(binding_validation_readiness_accepts(binding_validation_report))
    rejection_reasons = _rejection_reasons(
        cleanup_run,
        semantic_transfer_run,
        candidate_binding_run,
        deformation_validation_run,
        repair_retopology_plan_generated,
        partial_repair_result_generated,
        runtime_binding_result_generated,
        runtime_binding_accepted,
        clean_acceptance_gate_run,
        clean_acceptance_gate_accepted,
        validation_accepted,
    )
    required_before_canonical = _required_before_canonical(
        cleanup_run,
        semantic_transfer_run,
        deformation_validation_run,
        repair_retopology_plan_generated,
        partial_repair_result_generated,
        runtime_binding_result_generated,
        runtime_binding_accepted,
        clean_acceptance_gate_run,
        clean_acceptance_gate_accepted,
        validation_accepted,
    )
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "proposalId": "proposal.clean_tshirt_geometry_v1",
        "stageVersion": CLEAN_GEOMETRY_PROPOSAL_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceRawProposalId": raw_geometry_proposal["proposalId"],
        "sourceRawProposalHash": raw_geometry_proposal["integrity"]["geometryProposalHash"],
        "sourceProviderRegistryId": provider_registry["registryId"],
        "sourceProviderRegistryHash": provider_registry["integrity"]["providerRegistryHash"],
        "sourceRawTopologyReportId": topology_report_id,
        "sourceRawTopologyReportHash": topology_report_hash,
        "sourceGeometryCleanupPlanId": cleanup_plan_id,
        "sourceGeometryCleanupPlanHash": cleanup_plan_hash,
        "sourceGeometryCleanupResultId": cleanup_result_id,
        "sourceGeometryCleanupResultHash": cleanup_result_hash,
        "sourceGeometrySemanticTransferId": semantic_transfer_id,
        "sourceGeometrySemanticTransferHash": semantic_transfer_hash,
        "sourceGeometryBindingCandidateId": binding_candidate_id,
        "sourceGeometryBindingCandidateHash": binding_candidate_hash,
        "sourceGeometryBindingValidationId": binding_validation_id,
        "sourceGeometryBindingValidationHash": binding_validation_hash,
        "sourceGeometryRepairRetopologyPlanId": repair_retopology_plan_id,
        "sourceGeometryRepairRetopologyPlanHash": repair_retopology_plan_hash,
        "sourceGeometryRepairResultId": repair_result_id,
        "sourceGeometryRepairResultHash": repair_result_hash,
        "sourceGeometryRuntimeBindingResultId": runtime_binding_result_id,
        "sourceGeometryRuntimeBindingResultHash": runtime_binding_result_hash,
        "sourceGeometryMaterialUvTransferId": material_uv_transfer_id,
        "sourceGeometryMaterialUvTransferHash": material_uv_transfer_hash,
        "sourceGeometryVisualShellReviewId": visual_shell_review_id,
        "sourceGeometryVisualShellReviewHash": visual_shell_review_hash,
        "sourceGeometryCleanAcceptanceGateId": clean_acceptance_gate_id,
        "sourceGeometryCleanAcceptanceGateHash": clean_acceptance_gate_hash,
        "rawProposal": {
            "available": raw_proposal["available"],
            "assetPath": raw_proposal["assetPath"],
            "sourceAssetHash": raw_proposal.get("sourceAssetHash"),
            "providerId": raw_geometry_proposal["provider"]["providerId"],
            "qualityStatus": raw_geometry_proposal["quality"]["status"],
            "acceptedForCanonical": raw_geometry_proposal["quality"]["acceptedForCanonical"],
        },
        "cleanupPipeline": {
            "topologyDiagnosticsRun": topology_available,
            "cleanupPlanGenerated": cleanup_plan_available,
            "cleanupResultGenerated": cleanup_result_available,
            "semanticTransferReportGenerated": semantic_transfer_available,
            "bindingCandidateReportGenerated": binding_candidate_available,
            "bindingValidationReportGenerated": binding_validation_available,
            "repairRetopologyPlanGenerated": repair_retopology_plan_available,
            "partialRepairResultGenerated": repair_result_available,
            "runtimeBindingResultGenerated": runtime_binding_result_available,
            "materialUvTransferReportGenerated": material_uv_transfer_available,
            "visualShellReviewGenerated": visual_shell_review_available,
            "cleanAcceptanceGateGenerated": clean_acceptance_gate_available,
            "cleanupRun": cleanup_run,
            "repairRun": bool(cleanup_result_execution.get("repairRun", False)),
            "retopologyRun": bool(runtime_binding_result_execution.get("retopologyRun", False)),
            "seamSplitRun": bool(runtime_binding_result_execution.get("seamSplitRun", False)),
            "componentStitchingRun": bool(
                runtime_binding_result_execution.get("componentStitchingRun", False)
            ),
            "normalContinuityValidationRun": bool(
                runtime_binding_result_execution.get("normalContinuityValidationRun", False)
            ),
            "tangentContinuityValidationRun": bool(
                runtime_binding_result_execution.get("tangentContinuityValidationRun", False)
            ),
            "deformationReprojectionRun": bool(
                repair_result_execution.get("deformationReprojectionRun", False)
            ),
            "semanticTransferRun": semantic_transfer_run,
            "boundaryClassificationRun": bool(
                semantic_transfer_execution.get("boundaryClassificationRun", False)
            ),
            "candidateBindingRun": candidate_binding_run,
            "deformationValidationRun": deformation_validation_run,
            "simulationBindingRun": runtime_binding_accepted,
            "runtimeBindingWritten": runtime_binding_written,
            "runtimeBindingAccepted": runtime_binding_accepted,
            "cleanAcceptanceGateRun": clean_acceptance_gate_run,
            "cleanAcceptanceGateAccepted": clean_acceptance_gate_accepted,
            "visualFidelityReviewRun": visual_fidelity_review_run,
            "providerVisualFidelityAccepted": visual_fidelity_accepted,
            "singleShellWeldProofRun": single_shell_weld_proof_run,
            "singleShellWeldProven": single_shell_weld_proven,
            "uvTransferRun": uv_transfer_run,
            "materialTransferRun": material_transfer_run,
            "materialTransferAccepted": material_transfer_accepted,
            "connectedComponentAnalysisRun": topology_available,
            "nonManifoldAnalysisRun": topology_available,
            "blockedBy": [
                "raw_visual_reference_only",
                "clean_geometry_provider_unavailable",
                "clean_acceptance_gate_rejected"
                if clean_acceptance_gate_available and clean_acceptance_gate_run
                else "clean_geometry_acceptance_gate_not_run"
                if runtime_binding_result_available and runtime_binding_accepted
                else "partial_repair_result_not_clean"
                if repair_result_available
                else "repair_retopology_plan_not_executed",
                "material_transfer_completed"
                if material_transfer_accepted
                else "material_transfer_not_run"
                if material_uv_transfer_available
                else "material_transfer_pending",
                "visual_shell_review_completed"
                if visual_shell_review_available
                else "visual_shell_review_pending",
                "provider_visual_fidelity_not_accepted"
                if runtime_binding_accepted and not visual_fidelity_accepted
                else "simulation_binding_unavailable",
                "single_shell_weld_not_proven"
                if runtime_binding_accepted and not single_shell_weld_proven
                else "single_shell_weld_ready",
            ],
            "nextRequiredStages": [
                "rendered_visual_fidelity_acceptance",
                "single_shell_stitch_weld_execution",
                "canonical_acceptance_quality_gate",
            ],
        },
        "cleanProposal": {
            "available": False,
            "assetPath": None,
            "representation": "none",
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": False,
            "reason": "runtime_bound_visual_proposal_has_not_passed_clean_acceptance"
            if runtime_binding_accepted or clean_acceptance_gate_available
            else "raw_manual_proposal_has_not_passed_cleanup_or_binding",
        },
        "cleanGeometryAudit": {
            "meshAvailable": False,
            "meshCount": 0,
            "visibleMeshCount": 0,
            "triangleEstimate": 0,
            "materialCount": 0,
            "textureCount": 0,
            "bounds": None,
            "scaleApplied": None,
            "connectedComponentCount": topology.get("componentCount"),
            "nonManifoldEdgeCount": topology.get("nonManifoldEdgeCount"),
            "degenerateTriangleCount": topology.get("degenerateTriangleCount"),
            "rawTopologyManifoldStatus": topology.get("manifoldStatus"),
            "cleanupPlanStatus": cleanup_plan_status,
            "cleanupResultStatus": cleanup_result_status,
            "cleanupPreviewAssetPath": cleanup_result_output.get("path"),
            "cleanupPreviewAssetHash": cleanup_result_output.get("sourceAssetHash"),
            "postCleanupComponentCount": cleanup_result_topology_after.get("componentCount"),
            "postCleanupBoundaryEdgeCount": cleanup_result_topology_after.get("boundaryEdgeCount"),
            "postCleanupDuplicatePositionCount": cleanup_result_topology_after.get(
                "duplicatePositionCount"
            ),
            "semanticTransferStatus": semantic_transfer_status,
            "transferredPanelCount": semantic_transfer_aggregate.get("transferredPanelCount"),
            "classifiedBoundaryEdgeCount": semantic_transfer_aggregate.get(
                "classifiedBoundaryEdgeCount"
            ),
            "unclassifiedBoundaryEdgeCount": semantic_transfer_aggregate.get(
                "unclassifiedBoundaryEdgeCount"
            ),
            "ambiguousBoundaryEdgeCount": semantic_transfer_aggregate.get(
                "ambiguousBoundaryEdgeCount"
            ),
            "bindingCandidateStatus": binding_candidate_status,
            "bindingCandidateMappedVertexCount": binding_candidate_aggregate.get(
                "mappedVertexCount"
            ),
            "bindingCandidateUnmappedVertexCount": binding_candidate_aggregate.get(
                "unmappedVertexCount"
            ),
            "bindingCandidateCompleteness": binding_candidate_aggregate.get(
                "candidateCompleteness"
            ),
            "bindingValidationStatus": binding_validation_status,
            "bindingValidationMaxOffsetMeters": binding_validation_aggregate.get(
                "maxCleanupToSettledOffsetMeters"
            ),
            "bindingValidationRmsOffsetMeters": binding_validation_aggregate.get(
                "rmsCleanupToSettledOffsetMeters"
            ),
            "bindingValidationFailedCheckCount": binding_validation_quality.get("failedCheckCount"),
            "bindingValidationNotRunCheckCount": binding_validation_quality.get("notRunCheckCount"),
            "repairRetopologyPlanStatus": repair_retopology_plan_status,
            "repairRetopologyRequiredOperationCount": repair_retopology_plan_aggregate.get(
                "requiredOperationCount"
            ),
            "repairRetopologyEstimatedComplexity": repair_retopology_plan_aggregate.get(
                "estimatedRepairComplexity"
            ),
            "repairResultStatus": repair_result_status,
            "repairResultMovedVertexCount": repair_result_aggregate.get("movedVertexCount"),
            "repairResultDeferredOperationCount": repair_result_aggregate.get(
                "deferredOperationCount"
            ),
            "repairResultMaxOutputToSettledOffsetMeters": repair_result_aggregate.get(
                "maxOutputToSettledOffsetMeters"
            ),
            "runtimeBindingResultStatus": runtime_binding_result_status,
            "runtimeBindingResultQualityStatus": runtime_binding_result_quality.get("status"),
            "runtimeBindingRecordCount": runtime_binding_result_aggregate.get(
                "runtimeBindingRecordCount"
            ),
            "runtimeBindingAccepted": runtime_binding_accepted,
            "runtimeBindingMaxReconstructionError": runtime_binding_result_aggregate.get(
                "maxReconstructionError"
            ),
            "runtimeBindingFailedOrWarnCheckCount": runtime_binding_result_aggregate.get(
                "failedOrWarnCheckCount"
            ),
            "simulationBindingRecordCount": runtime_binding_result_aggregate.get(
                "runtimeBindingRecordCount", 0
            ),
            "materialUvTransferStatus": material_uv_transfer_status,
            "materialUvTransferRun": uv_transfer_run and material_transfer_run,
            "materialTransferAccepted": material_transfer_accepted,
            "materialTransferTransferredMaterialCount": material_uv_transfer_aggregate.get(
                "transferredMaterialCount"
            ),
            "materialTransferMissingMaterialCount": material_uv_transfer_aggregate.get(
                "missingMaterialCount"
            ),
            "materialTransferMissingUvCount": material_uv_transfer_aggregate.get("missingUvCount"),
            "visualShellReviewStatus": visual_shell_review_status,
            "visualShellReviewQualityStatus": visual_shell_review_quality.get("status"),
            "visualFidelityReviewRun": visual_fidelity_review_run,
            "visualFidelityScore": visual_shell_review_aggregate.get("visualFidelityScore"),
            "providerVisualFidelityAccepted": visual_fidelity_accepted,
            "renderedPixelComparisonRun": visual_shell_review_aggregate.get(
                "renderedPixelComparisonRun"
            ),
            "singleShellWeldProofRun": single_shell_weld_proof_run,
            "singleShellWeldProven": single_shell_weld_proven,
            "cleanAcceptanceGateStatus": clean_acceptance_gate_status,
            "cleanAcceptanceGateQualityStatus": clean_acceptance_gate_quality.get("status"),
            "cleanAcceptanceGateRun": clean_acceptance_gate_run,
            "cleanAcceptanceGateAccepted": clean_acceptance_gate_accepted,
            "cleanAcceptanceGateFailedCheckCount": clean_acceptance_gate_aggregate.get(
                "failedCheckCount"
            ),
            "cleanAcceptanceGateWarningCheckCount": clean_acceptance_gate_aggregate.get(
                "warningCheckCount"
            ),
            "cleanAcceptanceGateNotRunCheckCount": clean_acceptance_gate_aggregate.get(
                "notRunCheckCount"
            ),
            "failureReason": "clean_geometry_proposal_not_generated",
        },
        "canonicalization": {
            "coordinateConvention": COORDINATE_CONVENTION,
            "submittedAt": FIXED_TIMESTAMP,
            "canonicalUseAllowed": False,
            "forbiddenReason": "raw_provider_output_requires_cleanup_repair_and_semantic_binding",
            "requiredBeforeCanonical": required_before_canonical,
        },
        "quality": {
            "status": "rejected",
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": False,
            "rejectionReasons": rejection_reasons,
            "warnings": [
                "clean_geometry_proposal_not_available",
                "raw_visual_reference_not_simulation_ready",
                "geometry_cleanup_result_available_but_not_clean"
                if cleanup_result_available
                else "geometry_cleanup_result_not_generated",
                "geometry_semantic_transfer_available_but_not_bound"
                if semantic_transfer_available
                else "geometry_semantic_transfer_not_generated",
                "geometry_binding_candidate_available_but_not_runtime_binding"
                if binding_candidate_available
                else "geometry_binding_candidate_not_generated",
                "geometry_binding_validation_rejected_runtime_binding"
                if binding_validation_available
                else "geometry_binding_validation_not_generated",
                "geometry_repair_retopology_plan_available_but_not_executed"
                if repair_retopology_plan_available
                else "geometry_repair_retopology_plan_not_generated",
                "geometry_repair_result_partial_reprojection_not_clean"
                if repair_result_available
                else "geometry_repair_result_not_generated",
                "geometry_runtime_binding_result_available_but_clean_not_accepted"
                if runtime_binding_result_available
                else "geometry_runtime_binding_result_not_generated",
                "geometry_clean_acceptance_gate_rejected"
                if clean_acceptance_gate_available
                else "geometry_clean_acceptance_gate_not_generated",
                "geometry_cleanup_plan_generated_without_execution"
                if cleanup_plan_available
                else "geometry_cleanup_plan_not_generated",
                "topology_diagnostics_completed_without_repair"
                if topology_available
                else "topology_diagnostics_not_run",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"cleanGeometryProposalHash": ""},
    }
    report["integrity"]["cleanGeometryProposalHash"] = hash_clean_geometry_proposal(report)
    return report


def clean_geometry_proposal_quality_report(proposal: dict[str, Any]) -> dict[str, Any]:
    cleanup = proposal["cleanupPipeline"]
    audit = proposal["cleanGeometryAudit"]
    quality = proposal["quality"]
    clean = proposal["cleanProposal"]
    return {
        "schemaVersion": 1,
        "status": quality["status"],
        "proposalId": proposal["proposalId"],
        "sourceRawProposalId": proposal["sourceRawProposalId"],
        "sourceProviderRegistryId": proposal["sourceProviderRegistryId"],
        "rawProposalAvailable": proposal["rawProposal"]["available"],
        "rawAssetPath": proposal["rawProposal"]["assetPath"],
        "rawAssetHash": proposal["rawProposal"]["sourceAssetHash"],
        "cleanProposalAvailable": clean["available"],
        "acceptedForCanonical": quality["acceptedForCanonical"],
        "acceptedForSimulation": quality["acceptedForSimulation"],
        "acceptedForRuntimeRender": quality["acceptedForRuntimeRender"],
        "cleanupRun": cleanup["cleanupRun"],
        "repairRun": cleanup["repairRun"],
        "semanticTransferRun": cleanup["semanticTransferRun"],
        "simulationBindingRun": cleanup["simulationBindingRun"],
        "topologyDiagnosticsRun": cleanup["topologyDiagnosticsRun"],
        "cleanupPlanGenerated": cleanup["cleanupPlanGenerated"],
        "cleanupResultGenerated": cleanup["cleanupResultGenerated"],
        "semanticTransferReportGenerated": cleanup["semanticTransferReportGenerated"],
        "bindingCandidateReportGenerated": cleanup["bindingCandidateReportGenerated"],
        "bindingValidationReportGenerated": cleanup["bindingValidationReportGenerated"],
        "repairRetopologyPlanGenerated": cleanup["repairRetopologyPlanGenerated"],
        "partialRepairResultGenerated": cleanup["partialRepairResultGenerated"],
        "runtimeBindingResultGenerated": cleanup["runtimeBindingResultGenerated"],
        "materialUvTransferReportGenerated": cleanup["materialUvTransferReportGenerated"],
        "visualShellReviewGenerated": cleanup["visualShellReviewGenerated"],
        "cleanAcceptanceGateGenerated": cleanup["cleanAcceptanceGateGenerated"],
        "retopologyRun": cleanup["retopologyRun"],
        "seamSplitRun": cleanup["seamSplitRun"],
        "componentStitchingRun": cleanup["componentStitchingRun"],
        "normalContinuityValidationRun": cleanup["normalContinuityValidationRun"],
        "tangentContinuityValidationRun": cleanup["tangentContinuityValidationRun"],
        "deformationReprojectionRun": cleanup["deformationReprojectionRun"],
        "runtimeBindingWritten": cleanup["runtimeBindingWritten"],
        "runtimeBindingAccepted": cleanup["runtimeBindingAccepted"],
        "cleanAcceptanceGateRun": cleanup["cleanAcceptanceGateRun"],
        "cleanAcceptanceGateAccepted": cleanup["cleanAcceptanceGateAccepted"],
        "visualFidelityReviewRun": cleanup["visualFidelityReviewRun"],
        "providerVisualFidelityAccepted": cleanup["providerVisualFidelityAccepted"],
        "singleShellWeldProofRun": cleanup["singleShellWeldProofRun"],
        "singleShellWeldProven": cleanup["singleShellWeldProven"],
        "uvTransferRun": cleanup["uvTransferRun"],
        "materialTransferRun": cleanup["materialTransferRun"],
        "materialTransferAccepted": cleanup["materialTransferAccepted"],
        "connectedComponentAnalysisRun": cleanup["connectedComponentAnalysisRun"],
        "nonManifoldAnalysisRun": cleanup["nonManifoldAnalysisRun"],
        "connectedComponentCount": audit["connectedComponentCount"],
        "nonManifoldEdgeCount": audit["nonManifoldEdgeCount"],
        "degenerateTriangleCount": audit["degenerateTriangleCount"],
        "cleanupPlanStatus": audit["cleanupPlanStatus"],
        "cleanupResultStatus": audit["cleanupResultStatus"],
        "cleanupPreviewAssetPath": audit["cleanupPreviewAssetPath"],
        "postCleanupDuplicatePositionCount": audit["postCleanupDuplicatePositionCount"],
        "semanticTransferStatus": audit["semanticTransferStatus"],
        "transferredPanelCount": audit["transferredPanelCount"],
        "classifiedBoundaryEdgeCount": audit["classifiedBoundaryEdgeCount"],
        "unclassifiedBoundaryEdgeCount": audit["unclassifiedBoundaryEdgeCount"],
        "bindingCandidateStatus": audit["bindingCandidateStatus"],
        "bindingCandidateMappedVertexCount": audit["bindingCandidateMappedVertexCount"],
        "bindingCandidateUnmappedVertexCount": audit["bindingCandidateUnmappedVertexCount"],
        "bindingCandidateCompleteness": audit["bindingCandidateCompleteness"],
        "bindingValidationStatus": audit["bindingValidationStatus"],
        "bindingValidationMaxOffsetMeters": audit["bindingValidationMaxOffsetMeters"],
        "bindingValidationRmsOffsetMeters": audit["bindingValidationRmsOffsetMeters"],
        "bindingValidationFailedCheckCount": audit["bindingValidationFailedCheckCount"],
        "bindingValidationNotRunCheckCount": audit["bindingValidationNotRunCheckCount"],
        "repairRetopologyPlanStatus": audit["repairRetopologyPlanStatus"],
        "repairRetopologyRequiredOperationCount": audit["repairRetopologyRequiredOperationCount"],
        "repairRetopologyEstimatedComplexity": audit["repairRetopologyEstimatedComplexity"],
        "repairResultStatus": audit["repairResultStatus"],
        "repairResultMovedVertexCount": audit["repairResultMovedVertexCount"],
        "repairResultDeferredOperationCount": audit["repairResultDeferredOperationCount"],
        "repairResultMaxOutputToSettledOffsetMeters": audit[
            "repairResultMaxOutputToSettledOffsetMeters"
        ],
        "runtimeBindingResultStatus": audit["runtimeBindingResultStatus"],
        "runtimeBindingResultQualityStatus": audit["runtimeBindingResultQualityStatus"],
        "runtimeBindingRecordCount": audit["runtimeBindingRecordCount"],
        "runtimeBindingMaxReconstructionError": audit["runtimeBindingMaxReconstructionError"],
        "runtimeBindingFailedOrWarnCheckCount": audit["runtimeBindingFailedOrWarnCheckCount"],
        "materialUvTransferStatus": audit["materialUvTransferStatus"],
        "materialUvTransferRun": audit["materialUvTransferRun"],
        "materialTransferTransferredMaterialCount": audit[
            "materialTransferTransferredMaterialCount"
        ],
        "materialTransferMissingMaterialCount": audit["materialTransferMissingMaterialCount"],
        "materialTransferMissingUvCount": audit["materialTransferMissingUvCount"],
        "visualShellReviewStatus": audit["visualShellReviewStatus"],
        "visualShellReviewQualityStatus": audit["visualShellReviewQualityStatus"],
        "visualFidelityScore": audit["visualFidelityScore"],
        "renderedPixelComparisonRun": audit["renderedPixelComparisonRun"],
        "cleanAcceptanceGateStatus": audit["cleanAcceptanceGateStatus"],
        "cleanAcceptanceGateQualityStatus": audit["cleanAcceptanceGateQualityStatus"],
        "cleanAcceptanceGateFailedCheckCount": audit["cleanAcceptanceGateFailedCheckCount"],
        "cleanAcceptanceGateWarningCheckCount": audit["cleanAcceptanceGateWarningCheckCount"],
        "cleanAcceptanceGateNotRunCheckCount": audit["cleanAcceptanceGateNotRunCheckCount"],
        "meshCount": audit["meshCount"],
        "triangleEstimate": audit["triangleEstimate"],
        "failureReason": audit["failureReason"],
        "rejectionReasons": quality["rejectionReasons"],
        "warnings": quality["warnings"],
    }


def hash_clean_geometry_proposal(proposal: dict[str, Any]) -> str:
    payload = deepcopy(proposal)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["cleanGeometryProposalHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def binding_validation_readiness_accepts(
    binding_validation_report: dict[str, Any] | None,
) -> bool:
    if binding_validation_report is None:
        return False
    readiness = binding_validation_report.get("readiness", {})
    return (
        isinstance(readiness, dict)
        and readiness.get("acceptedForCleanProposal") is True
        and readiness.get("acceptedForSimulation") is True
        and readiness.get("acceptedForRuntimeRender") is True
    )


def _rejection_reasons(
    cleanup_run: bool,
    semantic_transfer_run: bool,
    candidate_binding_run: bool,
    deformation_validation_run: bool,
    repair_retopology_plan_generated: bool,
    partial_repair_result_generated: bool,
    runtime_binding_result_generated: bool,
    runtime_binding_accepted: bool,
    clean_acceptance_gate_run: bool,
    clean_acceptance_gate_accepted: bool,
    validation_accepted: bool,
) -> list[str]:
    if (
        cleanup_run
        and semantic_transfer_run
        and candidate_binding_run
        and deformation_validation_run
        and repair_retopology_plan_generated
        and partial_repair_result_generated
        and runtime_binding_result_generated
        and runtime_binding_accepted
        and clean_acceptance_gate_run
        and not clean_acceptance_gate_accepted
    ):
        return CLEAN_ACCEPTANCE_GATE_REJECTION_REASONS
    if (
        cleanup_run
        and semantic_transfer_run
        and candidate_binding_run
        and deformation_validation_run
        and repair_retopology_plan_generated
        and partial_repair_result_generated
        and runtime_binding_result_generated
        and runtime_binding_accepted
    ):
        return PARTIAL_RUNTIME_BINDING_RESULT_REJECTION_REASONS
    if (
        cleanup_run
        and semantic_transfer_run
        and candidate_binding_run
        and deformation_validation_run
        and repair_retopology_plan_generated
        and partial_repair_result_generated
        and not validation_accepted
    ):
        return PARTIAL_REPAIR_RESULT_REJECTION_REASONS
    if (
        cleanup_run
        and semantic_transfer_run
        and candidate_binding_run
        and deformation_validation_run
        and repair_retopology_plan_generated
        and not validation_accepted
    ):
        return PARTIAL_REPAIR_RETOPOLOGY_PLAN_REJECTION_REASONS
    if (
        cleanup_run
        and semantic_transfer_run
        and candidate_binding_run
        and deformation_validation_run
        and not validation_accepted
    ):
        return PARTIAL_BINDING_VALIDATION_REJECTION_REASONS
    if cleanup_run and semantic_transfer_run:
        return PARTIAL_SEMANTIC_TRANSFER_REJECTION_REASONS
    if cleanup_run:
        return PARTIAL_CLEANUP_REJECTION_REASONS
    return REQUIRED_CLEAN_REJECTION_REASONS


def _required_before_canonical(
    cleanup_run: bool,
    semantic_transfer_run: bool,
    deformation_validation_run: bool,
    repair_retopology_plan_generated: bool,
    partial_repair_result_generated: bool,
    runtime_binding_result_generated: bool,
    runtime_binding_accepted: bool,
    clean_acceptance_gate_run: bool,
    clean_acceptance_gate_accepted: bool,
    validation_accepted: bool,
) -> list[str]:
    required = [
        "partial_repair_incomplete" if partial_repair_result_generated else "repair_not_run",
        "clean_acceptance_gate_not_run"
        if runtime_binding_result_generated and runtime_binding_accepted
        else "simulation_binding_missing",
    ]
    if not cleanup_run:
        required.insert(0, "cleanup_not_run")
    else:
        required.insert(0, "cleanup_incomplete")
    if not semantic_transfer_run:
        required.insert(2, "semantic_transfer_missing")
    if deformation_validation_run and not validation_accepted:
        required.insert(-1, "binding_deformation_validation_failed")
    if repair_retopology_plan_generated and not partial_repair_result_generated:
        required.insert(-1, "repair_retopology_plan_not_executed")
    if partial_repair_result_generated:
        required.insert(-1, "retopology_not_run")
    if runtime_binding_result_generated and runtime_binding_accepted:
        required = [
            item
            for item in required
            if item not in {"partial_repair_incomplete", "retopology_not_run"}
        ]
        if clean_acceptance_gate_run and not clean_acceptance_gate_accepted:
            required.insert(-1, "clean_acceptance_gate_rejected")
            required.insert(-1, "visual_fidelity_review_not_accepted")
            required.insert(-1, "single_shell_weld_not_proven")
        else:
            required.insert(-1, "provider_visual_fidelity_not_accepted")
    required.append("provider_output_not_canonical_garment_truth")
    return required
