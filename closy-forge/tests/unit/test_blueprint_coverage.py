from __future__ import annotations

import json
import subprocess
from pathlib import Path

from closy_forge.blueprint.pr_dag import validate_pr_dag
from closy_forge.blueprint.status import (
    build_status_model,
    render_status_summary,
    validate_status_model,
)
from closy_forge.security.evidence_hygiene import scan_evidence_files

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS = REPO_ROOT / "closy-forge" / "docs"
STATUS_VOCABULARY = {
    "not_started",
    "scaffold",
    "partial",
    "implemented_unverified",
    "complete",
    "discovery_pending",
    "blocked_external",
    "not_applicable",
}
IMPLEMENTED_STATUSES = {"scaffold", "partial", "implemented_unverified", "complete"}


def _json(name: str) -> dict:
    return json.loads((DOCS / name).read_text(encoding="utf-8"))


def test_coverage_rows_are_unique_structured_and_truthfully_scoped() -> None:
    coverage = _json("blueprint_coverage.json")
    rows = coverage["rows"]
    ids = [row["id"] for row in rows]

    assert coverage["version"] == "closy.blueprint_coverage.c3_durable_z1_phase11.v3"
    assert set(coverage["statusVocabulary"]) == STATUS_VOCABULARY
    assert len(rows) == 101
    assert len(ids) == len(set(ids))
    for row in rows:
        assert row["status"] in STATUS_VOCABULARY
        assert row["sourceSection"]
        assert row["summary"]
        assert row["limitations"]
        assert row["nextAction"]
        if row["status"] in IMPLEMENTED_STATUSES:
            assert row["implementationPaths"], row["id"]
            assert row["executableEvidence"], row["id"]
            assert row["tests"], row["id"]
            assert row["commitSha"], row["id"]
        else:
            assert row["implementationPaths"] is None, row["id"]
            assert row["executableEvidence"] is None, row["id"]
            assert row["tests"] is None, row["id"]
            assert row["commitSha"] is None, row["id"]


def test_coverage_commit_references_resolve_without_asserting_specific_shas() -> None:
    coverage = _json("blueprint_coverage.json")
    refs = {ref for row in coverage["rows"] for ref in (row["commitSha"] or [])}

    for ref in sorted(refs):
        subprocess.run(
            ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )


def test_canonical_status_is_recomputed_from_coverage_and_stack() -> None:
    coverage = _json("blueprint_coverage.json")
    stack = _json("pr_stack_manifest.json")
    status = _json("current_blueprint_status.json")

    assert validate_status_model(status, coverage, stack) == []
    assert status == build_status_model(
        coverage, stack, evidence_anchor_sha=status["evidenceAnchorSha"]
    )
    counts: dict[str, int] = {}
    for row in coverage["rows"]:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    assert status["coverage"]["counts"] == dict(sorted(counts.items()))
    assert status["coverage"]["total"] == len(coverage["rows"])


