from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, canonical_text_bytes, read_json
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.recovery_foundation_v2.container_boundary import (
    CONTAINER_GID,
    CONTAINER_UID,
    IMAGE_REFERENCE,
)

UNIT_S_HEAD = "b8d222dadbe092e25604b838e7ad219d6a1c114b"
BENCHMARK_VERSION = "closy.d0_disjoint_tshirt_confirmation.v3"
FIXTURE_ROOT = Path("fixtures/d0_disjoint_tshirt_confirmation_v3")
PROTOCOL_PATH = FIXTURE_ROOT / "protocol_lock.json"
WORKFLOW_PATH = Path("../.github/workflows/forge-unit-t-d0-v3-authority.yml")
SEED_NAMESPACE = b"closy/d0-disjoint-tshirt/v3"

ROUTES = (
    "metadata_category_control_v3",
    "no_pixel_template_prior_v3",
    "pixel_mask_landmark_optimizer_v3",
    "pixel_learned_structured_tshirt_v3",
)
FULL_COMPILE_ROUTES = ROUTES[1:]
PRIMARY_ROUTE = ROUTES[3]
APPEARANCE_ORDINALS = tuple(range(8))
OUTCOMES = (
    "qualified_identity_disjoint_from_recoverable_inventory_d0_v3",
    "completed_benchmark_failed_absolute_gates",
    "completed_benchmark_failed_comparative_gates",
    "completed_benchmark_mixed_row_results",
    "attempted_integrity_error",
    "dependency_blocked_before_official_seed",
)
PUBLIC_FAILURE_ALLOWLIST = (
    "attempt_manifest.json",
    "authority_commitments.json",
    "benchmark_result.json",
    "changed_path_audit.json",
    "environment_attestation.json",
    "isolation_report.json",
    "prediction_freeze.json",
    "predictions.json",
    "public_failure.json",
    "public_source_inventory.json",
    "raw_draw_rejection_transcript.json",
    "source_roles/**",
    "target_reveal.json",
)


