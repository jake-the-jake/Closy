from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.contracts.common import COORDINATE_CONVENTION, FIXED_TIMESTAMP
from closy_forge.geometry.glb_io import audit_glb
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

PROVIDER_REGISTRY_VERSION = "closy.geometry_provider_registry.v1"
MANUAL_IMPORT_PROVIDER_ID = "closy.manual_local_glb_import.v1"
NULL_GEOMETRY_PROVIDER_ID = "closy.null_geometry_proposal_provider.v1"


def build_geometry_provider_registry(
    *,
    garment_id: str,
    garment_class: str,
    capture_record: dict[str, Any],
    visual_observations: dict[str, Any],
    fit_report: dict[str, Any],
    texture_identity: dict[str, Any],
    geometry_proposal: dict[str, Any],
    manual_asset_path: Path | None = None,
) -> dict[str, Any]:
    """Record allowed geometry providers without pretending a missing provider ran."""

    manual_candidate = inspect_manual_import_candidate(manual_asset_path)
    registry: dict[str, Any] = {
        "schemaVersion": 1,
        "registryId": "provider_registry.geometry_tshirt_reference_v1",
        "stageVersion": PROVIDER_REGISTRY_VERSION,
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
        "sourceGeometryProposalId": geometry_proposal["proposalId"],
        "sourceGeometryProposalHash": geometry_proposal["integrity"]["geometryProposalHash"],
        "scope": {
            "supportedDomain": "avatar_garment_only",
            "supportedPurposes": ["garment_visual_geometry_proposal"],
            "supportedGarmentClasses": [garment_class],
            "allowsGenericObjects": False,
            "unsupportedPurposePolicy": "reject_before_provider_execution",
        },
        "selectedProviderId": NULL_GEOMETRY_PROVIDER_ID,
        "selectionReason": "demo_package_has_no_operator_supplied_manual_glb_asset",
        "providers": [
            _null_provider(),
            _manual_import_provider(manual_candidate),
        ],
        "futureProviderSlots": [
            {
                "providerId": "meshy.image_to_3d.future",
                "status": "unconfigured_external_slot",
                "reason": (
                    "requires explicit consent, credentials, terms review and isolated worker"
                ),
            },
            {
                "providerId": "trellis.visual_geometry.future",
                "status": "unconfigured_external_or_local_research_slot",
                "reason": "requires model/licence review and isolated dependency environment",
            },
            {
                "providerId": "hunyuan3d.visual_geometry.future",
                "status": "unconfigured_external_or_local_research_slot",
                "reason": "requires model/licence review and isolated dependency environment",
            },
        ],
        "manualImportCandidate": manual_candidate,
        "d0Capabilities": {
            "providerRegistryAvailable": True,
            "nullProviderAvailable": True,
            "manualLocalImportAdapterDeclared": True,
            "manualLocalImportAssetAvailable": manual_candidate["acceptedForRawProposal"],
            "externalProvidersConfigured": False,
            "cleanProposalProviderAvailable": False,
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
            "providerDisclosureRequiredBeforeExternalUse": True,
        },
        "integrity": {"providerRegistryHash": ""},
    }
    registry["integrity"]["providerRegistryHash"] = hash_provider_registry(registry)
    return registry


def inspect_manual_import_candidate(asset_path: Path | None) -> dict[str, Any]:
    contract = _manual_import_contract()
    if asset_path is None:
        return _manual_candidate_result(
            status="missing_local_asset",
            accepted=False,
            failure_reason="manual_glb_asset_not_supplied",
            contract=contract,
        )

    candidate = Path(asset_path)
    if any(part == ".." for part in candidate.parts):
        return _manual_candidate_result(
            status="rejected",
            accepted=False,
            failure_reason="unsafe_path_traversal",
            contract=contract,
            asset_name=candidate.name,
        )
    if candidate.suffix.lower() != ".glb":
        return _manual_candidate_result(
            status="rejected",
            accepted=False,
            failure_reason="unsupported_manual_asset_extension",
            contract=contract,
            asset_name=candidate.name,
        )
    if not candidate.exists():
        return _manual_candidate_result(
            status="missing_local_asset",
            accepted=False,
            failure_reason="manual_glb_asset_not_found",
            contract=contract,
            asset_name=candidate.name,
        )
    if not candidate.is_file():
        return _manual_candidate_result(
            status="rejected",
            accepted=False,
            failure_reason="manual_glb_asset_not_a_file",
            contract=contract,
            asset_name=candidate.name,
        )
    try:
        audit = audit_glb(candidate)
    except Exception as exc:
        return _manual_candidate_result(
            status="rejected",
            accepted=False,
            failure_reason=f"manual_glb_audit_failed:{type(exc).__name__}",
            contract=contract,
            asset_name=candidate.name,
        )

    accepted = bool(
        audit.get("validGlb20") is True
        and int(audit.get("meshCount", 0)) > 0
        and int(audit.get("primitiveCount", 0)) > 0
        and int(audit.get("triangleEstimate", 0)) > 0
    )
    return _manual_candidate_result(
        status="eligible_raw_visual_proposal" if accepted else "rejected",
        accepted=accepted,
        failure_reason=None if accepted else "manual_glb_has_no_renderable_geometry",
        contract=contract,
        asset_name=candidate.name,
        asset_hash=sha256_file(candidate),
        byte_size=candidate.stat().st_size,
        audit=audit,
    )