def test_phase_gate_and_maturity_statuses_are_not_inflated() -> None:
    status = _json("current_blueprint_status.json")

    assert status["phases"]["00"] == "complete"
    assert set(status["phases"][f"{index:02d}"] for index in range(1, 15)) == {"partial"}
    assert status["gates"]["C1"]["scopedStatus"] == "pass"
    assert status["gates"]["C2"]["scopedStatus"] == "pass"
    assert status["gates"]["C3-Binding-D0"]["scopedStatus"] == "pass"
    assert status["gates"]["PHY1-SingleLayer-D0"]["scopedStatus"] == "failed"
    assert status["gates"]["Z1"]["globalStatus"] == "partial"
    assert status["gates"]["Z1"]["scopedStatus"] == "candidate_all_family_failed"
    assert status["gates"]["Z1"]["allFamilyAttemptCount"] == 9
    assert status["gates"]["Z1"]["successfulFamilyCount"] == 6
    assert status["gates"]["Z1"]["rejectedFamilyCount"] == 3
    assert status["gates"]["Z1"]["currentMasterRequalified"] is False
    assert status["gates"]["P1"]["scopedStatus"] == "not_run"
    assert {status["gates"][f"Z{index}"]["scopedStatus"] for index in range(2, 9)} == {"not_run"}
    assert status["maturity"] == {
        "ALPHA": "not_started",
        "BETA": "not_started",
        "PRODUCTION": "not_started",
        "RESEARCH-PROTOTYPE": "partial",
    }
    assert status["truth"] == {
        "actualPhase9TrainingExecuted": True,
        "actualZeroOneStaticCookExecutedThisInvocation": True,
        "actualZeroOneStaticArtifactLoaded": True,
        "zeroOneStaticFamilyAttemptCount": 9,
        "zeroOneStaticSuccessfulFamilyCount": 6,
        "zeroOneStaticRejectedFamilyCount": 3,
        "cacheValidated": False,
        "historicalZeroOneStaticCookEvidencePresent": True,
        "actualZeroOneDynamicDeformationExecuted": False,
        "actualZeroOneGpuRuntimeExecuted": False,
        "actualZeroOneMobileRuntimeExecuted": False,
        "humanReviewRun": False,
        "phase8EvidenceScope": "deterministic_fixture_family_verticals",
        "phases10To14EvidenceScope": (
            "candidate_all_family_phase10_partial_plus_phase11_to14_contract_fixtures"
        ),
        "physicalMobileEvidenceRun": False,
        "privateUserEvidenceRun": False,
    }


