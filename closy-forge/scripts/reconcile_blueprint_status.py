from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import cast

from closy_forge.blueprint.ancestry import apply_ancestry_metadata
from closy_forge.blueprint.pr_dag import validate_pr_dag
from closy_forge.blueprint.status import build_status_model, render_status_summary

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ANCHOR = "9078a09f1156ba8b7f98099185478ca9efcee952"
STALE_INVALID_EVIDENCE_ANCHORS = {
    "076cb93c95e0d98052332e52622a15d06c6b6a4e",
}
VERSION = "closy.blueprint_coverage.evidence_authority_recovery_v2.v21"
GENERATOR_VERSION = "closy.blueprint_reconciliation.evidence_authority_recovery_v2.v18"
UNIT_G_FINAL_HEAD = "bc4927fe6d36667b5b236d844b4eff511ef6f987"
UNIT_H_FINAL_HEAD = "e25da69d29eb1b68885b911c7354df085f4a22c0"
UNIT_I_EVIDENCE_HEAD = "854b85ed769bc3e67547e4195f65dfeb78878881"
UNIT_I_FINAL_HEAD = "69f17e0bc0d01472eec3aaf244c158181f74febf"
UNIT_L_FINAL_HEAD = "a72f45955abbe65ce14b7142668447d0477db71c"
UNIT_M_AUTHORITY_HEAD = "9078a09f1156ba8b7f98099185478ca9efcee952"
UNIT_M_FINAL_HEAD = "552867e96d53e9d4c728f90d12e0c1c9a344ba0d"
UNIT_N_AUTHORITY_HEAD = "d7b6e810477f169fea3a3cfca23c5ed99ba603b7"
UNIT_N_FINAL_HEAD = "e062a30ba295ed27334622916ddb449fd76e2166"
UNIT_O_EVIDENCE_HEAD = "d8c8318ad346ea66ebc1956ebc0839ee3d6db109"
UNIT_S_EVIDENCE_HEAD = "6d1b617cbe8bd1f9396a6f860e4368a9fb49ca92"
UNIT_S_PREFLIGHT_HEAD = "1ad839bfbb95dd62117c2cbefbb3e66b4a3a42d7"
UNIT_S_PREFLIGHT_RUN = "33611989613"
PR23_FINAL_RUN = "33150483293"
PR23_FINAL_HEAD = "a481ba26a424bd91607b8c1d41b6173a2c9579d9"
PR23_FINAL_JOB_IDS = {
    "Contracts static Ubuntu Python 3.11": "98781060581",
    "Integration shard-1 Ubuntu Python 3.11": "98781060668",
    "Integration shard-0 Ubuntu Python 3.11": "98781060705",
    "Tests shard-3 windows-latest Python 3.11": "98781060728",
    "Families structured ubuntu-latest Python 3.11": "98781060771",
    "Tests shard-3 ubuntu-latest Python 3.12": "98781060791",
    "Tests shard-0 ubuntu-latest Python 3.12": "98781060896",
    "Families lower ubuntu-latest Python 3.12": "98781060919",
    "Families upper ubuntu-latest Python 3.12": "98781060931",
    "Tests shard-1 ubuntu-latest Python 3.11": "98781060938",
    "Families lower windows-latest Python 3.11": "98781060941",
    "Families lower ubuntu-latest Python 3.11": "98781060947",
    "Families upper windows-latest Python 3.11": "98781060965",
    "Families structured ubuntu-latest Python 3.12": "98781060976",
    "Families upper ubuntu-latest Python 3.11": "98781060978",
    "Tests shard-1 windows-latest Python 3.11": "98781060997",
    "Tests shard-0 ubuntu-latest Python 3.11": "98781061003",
    "Tests shard-2 windows-latest Python 3.11": "98781061014",
    "Families structured windows-latest Python 3.11": "98781061015",
    "Tests shard-1 ubuntu-latest Python 3.12": "98781061022",
    "Tests shard-2 ubuntu-latest Python 3.12": "98781061066",
    "Tests shard-0 windows-latest Python 3.11": "98781061096",
    "Tests shard-2 ubuntu-latest Python 3.11": "98781061187",
    "Tests shard-3 ubuntu-latest Python 3.11": "98781061564",
    "Cross-platform and cross-minor digest consistency": "98782039797",
    "Forge required": "98784926669",
}

FAILED_RUN_JOB_COUNTS = {
    "33203903630": {"successfulJobCount": 21, "failedJobCount": 3, "cancelledJobCount": 2},
    "33275306155": {"successfulJobCount": 24, "failedJobCount": 2, "cancelledJobCount": 0},
}

PR_SNAPSHOTS = [
    (
        24,
        "Forge evidence security and integrity hardening",
        "codex/closy-forge-evidence-security-integrity-v2",
        "codex/closy-forge-phase-10-zeroone-static-integration",
        "a481ba26a424bd91607b8c1d41b6173a2c9579d9",
        "5d080caad354bcecff94a7eadf16d080d68a606c",
        1,
        41,
        "33183367784",
        "SUCCESS",
        "integrated_parent",
    ),
    (
        25,
        "Forge: close scoped C3 binding and harden PHY1 evidence",
        "codex/closy-forge-c3-physical-convergence-v2",
        "codex/closy-forge-evidence-security-integrity-v2",
        "5d080caad354bcecff94a7eadf16d080d68a606c",
        "f9f1ff86089f6b43157431bdd3ccdc83cbc8b974",
        8,
        20,
        "33203903630",
        "FAILURE",
        "superseded_source",
    ),
    (
        26,
        "Forge: add raster-derived synthetic Phase 9 evidence",
        "codex/closy-forge-phase-9-raster-trained-synthetic-d0",
        "codex/closy-forge-evidence-security-integrity-v2",
        "5d080caad354bcecff94a7eadf16d080d68a606c",
        "ba73b310a8609de4eb4f0ed2284c6d2d9a6fab53",
        5,
        27,
        "33201911956",
        "SUCCESS",
        "external_source",
    ),
    (
        27,
        "Forge: refresh all-family candidate ZeroOne evidence",
        "codex/closy-forge-phase-10-zeroone-static-integration-v2",
        "codex/closy-forge-evidence-security-integrity-v2",
        "5d080caad354bcecff94a7eadf16d080d68a606c",
        "2a4fcd8146d95d2fab9a3d39751ffdafd5196387",
        13,
        16,
        "33203908161",
        "SUCCESS",
        "integrated_parent",
    ),
    (
        28,
        "Forge: reconcile C3 and Phase 10 prerequisites",
        "codex/closy-forge-phase11-prerequisite-reconciliation-v2",
        "codex/closy-forge-phase-10-zeroone-static-integration-v2",
        "2a4fcd8146d95d2fab9a3d39751ffdafd5196387",
        "5538d8ca41ad86412d2a2ef5f0a0daa9984c0b72",
        10,
        35,
        "33212147981",
        "SUCCESS",
        "candidate_integration",
    ),
    (
        29,
        "Phase 12 static runtime delivery prep",
        "codex/closy-forge-phase-12-static-runtime-prep",
        "codex/closy-forge-phase-10-zeroone-static-integration-v2",
        "2a4fcd8146d95d2fab9a3d39751ffdafd5196387",
        "62464db2a91e4b24b808cfcd99ee95578fc95f32",
        2,
        12,
        "33216284248",
        "SUCCESS",
        "external_source",
    ),
    (
        30,
        "Phase 13 synthetic avatar fit evidence",
        "codex/closy-forge-phase-13-synthetic-avatar-fit-v2",
        "codex/closy-forge-phase11-prerequisite-reconciliation-v2",
        "5538d8ca41ad86412d2a2ef5f0a0daa9984c0b72",
        "1cf7ecff18bd0bbd37820638c0af2029d7a928ac",
        4,
        11,
        "33222010381",
        "SUCCESS",
        "external_source",
    ),
    (
        31,
        "Forge: add bounded Phase 14 advisory models",
        "codex/closy-forge-phase-14-bounded-models-v2",
        "codex/closy-forge-phase11-prerequisite-reconciliation-v2",
        "5538d8ca41ad86412d2a2ef5f0a0daa9984c0b72",
        "f0a3e3c9b7b1486ebbe736cfb16084299880ce2d",
        2,
        16,
        "33222016267",
        "SUCCESS",
        "external_source",
    ),
    (
        32,
        "Forge: implement LayerCollision-D0 core",
        "codex/closy-forge-layer-collision-d0-v2",
        "codex/closy-forge-phase11-prerequisite-reconciliation-v2",
        "5538d8ca41ad86412d2a2ef5f0a0daa9984c0b72",
        "386effb254d4ba15499399dfd7fd94c70a0e0fc5",
        2,
        10,
        "33222023390",
        "SUCCESS",
        "external_source",
    ),
    (
        33,
        "Repair Z1 garment processing surfaces",
        "codex/closy-forge-z1-surface-topology-repair-v3",
        "codex/closy-forge-phase11-prerequisite-reconciliation-v2",
        "5538d8ca41ad86412d2a2ef5f0a0daa9984c0b72",
        "531689b1d542dd9aeeec29a975e7136ee986c582",
        12,
        43,
        "33264403890",
        "SUCCESS",
        "frozen_integration_base",
    ),
    (
        34,
        "Integrate and audit compiled ZeroOne deformation",
        "codex/closy-forge-phase11-zeroone-dynamic-reference-v1",
        "codex/closy-forge-z1-surface-topology-repair-v3",
        "531689b1d542dd9aeeec29a975e7136ee986c582",
        "960662d237e187cd8ecbcc9ebe9192367f194317",
        11,
        26,
        "33270987449",
        "SUCCESS",
        "failed_dynamic_pairing_source",
    ),
    (
        35,
        "Evaluate bounded structured garment models",
        "codex/closy-forge-learned-structured-garment-v2",
        "codex/closy-forge-z1-surface-topology-repair-v3",
        "531689b1d542dd9aeeec29a975e7136ee986c582",
        "9d39d55e9d1cdae502808f73c4e14653e92d26d7",
        16,
        76,
        "33280862559",
        "SUCCESS",
        "accepted_structured_integration_base",
    ),
    (
        36,
        "Forge: qualify clean ZeroOne mechanical reference motion v2",
        "codex/closy-forge-zeroone-reference-motion-v2",
        "codex/closy-forge-phase11-zeroone-dynamic-reference-v1",
        "960662d237e187cd8ecbcc9ebe9192367f194317",
        "4c5dcd284a1221a7820184e640fb92b67b880787",
        9,
        27,
        "33302649199",
        "SUCCESS",
        "accepted_mt1_mechanical_reference_base",
    ),
    (
        37,
        "Forge: execute corrected structured learning v3",
        "codex/closy-forge-learned-structured-garment-v3",
        "codex/closy-forge-learned-structured-garment-v2",
        "9d39d55e9d1cdae502808f73c4e14653e92d26d7",
        "7430131d5ecab0df77d3933709aed0d86138e03e",
        19,
        41,
        "33321665632",
        "SUCCESS",
        "accepted_structured_learning_v3_source",
    ),
    (
        38,
        "Forge: integrate fail-closed avatar outfit runtime D0",
        "codex/closy-forge-integrated-runtime-avatar-outfit-v2",
        "codex/closy-forge-zeroone-reference-motion-v2",
        "4c5dcd284a1221a7820184e640fb92b67b880787",
        "921ef05b61f39e6020ad12126ffac24c4728f7e0",
        45,
        158,
        "33329481046",
        "SUCCESS",
        "integrated_runtime_avatar_outfit_d0",
    ),
    (
        39,
        "Forge: progress bounded PHY1 topology v2",
        "codex/closy-forge-phy1-topology-v2",
        "codex/closy-forge-integrated-runtime-avatar-outfit-v2",
        "921ef05b61f39e6020ad12126ffac24c4728f7e0",
        "f732df267642cd55960205764e699c7fa2bb2d0f",
        9,
        32,
        "33342673147",
        "SUCCESS",
        "phy1_topology_v2_experiment_only",
    ),
    (
        40,
        "Forge: add executable D0 truth and runtime authority",
        "codex/closy-forge-d0-truth-runtime-authority-v3",
        "codex/closy-forge-phy1-topology-v2",
        "f732df267642cd55960205764e699c7fa2bb2d0f",
        "dbe9b3691b6c7bfc8a8a92ceeb04a7916e34e30a",
        9,
        44,
        "33380042123",
        "SUCCESS",
        "d0_truth_runtime_authority_v3",
    ),
    (
        41,
        "Forge: execute exact D0 raster identity v2",
        "codex/closy-forge-d0-raster-identity-v2",
        "codex/closy-forge-d0-truth-runtime-authority-v3",
        "dbe9b3691b6c7bfc8a8a92ceeb04a7916e34e30a",
        "4b1f4d550cf6e595170f9ef7bd28384c147ca2e8",
        10,
        54,
        "33393781144",
        "SUCCESS",
        "d0_exact_raster_identity_v2",
    ),
    (
        42,
        "Forge: fit and evaluate exact D0 candidate v2",
        "codex/closy-forge-d0-fitting-pbr-fidelity-v2",
        "codex/closy-forge-d0-raster-identity-v2",
        "4b1f4d550cf6e595170f9ef7bd28384c147ca2e8",
        "7922e9b6ece8fca2c3b7dec13299a39de102cbc4",
        9,
        90,
        "33409665461",
        "SUCCESS",
        "d0_fitting_pbr_fidelity_v2",
    ),
    (
        43,
        "Forge: execute preregistered PHY1 seam support v3",
        "codex/closy-forge-phy1-seam-support-v3",
        "codex/closy-forge-d0-fitting-pbr-fidelity-v2",
        "7922e9b6ece8fca2c3b7dec13299a39de102cbc4",
        "6aee5ed3b2753ee99c95abdef6f5a24be39b3a7e",
        8,
        82,
        "33423822705",
        "SUCCESS",
        "phy1_seam_support_v3_neutral_failure",
    ),
    (
        44,
        "Forge: reset D0 evidence integrity and research truth",
        "codex/closy-forge-d0-evidence-integrity-v4",
        "codex/closy-forge-phy1-seam-support-v3",
        "6aee5ed3b2753ee99c95abdef6f5a24be39b3a7e",
        "2f40815010cef01685a7ed873081a22f11d67c00",
        3,
        32,
        "33452856012",
        "SUCCESS",
        "d0_evidence_integrity_v4_truth_reset",
    ),
    (
        45,
        "Forge: execute source-only D0 texture rerender v3",
        "codex/closy-forge-d0-texture-rerender-correction-v3",
        "codex/closy-forge-d0-evidence-integrity-v4",
        "2f40815010cef01685a7ed873081a22f11d67c00",
        "ba54b17a0aef7518d9acac30c6b7ec6564a38d87",
        8,
        82,
        "33464425080",
        "SUCCESS",
        "d0_texture_rerender_correction_v3_known_target",
    ),
    (
        46,
        "Forge: benchmark identity-disjoint T-shirt reconstruction",
        "codex/closy-forge-d0-disjoint-tshirt-benchmark-v1",
        "codex/closy-forge-d0-texture-rerender-correction-v3",
        "ba54b17a0aef7518d9acac30c6b7ec6564a38d87",
        UNIT_G_FINAL_HEAD,
        9,
        62,
        "33503777760",
        "SUCCESS",
        "d0_disjoint_tshirt_benchmark_v1_failed_evaluator_harness",
    ),
    (
        47,
        "Forge: pre-topology reproducibility and strict C3 v4",
        "codex/closy-forge-d0-core-runtime-c3-v4",
        "codex/closy-forge-d0-disjoint-tshirt-benchmark-v1",
        UNIT_G_FINAL_HEAD,
        UNIT_H_FINAL_HEAD,
        6,
        29,
        "33505903385",
        "SUCCESS",
        "d0_core_reproducibility_pass_strict_c3_harness_fail",
    ),
    (
        48,
        "Forge: execute bounded PHY1 topology strategy 2 v4",
        "codex/closy-forge-phy1-topology-strategy2-v4",
        "codex/closy-forge-d0-core-runtime-c3-v4",
        UNIT_H_FINAL_HEAD,
        UNIT_I_FINAL_HEAD,
        7,
        35,
        "33511517533",
        "SUCCESS",
        "phy1_topology_strategy2_outcome_M_logical_J_A",
    ),
    (
        49,
        "Forge: establish D0 recovery foundation v1",
        "codex/closy-forge-d0-recovery-foundation-v1",
        "codex/closy-forge-phy1-topology-strategy2-v4",
        UNIT_I_FINAL_HEAD,
        UNIT_L_FINAL_HEAD,
        1,
        36,
        "33524394054",
        "SUCCESS",
        "d0_recovery_foundation_v1",
    ),
    (
        50,
        "Forge: untouched identity-disjoint T-shirt confirmation v2",
        "codex/closy-forge-d0-disjoint-tshirt-confirmation-v2",
        "codex/closy-forge-d0-recovery-foundation-v1",
        UNIT_L_FINAL_HEAD,
        UNIT_M_FINAL_HEAD,
        4,
        27,
        "33533707412",
        "SUCCESS",
        "d0_disjoint_tshirt_confirmation_v2_integrity_error",
    ),
    (
        51,
        "Forge: strict C3 confirmation v5",
        "codex/closy-forge-d0-strict-c3-confirmation-v5",
        "codex/closy-forge-d0-disjoint-tshirt-confirmation-v2",
        UNIT_M_FINAL_HEAD,
        UNIT_N_FINAL_HEAD,
        3,
        41,
        "33547909132",
        "SUCCESS",
        "d0_strict_c3_confirmation_v5_pass",
    ),
    (
        52,
        "Forge Unit O: bounded PHY1 Strategy 3 diagnosis",
        "codex/closy-forge-phy1-topology-strategy3-diagnosis-v1",
        "codex/closy-forge-d0-strict-c3-confirmation-v5",
        UNIT_N_FINAL_HEAD,
        UNIT_O_EVIDENCE_HEAD,
        1,
        14,
        "",
        "PENDING",
        "phy1_topology_strategy3_diagnosis_integrity_error",
    ),
    (
        53,
        "Forge: evidence authority recovery foundation v2",
        "codex/closy-forge-evidence-authority-recovery-v2",
        "codex/closy-forge-phy1-topology-strategy3-diagnosis-v1",
        "8dd7a547debf038e9e27c48cf8e42009ae69ac3a",
        UNIT_S_EVIDENCE_HEAD,
        11,
        56,
        "",
        "PENDING",
        "evidence_authority_recovery_v2",
    ),
]

PR25_REPLAY_MAPPINGS = [
    ("47e6724df1f2480138645132b489d82332a85d2a", "6f3900d64a8d64db5b92c963f3c74f6405a78525"),
    ("c304f23376ab8d4a18e56eb7bf7380b9a48d8ad0", "5c5c12cf77a228954a660c9d2fcd0048148d5b95"),
    ("aea95a3a15c6e23ab56090a3239842bcd430754a", "5869a137af87dc52fc398180b7dbba15872fd6da"),
    ("9f16cf69e0e8b8fa31ee6ed7940643e1cd70aa2c", "5107b435c1f5440c3adebc1d268cdf5933e2a183"),
    ("67f50c4c590543a40275de33e48fd3412cbcff92", "dee96fe86192e3fee6b63be39456dd383d72825e"),
    ("1a500b1720edeae4a3f28b88a31f7cd14125854b", "816626992bf6bc451521ec5b9f2fdbc68e9ef012"),
    ("37fc2d8e6f4d658bf2b9dd61dae0f43dfbe21362", "0b2b9b729c559785ebd0abc921bb6e6f079a7d9f"),
    ("f9f1ff86089f6b43157431bdd3ccdc83cbc8b974", "f64c4ff2225141aa3fa04405e77fef0af360e050"),
]