def thresholds() -> dict[str, Any]:
    return {
        "minimumPrimaryPredictionCoverage": 14,
        "maximumMedianMacroNormalizedObservableError": 0.10,
        "maximumWorstNormalizedObservableError": 0.25,
        "minimumMeanEvaluatorViewSilhouetteIoU": 0.30,
        "maximumBoundaryProxyError": 0.20,
        "maximumLandmarkProxyError": 0.14,
        "maximumReferenceRmsVertexErrorMeters": 0.08,
        "requiredPanels": 5,
        "requiredOpenings": [
            "opening.cuff.left",
            "opening.cuff.right",
            "opening.hem",
            "opening.neck",
        ],
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


def route_contracts() -> list[dict[str, Any]]:
    return [
        {
            "routeId": ROUTES[0],
            "semantics": "attempt_only_metadata_category_control",
            "inputRoles": ["tshirt_category"],
            "compileScored": False,
            "appearanceScored": False,
        },
        {
            "routeId": ROUTES[1],
            "semantics": "fixed_no_pixel_template_prior",
            "inputRoles": ["tshirt_category"],
            "compileScored": True,
            "appearanceScored": True,
        },
        {
            "routeId": ROUTES[2],
            "semantics": "deterministic_decoded_pixel_mask_landmark_optimizer",
            "inputRoles": ["tshirt_category", "front_png", "rear_png"],
            "compileScored": True,
            "appearanceScored": True,
        },
        {
            "routeId": ROUTES[3],
            "semantics": "fixed_fitted_pixel_conditioned_structured_tshirt_model",
            "inputRoles": ["tshirt_category", "front_png", "rear_png", "fitted_model"],
            "compileScored": True,
            "appearanceScored": True,
        },
    ]


def build_protocol(
    *,
    implementation_files: Sequence[Mapping[str, Any]],
    workflow_sha256: str,
    model_sha256: str,
    model_digest: str,
    typed_inventory_digest: str,
) -> dict[str, Any]:
    implementations = [dict(row) for row in implementation_files]
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "benchmarkVersion": BENCHMARK_VERSION,
        "unitSHead": UNIT_S_HEAD,
        "unitSEvaluatorVersion": "closy.d0_disjoint_tshirt_confirmation.v3",
        "implementationFiles": implementations,
        "implementationDigest": _hash(implementations),
        "implementationHashMode": "utf8_canonical_lf_final_newline",
        "authorityWorkflowSha256": workflow_sha256,
        "container": {
            "baseImageReference": IMAGE_REFERENCE,
            "uid": CONTAINER_UID,
            "gid": CONTAINER_GID,
            "network": "none",
            "rootFilesystem": "read_only",
            "inputMount": "read_only_declared_roles_only",
            "outputMount": "bounded_allowlisted_collector",
            "capabilities": "all_dropped",
            "noNewPrivileges": True,
            "pidsLimit": 64,
            "cpuLimit": 1.0,
            "memoryMegabytes": 256,
            "timeoutSeconds": 30,
        },
        "contestant": {
            "dockerContext": "docker",
            "dockerfile": "docker/d0_v3_confirmation/Dockerfile",
            "entrypoint": "/app/entrypoint.sh",
            "modelPath": "models/d0_v3/public_pixel_fitted_tshirt_v1.json",
            "modelCanonicalTextSha256": model_sha256,
            "modelDigest": model_digest,
            "trainingClass": "public_fixed_pre_v3_development_only",
            "trainingOrCalibrationOnV3": False,
        },
        "routes": list(ROUTES),
        "routeContracts": route_contracts(),
        "primaryRoute": PRIMARY_ROUTE,
        "fullCompileRoutes": list(FULL_COMPILE_ROUTES),
        "appearanceRoutes": list(FULL_COMPILE_ROUTES),
        "denominators": {
            "identity": 16,
            "attempt": 64,
            "fullCompile": 48,
            "primaryCompileRepeat": 16,
            "appearance": 24,
            "primaryAppearanceRepeat": 8,
        },
        "appearanceOrdinals": list(APPEARANCE_ORDINALS),
        "repeatReserveReassignable": False,
        "failedTimeoutAbstentionRowsRetained": True,
        "failurePenalty": {"macroNormalizedError": 1.0, "silhouetteIoU": 0.0},
        "thresholds": thresholds(),
        "priorInventoryDigest": typed_inventory_digest,
        "identityDistance": {
            "metric": "range_normalized_maximum_observable_parameter_distance_v1",
            "minimum": 0.18,
            "augmentationAppliedBeforeIdentityCheck": True,
            "garmentAndCapturePredicatesIndependent": True,
        },
        "cohort": {
            "generator": "closy.disjoint_benchmark_v1.realize_identities+v3_augmentation",
            "maximumDraws": 65_536,
            "strata": ["logo_absent", "logo_present", "controlled_capture", "shape_extreme"],
            "varies": [
                "pattern_dimensions_and_curve_controls",
                "seam_ease_and_openings",
                "camera_and_view",
                "pixel_crop_and_occlusion",
                "lighting_and_background",
                "base_colour_logo_shape_placement_scale",
                "bounded_pbr_preset",
                "source_image_role_availability",
            ],
            "rejectionPolicy": "first_valid_draw_meeting_locked_typed_distance_and_stratum",
        },
        "seed": {
            "entropyBits": 256,
            "entropyApi": "python.secrets.token_bytes",
            "domainSeparationUtf8Hex": SEED_NAMESPACE.hex(),
            "encoding": "hmac_sha256(raw_32_bytes,domain_bytes)_lower_hex",
            "oneSeedConsumesAttempt": True,
        },
        "targetGeneration": (
            "latent_truth_source_observations_and_private_targets_created_together_then_"
            "crop_and_occlusion_applied_only_to_source_pixels"
        ),
        "packageCompiler": "closy.d0_disjoint.structural_compiler.v1",
        "packageValidators": "canonical_garment_package_and_gate_family_validators_v1",
        "targetRenderer": "closy.d0_disjoint.source_assets.v1",
        "metricCode": "closy.d0_disjoint.evaluation_worker.v1+v3_literal_result_adapter",
        "appearanceObservability": {
            "baseColourLogoPrint": "source_observed_when_derived_from_visible_pixels",
            "unseenSideInterior": "generated_or_preset",
            "roughnessMetalnessAo": "bounded_preset_unobserved_source_fraction_zero",
            "physicalMaterialRecoveryClaimed": False,
        },
        "promotion": {
            "requires": [
                "functional_absolute",
                "container_isolation",
                "source_conditioning_comparative",
                "appearance_absolute",
                "fresh_process_determinism",
                "learned_winner_comparative",
                "integrity",
            ],
            "perIdentityWinnerAllowed": False,
            "tieRule": "simpler_lower_evidence_route",
        },
        "sentinelRule": "primary_route_ordinal_zero_independent_of_performance",
        "authority": {
            "claim": "procedural_freeze_and_container_isolation_not_cryptographic_secrecy",
            "commitmentsExternallyImmutableBeforePrediction": False,
            "commitmentsEmittedAndFsyncedBeforePredictionThenUploadedAfterJob": True,
            "oneOfficialSeed": True,
            "qualificationRetryAllowed": False,
            "postAttemptMode": "sealed_verifier_only",
            "publicFailureArtifactAllowlist": list(PUBLIC_FAILURE_ALLOWLIST),
        },
        "changedPathAllowlistAfterSeed": [
            "closy-forge/docs/evidence/d0_disjoint_tshirt_confirmation_v3/**",
            "closy-forge/fixtures/d0_disjoint_tshirt_confirmation_v3/official_attempt/**",
            "closy-forge/schemas/v1/**",
            "closy-forge/docs/blueprint_coverage.json",
            "closy-forge/docs/status-summary.md",
            ".github/workflows/forge-unit-t-d0-v3-authority.yml",
        ],
        "outcomeVocabulary": list(OUTCOMES),
        "lostV2Relation": "disjointFromUnrecoverableV2OpaqueCohort = unverified",
        "officialV3IdentityPresent": False,
        "officialV3TargetPresent": False,
        "officialV3TargetHashPresent": False,
        "officialV3NoncePresent": False,
        "officialV3RawSeedPresent": False,
        "officialV3PredictionPresent": False,
        "officialV3ResultPresent": False,
        "lockHash": "",
    }
    document["lockHash"] = _hash({**document, "lockHash": ""})
    return document


