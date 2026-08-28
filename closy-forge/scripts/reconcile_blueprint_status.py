from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.blueprint.pr_dag import validate_pr_dag
from closy_forge.blueprint.status import build_status_model, render_status_summary

EVIDENCE_ANCHOR = "a481ba26a424bd91607b8c1d41b6173a2c9579d9"
VERSION = "closy.blueprint_coverage.evidence_security_integrity.v2"
GENERATED_BY = "Scoped gate, evidence security, and PR DAG reconciliation at " + EVIDENCE_ANCHOR
PR23_FINAL_RUN = "33150483293"
PR23_FINAL_HEAD = EVIDENCE_ANCHOR
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

PHASE10_PATHS = [
    "closy-forge/src/closy_forge/zeroone/integration.py",
    "closy-forge/src/closy_forge/zeroone/request.py",
    "closy-forge/src/closy_forge/zeroone/tool.py",
    "closy-forge/src/closy_forge/zeroone/validation.py",
    "closy-forge/docs/evidence/phase10_zeroone_static/execution_evidence.json",
]
PHASE10_TESTS = [
    "closy-forge/tests/unit/test_zeroone_static_integration.py",
    "closy-forge/tests/unit/test_zeroone_execution_evidence.py",
]
PHASE10_EVIDENCE = [
    (
        "the compiled pinned ZeroOneProcess Release executable ran headlessly on canonical D0 "
        "T-shirt and layered-asymmetric packages"
    ),
    (
        "both packages produced real mesh, cluster, hierarchy, page-pack, material, and garment "
        "stitch-row derivatives"
    ),
    (
        "clean miss, cache hit, and second clean miss outputs agree while canonical authority "
        "and fallback hashes remain unchanged"
    ),
    (
        "optional zeroone/static-d0 namespaces validate and T-shirt deletion/rebuild reproduces "
        "the canonical derivative hash"
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
            "Validated only for the exact task-owned D0 CPU/static profile; every conventional "
            "GLB fallback remains mandatory."
        ),
    },
    "BP-08-I-GEOMETRY-PROVIDERS": {
        "status": "partial",
        "summary": (
            "The pinned task-owned ZeroOne provider now produces validated optional static "
            "derivatives from canonical packages."
        ),
        "limitations": (
            "Only two D0 project-authored fixtures and one Windows CPU/static toolchain ran; "
            "provider breadth, visual review, mobile, and dynamic tiers remain open."
        ),
    },
    "BP-09-Z1": {
        "status": "partial",
        "summary": (
            "ZeroOne Z1 has a historical local pass for the exact Windows MSVC Release D0 "
            "CPU/headless static T-shirt and layered-asymmetric profile."
        ),
        "limitations": (
            "The source PR was owner-closed unmerged and current ZeroOne master is not yet "
            "requalified; global Z1 and Phase 10 remain partial."
        ),
        "nextAction": (
            "Requalify current ZeroOne master and refresh paired Closy static evidence."
        ),
    },
    "BP-09-GEOMOTREE": {
        "status": "partial",
        "summary": (
            "A real bounded GeomoTree/Nanite CPU static garment route now imports Closy GLB "
            "semantics and publishes validated derivatives."
        ),
        "limitations": (
            "The route covers T-shirt stitch rows and two D0 fixtures only; broad garment "
            "semantics and dynamic deformation are not established."
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
            "Evaluation now consumes authoritative C3, trained synthetic D0, and real ZeroOne "
            "static execution reports without promoting global readiness."
        ),
        "limitations": (
            "C3 still fails, and independent real/public, provider, mobile, private-user, licence, "
            "and human-review evidence remains incomplete."
        ),
    },
    "BP-17-PHASE-10": {
        "status": "partial",
        "summary": (
            "Blueprint Phase 10 now has real pinned ZeroOne D0 CPU/static execution and optional "
            "derivative packaging for two required garments."
        ),
        "limitations": (
            "Phase 10 remains partial without turntable or human visual review, broader "
            "garment/provider evidence, mobile execution, and other blueprint profiles."
        ),
        "nextAction": (
            "Run human visual review and broaden provider/mobile evidence; do not begin Phase 11 "
            "while C3 remains partial."
        ),
    },
    "BP-18-GATE-Z1": {
        "status": "partial",
        "summary": ("Gate Z1 retains a historical local scoped pass; global Z1 remains partial."),
        "limitations": (
            "Current ZeroOne master, durable workflow execution, mobile, dynamic deformation, "
            "provider breadth, and human review are not established."
        ),
        "nextAction": "Requalify current master, then regenerate paired scoped Z1 evidence.",
    },
    "BP-18-GATE-C3": {
        "status": "partial",
        "summary": (
            "C3-Binding-D0 is the master-blueprint dynamic-binding gate and requires separate "
            "literal requalification against topology, binding, poses, topology hash, and frames."
        ),
        "limitations": (
            "Earlier reports conflated C3 binding with the stricter PHY1 physical campaign; "
            "neither a fresh binding pass nor a PHY1 pass is claimed here."
        ),
        "nextAction": "Run literal C3-Binding-D0 independently from PHY1-SingleLayer-D0.",
    },
    "BP-20-RESEARCH-PROTOTYPE": {
        "status": "partial",
        "summary": (
            "The research prototype now includes corrected integrity evidence, a trained "
            "synthetic D0 model, and real optional ZeroOne CPU/static derivatives."
        ),
        "limitations": (
            "C3, independent fidelity, mobile, broader provider, private-user, licence, and "
            "human-review gates remain open; Alpha is not reached."
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
    "BP-20-RESEARCH-PROTOTYPE": True,
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
        "Requalify current ZeroOne master and refresh paired scoped Z1; keep global Phase 10 "
        "partial pending broader provider, mobile, and human-review evidence."
    ),
    "BP-17-PHASE-11": (
        "Begin actual dynamic deformation only after scoped C3 and real ZeroOne static gates pass."
    ),
    "BP-18-GATE-C3": (
        "Requalify the five literal C3-Binding-D0 requirements separately from the stricter "
        "PHY1-SingleLayer-D0 physical campaign."
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
    coverage["generatedBy"] = GENERATED_BY
    for row in coverage["rows"]:
        row_id = str(row["id"])
        update = ROW_UPDATES.get(row_id)
        if update:
            row.update(update)
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
    rows = list(stack["pullRequests"])  # type: ignore[arg-type]
    for row in rows:
        if int(row["number"]) != 23:
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
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        node_id = f"github:jake-the-jake/Closy:pr/{row['number']}"
        parent_ids: list[str] = []
        if index:
            parent_id = f"github:jake-the-jake/Closy:pr/{rows[index - 1]['number']}"
            parent_ids.append(parent_id)
            edges.extend(
                (
                    {"from": parent_id, "to": node_id, "kind": "parent"},
                    {"from": parent_id, "to": node_id, "kind": "dependency"},
                )
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
                "headSha": row["headSha"],
                "parentIds": parent_ids,
                "dependencyIds": list(parent_ids),
                "uniqueCommitRange": f"{row['baseSha']}..{row['headSha']}",
                "integrationMappings": [],
                "sourceOnly": False,
                "superseded": False,
                "mergeEligible": True,
                "neverMergeWith": [],
                "latestExactHeadForgeRun": row["latestExactHeadForgeRun"],
            }
        )
    stack["schemaVersion"] = 2
    stack["graphVersion"] = "closy.pr_stack.dag.v2"
    stack["topology"] = "explicit_dag"
    stack["nodes"] = nodes
    stack["edges"] = edges
    stack["validation"] = {
        "acyclic": True,
        "exactMergeBases": True,
        "replayedCommonAncestryAbsent": True,
        "mode": "read_only_git_graph_verification",
    }
    issues = validate_pr_dag(stack)
    if issues:
        raise ValueError(";".join(issues))
    return stack


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


if __name__ == "__main__":
    raise SystemExit(main())
