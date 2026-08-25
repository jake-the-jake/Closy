from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

PROVIDER_BAKEOFF_REPORT_VERSION = "closy.provider_bakeoff.phase5_contract_v1"


def build_provider_bakeoff_report(
    *,
    garment_id: str,
    garment_class: str,
    provider_registry: dict[str, Any],
    raw_geometry_proposal: dict[str, Any],
    raw_topology_report: dict[str, Any],
) -> dict[str, Any]:
    """Compare provider routes without granting any provider canonical authority."""

    selected_provider_id = str(provider_registry["selectedProviderId"])
    provider_results = [
        _provider_result(
            provider=provider,
            selected_provider_id=selected_provider_id,
            raw_geometry_proposal=raw_geometry_proposal,
            raw_topology_report=raw_topology_report,
        )
        for provider in provider_registry["providers"]
    ]
    executed_count = sum(
        1 for result in provider_results if result["executionStatus"].startswith("completed")
    )
    not_run_count = sum(
        1 for result in provider_results if result["executionStatus"].startswith("not_run")
    )
    rejected_count = sum(1 for result in provider_results if result["qualityStatus"] == "rejected")
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "provider_bakeoff.geometry_tshirt_reference_v1",
        "stageVersion": PROVIDER_BAKEOFF_REPORT_VERSION,
        "status": "completed_d0_contract_only_clean_rejected",
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceProviderRegistryId": provider_registry["registryId"],
        "sourceProviderRegistryHash": provider_registry["integrity"]["providerRegistryHash"],
        "sourceRawProposalId": raw_geometry_proposal["proposalId"],
        "sourceRawProposalHash": raw_geometry_proposal["integrity"]["geometryProposalHash"],
        "sourceRawTopologyReportId": raw_topology_report["reportId"],
        "sourceRawTopologyReportHash": raw_topology_report["integrity"][
            "rawGeometryTopologyReportHash"
        ],
        "providerResults": provider_results,
        "aggregate": {
            "providerCount": len(provider_results),
            "executedProviderCount": executed_count,
            "notRunProviderCount": not_run_count,
            "rejectedProviderCount": rejected_count,
            "externalProviderCount": 0,
            "canonicalAcceptedProviderCount": sum(
                1 for result in provider_results if result["acceptedForCanonical"]
            ),
            "bestAvailableProviderId": selected_provider_id,
            "bestAvailableStatus": _result_for(provider_results, selected_provider_id)[
                "executionStatus"
            ],
        },
        "policy": {
            "approvedDomain": "avatar_and_garment_only",
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "providerOutputMayBecomeCanonicalWithoutGate": False,
        },
        "limitations": [
            "manual_fixture_is_not_model_provider_evidence",
            "local_open_model_not_run_missing_runtime_or_weights",
            "external_provider_slots_not_configured",
            "provider_outputs_are_non_canonical_until_clean_acceptance",
        ],
        "integrity": {"providerBakeoffHash": ""},
    }
    report["integrity"]["providerBakeoffHash"] = hash_provider_bakeoff_report(report)
    return report


def provider_bakeoff_quality_report(report: dict[str, Any]) -> dict[str, Any]:
    aggregate = report["aggregate"]
    return {
        "schemaVersion": 1,
        "status": "pass",
        "reportId": report["reportId"],
        "providerCount": aggregate["providerCount"],
        "executedProviderCount": aggregate["executedProviderCount"],
        "notRunProviderCount": aggregate["notRunProviderCount"],
        "canonicalAcceptedProviderCount": aggregate["canonicalAcceptedProviderCount"],
        "bestAvailableProviderId": aggregate["bestAvailableProviderId"],
        "bestAvailableStatus": aggregate["bestAvailableStatus"],
        "limitations": report["limitations"],
    }


