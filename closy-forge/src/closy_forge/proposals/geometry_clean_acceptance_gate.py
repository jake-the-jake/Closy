from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

GEOMETRY_CLEAN_ACCEPTANCE_GATE_VERSION = "closy.geometry_clean_acceptance_gate.runtime_preview_v1"

CLEAN_ACCEPTANCE_GATE_REJECTION_REASONS = [
    "clean_acceptance_gate_rejected",
    "source_image_visual_comparison_not_run",
    "provider_appearance_comparison_not_run",
    "mesh_stitch_or_weld_not_executed",
    "normal_continuity_warn",
    "tangent_continuity_warn",
    "provider_output_not_canonical_garment_truth",
]

_MAX_RUNTIME_RECONSTRUCTION_ERROR_METERS = 1e-6
_MAX_RUNTIME_SEAM_DISTANCE_METERS = 0.15


def build_geometry_clean_acceptance_gate_report(
    *,
    garment_id: str,
    garment_class: str,
    runtime_binding_result_report: dict[str, Any],
    semantic_transfer_report: dict[str, Any],
    texture_identity_report: dict[str, Any],
    material_uv_transfer_report: dict[str, Any] | None = None,
    visual_shell_review_report: dict[str, Any] | None = None,
    provider_registry: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate whether a runtime-bound visual proposal can become clean geometry.

    This gate is intentionally stricter than runtime-preview readiness. The D0
    fixture has a valid simulation-driven preview binding, but it still lacks
    material/UV transfer, visual fidelity evidence and a single-shell stitch
    proof, so clean/canonical acceptance remains rejected.
    """

    runtime_execution = runtime_binding_result_report["execution"]
    runtime_readiness = runtime_binding_result_report["readiness"]
    runtime_aggregate = runtime_binding_result_report["aggregate"]
    runtime_retopology = runtime_binding_result_report["retopology"]
    runtime_seams = runtime_binding_result_report["seamContinuity"]
    semantic_aggregate = semantic_transfer_report["aggregate"]
    material_regions = texture_identity_report.get("observedMaterialRegions", [])
    material_execution = (
        material_uv_transfer_report.get("execution", {})
        if material_uv_transfer_report is not None
        else {}
    )
    material_readiness = (
        material_uv_transfer_report.get("readiness", {})
        if material_uv_transfer_report is not None
        else {}
    )
    material_transfer_run = bool(material_execution.get("materialTransferRun", False))
    uv_transfer_run = bool(material_execution.get("uvTransferRun", False))
    material_transfer_accepted = bool(material_readiness.get("acceptedForMaterialPreview", False))
    visual_execution = (
        visual_shell_review_report.get("execution", {})
        if visual_shell_review_report is not None
        else {}
    )
    visual_readiness = (
        visual_shell_review_report.get("readiness", {})
        if visual_shell_review_report is not None
        else {}
    )
    visual_aggregate = (
        visual_shell_review_report.get("aggregate", {})
        if visual_shell_review_report is not None
        else {}
    )
    representation_silhouette_comparison_run = bool(
        visual_execution.get(
            "representationSilhouetteComparisonRun",
            visual_execution.get("renderedPixelComparisonRun", False),
        )
    )
    representation_silhouette_accepted = bool(
        visual_readiness.get("representationSilhouetteAccepted", False)
    )
    source_image_visual_comparison_run = bool(
        visual_execution.get("sourceImageVisualComparisonRun", False)
    )
    source_image_visual_fidelity_accepted = bool(
        visual_readiness.get("sourceImageVisualFidelityAccepted", False)
    )
    provider_appearance_comparison_run = bool(
        visual_execution.get("providerAppearanceComparisonRun", False)
    )
    provider_appearance_accepted = bool(visual_readiness.get("providerAppearanceAccepted", False))
    visual_fidelity_review_run = bool(
        source_image_visual_comparison_run or provider_appearance_comparison_run
    )
    independent_visual_fidelity_accepted = (
        source_image_visual_fidelity_accepted or provider_appearance_accepted
    )
    stitch_graph_connectivity_check_run = bool(
        visual_execution.get("stitchGraphConnectivityCheckRun", False)
    )
    stitch_graph_connectable = bool(visual_readiness.get("stitchGraphConnectable", False))
    mesh_stitch_or_weld_execution_run = bool(
        visual_execution.get("meshStitchOrWeldExecutionRun", False)
    )
    mesh_stitch_or_weld_proven = bool(visual_readiness.get("meshStitchOrWeldProven", False))

    checks = _checks(
        runtime_execution=runtime_execution,
        runtime_readiness=runtime_readiness,
        runtime_aggregate=runtime_aggregate,
        runtime_retopology=runtime_retopology,
        runtime_seams=runtime_seams,
        semantic_aggregate=semantic_aggregate,
        texture_identity=texture_identity_report,
        material_uv_transfer=material_uv_transfer_report,
        visual_shell_review=visual_shell_review_report,
        provider_registry=provider_registry,
    )
    accepted_for_clean = all(check["status"] == "pass" for check in checks)
    blocking_reasons = _blocking_reasons(checks)

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "clean_acceptance_gate.runtime_bound_tshirt_visual_geometry_v1",
        "stageVersion": GEOMETRY_CLEAN_ACCEPTANCE_GATE_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceGeometryRuntimeBindingResultId": runtime_binding_result_report["reportId"],
        "sourceGeometryRuntimeBindingResultHash": runtime_binding_result_report["integrity"][
            "geometryRuntimeBindingResultHash"
        ],
        "sourceGeometrySemanticTransferId": semantic_transfer_report["reportId"],
        "sourceGeometrySemanticTransferHash": semantic_transfer_report["integrity"][
            "geometrySemanticTransferHash"
        ],
        "sourceTextureIdentityId": texture_identity_report["textureIdentityId"],
        "sourceTextureIdentityHash": texture_identity_report["integrity"]["textureIdentityHash"],
        "sourceGeometryMaterialUvTransferId": material_uv_transfer_report["reportId"]
        if material_uv_transfer_report is not None
        else None,
        "sourceGeometryMaterialUvTransferHash": material_uv_transfer_report["integrity"][
            "geometryMaterialUvTransferHash"
        ]
        if material_uv_transfer_report is not None
        else None,
        "sourceGeometryVisualShellReviewId": visual_shell_review_report["reportId"]
        if visual_shell_review_report is not None
        else None,
        "sourceGeometryVisualShellReviewHash": visual_shell_review_report["integrity"][
            "geometryVisualShellReviewHash"
        ]
        if visual_shell_review_report is not None
        else None,
        "sourceProviderRegistryId": provider_registry["registryId"],
        "sourceProviderRegistryHash": provider_registry["integrity"]["providerRegistryHash"],
        "candidate": {
            "runtimeRenderAssetPath": runtime_binding_result_report["outputRenderAsset"]["path"],
            "runtimeRenderAssetHash": runtime_binding_result_report["outputRenderAsset"][
                "sourceAssetHash"
            ],
            "runtimeBindingPath": runtime_binding_result_report["outputBinding"]["path"],
            "runtimeBindingHash": runtime_binding_result_report["outputBinding"]["sourceAssetHash"],
            "runtimePreviewUseAllowed": runtime_binding_result_report["outputRenderAsset"][
                "runtimePreviewUseAllowed"
            ],
            "canonicalUseAllowed": False,
            "providerTopologyRetainedForRuntime": runtime_retopology[
                "providerTopologyRetainedForRuntime"
            ],
            "singleShellWelded": runtime_retopology["vertexWeldedSingleShell"],
        },
        "measurements": {
            "runtimeBindingRecordCount": runtime_aggregate["runtimeBindingRecordCount"],
            "runtimeRenderVertexCount": runtime_aggregate["runtimeRenderVertexCount"],
            "runtimeRenderTriangleCount": runtime_aggregate["runtimeRenderTriangleCount"],
            "maxReconstructionErrorMeters": runtime_aggregate["maxReconstructionError"],
            "rmsReconstructionErrorMeters": runtime_aggregate["rmsReconstructionError"],
            "maxSeamPairDistanceMeters": runtime_aggregate["maxSeamPairDistanceMeters"],
            "rmsSeamPairDistanceMeters": runtime_aggregate["rmsSeamPairDistanceMeters"],
            "maxNormalAngleDegrees": runtime_aggregate["maxNormalAngleDegrees"],
            "maxTangentAngleDegrees": runtime_aggregate["maxTangentAngleDegrees"],
            "semanticPanelCoverage": _ratio(
                semantic_aggregate["transferredPanelCount"],
                semantic_aggregate["expectedPanelCount"],
            ),
            "boundaryClassificationCompleteness": semantic_aggregate["classificationCompleteness"],
            "materialRegionCount": len(material_regions),
            "sourceTextureAvailable": texture_identity_report["sourceTextureAvailable"],
            "textureProjectionRun": texture_identity_report["textureProjectionRun"],
            "uvTransferRun": uv_transfer_run,
            "materialTransferRun": material_transfer_run,
            "materialTransferAccepted": material_transfer_accepted,
            "transferredMaterialCount": material_uv_transfer_report["aggregate"][
                "transferredMaterialCount"
            ]
            if material_uv_transfer_report is not None
            else 0,
            "visualFidelityReviewRun": visual_fidelity_review_run,
            "visualFidelityScore": visual_aggregate.get("visualFidelityScore"),
            "visualFidelityAccepted": independent_visual_fidelity_accepted,
            "renderedPixelComparisonRun": bool(
                visual_aggregate.get("renderedPixelComparisonRun", False)
            ),
            "representationSilhouetteComparisonRun": representation_silhouette_comparison_run,
            "representationSilhouetteAccepted": representation_silhouette_accepted,
            "sourceImageVisualComparisonRun": source_image_visual_comparison_run,
            "sourceImageVisualFidelityAccepted": source_image_visual_fidelity_accepted,
            "providerAppearanceComparisonRun": provider_appearance_comparison_run,
            "providerAppearanceAccepted": provider_appearance_accepted,
            "stitchGraphConnectivityCheckRun": stitch_graph_connectivity_check_run,
            "stitchGraphConnectable": stitch_graph_connectable,
            "singleShellWeldProofRun": False,
            "singleShellWeldProven": False,
            "meshStitchOrWeldExecutionRun": mesh_stitch_or_weld_execution_run,
            "meshStitchOrWeldProven": mesh_stitch_or_weld_proven,
        },
        "thresholds": {
            "maxReconstructionErrorMeters": _MAX_RUNTIME_RECONSTRUCTION_ERROR_METERS,
            "maxSeamPairDistanceMeters": _MAX_RUNTIME_SEAM_DISTANCE_METERS,
            "semanticPanelCoverage": 1.0,
            "boundaryClassificationCompleteness": 1.0,
            "representationSilhouetteAccepted": True,
            "visualFidelityScore": 0.8,
            "materialTransferRequired": True,
            "independentVisualFidelityRequired": True,
            "meshStitchOrWeldRequired": True,
        },
        "checks": checks,
        "aggregate": {
            "checkCount": len(checks),
            "passedCheckCount": sum(check["status"] == "pass" for check in checks),
            "failedCheckCount": sum(check["status"] == "fail" for check in checks),
            "warningCheckCount": sum(check["status"] == "warn" for check in checks),
            "notRunCheckCount": sum(check["status"] == "not_run" for check in checks),
            "acceptedForCleanProposal": accepted_for_clean,
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": runtime_readiness["acceptedForRuntimeRender"],
            "blockingReasonCount": len(blocking_reasons),
        },
        "execution": {
            "cleanAcceptanceGateRun": True,
            "runtimeBindingEvidenceReviewed": True,
            "semanticTransferEvidenceReviewed": True,
            "materialEvidenceReviewed": True,
            "policyReviewed": True,
            "uvTransferRun": uv_transfer_run,
            "materialTransferRun": material_transfer_run,
            "materialTransferAccepted": material_transfer_accepted,
            "visualFidelityReviewRun": visual_fidelity_review_run,
            "representationSilhouetteComparisonRun": representation_silhouette_comparison_run,
            "representationSilhouetteAccepted": representation_silhouette_accepted,
            "sourceImageVisualComparisonRun": source_image_visual_comparison_run,
            "sourceImageVisualFidelityAccepted": source_image_visual_fidelity_accepted,
            "providerAppearanceComparisonRun": provider_appearance_comparison_run,
            "providerAppearanceAccepted": provider_appearance_accepted,
            "stitchGraphConnectivityCheckRun": stitch_graph_connectivity_check_run,
            "stitchGraphConnectable": stitch_graph_connectable,
            "singleShellWeldProofRun": False,
            "singleShellWeldProven": False,
            "visualFidelityAccepted": independent_visual_fidelity_accepted,
            "meshStitchOrWeldExecutionRun": mesh_stitch_or_weld_execution_run,
            "meshStitchOrWeldProven": mesh_stitch_or_weld_proven,
        },
        "readiness": {
            "status": _readiness_status(
                accepted_for_clean=accepted_for_clean,
                material_transfer_accepted=material_transfer_accepted,
                representation_silhouette_accepted=representation_silhouette_accepted,
                source_image_visual_comparison_run=source_image_visual_comparison_run,
                provider_appearance_comparison_run=provider_appearance_comparison_run,
                independent_visual_fidelity_accepted=independent_visual_fidelity_accepted,
                mesh_stitch_or_weld_proven=mesh_stitch_or_weld_proven,
            ),
            "acceptedForCleanProposal": accepted_for_clean,
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": runtime_readiness["acceptedForRuntimeRender"],
            "nextExecutableStage": _next_executable_stage(
                material_transfer_accepted=material_transfer_accepted,
                representation_silhouette_accepted=representation_silhouette_accepted,
                source_image_visual_comparison_run=source_image_visual_comparison_run,
                provider_appearance_comparison_run=provider_appearance_comparison_run,
                independent_visual_fidelity_accepted=independent_visual_fidelity_accepted,
                mesh_stitch_or_weld_proven=mesh_stitch_or_weld_proven,
            ),
            "blockingReasons": blocking_reasons,
        },
        "quality": {
            "status": "rejected" if not accepted_for_clean else "pass",
            "acceptedForCleanProposal": accepted_for_clean,
            "rejectionReasons": blocking_reasons,
            "warnings": [
                reason
                for reason in [
                    "runtime_preview_binding_is_not_clean_geometry",
                    "normal_continuity_warn"
                    if runtime_seams["normalContinuityStatus"] == "warn"
                    else None,
                    "tangent_continuity_warn"
                    if runtime_seams["tangentContinuityStatus"] == "warn"
                    else None,
                    "source_texture_projection_not_run"
                    if texture_identity_report["textureProjectionRun"] is False
                    else None,
                    "material_transfer_not_run" if not material_transfer_run else None,
                    "representation_silhouette_not_accepted"
                    if not representation_silhouette_accepted
                    else None,
                    "source_image_visual_comparison_not_run"
                    if not source_image_visual_comparison_run
                    else None,
                    "source_image_visual_fidelity_not_accepted"
                    if not source_image_visual_fidelity_accepted
                    else None,
                    "provider_appearance_comparison_not_run"
                    if not provider_appearance_comparison_run
                    else None,
                    "provider_appearance_not_accepted"
                    if not provider_appearance_accepted
                    else None,
                    "mesh_stitch_or_weld_not_proven" if not mesh_stitch_or_weld_proven else None,
                ]
                if reason is not None
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
            "providerOutputMayBecomeCanonicalWithoutGate": False,
        },
        "integrity": {"geometryCleanAcceptanceGateHash": ""},
    }
    report["integrity"]["geometryCleanAcceptanceGateHash"] = hash_geometry_clean_acceptance_gate(
        report
    )
    return report


def hash_geometry_clean_acceptance_gate(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["geometryCleanAcceptanceGateHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _checks(
    *,
    runtime_execution: dict[str, Any],
    runtime_readiness: dict[str, Any],
    runtime_aggregate: dict[str, Any],
    runtime_retopology: dict[str, Any],
    runtime_seams: dict[str, Any],
    semantic_aggregate: dict[str, Any],
    texture_identity: dict[str, Any],
    material_uv_transfer: dict[str, Any] | None,
    visual_shell_review: dict[str, Any] | None,
    provider_registry: dict[str, Any],
) -> list[dict[str, Any]]:
    if material_uv_transfer is None:
        material_check_status = "not_run"
        material_measured: dict[str, Any] = {
            "sourceTextureAvailable": texture_identity["sourceTextureAvailable"],
            "textureProjectionRun": texture_identity["textureProjectionRun"],
            "observedMaterialRegions": len(texture_identity.get("observedMaterialRegions", [])),
        }
    else:
        material_check_status = (
            "pass"
            if material_uv_transfer["readiness"]["acceptedForMaterialPreview"] is True
            and material_uv_transfer["execution"]["uvTransferRun"] is True
            and material_uv_transfer["execution"]["materialTransferRun"] is True
            else "fail"
        )
        material_measured = {
            "uvTransferRun": material_uv_transfer["execution"]["uvTransferRun"],
            "materialTransferRun": material_uv_transfer["execution"]["materialTransferRun"],
            "acceptedForMaterialPreview": material_uv_transfer["readiness"][
                "acceptedForMaterialPreview"
            ],
            "transferredMaterialCount": material_uv_transfer["aggregate"][
                "transferredMaterialCount"
            ],
            "missingMaterialCount": material_uv_transfer["aggregate"]["missingMaterialCount"],
            "missingUvCount": material_uv_transfer["aggregate"]["missingUvCount"],
        }
    if visual_shell_review is None:
        representation_check_status = "not_run"
        visual_check_status = "not_run"
        visual_measured: Any = None
        visual_reason = "no visual/shell review report exists yet"
        shell_check_status = "not_run"
        shell_measured: Any = {
            "vertexWeldedSingleShell": runtime_retopology["vertexWeldedSingleShell"]
        }
    else:
        representation_check_status = (
            "pass"
            if visual_shell_review["readiness"].get("representationSilhouetteAccepted") is True
            else "fail"
        )
        visual_check_status = (
            "pass"
            if (
                visual_shell_review["readiness"].get("sourceImageVisualFidelityAccepted") is True
                or visual_shell_review["readiness"].get("providerAppearanceAccepted") is True
            )
            else "not_run"
            if (
                visual_shell_review["execution"].get("sourceImageVisualComparisonRun") is not True
                and visual_shell_review["execution"].get("providerAppearanceComparisonRun")
                is not True
            )
            else "fail"
        )
        visual_measured = {
            "visualFidelityReviewRun": visual_shell_review["execution"]["visualFidelityReviewRun"],
            "renderedPixelComparisonRun": visual_shell_review["execution"][
                "renderedPixelComparisonRun"
            ],
            "representationSilhouetteComparisonRun": visual_shell_review["execution"][
                "representationSilhouetteComparisonRun"
            ],
            "representationSilhouetteAccepted": visual_shell_review["readiness"][
                "representationSilhouetteAccepted"
            ],
            "sourceImageVisualComparisonRun": visual_shell_review["execution"][
                "sourceImageVisualComparisonRun"
            ],
            "sourceImageVisualFidelityAccepted": visual_shell_review["readiness"][
                "sourceImageVisualFidelityAccepted"
            ],
            "providerAppearanceComparisonRun": visual_shell_review["execution"][
                "providerAppearanceComparisonRun"
            ],
            "providerAppearanceAccepted": visual_shell_review["readiness"][
                "providerAppearanceAccepted"
            ],
            "visualFidelityScore": visual_shell_review["aggregate"]["visualFidelityScore"],
            "acceptedForVisualFidelity": visual_shell_review["readiness"][
                "acceptedForVisualFidelity"
            ],
        }
        visual_reason = (
            "independent source/provider appearance comparison has not run"
            if visual_check_status == "not_run"
            else "independent visual fidelity has not been accepted"
            if visual_check_status == "fail"
            else "independent visual fidelity accepted"
        )
        shell_check_status = (
            "pass"
            if visual_shell_review["readiness"].get("meshStitchOrWeldProven") is True
            else "not_run"
            if visual_shell_review["execution"].get("meshStitchOrWeldExecutionRun") is not True
            else "fail"
        )
        shell_measured = {
            "singleShellWeldProofRun": visual_shell_review["execution"]["singleShellWeldProofRun"],
            "singleShellWeldProven": visual_shell_review["readiness"]["singleShellWeldProven"],
            "stitchGraphConnectivityCheckRun": visual_shell_review["execution"][
                "stitchGraphConnectivityCheckRun"
            ],
            "stitchGraphConnectable": visual_shell_review["readiness"]["stitchGraphConnectable"],
            "meshStitchOrWeldExecutionRun": visual_shell_review["execution"][
                "meshStitchOrWeldExecutionRun"
            ],
            "meshStitchOrWeldProven": visual_shell_review["readiness"]["meshStitchOrWeldProven"],
            "semanticPanelShellCount": visual_shell_review["shellProof"]["semanticPanelShellCount"],
            "vertexWeldedSingleShell": visual_shell_review["shellProof"]["vertexWeldedSingleShell"],
        }
    return [
        {
            "checkId": "runtime_binding_preview_ready",
            "status": "pass"
            if runtime_execution["runtimeBindingAccepted"] is True
            and runtime_readiness["acceptedForRuntimeRender"] is True
            else "fail",
            "measured": runtime_execution["runtimeBindingAccepted"],
            "threshold": True,
        },
        {
            "checkId": "runtime_reconstruction_error",
            "status": "pass"
            if runtime_aggregate["maxReconstructionError"]
            <= _MAX_RUNTIME_RECONSTRUCTION_ERROR_METERS
            else "fail",
            "measured": runtime_aggregate["maxReconstructionError"],
            "threshold": _MAX_RUNTIME_RECONSTRUCTION_ERROR_METERS,
        },
        {
            "checkId": "seam_distance_continuity",
            "status": "pass"
            if runtime_aggregate["maxSeamPairDistanceMeters"] <= _MAX_RUNTIME_SEAM_DISTANCE_METERS
            else "fail",
            "measured": runtime_aggregate["maxSeamPairDistanceMeters"],
            "threshold": _MAX_RUNTIME_SEAM_DISTANCE_METERS,
        },
        {
            "checkId": "normal_continuity",
            "status": runtime_seams["normalContinuityStatus"],
            "measured": runtime_aggregate["maxNormalAngleDegrees"],
            "threshold": runtime_seams["thresholds"]["warnNormalAngleDegrees"],
        },
        {
            "checkId": "tangent_continuity",
            "status": runtime_seams["tangentContinuityStatus"],
            "measured": runtime_aggregate["maxTangentAngleDegrees"],
            "threshold": runtime_seams["thresholds"]["warnTangentAngleDegrees"],
        },
        {
            "checkId": "semantic_panel_coverage",
            "status": "pass"
            if semantic_aggregate["transferredPanelCount"]
            == semantic_aggregate["expectedPanelCount"]
            else "fail",
            "measured": {
                "transferred": semantic_aggregate["transferredPanelCount"],
                "expected": semantic_aggregate["expectedPanelCount"],
            },
            "threshold": "all_panels_transferred",
        },
        {
            "checkId": "boundary_classification",
            "status": "pass" if semantic_aggregate["classificationCompleteness"] == 1.0 else "fail",
            "measured": semantic_aggregate["classificationCompleteness"],
            "threshold": 1.0,
        },
        {
            "checkId": "material_transfer",
            "status": material_check_status,
            "measured": material_measured,
            "threshold": "source texture or explicit transferred material evidence required",
        },
        {
            "checkId": "representation_silhouette_comparison",
            "status": representation_check_status,
            "measured": {
                "run": visual_measured["representationSilhouetteComparisonRun"]
                if visual_measured is not None
                else False,
                "accepted": visual_measured["representationSilhouetteAccepted"]
                if visual_measured is not None
                else False,
            },
            "threshold": "runtime preview must preserve canonical representation silhouette",
        },
        {
            "checkId": "visual_fidelity_review",
            "status": visual_check_status,
            "measured": visual_measured,
            "threshold": "independent source image or provider appearance comparison required",
            "reason": visual_reason,
        },
        {
            "checkId": "stitch_graph_connectivity",
            "status": "pass"
            if visual_shell_review is not None
            and visual_shell_review["readiness"].get("stitchGraphConnectable") is True
            else "fail",
            "measured": {
                "run": visual_shell_review["execution"].get("stitchGraphConnectivityCheckRun")
                if visual_shell_review is not None
                else False,
                "connectable": visual_shell_review["readiness"].get("stitchGraphConnectable")
                if visual_shell_review is not None
                else False,
            },
            "threshold": "seam-constraint graph connects settled simulation panel components",
        },
        {
            "checkId": "single_shell_stitch_weld_proof",
            "status": shell_check_status,
            "measured": shell_measured,
            "threshold": "material stitched/welded output asset with topology/content audit",
        },
        {
            "checkId": "provider_policy",
            "status": "pass"
            if provider_registry["policy"]["allowExternalApis"] is False
            and provider_registry["policy"]["allowTrainingUse"] is False
            and provider_registry["policy"]["containsUserImagery"] is False
            and provider_registry["policy"]["containsPersonalBodyData"] is False
            and provider_registry["policy"]["approvedDomain"] == "avatar_and_garment_only"
            else "fail",
            "measured": provider_registry["policy"],
            "threshold": "no_external_api_training_or_user_data",
        },
    ]


def _blocking_reasons(checks: list[dict[str, Any]]) -> list[str]:
    reasons = {"provider_output_not_canonical_garment_truth"}
    for check in checks:
        status = check["status"]
        if status in {"fail", "warn", "not_run"}:
            reasons.update(_reason_aliases(str(check["checkId"]), str(status)))
    if any(check["status"] != "pass" for check in checks):
        reasons.add("clean_acceptance_gate_rejected")
    return sorted(reasons)


def _reason_aliases(check_id: str, status: str) -> set[str]:
    if check_id == "material_transfer" and status == "not_run":
        return {"material_transfer_not_run"}
    if check_id == "material_transfer" and status == "fail":
        return {"material_transfer_failed"}
    if check_id == "visual_fidelity_review" and status == "not_run":
        return {
            "source_image_visual_comparison_not_run",
            "provider_appearance_comparison_not_run",
            "visual_fidelity_review_not_accepted",
        }
    if check_id == "visual_fidelity_review" and status == "fail":
        return {"visual_fidelity_review_not_accepted"}
    if check_id == "single_shell_stitch_weld_proof" and status == "not_run":
        return {"mesh_stitch_or_weld_not_executed", "mesh_stitch_or_weld_not_proven"}
    if check_id == "single_shell_stitch_weld_proof" and status == "fail":
        return {"mesh_stitch_or_weld_not_proven"}
    if check_id == "normal_continuity" and status == "warn":
        return {"normal_continuity_warn"}
    if check_id == "tangent_continuity" and status == "warn":
        return {"tangent_continuity_warn"}
    return {f"{check_id}_{status}"}


def _readiness_status(
    *,
    accepted_for_clean: bool,
    material_transfer_accepted: bool,
    representation_silhouette_accepted: bool,
    source_image_visual_comparison_run: bool,
    provider_appearance_comparison_run: bool,
    independent_visual_fidelity_accepted: bool,
    mesh_stitch_or_weld_proven: bool,
) -> str:
    if accepted_for_clean:
        return "clean_acceptance_passed"
    if not material_transfer_accepted:
        return "clean_acceptance_rejected_fidelity_material_pending"
    if not representation_silhouette_accepted:
        return "clean_acceptance_rejected_representation_failed"
    if not source_image_visual_comparison_run and not provider_appearance_comparison_run:
        return "clean_acceptance_rejected_independent_visual_not_run"
    if not independent_visual_fidelity_accepted:
        return "clean_acceptance_rejected_visual_shell_failed"
    if not mesh_stitch_or_weld_proven:
        return "clean_acceptance_rejected_mesh_stitch_weld_pending"
    return "clean_acceptance_rejected_continuity_warn"


def _next_executable_stage(
    *,
    material_transfer_accepted: bool,
    representation_silhouette_accepted: bool,
    source_image_visual_comparison_run: bool,
    provider_appearance_comparison_run: bool,
    independent_visual_fidelity_accepted: bool,
    mesh_stitch_or_weld_proven: bool,
) -> str:
    if not material_transfer_accepted:
        return "material_uv_transfer_and_visual_fidelity_review"
    if not representation_silhouette_accepted:
        return "representation_silhouette_regression_repair"
    if not source_image_visual_comparison_run and not provider_appearance_comparison_run:
        return "source_or_provider_visual_fidelity_comparison"
    if not independent_visual_fidelity_accepted:
        return "source_or_provider_visual_fidelity_acceptance"
    if not mesh_stitch_or_weld_proven:
        return "mesh_stitch_or_weld_execution"
    return "canonical_acceptance_quality_gate"


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 9)
