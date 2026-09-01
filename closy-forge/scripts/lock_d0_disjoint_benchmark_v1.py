from __future__ import annotations

from pathlib import Path

from closy_forge.disjoint_benchmark_v1.protocol import (
    BENCHMARK_VERSION,
    OBSERVABLE_PARAMETERS,
    PARAMETER_RANGES,
)
from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_file

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    source_files = sorted((ROOT / "src/closy_forge/disjoint_benchmark_v1").glob("*.py"))
    protocol = {
        "schemaVersion": 1,
        "benchmarkVersion": BENCHMARK_VERSION,
        "purpose": "public_project_authored_identity_disjoint_synthetic_tshirt_reconstruction",
        "developmentIdentityCount": 8,
        "evaluatorIdentityCount": 16,
        "splitPolicy": "eight_development_then_sixteen_seed_authority_derived_evaluator_identities",
        "identityDisjoint": True,
        "minimumNormalizedReferenceDistance": 0.15,
        "withinRoleMinimumDistance": 0.075,
        "maximumDrawAttempts": 4096,
        "firstDrawPolicy": "accept_or_reject_each_deterministic_draw_once_no_reroll_discretion",
        "firstDrawStructuralAcceptance": (
            "canonical_non_physical_pattern_topology_seam_opening_binding_compile_must_pass"
        ),
        "observableParameters": list(OBSERVABLE_PARAMETERS),
        "parameterRanges": {name: list(bounds) for name, bounds in PARAMETER_RANGES.items()},
        "fixedUnidentifiableControls": [
            "sleeve_cap_height",
            "hem_allowance",
            "neckband_width",
            "neckband_length_ease_ratio",
            "target_panel_edge_length",
        ],
        "requiredVariation": [
            "chest_width",
            "body_length",
            "sleeve_length",
            "sleeve_opening",
            "neck_shape",
            "shoulder_slope",
            "ease",
            "camera",
            "base_colour",
            "logo_position_scale_shape",
            "logo_absence",
            "controlled_occlusion",
            "controlled_crop",
        ],
        "opaqueIdentityPolicy": {
            "algorithm": "hmac_sha256_seed_role_attempt_first_20_hex",
            "targetValuesInIdentity": False,
            "targetValuesInFilename": False,
            "targetValuesInOrdering": False,
            "targetValuesInCacheKey": False,
        },
        "commitmentPolicy": {
            "algorithm": "sha256_512bit_deterministic_nonce_plus_canonical_target_payload",
            "nonceBits": 512,
            "nonceWithheldUntilPredictionFreeze": True,
            "targetWithheldUntilPredictionFreeze": True,
        },
        "seedAuthorityPolicy": {
            "derivation": "sha256_lock_commit_sha_first_non_rerun_run_id_job_id",
            "laterRerunsIgnored": True,
            "replacementLockHeadsIgnored": True,
        },
        "sourceRoles": ["front", "rear", "source_masks", "source_landmarks", "source_cameras"],
        "evaluatorOnlyRoles": [
            "target_parameters",
            "target_pattern",
            "target_3d",
            "third_view",
            "nonce",
        ],
        "cameraPolicy": {
            "projection": "orthographic",
            "imageSize": [128, 160],
            "intrinsicsExtrinsicsFrozenBeforePrediction": True,
            "candidateBoundsAutoFraming": False,
            "runtimeBoundsFramed": False,
            "principalPointPerturbationMaximum": 0.008,
            "azimuthPerturbationDegreesMaximum": 2.0,
            "elevationPerturbationDegreesMaximum": 1.0,
        },
        "captureAcceptance": {
            "maximumOcclusionFraction": 0.075,
            "maximumCropFraction": 0.025,
            "sourceMustRemainNonBlank": True,
            "rejectionsRemainInTranscript": True,
        },
        "metricDefinitions": {
            "parameter": (
                "absolute_error_divided_by_development_frozen_valid_range_macro_per_identity"
            ),
            "effectiveHalfChest": "half_chest_width_plus_body_ease",
            "silhouette": "foreground_intersection_over_union_fixed_evaluator_camera",
            "reference3d": "index_aligned_rms_and_maximum_rest_vertex_distance",
            "appearance": (
                "unit_f_visible_texture_predicates_with_logo_present_or_false_positive_branch"
            ),
            "failurePenaltyNormalizedError": 1.0,
            "failurePenaltySilhouetteIoU": 0.0,
        },
        "corruptionControls": [
            "commitment_nonce_mutation",
            "target_payload_mutation",
            "prediction_byte_mutation",
            "undeclared_file_read",
            "source_withdrawal",
            "route_identity_mutation",
            "compile_topology_mutation",
            "appearance_contribution_mismatch",
        ],
        "executionPolicy": {
            "applicationProcessInputIsolation": True,
            "operatingSystemSandboxClaimed": False,
            "denyByDefaultOpenedPathAudit": True,
            "subprocessRequired": True,
            "networkAllowed": False,
            "repositoryRootMountedInContestant": False,
            "maximumFullCompiles": 64,
            "maximumAppearanceEvaluations": 32,
            "physicsAllowed": False,
        },
        "bootstrapPolicy": {
            "identityLevelPaired": True,
            "resamples": 10000,
            "confidence": 0.95,
            "seedFrozenOnDevelopment": True,
        },
        "rendererDefinitions": {
            "source": "render_source_capture_separate_polygon_and_landmark_implementation",
            "evaluatorThirdView": (
                "render_evaluator_target_independent_projection_and_inclusion_implementation"
            ),
        },
        "implementationFiles": [
            {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)}
            for path in source_files
        ],
        "evaluatorIdentitiesRealized": False,
        "targetContentsMounted": False,
        "privateData": False,
        "realPhotoClaim": False,
        "productClaim": False,
    }
    write_canonical_json(
        ROOT / "fixtures/d0_disjoint_tshirt_benchmark_v1/protocol_lock.json", protocol
    )


if __name__ == "__main__":
    main()
