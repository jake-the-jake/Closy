from __future__ import annotations

import hashlib
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

_STACK_ROWS = {
    52: {
        "baseBranch": "codex/closy-forge-d0-strict-c3-confirmation-v5",
        "baseSha": "e062a30ba295ed27334622916ddb449fd76e2166",
        "branch": "codex/closy-forge-phy1-topology-strategy3-diagnosis-v1",
        "headSha": "8dd7a547debf038e9e27c48cf8e42009ae69ac3a",
        "role": "phy1_topology_strategy3_diagnosis_integrity_error",
        "title": "Forge Unit O: bounded PHY1 Strategy 3 diagnosis",
        "capabilityRole": "forge_unit_o_bounded_phy1_strategy_3_diagnosis",
    },
    53: {
        "baseBranch": "codex/closy-forge-phy1-topology-strategy3-diagnosis-v1",
        "baseSha": "8dd7a547debf038e9e27c48cf8e42009ae69ac3a",
        "branch": "codex/closy-forge-evidence-authority-recovery-v2",
        "headSha": "b8d222dadbe092e25604b838e7ad219d6a1c114b",
        "role": "evidence_authority_recovery_v2",
        "title": "Forge: evidence authority recovery foundation v2",
        "capabilityRole": "forge_evidence_authority_recovery_foundation_v2",
    },
    54: {
        "baseBranch": "codex/closy-forge-evidence-authority-recovery-v2",
        "baseSha": "b8d222dadbe092e25604b838e7ad219d6a1c114b",
        "branch": "codex/closy-forge-d0-disjoint-tshirt-confirmation-v3",
        "headSha": "0c45587371165f1c5f3e33934ee2cbf5156f9e02",
        "role": "d0_disjoint_tshirt_confirmation_v3_failed_absolute_gates",
        "title": "Forge Unit T: untouched D0 T-shirt confirmation v3",
        "capabilityRole": "forge_unit_t_untouched_d0_t_shirt_confirmation_v3",
    },
    55: {
        "baseBranch": "codex/closy-forge-d0-disjoint-tshirt-confirmation-v3",
        "baseSha": "0c45587371165f1c5f3e33934ee2cbf5156f9e02",
        "branch": "codex/closy-forge-phy1-final-strategy3-v2",
        "headSha": "f56fc44ccf7173155186a30b4f4978454fb3debf",
        "role": "final_strategy3_v2_dependency_blocked_before_official_seed",
        "title": "Forge Unit U: final Strategy 3 confirmation v2",
        "capabilityRole": "forge_unit_u_final_strategy_3_confirmation_v2",
    },
}


