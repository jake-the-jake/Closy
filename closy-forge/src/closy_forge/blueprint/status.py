from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

STATUS_MODEL_VERSION = "closy.blueprint_status_model.v17"
PHASE_IDS = tuple(f"BP-17-PHASE-{index:02d}" for index in range(15))
MATURITY_IDS = (
    "BP-20-RESEARCH-PROTOTYPE",
    "BP-20-ALPHA",
    "BP-20-BETA",
    "BP-20-PRODUCTION",
)
A1_HEAD = "5d080caad354bcecff94a7eadf16d080d68a606c"
C3_EVIDENCE_SHA = "531689b1d542dd9aeeec29a975e7136ee986c582"
PHY1_EVIDENCE_SHA = "d393b7185d14fe414a1eb3c4ef040c6c1ad8f780"
ZEROONE_CANDIDATE_SHA = "13a844d240f4bbb2cafde105c4a0bdca8d89a06b"
ZEROONE_EXECUTABLE_SHA256 = "59bb051455ae2878a30edd353bdb451271107bb5df3e3570b89b955379cf2065"
ZEROONE_DYNAMIC_SHA = "413aecd24434f90d89ad35c6a8f909de75df34c7"
ZEROONE_DYNAMIC_EXECUTABLE_SHA256 = (
    "e704a0f2196f066f7aab16669356ee7de97f59b89de5cf51cbb2f529526457dc"
)
CLOSY_DYNAMIC_EVIDENCE_SHA = "960662d237e187cd8ecbcc9ebe9192367f194317"
MT1_EVIDENCE_SHA = "6b2e64566e1484e70992ba4e10150c27591f0512"
MT1_EXECUTABLE_SHA256 = "b29345b062691cfa7d7e6873c7c9b9bca2cd5a46e670b866d8e69153c0ad8476"
INTEGRATED_RUNTIME_EVIDENCE_SHA = "dd916913ac14119bc2e127989703f1c51f91e00a"
PHY1_V2_SOURCE_SHA = "477c1fd881c7e55c352ca89732e5772d9d6bbeeb"
PHY1_V2_PUBLICATION_SHA = "a6134df2fb67a8cbcb572e344caf828b926df273"
PHY1_V2_PUBLISHED_EXACT_HEAD = "f732df267642cd55960205764e699c7fa2bb2d0f"
PHY1_V2_EXACT_HEAD_WORKFLOW = "https://github.com/jake-the-jake/Closy/actions/runs/33342673147"
D0_TRUTH_RUNTIME_PUBLICATION_SHA = "dbe9b3691b6c7bfc8a8a92ceeb04a7916e34e30a"
D0_RASTER_IDENTITY_PUBLICATION_SHA = "4b1f4d550cf6e595170f9ef7bd28384c147ca2e8"
D0_FITTING_PBR_PUBLICATION_SHA = "7922e9b6ece8fca2c3b7dec13299a39de102cbc4"
PHY1_V3_EVIDENCE_SHA = "fe8f6d8a6d08e4c1b75a838728d66fea5d2c92c0"
PHY1_V3_EVIDENCE_DIGEST = "280df4684724d2dae73eb20a09008aec824c2c6476ed21325c754c9c05ef1b4c"
D0_EVIDENCE_INTEGRITY_V4_SHA = "64fd0386dbb9dec5f91d6e154ebf96a2f3baf2dd"
D0_EVIDENCE_INTEGRITY_V4_PUBLISHED_HEAD = "2f40815010cef01685a7ed873081a22f11d67c00"
UNIT_F_TEXTURE_RERENDER_V3_SHA = "7b4fbc199f462d35ba2f440494cff7cc700b0b94"
UNIT_F_TEXTURE_RERENDER_V3_PUBLISHED_HEAD = "ba54b17a0aef7518d9acac30c6b7ec6564a38d87"
UNIT_G_DISJOINT_BENCHMARK_V1_SHA = "6de060d7fa4e985070187bf417f159ecbe31e8b4"
UNIT_G_DISJOINT_BENCHMARK_V1_PUBLISHED_HEAD = "bc4927fe6d36667b5b236d844b4eff511ef6f987"
UNIT_H_CORE_RUNTIME_C3_V4_SHA = "3541507808946ae1248fba110b7732599db3fdbc"
UNIT_H_CORE_RUNTIME_C3_V4_PUBLISHED_HEAD = "e25da69d29eb1b68885b911c7354df085f4a22c0"
UNIT_I_TOPOLOGY_STRATEGY2_V4_SHA = "854b85ed769bc3e67547e4195f65dfeb78878881"
UNIT_I_TOPOLOGY_STRATEGY2_V4_PUBLISHED_HEAD = "69f17e0bc0d01472eec3aaf244c158181f74febf"
UNIT_O_TOPOLOGY_STRATEGY3_DIAGNOSIS_SHA = "d8c8318ad346ea66ebc1956ebc0839ee3d6db109"
UNIT_L_RECOVERY_FOUNDATION_V1_PUBLISHED_HEAD = "a72f45955abbe65ce14b7142668447d0477db71c"
UNIT_M_DISJOINT_CONFIRMATION_V2_AUTHORITY_HEAD = "9078a09f1156ba8b7f98099185478ca9efcee952"
UNIT_M_DISJOINT_CONFIRMATION_V2_PUBLISHED_HEAD = "552867e96d53e9d4c728f90d12e0c1c9a344ba0d"
UNIT_N_STRICT_C3_V5_AUTHORITY_HEAD = "d7b6e810477f169fea3a3cfca23c5ed99ba603b7"
UNIT_N_STRICT_C3_V5_PUBLISHED_HEAD = "e062a30ba295ed27334622916ddb449fd76e2166"