def test_pr_stack_manifest_is_an_explicit_validated_dag() -> None:
    stack = _json("pr_stack_manifest.json")
    rows = stack["pullRequests"]
    nodes = stack["nodes"]
    unique_commits_seen: dict[str, int] = {}

    assert validate_pr_dag(stack) == []
    assert stack["schemaVersion"] == 2
    assert stack["topology"] == "explicit_dag"
    numbers = [int(row["number"]) for row in rows]
    assert numbers == list(range(numbers[0], numbers[-1] + 1))
    assert [int(node["pullRequest"]) for node in nodes] == numbers
    for index, row in enumerate(rows):
        assert row["draft"] is True
        assert row["mergeability"] == "MERGEABLE"
        assert row["directParentMergeBaseVerified"] is True
        assert row["layerBehind"] == 0
        assert row["layerCommitCount"] == row["layerAhead"]
        if index:
            assert row["baseBranch"] == rows[index - 1]["branch"]
            assert row["baseSha"] == rows[index - 1]["headSha"]
            merge_base = subprocess.run(
                ["git", "merge-base", row["baseSha"], row["headSha"]],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            assert merge_base == row["baseSha"]
        if row["number"] == 10:
            assert row["latestExactHeadForgeRun"] is None
            assert row["knownException"]["code"] == "missing_exact_head_forge_run"
            assert row["knownException"]["descendantEvidenceIsExactHead"] is False
        else:
            run = row["latestExactHeadForgeRun"]
            assert run["exactHead"] is True
            assert run["runId"]
            assert {job["conclusion"] for job in run["jobs"]} == {"SUCCESS"}
            assert {"ubuntu-latest", "windows-latest"} <= {
                os_name
                for job in run["jobs"]
                for os_name in ("ubuntu-latest", "windows-latest")
                if os_name in job["name"]
            }
        layer_commits = subprocess.run(
            ["git", "rev-list", f'{row["baseSha"]}..{row["headSha"]}'],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        assert len(layer_commits) == row["layerCommitCount"]
        for commit in layer_commits:
            assert commit not in unique_commits_seen, (
                f"commit {commit} is replayed by PR {row['number']} and "
                f"PR {unique_commits_seen[commit]}"
            )
            unique_commits_seen[commit] = row["number"]
    final = rows[-1]
    assert final["number"] == 23
    assert final["headSha"] == "a481ba26a424bd91607b8c1d41b6173a2c9579d9"
    assert final["layerCommitCount"] == 14
    assert final["changedFileCount"] == 24
    assert final["latestExactHeadForgeRun"]["runId"] == "33150483293"
    assert len(final["latestExactHeadForgeRun"]["jobs"]) == 26


def test_generated_markdown_is_exact_render_of_machine_status() -> None:
    status = _json("current_blueprint_status.json")
    summary = (DOCS / "BLUEPRINT_STATUS_SUMMARY.md").read_text(encoding="utf-8")

    assert summary == render_status_summary(status)
    assert "C3-Binding-D0 passes only for its fixed-avatar D0 T-shirt profile" in summary
    assert "No dynamic, GPU, mobile, private-user, or human-review execution" in summary


def test_phase11_prerequisite_reconciliation_is_exact_and_fail_closed() -> None:
    evidence = _json("evidence/phase11_prerequisite_reconciliation_v2.json")
    base_sha = "2a4fcd8146d95d2fab9a3d39751ffdafd5196387"
    source_head = "f9f1ff86089f6b43157431bdd3ccdc83cbc8b974"
    implementation_head = "f64c4ff2225141aa3fa04405e77fef0af360e050"

    assert evidence["base"]["sha"] == base_sha
    assert evidence["source"]["headSha"] == source_head
    assert evidence["destination"]["implementationHeadSha"] == implementation_head
    assert evidence["destination"]["directParentMergeBase"] == base_sha
    assert evidence["destination"]["behindParentCommitCount"] == 0
    assert len(evidence["mappings"]) == 8

    merge_base = subprocess.run(
        ["git", "merge-base", base_sha, implementation_head],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert merge_base == base_sha

    replayed_count = subprocess.run(
        ["git", "rev-list", "--count", f"{base_sha}..{implementation_head}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert replayed_count == "8"

    for mapping in evidence["mappings"]:
        for commit in (mapping["source"], mapping["destination"]):
            subprocess.run(
                ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
            )

    assert evidence["gates"] == {
        "C3-Binding-D0": "pass",
        "PHY1-SingleLayer-D0": "fail",
        "refreshedPairedScopedZ1": "fail",
        "mechanicalReferencePhase11Eligible": False,
        "solverDrivenPhysicalPhase11Eligible": False,
        "Z2Executed": False,
    }
    assert evidence["decision"] == "phase11_blocked_by_refreshed_paired_scoped_z1"


def test_next_actions_do_not_point_to_already_completed_stack_steps() -> None:
    coverage = _json("blueprint_coverage.json")
    next_actions = "\n".join(str(row["nextAction"]) for row in coverage["rows"])

    for stale in (
        "Proceed to BP-51",
        "Push and remote-validate the Phase 6",
        "Remote-validate the Phase 7",
        "apply the shared material contract to the sleeveless",
        "Phase 9 is next",
    ):
        assert stale not in next_actions


def test_human_ledgers_are_not_machine_readiness_authorities() -> None:
    status = _json("current_blueprint_status.json")
    stack = _json("pr_stack_manifest.json")
    coverage = _json("blueprint_coverage.json")

    assert validate_status_model(status, coverage, stack) == []


def test_generated_evidence_and_changed_status_documents_are_path_and_secret_safe() -> None:
    paths = [
        DOCS / "ACTIVE_BLUEPRINT_RESUME.md",
        DOCS / "BLUEPRINT_STATUS_SUMMARY.md",
        DOCS / "MASTER_BLUEPRINT_PROGRESS.md",
        DOCS / "blueprint_coverage.json",
        DOCS / "current_blueprint_status.json",
        DOCS / "execution_budget_v2.json",
        DOCS / "evidence_integrity_audit_v2.md",
        DOCS / "pr_stack_manifest.json",
        DOCS / "zeroone-static-integration-v1.md",
        *sorted((DOCS / "evidence").rglob("*.json")),
        *sorted((DOCS / "evidence").rglob("*.md")),
    ]

    assert scan_evidence_files(paths) == {}
