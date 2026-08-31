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
EVIDENCE_ANCHOR = "64fd0386dbb9dec5f91d6e154ebf96a2f3baf2dd"
STALE_INVALID_EVIDENCE_ANCHORS = {
    "076cb93c95e0d98052332e52622a15d06c6b6a4e",
}
VERSION = "closy.blueprint_coverage.d0_evidence_integrity_v4.v11"
GENERATOR_VERSION = "closy.blueprint_reconciliation.d0_evidence_integrity_v4.v8"
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
        11,
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
        if (
            row_id in NEXT_ACTIONS
            and row_id not in CURRENT_PROGRESSION_UPDATES
            and row_id not in PHY1_V2_PROGRESSION_UPDATES
            and row_id not in TRUTH_RUNTIME_PROGRESSION_UPDATES
            and row_id not in FINAL_D0_PHY1_V3_PROGRESSION_UPDATES
            and row_id not in UNIT_E_INTEGRITY_PROGRESSION_UPDATES
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
    model = build_status_model(coverage, stack, evidence_anchor_sha=EVIDENCE_ANCHOR)
    (docs / "current_blueprint_status.json").write_text(
        json.dumps(model, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (docs / "BLUEPRINT_STATUS_SUMMARY.md").write_text(
        render_status_summary(model), encoding="utf-8", newline="\n"
    )
    return 0


def _append_unique(current: object, additions: list[str]) -> list[str]:
    values = list(current) if isinstance(current, list) else []
    return values + [value for value in additions if value not in values]


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
    stack["schemaVersion"] = 3
    stack["graphVersion"] = "closy.cross_repository_pr_dag.v3"
    stack["topology"] = "explicit_dag"
    stack["pullRequests"] = rows
    stack["externalPullRequests"] = [zeroone_row, zeroone_dynamic_row]
    stack["nodes"] = nodes
    stack["edges"] = edges
    stack.pop("sequentialMergeOrder", None)
    stack.pop("sequentialMergeRehearsal", None)
    stack["topologicalOrder"] = _topological_order(nodes, edges)
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
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