PROVENANCE_INPUTS = [
    "closy-forge/scripts/reconcile_blueprint_status.py",
    "closy-forge/src/closy_forge/blueprint/ancestry.py",
    "closy-forge/src/closy_forge/blueprint/pr_dag.py",
    "closy-forge/src/closy_forge/blueprint/profiles.py",
    "closy-forge/src/closy_forge/blueprint/status.py",
    "closy-forge/docs/execution_budget_v3.json",
    "closy-forge/docs/threshold_registry_v1.json",
    "closy-forge/docs/evidence/phase11_prerequisite_reconciliation_v2.json",
    "closy-forge/docs/evidence/phase9_structured_v3/execution_summary.json",
    "closy-forge/docs/evidence/phase9_structured_v3/attestation.json",
    "closy-forge/docs/evidence/phase9_structured_v3/source_replay_map.json",
    "closy-forge/docs/evidence/phy1_progression_v3/sanitised_failure_witness.json",
    "closy-forge/docs/evidence/phase11_reference_motion_v2/execution_evidence.json",
    "closy-forge/docs/evidence/integrated_replay_manifest_d0_v1.json",
    "closy-forge/docs/evidence/integrated_runtime_avatar_outfit_v2.json",
    "closy-forge/docs/evidence/integrated_runtime_invalidation_ledger_d0_v1.json",
    "closy-forge/docs/evidence/canonical_outfit_surface_d0_v1.json",
    "closy-forge/docs/capability-profiles/phy1-single-layer-d0-v2.json",
    "closy-forge/docs/evidence/phy1_topology_v2/phy1_experiment.json",
    "closy-forge/docs/evidence/phy1_topology_v2/invalidation_ledger.json",
    "closy-forge/docs/evidence/phy1_topology_v2/final_d0_research_prototype_matrix.json",
    "closy-forge/src/closy_forge/simulation_topology_v2/evidence.py",
    "closy-forge/scripts/generate_phy1_topology_v2_evidence.py",
    "closy-forge/docs/evidence/d0_exact_raster_identity_v2/evidence_manifest.json",
    "closy-forge/docs/evidence/d0_fitting_pbr_fidelity_v2/evaluation/"
    "final_d0_research_prototype_matrix_v2.json",
    "closy-forge/docs/evidence/phy1_seam_support_v3/neutral_preflight.json",
    "closy-forge/docs/evidence/phy1_seam_support_v3/outcome.json",
    "closy-forge/docs/evidence/phy1_seam_support_v3/evidence_manifest.json",
    "closy-forge/fixtures/phy1_seam_support_v3/experiment_lock.json",
    "closy-forge/src/closy_forge/simulation_topology_v2/seam_support_v3.py",
    "closy-forge/src/closy_forge/simulation_topology_v2/physical_oracles_v3.py",
    "closy-forge/src/closy_forge/simulation_topology_v2/phy1_seam_support_v3.py",
    "closy-forge/scripts/generate_phy1_seam_support_v3_evidence.py",
    "closy-forge/fixtures/d0_texture_rerender_correction_v3/protocol_lock.json",
    "closy-forge/fixtures/d0_texture_rerender_correction_v3/implementation_freeze.json",
    "closy-forge/src/closy_forge/appearance_correction_v3/projection.py",
    "closy-forge/src/closy_forge/appearance_correction_v3/prediction.py",
    "closy-forge/src/closy_forge/appearance_correction_v3/known_target.py",
    "closy-forge/docs/evidence/d0_texture_rerender_correction_v3/predictions/"
    "prediction_summary.json",
    "closy-forge/docs/evidence/d0_texture_rerender_correction_v3/predictions/"
    "source_only_controls.json",
    "closy-forge/docs/evidence/d0_texture_rerender_correction_v3/evaluation/"
    "qualification_summary.json",
    "closy-forge/docs/evidence/d0_texture_rerender_correction_v3/evaluation/"
    "predicate_table.json",
    "closy-forge/docs/evidence/d0_texture_rerender_correction_v3/evaluation/"
    "attempt_registry.json",
    "closy-forge/fixtures/d0_disjoint_tshirt_benchmark_v1/protocol_lock.json",
    "closy-forge/fixtures/d0_disjoint_tshirt_benchmark_v1/development_lock.json",
    "closy-forge/fixtures/d0_disjoint_tshirt_benchmark_v1/evaluator/seed_authority.json",
    "closy-forge/fixtures/d0_disjoint_tshirt_benchmark_v1/evaluator/commitments.json",
    "closy-forge/fixtures/d0_disjoint_tshirt_benchmark_v1/evaluator/prediction_freeze.json",
    "closy-forge/fixtures/d0_disjoint_tshirt_benchmark_v1/evaluator/benchmark_result.json",
    "closy-forge/fixtures/d0_disjoint_tshirt_benchmark_v1/evaluator/"
    "evaluation_attempt_failure.json",
    "closy-forge/fixtures/d0_core_runtime_c3_v4/sentinel_manifest.json",
    "closy-forge/fixtures/d0_core_runtime_c3_v4/protocol_lock.json",
    "closy-forge/src/closy_forge/core_runtime_c3_v4/sentinel.py",
    "closy-forge/src/closy_forge/core_runtime_c3_v4/reproducibility.py",
    "closy-forge/src/closy_forge/core_runtime_c3_v4/oracle.py",
    "closy-forge/src/closy_forge/core_runtime_c3_v4/evaluator.py",
    "closy-forge/docs/evidence/d0_core_runtime_c3_v4/core_reproducibility.json",
    "closy-forge/docs/evidence/d0_core_runtime_c3_v4/strict_c3_result.json",
    "closy-forge/docs/evidence/d0_core_runtime_c3_v4/processor_authority_audit.json",
    "closy-forge/docs/evidence/d0_core_runtime_c3_v4/unit_h_outcome.json",
    "closy-forge/fixtures/phy1_topology_strategy2_v4/budget_classifier.json",
    "closy-forge/fixtures/phy1_topology_strategy2_v4/strategy_lock.json",
    "closy-forge/src/closy_forge/phy1_topology_strategy2_v4/budget.py",
    "closy-forge/src/closy_forge/phy1_topology_strategy2_v4/diagnosis.py",
    "closy-forge/src/closy_forge/phy1_topology_strategy2_v4/strategy.py",
    "closy-forge/src/closy_forge/phy1_topology_strategy2_v4/evidence.py",
    "closy-forge/scripts/freeze_phy1_topology_strategy2_v4_budget.py",
    "closy-forge/scripts/diagnose_phy1_topology_strategy2_v4.py",
    "closy-forge/scripts/lock_phy1_topology_strategy2_v4.py",
    "closy-forge/scripts/validate_phy1_topology_strategy2_v4_evidence.py",
    "closy-forge/docs/evidence/phy1_topology_strategy2_v4/diagnosis.json",
    "closy-forge/docs/evidence/phy1_topology_strategy2_v4/general_microfixtures.json",
    "closy-forge/docs/evidence/phy1_topology_strategy2_v4/strategy_microfixtures.json",
    "closy-forge/docs/evidence/phy1_topology_strategy2_v4/physical_attempt_registry.json",
    "closy-forge/docs/evidence/phy1_topology_strategy2_v4/unit_i_outcome.json",
    "closy-forge/docs/evidence/phy1_topology_strategy2_v4/logical_j_a_closure.json",
    "closy-forge/docs/evidence/phy1_topology_strategy2_v4/evidence_manifest.json",
    "closy-forge/fixtures/d0_disjoint_tshirt_confirmation_v2/authority_lifecycle.json",
    "closy-forge/fixtures/d0_disjoint_tshirt_confirmation_v2/official_attempt_failure.json",
    "closy-forge/src/closy_forge/recovery_foundation_v1/contracts.py",
    "closy-forge/src/closy_forge/recovery_foundation_v1/evaluator_v2.py",
    "closy-forge/src/closy_forge/recovery_foundation_v1/contestant_boundary.py",
    "closy-forge/src/closy_forge/recovery_foundation_v1/c3_v5.py",
    "closy-forge/src/closy_forge/recovery_foundation_v1/sentinel.py",
    "closy-forge/docs/evidence/d0_recovery_foundation_v1/publication_truth.json",
    "closy-forge/docs/evidence/d0_recovery_foundation_v1/result_semantics.json",
    "closy-forge/docs/evidence/d0_recovery_foundation_v1/physical_budget_authority.json",
    "closy-forge/docs/evidence/d0_recovery_foundation_v1/unit_l_outcome.json",
    "closy-forge/fixtures/d0_strict_c3_confirmation_v5/protocol_lock.json",
    "closy-forge/fixtures/d0_strict_c3_confirmation_v5/authority_lifecycle.json",
    "closy-forge/docs/evidence/d0_strict_c3_confirmation_v5/strict_c3_result.json",
    "closy-forge/docs/evidence/d0_strict_c3_confirmation_v5/outcome_report.json",
    "closy-forge/fixtures/phy1_topology_strategy3_diagnosis_v1/diagnosis_lock.json",
    "closy-forge/fixtures/phy1_topology_strategy3_diagnosis_v1/confirmation_generator_lock.json",
    "closy-forge/docs/evidence/phy1_topology_strategy3_diagnosis_v1/starting_authority.json",
    "closy-forge/docs/evidence/phy1_topology_strategy3_diagnosis_v1/unit_o_outcome.json",
    "closy-forge/docs/evidence/phy1_topology_strategy3_diagnosis_v1/integrity_attestation.json",
    "closy-forge/src/closy_forge/phy1_topology_strategy3_diagnosis_v1/" "integrity_attestation.py",
]

PHASE10_PATHS = [
    "closy-forge/src/closy_forge/zeroone/integration.py",
    "closy-forge/src/closy_forge/zeroone/request.py",
    "closy-forge/src/closy_forge/zeroone/tool.py",
    "closy-forge/src/closy_forge/zeroone/validation.py",
    "closy-forge/src/closy_forge/zeroone/derivative_inspection.py",
    "closy-forge/docs/evidence/phase10_zeroone_static/execution_evidence.json",
]
PHASE10_TESTS = [
    "closy-forge/tests/unit/test_zeroone_static_integration.py",
    "closy-forge/tests/unit/test_zeroone_execution_evidence.py",
]
PHASE10_EVIDENCE = [
    (
        "the durable candidate ZeroOneProcess Release executable attempted all nine declared "
        "canonical D0 garment families headlessly"
    ),
    (
        "six families produced validated mesh, cluster, hierarchy, page-pack, material, and "
        "garment semantic derivatives"
    ),
    (
        "long-sleeved top, button shirt, and jacket were rejected fail-closed for exact "
        "degenerate-surface diagnostics"
    ),
    (
        "successful namespaces pass cache, deletion/rebuild, independent derivative inspection, "
        "canonical-authority preservation, and conventional-fallback preservation"
    ),
    (
        "exact execution records clean Closy and ZeroOne SHAs, executable hash, commands, "
        "wall/CPU timings, peak memory, input/output hashes, and remaining blockers"
    ),
]
ROW_UPDATES = {
    "BP-05-04-ZEROONE-OPTIONAL": {
        "summary": (
            "ZeroOne remains optional, derived, regenerable, and validated without changing "
            "canonical package authority."
        ),
        "limitations": (
            "All nine families were attempted, but three structured families were rejected for "
            "degenerate surfaces; every conventional GLB fallback remains mandatory."
        ),
    },
    "BP-08-I-GEOMETRY-PROVIDERS": {
        "status": "partial",
        "summary": (
            "The pinned task-owned ZeroOne provider now produces validated optional static "
            "derivatives from canonical packages."
        ),
        "limitations": (
            "Six of nine D0 families passed on one Windows CPU/static toolchain; three structured "
            "families, visual review, mobile, and dynamic tiers remain open."
        ),
    },
    "BP-09-Z1": {
        "status": "partial",
        "summary": (
            "The refreshed candidate ZeroOne pairing attempted all nine families; six passed and "
            "three were rejected, so the candidate all-family scoped Z1 result is failed."
        ),
        "limitations": (
            "The durable ZeroOne candidate is unmerged, the paired Closy run is local, and "
            "long-sleeved top, button shirt, and jacket contain rejected degenerate surfaces."
        ),
        "nextAction": (
            "Repair the three canonical surfaces without changing authority, rebuild ZeroOne, "
            "and rerun the paired all-family profile."
        ),
    },
    "BP-09-GEOMOTREE": {
        "status": "partial",
        "summary": (
            "A real bounded GeomoTree/Nanite CPU static route publishes validated optional "
            "derivatives for six of nine declared garment families."
        ),
        "limitations": (
            "Three structured surfaces are rejected; dynamic deformation, mobile execution, and "
            "human review are not established."
        ),
    },
    "BP-12-MODEL-STRATEGY": {
        "status": "partial",
        "summary": (
            "The model strategy now includes an actually trained synthetic D0 grammar model and "
            "a pinned real ZeroOne static processor with deterministic rollback paths."
        ),
        "limitations": (
            "No authorised real/public capture evaluation, learned superiority, mobile provider "
            "execution, or dynamic ZeroOne profile exists."
        ),
    },
    "BP-14-EVALUATION": {
        "status": "partial",
        "summary": (
            "Evaluation now consumes a scoped C3 binding pass, a separate PHY1 failure, trained "
            "synthetic D0 evidence, and an all-family paired ZeroOne failure."
        ),
        "limitations": (
            "PHY1 and paired Z1 fail; independent real/public, provider, mobile, private-user, "
            "licence, and human-review evidence remains incomplete."
        ),
    },
    "BP-17-PHASE-10": {
        "status": "partial",
        "summary": (
            "Blueprint Phase 10 now records nine valid default-family derivatives and a passing "
            "fixed T-shirt representative on the exact candidate ZeroOne executable."
        ),
        "limitations": (
            "The original affected-family parameter range remains partial; human review, current-"
            "master requalification, mobile execution, and dynamic profiles also remain open."
        ),
        "nextAction": (
            "Preserve the scoped static pass and begin compiled ZeroOne B without promoting the "
            "partial original parameter range."
        ),
    },
    "BP-18-GATE-Z1": {
        "status": "partial",
        "summary": (
            "Candidate default-family breadth and the exact representative static profile pass; "
            "global Z1 remains partial."
        ),
        "limitations": (
            "Current ZeroOne master, durable workflow execution, mobile, dynamic deformation, "
            "provider breadth, and human review are not established."
        ),
        "nextAction": "Build compiled ZeroOne B while retaining current-master and range limits.",
    },
    "BP-18-GATE-C3": {
        "status": "complete",
        "summary": (
            "C3-Binding-D0 passes its literal five-part fixed-avatar D0 T-shirt profile across "
            "all 11 binding states with exact persisted lineage and frame validation."
        ),
        "limitations": (
            "This is a scoped binding pass only. PHY1 fails and broader avatars, garments, mobile, "
            "private-user, and production profiles remain unproven."
        ),
        "nextAction": "Preserve the scoped pass while repairing paired Z1 and PHY1 separately.",
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "The research prototype now includes corrected integrity evidence, a trained "
            "synthetic D0 model, and real optional ZeroOne CPU/static derivatives."
        ),
        "limitations": (
            "Paired Z1, PHY1, independent fidelity, mobile, broader provider, private-user, "
            "licence, and human-review gates remain open; Alpha is not reached."
        ),
    },
}
ROW_EVIDENCE_ADDITIONS = {
    "BP-05-04-ZEROONE-OPTIONAL": True,
    "BP-08-I-GEOMETRY-PROVIDERS": True,
    "BP-09-Z1": True,
    "BP-09-GEOMOTREE": True,
    "BP-12-MODEL-STRATEGY": True,
    "BP-14-EVALUATION": True,
    "BP-17-PHASE-10": True,
    "BP-18-GATE-Z1": True,
    "BP-18-GATE-C3": True,
    "BP-20-RESEARCH-PROTOTYPE": True,
}

ANCESTRY_TRUTH_UPDATES = {
    "BP-08-H-PATTERN-INFERENCE": {
        "summary": (
            "Current raster-trained Phase 9 evidence exists on independent source PR #26; its "
            "53/64 held-out top-1 result is not integrated into PR #28."
        ),
        "limitations": (
            "The source experiment trails its equal-input centroid baseline, has 0/14 correct OOD "
            "actions, uses template builders, and is external until replayed and repaired."
        ),
    },
    "BP-17-PHASE-09": {
        "summary": (
            "Phase 9 is external-source partial at PR #26 with 53/64 held-out top-1 and 37/64 "
            "accepted predictions; it is not present in the PR #28 source tree."
        ),
        "limitations": (
            "E1 remains partial, E2 is not run, OOD action accuracy is 0/14, and no learned "
            "superiority or integrated Phase 9 claim is supported."
        ),
        "nextAction": (
            "Replay PR #26 on Closy E, remove oracle fallback, and rerun frozen E1/E2 profiles."
        ),
    },
    "BP-17-PHASE-11": {
        "summary": "Phase 11 remains partial with no compiled dynamic ZeroOne execution.",
        "limitations": (
            "C3-Binding-D0 and Z1-D0-representative-static pass for the exact fixed T-shirt; "
            "compiled dynamic execution remains absent."
        ),
        "nextAction": "Build compiled ZeroOne B and pair the exact representative asset.",
    },
    "BP-17-PHASE-12": {
        "summary": "Phase 12 runtime preparation is external-source partial on PR #29.",
        "limitations": (
            "PR #29 is not in PR #28 ancestry and has no Z2, device, battery, thermal, cellular, "
            "driver, or production evidence."
        ),
    },
    "BP-17-PHASE-13": {
        "summary": (
            "Phase 13 synthetic avatar-fit work is external-source partial on PR #30; the radial "
            "LayerCollision-D0 source on PR #32 is also external and not garment-surface proof."
        ),
        "limitations": (
            "No integrated dynamic lineage, canonical garment-surface outfit, licensed body, "
            "private user, P1, or human correction evidence exists."
        ),
    },
    "BP-17-PHASE-14": {
        "summary": "Phase 14 bounded advisory models are external-source partial on PR #31.",
        "limitations": (
            "The advisory source is not integrated, remains validator-subordinate, and includes no "
            "structured generator, private data, real fabric, or production claim."
        ),
    },
    "BP-18-GATE-Z1": {
        "summary": (
            "Candidate-static default breadth accepts all nine families, and the exact fixed "
            "T-shirt representative profile passes with paired C3-Binding-D0."
        ),
        "limitations": (
            "The original affected-family parameter range remains partial, the candidate-static "
            "ZeroOne source is unmerged, and no current-master, dynamic, mobile, or human-review "
            "claim is supported."
        ),
        "nextAction": (
            "Preserve the scoped static evidence while building compiled ZeroOne B; do not promote "
            "the partial original parameter range."
        ),
    },
    "BP-18-GATE-Z2": {
        "summary": "Gate Z2 is not run; C3-Binding-D0 is no longer an unsatisfied blocker.",
        "limitations": "Compiled dynamic execution is not yet established.",
        "nextAction": "Build and execute compiled ZeroOne B against the frozen representative.",
    },
}

