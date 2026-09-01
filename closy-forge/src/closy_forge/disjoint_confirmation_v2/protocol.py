from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, canonical_text_bytes, read_json
from closy_forge.package_io.hashing import sha256_bytes

BENCHMARK_VERSION = "closy.d0_disjoint_tshirt_confirmation.v2"
FIXTURE_ROOT = Path("fixtures/d0_disjoint_tshirt_confirmation_v2")
PROTOCOL_PATH = FIXTURE_ROOT / "protocol_lock.json"
PRIMARY_ROUTE = "deterministic_masks_landmarks"
ROUTES = (
    "metadata_only_control",
    "no_pixel_template_prior",
    PRIMARY_ROUTE,
    "image_conditioned_iterative",
)
FULL_COMPILE_ROUTES = ROUTES[1:]
APPEARANCE_ROUTES = FULL_COMPILE_ROUTES
APPEARANCE_ORDINALS = tuple(range(8))
REQUIRED_OPENINGS = (
    "opening.cuff.left",
    "opening.cuff.right",
    "opening.hem",
    "opening.neck",
)
RESULT_VALUES = ("pass", "fail", "not_run")


def locked_thresholds() -> dict[str, Any]:
    return {
        "minimumPrimaryPredictionCoverage": 14,
        "maximumMedianMacroNormalizedObservableError": 0.10,
        "maximumWorstNormalizedObservableError": 0.25,
        "minimumMeanEvaluatorViewSilhouetteIoU": 0.30,
        "maximumBoundaryProxyError": 0.20,
        "maximumLandmarkProxyError": 0.14,
        "maximumReferenceRmsVertexErrorMeters": 0.08,
        "requiredPanels": 5,
        "legacyRequiredSeamsMinimum": 1,
        "requiredOpenings": list(REQUIRED_OPENINGS),
        "maximumForegroundSrgbMae": 0.12,
        "maximumLogoDisplacementNormalized": 0.14,
        "maximumLogoFalsePositiveFraction": 0.002,
        "minimumLogoIoUWhenApplicable": 0.02,
        "requiredApplicableAppearanceIdentities": 8,
        "primaryVersusNoPixelParameterRelativeImprovementMinimum": 0.10,
        "primaryVersusNoPixelSilhouetteAbsoluteImprovementMinimum": 0.01,
        "learnedWinnerParameterRelativeImprovementMinimum": 0.20,
        "learnedWinnerSilhouetteAbsoluteImprovementMinimum": 0.02,
        "bootstrapResamples": 10_000,
        "bootstrapSeed": 4_107_301,
        "bootstrapConfidence": 0.95,
        "bootstrapLowerBoundStrictlyAboveZero": True,
        "failurePenalty": {"macroNormalizedError": 1.0, "silhouetteIoU": 0.0},
    }


def protocol_document(
    *,
    source_anchor_sha: str,
    implementation_files: list[dict[str, Any]],
    initial_authority_workflow_sha256: str,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "benchmarkVersion": BENCHMARK_VERSION,
        "sourceEvidenceAnchorSha": source_anchor_sha,
        "implementationFiles": implementation_files,
        "implementationDigest": _hash(implementation_files),
        "implementationHashMode": "utf8_canonical_lf_final_newline",
        "compilerVersion": "closy.d0_disjoint.structural_compiler.v1",
        "canonicalPackageVersion": "closy.garment_package.v1",
        "routes": list(ROUTES),
        "primaryRoute": PRIMARY_ROUTE,
        "fullCompileRoutes": list(FULL_COMPILE_ROUTES),
        "appearanceRoutes": list(APPEARANCE_ROUTES),
        "evaluatorIdentityCount": 16,
        "predictionDenominator": 64,
        "fullCompileDenominator": 48,
        "primaryCompileRepeatDenominator": 16,
        "maximumFullCompiles": 64,
        "appearanceOrdinals": list(APPEARANCE_ORDINALS),
        "appearanceDenominator": 24,
        "primaryAppearanceRepeatDenominator": 8,
        "maximumAppearanceEvaluations": 32,
        "repeatReserveReassignable": False,
        "failedItemsRetainedInDenominator": True,
        "inapplicableItemsRetainedInDenominator": True,
        "perIdentityRouteSelectionAllowed": False,
        "routePromotionRule": (
            "fixed_primary_must_pass_its_row_absolute_gates_and_equal_evidence_comparative_"
            "gates_with_positive_frozen_bootstrap_lower_bound_no_per_identity_mosaic"
        ),
        "tieRule": "simpler_lower_evidence_route",
        "oneAttemptPolicy": "one_official_cohort_after_first_accepted_draw_no_qualification_retry",
        "targetGenerationProcedure": (
            "truth_and_source_observations_generated_together_then_crop_and_occlusion_applied_"
            "only_to_derived_source_roles_private_truth_unmounted_until_prediction_freeze"
        ),
        "externalSeedAuthorityLifecycle": (
            "one_shot_pull_request_authority_random_256_bit_seed_then_commitments_predictions_"
            "freeze_reveal"
        ),
        "seedAuthorityLifecycle": {
            "initialWorkflowSha256": initial_authority_workflow_sha256,
            "initialMode": "one_shot_untouched_authority",
            "postAttemptMode": "sealed_verification_only_no_seed_or_evaluator_dispatch",
        },
        "seedSecurityClaim": "procedural_freeze_and_container_isolation_not_cryptographic_secrecy",
        "sourceRoleAllowlist": ["front", "rear", "source_features", "public_model_config"],
        "forbiddenContestantRoles": [
            "evaluator_target",
            "target_hash",
            "target_nonce",
            "raw_draw_transcript",
            "private_registry",
            "repository_history",
            "evaluator_source",
            "third_view",
        ],
        "canonicalIsolationRequirement": (
            "container_read_only_allowlist_mount_network_none_capabilities_dropped"
        ),
        "budgets": {
            "contestantTimeoutSeconds": 30,
            "contestantMemoryMegabytes": 256,
            "contestantCpuLimit": 1.0,
            "evaluatorTimeoutSeconds": 900,
            "workflowTimeoutMinutes": 60,
        },
        "thresholds": locked_thresholds(),
        "metricDefinitions": metric_definitions(),
        "fieldClasses": {
            "thresholds": "semantic_consumed",
            "denominators": "validation_only",
            "sourceEvidenceAnchorSha": "provenance_only",
        },
        "downstreamSentinelRule": (
            "fixed_primary_route_evaluator_ordinal_0_if_complete_else_unit_f_else_pr43"
        ),
        "developmentEvidence": {
            "genericFixturesOnly": True,
            "unitGV1CohortClassification": "revealed_contaminated_development_only",
            "mayCloseResearchPrototypeRows": False,
        },
        "freshEvaluatorIdentitiesRealized": False,
        "freshEvaluatorTargetsRealized": False,
        "lockHash": "",
    }
    document["lockHash"] = _hash({**document, "lockHash": ""})
    return document