_COMMON_UNSUPPORTED = ["D1", "D2", "D3", "GPU", "mobile", "private_user"]
GATE_RECORDS: dict[str, dict[str, Any]] = {
    "C1": {
        "gateId": "C1",
        "globalStatus": "partial",
        "scopedStatus": "pass",
        "evidenceTier": "committed_deterministic_fixture_reports",
        "platform": ["ubuntu", "windows"],
        "toolchain": ["CPython 3.11", "CPython 3.12"],
        "sourceSha": A1_HEAD,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU",
        "gateScope": "capture_contract",
        "evidenceDurability": "committed_reports_plus_exact_head_ci",
        "workflowRun": "33183367784",
        "unsupportedTiers": _COMMON_UNSUPPORTED,
        "blockers": ["authorised_capture_breadth", "private_user_evidence"],
    },
    "C2": {
        "gateId": "C2",
        "globalStatus": "partial",
        "scopedStatus": "pass",
        "evidenceTier": "committed_deterministic_fixture_reports",
        "platform": ["ubuntu", "windows"],
        "toolchain": ["CPython 3.11", "CPython 3.12"],
        "sourceSha": A1_HEAD,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU",
        "gateScope": "canonical_generation_contract",
        "evidenceDurability": "committed_reports_plus_exact_head_ci",
        "workflowRun": "33183367784",
        "unsupportedTiers": _COMMON_UNSUPPORTED,
        "blockers": ["independent_provider_breadth", "human_visual_review"],
    },
    "C3-Binding-D0": {
        "gateId": "C3-Binding-D0",
        "globalStatus": "partial",
        "scopedStatus": "pass",
        "evidenceTier": "committed_executed_candidate_profile",
        "platform": ["windows"],
        "toolchain": ["CPython 3.11"],
        "sourceSha": C3_EVIDENCE_SHA,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU",
        "gateScope": "binding",
        "evidenceDurability": "committed_report_plus_external_exact_head_check_attestation",
        "workflowRun": "33264403890",
        "unsupportedTiers": _COMMON_UNSUPPORTED,
        "blockers": ["broader_avatar_garment_platform_and_private_user_profiles"],
        "legacyHistoricalOnly": True,
        "maySatisfyStrictC3OrD0Rp08": False,
    },
    "PHY1-SingleLayer-D0": {
        "gateId": "PHY1-SingleLayer-D0",
        "globalStatus": "partial",
        "scopedStatus": "failed",
        "evidenceTier": "committed_failure_witnesses",
        "platform": ["windows"],
        "toolchain": ["CPython 3.11"],
        "sourceSha": PHY1_EVIDENCE_SHA,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU",
        "gateScope": "physical",
        "evidenceDurability": "committed_failure_reports",
        "workflowRun": None,
        "unsupportedTiers": _COMMON_UNSUPPORTED + ["multilayer"],
        "blockers": [
            "qualified_timestamped_states_passed_0_of_11",
            "unresolved_contacts_9",
            "residual_depth_0.001878992_exceeds_0.000160000",
            "simulation_surface_clearance_not_run",
            "stitched_surface_clearance_negative_0.009084014",
            "maximum_seam_crack_0.109609688",
            "maximum_tangential_seam_slip_0.028009643",
            "qualified_temporal_degenerate_frame_triangles_198",
            "qualified_swept_degenerate_transitions_191",
            "qualified_true_inversions_15",
        ],
    },
    "PHY1-SingleLayer-D0-v2": {
        "gateId": "PHY1-SingleLayer-D0-v2",
        "globalStatus": "partial",
        "scopedStatus": "failed",
        "evidenceTier": "committed_deterministic_topology_v2_failure_witnesses",
        "platform": ["windows"],
        "toolchain": ["CPython 3.11"],
        "sourceSha": PHY1_V2_SOURCE_SHA,
        "evidencePublicationSha": PHY1_V2_PUBLICATION_SHA,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU/source/opt-in topology-v2 physical experiment",
        "gateScope": "physical topology-v2 experiment only",
        "evidenceDurability": "committed_report_with_byte_identical_double_replay",
        "workflowRun": None,
        "stateCount": 11,
        "statePassCount": 0,
        "qualifiedTemporalDegenerateFrameTriangles": 0,
        "qualifiedSweptDegenerateTransitions": 0,
        "qualifiedTrueInversions": 0,
        "runtimeCapabilityExposed": False,
        "dRuntimePinnedToV1": True,
        "unsupportedTiers": _COMMON_UNSUPPORTED
        + ["multilayer", "integrated_CCD", "solver_driven_Z2"],
        "blockers": [
            "qualified_physical_states_passed_0_of_11",
            "maximum_unresolved_contacts_867",
            "residual_depth_0.002399077_exceeds_0.000160000",
            "residual_violations_4143",
            "simulation_surface_clearance_negative_0.014360829",
            "render_surface_clearance_negative_0.064466621",
            "maximum_seam_crack_0.417546910",
            "maximum_tangential_seam_slip_0.417546910",
            "strain_opening_support_energy_failed",
            "coupled_convergence_failed",
        ],
    },
    "PHY1-Neutral-SeamSupport-D0-v3": {
        "gateId": "PHY1-Neutral-SeamSupport-D0-v3",
        "globalStatus": "partial",
        "scopedStatus": "failed",
        "evidenceTier": "committed_persisted_neutral_trajectory_and_independent_oracles",
        "platform": ["windows"],
        "toolchain": ["CPython 3.12"],
        "sourceSha": PHY1_V3_EVIDENCE_SHA,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored public fixture",
        "executionKind": "CPU/source/opt-in topology-v2 neutral physical experiment",
        "gateScope": "neutral seam-support-collision preflight only",
        "evidenceDurability": "59-file content-addressed evidence with unchanged GLB rescore",
        "workflowRun": None,
        "outcomeClass": "A_neutral_preflight_failed_v3",
        "trajectoryFrameCount": 49,
        "unresolvedContactCount": 242,
        "maximumResidualDepthMeters": 0.0024,
        "maximumSeamCrackMeters": 0.041513220488,
        "maximumTangentialSlipMeters": 0.145067036152,
        "minimumRenderClearanceMeters": -0.050591166989,
        "evidenceDigest": PHY1_V3_EVIDENCE_DIGEST,
        "phy1Executed": False,
        "ccdExecuted": False,
        "z2Executed": False,
        "runtimeCapabilityExposed": False,
        "dRuntimePinnedToV1": True,
        "remainingTopologyStrategies": 2,
        "remainingSeamModels": 0,
        "unsupportedTiers": _COMMON_UNSUPPORTED
        + ["multilayer", "full_PHY1", "integrated_CCD", "solver_driven_Z2"],
        "blockers": [
            "neutral_acceptance_passed_11_of_28_checks",
            "unresolved_contacts_242",
            "residual_depth_0.0024_exceeds_0.00016",
            "simulation_clearance_0_below_0.000005",
            "render_clearance_negative_0.050591166989",
            "seam_crack_0.041513220488_exceeds_0.002",
            "tangential_slip_0.145067036152_exceeds_0.005",
            "support_strain_area_terminal_energy_and_runtime_failed",
        ],
    },
    "PHY1-Topology-Strategy2-D0-v4": {
        "gateId": "PHY1-Topology-Strategy2-D0-v4",
        "globalStatus": "partial",
        "scopedStatus": "outcome_M_strategy_microfixture_failed_no_candidate",
        "evidenceTier": "committed_candidate_independent_mechanical_equivalence_failure",
        "platform": ["windows"],
        "toolchain": ["CPython 3.11"],
        "sourceSha": UNIT_I_TOPOLOGY_STRATEGY2_V4_SHA,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored public fixture",
        "executionKind": "candidate-independent analytic mechanical equivalence microfixture",
        "gateScope": "reserved topology strategy 2 transfer admission only",
        "evidenceDurability": "immutable lock_result_attempt_registry_and_logical_J_A_closure",
        "workflowRun": None,
        "strategyId": "PHY1-V4-S2-CONFORMING-SEAM-QUOTIENT",
        "outcomeClass": "M",
        "candidateOpened": False,
        "solverStepAdvanced": False,
        "candidateAttemptConsumed": False,
        "unitJAuthorized": False,
        "unitKEligible": False,
        "runtimeCapabilityExposed": False,
        "dRuntimePinnedToV1": True,
        "remainingTopologyStrategies": 1,
        "remainingSeamModels": 0,
        "unsupportedTiers": _COMMON_UNSUPPORTED
        + ["full_PHY1", "integrated_CCD", "solver_driven_Z2", "post_topology_candidate"],
        "blockers": [
            "quotient_shared_DOFs_not_mechanically_equivalent_to_frozen_finite_compliance_seams",
            "position_difference_1.5999980159352167e-08_exceeds_1e-12",
            "stored_energy_difference_2.8799928574752917e-07_exceeds_1e-12",
            "impulse_difference_1.3333317066849276e-10_exceeds_1e-12",
            "no_admissible_post_topology_candidate",
        ],
    },
    "PHY1-Topology-Strategy3-Diagnosis-D0-v1": {
        "gateId": "PHY1-Topology-Strategy3-Diagnosis-D0-v1",
        "globalStatus": "partial",
        "scopedStatus": "no_strategy3_class_admitted_within_bounded_diagnosis",
        "evidenceTier": "committed_candidate_independent_production_kernel_development_fixtures",
        "platform": ["windows", "ubuntu"],
        "toolchain": ["CPython 3.11", "CPython 3.12"],
        "sourceSha": UNIT_O_TOPOLOGY_STRATEGY3_DIAGNOSIS_SHA,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic development fixtures",
        "executionKind": "two bounded candidate-independent production-kernel revisions",
        "gateScope": "pre-candidate topology strategy class admission only",
        "evidenceDurability": "immutable_lock_two_revision_results_and_exact_head_ci",
        "workflowRun": None,
        "revisionCount": 2,
        "revisionFixturePassCounts": [7, 7],
        "revisionFixtureDenominator": 8,
        "admittedStrategyClass": None,
        "candidateCreated": False,
        "candidateAttemptConsumed": False,
        "finalStrategyConsumed": False,
        "unitPEligible": False,
        "unitQEligible": False,
        "unitREligible": False,
        "runtimeCapabilityExposed": False,
        "dRuntimePinnedToV1": True,
        "remainingTopologyStrategies": 1,
        "remainingCandidateAttempts": 1,
        "remainingSeamModels": 0,
        "unsupportedTiers": _COMMON_UNSUPPORTED
        + ["full_PHY1", "integrated_CCD", "solver_driven_Z2", "post_topology_candidate"],
        "blockers": [
            "revision_1_t_junction_and_incomplete_semantic_seam_transfer",
            "revision_2_incomplete_semantic_seam_transfer",
            "no_strategy3_class_admitted",
        ],
    },
    "ResearchPrototype-D0-matrix-v2": {
        "gateId": "ResearchPrototype-D0-matrix-v2",
        "globalStatus": "partial",
        "scopedStatus": "historical_superseded_9_pass_3_fail_3_not_run",
        "evidenceTier": "exact_selected_identity_predicate_matrix",
        "platform": ["windows", "ubuntu"],
        "toolchain": ["CPython 3.11", "CPython 3.12"],
        "sourceSha": PHY1_V3_EVIDENCE_SHA,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored public fixture",
        "executionKind": "predicate evaluation over opened exact evidence",
        "gateScope": "research prototype",
        "evidenceDurability": "committed matrix and exact-head stacked CI",
        "workflowRun": None,
        "firstUnmetRequiredPredicate": "D0-RP-07",
        "unsupportedTiers": _COMMON_UNSUPPORTED + ["real_fabric", "human_review"],
        "blockers": ["superseded_by_matrix_v3_integrity_reset"],
    },
    "ResearchPrototype-D0-matrix-v3-core": {
        "gateId": "ResearchPrototype-D0-matrix-v3-core",
        "globalStatus": "partial",
        "scopedStatus": "partial_7_pass_4_fail_0_not_run",
        "evidenceTier": "artifact_reopened_selected_identity_predicate_matrix",
        "platform": ["windows", "ubuntu"],
        "toolchain": ["CPython 3.11", "CPython 3.12"],
        "sourceSha": D0_EVIDENCE_INTEGRITY_V4_SHA,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored public fixture",
        "executionKind": "predicate evaluation over opened exact evidence",
        "gateScope": "research prototype core exact fixture",
        "evidenceDurability": "committed_hash_chained_matrix_and_exact_head_stacked_ci",
        "workflowRun": None,
        "firstUnmetRequiredPredicate": "D0-RP-03",
        "unsupportedTiers": _COMMON_UNSUPPORTED
        + ["real_fabric", "human_review", "identity_disjoint_cohort"],
        "blockers": ["D0-RP-03", "D0-RP-04", "D0-RP-07", "D0-RP-15"],
    },
    "ResearchPrototype-D0-matrix-v3-supplemental": {
        "gateId": "ResearchPrototype-D0-matrix-v3-supplemental",
        "globalStatus": "partial",
        "scopedStatus": "2_pass_0_fail_2_not_run",
        "evidenceTier": "artifact_reopened_supplemental_predicate_matrix",
        "platform": ["windows", "ubuntu"],
        "toolchain": ["CPython 3.11", "CPython 3.12"],
        "sourceSha": D0_EVIDENCE_INTEGRITY_V4_SHA,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored public fixture",
        "executionKind": "predicate evaluation over opened supplemental evidence",
        "gateScope": "supplemental runtime and governance",
        "evidenceDurability": "committed_hash_chained_matrix_and_exact_head_stacked_ci",
        "workflowRun": None,
        "firstUnmetRequiredPredicate": "D0-RP-10",
        "unsupportedTiers": _COMMON_UNSUPPORTED
        + ["real_fabric", "human_review", "identity_disjoint_cohort"],
        "blockers": ["D0-RP-10", "D0-RP-14"],
    },
    "TextureRerender-KnownTarget-v3": {
        "gateId": "TextureRerender-KnownTarget-v3",
        "globalStatus": "partial",
        "scopedStatus": "known_target_regression_pass_not_qualification",
        "evidenceTier": "one_shot_known_target_engineering_regression",
        "platform": ["windows", "ubuntu"],
        "toolchain": ["CPython 3.11", "CPython 3.12"],
        "sourceSha": UNIT_F_TEXTURE_RERENDER_V3_SHA,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored public fixture and already-known evaluator target",
        "executionKind": "frozen source projection followed by one known-target replay",
        "gateScope": "engineering regression only",
        "evidenceDurability": "committed prediction before evaluator and hash-chained attempt",
        "workflowRun": None,
        "knownTargetTrialCount": 1,
        "passedPredicateCount": 34,
        "totalPredicateCount": 34,
        "d0Rp07Promoted": False,
        "unitGRequired": True,
        "unsupportedTiers": _COMMON_UNSUPPORTED
        + ["held_out", "identity_disjoint_cohort", "real_fabric", "human_review"],
        "blockers": ["unit_g_identity_disjoint_benchmark_required"],
    },
    "D0-DisjointTshirt-v1": {
        "gateId": "D0-DisjointTshirt-v1",
        "globalStatus": "partial",
        "scopedStatus": "benchmark_failed_fixed_inventory_unfinished",
        "evidenceTier": "identity_disjoint_committed_predictions_failed_evaluator_harness",
        "platform": ["windows"],
        "toolchain": ["CPython 3.11"],
        "sourceSha": UNIT_G_DISJOINT_BENCHMARK_V1_SHA,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored public synthetic identity-disjoint cohort",
        "executionKind": "isolated predictions then frozen evaluator harness failure",
        "gateScope": "16-identity evaluator cohort",
        "evidenceDurability": "committed_lock_commitments_predictions_reveal_and_failure",
        "workflowRun": "33467062432",
        "developmentIdentityCount": 8,
        "evaluatorIdentityCount": 16,
        "predictionCount": 64,
        "fullCompileCount": 0,
        "appearanceEvaluationCount": 0,
        "rowResults": {
            "D0-RP-03": {"result": "fail", "attemptState": "completed"},
            "D0-RP-04": {
                "result": "fail",
                "attemptState": "attempted_integrity_error",
            },
            "D0-RP-06": {"result": "fail", "attemptState": "completed"},
            "D0-RP-07": {"result": "fail", "attemptState": "completed"},
        },
        "coverageState": "partial",
        "latestGreenChecksMeaning": "failed_state_preservation_not_cohort_success",
        "firstUnmetRequiredPredicate": "fixed_inventory_evaluator_completion",
        "unsupportedTiers": _COMMON_UNSUPPORTED
        + ["cohort_gate_pass", "real_photo", "real_fabric", "human_review"],
        "blockers": [
            "frozen_evaluator_transcript_loader_expected_mapping_but_transcript_is_list",
            "no_completed_canonical_compile_or_appearance_evaluation",
        ],
    },
    "D0-DisjointTshirt-v2": {
        "gateId": "D0-DisjointTshirt-v2",
        "globalStatus": "partial",
        "scopedStatus": "attempted_integrity_error",
        "evidenceTier": "external_authority_log_and_committed_failure_record",
        "platform": ["ubuntu"],
        "toolchain": ["CPython 3.11", "Docker"],
        "sourceSha": UNIT_M_DISJOINT_CONFIRMATION_V2_AUTHORITY_HEAD,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored public synthetic ephemeral cohort",
        "executionKind": "external authority stopped at container negative control",
        "gateScope": "16-identity evaluator-v2 cohort",
        "evidenceDurability": "github_run_log_plus_committed_sealed_failure_record",
        "workflowRun": "33532344652",
        "authorityJob": "99938286152",
        "acceptedIdentityCount": 16,
        "predictionCount": 0,
        "predictionDenominator": 64,
        "fullCompileCount": 0,
        "fullCompileDenominator": 48,
        "appearanceEvaluationCount": 0,
        "appearanceEvaluationDenominator": 24,
        "rowResults": {
            row: {"result": "fail", "attemptState": "attempted_integrity_error"}
            for row in ("D0-RP-03", "D0-RP-04", "D0-RP-06", "D0-RP-07")
        },
        "coverageState": "partial",
        "qualificationRetryAllowed": False,
        "firstUnmetRequiredPredicate": "container_negative_control_must_write_audited_output",
        "unsupportedTiers": _COMMON_UNSUPPORTED
        + ["cohort_gate_pass", "real_photo", "real_fabric", "human_review"],
        "blockers": [
            "container_boundary_probe_output_mount_permission_denied",
            "official_commitment_and_source_bytes_not_recoverable_after_skipped_artifact_upload",
            "no_prediction_compile_or_appearance_denominator_completed",
        ],
    },
    "MT1-MechanicalReference-D0": {
        "gateId": "MT1-MechanicalReference-D0",
        "globalStatus": "partial",
        "scopedStatus": "pass",
        "evidenceTier": "committed_clean_reference_mechanical_transport_evidence",
        "platform": ["ubuntu", "windows"],
        "toolchain": ["CPython 3.11", "MSVC Release"],
        "sourceSha": MT1_EVIDENCE_SHA,
        "executableSha": MT1_EXECUTABLE_SHA256,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "compiled CPU/headless/analytic mechanical reference",
        "gateScope": "mechanical transport only",
        "evidenceDurability": "committed_report_plus_exact_head_cross_platform_ci",
        "workflowRun": "33302649199",
        "requestIdentity": "38fadbc2b08bddb83a6dff0d2c086070ebf22c715767b847d08bff1d2431e3ca",
        "outputIdentity": "996b50ed90946f1c01afe9bf450060008547b5db4fd2ba66902bf9ddf6e80217",
        "unsupportedTiers": [
            "blueprint_Z2",
            "solver_driven",
            "PHY1",
            "GPU",
            "mobile",
            "private_user",
        ],
        "blockers": [
            "analytic_clip_is_not_solver_driven_cloth",
            "no_phy1_or_blueprint_z2_implication",
        ],
    },
    "LayerCollision-D0": {
        "gateId": "LayerCollision-D0",
        "globalStatus": "partial",
        "scopedStatus": "pass",
        "evidenceTier": "committed_canonical_surface_geometric_projection",
        "platform": ["windows"],
        "toolchain": ["CPython 3.12"],
        "sourceSha": INTEGRATED_RUNTIME_EVIDENCE_SHA,
        "executableSha": None,
        "garmentFamilies": ["inner_top", "outer_overshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU/headless/geometric simultaneous surface projection",
        "gateScope": "geometric two-layer outfit clearance",
        "evidenceDurability": "committed_indexed_surface_report",
        "workflowRun": None,
        "unsupportedTiers": ["physical_cloth", "PHY1", "GPU", "mobile", "private_user"],
        "blockers": [
            "geometric_projection_is_not_physical_simulation",
            "no_solver_driven_outfit_motion",
        ],
    },
    "Z1": {
        "gateId": "Z1",
        "globalStatus": "partial",
        "scopedStatus": "candidate_default_all_family_and_representative_pass",
        "historicalProfileStatus": "pass",
        "candidateAllFamilyStatus": "pass",
        "representativeStaticStatus": "pass",
        "originalDeclaredParameterRangeStatus": "partial",
        "currentMasterRequalified": False,
        "phase10Status": "partial",
        "evidenceTier": "durable_candidate_binary_plus_committed_all_family_reports",
        "platform": ["windows"],
        "toolchain": ["MSVC 19.36 Release"],
        "sourceSha": ZEROONE_CANDIDATE_SHA,
        "closySourceSha": C3_EVIDENCE_SHA,
        "currentMasterSha": None,
        "executableSha": ZEROONE_EXECUTABLE_SHA256,
        "garmentFamilies": [
            "tshirt",
            "sleeveless_top",
            "long_sleeved_top",
            "simple_skirt",
            "simple_trousers",
            "simple_dress",
            "button_shirt",
            "jacket_outerwear",
            "layered_asymmetric",
        ],
        "avatarProfile": "not_applicable_static_cook",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU/headless/static",
        "gateScope": "static ZeroOne",
        "evidenceDurability": "durable_zeroone_build_artifact_plus_local_paired_reports",
        "workflowRun": "33264403890",
        "allFamilyAttemptCount": 9,
        "successfulFamilyCount": 9,
        "rejectedFamilyCount": 0,
        "unsupportedTiers": ["current_master", "GPU", "mobile", "dynamic", "human_review"],
        "blockers": [
            "original_declared_parameter_range_partial",
            "candidate_static_not_merged_to_master",
            "paired_closy_workflow_not_durable",
            "human_visual_review_not_performed",
        ],
    },
    "Z2": {
        "gateId": "Z2",
        "globalStatus": "partial",
        "scopedStatus": "failed_compiled_single_lod_reference_pairing",
        "evidenceTier": "committed_compiled_failure_witnesses_plus_exact_head_ci",
        "platform": ["windows"],
        "toolchain": ["MSVC Release", "CPython 3.11"],
        "sourceSha": CLOSY_DYNAMIC_EVIDENCE_SHA,
        "zeroOneSourceSha": ZEROONE_DYNAMIC_SHA,
        "executableSha": ZEROONE_DYNAMIC_EXECUTABLE_SHA256,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "compiled CPU/headless/dynamic/single-LOD reference",
        "gateScope": "dynamic ZeroOne",
        "evidenceDurability": "committed_pairing_reports_plus_exact_head_ci",
        "workflowRun": "33270987449",
        "zeroOneWorkflowRun": "33262736792",
        "frameCount": 13,
        "maximumPositionErrorMeters": 0.0,
        "maximumRestErrorMeters": 0.0,
        "cullingFalseNegativeCount": 0,
        "minimumSweptTriangleDoubleArea": 0.00005516801958569897,
        "nonAdjacentSelfIntersectionsByFrame": [
            971,
            931,
            930,
            931,
            929,
            933,
            933,
            933,
            929,
            931,
            930,
            931,
            971,
        ],
        "unsupportedTiers": [
            "accepted_dynamic_namespace",
            "multi_LOD",
            "solver_driven",
            "GPU",
            "mobile",
        ],
        "blockers": [
            "compiled_output_fails_nonadjacent_dense_self_intersection_oracle",
            "pairing_revision_budget_exhausted",
        ],
    },
    "P1": {
        "gateId": "P1",
        "globalStatus": "discovery_pending",
        "scopedStatus": "not_run",
        "evidenceTier": "none",
        "platform": [],
        "toolchain": [],
        "sourceSha": A1_HEAD,
        "executableSha": None,
        "garmentFamilies": [],
        "avatarProfile": "none",
        "computeProfile": "not_run",
        "dataProvenance": "private user",
        "executionKind": "not_run",
        "gateScope": "product",
        "evidenceDurability": "none",
        "workflowRun": None,
        "unsupportedTiers": ["private_user", "licence", "human_review", "mobile"],
        "blockers": ["consent", "privacy_review", "licence_review", "device_evidence"],
    },
}


def build_status_model(
    coverage: dict[str, Any], stack: dict[str, Any], *, evidence_anchor_sha: str
) -> dict[str, Any]:
    rows = list(coverage["rows"])
    by_id = {str(row["id"]): row for row in rows}
    counts = Counter(str(row["status"]) for row in rows)
    stages = {
        f"Z{index}": deepcopy(
            GATE_RECORDS.get(
                f"Z{index}",
                {
                    "gateId": f"Z{index}",
                    "globalStatus": by_id[f"BP-09-Z{index}"]["status"],
                    "scopedStatus": "not_run",
                    "evidenceTier": "none",
                    "platform": [],
                    "toolchain": [],
                    "sourceSha": ZEROONE_CANDIDATE_SHA,
                    "executableSha": None,
                    "garmentFamilies": [],
                    "avatarProfile": "none",
                    "computeProfile": "not_run",
                    "dataProvenance": "none",
                    "executionKind": "not_run",
                    "gateScope": "dynamic ZeroOne",
                    "evidenceDurability": "none",
                    "workflowRun": None,
                    "unsupportedTiers": ["all_runtime_profiles"],
                    "blockers": ["stage_not_implemented_or_executed"],
                },
            )
        )
        for index in range(1, 9)
    }
    gates = {name: deepcopy(record) for name, record in GATE_RECORDS.items() if name != "Z2"}
    gates.update(stages)
    return {
        "schemaVersion": 3,
        "statusModelVersion": STATUS_MODEL_VERSION,
        "evidenceAnchorSha": evidence_anchor_sha,
        "coverage": {
            "total": len(rows),
            "counts": dict(sorted(counts.items())),
            "blueprintSha256": coverage["blueprintSha256"],
            "coverageVersion": coverage["version"],
        },
        "phases": {
            phase_id.removeprefix("BP-17-PHASE-"): by_id[phase_id]["status"]
            for phase_id in PHASE_IDS
        },
        "gates": gates,
        "maturity": {
            maturity_id.removeprefix("BP-20-"): by_id[maturity_id]["status"]
            for maturity_id in MATURITY_IDS
        },
        "stack": {
            "pullRequestCount": len(stack["pullRequests"]),
            "crossRepositoryNodeCount": len(stack["nodes"]),
            "latestPullRequest": max(
                int(row["pullRequest"])
                for row in stack["nodes"]
                if row["repository"] == "jake-the-jake/Closy"
            ),
            "topology": "explicit_dag",
            "acyclic": bool(stack["validation"]["acyclic"]),
            "exactMergeBases": bool(stack["validation"]["exactMergeBases"]),
            "businessPatchMappingsComplete": bool(
                stack["validation"]["businessPatchMappingsComplete"]
            ),
            "committedSourceAnchorExceptions": [
                int(row["pullRequest"])
                for row in stack["nodes"]
                if row["repository"] == "jake-the-jake/Closy"
                and not row["latestExactHeadWorkflows"]
                and int(row["pullRequest"]) not in {39, 47, 48}
            ],
            "externalExactHeadAttestations": [
                {
                    "pullRequest": 39,
                    "committedSourceAnchorSha": PHY1_V2_PUBLICATION_SHA,
                    "publishedHeadSha": PHY1_V2_PUBLISHED_EXACT_HEAD,
                    "workflowRunUrl": PHY1_V2_EXACT_HEAD_WORKFLOW,
                    "result": "pass",
                    "authority": "github_workflow_api_and_draft_pr_body",
                },
                {
                    "pullRequest": 40,
                    "committedSourceAnchorSha": D0_TRUTH_RUNTIME_PUBLICATION_SHA,
                    "publishedHeadSha": D0_TRUTH_RUNTIME_PUBLICATION_SHA,
                    "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33380042123",
                    "result": "pass",
                    "authority": "github_workflow_api_and_draft_pr_body",
                },
                {
                    "pullRequest": 41,
                    "committedSourceAnchorSha": D0_RASTER_IDENTITY_PUBLICATION_SHA,
                    "publishedHeadSha": D0_RASTER_IDENTITY_PUBLICATION_SHA,
                    "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33393781144",
                    "result": "pass",
                    "authority": "github_workflow_api_and_draft_pr_body",
                },
                {
                    "pullRequest": 42,
                    "committedSourceAnchorSha": D0_FITTING_PBR_PUBLICATION_SHA,
                    "publishedHeadSha": D0_FITTING_PBR_PUBLICATION_SHA,
                    "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33409665461",
                    "result": "pass",
                    "authority": "github_workflow_api_and_draft_pr_body",
                },
                {
                    "pullRequest": 43,
                    "committedSourceAnchorSha": PHY1_V3_EVIDENCE_SHA,
                    "publishedHeadSha": "6aee5ed3b2753ee99c95abdef6f5a24be39b3a7e",
                    "workflowRunUrl": (
                        "https://github.com/jake-the-jake/Closy/actions/runs/33423822705"
                    ),
                    "result": "pass",
                    "authority": "github_workflow_api_and_draft_pr_body",
                },
                {
                    "pullRequest": 44,
                    "committedSourceAnchorSha": D0_EVIDENCE_INTEGRITY_V4_SHA,
                    "publishedHeadSha": D0_EVIDENCE_INTEGRITY_V4_PUBLISHED_HEAD,
                    "workflowRunUrl": (
                        "https://github.com/jake-the-jake/Closy/actions/runs/33452856012"
                    ),
                    "result": "pass",
                    "authority": "github_workflow_api_and_draft_pr_body",
                },
                {
                    "pullRequest": 45,
                    "committedSourceAnchorSha": UNIT_F_TEXTURE_RERENDER_V3_SHA,
                    "publishedHeadSha": UNIT_F_TEXTURE_RERENDER_V3_PUBLISHED_HEAD,
                    "workflowRunUrl": (
                        "https://github.com/jake-the-jake/Closy/actions/runs/33464425080"
                    ),
                    "result": "pass",
                    "authority": "github_workflow_api_and_draft_pr_body",
                },
                {
                    "pullRequest": 46,
                    "committedSourceAnchorSha": UNIT_G_DISJOINT_BENCHMARK_V1_SHA,
                    "publishedHeadSha": UNIT_G_DISJOINT_BENCHMARK_V1_PUBLISHED_HEAD,
                    "workflowRunUrl": (
                        "https://github.com/jake-the-jake/Closy/actions/runs/33503777760"
                    ),
                    "result": "pass",
                    "authority": "github_workflow_api_and_draft_pr_body",
                },
                {
                    "pullRequest": 47,
                    "committedSourceAnchorSha": UNIT_H_CORE_RUNTIME_C3_V4_SHA,
                    "publishedHeadSha": UNIT_H_CORE_RUNTIME_C3_V4_PUBLISHED_HEAD,
                    "workflowRunUrl": (
                        "https://github.com/jake-the-jake/Closy/actions/runs/33505903385"
                    ),
                    "result": "pass",
                    "authority": "github_workflow_api_and_draft_pr_body",
                },
                {
                    "pullRequest": 48,
                    "committedSourceAnchorSha": UNIT_I_TOPOLOGY_STRATEGY2_V4_SHA,
                    "publishedHeadSha": UNIT_I_TOPOLOGY_STRATEGY2_V4_PUBLISHED_HEAD,
                    "workflowRunUrl": (
                        "https://github.com/jake-the-jake/Closy/actions/runs/33511517533"
                    ),
                    "result": "pass",
                    "authority": "github_workflow_api_and_draft_pr_body",
                },
                {
                    "pullRequest": 49,
                    "committedSourceAnchorSha": UNIT_L_RECOVERY_FOUNDATION_V1_PUBLISHED_HEAD,
                    "publishedHeadSha": UNIT_L_RECOVERY_FOUNDATION_V1_PUBLISHED_HEAD,
                    "workflowRunUrl": (
                        "https://github.com/jake-the-jake/Closy/actions/runs/33524394054"
                    ),
                    "result": "pass",
                    "authority": "github_workflow_api_and_draft_pr_body",
                },
                {
                    "pullRequest": 50,
                    "committedSourceAnchorSha": UNIT_M_DISJOINT_CONFIRMATION_V2_AUTHORITY_HEAD,
                    "publishedHeadSha": UNIT_M_DISJOINT_CONFIRMATION_V2_PUBLISHED_HEAD,
                    "workflowRunUrl": (
                        "https://github.com/jake-the-jake/Closy/actions/runs/33533707412"
                    ),
                    "result": "pass",
                    "authority": "github_workflow_api_and_draft_pr_body",
                },
                {
                    "pullRequest": 51,
                    "committedSourceAnchorSha": UNIT_N_STRICT_C3_V5_AUTHORITY_HEAD,
                    "publishedHeadSha": UNIT_N_STRICT_C3_V5_PUBLISHED_HEAD,
                    "workflowRunUrl": (
                        "https://github.com/jake-the-jake/Closy/actions/runs/33547909132"
                    ),
                    "result": "pass",
                    "authority": "github_workflow_api_and_draft_pr_body",
                },
            ],
            "pendingExternalExactHeadAttestations": [52],
            "headAuthorityPolicy": (
                "committed_status_describes_immutable_source_anchor;_github_workflow_api_and_"
                "draft_pr_body_attest_final_published_head"
            ),
        },
        "truth": {
            "phase8EvidenceScope": "deterministic_fixture_family_verticals",
            "phases10To14EvidenceScope": (
                "default_all_family_static_pass_parameter_range_partial_compiled_phase11_"
                "pairing_failed_mt1_mechanical_pass_phase12_13_integrated_headless_"
                "phase14_integrated_advisory"
            ),
            "actualZeroOneStaticCookExecutedThisInvocation": True,
            "actualZeroOneStaticArtifactLoaded": True,
            "zeroOneStaticFamilyAttemptCount": 9,
            "zeroOneStaticSuccessfulFamilyCount": 9,
            "zeroOneStaticRejectedFamilyCount": 0,
            "cacheValidated": True,
            "historicalZeroOneStaticCookEvidencePresent": True,
            "actualZeroOneDynamicDeformationExecuted": True,
            "actualZeroOneDynamicPairingAccepted": False,
            "actualZeroOneGpuRuntimeExecuted": False,
            "actualZeroOneMobileRuntimeExecuted": False,
            "actualPhase9TrainingExecuted": True,
            "currentRasterPhase9SourceIntegrated": True,
            "currentRasterPhase9SourcePullRequest": 26,
            "phase12SourceIntegrated": True,
            "phase13SourceIntegrated": True,
            "phase14SourceIntegrated": True,
            "layerCollisionSurfaceIntegrated": True,
            "mt1ReferenceMotionD0Available": True,
            "phy1TopologyV2ExperimentExecuted": True,
            "phy1TopologyV2Passed": False,
            "phy1TopologyV2RuntimeExposed": False,
            "phy1SeamSupportV3NeutralExecuted": True,
            "phy1SeamSupportV3Outcome": "A_neutral_preflight_failed_v3",
            "phy1SeamSupportV3TrajectoryBytesPreserved": True,
            "phy1SeamSupportV3FullSuiteExecuted": False,
            "phy1SeamSupportV3CcdExecuted": False,
            "phy1SeamSupportV3Z2Executed": False,
            "phy1TopologyStrategy2V4Executed": True,
            "phy1TopologyStrategy2V4Outcome": "M_strategy_microfixture_failed_no_candidate",
            "phy1TopologyStrategy2CandidateOpened": False,
            "phy1TopologyStrategy2SolverStepAdvanced": False,
            "phy1TopologyStrategy2CandidateAttemptConsumed": False,
            "phy1TopologyStrategy2RemainingTopologyStrategies": 1,
            "phy1TopologyStrategy2RemainingSeamModels": 0,
            "phy1TopologyStrategy3DiagnosisExecuted": True,
            "phy1TopologyStrategy3DiagnosisOutcome": (
                "no_strategy3_class_admitted_within_bounded_diagnosis"
            ),
            "phy1TopologyStrategy3DiagnosisRevisionCount": 2,
            "phy1TopologyStrategy3AdmittedClass": None,
            "phy1TopologyStrategy3CandidateCreated": False,
            "phy1TopologyStrategy3CandidateAttemptConsumed": False,
            "phy1TopologyStrategy3FinalStrategyConsumed": False,
            "phy1TopologyStrategy3RemainingTopologyStrategies": 1,
            "unitPEligible": False,
            "unitQEligible": False,
            "unitREligible": False,
            "unitJLogicalOutcome": "J-A_post_topology_candidate_unavailable",
            "unitJBranchAuthorized": False,
            "unitKEligible": False,
            "integratedRuntimePinnedToTopologyV1": True,
            "historicalD0ResearchMatrixStatus": "partial_superseded",
            "historicalD0ResearchMatrixVersion": ("closy.final_d0_research_prototype_matrix.v2"),
            "historicalD0ResearchMatrixStatusCounts": {
                "pass": 9,
                "fail": 3,
                "not_run": 3,
            },
            "historicalD0ResearchMatrixFirstUnmetPredicate": "D0-RP-07",
            "currentD0ResearchMatrixStatus": "partial",
            "currentD0ResearchMatrixVersion": "closy.final_d0_research_matrix.v3",
            "currentD0ResearchMatrixCoreStatusCounts": {
                "pass": 7,
                "fail": 4,
                "not_run": 0,
            },
            "currentD0ResearchMatrixSupplementalStatusCounts": {
                "pass": 2,
                "fail": 0,
                "not_run": 2,
            },
            "currentD0ResearchMatrixFirstUnmetPredicate": "D0-RP-03",
            "knownTargetTextureRegressionExecuted": True,
            "knownTargetTextureRegressionOutcome": "known_target_regression_pass",
            "knownTargetTextureRegressionTrialCount": 1,
            "knownTargetTextureRegressionPromotedD0Rp07": False,
            "identityDisjointV2AuthorityExecuted": True,
            "identityDisjointV2Outcome": "attempted_integrity_error",
            "identityDisjointV2AcceptedIdentityCount": 16,
            "identityDisjointV2PredictionCount": 0,
            "identityDisjointV2QualificationRetryAllowed": False,
            "dependencyIdentityGraphAvailable": True,
            "runtimeCandidateV2Available": True,
            "runtimeCandidateV2ProductSelected": False,
            "runtimeCandidateV2FallbackIsCanonicalGarment": True,
            "runtimeCandidateV2DescriptorPayloadCapability": False,
            "boundedRuntimeAndRasterDecompression": True,
            "packageValidityDependsOnZeroOne": False,
            "phase9E1Status": "partial_experimental",
            "phase9E2Status": "executed_feasibility_partial",
            "privateUserEvidenceRun": False,
            "physicalMobileEvidenceRun": False,
            "humanReviewRun": False,
        },
    }


def validate_status_model(
    model: dict[str, Any], coverage: dict[str, Any], stack: dict[str, Any]
) -> list[str]:
    issues: list[str] = []
    rebuilt = build_status_model(
        coverage, stack, evidence_anchor_sha=str(model.get("evidenceAnchorSha", ""))
    )
    if model != rebuilt:
        issues.append("status_model_not_recomputed_from_authority")
    if model.get("phases", {}).get("00") != "complete":
        issues.append("phase_zero_not_complete")
    if any(model.get("phases", {}).get(f"{index:02d}") != "partial" for index in range(1, 15)):
        issues.append("phase_completion_overclaimed")
    status_stack = model.get("stack", {})
    if status_stack.get("committedSourceAnchorExceptions") != [10, 52]:
        issues.append("stack_exception_set_invalid")
    attestations = status_stack.get("externalExactHeadAttestations", [])
    expected_attestations = [
        {
            "pullRequest": 39,
            "committedSourceAnchorSha": PHY1_V2_PUBLICATION_SHA,
            "publishedHeadSha": PHY1_V2_PUBLISHED_EXACT_HEAD,
            "workflowRunUrl": PHY1_V2_EXACT_HEAD_WORKFLOW,
            "result": "pass",
            "authority": "github_workflow_api_and_draft_pr_body",
        },
        {
            "pullRequest": 40,
            "committedSourceAnchorSha": D0_TRUTH_RUNTIME_PUBLICATION_SHA,
            "publishedHeadSha": D0_TRUTH_RUNTIME_PUBLICATION_SHA,
            "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33380042123",
            "result": "pass",
            "authority": "github_workflow_api_and_draft_pr_body",
        },
        {
            "pullRequest": 41,
            "committedSourceAnchorSha": D0_RASTER_IDENTITY_PUBLICATION_SHA,
            "publishedHeadSha": D0_RASTER_IDENTITY_PUBLICATION_SHA,
            "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33393781144",
            "result": "pass",
            "authority": "github_workflow_api_and_draft_pr_body",
        },
        {
            "pullRequest": 42,
            "committedSourceAnchorSha": D0_FITTING_PBR_PUBLICATION_SHA,
            "publishedHeadSha": D0_FITTING_PBR_PUBLICATION_SHA,
            "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33409665461",
            "result": "pass",
            "authority": "github_workflow_api_and_draft_pr_body",
        },
        {
            "pullRequest": 43,
            "committedSourceAnchorSha": PHY1_V3_EVIDENCE_SHA,
            "publishedHeadSha": "6aee5ed3b2753ee99c95abdef6f5a24be39b3a7e",
            "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33423822705",
            "result": "pass",
            "authority": "github_workflow_api_and_draft_pr_body",
        },
        {
            "pullRequest": 44,
            "committedSourceAnchorSha": D0_EVIDENCE_INTEGRITY_V4_SHA,
            "publishedHeadSha": D0_EVIDENCE_INTEGRITY_V4_PUBLISHED_HEAD,
            "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33452856012",
            "result": "pass",
            "authority": "github_workflow_api_and_draft_pr_body",
        },
        {
            "pullRequest": 45,
            "committedSourceAnchorSha": UNIT_F_TEXTURE_RERENDER_V3_SHA,
            "publishedHeadSha": UNIT_F_TEXTURE_RERENDER_V3_PUBLISHED_HEAD,
            "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33464425080",
            "result": "pass",
            "authority": "github_workflow_api_and_draft_pr_body",
        },
        {
            "pullRequest": 46,
            "committedSourceAnchorSha": UNIT_G_DISJOINT_BENCHMARK_V1_SHA,
            "publishedHeadSha": UNIT_G_DISJOINT_BENCHMARK_V1_PUBLISHED_HEAD,
            "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33503777760",
            "result": "pass",
            "authority": "github_workflow_api_and_draft_pr_body",
        },
        {
            "pullRequest": 47,
            "committedSourceAnchorSha": UNIT_H_CORE_RUNTIME_C3_V4_SHA,
            "publishedHeadSha": UNIT_H_CORE_RUNTIME_C3_V4_PUBLISHED_HEAD,
            "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33505903385",
            "result": "pass",
            "authority": "github_workflow_api_and_draft_pr_body",
        },
        {
            "pullRequest": 48,
            "committedSourceAnchorSha": UNIT_I_TOPOLOGY_STRATEGY2_V4_SHA,
            "publishedHeadSha": UNIT_I_TOPOLOGY_STRATEGY2_V4_PUBLISHED_HEAD,
            "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33511517533",
            "result": "pass",
            "authority": "github_workflow_api_and_draft_pr_body",
        },
        {
            "pullRequest": 49,
            "committedSourceAnchorSha": UNIT_L_RECOVERY_FOUNDATION_V1_PUBLISHED_HEAD,
            "publishedHeadSha": UNIT_L_RECOVERY_FOUNDATION_V1_PUBLISHED_HEAD,
            "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33524394054",
            "result": "pass",
            "authority": "github_workflow_api_and_draft_pr_body",
        },
        {
            "pullRequest": 50,
            "committedSourceAnchorSha": UNIT_M_DISJOINT_CONFIRMATION_V2_AUTHORITY_HEAD,
            "publishedHeadSha": UNIT_M_DISJOINT_CONFIRMATION_V2_PUBLISHED_HEAD,
            "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33533707412",
            "result": "pass",
            "authority": "github_workflow_api_and_draft_pr_body",
        },
        {
            "pullRequest": 51,
            "committedSourceAnchorSha": UNIT_N_STRICT_C3_V5_AUTHORITY_HEAD,
            "publishedHeadSha": UNIT_N_STRICT_C3_V5_PUBLISHED_HEAD,
            "workflowRunUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33547909132",
            "result": "pass",
            "authority": "github_workflow_api_and_draft_pr_body",
        },
    ]
    if attestations != expected_attestations:
        issues.append("external_exact_head_attestation_invalid")
    pending_attestations = status_stack.get("pendingExternalExactHeadAttestations", [])
    if pending_attestations != [52]:
        issues.append("pending_external_exact_head_attestation_invalid")
    z1 = model.get("gates", {}).get("Z1", {})
    if z1.get("globalStatus") != "partial" or z1.get("scopedStatus") != (
        "candidate_default_all_family_and_representative_pass"
    ):
        issues.append("zeroone_z1_scope_inflated")
    truth = model.get("truth", {})
    if truth.get("actualZeroOneStaticCookExecutedThisInvocation") is not True:
        issues.append("status_reconciliation_missing_candidate_static_cook")
    if truth.get("actualZeroOneDynamicDeformationExecuted") is not True:
        issues.append("dynamic_execution_missing")
    if truth.get("actualZeroOneDynamicPairingAccepted") is not False:
        issues.append("dynamic_pairing_acceptance_overclaimed")
    if truth.get("mt1ReferenceMotionD0Available") is not True:
        issues.append("mt1_reference_motion_missing")
    if truth.get("phy1TopologyV2ExperimentExecuted") is not True:
        issues.append("phy1_topology_v2_experiment_missing")
    if truth.get("phy1TopologyV2Passed") is not False:
        issues.append("phy1_topology_v2_overclaimed")
    if truth.get("phy1TopologyV2RuntimeExposed") is not False:
        issues.append("phy1_topology_v2_runtime_exposure_overclaimed")
    if truth.get("phy1SeamSupportV3Outcome") != "A_neutral_preflight_failed_v3":
        issues.append("phy1_v3_outcome_missing_or_overclaimed")
    if truth.get("phy1SeamSupportV3FullSuiteExecuted") is not False:
        issues.append("phy1_v3_full_suite_overclaimed")
    if truth.get("phy1SeamSupportV3CcdExecuted") is not False:
        issues.append("phy1_v3_ccd_overclaimed")
    if truth.get("phy1SeamSupportV3Z2Executed") is not False:
        issues.append("phy1_v3_z2_overclaimed")
    if truth.get("phy1TopologyStrategy2V4Outcome") != (
        "M_strategy_microfixture_failed_no_candidate"
    ):
        issues.append("phy1_topology_strategy2_outcome_missing_or_overclaimed")
    if truth.get("phy1TopologyStrategy2CandidateOpened") is not False:
        issues.append("phy1_topology_strategy2_candidate_opened_overclaimed")
    if truth.get("phy1TopologyStrategy2SolverStepAdvanced") is not False:
        issues.append("phy1_topology_strategy2_solver_advanced_overclaimed")
    if truth.get("phy1TopologyStrategy2CandidateAttemptConsumed") is not False:
        issues.append("phy1_topology_strategy2_candidate_attempt_consumption_invalid")
    if truth.get("phy1TopologyStrategy3DiagnosisOutcome") != (
        "no_strategy3_class_admitted_within_bounded_diagnosis"
    ):
        issues.append("phy1_topology_strategy3_diagnosis_outcome_missing_or_overclaimed")
    if truth.get("phy1TopologyStrategy3DiagnosisRevisionCount") != 2:
        issues.append("phy1_topology_strategy3_revision_count_invalid")
    if truth.get("phy1TopologyStrategy3AdmittedClass") is not None:
        issues.append("phy1_topology_strategy3_admission_overclaimed")
    if truth.get("phy1TopologyStrategy3CandidateCreated") is not False:
        issues.append("phy1_topology_strategy3_candidate_overclaimed")
    if truth.get("phy1TopologyStrategy3CandidateAttemptConsumed") is not False:
        issues.append("phy1_topology_strategy3_candidate_attempt_consumption_invalid")
    if truth.get("phy1TopologyStrategy3FinalStrategyConsumed") is not False:
        issues.append("phy1_topology_strategy3_strategy_consumption_invalid")
    if any(
        truth.get(key) is not False for key in ("unitPEligible", "unitQEligible", "unitREligible")
    ):
        issues.append("conditional_unit_eligibility_overclaimed")
    if truth.get("unitJLogicalOutcome") != "J-A_post_topology_candidate_unavailable":
        issues.append("unit_j_logical_closure_missing")
    if truth.get("unitJBranchAuthorized") is not False:
        issues.append("unit_j_branch_authorization_overclaimed")
    if truth.get("unitKEligible") is not False:
        issues.append("unit_k_eligibility_overclaimed")
    if truth.get("integratedRuntimePinnedToTopologyV1") is not True:
        issues.append("integrated_runtime_topology_identity_drift")
    if truth.get("packageValidityDependsOnZeroOne") is not False:
        issues.append("zeroone_made_package_authoritative")
    if truth.get("runtimeCandidateV2ProductSelected") is not False:
        issues.append("runtime_candidate_v2_product_selection_overclaimed")
    if truth.get("runtimeCandidateV2FallbackIsCanonicalGarment") is not True:
        issues.append("runtime_candidate_v2_garment_fallback_missing")
    if truth.get("runtimeCandidateV2DescriptorPayloadCapability") is not False:
        issues.append("runtime_candidate_descriptor_payload_overclaimed")
    if truth.get("actualZeroOneGpuRuntimeExecuted") is not False:
        issues.append("gpu_execution_overclaimed")
    if truth.get("actualZeroOneMobileRuntimeExecuted") is not False:
        issues.append("mobile_execution_overclaimed")
    return issues


def render_status_summary(model: dict[str, Any]) -> str:
    counts = model["coverage"]["counts"]
    phase_lines = "\n".join(
        f"- Phase {int(index)}: `{model['phases'][index]}`" for index in sorted(model["phases"])
    )
    gate_lines = "\n".join(
        f"- {name}: global `{record['globalStatus']}`, scoped `{record['scopedStatus']}`"
        for name, record in sorted(model["gates"].items())
    )
    return (
        "# Generated Blueprint Status\n\n"
        f"Authority: `{model['statusModelVersion']}` at evidence anchor "
        f"`{model['evidenceAnchorSha']}`.\n\n"
        "## Requirement Rows\n\n"
        f"- complete: {counts.get('complete', 0)}\n"
        f"- partial: {counts.get('partial', 0)}\n"
        f"- not started: {counts.get('not_started', 0)}\n"
        f"- discovery pending: {counts.get('discovery_pending', 0)}\n"
        f"- total: {model['coverage']['total']}\n\n"
        "## Phases\n\n"
        f"{phase_lines}\n\n"
        "## Scoped Gates\n\n"
        f"{gate_lines}\n\n"
        "Compute profile, data provenance, execution profile, and gate scope are independent "
        "axes. C3-Binding-D0 passes only for its fixed-avatar D0 T-shirt profile; "
        "PHY1-SingleLayer-D0 and its opt-in topology-v2 experiment both fail their declared "
        "scopes. The exact-candidate seam/support-v3 neutral preflight also fails, so the full "
        "11-state PHY1 replay, CCD, and solver-driven Z2 are not run. Topology v2 remains "
        "opt-in and is not runtime-exposed. Historical matrix v2 is superseded at 9 pass, "
        "3 fail, and 3 not-run. Current matrix v3 reports core 6 pass, 5 fail, and 0 not-run, "
        "first unmet at D0-RP-03, plus supplemental 2 pass and 2 not-run. The separate Unit F "
        "known-target texture replay passes 34 of 34 predicates but does not promote D0-RP-07. "
        "Historical compiled dynamic ZeroOne "
        "pairing failed, while the separate clean analytic MT1 mechanical-reference profile passes "
        "without implying Z2 or physical cloth. Geometric LayerCollision-D0 passes only for the "
        "indexed synthetic two-garment surface profile and does not imply PHY1. "
        "No GPU, mobile, private-user, or human-review execution is claimed.\n"
    )