def provider_registry_quality_report(registry: dict[str, Any]) -> dict[str, Any]:
    capabilities = registry["d0Capabilities"]
    manual = registry["manualImportCandidate"]
    return {
        "schemaVersion": 1,
        "status": "pass",
        "registryId": registry["registryId"],
        "selectedProviderId": registry["selectedProviderId"],
        "selectionReason": registry["selectionReason"],
        "providerCount": len(registry["providers"]),
        "futureProviderSlotCount": len(registry["futureProviderSlots"]),
        "manualLocalImportAdapterDeclared": capabilities["manualLocalImportAdapterDeclared"],
        "manualLocalImportAssetAvailable": capabilities["manualLocalImportAssetAvailable"],
        "externalProvidersConfigured": capabilities["externalProvidersConfigured"],
        "cleanProposalProviderAvailable": capabilities["cleanProposalProviderAvailable"],
        "manualImportStatus": manual["status"],
        "manualImportFailureReason": manual["failureReason"],
        "policy": registry["policy"],
    }


def hash_provider_registry(registry: dict[str, Any]) -> str:
    payload = deepcopy(registry)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["providerRegistryHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _null_provider() -> dict[str, Any]:
    return {
        "providerId": NULL_GEOMETRY_PROVIDER_ID,
        "label": "Deterministic null geometry proposal provider",
        "providerKind": "deterministic_null_test_adapter",
        "status": "available",
        "environmentProfile": "D0_CPU",
        "isolation": {
            "required": False,
            "reason": "no heavy dependencies, no external process and no model runtime",
        },
        "policy": _provider_policy(),
        "capabilities": {
            "producesRawProposalRecord": True,
            "producesRawMeshAsset": False,
            "producesCleanProposal": False,
            "automaticGeneration": False,
            "deterministicFixture": True,
        },
        "supportedPurposes": ["garment_visual_geometry_proposal"],
        "supportedGarmentClasses": ["tshirt"],
        "licence": {
            "assetRightsStatus": "not_applicable_no_generated_asset",
            "termsReviewed": True,
        },
    }


def _manual_import_provider(manual_candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "providerId": MANUAL_IMPORT_PROVIDER_ID,
        "label": "Manual local GLB import provider",
        "providerKind": "manual_local_asset_import_adapter",
        "status": (
            "available_with_operator_asset"
            if manual_candidate["acceptedForRawProposal"]
            else "declared_unavailable_for_demo_package"
        ),
        "environmentProfile": "D0_CPU",
        "isolation": {
            "required": False,
            "reason": "local file audit only; future heavy cleanup can run in a worker",
        },
        "policy": _provider_policy(),
        "capabilities": {
            "producesRawProposalRecord": True,
            "producesRawMeshAsset": True,
            "producesCleanProposal": False,
            "automaticGeneration": False,
            "deterministicFixture": False,
        },
        "supportedPurposes": ["garment_visual_geometry_proposal"],
        "supportedGarmentClasses": ["tshirt"],
        "licence": {
            "assetRightsStatus": "operator_supplied_asset_requires_review",
            "termsReviewed": False,
        },
        "configuration": {
            "requiresOperatorSuppliedLocalAsset": True,
            "configuredForDemoPackage": manual_candidate["acceptedForRawProposal"],
        },
        "contract": manual_candidate["contract"],
    }


def _manual_import_contract() -> dict[str, Any]:
    return {
        "acceptedExtensions": [".glb"],
        "maxByteSize": 12_000_000,
        "maxTriangleEstimate": 75_000,
        "coordinateConvention": COORDINATE_CONVENTION,
        "rawAssetPolicy": "visual_reference_only_never_canonical",
        "requiredAudit": [
            "valid_glb_2_0",
            "mesh_count_positive",
            "triangle_estimate_positive",
            "material_count_recorded",
        ],
    }


def _manual_candidate_result(
    *,
    status: str,
    accepted: bool,
    failure_reason: str | None,
    contract: dict[str, Any],
    asset_name: str | None = None,
    asset_hash: str | None = None,
    byte_size: int | None = None,
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = audit or {
        "validGlb20": False,
        "meshCount": 0,
        "primitiveCount": 0,
        "triangleEstimate": 0,
        "materialCount": 0,
        "nodeCount": 0,
    }
    return {
        "providerId": MANUAL_IMPORT_PROVIDER_ID,
        "checkedAt": FIXED_TIMESTAMP,
        "status": status,
        "acceptedForRawProposal": accepted,
        "acceptedForCanonical": False,
        "failureReason": failure_reason,
        "asset": {
            "available": accepted,
            "assetName": asset_name,
            "assetHash": asset_hash,
            "byteSize": byte_size,
            "pathRecorded": False,
            "pathRecordReason": "local_operator_paths_are_not_canonical_package_identity",
        },
        "audit": audit,
        "contract": contract,
    }


def _provider_policy() -> dict[str, Any]:
    return {
        "runtimeExternalApis": False,
        "allowTrainingUse": False,
        "acceptsUserImagery": False,
        "containsPersonalBodyData": False,
        "approvedDomain": "avatar_and_garment_only",
        "allowsGenericObjects": False,
    }
