from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from closy_forge.recovery_foundation_v2.contracts import (  # type: ignore[import-untyped]
    validate_budget_event_ledger,
)

ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT.parent
EVIDENCE = ROOT / "docs" / "evidence" / "final_strategy3_v2"


def _json(name: str) -> dict[str, object]:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_unit_u_publication_is_fresh() -> None:
    # Current status is owned by the append-only successor publication; Unit U artifacts remain
    # immutable inputs rather than regenerating current dashboards with the historical builder.
    subprocess.run(
        [sys.executable, "scripts/build_truth_authority_integrity_v3.py", "--check"],
        cwd=ROOT,
        check=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        timeout=30,
    )


def test_unit_u_markdown_publication_is_checkout_stable() -> None:
    report = "closy-forge/docs/evidence/final_strategy3_v2/REPORT.md"
    attribute = subprocess.check_output(
        ["git", "check-attr", "eol", "--", report],
        cwd=REPO_ROOT,
        text=True,
    )
    assert attribute.strip().endswith(": eol: lf")


def test_preseed_dependency_block_is_literal_and_non_scientific() -> None:
    outcome = _json("outcome_report.json")
    authority = outcome["officialAuthority"]
    admission = outcome["admission"]
    budgets = outcome["budgetsAfter"]
    assert isinstance(authority, dict)
    assert isinstance(admission, dict)
    assert isinstance(budgets, dict)
    assert outcome["literalOutcome"] == "dependency_blocked_before_official_seed_v2"
    assert authority["officialSeedCreated"] is False
    assert authority["strategyContainerExecutions"] == 0
    assert authority["attemptConsumed"] is False
    assert authority["rerunPerformed"] is False
    assert admission == {
        "confirmationExecuted": False,
        "admitted": False,
        "unitVEligible": False,
        "unitWEligible": False,
        "unitXEligible": False,
    }
    assert budgets == {
        "seamModels": 0,
        "topologyStrategies": 0,
        "candidateAttempts": 1,
        "untouchedConfirmationAttemptConsumed": False,
    }


def test_lock_mismatch_audit_matches_repository_blobs() -> None:
    outcome = _json("outcome_report.json")
    failure = outcome["failure"]
    assert isinstance(failure, dict)
    mismatches = failure["mismatches"]
    assert isinstance(mismatches, list)
    assert len(mismatches) == 4
    for item in mismatches:
        assert isinstance(item, dict)
        relative = f"closy-forge/{item['path']}"
        blob = subprocess.check_output(
            ["git", "cat-file", "blob", f"HEAD:{relative}"], cwd=REPO_ROOT
        )
        assert len(blob) == item["repositoryByteLength"]
        assert hashlib.sha256(blob).hexdigest() == item["repositorySha256"]
        assert hashlib.sha256(blob.replace(b"\n", b"\r\n")).hexdigest() == item["lockedSha256"]


def test_post_unit_u_budget_ledger_extends_without_rewriting_unit_s() -> None:
    ledger = _json("physical_budget_event_ledger_after_unit_u.json")
    assert validate_budget_event_ledger(ledger) == []
    derived = ledger["derived"]
    assert isinstance(derived, dict)
    assert derived["remaining"] == {
        "canonical_candidate": 1,
        "seam_model": 0,
        "topology_strategy": 0,
    }
    assert ledger["candidateAttemptConsumed"] is False
    assert ledger["untouchedConfirmationAttemptConsumed"] is False


def test_successor_status_preserves_literal_y1_and_y2_outcomes() -> None:
    resume = json.loads((ROOT / "docs" / "ACTIVE_BLUEPRINT_RESUME.json").read_text())
    assert resume["machineResumeVersion"] == (
        "closy.active_blueprint_resume.truth_dependency_authority.v4"
    )
    assert resume["unitY1Result"]["result"] == "strategy3_dependency_blocked_before_seed_v3"
    assert resume["unitY2Result"]["terminalOutcome"] == "preseed_scientific_protocol_invalid"
    assert resume["unitY2Result"]["seedCreated"] is False
    assert resume["unitY2Result"]["scientificAttemptConsumed"] is False
    assert resume["remainingBudgets"] == {
        "candidateAttempts": 1,
        "seamModels": 0,
        "topologyStrategies": 0,
    }
    assert resume["exactNextAction"] == (
        "implement_PR_C_capture_camera_material_engineering_from_PR_A_final_head"
    )
