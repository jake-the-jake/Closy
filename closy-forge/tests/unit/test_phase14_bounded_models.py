from __future__ import annotations

from copy import deepcopy

import pytest

from closy_forge.bounded_models.contracts import FEATURE_NAMES, validate_feature_snapshot
from closy_forge.bounded_models.dataset import (
    build_phase14_dataset,
    dataset_hash,
    rows_for_split,
    validate_split_manifest,
)
from closy_forge.bounded_models.evaluation import evaluate_phase14_model, evaluation_hash
from closy_forge.bounded_models.model import (
    predict_candidate,
    rank_material_presets,
    train_phase14_model,
    validate_model,
)
from closy_forge.bounded_models.solver_fixtures import run_project_authored_settle_fixture


@pytest.fixture(scope="module")
def dataset() -> dict[str, object]:
    return build_phase14_dataset()


@pytest.fixture(scope="module")
def model(dataset: dict[str, object]) -> dict[str, object]:
    return train_phase14_model(dataset)


def test_dataset_is_deterministic_group_disjoint_and_hash_bound(
    dataset: dict[str, object],
) -> None:
    assert dataset["rowCount"] == 384
    assert dataset["scenarioCounts"] == {"train": 60, "validation": 18, "test": 18}
    assert dataset["integrity"]["datasetHash"] == dataset_hash(dataset)
    assert validate_split_manifest(dataset) == []
    assert (
        build_phase14_dataset()["integrity"]["datasetHash"] == dataset["integrity"]["datasetHash"]
    )


def test_features_are_frozen_before_solver_and_post_outcome_leakage_is_rejected(
    dataset: dict[str, object],
) -> None:
    row = rows_for_split(dataset, "train")[0]
    features = deepcopy(row["featureSnapshot"])
    outcome = run_project_authored_settle_fixture(features)
    assert features == row["featureSnapshot"]
    assert outcome["stepCount"] == 180
    assert outcome["authority"] == "project_authored_numerical_fixture_validators"
    leaked = dict(features)
    leaked["finalValidatorOutcome"] = 1.0
    issues = validate_feature_snapshot(leaked)
    assert "post_outcome_feature_forbidden:finalValidatorOutcome" in issues


def test_training_is_deterministic_bounded_and_train_only(
    dataset: dict[str, object], model: dict[str, object]
) -> None:
    assert validate_model(model) == []
    assert model["training"]["trialCount"] == 3
    assert model["training"]["epochsPerTrial"] == 60
    assert model["deterministicValidatorsRetainFinalAuthority"] is True
    assert train_phase14_model(dataset)["integrity"]["modelHash"] == model["integrity"]["modelHash"]
    poisoned = deepcopy(dataset)
    test_row = rows_for_split(poisoned, "test")[0]
    test_row["featureSnapshot"][FEATURE_NAMES[0]] = 99999.0
    retrained = train_phase14_model(poisoned)
    assert retrained["normalization"] == model["normalization"]


def test_ood_and_corrupt_features_fail_closed_to_deterministic_fallback(
    dataset: dict[str, object], model: dict[str, object]
) -> None:
    features = dict(rows_for_split(dataset, "test")[0]["featureSnapshot"])
    features[FEATURE_NAMES[0]] = 99999.0
    prediction = predict_candidate(model, features)
    assert prediction["fallbackRequired"] is True
    assert prediction["reason"] == "out_of_distribution"
    del features[FEATURE_NAMES[1]]
    assert predict_candidate(model, features)["fallbackRequired"] is True


def test_material_ranker_exposes_bounded_initialization_priors_or_safe_fallback(
    dataset: dict[str, object], model: dict[str, object]
) -> None:
    features = dict(rows_for_split(dataset, "test")[0]["featureSnapshot"])
    scenario = {name: features[name] for name in FEATURE_NAMES[:8]}
    result = rank_material_presets(model, scenario)
    assert result["status"] in {"ranked", "fallback"}
    if result["status"] == "ranked":
        assert result["priors"]["stiffnessNPerM"] > 0.0
        assert result["priors"]["complianceMetersPerNewton"] > 0.0
        assert result["authority"] == "advisory_initialization_only"
    else:
        assert result["selectedPresetId"] == "material.cotton_jersey_d0_v1"


def test_evaluation_records_baselines_calibration_ood_utility_and_truth(
    dataset: dict[str, object], model: dict[str, object]
) -> None:
    evaluation = evaluate_phase14_model(dataset, model)
    assert evaluation["integrity"]["evaluationHash"] == evaluation_hash(evaluation)
    assert evaluation["leakageAudit"]["accepted"] is True
    assert evaluation["ood"]["challengeRejectionRate"] == 1.0
    assert evaluation["ood"]["inDistributionAcceptanceRate"] >= 0.9
    assert evaluation["calibration"]["brierScore"] >= 0.0
    assert evaluation["decisionUtility"]["learnedWarningUtility"] > -4.0
    assert evaluation["truth"]["deterministicValidatorsRetainFinalAuthority"] is True
    assert evaluation["truth"]["broadVisualGeometryFineTuningRun"] is False
