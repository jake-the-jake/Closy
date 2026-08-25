from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.contracts.common import COORDINATE_CONVENTION, FIXED_TIMESTAMP
from closy_forge.geometry.glb_io import audit_glb
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

PROVIDER_REGISTRY_VERSION = "closy.geometry_provider_registry.phase5_contract_v2"
PROVIDER_CONTRACT_VERSION = "closy.provider_contract.garment_avatar_only.v1"
MANUAL_IMPORT_PROVIDER_ID = "closy.manual_local_glb_import.v1"
NULL_GEOMETRY_PROVIDER_ID = "closy.null_geometry_proposal_provider.v1"
LOCAL_OPEN_MODEL_PROVIDER_ID = "closy.local_open_model_geometry_adapter.v1"


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
    manual_asset_rights_reviewed: bool = False,
    manual_asset_rights_status: str = "operator_supplied_asset_requires_review",
) -> dict[str, Any]:
    """Record allowed geometry providers without pretending a missing provider ran."""

    manual_candidate = inspect_manual_import_candidate(manual_asset_path)
    manual_asset_available = bool(manual_candidate["acceptedForRawProposal"])
    manual_asset_selectable = manual_asset_available and manual_asset_rights_reviewed
    selected_provider_id = (
        MANUAL_IMPORT_PROVIDER_ID if manual_asset_selectable else NULL_GEOMETRY_PROVIDER_ID
    )
    registry: dict[str, Any] = {
        "schemaVersion": 1,
        "registryId": "provider_registry.geometry_tshirt_reference_v1",
        "stageVersion": PROVIDER_REGISTRY_VERSION,
        "contractVersion": PROVIDER_CONTRACT_VERSION,
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
        "selectedProviderId": selected_provider_id,
        "selectionReason": (
            "manual_local_glb_passed_d0_audit_and_rights_review"
            if manual_asset_selectable
            else "demo_package_has_no_reviewed_manual_glb_asset"
        ),
        "providers": [
            _null_provider(),
            _manual_import_provider(
                manual_candidate,
                manual_asset_rights_reviewed=manual_asset_rights_reviewed,
                manual_asset_rights_status=manual_asset_rights_status,
            ),
            _local_open_model_provider(),
        ],
        "invocationRecords": _invocation_records(
            selected_provider_id=selected_provider_id,
            manual_candidate=manual_candidate,
            geometry_proposal=geometry_proposal,
        ),
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
            "manualLocalImportAssetAvailable": manual_asset_available,
            "localOpenModelAdapterDeclared": True,
            "localOpenModelExecutionAvailable": False,
            "providerContractValidationAvailable": True,
            "providerBakeoffReportAvailable": True,
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
            "networkDefault": "deny_all",
            "rawProviderOutputAuthority": "proposal_only_never_canonical",
        },
        "security": {
            "archiveExpansionPolicy": "reject_path_traversal_and_bounded_byte_expansion",
            "subprocessPolicy": "bounded_time_memory_and_process_count",
            "socketPolicy": "deny_by_default_for_ci_and_d0",
            "diagnosticPolicy": "safe_error_codes_no_paths_urls_pixels_tokens_or_secrets",
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
    invocation_statuses = [
        str(record.get("status", "")) for record in registry.get("invocationRecords", [])
    ]
    return {
        "schemaVersion": 1,
        "status": "pass",
        "registryId": registry["registryId"],
        "contractVersion": registry["contractVersion"],
        "selectedProviderId": registry["selectedProviderId"],
        "selectionReason": registry["selectionReason"],
        "providerCount": len(registry["providers"]),
        "futureProviderSlotCount": len(registry["futureProviderSlots"]),
        "manualLocalImportAdapterDeclared": capabilities["manualLocalImportAdapterDeclared"],
        "manualLocalImportAssetAvailable": capabilities["manualLocalImportAssetAvailable"],
        "localOpenModelAdapterDeclared": capabilities["localOpenModelAdapterDeclared"],
        "localOpenModelExecutionAvailable": capabilities["localOpenModelExecutionAvailable"],
        "providerContractValidationAvailable": capabilities["providerContractValidationAvailable"],
        "providerBakeoffReportAvailable": capabilities["providerBakeoffReportAvailable"],
        "externalProvidersConfigured": capabilities["externalProvidersConfigured"],
        "cleanProposalProviderAvailable": capabilities["cleanProposalProviderAvailable"],
        "manualImportStatus": manual["status"],
        "manualImportFailureReason": manual["failureReason"],
        "invocationRecordCount": len(invocation_statuses),
        "invocationStatuses": invocation_statuses,
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
        "providerVersion": "1.0.0",
        "contractVersion": PROVIDER_CONTRACT_VERSION,
        "label": "Deterministic null geometry proposal provider",
        "providerKind": "deterministic_null_test_adapter",
        "status": "available",
        "executionClass": "local_in_process_contract_test",
        "environmentProfile": "D0_CPU_NO_MODEL",
        "isolation": {
            "required": False,
            "reason": "no heavy dependencies, no external process and no model runtime",
        },
        "policy": _provider_policy(),
        "networkPolicy": _network_policy(),
        "capabilities": {
            "producesRawProposalRecord": True,
            "producesRawMeshAsset": False,
            "producesCleanProposal": False,
            "automaticGeneration": False,
            "deterministicFixture": True,
            "supportsCancellation": True,
            "supportsResume": False,
            "supportsTimeout": True,
        },
        "capabilityDeclaration": _capability_declaration(
            output_representations=["none"], deterministic_seed_control=True
        ),
        "ioSchemas": _io_schemas(),
        "limits": _provider_limits(max_output_bytes=0, max_triangles=0),
        "lifecycle": _lifecycle(cancel=True, resume=False),
        "authority": _provider_authority(),
        "supportedPurposes": ["garment_visual_geometry_proposal"],
        "supportedGarmentClasses": ["tshirt"],
        "licence": {
            "assetRightsStatus": "not_applicable_no_generated_asset",
            "termsReviewed": True,
        },
    }


def _manual_import_provider(
    manual_candidate: dict[str, Any],
    *,
    manual_asset_rights_reviewed: bool,
    manual_asset_rights_status: str,
) -> dict[str, Any]:
    return {
        "providerId": MANUAL_IMPORT_PROVIDER_ID,
        "providerVersion": "1.0.0",
        "contractVersion": PROVIDER_CONTRACT_VERSION,
        "label": "Manual local GLB import provider",
        "providerKind": "manual_local_asset_import_adapter",
        "status": (
            "available_with_operator_asset"
            if manual_candidate["acceptedForRawProposal"]
            else "declared_unavailable_for_demo_package"
        ),
        "executionClass": "local_in_process_manual_asset_audit",
        "environmentProfile": "D0_CPU_NO_MODEL",
        "isolation": {
            "required": False,
            "reason": "local file audit only; future heavy cleanup can run in a worker",
        },
        "policy": _provider_policy(),
        "networkPolicy": _network_policy(),
        "capabilities": {
            "producesRawProposalRecord": True,
            "producesRawMeshAsset": True,
            "producesCleanProposal": False,
            "automaticGeneration": False,
            "deterministicFixture": False,
            "supportsCancellation": True,
            "supportsResume": False,
            "supportsTimeout": True,
        },
        "capabilityDeclaration": _capability_declaration(
            output_representations=["glb2_triangle_mesh"],
            deterministic_seed_control=False,
        ),
        "ioSchemas": _io_schemas(),
        "limits": _provider_limits(max_output_bytes=12_000_000, max_triangles=75_000),
        "lifecycle": _lifecycle(cancel=True, resume=False),
        "authority": _provider_authority(),
        "supportedPurposes": ["garment_visual_geometry_proposal"],
        "supportedGarmentClasses": ["tshirt"],
        "licence": {
            "assetRightsStatus": manual_asset_rights_status,
            "termsReviewed": manual_asset_rights_reviewed,
        },
        "configuration": {
            "requiresOperatorSuppliedLocalAsset": True,
            "configuredForDemoPackage": manual_candidate["acceptedForRawProposal"],
            "assetRightsReviewed": manual_asset_rights_reviewed,
        },
        "contract": manual_candidate["contract"],
    }


def _local_open_model_provider() -> dict[str, Any]:
    return {
        "providerId": LOCAL_OPEN_MODEL_PROVIDER_ID,
        "providerVersion": "0.1.0-boundary",
        "contractVersion": PROVIDER_CONTRACT_VERSION,
        "label": "Local open-model garment/avatar proposal adapter boundary",
        "providerKind": "local_open_model_adapter_boundary",
        "status": "not_run_missing_runtime_or_weights",
        "executionClass": "optional_isolated_local_model_subprocess",
        "environmentProfile": "D0_OPTIONAL_GPU_OR_MODEL_RUNTIME_NOT_IN_CI",
        "isolation": {
            "required": True,
            "reason": (
                "future model dependencies, weights and GPU probes must stay outside "
                "ordinary Forge CI"
            ),
        },
        "policy": _provider_policy(),
        "networkPolicy": _network_policy(),
        "capabilities": {
            "producesRawProposalRecord": True,
            "producesRawMeshAsset": True,
            "producesCleanProposal": False,
            "automaticGeneration": True,
            "deterministicFixture": False,
            "supportsCancellation": True,
            "supportsResume": True,
            "supportsTimeout": True,
        },
        "capabilityDeclaration": _capability_declaration(
            output_representations=["glb2_triangle_mesh", "gltf2_triangle_mesh"],
            deterministic_seed_control=True,
        ),
        "ioSchemas": _io_schemas(),
        "limits": _provider_limits(max_output_bytes=50_000_000, max_triangles=120_000),
        "lifecycle": _lifecycle(cancel=True, resume=True),
        "authority": _provider_authority(),
        "supportedPurposes": ["garment_visual_geometry_proposal"],
        "supportedGarmentClasses": ["tshirt"],
        "licence": {
            "assetRightsStatus": "not_run_model_license_and_weights_unavailable",
            "termsReviewed": False,
            "commercialUseReviewed": False,
        },
        "runtimeRequirements": {
            "weightsAvailable": False,
            "weightsDigestKnown": False,
            "gpuRequiredForExecution": "unknown_until_model_selected",
            "ordinaryCiMayInstallExtras": False,
            "ordinaryCiMayDownloadWeights": False,
            "capabilityProbeSideEffectFree": True,
        },
        "notRunReason": "not_run_missing_runtime_or_weights",
    }


def _manual_import_contract() -> dict[str, Any]:
    return {
        "acceptedExtensions": [".glb"],
        "maxByteSize": 12_000_000,
        "maxTriangleEstimate": 75_000,
        "maxMaterialCount": 64,
        "maxTextureCount": 32,
        "maxArchiveExpansionBytes": 60_000_000,
        "maxSubprocessWallTimeSeconds": 30,
        "maxSubprocessMemoryBytes": 512_000_000,
        "maxSubprocessCount": 1,
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


def _network_policy() -> dict[str, Any]:
    return {
        "runtimeNetworkAccess": False,
        "socketAccess": "denied",
        "modelHubAccess": "denied_in_ci",
        "externalApiCalls": "denied_without_explicit_future_authority",
    }


def _capability_declaration(
    *, output_representations: list[str], deterministic_seed_control: bool
) -> dict[str, Any]:
    return {
        "supportedAssetClasses": ["garment"],
        "supportedDomain": "avatar_garment_only",
        "supportedGarmentClasses": ["tshirt"],
        "supportedAvatarClasses": ["reference_avatar"],
        "outputRepresentations": output_representations,
        "deterministicSeedControl": deterministic_seed_control,
        "cleanupBoundary": "raw_proposal_only_cleanup_is_separate",
        "canonicalTruthAuthority": False,
    }


def _io_schemas() -> dict[str, str]:
    return {
        "requestSchema": "closy.provider_request.garment_visual_geometry.v1",
        "rawOutputSchema": "closy.provider_output.raw_visual_geometry.v1",
        "analysisSchema": "closy.provider_output.independent_analysis.v1",
        "failureSchema": "closy.provider_failure.safe_code.v1",
    }


def _provider_limits(*, max_output_bytes: int, max_triangles: int) -> dict[str, Any]:
    return {
        "maxRequestBytes": 1_000_000,
        "maxOutputBytes": max_output_bytes,
        "maxArchiveExpansionBytes": max(max_output_bytes * 2, max_output_bytes),
        "maxVertices": max_triangles * 2 if max_triangles else 0,
        "maxTriangles": max_triangles,
        "maxMaterials": 64 if max_triangles else 0,
        "maxTextures": 32 if max_triangles else 0,
        "maxTextureSizePx": 2048,
        "maxWallTimeSeconds": 30,
        "maxSubprocessMemoryBytes": 512_000_000,
        "maxProcessCount": 1,
    }


def _lifecycle(*, cancel: bool, resume: bool) -> dict[str, Any]:
    return {
        "states": [
            "declared",
            "queued",
            "running",
            "completed",
            "failed",
            "cancelled",
            "not_run",
        ],
        "supportsCancellation": cancel,
        "supportsResume": resume,
        "timeoutState": "failed_timeout_safe_code",
        "malformedOutputState": "failed_malformed_output_safe_code",
    }


def _provider_authority() -> dict[str, Any]:
    return {
        "rawProposalOnly": True,
        "canonicalTruthAuthority": False,
        "mayOverwritePattern": False,
        "mayOverwriteSimulationMesh": False,
        "requiresIndependentAnalysisBeforeCleanup": True,
        "requiresCleanAcceptanceGateBeforeCanonical": True,
    }


def _invocation_records(
    *,
    selected_provider_id: str,
    manual_candidate: dict[str, Any],
    geometry_proposal: dict[str, Any],
) -> list[dict[str, Any]]:
    manual_selected = selected_provider_id == MANUAL_IMPORT_PROVIDER_ID
    return [
        {
            "invocationId": "provider_invocation.null_tshirt_contract_v1",
            "providerId": NULL_GEOMETRY_PROVIDER_ID,
            "status": (
                "not_run_provider_not_selected"
                if selected_provider_id != NULL_GEOMETRY_PROVIDER_ID
                else "completed_rejected_no_geometry"
            ),
            "startedAt": FIXED_TIMESTAMP
            if selected_provider_id == NULL_GEOMETRY_PROVIDER_ID
            else None,
            "completedAt": FIXED_TIMESTAMP
            if selected_provider_id == NULL_GEOMETRY_PROVIDER_ID
            else None,
            "deterministicSeed": 101,
            "networkAccessObserved": False,
            "safeFailureCode": None,
            "outputHash": None,
        },
        {
            "invocationId": "provider_invocation.manual_tshirt_glb_import_v1",
            "providerId": MANUAL_IMPORT_PROVIDER_ID,
            "status": (
                "completed_manual_fixture_import"
                if manual_selected
                else manual_candidate["failureReason"]
            ),
            "startedAt": FIXED_TIMESTAMP if manual_selected else None,
            "completedAt": FIXED_TIMESTAMP if manual_selected else None,
            "deterministicSeed": 101,
            "networkAccessObserved": False,
            "safeFailureCode": None if manual_selected else manual_candidate["failureReason"],
            "outputHash": (
                geometry_proposal["integrity"]["geometryProposalHash"] if manual_selected else None
            ),
        },
        {
            "invocationId": "provider_invocation.local_open_model_tshirt_boundary_v1",
            "providerId": LOCAL_OPEN_MODEL_PROVIDER_ID,
            "status": "not_run_missing_runtime_or_weights",
            "startedAt": None,
            "completedAt": None,
            "deterministicSeed": 101,
            "networkAccessObserved": False,
            "safeFailureCode": "not_run_missing_runtime_or_weights",
            "outputHash": None,
        },
    ]
