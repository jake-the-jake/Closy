from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.contracts.common import COORDINATE_CONVENTION, FIXED_TIMESTAMP
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

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


def build_clean_geometry_proposal_rejection(
    *,
    garment_id: str,
    garment_class: str,
    raw_geometry_proposal: dict[str, Any],
    provider_registry: dict[str, Any],
    raw_topology_report: dict[str, Any] | None = None,
    cleanup_plan_report: dict[str, Any] | None = None,
    cleanup_result_report: dict[str, Any] | None = None,
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
    cleanup_run = bool(cleanup_result_execution.get("cleanupRun", False))
    rejection_reasons = (
        PARTIAL_CLEANUP_REJECTION_REASONS if cleanup_run else REQUIRED_CLEAN_REJECTION_REASONS
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
            "cleanupRun": cleanup_run,
            "repairRun": bool(cleanup_result_execution.get("repairRun", False)),
            "retopologyRun": False,
            "semanticTransferRun": False,
            "simulationBindingRun": False,
            "uvTransferRun": False,
            "materialTransferRun": False,
            "connectedComponentAnalysisRun": topology_available,
            "nonManifoldAnalysisRun": topology_available,
            "blockedBy": [
                "raw_visual_reference_only",
                "clean_geometry_provider_unavailable",
                "semantic_correspondence_unavailable",
                "simulation_binding_unavailable",
            ],
            "nextRequiredStages": [
                "mesh_cleanup_and_repair",
                "semantic_garment_region_transfer",
                "simulation_ready_topology_or_binding",
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
            "reason": "raw_manual_proposal_has_not_passed_cleanup_or_binding",
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
            "simulationBindingRecordCount": 0,
            "failureReason": "clean_geometry_proposal_not_generated",
        },
        "canonicalization": {
            "coordinateConvention": COORDINATE_CONVENTION,
            "submittedAt": FIXED_TIMESTAMP,
            "canonicalUseAllowed": False,
            "forbiddenReason": "raw_provider_output_requires_cleanup_repair_and_semantic_binding",
            "requiredBeforeCanonical": REQUIRED_CLEAN_REJECTION_REASONS,
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
        "connectedComponentAnalysisRun": cleanup["connectedComponentAnalysisRun"],
        "nonManifoldAnalysisRun": cleanup["nonManifoldAnalysisRun"],
        "connectedComponentCount": audit["connectedComponentCount"],
        "nonManifoldEdgeCount": audit["nonManifoldEdgeCount"],
        "degenerateTriangleCount": audit["degenerateTriangleCount"],
        "cleanupPlanStatus": audit["cleanupPlanStatus"],
        "cleanupResultStatus": audit["cleanupResultStatus"],
        "cleanupPreviewAssetPath": audit["cleanupPreviewAssetPath"],
        "postCleanupDuplicatePositionCount": audit["postCleanupDuplicatePositionCount"],
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