def validate_protocol(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    expected = {
        "benchmarkVersion": BENCHMARK_VERSION,
        "unitSHead": UNIT_S_HEAD,
        "routes": list(ROUTES),
        "primaryRoute": PRIMARY_ROUTE,
        "fullCompileRoutes": list(FULL_COMPILE_ROUTES),
        "appearanceRoutes": list(FULL_COMPILE_ROUTES),
        "appearanceOrdinals": list(APPEARANCE_ORDINALS),
        "outcomeVocabulary": list(OUTCOMES),
        "lostV2Relation": "disjointFromUnrecoverableV2OpaqueCohort = unverified",
    }
    for field, value in expected.items():
        if document.get(field) != value:
            issues.append(f"d0_v3_protocol_field_invalid:{field}")
    denominators = _mapping(document.get("denominators"))
    if denominators != {
        "identity": 16,
        "attempt": 64,
        "fullCompile": 48,
        "primaryCompileRepeat": 16,
        "appearance": 24,
        "primaryAppearanceRepeat": 8,
    }:
        issues.append("d0_v3_denominators_invalid")
    if document.get("repeatReserveReassignable") is not False:
        issues.append("d0_v3_repeat_reserve_mutable")
    if document.get("failedTimeoutAbstentionRowsRetained") is not True:
        issues.append("d0_v3_failure_rows_not_retained")
    if _mapping(document.get("failurePenalty")) != {
        "macroNormalizedError": 1.0,
        "silhouetteIoU": 0.0,
    }:
        issues.append("d0_v3_failure_penalty_invalid")
    if len(_records(document.get("routeContracts"))) != 4:
        issues.append("d0_v3_route_contract_inventory_invalid")
    for field in (
        "officialV3IdentityPresent",
        "officialV3TargetPresent",
        "officialV3TargetHashPresent",
        "officialV3NoncePresent",
        "officialV3RawSeedPresent",
        "officialV3PredictionPresent",
        "officialV3ResultPresent",
    ):
        if document.get(field) is not False:
            issues.append(f"d0_v3_preseed_lock_contains_official_data:{field}")
    if _hash({**dict(document), "lockHash": ""}) != document.get("lockHash"):
        issues.append("d0_v3_lock_hash_invalid")
    return sorted(set(issues))


def load_protocol(root: Path) -> dict[str, Any]:
    value = read_json(root / PROTOCOL_PATH)
    if not isinstance(value, Mapping):
        raise ValueError("d0_v3_protocol_mapping_required")
    document = dict(value)
    issues = validate_protocol(document)
    if issues:
        raise ValueError(";".join(issues))
    return document


def validate_implementation(root: Path, protocol: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    records = _records(protocol.get("implementationFiles"))
    if not records:
        return ["d0_v3_implementation_inventory_missing"]
    for row in records:
        path = root / str(row.get("path", ""))
        if not path.is_file() or canonical_source_sha256(path) != row.get("sha256"):
            issues.append(f"d0_v3_implementation_hash_mismatch:{row.get('path')}")
    if _hash(records) != protocol.get("implementationDigest"):
        issues.append("d0_v3_implementation_digest_invalid")
    return sorted(set(issues))


def canonical_source_sha256(path: Path) -> str:
    return sha256_bytes(canonical_text_bytes(path.read_text(encoding="utf-8")))


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: object) -> list[dict[str, Any]]:
    return [_mapping(row) for row in value] if isinstance(value, list | tuple) else []
