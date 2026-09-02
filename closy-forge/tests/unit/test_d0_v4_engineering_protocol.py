from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from closy_forge.d0_v4_engineering.protocol import (
    LIFECYCLE_STATES,
    load_budget_ledger,
    load_engineering_protocol,
    validate_budget_ledger,
    validate_engineering_protocol,
)

ROOT = Path(__file__).resolve().parents[2]


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


def test_initial_budget_ledger_is_append_only_and_unconsumed() -> None:
    protocol = load_engineering_protocol(ROOT)
    ledger = load_budget_ledger(ROOT)
    assert validate_budget_ledger(ledger, protocol) == []
    assert ledger["observationContractRevisionsConsumed"] == 0
    assert ledger["modelTrainingTrialsConsumed"] == 0
    assert ledger["publicTestExecutionsConsumed"] == 0


def test_budget_ledger_rejects_reorder_and_overrun() -> None:
    protocol = load_engineering_protocol(ROOT)
    ledger = load_budget_ledger(ROOT)
    reordered = deepcopy(ledger)
    reordered["events"][0]["ordinal"] = 1
    assert "budget_event_order_invalid" in validate_budget_ledger(reordered, protocol)
    overrun = deepcopy(ledger)
    for ordinal in range(1, 14):
        overrun["events"].append({"ordinal": ordinal, "event": "model_training_trial_completed"})
    overrun["modelTrainingTrialsConsumed"] = 13
    assert "model_training_trial_budget_exceeded" in validate_budget_ledger(overrun, protocol)
