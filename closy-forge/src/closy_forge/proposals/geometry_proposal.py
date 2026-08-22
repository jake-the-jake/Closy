from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.contracts.common import COORDINATE_CONVENTION, FIXED_TIMESTAMP
from closy_forge.geometry.glb_io import audit_glb
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

GEOMETRY_PROPOSAL_VERSION = "closy.geometry_proposal.manual_local_glb_import.v1"
NULL_GEOMETRY_PROPOSAL_VERSION = "closy.geometry_proposal.null_provider.v1"


def build_null_geometry_proposal(
    *,
    garment_id: str,
    garment_class: str,
    capture_record: dict[str, Any],
    visual_observations: dict[str, Any],
    fit_report: dict[str, Any],
    texture_identity: dict[str, Any],
) -> dict[str, Any]:
    """Exercise the provider boundary without accepting fake generated geometry."""

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "proposalId": "proposal.null_tshirt_visual_geometry_v1",
        "stageVersion": NULL_GEOMETRY_PROPOSAL_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceRecordId": capture_record["recordId"],
        "sourceRecordHash": capture_record["immutability"]["sourceRecordHash"],
        "sourceVisualUnderstandingId": visual_observations["visualUnderstandingId"],
        "sourceVisualRecordHash": visual_observations["integrity"]["visualRecordHash"],
        "sourceFitReportId": fit_report["fitReportId"],
        "sourceFitReportHash": fit_report["integrity"]["fitReportHash"],
        "sourceTextureIdentityId": texture_identity["textureIdentityId"],
        "sourceTextureIdentityHash": texture_identity["integrity"]["textureIdentityHash"],
        "provider": {
            "providerId": "closy.null_geometry_proposal_provider.v1",
            "providerKind": "deterministic_null_test_adapter",
            "modelId": "none",
            "modelVersion": "none",
            "runtimeExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "termsReviewed": True,
        },
        "request": {
            "purpose": "garment_visual_geometry_proposal",
            "supportedDomain": "avatar_garment_only",
            "garmentClass": garment_class,
            "desiredTopologyStyle": "raw_visual_proposal_not_simulation_ready",
            "targetResolution": "contract_test_no_generation",
            "texturePbrRequested": bool(texture_identity["textureProjectionRun"]),
            "deterministicSeed": 101,
            "submittedAt": FIXED_TIMESTAMP,
        },
        "rawProposal": {
            "available": False,
            "assetPath": None,
            "representation": "none",
            "noCanonicalUse": True,
            "reason": "null_provider_no_geometry_generated",
        },
        "cleanProposal": {
            "available": False,
            "assetPath": None,
            "representation": "none",
            "reason": "raw_proposal_rejected_before_cleaning",
        },
        "alignmentRules": {
            "coordinateConvention": COORDINATE_CONVENTION,
            "unitScale": "metres",
            "groundPlane": "Y=0",
            "forwardAxis": "+Z",
            "centerPolicy": "center_xz_and_place_feet_on_ground_when_geometry_exists",
            "scalePolicy": "normalise_to_avatar_contract_height_when_geometry_exists",
            "windingPolicy": "counter_clockwise_front_face",
        },
        "geometryAudit": {
            "meshAvailable": False,
            "meshCount": 0,
            "visibleMeshCount": 0,
            "triangleEstimate": 0,
            "materialCount": 0,
            "textureCount": 0,
            "bounds": None,
            "scaleApplied": None,
            "failureReason": "null_provider_no_geometry_generated",
        },
        "quality": {
            "status": "rejected",
            "acceptedForCanonical": False,
            "acceptedForVisualReference": False,
            "rejectionReasons": [
                "no_geometry_asset",
                "null_provider_contract_only",
                "raw_proposal_not_simulation_ready",
            ],
            "warnings": [
                "provider_adapter_scaffold_only",
                "no_raw_mesh_generated",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"geometryProposalHash": ""},
    }
    report["integrity"]["geometryProposalHash"] = hash_geometry_proposal(report)
    return report


