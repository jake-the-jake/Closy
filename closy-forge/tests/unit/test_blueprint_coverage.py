from __future__ import annotations

import json
import subprocess
from pathlib import Path

from closy_forge.blueprint.status import (
    build_status_model,
    render_status_summary,
    validate_status_model,
)

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

    assert coverage["version"] == "closy.blueprint_coverage.integrity_reconciliation.v1"
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
    assert status["gates"] == {
        "C1": "complete",
        "C2": "complete",
        "C3": "partial",
        "P1": "discovery_pending",
        "Z1": "complete",
        "Z2": "discovery_pending",
    }
    assert status["maturity"] == {
        "ALPHA": "not_started",
        "BETA": "not_started",
        "PRODUCTION": "not_started",
        "RESEARCH-PROTOTYPE": "partial",
    }
    assert status["truth"] == {
        "actualPhase9TrainingExecuted": True,
        "actualZeroOneComputeExecuted": True,
        "actualZeroOneRuntimeExecuted": True,
        "humanReviewRun": False,
        "phase8EvidenceScope": "deterministic_d0_fixture_family_verticals",
        "phases10To14EvidenceScope": (
            "phase10_real_d0_cpu_static_plus_phases11_to14_contract_fixtures"
        ),
        "physicalMobileEvidenceRun": False,
        "privateUserEvidenceRun": False,
    }


def test_pr_stack_manifest_is_linear_draft_and_exact_head_evidenced() -> None:
    stack = _json("pr_stack_manifest.json")
    rows = stack["pullRequests"]

    numbers = [int(row["number"]) for row in rows]
    assert numbers == list(range(numbers[0], numbers[-1] + 1))
    assert stack["sequentialMergeOrder"] == numbers
    assert stack["sequentialMergeRehearsal"] == {
        "mode": "read_only_direct_parent_merge_base_verification",
        "passed": True,
    }
    for index, row in enumerate(rows):
        assert row["draft"] is True
        assert row["mergeability"] == "MERGEABLE"
        assert row["directParentMergeBaseVerified"] is True
        assert row["layerBehind"] == 0
        assert row["layerCommitCount"] == row["layerAhead"]
        if index:
            assert row["baseBranch"] == rows[index - 1]["branch"]
            assert row["baseSha"] == rows[index - 1]["headSha"]
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


def test_generated_markdown_is_exact_render_of_machine_status() -> None:
    status = _json("current_blueprint_status.json")
    summary = (DOCS / "BLUEPRINT_STATUS_SUMMARY.md").read_text(encoding="utf-8")

    assert summary == render_status_summary(status)
    assert "deterministic D0 fixture family verticals" in summary
    assert "Phases 11-14 remain versioned contract-fixture foundations" in summary


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
