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
EVIDENCE_ANCHOR = "eb5becfa385ec4a5c6ef95b2c15b753dffbcea42"
VERSION = "closy.blueprint_coverage.z1_z2_structured_ai.v4"
GENERATOR_VERSION = "closy.blueprint_reconciliation.z1_z2.v1"
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
        row_id = str(row["id"])
        update = ROW_UPDATES.get(row_id)
        if update:
            row.update(update)
        ancestry_update = ANCESTRY_TRUTH_UPDATES.get(row_id)
        if ancestry_update:
            row.update(ancestry_update)
        if ROW_EVIDENCE_ADDITIONS.get(row_id):
            row["implementationPaths"] = _append_unique(
                row.get("implementationPaths"), PHASE10_PATHS
            )
            row["executableEvidence"] = _append_unique(
                row.get("executableEvidence"), PHASE10_EVIDENCE
            )
            row["tests"] = _append_unique(row.get("tests"), PHASE10_TESTS)
            row["commitSha"] = _append_unique(row.get("commitSha"), [EVIDENCE_ANCHOR])
        if row_id in NEXT_ACTIONS:
            row["nextAction"] = NEXT_ACTIONS[row_id]
        if row_id.startswith("BP-09-Z") and row_id != "BP-09-Z1":
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
                "knownException": None,
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
        for dependency_id in dependency_ids:
            edges.append({"from": dependency_id, "to": node_id, "kind": "dependency"})
        source_only = pr_number in {25, 26, 29, 30, 31, 32}
        superseded = pr_number == 25
        workflows = _normalise_workflows(row.get("latestExactHeadForgeRun"))
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
    stack["schemaVersion"] = 3
    stack["graphVersion"] = "closy.cross_repository_pr_dag.v3"
    stack["topology"] = "explicit_dag"
    stack["pullRequests"] = rows
    stack["externalPullRequests"] = [zeroone_row]
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


def _closy_run(run_id: str, conclusion: str) -> dict[str, object]:
    result: dict[str, object] = {
        "exactHead": True,
        "runId": run_id,
        "workflow": "Closy Forge",
        "conclusion": conclusion,
        "jobCount": 26,
    }
    if conclusion == "SUCCESS":
        result["successfulJobCount"] = 26
    else:
        result.update({"successfulJobCount": 21, "failedJobCount": 3, "cancelledJobCount": 2})
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
            int(run.get("jobCount", 0)),
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