def build_manual_geometry_proposal(
    *,
    garment_id: str,
    garment_class: str,
    capture_record: dict[str, Any],
    visual_observations: dict[str, Any],
    fit_report: dict[str, Any],
    texture_identity: dict[str, Any],
    asset_path: Path,
    package_asset_path: str,
) -> dict[str, Any]:
    """Import a local GLB as raw visual evidence while rejecting canonical use."""

    audit = audit_glb(asset_path)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "proposalId": "proposal.manual_tshirt_raw_visual_geometry_v1",
        "stageVersion": GEOMETRY_PROPOSAL_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceRecordId": capture_record["recordId"],
        "sourceRecordHash": capture_record["immutability"]["sourceRecordHash"],
        "sourceVisualUnderstandingId": visual_observations["visualUnderstandingId"],
        "sourceVisualRecordHash": visual_observations["integrity"]["visualRecordHash"],
        "sourceFitReportId": fit_report["fitReportId"],
        "sourceFitReportHash": fit_report["integrity"]["fitReportHash"],
        "sourceTextureIdentityId": texture_identity["textureIdentityId"],
        "sourceTextureIdentityHash": texture_identity["integrity"]["textureIdentityHash"],
        "provider": {
            "providerId": "closy.manual_local_glb_import.v1",
            "providerKind": "manual_local_asset_import_adapter",
            "modelId": "project_authored_manual_fixture",
            "modelVersion": "closy.manual_tshirt_fixture.v1",
            "runtimeExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "termsReviewed": True,
        },
        "request": {
            "purpose": "garment_visual_geometry_proposal",
            "supportedDomain": "avatar_garment_only",
            "garmentClass": garment_class,
            "desiredTopologyStyle": "raw_visual_proposal_not_simulation_ready",
            "targetResolution": "package_contained_manual_fixture_glb",
            "texturePbrRequested": bool(texture_identity["textureProjectionRun"]),
            "deterministicSeed": 101,
            "submittedAt": FIXED_TIMESTAMP,
        },
        "rawProposal": {
            "available": True,
            "assetPath": package_asset_path,
            "representation": "glb2_triangle_mesh",
            "noCanonicalUse": True,
            "reason": "manual_fixture_available_for_visual_reference_only",
            "sourceAssetHash": sha256_file(asset_path),
            "byteSize": asset_path.stat().st_size,
        },
        "cleanProposal": {
            "available": False,
            "assetPath": None,
            "representation": "none",
            "reason": "raw_manual_proposal_not_cleaned_or_bound_to_canonical_topology",
        },
        "alignmentRules": {
            "coordinateConvention": COORDINATE_CONVENTION,
            "unitScale": "metres",
            "groundPlane": "Y=0",
            "forwardAxis": "+Z",
            "centerPolicy": "center_xz_and_place_feet_on_ground_when_geometry_exists",
            "scalePolicy": "normalise_to_avatar_contract_height_when_geometry_exists",
            "windingPolicy": "counter_clockwise_front_face",
        },
        "geometryAudit": {
            "meshAvailable": True,
            "meshCount": audit["meshCount"],
            "visibleMeshCount": audit["primitiveCount"],
            "triangleEstimate": audit["triangleEstimate"],
            "materialCount": audit["materialCount"],
            "textureCount": 0,
            "bounds": None,
            "scaleApplied": None,
            "failureReason": None,
        },
        "quality": {
            "status": "accepted_visual_reference",
            "acceptedForCanonical": False,
            "acceptedForVisualReference": True,
            "rejectionReasons": [
                "raw_proposal_not_simulation_ready",
                "clean_geometry_proposal_not_available",
                "provider_output_not_canonical_garment_truth",
            ],
            "warnings": [
                "manual_fixture_not_production_provider",
                "clean_geometry_proposal_not_generated",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"geometryProposalHash": ""},
    }
    report["integrity"]["geometryProposalHash"] = hash_geometry_proposal(report)
    return report


def geometry_proposal_quality_report(proposal: dict[str, Any]) -> dict[str, Any]:
    audit = proposal["geometryAudit"]
    quality = proposal["quality"]
    return {
        "schemaVersion": 1,
        "status": quality["status"],
        "proposalId": proposal["proposalId"],
        "providerId": proposal["provider"]["providerId"],
        "providerKind": proposal["provider"]["providerKind"],
        "rawProposalAvailable": proposal["rawProposal"]["available"],
        "cleanProposalAvailable": proposal["cleanProposal"]["available"],
        "acceptedForCanonical": quality["acceptedForCanonical"],
        "meshCount": audit["meshCount"],
        "visibleMeshCount": audit["visibleMeshCount"],
        "triangleEstimate": audit["triangleEstimate"],
        "failureReason": audit["failureReason"],
        "rejectionReasons": quality["rejectionReasons"],
        "warnings": quality["warnings"],
    }


def hash_geometry_proposal(proposal: dict[str, Any]) -> str:
    payload = deepcopy(proposal)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["geometryProposalHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