def metric_definitions() -> dict[str, Any]:
    return {
        "macroNormalizedObservableError": "mean absolute range-normalised observable error",
        "worstNormalizedObservableError": "maximum absolute range-normalised observable error",
        "silhouetteIoU": "foreground intersection over union in the declared evaluator view",
        "boundaryProxyError": "one_minus_silhouette_iou",
        "landmarkProxyError": "maximum Euclidean source-landmark displacement in normalised image",
        "referenceRmsVertexErrorMeters": "RMS Euclidean error on canonical rest vertices in metres",
        "semanticSeamCorrectness": (
            "exact seam role inventory endpoint pairing and opening relationship equality"
        ),
        "sourceContribution": "observed and generated field counts derived from prediction lineage",
        "pbrIntegrity": "finite bounded declared PBR fields only; no physical-accuracy claim",
        "determinism": "fresh evaluator subprocess stable-record equality",
    }


def load_protocol(root: Path) -> dict[str, Any]:
    value = read_json(root / PROTOCOL_PATH)
    if not isinstance(value, Mapping):
        raise ValueError("confirmation_v2_protocol_mapping_required")
    protocol = dict(value)
    issues = validate_protocol(protocol)
    if issues:
        raise ValueError(";".join(issues))
    return protocol


def validate_protocol(protocol: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    expected = {
        "benchmarkVersion": BENCHMARK_VERSION,
        "evaluatorIdentityCount": 16,
        "predictionDenominator": 64,
        "fullCompileDenominator": 48,
        "primaryCompileRepeatDenominator": 16,
        "maximumFullCompiles": 64,
        "appearanceDenominator": 24,
        "primaryAppearanceRepeatDenominator": 8,
        "maximumAppearanceEvaluations": 32,
        "primaryRoute": PRIMARY_ROUTE,
        "implementationHashMode": "utf8_canonical_lf_final_newline",
    }
    for field, expected_value in expected.items():
        if protocol.get(field) != expected_value:
            issues.append(f"protocol_field_invalid:{field}")
    for field, expected_routes in (
        ("routes", ROUTES),
        ("fullCompileRoutes", FULL_COMPILE_ROUTES),
        ("appearanceRoutes", APPEARANCE_ROUTES),
    ):
        if tuple(protocol.get(field, ())) != expected_routes:
            issues.append(f"protocol_routes_invalid:{field}")
    if tuple(protocol.get("appearanceOrdinals", ())) != APPEARANCE_ORDINALS:
        issues.append("protocol_appearance_ordinals_invalid")
    for field in (
        "repeatReserveReassignable",
        "perIdentityRouteSelectionAllowed",
        "freshEvaluatorIdentitiesRealized",
        "freshEvaluatorTargetsRealized",
    ):
        if protocol.get(field) is not False:
            issues.append(f"protocol_false_field_invalid:{field}")
    if protocol.get("failedItemsRetainedInDenominator") is not True:
        issues.append("protocol_failure_denominator_mutable")
    expected_hash = _hash({**dict(protocol), "lockHash": ""})
    if protocol.get("lockHash") != expected_hash:
        issues.append("protocol_lock_hash_mismatch")
    return issues


def validate_implementation(root: Path, protocol: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    files = protocol.get("implementationFiles")
    if not isinstance(files, list) or not files:
        return ["implementation_inventory_missing"]
    for item in files:
        if not isinstance(item, Mapping):
            issues.append("implementation_record_invalid")
            continue
        relative = str(item.get("path", ""))
        path = root / relative
        if not path.is_file() or canonical_source_sha256(path) != item.get("sha256"):
            issues.append(f"implementation_hash_mismatch:{relative}")
    if protocol.get("implementationDigest") != _hash(files):
        issues.append("implementation_digest_mismatch")
    return issues


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


def canonical_source_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return sha256_bytes(canonical_text_bytes(text, final_newline=True))