def reconcile_coverage(
    repo_root: Path, coverage: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    result = deepcopy(coverage)
    result["version"] = "closy.blueprint_coverage.truth_authority_integrity_v3.v23"
    rows = {str(row["id"]): row for row in result["rows"]}
    unit_t = overlay["unitT"]
    unit_u = overlay["unitU"]
    budget = overlay["budgetStateBeforeSuccessorAuthority"]

    rows["BP-17-PHASE-03"]["summary"] = (
        "Blueprint phase 3 has bounded iterative public-D0 fitting, but the untouched Unit T v3 "
        f"confirmation failed its absolute gates after {unit_t['attemptsExecutedCount']} executed "
        f"attempts and {unit_t['predictionArtifactProducedCount']} prediction artifacts."
    )
    rows["BP-17-PHASE-03"]["limitations"] = (
        "Unit T had zero strict complete pixel-route compile-valid candidates; D0-RP-03 failed. "
        "Private-user fitting, learned generalisation, depth estimation, and product-calibrated "
        "acceptance remain unproven."
    )
    rows["BP-17-PHASE-04"]["summary"] = (
        "The frozen source-only atlas route remains known-target engineering evidence. Unit T "
        f"actually evaluated {unit_t['appearanceRowsActuallyEvaluatedCount']} of "
        f"{unit_t['appearanceRowsScheduledCount']} scheduled appearance rows and passed "
        f"{unit_t['appearanceGatePassCount']}; D0-RP-07 failed."
    )
    rows["BP-17-PHASE-04"]["nextAction"] = (
        "Use the Unit T failure atlas to design a new development-only appearance route; do not "
        "promote the frozen v3 route."
    )
    rows["BP-17-PHASE-06"]["summary"] = (
        "Strategy 3 is reserved and consumed. Unit U passed 8/8 public conformance but ended as "
        f"{unit_u['literalOutcome']} before seed, fixture, oracle, admission, or candidate "
        "creation."
    )
    rows["BP-17-PHASE-06"]["limitations"] = (
        "No post-topology candidate, neutral preflight, full PHY1, or CCD run exists. The "
        f"topology-strategy budget is {budget['derived']['remaining']['topology_strategy']}; the "
        "remaining candidate attempt is not eligible until a separately authorised admission."
    )
    rows["BP-17-PHASE-06"]["nextAction"] = (
        "Publish and validate the repository-blob successor authority without restoring topology "
        "budget or changing frozen Strategy 3 scientific bytes."
    )
    rows["BP-18-GATE-C3"]["summary"] = (
        "Pre-topology strict C3 remains a scoped 8/8 positional/analytic pass. Unit U created no "
        "candidate, so no post-topology strict or trajectory C3 claim exists."
    )
    rows["BP-18-GATE-C3"]["limitations"] = (
        "The pre-topology result cannot satisfy post-topology C3; Strategy 3 admission was not "
        "executed and zero topology strategies remain."
    )
    rows["BP-09-Z1"]["nextAction"] = (
        "Scoped compiled static Z1 evidence already exists. Do not rebuild a processor as a "
        "substitute for qualification; run exact-candidate Z1 only after an admitted candidate."
    )
    rows["BP-20-RESEARCH-PROTOTYPE"]["summary"] = (
        "Unit T is a completed scientific failure at its absolute gates. Unit U is a distinct "
        "pre-seed infrastructure failure; no scientific Strategy 3 admission or candidate exists."
    )
    rows["BP-20-RESEARCH-PROTOTYPE"]["nextAction"] = overlay["nextAction"]

    generated = result["generatedBy"]
    generated["generatorVersion"] = "closy.blueprint_publication.truth_authority_v3.v20"
    generated["declaredInputPaths"] = _append_unique(
        generated["declaredInputPaths"],
        [
            "closy-forge/scripts/build_truth_authority_integrity_v3.py",
            "closy-forge/src/closy_forge/truth_authority_integrity_v3/truth_overlay.py",
            "closy-forge/src/closy_forge/truth_authority_integrity_v3/status_reconciliation.py",
            "closy-forge/fixtures/truth_authority_integrity_v3/external_exact_head_attestations.json",
        ],
    )
    generated["sourceTreeHash"] = _source_tree_hash(repo_root, generated["declaredInputPaths"])
    return result


def reconcile_stack(
    repo_root: Path, stack: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    result = deepcopy(stack)
    attestations = {
        int(row["pullRequest"]): row for row in overlay["externalExactHeadAttestations"]
    }
    rows = {int(row["number"]): row for row in result["pullRequests"]}
    nodes = {
        int(node["pullRequest"]): node
        for node in result["nodes"]
        if node["repository"] == "jake-the-jake/Closy"
    }
    for number, declared in _STACK_ROWS.items():
        attestation = attestations[number]
        base = declared["baseSha"]
        head = declared["headSha"]
        ahead = _git_count(repo_root, f"{base}..{head}")
        changed = len(_git_lines(repo_root, "diff", "--name-only", base, head))
        conclusion = "SUCCESS" if attestation["result"] == "pass" else "FAILURE"
        successful = 29 if conclusion == "SUCCESS" else 25
        exact_run = {
            "exactHead": True,
            "runId": attestation["exactHeadCiRun"],
            "workflow": "Closy Forge",
            "conclusion": conclusion,
            "forgeJobCount": 29,
            "successfulForgeJobCount": successful,
            "forgeJobCountSemantics": "all jobs in the exact-head Closy Forge workflow",
        }
        row = rows[number]
        row.update(
            {
                "baseBranch": declared["baseBranch"],
                "baseSha": base,
                "branch": declared["branch"],
                "changedFileCount": changed,
                "headSha": head,
                "knownException": None,
                "latestExactHeadForgeRun": exact_run,
                "layerAhead": ahead,
                "layerBehind": 0,
                "layerCommitCount": ahead,
                "mergeBase": base,
                "role": declared["role"],
                "title": declared["title"],
            }
        )
        node = nodes[number]
        parent = number - 1
        parent_ids = [f"github:jake-the-jake/Closy:pr/{parent}"]
        node.update(
            {
                "ahead": ahead,
                "baseRef": declared["baseBranch"],
                "baseSha": base,
                "behind": 0,
                "branch": declared["branch"],
                "capabilityRole": declared["capabilityRole"],
                "changedFileCount": changed,
                "dependencyIds": parent_ids,
                "headSha": head,
                "latestExactHeadWorkflows": [
                    {
                        "workflow": "Closy Forge",
                        "runId": attestation["exactHeadCiRun"],
                        "exactHead": True,
                        "conclusion": conclusion,
                        "jobCount": 29,
                        "successfulJobCount": successful,
                    }
                ],
                "mergeBase": base,
                "parentIds": parent_ids,
                "role": declared["role"],
                "uniqueCommitRange": f"{base}..{head}",
            }
        )
        if number == 55:
            node["latestExactHeadWorkflows"][0]["failedJobIds"] = attestation["failedJobIds"]

    affected = {f"github:jake-the-jake/Closy:pr/{number}" for number in _STACK_ROWS}
    result["edges"] = [
        edge
        for edge in result["edges"]
        if edge["from"] not in affected and edge["to"] not in affected
    ]
    for number in _STACK_ROWS:
        parent_id = f"github:jake-the-jake/Closy:pr/{number - 1}"
        node_id = f"github:jake-the-jake/Closy:pr/{number}"
        result["edges"].extend(
            [
                {"from": parent_id, "kind": "parent", "to": node_id},
                {"from": parent_id, "kind": "dependency", "to": node_id},
            ]
        )
    result["topologicalOrder"] = _topological_order(result["nodes"], result["edges"])
    result["graphCounts"] = {
        "closyPullRequests": len(result["pullRequests"]),
        "externalPullRequests": len(result["externalPullRequests"]),
        "nodes": len(result["nodes"]),
        "edges": len(result["edges"]),
    }
    return result


def build_resume(
    overlay: dict[str, Any], *, source_anchor: str, branch: str, pull_request: int
) -> dict[str, Any]:
    unit_t = overlay["unitT"]
    unit_u = overlay["unitU"]
    return {
        "schemaVersion": 1,
        "machineResumeVersion": "closy.active_blueprint_resume.truth_authority_v3.v14",
        "activeLane": "Unit Y0 truth repair and authority-integrity hardening",
        "branch": branch,
        "pullRequest": pull_request,
        "evidenceHead": source_anchor,
        "sourceEvidenceAnchor": source_anchor,
        "finalPublicationHead": None,
        "finalHeadAttestationLocation": "draft PR body and exact-head workflow",
        "sourceAnchorIsSelfReferential": False,
        "localHeadAtResumeSource": source_anchor,
        "remoteHeadAtResumeSource": source_anchor,
        "pendingCIAtEvidenceHead": True,
        "latestFinishedParentPublicationHead": unit_u["finalPublicationHead"],
        "parent": {
            "branch": "codex/closy-forge-phy1-final-strategy3-v2",
            "pullRequest": 55,
            "sha": unit_u["finalPublicationHead"],
            "exactHeadWorkflow": unit_u["exactHeadCi"]["run"],
            "forgeJobsPassed": unit_u["exactHeadCi"]["passedJobs"],
            "forgeJobsTotal": 29,
            "literalCiResult": unit_u["exactHeadCi"]["result"],
        },
        "remainingBudgets": {
            "candidateAttempts": 1,
            "seamModels": 0,
            "topologyStrategies": 0,
        },
        "budgetState": {
            "strategy3Reserved": True,
            "strategy3Consumed": True,
            "strategy3ScientificAdmissionExecuted": False,
            "untouchedStrategy3ConfirmationAttemptConsumed": False,
        },
        "conditionalUnits": {
            "Y0": "implementation_complete_publication_and_exact_head_ci_pending",
            "Y1": "ineligible_until_unit_y0_exact_head_ci_passes",
            "Z": "ineligible_until_strategy3_v3_admission",
            "AA": "ineligible_no_unit_z_candidate",
            "AB": "ineligible_no_post_topology_prerequisites",
            "AC": "unconditional_after_topology_sequence_literal_outcome",
            "AD": "conditional_on_d0_v4_development_admission",
            "AE": "pending_literal_outcomes",
        },
        "gates": {
            "D0-DisjointTshirt-v3": unit_t["literalOutcome"],
            "PHY1-Topology-Strategy3-Confirmation-D0-v2": unit_u["literalOutcome"],
            "ResearchPrototype-D0-matrix-v3-core": "partial_7_pass_4_fail_0_not_run",
            "ResearchPrototype-D0-matrix-v3-supplemental": "2_pass_0_fail_2_not_run",
            "S-core-truth-successor": "integrity_predicates_pass",
            "S-D0-authority-successor": "integrity_predicates_pass",
            "S-PHY-authority-successor": "integrity_predicates_pass",
            "C3": "pre_topology_scoped_pass_post_topology_unproven",
            "Z1": "scoped_static_pass_exact_candidate_unproven",
            "Z2": "failed_non_solver_evidence_only",
        },
        "unitTResult": deepcopy(unit_t),
        "unitUResult": deepcopy(unit_u),
        "unitSSuccessor": deepcopy(overlay["unitSSuccessor"]),
        "truthOverlay": {
            "version": overlay["overlayVersion"],
            "digest": overlay["overlayDigest"],
            "consumerPolicy": overlay["consumerPolicy"],
        },
        "stopReason": "unit_y0_exact_head_ci_required_before_unit_y1",
        "exactNextAction": overlay["nextAction"],
        "nextHandoff": {
            "selection": "unit_y1_after_y0_exact_head_pass",
            "firstUnmetPrerequisite": "unit_y0_exact_head_forge_and_sealed_v2_failure_lane_pass",
            "safestEvidenceAction": "publish_y0_without_touching_frozen_strategy3_bytes",
        },
        "mergeAuthorised": False,
        "unsupportedEvidenceClasses": [
            "strategy3_repository_blob_admission",
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
        ],
    }


def render_resume(resume: dict[str, Any]) -> str:
    unit_t = resume["unitTResult"]
    unit_u = resume["unitUResult"]
    return f"""# Active Blueprint Resume

## Current Lane

- Unit: `Y0` truth repair and authority-integrity hardening.
- Branch: `{resume['branch']}`
- Draft PR: `#{resume['pullRequest']}`
- Source evidence anchor: `{resume['sourceEvidenceAnchor']}`
- Exact parent: `{resume['parent']['sha']}` (PR #55)
- Final publication head: externally attested after publication, not self-referential here.

## Literal State

- Unit T: `{unit_t['literalOutcome']}`; {unit_t['attemptsExecutedCount']}/64 attempts executed,
  {unit_t['predictionArtifactProducedCount']} artifacts, {unit_t['explicitAbstentionCount']}
  abstentions, 48 compile rows evaluated, zero strict complete pixel-route compile-valid
  candidates, and {unit_t['appearanceRowsActuallyEvaluatedCount']}/24 appearance rows evaluated
  with zero passes.
- Unit T rows: D0-RP-03 `fail`, D0-RP-04: `pass`, D0-RP-06 `fail`, D0-RP-07 `fail`.
- Unit U: `{unit_u['literalOutcome']}`; pre-seed infrastructure failure, not a scientific failure.
- Unit U seed, untouched fixture, oracle reveal, admission, and candidate: none.
- Supplemental matrix: D0-RP-09 and D0-RP-14 pass; D0-RP-10 and D0-RP-11 are not run.
- Strategy 3 is reserved and consumed; admission was not executed. Remaining budgets: seam models
  `0`, topology strategies `0`, canonical-candidate attempts `1`.
- The immutable v2 failure remains mandatory in its dedicated sealed-failure CI lane. Do not
  relock, rerun, or weaken the historical test.

## Next Action

{resume['exactNextAction']} Unit Y1 remains ineligible until both required Y0 lanes pass at the
exact published head.
"""


def render_master_checkpoint(
    current: str,
    overlay: dict[str, Any],
    *,
    source_anchor: str,
    branch: str,
    pull_request: int,
) -> str:
    suffix = current.split("## Status Vocabulary", 1)[1]
    counts = overlay["coverage"]["statusCounts"]
    unit_t = overlay["unitT"]
    unit_u = overlay["unitU"]
    prefix = f"""# Master Blueprint Progress Ledger

This ledger records executable evidence against
`Closy_AI_3D_Garment_and_ZeroOne_Integration_Master_Blueprint.md`. Machine-readable status,
coverage, stack topology, and the versioned successor truth overlay are the readiness authority;
historical prose below is append-only context.

## Current Truth And Authority Checkpoint

- Active branch: `{branch}`; draft PR `#{pull_request}`; source evidence anchor
  `{source_anchor}`. Final publication head and exact-head CI are externally attested.
- Unit T literally returned `{unit_t['literalOutcome']}`. It executed 64 attempts, produced 60
  artifacts with four explicit abstentions, evaluated 48 compile rows, yielded zero strict
  complete pixel-route compile-valid candidates, and actually evaluated 8/24 appearance rows
  with zero passes. D0-RP-04 passed; D0-RP-03, D0-RP-06, and D0-RP-07 failed.
- Unit U literally returned `{unit_u['literalOutcome']}`. It created no seed, untouched fixture,
  oracle reveal, scientific admission, or candidate. PR #55 exact-head Forge run
  `{unit_u['exactHeadCi']['run']}` completed with 25 passing and four failing jobs.
- Strategy 3 is reserved and consumed; scientific admission was not executed. Remaining budgets
  are seam models `0`, topology strategies `0`, and canonical-candidate attempts `1`.
- Unit S successor authority integrity is derived from the complete executable predicate and
  mutation sets. These are integrity results only and create no scientific capability claim.
- The supplemental matrix identities are D0-RP-09 and D0-RP-14 pass; D0-RP-10 and D0-RP-11 not
  run. Pre-topology C3, scoped static Z1, failed non-solver Z2 evidence, and globally unproven
  gates remain distinct.

## Dashboard

- Requirement rows: {counts['complete']} complete / {counts['partial']} partial /
  {counts['not_started']} not started / {counts['discovery_pending']} discovery pending; 101 total.
- Phase 0 is complete. Phases 1-14 remain partial. Research Prototype remains partial; Alpha,
  Beta, and Production are not started.
- The immutable v2 Strategy 3 test remains byte-identical and its exact historical mismatch is
  required in a dedicated CI lane. Ordinary pass-oriented shards deselect only that exact node.
- Unit Y1 may start only after Unit Y0 exact-head Forge and sealed-v2-failure lanes both pass.
- No merge, rebase, force-push, scientific retry, budget restoration, candidate transformation,
  private-user, GPU, mobile, or human-review evidence is authorised by this checkpoint.

## Status Vocabulary"""
    return prefix + suffix


def _append_unique(current: list[str], additions: list[str]) -> list[str]:
    return [*current, *(item for item in additions if item not in current)]


def _source_tree_hash(repo_root: Path, paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((repo_root / relative).read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


def _git_count(repo_root: Path, revision_range: str) -> int:
    return int(_git_lines(repo_root, "rev-list", "--count", revision_range)[0])


def _git_lines(repo_root: Path, *args: str) -> list[str]:
    output = subprocess.check_output(["git", *args], cwd=repo_root, text=True)
    return output.splitlines()


def _topological_order(nodes: list[dict[str, Any]], edges: list[dict[str, str]]) -> list[str]:
    declared = [str(node["id"]) for node in nodes]
    position = {node_id: index for index, node_id in enumerate(declared)}
    incoming = {node_id: set[str]() for node_id in declared}
    outgoing = {node_id: set[str]() for node_id in declared}
    for edge in edges:
        incoming[edge["to"]].add(edge["from"])
        outgoing[edge["from"]].add(edge["to"])
    ready = [node_id for node_id in declared if not incoming[node_id]]
    ordered: list[str] = []
    while ready:
        ready.sort(key=position.__getitem__)
        node_id = ready.pop(0)
        ordered.append(node_id)
        for target in sorted(outgoing[node_id], key=position.__getitem__):
            incoming[target].discard(node_id)
            if not incoming[target] and target not in ordered and target not in ready:
                ready.append(target)
    if len(ordered) != len(declared):
        raise ValueError("truth_authority_stack_cycle")
    return ordered