CURRENT_PROGRESSION_UPDATES = {
    "BP-08-S-LAYERING-ANIMATION": {
        "status": "partial",
        "summary": (
            "PR #38 executes simultaneous geometric projection on indexed inner-top and outer-"
            "overshirt surfaces fitted to the exact synthetic avatar authority."
        ),
        "limitations": (
            "The D0 result is geometric LayerCollision evidence only; it is not solver-driven "
            "cloth, PHY1, mobile, private-user, or production evidence."
        ),
        "nextAction": (
            "Keep the surface profile identity-bound and consume topology-v2 only after its "
            "seams, openings, bindings, and physical profile are independently requalified."
        ),
    },
    "BP-08-H-PATTERN-INFERENCE": {
        "status": "partial",
        "summary": (
            "Phase 9 v3 executes a 512-program, 8,192-image reference-assembly corpus, a nonlinear "
            "E1 route, and a genuine factorized compositional E2 decoder without oracle fallback."
        ),
        "limitations": (
            "E1 raw macro top-1 is 0.171875 versus 0.9765625 for nearest-neighbour retrieval and "
            "accepts 0/128 tests. E2 true token macro-F1 is 0.535520366, compiles and renders "
            "96/96 proposals, but its baseline lower 95% is -0.028125 and the gate fails 10 checks."
        ),
        "nextAction": (
            "Keep deterministic retrieval selected; obtain broader lawful identity-disjoint data "
            "before another bounded learned configuration."
        ),
    },
    "BP-08-Q-MATERIAL-INFERENCE": {
        "status": "partial",
        "summary": (
            "Phase 14 v3 fixes the ablation status filter, scenario-cluster bootstrap and "
            "normalized selection-regret reporting while keeping model authority advisory."
        ),
        "limitations": (
            "Material top-1 is 10/18, normalized regret mean/P95/worst is "
            "0.100424120738/1.0/1.0, and excessive-strain and seam-risk F1 are both 0.4. The "
            "authored scalar corpus is not solver-backed, real-fabric, private-user or production "
            "evidence."
        ),
    },
    "BP-09-Z2": {
        "status": "partial",
        "summary": (
            "The historical solver-derived Z2 v1 pairing remains failed. A separate clean "
            "analytic MT1 mechanical-reference profile now passes and is available only in its "
            "identity-matched lab namespace."
        ),
        "limitations": (
            "MT1 is not blueprint Gate Z2 and supplies no PHY1 or solver-driven cloth claim. The "
            "historical Z2 oracle still records 929 to 971 nonadjacent intersections per frame; "
            "multi-LOD, GPU, and mobile profiles were not run."
        ),
        "nextAction": (
            "Repair the processing/reference surface correspondence before another bounded "
            "pairing strategy; do not promote the compiled-output hash alone."
        ),
    },
    "BP-17-PHASE-09": {
        "status": "partial",
        "summary": (
            "Phase 9 v3 has corrected policy-matched E1 and a 256/64/96 compositional E2 attempt "
            "whose every test proposal executes compile, topology and reference-3D evaluation."
        ),
        "limitations": (
            "E1 is a losing experiment; E2 fails 10/17 frozen checks and its bootstrap lower 95% "
            "misses the -0.02 floor. No learned route is default and no private, human or "
            "real-photo claim exists."
        ),
        "nextAction": (
            "Retain both learned routes as experimental and broaden only with authorised, "
            "identity-disjoint evidence and precommitted comparisons."
        ),
    },
    "BP-17-PHASE-11": {
        "status": "partial",
        "summary": (
            "Phase 11 retains the authentic historical Z2 pairing failure and now adds a clean, "
            "compiled, exact-identity MT1 analytic mechanical-reference capability."
        ),
        "limitations": (
            "MT1 is lab mechanical transport, not solver-driven cloth. Blueprint Z2 remains "
            "unaccepted, PHY1 remains failed, and no mobile or product claim follows."
        ),
        "nextAction": (
            "Use topology-v2 to attempt PHY1 independently; create a cloth-driven Z2 profile only "
            "if a solver-driven clip later passes PHY1 and the independent dynamic oracle."
        ),
    },
    "BP-17-PHASE-12": {
        "status": "partial",
        "summary": (
            "Phase 12 source work is integrated in PR #38 as a deterministic headless runtime "
            "package with schema negotiation, conventional fallback, and fail-closed optional "
            "ZeroOne capability selection."
        ),
        "limitations": (
            "Execution is host CPU reference evidence only; device, GPU, battery, thermal, "
            "cellular, driver, and production deployment evidence are not run."
        ),
        "nextAction": (
            "Preserve package validity independent of ZeroOne and obtain real mobile runtime "
            "measurements only after the canonical capability set is stable."
        ),
    },
    "BP-17-PHASE-13": {
        "status": "partial",
        "summary": (
            "Phase 13 synthetic-avatar fitting and a canonical indexed two-garment outfit surface "
            "are integrated in PR #38 with exact authority and fit identities."
        ),
        "limitations": (
            "The avatar is project-authored synthetic and the outfit correction is geometric; no "
            "licensed body, private user, human correction, physical cloth, or P1 evidence exists."
        ),
        "nextAction": (
            "Retain synthetic authority separation while evaluating topology-v2 physical behavior "
            "and later lawful licensed/private cohorts under explicit consent."
        ),
    },
    "BP-17-PHASE-14": {
        "status": "partial",
        "summary": (
            "Phase 14 v3 reevaluates the bounded advisory model with non-null scenario/material "
            "ablations and scenario-cluster confidence intervals."
        ),
        "limitations": (
            "Only 4/10 frozen checks pass; low per-target F1 remains visible, the solver-backed "
            "replacement corpus is dependency-blocked, and no large-model, real-fabric or "
            "production run occurred."
        ),
        "nextAction": (
            "Obtain authorised data, checkpoint, licence, hardware, privacy, and deployment "
            "governance before any larger model experiment."
        ),
    },
    "BP-18-GATE-Z2": {
        "status": "partial",
        "summary": (
            "Historical Gate Z2 v1 remains failed; the newer MT1 analytic mechanical-reference "
            "profile passes its separate scoped transport gate and is not relabelled Z2."
        ),
        "limitations": (
            "No accepted solver-driven cloth namespace exists. Multi-LOD cloth, PHY1, GPU, mobile, "
            "private-user, and production claims remain unsupported."
        ),
        "nextAction": (
            "Run topology-v2 PHY1 first; only a valid solver-driven clip may enter a new, "
            "versioned Z2-ClothDriven profile."
        ),
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "The research prototype now includes 9/9 default-family static evidence, a scoped MT1 "
            "mechanical pass, integrated fail-closed headless runtime and synthetic-avatar outfit "
            "surfaces, plus the bounded Phase 9/14 experiments."
        ),
        "limitations": (
            "Z2 and PHY1 remain failed, and Alpha, Beta, Production, human, "
            "private, licensed-body, real-fabric, GPU, and mobile evidence remain unproven."
        ),
    },
}

CURRENT_EVIDENCE_ADDITIONS = {
    "BP-08-S-LAYERING-ANIMATION": {
        "implementationPaths": [
            "closy-forge/src/closy_forge/integrated_runtime/outfit_surface.py",
            "closy-forge/docs/evidence/canonical_outfit_surface_d0_v1.json",
        ],
        "executableEvidence": [
            "indexed 128-vertex/192-triangle garment surfaces progress from 256 to zero exact "
            "triangle intersections while preserving seams and openings",
            "final semantic clearance is 0.002 m with zero contacts and ordering inversions",
        ],
        "tests": [
            "closy-forge/tests/unit/test_integrated_runtime_d0.py",
            "closy-forge/tests/unit/test_integrated_runtime_evidence_v2.py",
        ],
    },
    "BP-08-H-PATTERN-INFERENCE": {
        "implementationPaths": [
            "closy-forge/src/closy_forge/pattern_inference/multiview_corpus_v5.py",
            "closy-forge/src/closy_forge/pattern_inference/e1_kernel_v3.py",
            "closy-forge/src/closy_forge/pattern_inference/e1_evaluation_v5.py",
            "closy-forge/src/closy_forge/pattern_inference/reference_3d_v1.py",
            "closy-forge/src/closy_forge/pattern_inference/typed_program_v2.py",
            "closy-forge/src/closy_forge/pattern_inference/structured_decoder_v2.py",
        ],
        "executableEvidence": [
            (
                "E1 full run covers 512 programs, 2,048 capture sets and 8,192 decoded "
                "reference-assembly images; its losing 0.171875 macro top-1 remains non-default"
            ),
            (
                "E2 trains atomic grammar heads over 256/64/96 programs and executes all 96 "
                "held-out proposals through compile, topology and reference-3D"
            ),
        ],
        "tests": [
            "closy-forge/tests/unit/test_multiview_corpus_v5.py",
            "closy-forge/tests/unit/test_e1_kernel_v3.py",
            "closy-forge/tests/unit/test_typed_program_v2.py",
            "closy-forge/tests/unit/test_structured_decoder_v2.py",
        ],
    },
    "BP-08-Q-MATERIAL-INFERENCE": {
        "implementationPaths": [
            "closy-forge/src/closy_forge/bounded_models/integrated_evaluation_v3.py"
        ],
        "executableEvidence": [
            "Phase 14 v3 records 10/18 material top-1, scenario-cluster bootstrap, and two "
            "non-null ablations"
        ],
        "tests": ["closy-forge/tests/unit/test_phase14_integrated_evaluation_v3.py"],
    },
    "BP-09-Z2": {
        "implementationPaths": [
            "closy-forge/src/closy_forge/zeroone/dynamic_integration.py",
            "closy-forge/src/closy_forge/zeroone/dynamic_oracle.py",
        ],
        "executableEvidence": [
            "compiled output hash 097f1f9c2621870dd460b0a5bc4374cf6212a59e5b282da00a207133864f5847",
            (
                "independent dense oracle rejects every frame with 929 to 971 nonadjacent "
                "self-intersections"
            ),
            (
                "separate MT1 request 38fadbc2... and output 996b50ed... pass clean analytic "
                "mechanical transport without claiming Z2 or PHY1"
            ),
        ],
        "tests": ["closy-forge/tests/unit/test_zeroone_dynamic_reference.py"],
    },
    "BP-17-PHASE-09": {
        "implementationPaths": [
            "closy-forge/src/closy_forge/pattern_inference/e1_evaluation_v5.py",
            "closy-forge/src/closy_forge/pattern_inference/structured_decoder_v2.py",
            "closy-forge/docs/evidence/phase9_structured_v3/execution_summary.json",
        ],
        "executableEvidence": [
            "E1 is a policy-correct losing experiment with no oracle fallback",
            "E2 parses, compiles, validates topology and renders 96/96 held-out typed proposals",
        ],
        "tests": ["closy-forge/tests/unit/test_phase9_structured_v3_evidence.py"],
    },
    "BP-17-PHASE-11": {
        "implementationPaths": [
            "closy-forge/docs/evidence/phase11_dynamic_reference/r3_compiled_pairing_failure.json",
            "closy-forge/docs/evidence/phase11_reference_motion_v2/execution_evidence.json",
            "closy-forge/src/closy_forge/integrated_runtime/decision.py",
        ],
        "executableEvidence": [
            (
                "13 compiled frames have zero position/rest error and zero culling false "
                "negatives but fail dense self-intersection"
            ),
            "clean analytic MT1 passes its bounded mechanical-reference transport profile",
        ],
        "tests": [
            "closy-forge/tests/unit/test_zeroone_dynamic_reference.py",
            "closy-forge/tests/unit/test_zeroone_reference_motion_evidence_v2.py",
            "closy-forge/tests/unit/test_integrated_runtime_d0.py",
        ],
    },
    "BP-17-PHASE-12": {
        "implementationPaths": [
            "closy-forge/src/closy_forge/integrated_runtime/contracts.py",
            "closy-forge/src/closy_forge/integrated_runtime/decision.py",
            "closy-forge/src/closy_forge/runtime_delivery/package.py",
            "closy-forge/docs/evidence/integrated_runtime_avatar_outfit_v2.json",
        ],
        "executableEvidence": [
            "conventional package loads without ZeroOne and stale, corrupt, unsupported optional "
            "capabilities fail closed",
            "host CPU latency and memory observations are explicitly advisory and not mobile "
            "evidence",
        ],
        "tests": [
            "closy-forge/tests/unit/test_integrated_runtime_d0.py",
            "closy-forge/tests/unit/test_integrated_runtime_evidence_v2.py",
        ],
    },
    "BP-17-PHASE-13": {
        "implementationPaths": [
            "closy-forge/src/closy_forge/avatar_variation/synthetic_suite.py",
            "closy-forge/src/closy_forge/integrated_runtime/outfit_surface.py",
            "closy-forge/docs/evidence/canonical_outfit_surface_d0_v1.json",
        ],
        "executableEvidence": [
            "exact project-authored synthetic avatar authority and fit identities are enforced",
            "canonical two-garment indexed surfaces finish with zero geometric contacts, "
            "intersections, and ordering inversions",
        ],
        "tests": [
            "closy-forge/tests/unit/test_avatar_variation_fit.py",
            "closy-forge/tests/unit/test_integrated_runtime_d0.py",
        ],
    },
    "BP-17-PHASE-14": {
        "implementationPaths": [
            "closy-forge/src/closy_forge/bounded_models/integrated_evaluation_v3.py",
            "closy-forge/docs/evidence/phase9_structured_v3/phase14_integrated_evaluation.json",
        ],
        "executableEvidence": [
            (
                "Phase 14 v3 reports normalized regret mean/P95/worst "
                "0.100424120738/1.0/1.0 and failure macro-F1 0.704125286478"
            )
        ],
        "tests": [
            "closy-forge/tests/unit/test_phase14_bounded_models.py",
            "closy-forge/tests/unit/test_phase14_integrated_evaluation_v3.py",
        ],
    },
    "BP-18-GATE-Z2": {
        "implementationPaths": [
            "closy-forge/docs/evidence/phase11_dynamic_reference/r3_compiled_pairing_failure.json"
        ],
        "executableEvidence": [
            (
                "authenticated ZeroOne workflow artifact "
                "e704a0f2196f066f7aab16669356ee7de97f59b89de5cf51cbb2f529526457dc "
                "executed and failed admission"
            )
        ],
        "tests": ["closy-forge/tests/unit/test_zeroone_dynamic_reference.py"],
    },
}

PHY1_V2_PROGRESSION_UPDATES = {
    "BP-08-N-GARMENT-RETOPOLOGY": {
        "status": "partial",
        "summary": (
            "An opt-in deterministic interior-constrained topology v2 preserves exact panel "
            "boundaries and semantics while adding quality-bounded interior vertices."
        ),
        "limitations": (
            "The topology is physical-experiment-only. It is not selected by packages, runtime "
            "capabilities, ZeroOne derivatives, C3, or MT1."
        ),
        "nextAction": (
            "Keep v2 isolated until a later bounded coupled-convergence strategy passes all "
            "frozen PHY1 requirements."
        ),
    },
    "BP-14-EVALUATION": {
        "status": "partial",
        "summary": (
            "Evaluation now includes a deterministic 11-state topology-v2 replay, separate "
            "simulation/render clearance, and the final fixed-row D0 research matrix."
        ),
        "limitations": (
            "PHY1-v2 passes temporal integrity but fails contact, clearance, seam, strain, "
            "support, energy, and convergence; six research-matrix rows remain not run."
        ),
        "nextAction": (
            "Close exact decoded-raster lineage first, independently of the failed physical lane."
        ),
    },
    "BP-17-PHASE-06": {
        "status": "partial",
        "summary": (
            "Topology v2 removes all qualified temporal degeneracy in the frozen 11-state replay "
            "without changing v1 runtime identities."
        ),
        "limitations": (
            "Zero of 11 physical states pass; maximum residual depth is 0.002399077 m, simulation "
            "clearance is -0.014360829 m, and render clearance is -0.064466621 m."
        ),
        "nextAction": (
            "Attempt one later versioned coupled-convergence strategy with joint residual traces; "
            "CCD remains ineligible."
        ),
    },
    "BP-17-PHASE-11": {
        "status": "partial",
        "summary": (
            "The clean analytic MT1 mechanical-reference pass remains available; topology-v2 "
            "produces no solver-driven cloth clip because PHY1-v2 fails."
        ),
        "limitations": (
            "No Z2-ClothDriven namespace, integrated CCD, or physical runtime capability is "
            "created."
        ),
        "nextAction": (
            "Do not revisit solver-driven Z2 until a future PHY1 profile passes every frozen gate."
        ),
    },
    "BP-18-GATE-Z2": {
        "status": "partial",
        "summary": (
            "Historical Z2 remains failed and topology-v2 does not create a replacement; MT1 "
            "continues as a separate clean mechanical-reference capability."
        ),
        "limitations": (
            "PHY1-v2 fails 0/11 states, so integrated CCD and a solver-driven Z2 profile are "
            "ineligible."
        ),
        "nextAction": "Preserve the failed gate until a valid solver-driven cloth clip exists.",
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "The final fixed-avatar T-shirt D0 matrix records 8 passing and 6 not-run components "
            "with exact package, executable, C3, Z1, MT1, and fallback identities."
        ),
        "limitations": (
            "The first unmet requirement is exact-row decoded front/rear raster ingestion and "
            "source identity; no human, private, device, or physical claim is promoted."
        ),
        "nextAction": (
            "Close the exact D0 decoded-raster and independent rerender rows before widening scope."
        ),
    },
}

PHY1_V2_EVIDENCE_ADDITIONS = {
    row_id: {
        "implementationPaths": [
            "closy-forge/src/closy_forge/simulation_topology_v2/triangulator.py",
            "closy-forge/src/closy_forge/simulation_topology_v2/seam_junctions.py",
            "closy-forge/src/closy_forge/simulation_topology_v2/binding.py",
            "closy-forge/src/closy_forge/simulation_topology_v2/temporal_quality.py",
            "closy-forge/src/closy_forge/simulation_topology_v2/phy1_experiment.py",
            "closy-forge/docs/evidence/phy1_topology_v2/phy1_experiment.json",
        ],
        "executableEvidence": [
            (
                "all 11 frozen states execute with zero temporal degenerates, swept collapses, "
                "and true inversions but zero states pass the complete physical profile"
            ),
            (
                "the invalidation ledger proves all integrated D runtime capabilities remain "
                "pinned to unchanged topology-v1 identities"
            ),
        ],
        "tests": [
            "closy-forge/tests/unit/test_simulation_topology_v2.py",
            "closy-forge/tests/unit/test_topology_v2_seams_binding.py",
            "closy-forge/tests/unit/test_topology_v2_temporal_quality.py",
            "closy-forge/tests/unit/test_phy1_topology_v2_experiment.py",
            "closy-forge/tests/unit/test_phy1_topology_v2_evidence.py",
        ],
    }
    for row_id in PHY1_V2_PROGRESSION_UPDATES
}

TRUTH_RUNTIME_PROGRESSION_UPDATES = {
    "BP-14-EVALUATION": {
        "status": "partial",
        "summary": (
            "The versioned D0 matrix now derives every result from opened, hashed evidence and "
            "exact selected-identity predicates; it records 8 pass and 7 not-run rows."
        ),
        "limitations": (
            "Exact decoded raster, observation, fit, baseline, reference-3D, independent "
            "texture-rerender, and neutral-simulation evidence remain not run."
        ),
        "nextAction": "Execute the exact public front/rear raster lineage as the next child unit.",
    },
    "BP-15-SECURITY-PRIVACY": {
        "status": "partial",
        "summary": (
            "Portable dependency and matrix authorities now reject private paths/fingerprints; "
            "public-fixture hashes require explicit classification."
        ),
        "limitations": (
            "Private-user qualification remains local/restricted and Gate P1 remains not run."
        ),
        "nextAction": (
            "Keep private source bytes and durable identifiers outside portable raster evidence."
        ),
    },
    "BP-17-PHASE-12": {
        "status": "partial",
        "summary": (
            "A versioned research runtime candidate parses package authority from selected "
            "canonical bytes and loads the canonical garment fallback after source withdrawal."
        ),
        "limitations": (
            "ZeroOne entries remain descriptors, product runtime v1 is unchanged, and no mobile "
            "or actual ZeroOne payload runtime execution is claimed."
        ),
        "nextAction": (
            "Carry candidate-v2 authority forward while keeping conventional garment fallback "
            "available and product selection unchanged."
        ),
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "The executable v2 Research Prototype matrix records 8 passing and 7 not-run rows "
            "from exact selected public-fixture/package identities."
        ),
        "limitations": (
            "The first unmet row is decoded front/rear raster source identity; the new neutral "
            "simulation row is also not run, and no unsupported tier is promoted."
        ),
        "nextAction": (
            "Execute exact raster lineage, fitting, fidelity, and neutral simulation predicates "
            "without replaying historical summary booleans."
        ),
    },
}

TRUTH_RUNTIME_EVIDENCE_ADDITIONS = {
    row_id: {
        "implementationPaths": [
            "closy-forge/src/closy_forge/research_matrix/evaluator.py",
            "closy-forge/src/closy_forge/dependency_identity/graph.py",
            "closy-forge/src/closy_forge/runtime_delivery/candidate_v2.py",
            "closy-forge/src/closy_forge/truth_runtime/evidence.py",
            "closy-forge/docs/evidence/d0_truth_runtime_authority_v3/"
            "final_d0_research_prototype_matrix_v2.json",
        ],
        "executableEvidence": [
            "predicate-derived 15-row matrix rejects stale, swapped, and cross-package evidence",
            "candidate-v2 selects the canonical garment fallback and remains offline after source "
            "withdrawal",
            "bounded raster/runtime decompression rejects truncation and trailing streams",
        ],
        "tests": [
            "closy-forge/tests/unit/test_research_matrix_v2.py",
            "closy-forge/tests/unit/test_dependency_identity_graph.py",
            "closy-forge/tests/unit/test_runtime_candidate_v2.py",
            "closy-forge/tests/unit/test_truth_runtime_authority_evidence.py",
        ],
    }
    for row_id in TRUTH_RUNTIME_PROGRESSION_UPDATES
}