def hash_provider_bakeoff_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["providerBakeoffHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _provider_result(
    *,
    provider: dict[str, Any],
    selected_provider_id: str,
    raw_geometry_proposal: dict[str, Any],
    raw_topology_report: dict[str, Any],
) -> dict[str, Any]:
    provider_id = str(provider.get("providerId", ""))
    selected = provider_id == selected_provider_id
    if provider_id == raw_geometry_proposal["provider"]["providerId"] and selected:
        execution_status = "completed_manual_fixture_import"
        quality_status = str(raw_geometry_proposal["quality"]["status"])
        raw_available = bool(raw_geometry_proposal["rawProposal"]["available"])
        triangle_estimate = int(raw_geometry_proposal["geometryAudit"]["triangleEstimate"])
        defect_summary = {
            "topologyDiagnosticsRun": True,
            "componentCount": raw_topology_report["topology"]["componentCount"],
            "nonManifoldEdgeCount": raw_topology_report["topology"]["nonManifoldEdgeCount"],
            "degenerateTriangleCount": raw_topology_report["topology"]["degenerateTriangleCount"],
            "cleanupRequired": not raw_topology_report["cleanReadiness"][
                "acceptedForCleanProposal"
            ],
        }
    elif str(provider.get("status", "")).startswith("not_run"):
        execution_status = str(provider["status"])
        quality_status = "not_run"
        raw_available = False
        triangle_estimate = 0
        defect_summary = {
            "topologyDiagnosticsRun": False,
            "componentCount": 0,
            "nonManifoldEdgeCount": 0,
            "degenerateTriangleCount": 0,
            "cleanupRequired": True,
        }
    else:
        execution_status = "not_run_provider_not_selected"
        quality_status = "rejected"
        raw_available = False
        triangle_estimate = 0
        defect_summary = {
            "topologyDiagnosticsRun": False,
            "componentCount": 0,
            "nonManifoldEdgeCount": 0,
            "degenerateTriangleCount": 0,
            "cleanupRequired": True,
        }

    return {
        "providerId": provider_id,
        "providerKind": provider.get("providerKind"),
        "selected": selected,
        "executionStatus": execution_status,
        "qualityStatus": quality_status,
        "rawProposalAvailable": raw_available,
        "acceptedForCanonical": False,
        "acceptedForCleanProposal": False,
        "costClass": _cost_class(provider),
        "runtimeProfile": provider.get("environmentProfile"),
        "triangleEstimate": triangle_estimate,
        "defectSummary": defect_summary,
        "silhouetteFidelityStatus": "not_run",
        "textureFidelityStatus": "not_run",
        "bindabilityStatus": "not_clean_or_not_bound",
        "licenseRestrictionStatus": _license_status(provider),
        "networkAccessObserved": False,
        "cleanupEffortStatus": _cleanup_effort_status(
            selected=selected,
            raw_available=raw_available,
            cleanup_required=bool(defect_summary["cleanupRequired"]),
        ),
        "failureReason": provider.get("notRunReason"),
    }


def _result_for(results: list[dict[str, Any]], provider_id: str) -> dict[str, Any]:
    for result in results:
        if result["providerId"] == provider_id:
            return result
    raise KeyError(provider_id)


def _cost_class(provider: dict[str, Any]) -> str:
    if provider.get("providerKind") == "local_open_model_adapter_boundary":
        return "unknown_optional_local_model_runtime"
    if provider.get("providerKind") == "manual_local_asset_import_adapter":
        return "manual_operator_asset"
    return "zero_cost_contract_test"


def _license_status(provider: dict[str, Any]) -> str:
    licence = provider.get("licence", {})
    if not isinstance(licence, dict):
        return "license_unknown"
    if licence.get("termsReviewed") is True:
        return str(licence.get("assetRightsStatus", "reviewed"))
    return "not_reviewed"


def _cleanup_effort_status(*, selected: bool, raw_available: bool, cleanup_required: bool) -> str:
    if not raw_available:
        return "not_run_no_raw_geometry"
    if cleanup_required:
        return (
            "cleanup_required_before_clean_or_canonical_use"
            if selected
            else "not_selected_cleanup_not_assessed"
        )
    return "no_cleanup_required_for_visual_reference"
