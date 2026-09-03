from __future__ import annotations

import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from closy_forge.d0_v4_engineering.protocol import (
    LIFECYCLE_STATES,
    claim_public_test_execution,
    complete_public_test_execution,
    ledger_digest,
    load_budget_ledger,
    load_engineering_protocol,
    validate_budget_ledger,
    validate_engineering_protocol,
)
from closy_forge.package_io.canonical_json import write_canonical_json

ROOT = Path(__file__).resolve().parents[2]


def _copy_pre_public_test_state(root: Path) -> None:
    evidence = root / "docs" / "evidence" / "d0_v4_engineering"
    evidence.mkdir(parents=True)
    shutil.copy2(
        ROOT / "docs" / "evidence" / "d0_v4_engineering" / "engineering_protocol.json",
        evidence / "engineering_protocol.json",
    )
    ledger = deepcopy(load_budget_ledger(ROOT))
    ledger["events"] = [
        event for event in ledger["events"] if not event["event"].startswith("public_test_")
    ]
    for ordinal, event in enumerate(ledger["events"]):
        event["ordinal"] = ordinal
    ledger["publicTestExecutionsConsumed"] = 0
    ledger["ledgerDigest"] = ledger_digest(ledger)
    write_canonical_json(evidence / "engineering_budget_ledger.json", ledger)


def test_engineering_protocol_freezes_budget_partitions_and_readiness() -> None:
    protocol = load_engineering_protocol(ROOT)
    assert protocol["budgets"]["maximumObservationContractRevisions"] == 3
    assert protocol["budgets"]["maximumCompleteModelTrainingTrials"] == 12
    assert protocol["budgets"]["maximumPublicTestExecutions"] == 1
    assert protocol["partitions"] == {
        "trainingIdentityCount": 512,
        "validationIdentityCount": 128,
        "publicTestIdentityCount": 128,
        "qualificationIdentityCount": 0,
        "identityDisjoint": True,
        "parameterRasterSourceSeedAndNearDuplicateDisjoint": True,
        "rendererFamilyMinimum": 2,
        "publicTestExcludedFromModelThresholdAndArchitectureSelection": True,
    }
    assert protocol["lifecycleStates"] == list(LIFECYCLE_STATES)
    assert protocol["publicTestMayGuideDevelopment"] is False
    assert protocol["v4QualificationCohortCreated"] is False


def test_protocol_mutations_fail_closed() -> None:
    protocol = load_engineering_protocol(ROOT)
    mutations = (
        ("budgets", "maximumCompleteModelTrainingTrials", 13),
        ("partitions", "trainingIdentityCount", 511),
        ("readinessThresholds", "maximumForegroundSrgbMae", 0.12),
    )
    for section, field, value in mutations:
        mutated = deepcopy(protocol)
        mutated[section][field] = value
        assert validate_engineering_protocol(mutated)


def test_budget_ledger_is_append_only_and_within_frozen_caps() -> None:
    protocol = load_engineering_protocol(ROOT)
    ledger = load_budget_ledger(ROOT)
    assert validate_budget_ledger(ledger, protocol) == []
    counts = {
        event: sum(item["event"] == event for item in ledger["events"])
        for event in (
            "observation_contract_revision_completed",
            "model_training_trial_completed",
            "public_test_execution_started",
        )
    }
    assert (
        ledger["observationContractRevisionsConsumed"]
        == counts["observation_contract_revision_completed"]
    )
    assert ledger["modelTrainingTrialsConsumed"] == counts["model_training_trial_completed"]
    assert ledger["publicTestExecutionsConsumed"] == counts["public_test_execution_started"]


def test_budget_ledger_rejects_reorder_and_overrun() -> None:
    protocol = load_engineering_protocol(ROOT)
    ledger = load_budget_ledger(ROOT)
    reordered = deepcopy(ledger)
    reordered["events"][0]["ordinal"] = 1
    assert "budget_event_order_invalid" in validate_budget_ledger(reordered, protocol)
    overrun = deepcopy(ledger)
    for ordinal in range(len(overrun["events"]), len(overrun["events"]) + 12):
        overrun["events"].append({"ordinal": ordinal, "event": "model_training_trial_completed"})
    overrun["modelTrainingTrialsConsumed"] = 13
    assert "model_training_trial_budget_exceeded" in validate_budget_ledger(overrun, protocol)


def test_public_test_claim_is_atomic_one_shot_and_consumes_before_read(tmp_path: Path) -> None:
    _copy_pre_public_test_state(tmp_path)
    claimed = claim_public_test_execution(
        tmp_path,
        source_head="a" * 40,
        model_sha256="b" * 64,
    )
    assert claimed["publicTestExecutionsConsumed"] == 1
    assert claimed["events"][-1]["publicTestRead"] is False
    with pytest.raises((FileExistsError, ValueError)):
        claim_public_test_execution(
            tmp_path,
            source_head="a" * 40,
            model_sha256="b" * 64,
        )
    completed = complete_public_test_execution(
        tmp_path,
        result_digest="c" * 64,
        readiness_pass=True,
    )
    assert completed["publicTestExecutionsConsumed"] == 1
    assert completed["events"][-1]["event"] == "public_test_execution_completed"


def test_public_test_failure_reason_is_bounded_and_single_line(tmp_path: Path) -> None:
    _copy_pre_public_test_state(tmp_path)
    claim_public_test_execution(
        tmp_path,
        source_head="a" * 40,
        model_sha256="b" * 64,
    )
    completed = complete_public_test_execution(
        tmp_path,
        result_digest=None,
        readiness_pass=False,
        failed_reason="private-path\n" + ("x" * 400),
    )
    reason = completed["events"][-1]["failedReason"]
    assert isinstance(reason, str)
    assert "\n" not in reason
    assert len(reason) == 240