FINAL_D0_PHY1_V3_PROGRESSION_UPDATES = {
    "BP-49-RASTER-INGESTION-PRIVACY": {
        "status": "partial",
        "summary": (
            "The exact public D0 front/rear raster identities are frozen before fitting, decoded "
            "from source bytes, privacy-classified, and joined to the selected candidate."
        ),
        "limitations": (
            "The evidence is project-authored public-fixture data only; private-user Gate P1, "
            "real-photo breadth, and device capture remain not run."
        ),
        "nextAction": "Add authorised identity-disjoint public capture without widening claims.",
    },
    "BP-50-PIXEL-PARSING-CORRECTIONS": {
        "status": "partial",
        "summary": (
            "Pixel-derived masks, landmarks, openings, camera evidence, and correction replay "
            "pass exact selected-identity lineage controls."
        ),
        "limitations": "The exact D0 fixture does not establish private-user or learned parsing.",
        "nextAction": "Retain the frozen observation contract for independent capture tiers.",
    },
    "BP-52-IMAGE-CONDITIONED-FITTING": {
        "status": "partial",
        "summary": (
            "The exact image-conditioned template ranker and continuous fitter produce finite, "
            "deterministic candidate 060e8d4aaaa7e82eddb75880 with permissioned controls."
        ),
        "limitations": (
            "The candidate remains a public D0 research fixture and its strict C3 and neutral "
            "physical predicates fail."
        ),
        "nextAction": "Preserve the fit while isolating appearance and physical failures.",
    },
    "BP-53-SOURCE-TEXTURE-PBR-RECOVERY": {
        "status": "partial",
        "summary": (
            "Decoded bitmap/PBR maps and independent rerender evidence are persisted against "
            "source pixels rather than candidate-derived targets."
        ),
        "limitations": (
            "D0-RP-07 fails because logo displacement 0.154158086 exceeds the frozen 0.14 limit; "
            "no measured-fabric claim is made."
        ),
        "nextAction": "Improve source-conditioned logo placement under a new frozen visual trial.",
    },
    "BP-14-EVALUATION": {
        "status": "partial",
        "summary": (
            "The final exact-candidate matrix records 9 pass, 3 fail, and 3 not-run rows after "
            "persisted PHY1-v3 neutral scoring."
        ),
        "limitations": (
            "D0-RP-07 texture rerender, D0-RP-08 strict C3, and D0-RP-15 neutral simulation "
            "fail; the first unmet required predicate is D0-RP-07."
        ),
        "nextAction": "Repair exact source-conditioned appearance before another physical trial.",
    },
    "BP-17-PHASE-04": {
        "status": "partial",
        "summary": (
            "Source-backed bitmap/PBR recovery executes with an independent rerender oracle."
        ),
        "limitations": "The frozen logo-displacement predicate fails and fabric is not calibrated.",
        "nextAction": "Run a new preregistered appearance correction without target leakage.",
    },
    "BP-17-PHASE-06": {
        "status": "partial",
        "summary": (
            "PHY1 seam/support v3 executes a solver-active 49-frame neutral trajectory with "
            "rank-aware junctions, temporary supports, in-iteration collision, and independent "
            "simulation/render oracles."
        ),
        "limitations": (
            "Outcome A is frozen: 242 unresolved contacts, 0.0024 m residual depth, "
            "0.041513220488 m "
            "seam crack, 0.145067036152 m slip, negative render clearance, strain/energy failures, "
            "and runtime above 180 s."
        ),
        "nextAction": (
            "Do not spend topology strategy 2 until a newly budgeted dependency-ready physical "
            "milestone is explicitly authorised."
        ),
    },
    "BP-17-PHASE-11": {
        "status": "partial",
        "summary": (
            "MT1 remains a separate analytic transport pass; the exact candidate produces no "
            "admissible solver-driven clip because neutral preflight fails."
        ),
        "limitations": "The 11-state PHY1 replay, CCD, and solver-driven Z2 are not run.",
        "nextAction": "Keep ZeroOne PR #4 frozen until exact C3 and PHY1 prerequisites pass.",
    },
    "BP-18-GATE-C3": {
        "status": "partial",
        "summary": (
            "Historical scoped C3 remains preserved, while strict C3 on exact candidate "
            "060e8d4aaaa7e82eddb75880 fails and is not promoted."
        ),
        "limitations": "No cross-identity evidence is used to repair the exact-candidate result.",
        "nextAction": "Regenerate strict binding only from a future exact candidate identity.",
    },
    "BP-18-GATE-Z2": {
        "status": "partial",
        "summary": "No new solver-driven Z2 attempt is admitted after neutral outcome A.",
        "limitations": "PHY1, CCD, and current-platform ZeroOne execution are not run.",
        "nextAction": "Retain failed/not-run Z2 until exact C3 and full PHY1 both pass.",
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "The exact public-fixture D0 matrix records 9 pass, 3 fail, and 3 not-run rows on "
            "candidate 060e8d4aaaa7e82eddb75880."
        ),
        "limitations": (
            "The first unmet row is D0-RP-07; strict C3 and neutral physics also fail, and human, "
            "private, device, GPU, mobile, and real-fabric evidence remain not run."
        ),
        "nextAction": "Open one appearance-correction branch gated by the frozen D0-RP-07 limit.",
    },
}

FINAL_D0_PHY1_V3_EVIDENCE_ADDITIONS = {
    row_id: {
        "implementationPaths": [
            "closy-forge/docs/evidence/d0_exact_raster_identity_v2",
            "closy-forge/docs/evidence/d0_fitting_pbr_fidelity_v2",
            "closy-forge/docs/evidence/phy1_seam_support_v3",
            "closy-forge/src/closy_forge/simulation_topology_v2/seam_support_v3.py",
            "closy-forge/src/closy_forge/simulation_topology_v2/physical_oracles_v3.py",
            "closy-forge/src/closy_forge/simulation_topology_v2/phy1_seam_support_v3.py",
        ],
        "executableEvidence": [
            "exact D0 matrix: 9 pass, 3 fail, 3 not-run; first unmet D0-RP-07",
            "PHY1-v3 outcome A with unchanged persisted GLB trajectory bytes after evaluator "
            "repair",
            "runtime v1 remains selected and topology v2 remains opt-in",
        ],
        "tests": [
            "closy-forge/tests/unit/test_phy1_seam_support_v3.py",
            "closy-forge/tests/unit/test_exact_d0_fitting_pbr_v2.py",
            "closy-forge/tests/unit/test_exact_raster_identity.py",
        ],
    }
    for row_id in FINAL_D0_PHY1_V3_PROGRESSION_UPDATES
}

UNIT_E_INTEGRITY_PROGRESSION_UPDATES = {
    "BP-14-EVALUATION": {
        "status": "partial",
        "summary": (
            "Research Prototype matrix v3 independently reports core 6 pass, 5 fail, 0 not-run "
            "and supplemental 2 pass, 0 fail, 2 not-run on the exact-fixture authority."
        ),
        "limitations": (
            "D0-RP-03 is attempted-fail, D0-RP-04 is attempted-integrity-error, D0-RP-07, "
            "D0-RP-08, and D0-RP-15 fail; broader identity-disjoint reconstruction remains "
            "never attempted."
        ),
        "nextAction": (
            "Run the one frozen known-target appearance diagnostic, then the separately scoped "
            "identity-disjoint benchmark without donating identities across matrices."
        ),
    },
    "BP-18-GATE-C3": {
        "status": "partial",
        "summary": (
            "Historical scoped C3 is preserved, while matrix v3 keeps strict exact-candidate C3 "
            "failed and independently identity-bound."
        ),
        "limitations": (
            "No summary flag, supplemental execution, or cross-candidate package may repair the "
            "failed exact-candidate result."
        ),
        "nextAction": "Run strict C3 only on a newly frozen exact candidate lineage.",
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "Matrix v3 recomputes exact-fixture core status as 6 pass and 5 fail, with a separate "
            "supplemental summary of 2 pass and 2 not-run."
        ),
        "limitations": (
            "The image-conditioned comparison and execution-isolation claims were demoted; "
            "texture fidelity, strict C3, and neutral simulation also fail. No identity-disjoint, "
            "private, human, GPU, mobile, or production qualification follows."
        ),
        "nextAction": (
            "Preserve the failed attempt chain and execute Unit F then the untouched Unit G "
            "identity-disjoint cohort."
        ),
    },
}

UNIT_E_INTEGRITY_EVIDENCE_ADDITIONS = {
    row_id: {
        "implementationPaths": [
            "closy-forge/src/closy_forge/evidence_integrity_v4",
            "closy-forge/docs/capability-profiles/d0-research-matrix-v3.json",
            "closy-forge/docs/evidence/d0_evidence_integrity_v4",
            "closy-forge/scripts/generate_d0_evidence_integrity_v4.py",
        ],
        "executableEvidence": [
            "matrix v3 opens evidence and recomputes byte, payload, identity, and predicate truth",
            "exact-fixture core 6 pass/5 fail/0 not-run and supplemental 2 pass/0 fail/2 not-run",
            "append-only hash-chained attempts preserve failures and fail closed on missing bytes",
            "PR #43 diagnostic PHY rescore changes definitions without rerunning physics or "
            "outcome",
        ],
        "tests": ["closy-forge/tests/unit/test_d0_evidence_integrity_v4.py"],
    }
    for row_id in UNIT_E_INTEGRITY_PROGRESSION_UPDATES
}

UNIT_F_APPEARANCE_COMMITS = [
    "5a01ed40656c3f2924169f2c3e8f4d702f572cc5",
    "1038cbc9125461a8b80587b56e083191296861ec",
    "1dc8bec3adf8e9f35332b888499af8c2c0b8ae4c",
    "7b4fbc199f462d35ba2f440494cff7cc700b0b94",
]

UNIT_F_APPEARANCE_PROGRESSION_UPDATES = {
    "BP-53-SOURCE-TEXTURE-PBR-RECOVERY": {
        "status": "partial",
        "summary": (
            "One preregistered source-only geometric projection preserves exact front/rear pixel "
            "provenance, passes all eight causal controls, and passes 34 of 34 predicates in the "
            "single known-target regression replay."
        ),
        "limitations": (
            "This is known-target engineering regression evidence, not held-out qualification; "
            "physical PBR remains not measured and D0-RP-07 remains failed until Unit G."
        ),
        "nextAction": (
            "Run the untouched identity-disjoint Unit G cohort with the frozen appearance route."
        ),
    },
    "BP-14-EVALUATION": {
        "status": "partial",
        "summary": (
            "Matrix v3 remains authoritative at core 6 pass/5 fail/0 not-run and supplemental "
            "2 pass/0 fail/2 not-run; Unit F separately records a 34-of-34 known-target "
            "regression pass without changing matrix rows."
        ),
        "limitations": (
            "D0-RP-07, strict C3, and neutral physics remain failed; no held-out, cohort, human, "
            "private-user, mobile, or product qualification follows from Unit F."
        ),
        "nextAction": (
            "Execute the identity-disjoint Unit G benchmark before any D0-RP-07 reconsideration."
        ),
    },
    "BP-17-PHASE-04": {
        "status": "partial",
        "summary": (
            "The frozen source-only atlas route maps source pixels through camera-visible "
            "triangles and material UVs, yielding 0.552461694 source-observed and 0.447538306 "
            "explicit generated-fill fractions."
        ),
        "limitations": (
            "Only the already-known exact D0 target was replayed once; independent identity "
            "generalisation and measured physical material accuracy are not established."
        ),
        "nextAction": "Carry the unchanged route into Unit G without target-specific tuning.",
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "Unit F produces a new appearance/package identity and a successful one-shot "
            "known-target regression diagnostic while preserving matrix v3 and runtime-v1 "
            "authority."
        ),
        "limitations": (
            "Known-target regression cannot promote Research Prototype or D0-RP-07; Unit G "
            "identity-disjoint evidence, strict C3, and admissible physics remain outstanding."
        ),
        "nextAction": (
            "Execute Unit G's preregistered 8-development/16-evaluator identity-disjoint cohort."
        ),
    },
}

UNIT_F_APPEARANCE_EVIDENCE_ADDITIONS = {
    row_id: {
        "implementationPaths": [
            "closy-forge/fixtures/d0_texture_rerender_correction_v3",
            "closy-forge/src/closy_forge/appearance_correction_v3",
            "closy-forge/docs/evidence/d0_texture_rerender_correction_v3",
            "closy-forge/scripts/generate_d0_texture_rerender_v3_prediction.py",
            "closy-forge/scripts/evaluate_d0_texture_rerender_v3_known_target.py",
        ],
        "executableEvidence": [
            "protocol committed before implementation and evaluator-only inputs remained "
            "unmounted through prediction commit",
            "all eight source-only causal controls pass with geometry invariant",
            "source-observed atlas fraction 0.552461694 and generated fill 0.447538306",
            "single known-target replay passes 34/34 atomic predicates",
            "D0-RP-07 fail, Research Prototype partial, and runtime v1 selection preserved",
        ],
        "tests": [
            "closy-forge/tests/unit/test_d0_texture_rerender_correction_v3.py",
        ],
    }
    for row_id in UNIT_F_APPEARANCE_PROGRESSION_UPDATES
}

UNIT_G_DISJOINT_PROGRESSION_UPDATES = {
    "BP-52-IMAGE-CONDITIONED-FITTING": {
        "status": "partial",
        "summary": (
            "Unit G froze 8 development and 16 identity-disjoint evaluator identities, then "
            "completed 64 isolated predictions before its frozen evaluator failed at transcript "
            "loading. No cohort fitting metric or promotion was produced."
        ),
        "limitations": (
            "The fixed inventory completed zero canonical compiles; D0-RP-03 and D0-RP-06 "
            "remain failed and no route is a cohort winner."
        ),
        "nextAction": (
            "Preserve the failed Unit G attempt and continue independent Unit H core "
            "reproducibility and strict C3 infrastructure."
        ),
    },
    "BP-53-SOURCE-TEXTURE-PBR-RECOVERY": {
        "status": "partial",
        "summary": (
            "Unit F known-target regression remains 34/34; Unit G froze an untouched "
            "8-identity appearance subset but completed zero appearance evaluations after the "
            "frozen evaluator harness failed."
        ),
        "limitations": (
            "D0-RP-07 remains failed. Known-target and cohort scopes are separate and cannot be "
            "unioned."
        ),
        "nextAction": "Do not rerun or retune the revealed Unit G cohort in this review unit.",
    },
    "BP-14-EVALUATION": {
        "status": "partial",
        "summary": (
            "Unit G preserves a complete two-stage lock, seed authority, 16 commitments, 64 "
            "isolated predictions, target reveal, and the literal fixed-inventory evaluator "
            "harness failure."
        ),
        "limitations": (
            "No canonical compile, reference-3D, appearance, aggregate, bootstrap, or route "
            "promotion result was produced."
        ),
        "nextAction": "Continue Unit H without repairing or replaying Unit G evaluator targets.",
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "Research Prototype remains partial after the identity-disjoint benchmark failed "
            "before evaluator worker dispatch; Unit F known-target evidence remains separately "
            "scoped."
        ),
        "limitations": (
            "Image-conditioned cohort fitting, cohort appearance, strict C3, and admissible "
            "physics remain unpassed."
        ),
        "nextAction": "Execute predecessor-scoped Unit H reproducibility and strict C3 harness.",
    },
}

UNIT_G_DISJOINT_EVIDENCE_ADDITIONS = {
    row_id: {
        "implementationPaths": [
            "closy-forge/src/closy_forge/disjoint_benchmark_v1",
            "closy-forge/fixtures/d0_disjoint_tshirt_benchmark_v1",
        ],
        "executableEvidence": [
            "8 development identities and 16 seed-authority-derived evaluator commitments",
            "64 predictions executed with application-process deny-by-default input isolation",
            "all target commitments validated only after prediction freeze",
            "frozen evaluator failed before worker dispatch with zero compile/appearance counts",
        ],
        "tests": ["closy-forge/tests/unit/test_d0_disjoint_tshirt_benchmark_v1.py"],
    }
    for row_id in UNIT_G_DISJOINT_PROGRESSION_UPDATES
}

UNIT_M_DISJOINT_PROGRESSION_UPDATES = {
    "BP-52-IMAGE-CONDITIONED-FITTING": {
        "status": "partial",
        "summary": (
            "Unit M froze evaluator v2 and accepted 16 fresh synthetic identities, but the "
            "official authority stopped at its Docker output-mount negative control before any "
            "of the fixed 64 predictions. D0-RP-03 and D0-RP-06 remain failed."
        ),
        "limitations": (
            "The accepted cohort is consumed and cannot be retried; no fitting, compile, "
            "reference-3D, comparative, or promotion metric exists."
        ),
        "nextAction": "Continue independent strict C3 v5 on the predeclared fallback sentinel.",
    },
    "BP-53-SOURCE-TEXTURE-PBR-RECOVERY": {
        "status": "partial",
        "summary": (
            "Unit M created fresh source and private-target bytes but stopped before predictions "
            "or target reveal; appearance execution is 0/24 plus 0/8 repeats."
        ),
        "limitations": (
            "D0-RP-07 remains failed and the skipped artifact upload makes the ephemeral cohort "
            "bytes unavailable for diagnostic replay."
        ),
        "nextAction": "Do not retry the consumed Unit M cohort; preserve its sealed failure.",
    },
    "BP-14-EVALUATION": {
        "status": "partial",
        "summary": (
            "Unit M records an attempted-integrity-error after first accepted draw: 16 accepted "
            "identities, 0/64 predictions, 0/48 compiles, and 0/24 appearance evaluations."
        ),
        "limitations": (
            "No target reveal, aggregate, bootstrap, route promotion, or qualifying row result "
            "exists; all four scoped rows retain literal fail states."
        ),
        "nextAction": "Run independent Unit N strict C3 confirmation under its fallback rule.",
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "Research Prototype remains partial after Unit M's immutable identity-disjoint "
            "authority attempt ended in an isolation-harness integrity failure."
        ),
        "limitations": (
            "Identity-disjoint fitting, isolation qualification, reference-3D fidelity, "
            "appearance, strict C3, and admissible physics remain unpassed."
        ),
        "nextAction": "Continue Unit N; do not promote any Unit M row or route.",
    },
}

UNIT_M_DISJOINT_EVIDENCE_ADDITIONS = {
    row_id: {
        "implementationPaths": [
            "closy-forge/src/closy_forge/disjoint_confirmation_v2",
            "closy-forge/fixtures/d0_disjoint_tshirt_confirmation_v2",
            "closy-forge/docs/d0-disjoint-tshirt-confirmation-v2-lock.md",
        ],
        "executableEvidence": [
            "canonical-LF source lock with 26 implementation files",
            "16 accepted fresh identities and commitment creation before boundary failure",
            "0/64 predictions, 0/48 compiles, and 0/24 appearance evaluations retained",
            "authority run 33532344652 sealed attempted_integrity_error without retry",
        ],
        "tests": ["closy-forge/tests/unit/test_d0_disjoint_confirmation_v2.py"],
    }
    for row_id in UNIT_M_DISJOINT_PROGRESSION_UPDATES
}

UNIT_N_C3_PROGRESSION_UPDATES = {
    "BP-48-PERSISTED-FRAMES-TANGENTS": {
        "status": "partial",
        "summary": (
            "Unit N preserved H4 at consumed 0/8, then the sole fresh v5 authority passed all "
            "eight untouched synthetic pose classes with corrected frame and seam metrics."
        ),
        "limitations": (
            "The pass is exact-Unit-F, synthetic, and pre-topology; it is not physical-cloth, "
            "trajectory, real-world deformation, or post-topology evidence."
        ),
        "nextAction": "Run candidate-independent Unit O topology diagnosis without reusing poses.",
    },
    "BP-08-R-SIM-TO-RENDER-BINDING": {
        "status": "partial",
        "summary": (
            "The exact Unit F binding passed strict C3 v5 on 8/8 fresh committed states with "
            "maximum reconstruction error 6.71791165111579e-08 m and zero candidate-versus-"
            "oracle seam-delta residual."
        ),
        "limitations": (
            "D0-RP-08 closes only for this frozen pre-topology sentinel; any topology or binding "
            "change requires a new untouched confirmation."
        ),
        "nextAction": "Preserve this pass while Unit O diagnoses a distinct topology class.",
    },
    "BP-14-EVALUATION": {
        "status": "partial",
        "summary": (
            "Unit N records a literal strict-C3 pass: 8/8 fresh poses, semantic seam metrics, "
            "two fresh-process repeats, mutation controls, and bounded resources all passed."
        ),
        "limitations": (
            "Identity-disjoint reconstruction and appearance still fail; exact Z1/MT1 remain "
            "not_run/dependency_blocked."
        ),
        "nextAction": "Continue to Unit O; do not infer physical accuracy from C3.",
    },
    "BP-18-GATE-C3": {
        "status": "partial",
        "summary": (
            "Strict C3 v5 passes 8/8 for the exact Unit F sentinel after one externally committed "
            "fresh confirmation; D0-RP-08 is pass in that scope."
        ),
        "limitations": (
            "This is pre-topology synthetic binding reconstruction and cannot transfer to a "
            "future Strategy-3 candidate."
        ),
        "nextAction": "Require a new strict C3 attempt if Unit P changes topology.",
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "With Unit N, the scoped Research Prototype core matrix is 7 pass, 4 fail, 0 "
            "not-run; supplemental remains 2 pass, 0 fail, 2 not-run."
        ),
        "limitations": (
            "D0-RP-03/04/06/07 and D0-RP-15 remain blockers; no coherent identity-disjoint, "
            "physical, private-user, device, or production qualification exists."
        ),
        "nextAction": "Execute bounded candidate-independent Unit O diagnosis.",
    },
}

UNIT_N_C3_EVIDENCE_ADDITIONS = {
    row_id: {
        "implementationPaths": [
            "closy-forge/src/closy_forge/strict_c3_confirmation_v5",
            "closy-forge/fixtures/d0_strict_c3_confirmation_v5",
            "closy-forge/docs/evidence/d0_strict_c3_confirmation_v5",
        ],
        "executableEvidence": [
            "authority run 33546821637 job 99986277154 committed exactly eight fresh poses",
            "8/8 strict C3 states passed on exact Unit F sentinel",
            "maximum binding reconstruction error 6.71791165111579e-08 m",
            "candidate-versus-oracle seam-delta and orientation residuals remained zero; "
            "absolute seam crack and rest-relative inversion were not measured",
            "two fresh-process repeats and negative mutation controls passed",
        ],
        "tests": ["closy-forge/tests/unit/test_d0_strict_c3_confirmation_v5.py"],
    }
    for row_id in UNIT_N_C3_PROGRESSION_UPDATES
}

UNIT_O_TOPOLOGY_PROGRESSION_UPDATES = {
    "BP-08-K-CLOTH-SIMULATION": {
        "status": "partial",
        "summary": (
            "Unit O executed two candidate-independent constrained-remesh revisions through "
            "the production distance, support, and body-collision kernels. Each passed seven "
            "of eight fixtures, and neither strategy class was admitted in the preserved raw "
            "execution; exact cross-minor regeneration then failed."
        ),
        "limitations": (
            "Revision 1 introduced one T-junction and omitted semantic seam-sequence transfer; "
            "revision 2 removed the topology defect but still omitted that semantic transfer. "
            "A local witness found three one-ULP impulse-total differences and Linux had "
            "additional numeric drift, so "
            "the effective Unit O outcome is diagnosis_integrity_error. No canonical garment "
            "candidate or physical solve was created."
        ),
        "nextAction": (
            "Keep Unit P ineligible. A future authorised programme must begin with a new "
            "candidate-independent class; the final Strategy 3 slot remains unspent."
        ),
    },
    "BP-14-EVALUATION": {
        "status": "partial",
        "summary": (
            "Unit O records diagnosis_integrity_error after its exact-head matrix could not "
            "regenerate the preserved revision bytes across Python/platform combinations."
        ),
        "limitations": (
            "The eight fixtures are synthetic development/discrimination evidence, not held-out "
            "qualification. The preserved raw execution rejected both classes, but cannot be "
            "promoted as cross-minor deterministic evidence. Unit P confirmation seed and "
            "instances remain unrealised."
        ),
        "nextAction": (
            "Preserve the rejection and do not create Units P, Q, or R in this finite sequence."
        ),
    },
    "BP-17-PHASE-06": {
        "status": "partial",
        "summary": (
            "The bounded Strategy 3 diagnosis exercised explicit duplicated seams, finite "
            "compliance, openings, transfer fields, contacts, mutations, and deterministic "
            "same-process recomputation without touching the canonical T-shirt."
        ),
        "limitations": (
            "No investigated revision preserved every topology and semantic transfer invariant, "
            "and exact cross-minor regeneration failed, so no topology candidate, neutral "
            "preflight, full PHY1, or CCD run exists."
        ),
        "nextAction": "Do not spend the reserved strategy or candidate attempt on either class.",
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "Research Prototype remains partial. Unit O improves solver-level diagnostic "
            "coverage but closes with diagnosis_integrity_error, admits no post-topology "
            "candidate, and changes no matrix row result."
        ),
        "limitations": (
            "D0-RP-03/04/07/15, identity-disjoint qualification, admissible physics, "
            "post-topology C3/Z1, and all private/device/product evidence remain unresolved."
        ),
        "nextAction": (
            "End this authorised finite sequence with runtime v1 selected and conditional Units "
            "P/Q/R uncreated."
        ),
    },
}

UNIT_O_TOPOLOGY_EVIDENCE_ADDITIONS = {
    row_id: {
        "implementationPaths": [
            "closy-forge/src/closy_forge/phy1_topology_strategy3_diagnosis_v1",
            "closy-forge/fixtures/phy1_topology_strategy3_diagnosis_v1",
            "closy-forge/docs/evidence/phy1_topology_strategy3_diagnosis_v1",
        ],
        "executableEvidence": [
            "two immutable candidate-independent revisions each passed 7/8 production-kernel "
            "development fixtures",
            "revision 1 rejected for one T-junction and incomplete semantic seam transfer",
            "revision 2 rejected for incomplete semantic seam transfer despite valid topology",
            "exact cross-minor regeneration failed; local 3.11 exposed three one-ULP totals and "
            "Linux exposed additional numeric drift",
            "no candidate, candidate attempt, final strategy, confirmation seed, or confirmation "
            "instance was consumed",
        ],
        "tests": ["closy-forge/tests/unit/test_phy1_topology_strategy3_diagnosis_v1.py"],
    }
    for row_id in UNIT_O_TOPOLOGY_PROGRESSION_UPDATES
}

UNIT_S_RECOVERY_PROGRESSION_UPDATES = {
    "BP-08-K-CLOTH-SIMULATION": {
        "status": "partial",
        "summary": (
            "Unit S preserves every physical result while adding prospective portable numeric "
            "policy, real production-path instrumentation, and an executable independent "
            "eight-fixture Strategy-3 confirmation generator."
        ),
        "limitations": (
            "Only public development fixtures ran. No official topology seed, untouched fixture, "
            "strategy admission, candidate transformation, neutral solve, PHY1, or CCD exists."
        ),
        "nextAction": "Run Unit U only after S-core and S-PHY are externally green.",
    },
    "BP-14-EVALUATION": {
        "status": "partial",
        "summary": (
            "Unit S repairs replay, result-schema, fixed-denominator, external-attestation, "
            "typed-inventory, and mutation semantics without revising historical outcomes."
        ),
        "limitations": (
            "The v3 evaluator has only generic/public contaminated development evidence until "
            "one externally authorised untouched cohort is created."
        ),
        "nextAction": "Run Unit T only after the exact-image 3/3 S-D0 preflight is green.",
    },
    "BP-18-GATE-C3": {
        "status": "partial",
        "summary": (
            "Unit S decomposes strict-C3 v5 accurately: exact positional binding and analytic "
            "agreement pass, while absolute seam, physical deformation, rest-relative inversion, "
            "persisted deformed frames, and coherent-shell predicates remain not measured."
        ),
        "limitations": (
            "The frozen v5 artifact has 614 raw indexed components per side and no stable ancestry "
            "map capable of proving prospective coherent-shell equivalence."
        ),
        "nextAction": "Require the corrected prospective C3 contract for any new candidate.",
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "Unit S changes no Research Prototype result: core remains 7 pass, 4 fail, 0 not-run; "
            "supplemental remains 2 pass, 0 fail, 2 not-run."
        ),
        "limitations": (
            "D0-RP-03/04/06/07 and D0-RP-15 remain failed; no identity-disjoint v3, post-topology, "
            "physical, private, device, human, Alpha, Beta, or Production evidence exists."
        ),
        "nextAction": "Advance only through the independently green Unit S sub-gates.",
    },
}

UNIT_S_RECOVERY_EVIDENCE_ADDITIONS = {
    row_id: {
        "implementationPaths": [
            "closy-forge/src/closy_forge/recovery_foundation_v2",
            "closy-forge/docker/d0_v3",
            "closy-forge/fixtures/evidence_authority_recovery_v2",
        ],
        "executableEvidence": [
            "typed prior inventory and opaque-v2 unverified caveat",
            "64/48/16/24/8 fail-closed evaluator contract and mutations",
            "portable three-layer numeric boundary and exact geometry policy",
            "independent executable eight-fixture Strategy-3 public development generator",
            "historical C3 v5 predicate decomposition without replay",
        ],
        "tests": ["closy-forge/tests/unit/test_evidence_authority_recovery_v2.py"],
    }
    for row_id in UNIT_S_RECOVERY_PROGRESSION_UPDATES
}

UNIT_H_CORE_C3_PROGRESSION_UPDATES = {
    "BP-48-PERSISTED-FRAMES-TANGENTS": {
        "status": "partial",
        "summary": (
            "Unit H froze an independently implemented direct-shell oracle and eight-state "
            "non-physical C3 suite, but the sole held-out attempt failed in the frozen frame-"
            "metric reporting adapter before any state completed."
        ),
        "limitations": (
            "No held-out frame validity or dense/fallback C3 pass exists; the one-attempt "
            "budget is consumed and no retry or post-result key repair is permitted."
        ),
        "nextAction": (
            "Preserve the failed predecessor attempt and continue the separately bounded Unit I "
            "topology strategy without claiming C3 success."
        ),
    },
    "BP-08-R-SIM-TO-RENDER-BINDING": {
        "status": "partial",
        "summary": (
            "The exact Unit F sentinel, package, simulation/render topology, and binding are "
            "locked under H0; H4 consumed one strict held-out attempt and failed in its frozen "
            "frame-metric adapter."
        ),
        "limitations": (
            "Development-state reconstruction below 6.7e-8 m is not held-out qualification, "
            "and the failed harness yields D0-RP-08 fail rather than partial metric credit."
        ),
        "nextAction": (
            "Any admissible post-topology Unit I candidate must be requalified from bytes in "
            "Unit J; predecessor H evidence cannot transfer."
        ),
    },
    "BP-14-EVALUATION": {
        "status": "partial",
        "summary": (
            "Unit H independently records core Forge reproducibility pass, static Z1 and MT1 "
            "dependency blocks, and a literal strict-C3 frozen-evaluator failure."
        ),
        "limitations": (
            "The exact authenticated supplemental processors were unavailable, and zero of eight "
            "held-out C3 states completed."
        ),
        "nextAction": (
            "Execute Unit I's one preregistered topology strategy, then apply the mandatory "
            "post-topology J or logical J-A rules."
        ),
    },
    "BP-18-GATE-C3": {
        "status": "partial",
        "summary": (
            "Core runtime reconstruction is reproducible, but strict exact-sentinel C3 remains "
            "failed after its one frozen held-out attempt stopped on a frame-metric key mismatch."
        ),
        "limitations": (
            "No held-out C3 pass, PHY1 implication, trajectory qualification, or Z2 admission "
            "follows from Unit H."
        ),
        "nextAction": (
            "Do not replay Unit H; requalification is required only for a newly minted admissible "
            "Unit I lineage in Unit J."
        ),
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "Unit H closes D0-RP-12 with predecessor-scoped core Forge reproducibility while "
            "D0-RP-08 remains failed and D0-RP-10/11 remain not run."
        ),
        "limitations": (
            "Research Prototype remains partial; identity-disjoint fitting, appearance, strict "
            "C3, neutral physics, human, private-user, and device evidence are unpassed."
        ),
        "nextAction": (
            "Spend only Unit I's one topology-strategy-2 attempt under its frozen budget."
        ),
    },
}

UNIT_H_CORE_C3_EVIDENCE_ADDITIONS = {
    row_id: {
        "implementationPaths": [
            "closy-forge/fixtures/d0_core_runtime_c3_v4",
            "closy-forge/src/closy_forge/core_runtime_c3_v4",
            "closy-forge/docs/evidence/d0_core_runtime_c3_v4",
        ],
        "executableEvidence": [
            "H0 resolves to Unit F candidate 49161d8adafb514e5a04b1a9 only after "
            "byte-descendant checks",
            "core runtime fresh, second-clean, cache, corruption, withdrawal, and "
            "delete/rebuild checks pass",
            "exact authenticated static Z1 and clean MT1 processors are unavailable and "
            "remain not run",
            "one strict C3 held-out attempt was consumed and failed before any of eight "
            "states completed",
        ],
        "tests": ["closy-forge/tests/unit/test_d0_core_runtime_c3_v4.py"],
    }
    for row_id in UNIT_H_CORE_C3_PROGRESSION_UPDATES
}

UNIT_I_TOPOLOGY_PROGRESSION_UPDATES = {
    "BP-08-K-CLOTH-SIMULATION": {
        "status": "partial",
        "summary": (
            "Unit I locked one topology/DOF-only conforming-seam quotient strategy, then its "
            "single candidate-independent transfer microfixture proved that shared quotient "
            "DOFs are not mechanically equivalent to the frozen finite-compliance seam law."
        ),
        "limitations": (
            "Outcome M opened no candidate and advanced no solver step. Neutral PHY1, full PHY1, "
            "integrated CCD, post-topology C3, and solver-driven Z2 were not run."
        ),
        "nextAction": (
            "Do not create Unit J or K; require new candidate-independent diagnosis before the "
            "reserved materially different topology strategy 3 can be authorised."
        ),
    },
    "BP-14-EVALUATION": {
        "status": "partial",
        "summary": (
            "Unit I preserves a frozen lock, one failed strategy-specific equivalence result, an "
            "append-only attempt registry, Outcome M, and logical J-A closure."
        ),
        "limitations": (
            "There is no canonical post-topology candidate and therefore no post-topology "
            "reproducibility, strict/trajectory C3, Z1, PHY1, CCD, or Z2 matrix scope."
        ),
        "nextAction": (
            "Keep the three evaluation scopes separate and record none_dependency_ready until a "
            "new candidate-independent Strategy 3 diagnosis exists."
        ),
    },
    "BP-17-PHASE-06": {
        "status": "partial",
        "summary": (
            "The reserved Strategy 2 lane executed exactly one candidate-independent mechanical "
            "equivalence microfixture and closed as Outcome M before candidate construction."
        ),
        "limitations": (
            "Normal separation, tangential slip, stored energy, and impulse equivalence all fail "
            "the frozen 1e-12 transfer limits; the finite-compliance seam model cannot be "
            "silently replaced by quotient shared DOFs."
        ),
        "nextAction": (
            "Preserve explicit finite-compliance seams and design analytic transfer fixtures for "
            "a materially different reserved Strategy 3 without executing a candidate."
        ),
    },
    "BP-18-GATE-C3": {
        "status": "partial",
        "summary": (
            "Predecessor strict C3 remains failed; logical J-A correctly records that no new "
            "post-topology candidate exists to requalify."
        ),
        "limitations": (
            "Unit H evidence cannot transfer to a changed topology, and Unit I produced no changed "
            "topology. Post-topology strict and trajectory C3 are dependency-blocked, not passed."
        ),
        "nextAction": "Do not create a report-only Unit J branch without an admissible candidate.",
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "Research Prototype remains partial after Strategy 2 failed its pre-candidate "
            "mechanical transfer gate and closed through logical J-A."
        ),
        "limitations": (
            "Matrix v3 failures, the unfinished identity-disjoint cohort, strict C3 failure, "
            "inadmissible physics, and all human/private/device/product tiers remain unresolved."
        ),
        "nextAction": (
            "Record none_dependency_ready; the first prerequisite is new candidate-independent "
            "diagnosis for a materially different reserved topology strategy 3."
        ),
    },
}

UNIT_I_TOPOLOGY_EVIDENCE_ADDITIONS = {
    row_id: {
        "implementationPaths": [
            "closy-forge/fixtures/phy1_topology_strategy2_v4",
            "closy-forge/src/closy_forge/phy1_topology_strategy2_v4",
            "closy-forge/docs/evidence/phy1_topology_strategy2_v4",
        ],
        "executableEvidence": [
            "immutable topology-only budget and strategy lock precede the sole strategy-specific "
            "microfixture",
            "quotient transfer differs by 1.5999980159352167e-08 m position, "
            "2.8799928574752917e-07 J stored energy, and 1.3333317066849276e-10 N*s impulse",
            "Outcome M records candidateOpened=false, solverStepAdvanced=false, and "
            "candidateAttemptConsumed=false",
            "logical J-A forbids Unit J and K because no post-topology candidate exists",
        ],
        "tests": [
            "closy-forge/tests/unit/test_phy1_topology_strategy2_v4_budget.py",
            "closy-forge/tests/unit/test_phy1_topology_strategy2_v4_diagnosis.py",
            "closy-forge/tests/unit/test_phy1_topology_strategy2_v4_lock.py",
            "closy-forge/tests/unit/test_phy1_topology_strategy2_v4_evidence.py",
        ],
    }
    for row_id in UNIT_I_TOPOLOGY_PROGRESSION_UPDATES
}

NEXT_ACTIONS = {
    "BP-05-04-ZEROONE-OPTIONAL": (
        "Retain optional hash-linked ZeroOne derivatives while broadening provider, mobile, and "
        "human-review evidence."
    ),
    "BP-47-INSPECTION-ARTIFACTS": (
        "Add validation-time rerendering and independent hidden synthetic targets before broader "
        "fidelity acceptance."
    ),
    "BP-48-PERSISTED-FRAMES-TANGENTS": (
        "Validate independently reconstructed dense and fallback frames over real stitched-shell "
        "deformation states."
    ),
    "BP-49-RASTER-INGESTION-PRIVACY": (
        "Retain fixture-only capture authority while completing bounded JPEG decode and deletion "
        "safety; private-user Gate P1 remains not run."
    ),
    "BP-50-PIXEL-PARSING-CORRECTIONS": (
        "Evaluate parsing and correction contracts on identity-disjoint hidden targets; automated "
        "fixtures remain simulated corrections."
    ),
    "BP-51-MULTIVIEW-CAPTURE-FUSION": (
        "Add independent public/provider capture evidence without exposing target program identity."
    ),
    "BP-52-IMAGE-CONDITIONED-FITTING": (
        "Evaluate the trained synthetic D0 grammar model on identity-disjoint hidden targets and "
        "retain deterministic fitting fallback."
    ),
    "BP-53-SOURCE-TEXTURE-PBR-RECOVERY": (
        "Validate appearance against independently authored target rasters and authorised source "
        "tiers without treating generated fill as source evidence."
    ),
    "BP-08-A-INGESTION": (
        "Complete bounded JPEG pixel decode and preserve fixture/private evidence separation."
    ),
    "BP-08-C-SEGMENTATION": (
        "Evaluate masks on identity-disjoint hidden targets and later authorised capture tiers."
    ),
    "BP-08-E-MULTIVIEW-FUSION": (
        "Evaluate fusion on identity-disjoint hidden synthetic targets and later authorised "
        "captures."
    ),
    "BP-08-H-PATTERN-INFERENCE": (
        "Broaden the trained grammar-constrained model evaluation beyond project-authored "
        "synthetic D0 data and establish superiority against independent baselines."
    ),
    "BP-08-I-GEOMETRY-PROVIDERS": (
        "Keep the validated ZeroOne static derivative non-authoritative while adding broader "
        "garment/provider and human-review evidence."
    ),
    "BP-08-K-CLOTH-SIMULATION": (
        "Close the scoped XPBD collision gate without filtering contacts, then gather broader "
        "provider, motion, and hardware evidence."
    ),
    "BP-08-L-FIT-REFINEMENT": (
        "Evaluate learned and deterministic fit routes on identity-disjoint hidden synthetic "
        "targets."
    ),
    "BP-08-M-MESH-ANALYSIS": (
        "Apply concave-safe topology validation to every family and validate real ZeroOne "
        "derivatives."
    ),
    "BP-08-P-TEXTURE-PBR": (
        "Add independent source-tier fidelity and mobile runtime evidence without overclaiming "
        "generated fixture appearance."
    ),
    "BP-08-Q-MATERIAL-INFERENCE": (
        "Complete per-family applicability and calibrated physical evidence beyond authored D0 "
        "presets."
    ),
    "BP-08-U-QUALITY-PROVENANCE": (
        "Regenerate evidence from corrected topology, XPBD, independent fidelity, and real "
        "ZeroOne runs."
    ),
    "BP-09-GEOMOTREE": (
        "Preserve the validated pinned static derivative path while closing C3 and gathering "
        "broader garment, mobile, and human-review evidence before dynamic work."
    ),
    "BP-12-MODEL-STRATEGY": (
        "Evaluate the project-owned trained synthetic grammar model and real ZeroOne static "
        "processor; "
        "retain licence and evidence-tier boundaries."
    ),
    "BP-14-EVALUATION": (
        "Use authoritative independent C3, fidelity, learned-model, and ZeroOne reports rather "
        "than stale prose."
    ),
    "BP-17-PHASE-02": (
        "Keep Phase 2 partial while adding independent and authorised capture tiers beyond D0 "
        "fixtures."
    ),
    "BP-17-PHASE-03": (
        "Evaluate fitting on identity-disjoint hidden targets and authorised capture tiers."
    ),
    "BP-17-PHASE-04": (
        "Validate texture/PBR fidelity against independent targets and authorised source tiers."
    ),
    "BP-17-PHASE-06": (
        "Resolve stitched-shell body clearance/source correspondence and bring recomputed "
        "self-collision residual depth within the declared D0 budget."
    ),
    "BP-17-PHASE-08": (
        "Retain package-contract-complete D0 fixture verticals while adding continuous collision, "
        "provider, private, hardware, and human-review evidence."
    ),
    "BP-17-PHASE-10": (
        "Retain the 9/9 default-family and representative static passes while keeping the original "
        "parameter range and global Phase 10 partial."
    ),
    "BP-17-PHASE-11": (
        "Build compiled ZeroOne B against the exact passing representative; PHY1 remains "
        "separately required for solver-driven physical claims."
    ),
    "BP-18-GATE-C3": (
        "Preserve the scoped C3 and representative Z1 passes while running the stricter "
        "PHY1-SingleLayer-D0 physical campaign independently."
    ),
    "BP-20-RESEARCH-PROTOTYPE": (
        "Integrate corrected topology, scoped C3, trained synthetic D0 inference, and real ZeroOne "
        "static "
        "execution while retaining unsupported tiers."
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate canonical blueprint status artifacts.")
    parser.add_argument("--docs", type=Path, required=True)
    args = parser.parse_args()
    docs = args.docs.resolve()
    coverage_path = docs / "blueprint_coverage.json"
    stack_path = docs / "pr_stack_manifest.json"
    coverage_value = _replace_legacy_truth_terms(
        json.loads(coverage_path.read_text(encoding="utf-8"))
    )
    if not isinstance(coverage_value, dict):
        raise ValueError("coverage authority root must be an object")
    coverage = coverage_value
    coverage["version"] = VERSION
    for row in coverage["rows"]:
        valid_commit_shas = [
            sha for sha in (row.get("commitSha") or []) if sha not in STALE_INVALID_EVIDENCE_ANCHORS
        ]
        row["commitSha"] = valid_commit_shas or None
        row_id = str(row["id"])
        update = ROW_UPDATES.get(row_id)
        if update:
            row.update(update)
        ancestry_update = ANCESTRY_TRUTH_UPDATES.get(row_id)
        if ancestry_update:
            row.update(ancestry_update)
        current_update = CURRENT_PROGRESSION_UPDATES.get(row_id)
        if current_update:
            row.update(current_update)
        phy1_v2_update = PHY1_V2_PROGRESSION_UPDATES.get(row_id)
        if phy1_v2_update:
            row.update(phy1_v2_update)
        truth_runtime_update = TRUTH_RUNTIME_PROGRESSION_UPDATES.get(row_id)
        if truth_runtime_update:
            row.update(truth_runtime_update)
        final_d0_phy1_update = FINAL_D0_PHY1_V3_PROGRESSION_UPDATES.get(row_id)
        if final_d0_phy1_update:
            row.update(final_d0_phy1_update)
        unit_e_update = UNIT_E_INTEGRITY_PROGRESSION_UPDATES.get(row_id)
        if unit_e_update:
            row.update(unit_e_update)
        unit_f_update = UNIT_F_APPEARANCE_PROGRESSION_UPDATES.get(row_id)
        if unit_f_update:
            row.update(unit_f_update)
        unit_g_update = UNIT_G_DISJOINT_PROGRESSION_UPDATES.get(row_id)
        if unit_g_update:
            row.update(unit_g_update)
        unit_h_update = UNIT_H_CORE_C3_PROGRESSION_UPDATES.get(row_id)
        if unit_h_update:
            row.update(unit_h_update)
        unit_i_update = UNIT_I_TOPOLOGY_PROGRESSION_UPDATES.get(row_id)
        if unit_i_update:
            row.update(unit_i_update)
        unit_m_update = UNIT_M_DISJOINT_PROGRESSION_UPDATES.get(row_id)
        if unit_m_update:
            row.update(unit_m_update)
        unit_n_update = UNIT_N_C3_PROGRESSION_UPDATES.get(row_id)
        if unit_n_update:
            row.update(unit_n_update)
        unit_o_update = UNIT_O_TOPOLOGY_PROGRESSION_UPDATES.get(row_id)
        if unit_o_update:
            row.update(unit_o_update)
        unit_s_update = UNIT_S_RECOVERY_PROGRESSION_UPDATES.get(row_id)
        if unit_s_update:
            row.update(unit_s_update)
        if ROW_EVIDENCE_ADDITIONS.get(row_id):
            row["implementationPaths"] = _append_unique(
                row.get("implementationPaths"), PHASE10_PATHS
            )
            row["executableEvidence"] = _append_unique(
                row.get("executableEvidence"), PHASE10_EVIDENCE
            )
            row["tests"] = _append_unique(row.get("tests"), PHASE10_TESTS)
            row["commitSha"] = _append_unique(row.get("commitSha"), [EVIDENCE_ANCHOR])
        current_evidence = CURRENT_EVIDENCE_ADDITIONS.get(row_id)
        if current_evidence:
            for field in ("implementationPaths", "executableEvidence", "tests"):
                row[field] = _append_unique(row.get(field), current_evidence[field])
            row["commitSha"] = _append_unique(row.get("commitSha"), [EVIDENCE_ANCHOR])
        phy1_v2_evidence = PHY1_V2_EVIDENCE_ADDITIONS.get(row_id)
        if phy1_v2_evidence:
            for field in ("implementationPaths", "executableEvidence", "tests"):
                row[field] = _append_unique(row.get(field), phy1_v2_evidence[field])
            row["commitSha"] = _append_unique(row.get("commitSha"), [EVIDENCE_ANCHOR])
        truth_runtime_evidence = TRUTH_RUNTIME_EVIDENCE_ADDITIONS.get(row_id)
        if truth_runtime_evidence:
            for field in ("implementationPaths", "executableEvidence", "tests"):
                row[field] = _append_unique(row.get(field), truth_runtime_evidence[field])
            row["commitSha"] = _append_unique(row.get("commitSha"), [EVIDENCE_ANCHOR])
        final_d0_phy1_evidence = FINAL_D0_PHY1_V3_EVIDENCE_ADDITIONS.get(row_id)
        if final_d0_phy1_evidence:
            for field in ("implementationPaths", "executableEvidence", "tests"):
                row[field] = _append_unique(row.get(field), final_d0_phy1_evidence[field])
            row["commitSha"] = _append_unique(row.get("commitSha"), [EVIDENCE_ANCHOR])
        unit_e_evidence = UNIT_E_INTEGRITY_EVIDENCE_ADDITIONS.get(row_id)
        if unit_e_evidence:
            for field in ("implementationPaths", "executableEvidence", "tests"):
                row[field] = _append_unique(row.get(field), unit_e_evidence[field])
            row["commitSha"] = _append_unique(row.get("commitSha"), [EVIDENCE_ANCHOR])
        unit_f_evidence = UNIT_F_APPEARANCE_EVIDENCE_ADDITIONS.get(row_id)
        if unit_f_evidence:
            for field in ("implementationPaths", "executableEvidence", "tests"):
                row[field] = _append_unique(row.get(field), unit_f_evidence[field])
            row["commitSha"] = _append_unique(row.get("commitSha"), UNIT_F_APPEARANCE_COMMITS)
        unit_g_evidence = UNIT_G_DISJOINT_EVIDENCE_ADDITIONS.get(row_id)
        if unit_g_evidence:
            for field in ("implementationPaths", "executableEvidence", "tests"):
                row[field] = _append_unique(row.get(field), unit_g_evidence[field])
            row["commitSha"] = _append_unique(row.get("commitSha"), [EVIDENCE_ANCHOR])
        unit_h_evidence = UNIT_H_CORE_C3_EVIDENCE_ADDITIONS.get(row_id)
        if unit_h_evidence:
            for field in ("implementationPaths", "executableEvidence", "tests"):
                row[field] = _append_unique(row.get(field), unit_h_evidence[field])
            row["commitSha"] = _append_unique(row.get("commitSha"), [EVIDENCE_ANCHOR])
        unit_i_evidence = UNIT_I_TOPOLOGY_EVIDENCE_ADDITIONS.get(row_id)
        if unit_i_evidence:
            for field in ("implementationPaths", "executableEvidence", "tests"):
                row[field] = _append_unique(row.get(field), unit_i_evidence[field])
            row["commitSha"] = _append_unique(row.get("commitSha"), [UNIT_I_EVIDENCE_HEAD])
        unit_m_evidence = UNIT_M_DISJOINT_EVIDENCE_ADDITIONS.get(row_id)
        if unit_m_evidence:
            for field in ("implementationPaths", "executableEvidence", "tests"):
                row[field] = _append_unique(row.get(field), unit_m_evidence[field])
            row["commitSha"] = _append_unique(row.get("commitSha"), [UNIT_M_AUTHORITY_HEAD])
        unit_n_evidence = UNIT_N_C3_EVIDENCE_ADDITIONS.get(row_id)
        if unit_n_evidence:
            for field in ("implementationPaths", "executableEvidence", "tests"):
                row[field] = _append_unique(row.get(field), unit_n_evidence[field])
            row["commitSha"] = _append_unique(row.get("commitSha"), [UNIT_N_AUTHORITY_HEAD])
        unit_o_evidence = UNIT_O_TOPOLOGY_EVIDENCE_ADDITIONS.get(row_id)
        if unit_o_evidence:
            for field in ("implementationPaths", "executableEvidence", "tests"):
                row[field] = _append_unique(row.get(field), unit_o_evidence[field])
            row["commitSha"] = _append_unique(row.get("commitSha"), [UNIT_O_EVIDENCE_HEAD])
        unit_s_evidence = UNIT_S_RECOVERY_EVIDENCE_ADDITIONS.get(row_id)
        if unit_s_evidence:
            for field in ("implementationPaths", "executableEvidence", "tests"):
                row[field] = _append_unique(row.get(field), unit_s_evidence[field])
            row["commitSha"] = _append_unique(row.get("commitSha"), [UNIT_S_EVIDENCE_HEAD])
        if (
            row_id in NEXT_ACTIONS
            and row_id not in CURRENT_PROGRESSION_UPDATES
            and row_id not in PHY1_V2_PROGRESSION_UPDATES
            and row_id not in TRUTH_RUNTIME_PROGRESSION_UPDATES
            and row_id not in FINAL_D0_PHY1_V3_PROGRESSION_UPDATES
            and row_id not in UNIT_E_INTEGRITY_PROGRESSION_UPDATES
            and row_id not in UNIT_F_APPEARANCE_PROGRESSION_UPDATES
            and row_id not in UNIT_G_DISJOINT_PROGRESSION_UPDATES
            and row_id not in UNIT_H_CORE_C3_PROGRESSION_UPDATES
            and row_id not in UNIT_I_TOPOLOGY_PROGRESSION_UPDATES
            and row_id not in UNIT_M_DISJOINT_PROGRESSION_UPDATES
            and row_id not in UNIT_N_C3_PROGRESSION_UPDATES
            and row_id not in UNIT_O_TOPOLOGY_PROGRESSION_UPDATES
            and row_id not in UNIT_S_RECOVERY_PROGRESSION_UPDATES
        ):
            row["nextAction"] = NEXT_ACTIONS[row_id]
        if row_id.startswith("BP-09-Z") and row_id not in {"BP-09-Z1", "BP-09-Z2"}:
            stage = row_id.removeprefix("BP-09-")
            row["status"] = "discovery_pending"
            row["summary"] = f"ZeroOne stage {stage} is not implemented or executed."
            row["limitations"] = (
                "No compiled dynamic, GPU, mobile, provider, or product evidence exists for "
                f"{stage}; static Z1 evidence must not be replayed into this stage."
            )
            row["nextAction"] = (
                f"Implement and execute {stage} only after its explicit prerequisites pass."
            )
    coverage = apply_ancestry_metadata(coverage)
    coverage["generatedBy"] = {
        "generatorVersion": GENERATOR_VERSION,
        "declaredInputPaths": PROVENANCE_INPUTS,
        "sourceTreeHash": _source_tree_hash(PROVENANCE_INPUTS),
        "sourceTreeHashAlgorithm": "sha256_path_nul_lf_normalized_content_nul_v2",
        "finalHeadAttestationLocation": "external_exact_head_ci_check_or_draft_pr_body",
        "selfReferentialCommitSha": False,
    }
    coverage_path.write_text(
        json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    stack = _upgrade_stack_to_dag(json.loads(stack_path.read_text(encoding="utf-8")))
    stack_path.write_text(
        json.dumps(stack, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    model = build_status_model(coverage, stack, evidence_anchor_sha=UNIT_S_EVIDENCE_HEAD)
    (docs / "current_blueprint_status.json").write_text(
        json.dumps(model, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (docs / "BLUEPRINT_STATUS_SUMMARY.md").write_text(
        render_status_summary(model), encoding="utf-8", newline="\n"
    )
    _write_active_resume(docs)
    _update_master_progress(docs)
    _apply_unit_s_status_overlay(docs)
    return 0


def _append_unique(current: object, additions: list[str]) -> list[str]:
    values = list(current) if isinstance(current, list) else []
    return values + [value for value in additions if value not in values]


def _write_active_resume(docs: Path) -> None:
    outcome_path = docs / "evidence" / "phy1_topology_strategy3_diagnosis_v1"
    outcome = json.loads((outcome_path / "unit_o_outcome.json").read_text(encoding="utf-8"))
    integrity_attestation = json.loads(
        (outcome_path / "integrity_attestation.json").read_text(encoding="utf-8")
    )
    effective_outcome = integrity_attestation["effectiveOutcome"]
    revisions = outcome["revisions"]
    resume = {
        "schemaVersion": 1,
        "machineResumeVersion": "closy.active_blueprint_resume.phy1_strategy3_diagnosis_v1.v11",
        "activeLane": "finite sequence complete after Unit O diagnosis integrity error",
        "branch": "codex/closy-forge-phy1-topology-strategy3-diagnosis-v1",
        "pullRequest": 52,
        "evidenceHead": UNIT_O_EVIDENCE_HEAD,
        "latestFinishedParentPublicationHead": UNIT_N_FINAL_HEAD,
        "localHeadAtResumeSource": "pending_final_commit",
        "remoteHeadAtResumeSource": "pending_final_commit",
        "sourceAnchorIsSelfReferential": False,
        "finalHeadAttestationLocation": "draft PR body and exact-head workflow",
        "pendingCIAtEvidenceHead": True,
        "mergeAuthorised": False,
        "parent": {
            "branch": "codex/closy-forge-d0-strict-c3-confirmation-v5",
            "pullRequest": 51,
            "sha": UNIT_N_FINAL_HEAD,
            "exactHeadWorkflow": "33547909132",
            "forgeJobsPassed": 29,
            "forgeJobsTotal": 29,
        },
        "gates": {
            "ResearchPrototype-D0-matrix-v2": "historical_superseded_9_pass_3_fail_3_not_run",
            "ResearchPrototype-D0-matrix-v3-core": "partial_7_pass_4_fail_0_not_run",
            "ResearchPrototype-D0-matrix-v3-supplemental": "2_pass_0_fail_2_not_run",
            "D0-DisjointTshirt-v2": "attempted_integrity_error",
            "D0-Strict-C3-v5": "pass_exact_unit_f_pre_topology_8_of_8",
            "PHY1-Neutral-SeamSupport-D0-v3": "A_neutral_preflight_failed_v3",
            "PHY1-Topology-Strategy2-D0-v4": (
                "outcome_M_strategy_microfixture_failed_no_candidate"
            ),
            "PHY1-Topology-Strategy3-Diagnosis-D0-v1": effective_outcome,
            "Unit-P": "ineligible_unit_o_diagnosis_integrity_error",
            "Unit-Q": "ineligible_no_unit_p_candidate",
            "Unit-R": "ineligible_no_unit_q_prerequisites",
            "Runtime": "v1_selected_topology_v2_opt_in_unchanged",
        },
        "matrixScopes": {
            "knownTarget": {
                "outcome": "known_target_regression_pass",
                "predicatesPassed": 34,
                "predicatesTotal": 34,
                "d0Rp07Promoted": False,
            },
            "identityDisjointV1": {
                "outcome": "benchmark_failed_fixed_inventory_unfinished",
                "predictions": 64,
                "canonicalCompiles": 0,
                "appearanceEvaluations": 0,
            },
            "identityDisjointV2": {
                "outcome": "attempted_integrity_error",
                "acceptedIdentities": 16,
                "predictions": 0,
                "predictionDenominator": 64,
                "canonicalCompiles": 0,
                "compileDenominator": 48,
                "appearanceEvaluations": 0,
                "appearanceDenominator": 24,
            },
            "strictC3V5": {
                "outcome": "pass",
                "posePassCount": 8,
                "poseCount": 8,
                "preTopology": True,
            },
            "postTopologyCandidate": {
                "candidateExists": False,
                "matrixNotRunReason": "unit_o_diagnosis_integrity_error",
            },
        },
        "unitMResult": {
            "outcome": "attempted_integrity_error",
            "acceptedIdentityCount": 16,
            "predictionCount": 0,
            "fullCompileCount": 0,
            "appearanceEvaluationCount": 0,
            "qualificationRetryAllowed": False,
        },
        "unitNResult": {
            "outcome": "pass",
            "publishedHead": UNIT_N_FINAL_HEAD,
            "posePassCount": 8,
            "poseCount": 8,
            "maximumBindingReconstructionErrorMeters": 6.71791165111579e-08,
            "maximumSemanticSeamCrackMeters": 0.0,
            "maximumTangentialSeamSlidingMeters": 0.0,
            "preTopology": True,
        },
        "unitOResult": {
            "outcome": effective_outcome,
            "rawOutcome": outcome["outcomeClass"],
            "rawOutcomeDigest": outcome["integrity"]["outcomeDigest"],
            "integrityAttestationDigest": integrity_attestation["integrity"]["attestationDigest"],
            "integrityFailureRun": integrity_attestation["discovery"]["runId"],
            "replayPerformed": integrity_attestation["replayPerformed"],
            "revisionCount": outcome["revisionCount"],
            "revisionFixturePassCounts": [
                {
                    "revision": row["revision"],
                    "strategyClass": row["strategyClass"],
                    "fixturePassCount": row["fixturePassCount"],
                    "fixtureCount": row["fixtureCount"],
                    "admitted": row["admitted"],
                    "firstUnmetPredicate": row["firstUnmetPredicate"],
                }
                for row in revisions
            ],
            "admittedStrategyClass": outcome["admittedStrategyClass"],
            "candidateCreated": outcome["candidateCreated"],
            "candidateAttemptConsumed": outcome["candidateAttemptConsumed"],
            "finalStrategyConsumed": outcome["finalStrategyConsumed"],
            "unitPEligible": outcome["unitPEligible"],
        },
        "remainingBudgets": outcome["budgetsAfter"],
        "conditionalUnits": {
            "P": "not_created_ineligible",
            "Q": "not_created_ineligible",
            "R": "not_created_ineligible",
        },
        "nextHandoff": {
            "selection": "none_dependency_ready_in_authorised_sequence",
            "firstUnmetPrerequisite": "unit_o_cross_minor_evidence_integrity",
            "safestEvidenceAction": (
                "preserve_raw_execution_and_integrity_error_with_unspent_budget"
            ),
        },
        "exactNextAction": "Complete external exact-head attestation and final handoff.",
        "stopReason": "authorised_finite_sequence_complete_after_unit_o_integrity_error",
        "unsupportedEvidenceClasses": [
            "post_topology_candidate",
            "post_topology_core_reproducibility",
            "post_topology_strict_or_trajectory_C3",
            "full_PHY1",
            "integrated_CCD",
            "solver_driven_Z2",
            "private_user",
            "human_review",
            "real_photo",
            "real_fabric",
            "GPU",
            "mobile",
            "Alpha",
            "Beta",
            "Production",
            "identity_disjoint_cohort_qualification",
        ],
    }
    (docs / "ACTIVE_BLUEPRINT_RESUME.json").write_text(
        json.dumps(resume, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    markdown = f"""# Active Blueprint Resume

## Frozen boundary

- Branch: `{resume['branch']}`
- Pull request: `#52` (draft)
- Immutable pre-execution lock head: `{UNIT_O_EVIDENCE_HEAD}`
- Exact parent: PR `#51` at `{UNIT_N_FINAL_HEAD}`
- Parent exact-head Forge workflow: `33547909132` (`29/29` successful)
- Merge authorised: `false`

## Literal Unit O outcome

Unit O executed exactly two candidate-independent development revisions. The preserved raw results
were `7/8` for each revision and admitted no class. Exact-head Forge then failed to regenerate the
revision bytes across Python/platform combinations. A local Python 3.11 witness found three
one-ULP impulse-total differences, while Linux contained additional numeric drift. Effective
literal outcome: `{effective_outcome}`. The raw result was not replayed or rewritten.
No class was admitted in the preserved raw execution.

No canonical garment candidate was created. The candidate attempt and final topology strategy are
both unspent. The separately frozen Unit P confirmation generator has no seed or instances. Units
P, Q, and R are ineligible and were not created. Runtime v1 and its conventional fallback remain
selected.

## Scope-separated truth

- Identity-disjoint v2: `16` accepted identities, `0/64` predictions, `0/48` compiles, and `0/24`
  appearance evaluations; literal `attempted_integrity_error`.
- Known target: `known_target_regression_pass`, `34/34`; engineering regression only.
- Strict C3 v5: exact Unit F synthetic pre-topology sentinel, `8/8 pass`.
- Unit O: two preserved synthetic development revisions, each `7/8`, followed by an exact
  cross-minor regeneration integrity failure; effective `diagnosis_integrity_error`.
- Prior neutral physical outcome: `A_neutral_preflight_failed_v3`; no physics was rerun.
- Current matrix v3 core: `7 pass / 4 fail / 0 not-run`.
- Current matrix v3 supplemental: `2 pass / 0 fail / 2 not-run`.
- Coverage: `20 complete / 63 partial / 7 not started / 11 discovery pending`.

## Remaining budget and handoff

- Seam models remaining: `0`
- Reserved topology strategies remaining: `1`
- Candidate attempts remaining: `1`
- Next authorised conditional unit: `none`
- First unmet prerequisite: `unit_o_cross_minor_evidence_integrity`

This finite prompt is complete once PR #52 receives exact-head external attestation for this
additive integrity classification. No physical
cloth, full PHY1, integrated CCD, post-topology qualification, solver-driven Z2, private-user,
human-review, real-photo, real-fabric, GPU, mobile, Alpha, Beta, or Production claim is made.
"""
    (docs / "ACTIVE_BLUEPRINT_RESUME.md").write_text(markdown, encoding="utf-8", newline="\n")


def _write_active_resume_unit_n_legacy(docs: Path) -> None:
    evidence_dir = docs / "evidence" / "phy1_topology_strategy2_v4"
    outcome = json.loads((evidence_dir / "unit_i_outcome.json").read_text(encoding="utf-8"))
    closure = json.loads((evidence_dir / "logical_j_a_closure.json").read_text(encoding="utf-8"))
    attempt_registry = json.loads(
        (evidence_dir / "physical_attempt_registry.json").read_text(encoding="utf-8")
    )
    microfixtures = json.loads(
        (evidence_dir / "strategy_microfixtures.json").read_text(encoding="utf-8")
    )
    resume = {
        "schemaVersion": 1,
        "machineResumeVersion": "closy.active_blueprint_resume.d0_strict_c3_confirmation_v5.v9",
        "activeLane": "Unit N strict C3 pass sealed; Unit O topology diagnosis next",
        "branch": "codex/closy-forge-d0-strict-c3-confirmation-v5",
        "pullRequest": 51,
        "evidenceHead": UNIT_N_AUTHORITY_HEAD,
        "latestFinishedParentPublicationHead": UNIT_M_FINAL_HEAD,
        "localHeadAtResumeSource": "pending_final_commit",
        "remoteHeadAtResumeSource": "pending_final_commit",
        "sourceAnchorIsSelfReferential": False,
        "finalHeadAttestationLocation": "draft PR body and exact-head workflow",
        "pendingCIAtEvidenceHead": False,
        "mergeAuthorised": False,
        "parent": {
            "branch": "codex/closy-forge-d0-disjoint-tshirt-confirmation-v2",
            "pullRequest": 50,
            "sha": UNIT_M_FINAL_HEAD,
            "exactHeadWorkflow": "33533707412",
            "forgeJobsPassed": 29,
            "forgeJobsTotal": 29,
        },
        "gates": {
            "ResearchPrototype-D0-matrix-v2": "historical_superseded_9_pass_3_fail_3_not_run",
            "ResearchPrototype-D0-matrix-v3-core": "partial_7_pass_4_fail_0_not_run",
            "ResearchPrototype-D0-matrix-v3-supplemental": "2_pass_0_fail_2_not_run",
            "D0-DisjointTshirt-v1": "benchmark_failed_fixed_inventory_unfinished",
            "D0-DisjointTshirt-v2": "attempted_integrity_error",
            "D0-Core-Reproducibility-H1": "pass_predecessor_sentinel_scoped",
            "D0-Strict-C3-H4": "fail_frozen_evaluator_adapter_0_of_8",
            "D0-Strict-C3-v5": "pass_exact_unit_f_pre_topology_8_of_8",
            "D0-Recovery-Foundation-v1": "pass_generic_candidate_independent_no_confirmation",
            "PHY1-Neutral-SeamSupport-D0-v3": "A_neutral_preflight_failed_v3",
            "PHY1-Topology-Strategy2-D0-v4": (
                "outcome_M_strategy_microfixture_failed_no_candidate"
            ),
            "Unit-J": "J-A_post_topology_candidate_unavailable",
            "Unit-K": "ineligible_no_post_topology_candidate",
            "Runtime": "v1_selected_topology_v2_opt_in_unchanged",
        },
        "matrixScopes": {
            "knownTarget": {
                "outcome": "known_target_regression_pass",
                "predicatesPassed": 34,
                "predicatesTotal": 34,
                "d0Rp07Promoted": False,
            },
            "identityDisjointV1": {
                "outcome": "benchmark_failed_fixed_inventory_unfinished",
                "predictions": 64,
                "canonicalCompiles": 0,
                "appearanceEvaluations": 0,
            },
            "identityDisjointV2": {
                "outcome": "attempted_integrity_error",
                "acceptedIdentities": 16,
                "predictions": 0,
                "predictionDenominator": 64,
                "canonicalCompiles": 0,
                "compileDenominator": 48,
                "appearanceEvaluations": 0,
                "appearanceDenominator": 24,
                "targetRevealOccurred": False,
            },
            "strictC3V5": {
                "outcome": "pass",
                "candidateId": "candidate.d0_texture_rerender_v3.49161d8adafb514e5a04b1a9",
                "posePassCount": 8,
                "poseCount": 8,
                "preTopology": True,
            },
            "postTopologyCandidate": {
                "candidateExists": False,
                "matrixNotRunReason": "post_topology_candidate_unavailable",
            },
        },
        "unitIResult": {
            "strategyId": outcome["strategyId"],
            "outcomeClass": outcome["outcomeClass"],
            "reasonCode": outcome["reasonCode"],
            "strategyLockDigest": outcome["strategyLockDigest"],
            "strategyMicrofixtureDigest": outcome["strategyMicrofixtureDigest"],
            "outcomeDigest": outcome["integrity"]["outcomeDigest"],
            "attemptRegistryHead": attempt_registry["headHash"],
            "failedChecks": microfixtures["failedChecks"],
            "positionDifferenceMeters": microfixtures["equivalence"]["differences"][
                "positionMeters"
            ],
            "storedEnergyDifferenceJoules": microfixtures["equivalence"]["differences"][
                "storedEnergyJoules"
            ],
            "impulseDifferenceNewtonSeconds": microfixtures["equivalence"]["differences"][
                "impulseNewtonSeconds"
            ],
            "candidateOpened": outcome["admissibleCanonicalPostTopologyCandidateExists"],
            "solverStepAdvanced": False,
            "candidateAttemptConsumed": outcome["candidateAttemptConsumed"],
            "neutralExecuted": outcome["neutralExecuted"],
            "fullPhy1Executed": outcome["fullPhy1Executed"],
            "integratedCcdExecuted": outcome["integratedCcdExecuted"],
            "solverDrivenZ2Executed": outcome["solverDrivenZ2Executed"],
            "runtimeV1RemainsSelected": outcome["runtimeV1RemainsSelected"],
        },
        "logicalJResult": {
            "outcome": closure["logicalOutcome"],
            "closureDigest": closure["integrity"]["closureDigest"],
            "postTopologyCandidateAvailable": closure["postTopologyCandidateAvailable"],
            "unitJBranchAuthorized": closure["unitJBranchAuthorized"],
            "unitKEligible": closure["unitKEligible"],
        },
        "unitMResult": {
            "outcome": "attempted_integrity_error",
            "authorityHead": UNIT_M_AUTHORITY_HEAD,
            "authorityRun": "33532344652",
            "authorityJob": "99938286152",
            "acceptedIdentityCount": 16,
            "predictionCount": 0,
            "fullCompileCount": 0,
            "appearanceEvaluationCount": 0,
            "targetRevealOccurred": False,
            "qualificationRetryAllowed": False,
            "firstUnmetPredicate": ("container_negative_control_must_write_audited_output"),
        },
        "unitNResult": {
            "outcome": "pass",
            "authorityHead": UNIT_N_AUTHORITY_HEAD,
            "authorityRun": "33546821637",
            "authorityJob": "99986277154",
            "posePassCount": 8,
            "poseCount": 8,
            "maximumBindingReconstructionErrorMeters": 6.71791165111579e-08,
            "maximumSemanticSeamCrackMeters": 0.0,
            "maximumTangentialSeamSlidingMeters": 0.0,
            "maximumInvertedTriangleCount": 0,
            "qualificationRetryAllowed": False,
            "d0Rp08Status": "pass_exact_unit_f_pre_topology",
        },
        "remainingBudgets": {
            "seamModels": outcome["remainingBudgets"]["seamModels"],
            "topologyStrategies": outcome["remainingBudgets"]["reservedTopologyStrategies"],
        },
        "nextHandoff": {
            "selection": "unit_o_phy1_topology_strategy3_diagnosis_v1",
            "firstUnmetPrerequisite": "candidate_independent_strategy3_class_admission",
            "safestEvidenceAction": "freeze production-kernel microfixtures before diagnosis",
        },
        "exactNextAction": (
            "Create Unit O from the final Unit N head, freeze physical authority and production-"
            "kernel microfixtures, then execute at most two candidate-independent revisions."
        ),
        "stopReason": "unit_n_pass_sealed_unit_o_dependency_ready",
        "unsupportedEvidenceClasses": [
            "post_topology_candidate",
            "post_topology_core_reproducibility",
            "post_topology_strict_or_trajectory_C3",
            "full_PHY1",
            "integrated_CCD",
            "solver_driven_Z2",
            "private_user",
            "human_review",
            "real_photo",
            "real_fabric",
            "GPU",
            "mobile",
            "Alpha",
            "Beta",
            "Production",
            "identity_disjoint_cohort_qualification",
        ],
    }
    (docs / "ACTIVE_BLUEPRINT_RESUME.json").write_text(
        json.dumps(resume, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    markdown = f"""# Active Blueprint Resume

## Frozen boundary

- Branch: `{resume['branch']}`
- Pull request: `#51` (draft)
- Immutable Unit N authority head: `{UNIT_N_AUTHORITY_HEAD}`
- Latest finished parent publication: PR `#50` at `{UNIT_M_FINAL_HEAD}`
- Parent exact-head Forge workflow: `33533707412` (`29/29` successful after failed-jobs rerun)
- Merge authorised: `false`

Unit N is sealed after its official external authority committed and evaluated exactly eight fresh
poses. Its final publication head and exact-head workflow remain external to avoid self-reference.

## Literal outcome

Authority run `33546821637`, job `99986277154`, passed `8/8` fresh semantic pose classes on the
exact Unit F sentinel. Maximum binding reconstruction error was `6.71791165111579e-08 m`; seam
crack, tangential sliding, and inverted triangles were zero. The attempt is consumed and cannot be
rerolled. D0-RP-08 is pass only for this synthetic pre-topology identity.

Unit M remains `attempted_integrity_error` at `0/64` predictions. Logical outcome is
`{closure['logicalOutcome']}`. Neutral/full PHY1, integrated CCD, post-topology C3/Z1, and
solver-driven Z2 were not run. Runtime v1 and its conventional fallback remain selected.

## Scope-separated matrix state

- Known target: `known_target_regression_pass`, `34/34` predicates, engineering regression only;
  D0-RP-07 not promoted.
- Identity-disjoint v1: `64` predictions, `0` canonical compiles, `0` appearance evaluations.
- Identity-disjoint v2: `16` accepted identities and `0/64` predictions; immutable integrity error.
- Strict C3 v5: exact Unit F sentinel, `8/8 pass`, synthetic and pre-topology only.
- Post-topology candidate: nonexistent, so no Unit J matrix scope exists.
- Current matrix v3 core after scoped Unit N evidence: `7 pass / 4 fail / 0 not-run`.
- Current matrix v3 supplemental: `2 pass / 0 fail / 2 not-run`.
- Frozen predecessor physical outcome: `A_neutral_preflight_failed_v3`; no physics was rerun.

## Remaining budget and handoff

- Seam models remaining: `0`
- Reserved topology strategies remaining: `1` (Strategy 3)
- Selected next lane: `unit_o_phy1_topology_strategy3_diagnosis_v1`
- First unmet prerequisite: `candidate_independent_strategy3_class_admission`
- Safest action: freeze production-kernel microfixtures before bounded diagnosis.

Unit O is dependency-ready regardless of Unit N's pre-topology scope. Unit P remains ineligible
unless Unit O literally records `strategy3_class_admitted_pre_candidate`.
"""
    (docs / "ACTIVE_BLUEPRINT_RESUME.md").write_text(markdown, encoding="utf-8", newline="\n")


def _update_master_progress(docs: Path) -> None:
    path = docs / "MASTER_BLUEPRINT_PROGRESS.md"
    marker = "## PHY1 Strategy 3 Candidate-Independent Diagnosis v1 Outcome"
    current = path.read_text(encoding="utf-8")
    prefix = current.split(marker, 1)[0].rstrip()
    section = f"""

{marker}

Unit O froze the exact PR43 package and physical authority, eight production-kernel development
fixtures, two maximum pre-candidate revisions, and a separate unrealised Unit P confirmation
generator at `{UNIT_O_EVIDENCE_HEAD}`. It then executed the two revisions without transforming the
canonical T-shirt or creating a candidate.

Local longest-edge bisection passed `7/8` fixtures but introduced one T-junction and omitted the
updated semantic seam sequence. Closure longest-edge bisection also passed `7/8`; it removed the
topology defect but still omitted the semantic seam sequence. Exact-head Forge run `33559874476`
then found that the committed revision bytes do not regenerate across the Python/platform matrix.
A local Python 3.11 witness identified three one-ULP impulse-total differences, while Linux exposed
additional numeric drift. The effective literal outcome is
`diagnosis_integrity_error`; the raw files remain preserved and no replay occurred. Unit P is
ineligible, so Units P, Q, and R were not created. The final topology strategy and candidate
attempt remain unspent.

The Research Prototype matrix remains `7 pass / 4 fail / 0 not-run` core plus
`2 pass / 0 fail / 2 not-run` supplemental. Coverage remains `20 complete / 63 partial / 7 not
started / 11 discovery pending`. Runtime v1 and the conventional fallback remain selected. No
physical-cloth, real-world deformation, private-user, human-review, real-photo, real-fabric, GPU,
mobile, Alpha, Beta, Production, post-topology candidate, full-PHY1, integrated-CCD, or
solver-driven-Z2 claim is made.
"""
    path.write_text(prefix + section, encoding="utf-8", newline="\n")


def _apply_unit_s_status_overlay(docs: Path) -> None:
    evidence_path = docs / "evidence" / "evidence_authority_recovery_v2"
    outcome = json.loads((evidence_path / "unit_s_outcome.json").read_text(encoding="utf-8"))
    subgates = outcome["subgates"]
    all_green = all(row["result"] == "pass" for row in subgates.values())

    resume_path = docs / "ACTIVE_BLUEPRINT_RESUME.json"
    resume = json.loads(resume_path.read_text(encoding="utf-8"))
    resume.update(
        {
            "machineResumeVersion": "closy.active_blueprint_resume.evidence_authority_v2.v12",
            "activeLane": "Unit S evidence and authority recovery v2",
            "branch": "codex/closy-forge-evidence-authority-recovery-v2",
            "pullRequest": 53,
            "evidenceHead": UNIT_S_EVIDENCE_HEAD,
            "latestFinishedParentPublicationHead": ("8dd7a547debf038e9e27c48cf8e42009ae69ac3a"),
            "localHeadAtResumeSource": "pending_final_commit",
            "remoteHeadAtResumeSource": "pending_final_commit",
            "pendingCIAtEvidenceHead": True,
            "parent": {
                "branch": "codex/closy-forge-phy1-topology-strategy3-diagnosis-v1",
                "pullRequest": 52,
                "sha": "8dd7a547debf038e9e27c48cf8e42009ae69ac3a",
                "exactHeadWorkflow": "33570351597",
                "forgeJobsPassed": 29,
                "forgeJobsTotal": 29,
            },
            "unitSResult": {
                "outcome": outcome["result"],
                "subgates": subgates,
                "preflightHead": UNIT_S_PREFLIGHT_HEAD,
                "preflightRun": UNIT_S_PREFLIGHT_RUN,
                "officialD0CohortCreated": False,
                "officialTopologyFixturesCreated": False,
                "canonicalCandidateCreated": False,
                "physicalAttemptConsumed": False,
            },
            "remainingBudgets": {
                "seamModels": 0,
                "topologyStrategies": 1,
                "candidateAttempts": 1,
            },
            "conditionalUnits": {
                "T": "dependency_ready" if all_green else "blocked_by_S_D0",
                "U": "dependency_ready_after_T" if all_green else "blocked_by_S_PHY",
                "V": "not_created_requires_unit_u_pass",
                "W": "not_created_requires_unit_v_candidate",
                "X": "not_created_requires_unit_w_core_prerequisites",
            },
            "stopReason": None if all_green else "unit_s_external_subgate_pending",
            "exactNextAction": (
                "Create Unit T from exact Unit S publication head and freeze its v3 protocol."
                if all_green
                else "Complete exact-head Unit S external preflight before scientific execution."
            ),
            "nextHandoff": {
                "selection": "unit_t_d0_confirmation_v3" if all_green else "unit_s_preflight",
                "firstUnmetPrerequisite": (
                    "unit_t_protocol_lock" if all_green else "unit_s_external_subgates"
                ),
                "safestEvidenceAction": (
                    "freeze_before_official_seed"
                    if all_green
                    else "preserve_nonqualifying_public_evidence"
                ),
            },
        }
    )
    resume["gates"].update(
        {name: f"{row['result']}:{row['reason']}" for name, row in subgates.items()}
    )
    resume_path.write_text(
        json.dumps(resume, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    subgate_lines = "\n".join(
        f"- `{name}`: `{row['result']}` - `{row['reason']}`" for name, row in subgates.items()
    )
    markdown = f"""# Active Blueprint Resume

## Current Lane

- Unit: `S` - evidence and authority recovery foundation v2
- Branch: `codex/closy-forge-evidence-authority-recovery-v2`
- Draft PR: `#53`
- Exact parent: `8dd7a547debf038e9e27c48cf8e42009ae69ac3a` (PR #52)
- Immutable evidence anchor: `{UNIT_S_EVIDENCE_HEAD}`
- Exact preflight head: `{UNIT_S_PREFLIGHT_HEAD}`
- Exact preflight workflow: `{UNIT_S_PREFLIGHT_RUN}`

## Sub-gates

{subgate_lines}

## Literal State

- Current Research Prototype core: `7 pass / 4 fail / 0 not-run`.
- Current supplemental: `2 pass / 0 fail / 2 not-run`.
- Runtime remains `closy.integrated_runtime.headless_d0.v1`.
- Package remains `836abc564a79c0f38ae8bdad3d4a418b0fb05a550193059c1cece8130203c20a`.
- Fallback remains `8eccea814251f8974f5349548038be73a4d00cec73df7a7bfb787aede58385c6`.
- Remaining budgets: seam models `0`, topology strategies `1`, candidate attempts `1`.
- No official v3 cohort, official topology fixture, candidate, or physical attempt exists in Unit S.

## Next Action

{resume['exactNextAction']}
"""
    (docs / "ACTIVE_BLUEPRINT_RESUME.md").write_text(markdown, encoding="utf-8", newline="\n")

    summary_path = docs / "BLUEPRINT_STATUS_SUMMARY.md"
    summary = summary_path.read_text(encoding="utf-8").rstrip()
    summary += (
        "\n\n## Unit S Authority Recovery\n\n"
        + "\n".join(
            f"- {name}: `{row['result']}` - `{row['reason']}`" for name, row in subgates.items()
        )
        + "\n\nUnit S changes no Research Prototype row and creates no scientific cohort, "
        "untouched topology fixture, candidate, or physical attempt.\n"
    )
    summary_path.write_text(summary, encoding="utf-8", newline="\n")

    master_path = docs / "MASTER_BLUEPRINT_PROGRESS.md"
    marker = "## Evidence and Authority Recovery Foundation v2"
    master = master_path.read_text(encoding="utf-8")
    master = master.split(marker, 1)[0].rstrip()
    master += f"""

{marker}

Unit S starts exactly from PR #52 head `8dd7a547debf038e9e27c48cf8e42009ae69ac3a`.
It repairs the 41-source replay generator, separates scientific result and publication anchors,
derives the remaining physical budgets from a hash-chained event ledger, and preserves Unit O's
raw result plus superseding integrity error without replay.

The D0 v3 foundation uses a pinned minimal Linux image, UID/GID `65532`, no network, a read-only
root/input boundary, scrubbed environment, allowlisted output collection, four fixed routes, an
honestly fitted public-development pixel model, typed prior domains, and exact evaluator
denominators `64/48/16/24/8`. The opaque v2 cohort remains explicitly unverified.

The PHY foundation decomposes historical C3 v5 to its positional binding scope, validates persisted
rest-asset frame attributes without replaying qualification, introduces prospective raw/portable
numeric layers, and freezes an executable independent eight-fixture Strategy-3 holdout generator.
Only public ineligible development fixtures ran in Unit S. No topology strategy, candidate, neutral
solve, PHY1, CCD, or runtime selection changed.

Unit S evidence anchor is `{UNIT_S_EVIDENCE_HEAD}`. Exact pinned-image and portability preflight is
recorded at `{UNIT_S_PREFLIGHT_HEAD}` by workflow `{UNIT_S_PREFLIGHT_RUN}`. The Research Prototype
remains `7/4/0` core and `2/0/2` supplemental; broader evidence tiers remain unsupported.
"""
    master_path.write_text(master, encoding="utf-8", newline="\n")


def _upgrade_stack_to_dag(stack: dict[str, object]) -> dict[str, object]:
    rows = [
        row
        for row in cast(list[dict[str, object]], stack["pullRequests"])
        if _as_int(row["number"]) <= 23
    ]
    for row in rows:
        if row.get("number") != 23:
            continue
        row["headSha"] = PR23_FINAL_HEAD
        row["layerAhead"] = 14
        row["layerCommitCount"] = 14
        row["changedFileCount"] = 24
        row["latestExactHeadForgeRun"] = {
            "exactHead": True,
            "runId": PR23_FINAL_RUN,
            "jobs": [
                {"jobId": job_id, "name": name, "conclusion": "SUCCESS"}
                for name, job_id in PR23_FINAL_JOB_IDS.items()
            ],
        }
    for snapshot in PR_SNAPSHOTS:
        (
            number,
            title,
            branch,
            base_branch,
            base_sha,
            head_sha,
            commit_count,
            changed_files,
            run_id,
            conclusion,
            role,
        ) = snapshot
        rows.append(
            {
                "repository": "jake-the-jake/Closy",
                "number": number,
                "url": f"https://github.com/jake-the-jake/Closy/pull/{number}",
                "title": title,
                "branch": branch,
                "baseBranch": base_branch,
                "baseSha": base_sha,
                "headSha": head_sha,
                "mergeBase": base_sha,
                "layerAhead": commit_count,
                "layerBehind": 0,
                "layerCommitCount": commit_count,
                "changedFileCount": changed_files,
                "draft": True,
                "state": "OPEN",
                "mergeability": "MERGEABLE",
                "directParentMergeBaseVerified": True,
                "knownException": (
                    None
                    if run_id
                    else {
                        "code": "exact_head_ci_recorded_outside_generated_evidence",
                        "descendantEvidenceIsExactHead": False,
                        "reason": (
                            f"PR #{number} exact-head CI is recorded in the draft PR body "
                            "because this "
                            "generated report is anchored to its immutable implementation source"
                        ),
                    }
                ),
                "role": role,
                "latestExactHeadForgeRun": _closy_run(run_id, conclusion),
            }
        )
    zeroone_row: dict[str, object] = {
        "repository": "jake-the-jake/ZeroOne",
        "number": 2,
        "url": "https://github.com/jake-the-jake/ZeroOne/pull/2",
        "title": "Requalify the headless Closy static processor",
        "branch": "codex/closy-zeroone-static-source-requalification",
        "baseBranch": "master",
        "baseSha": "a17762bc1fc12fbd33f0488634635a5dcfdf8da3",
        "headSha": "13a844d240f4bbb2cafde105c4a0bdca8d89a06b",
        "mergeBase": "a17762bc1fc12fbd33f0488634635a5dcfdf8da3",
        "layerAhead": 3,
        "layerBehind": 0,
        "layerCommitCount": 3,
        "changedFileCount": 11,
        "draft": True,
        "state": "OPEN",
        "mergeability": "MERGEABLE",
        "directParentMergeBaseVerified": True,
        "knownException": None,
        "role": "candidate_static_source",
        "latestExactHeadWorkflows": [
            _workflow("Closy Static Processor", "33187775880", "SUCCESS", 2),
            _workflow("Viewport UI Corrective CPU Validation", "33187776003", "SUCCESS", 1),
        ],
    }
    zeroone_dynamic_row: dict[str, object] = {
        "repository": "jake-the-jake/ZeroOne",
        "number": 3,
        "url": "https://github.com/jake-the-jake/ZeroOne/pull/3",
        "title": "Add compiled Closy dynamic reference processor",
        "branch": "codex/closy-zeroone-dynamic-reference-v1",
        "baseBranch": "master",
        "baseSha": "a17762bc1fc12fbd33f0488634635a5dcfdf8da3",
        "sourceParentSha": "13a844d240f4bbb2cafde105c4a0bdca8d89a06b",
        "headSha": "413aecd24434f90d89ad35c6a8f909de75df34c7",
        "mergeBase": "a17762bc1fc12fbd33f0488634635a5dcfdf8da3",
        "layerAhead": 12,
        "layerBehind": 0,
        "layerCommitCount": 12,
        "changedFileCount": 23,
        "draft": True,
        "state": "OPEN",
        "mergeability": "MERGEABLE",
        "directParentMergeBaseVerified": True,
        "knownException": None,
        "role": "compiled_dynamic_source",
        "latestExactHeadWorkflows": [
            _workflow("Closy Static Processor", "33262736792", "SUCCESS", 2),
            _workflow("Viewport UI Corrective CPU Validation", "33262736795", "SUCCESS", 1),
        ],
    }
    zeroone_transport_row: dict[str, object] = {
        "repository": "jake-the-jake/ZeroOne",
        "number": 4,
        "url": "https://github.com/jake-the-jake/ZeroOne/pull/4",
        "title": "Qualify ZeroOne dynamic mechanical transport v2",
        "branch": "codex/zeroone-closy-dynamic-contract-v2",
        "baseBranch": "codex/closy-zeroone-dynamic-reference-v1",
        "baseSha": "413aecd24434f90d89ad35c6a8f909de75df34c7",
        "headSha": "9cbae4a8e6ef2e61c1839ecbdf8a462aaa560027",
        "mergeBase": "413aecd24434f90d89ad35c6a8f909de75df34c7",
        "layerAhead": 3,
        "layerBehind": 0,
        "layerCommitCount": 3,
        "changedFileCount": 9,
        "draft": True,
        "state": "OPEN",
        "mergeability": "MERGEABLE",
        "directParentMergeBaseVerified": True,
        "knownException": None,
        "role": "compiled_mechanical_transport_v2_source",
        "latestExactHeadWorkflows": [
            _workflow("Closy Static Processor", "33297149608", "SUCCESS", 2),
        ],
    }
    rows.sort(key=lambda row: _as_int(row["number"]))
    parent_by_pr = {
        **{number: number - 1 for number in range(2, 25)},
        25: 24,
        26: 24,
        27: 24,
        28: 27,
        29: 27,
        30: 28,
        31: 28,
        32: 28,
        33: 28,
        34: 33,
        35: 33,
        36: 34,
        37: 35,
        38: 36,
        39: 38,
        40: 39,
        41: 40,
        42: 41,
        43: 42,
        44: 43,
        45: 44,
        46: 45,
        47: 46,
        48: 47,
        49: 48,
        50: 49,
        51: 50,
        52: 51,
    }
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, str]] = []
    for row in rows:
        pr_number = _as_int(row["number"])
        node_id = f"github:jake-the-jake/Closy:pr/{row['number']}"
        parent_ids: list[str] = []
        parent_number = parent_by_pr.get(pr_number)
        if parent_number is not None:
            parent_id = f"github:jake-the-jake/Closy:pr/{parent_number}"
            parent_ids.append(parent_id)
            edges.append({"from": parent_id, "to": node_id, "kind": "parent"})
        dependency_ids = list(parent_ids)
        if pr_number == 28:
            dependency_ids.extend(
                [
                    "github:jake-the-jake/Closy:pr/25",
                    "github:jake-the-jake/ZeroOne:pr/2",
                ]
            )
        if pr_number == 34:
            dependency_ids.append("github:jake-the-jake/ZeroOne:pr/3")
        if pr_number == 35:
            dependency_ids.extend(
                [
                    "github:jake-the-jake/Closy:pr/26",
                    "github:jake-the-jake/Closy:pr/31",
                ]
            )
        if pr_number == 38:
            dependency_ids.extend(
                [
                    "github:jake-the-jake/Closy:pr/37",
                    "github:jake-the-jake/Closy:pr/29",
                    "github:jake-the-jake/Closy:pr/30",
                    "github:jake-the-jake/Closy:pr/32",
                ]
            )
        for dependency_id in dependency_ids:
            edges.append({"from": dependency_id, "to": node_id, "kind": "dependency"})
        source_only = pr_number in {25, 26, 29, 30, 31, 32, 34}
        superseded = pr_number == 25
        workflows = _normalise_workflows(row.get("latestExactHeadForgeRun"))
        if pr_number == 37:
            workflows.append(
                _workflow("Closy Forge Phase 9 Structured v3", "33321665610", "SUCCESS", 1)
            )
        if pr_number == 38:
            workflows.append(
                _workflow("Closy Forge Phase 9 Structured v3", "33329481042", "SUCCESS", 1)
            )
        mappings = []
        if pr_number == 28:
            mappings = [
                {
                    "sourceNode": "github:jake-the-jake/Closy:pr/25",
                    "sourceCommit": source,
                    "destinationCommit": destination,
                    "disposition": "replayed",
                }
                for source, destination in PR25_REPLAY_MAPPINGS
            ]
        if pr_number == 35:
            mappings = [
                {
                    "sourceNode": "github:jake-the-jake/Closy:pr/26",
                    "sourceCommit": source,
                    "destinationCommit": destination,
                    "disposition": "replayed",
                }
                for source, destination in (
                    (
                        "12cdfd60e841bf33903f6e75b102d9d48f69501c",
                        "b90d795125671778ed27075492bad0cd57cdafaf",
                    ),
                    (
                        "644da7468d890a2a8600f7fa141ee3298f00bad8",
                        "b2621ea7e5644d743e5a8a5717e40b8f8ba3bd7d",
                    ),
                    (
                        "fdcdfb22c02c796b97ee6406bbd76025a645822f",
                        "7b2176a6a8fb22ef8a1b960656b36061f1356aa9",
                    ),
                    (
                        "86f8175769191ef6231cbafd04b72c4a23bd4720",
                        "5c9abbbf953407810a3efccebebcef7cf3b2bb5c",
                    ),
                    (
                        "ba73b310a8609de4eb4f0ed2284c6d2d9a6fab53",
                        "dba7f57e2484780a4de9a2d13617d2c368be433e",
                    ),
                )
            ]
            mappings.append(
                {
                    "sourceNode": "github:jake-the-jake/Closy:pr/31",
                    "sourceCommit": "f99ab295677556a0df37af25c7a1b8541a648ad3",
                    "destinationCommit": "0f7e10c98a75e15a061aa00e538e8b0a4526c68d",
                    "disposition": "replayed",
                }
            )
        nodes.append(
            {
                "id": node_id,
                "repository": row["repository"],
                "pullRequest": row["number"],
                "capabilityRole": _capability_role(str(row["title"])),
                "branch": row["branch"],
                "baseRef": row["baseBranch"],
                "baseSha": row["baseSha"],
                "mergeBase": row.get("mergeBase", row["baseSha"]),
                "ahead": row["layerAhead"],
                "behind": row["layerBehind"],
                "changedFileCount": row["changedFileCount"],
                "state": "OPEN" if row.get("state") is None else row["state"],
                "role": row.get("role", "integrated_stack"),
                "headSha": row["headSha"],
                "parentIds": parent_ids,
                "dependencyIds": dependency_ids,
                "uniqueCommitRange": f"{row['baseSha']}..{row['headSha']}",
                "integrationMappings": mappings,
                "sourceOnly": source_only,
                "superseded": superseded,
                "mergeEligible": not source_only,
                "neverMergeWith": (["github:jake-the-jake/Closy:pr/28"] if pr_number == 25 else []),
                "latestExactHeadWorkflows": workflows,
            }
        )
    zeroone_id = "github:jake-the-jake/ZeroOne:pr/2"
    nodes.append(
        {
            "id": zeroone_id,
            "repository": zeroone_row["repository"],
            "pullRequest": zeroone_row["number"],
            "capabilityRole": "candidate_static_source",
            "branch": zeroone_row["branch"],
            "baseRef": zeroone_row["baseBranch"],
            "baseSha": zeroone_row["baseSha"],
            "mergeBase": zeroone_row["mergeBase"],
            "ahead": zeroone_row["layerAhead"],
            "behind": zeroone_row["layerBehind"],
            "changedFileCount": zeroone_row["changedFileCount"],
            "state": zeroone_row["state"],
            "role": zeroone_row["role"],
            "headSha": zeroone_row["headSha"],
            "parentIds": [],
            "dependencyIds": [],
            "uniqueCommitRange": f"{zeroone_row['baseSha']}..{zeroone_row['headSha']}",
            "integrationMappings": [],
            "sourceOnly": False,
            "superseded": False,
            "mergeEligible": True,
            "neverMergeWith": [],
            "latestExactHeadWorkflows": zeroone_row["latestExactHeadWorkflows"],
        }
    )
    zeroone_dynamic_id = "github:jake-the-jake/ZeroOne:pr/3"
    edges.append({"from": zeroone_id, "to": zeroone_dynamic_id, "kind": "dependency"})
    nodes.append(
        {
            "id": zeroone_dynamic_id,
            "repository": zeroone_dynamic_row["repository"],
            "pullRequest": zeroone_dynamic_row["number"],
            "capabilityRole": "compiled_dynamic_source",
            "branch": zeroone_dynamic_row["branch"],
            "baseRef": zeroone_dynamic_row["baseBranch"],
            "baseSha": zeroone_dynamic_row["baseSha"],
            "mergeBase": zeroone_dynamic_row["mergeBase"],
            "ahead": zeroone_dynamic_row["layerAhead"],
            "behind": zeroone_dynamic_row["layerBehind"],
            "changedFileCount": zeroone_dynamic_row["changedFileCount"],
            "state": zeroone_dynamic_row["state"],
            "role": zeroone_dynamic_row["role"],
            "headSha": zeroone_dynamic_row["headSha"],
            "parentIds": [],
            "dependencyIds": [zeroone_id],
            "uniqueCommitRange": (
                f"{zeroone_dynamic_row['baseSha']}..{zeroone_dynamic_row['headSha']}"
            ),
            "integrationMappings": [],
            "sourceOnly": False,
            "superseded": False,
            "mergeEligible": True,
            "neverMergeWith": [],
            "latestExactHeadWorkflows": zeroone_dynamic_row["latestExactHeadWorkflows"],
        }
    )
    zeroone_transport_id = "github:jake-the-jake/ZeroOne:pr/4"
    edges.append({"from": zeroone_dynamic_id, "to": zeroone_transport_id, "kind": "parent"})
    nodes.append(
        {
            "id": zeroone_transport_id,
            "repository": zeroone_transport_row["repository"],
            "pullRequest": zeroone_transport_row["number"],
            "capabilityRole": "compiled_mechanical_transport_v2_source",
            "branch": zeroone_transport_row["branch"],
            "baseRef": zeroone_transport_row["baseBranch"],
            "baseSha": zeroone_transport_row["baseSha"],
            "mergeBase": zeroone_transport_row["mergeBase"],
            "ahead": zeroone_transport_row["layerAhead"],
            "behind": zeroone_transport_row["layerBehind"],
            "changedFileCount": zeroone_transport_row["changedFileCount"],
            "state": zeroone_transport_row["state"],
            "role": zeroone_transport_row["role"],
            "headSha": zeroone_transport_row["headSha"],
            "parentIds": [zeroone_dynamic_id],
            "dependencyIds": [zeroone_dynamic_id],
            "uniqueCommitRange": (
                f"{zeroone_transport_row['baseSha']}..{zeroone_transport_row['headSha']}"
            ),
            "integrationMappings": [],
            "sourceOnly": False,
            "superseded": False,
            "mergeEligible": True,
            "neverMergeWith": [],
            "latestExactHeadWorkflows": zeroone_transport_row["latestExactHeadWorkflows"],
        }
    )
    stack["schemaVersion"] = 3
    stack["graphVersion"] = "closy.cross_repository_pr_dag.v3"
    stack["topology"] = "explicit_dag"
    stack["pullRequests"] = rows
    external_pull_requests = [
        zeroone_row,
        zeroone_dynamic_row,
        zeroone_transport_row,
    ]
    stack["externalPullRequests"] = external_pull_requests
    stack["nodes"] = nodes
    stack["edges"] = edges
    stack.pop("sequentialMergeOrder", None)
    stack.pop("sequentialMergeRehearsal", None)
    stack["topologicalOrder"] = _topological_order(nodes, edges)
    stack["graphCounts"] = {
        "closyPullRequests": len(rows),
        "externalPullRequests": len(external_pull_requests),
        "nodes": len(nodes),
        "edges": len(edges),
    }
    stack["validation"] = {
        "acyclic": True,
        "exactMergeBases": True,
        "allDeclaredParentsZeroBehind": True,
        "businessPatchMappingsComplete": True,
        "publishedParentsUnmoved": True,
        "mode": "read_only_git_graph_verification",
    }
    issues = validate_pr_dag(stack)
    if issues:
        raise ValueError(";".join(issues))
    return stack


def _topological_order(nodes: list[dict[str, object]], edges: list[dict[str, str]]) -> list[str]:
    declared = [str(node["id"]) for node in nodes]
    position = {node_id: index for index, node_id in enumerate(declared)}
    incoming: dict[str, set[str]] = {node_id: set() for node_id in declared}
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in declared}
    for edge in edges:
        source = edge["from"]
        target = edge["to"]
        incoming[target].add(source)
        outgoing[source].add(target)
    ready = [node_id for node_id in declared if not incoming[node_id]]
    result: list[str] = []
    while ready:
        ready.sort(key=position.__getitem__)
        node_id = ready.pop(0)
        result.append(node_id)
        for target in sorted(outgoing[node_id], key=position.__getitem__):
            incoming[target].discard(node_id)
            if not incoming[target] and target not in result and target not in ready:
                ready.append(target)
    if len(result) != len(declared):
        raise ValueError("pull-request dependency graph contains a cycle")
    return result


def _capability_role(title: str) -> str:
    return "_".join(
        "".join(character.lower() if character.isalnum() else " " for character in title).split()
    )


def _replace_legacy_truth_terms(value: object) -> object:
    if isinstance(value, str):
        return value.replace(
            "actualZeroOneRuntimeExecuted", "actualZeroOneStaticCookExecutedThisInvocation"
        )
    if isinstance(value, list):
        return [_replace_legacy_truth_terms(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace_legacy_truth_terms(item) for key, item in value.items()}
    return value


def _closy_run(run_id: str, conclusion: str) -> dict[str, object] | None:
    if not run_id:
        return None
    forge_29_job_runs = {
        "33329481046",
        "33342673147",
        "33380042123",
        "33393781144",
        "33409665461",
        "33423822705",
        "33452856012",
        "33464425080",
        "33470303559",
        "33475901299",
        "33503777760",
        "33505903385",
        "33511517533",
        "33524394054",
        "33533707412",
        "33547909132",
    }
    job_count = 29 if run_id in forge_29_job_runs else 26
    result: dict[str, object] = {
        "exactHead": True,
        "runId": run_id,
        "workflow": "Closy Forge",
        "conclusion": conclusion,
        "forgeJobCount": job_count,
        "forgeJobCountSemantics": (
            "all jobs in the Closy Forge workflow; unrelated skipped checks are excluded"
        ),
    }
    if conclusion == "SUCCESS":
        result["successfulForgeJobCount"] = job_count
    else:
        result.update(FAILED_RUN_JOB_COUNTS[run_id])
    return result


def _as_int(value: object) -> int:
    if not isinstance(value, int | str):
        raise TypeError("expected integer-compatible manifest value")
    return int(value)


def _workflow(name: str, run_id: str, conclusion: str, job_count: int) -> dict[str, object]:
    return {
        "workflow": name,
        "runId": run_id,
        "exactHead": True,
        "conclusion": conclusion,
        "jobCount": job_count,
    }


def _normalise_workflows(run: object) -> list[dict[str, object]]:
    if not isinstance(run, dict):
        return []
    jobs = run.get("jobs")
    if isinstance(jobs, list):
        conclusions = {str(job.get("conclusion")) for job in jobs if isinstance(job, dict)}
        conclusion = "SUCCESS" if conclusions == {"SUCCESS"} else "FAILURE"
        return [_workflow("Closy Forge", str(run["runId"]), conclusion, len(jobs))]
    return [
        _workflow(
            str(run.get("workflow", "Closy Forge")),
            str(run["runId"]),
            str(run.get("conclusion", "UNKNOWN")),
            int(run.get("forgeJobCount", run.get("jobCount", 0))),
        )
    ]


def _source_tree_hash(paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        path = REPO_ROOT / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
