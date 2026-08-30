from __future__ import annotations

import json
from copy import deepcopy

import pytest

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.pattern_inference.e1_evaluation_v5 import evaluate_e1_v5
from closy_forge.pattern_inference.e1_kernel_v3 import (
    e1_model_hash,
    predict_e1_kernel_v3,
    rbf_score_and_gradient,
    train_e1_kernel_v3,
    validate_e1_model_v3,
)
from closy_forge.pattern_inference.multiview_corpus_v5 import build_multiview_corpus_v5


@pytest.fixture(scope="module")
def smoke_bundle() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    dataset, split = build_multiview_corpus_v5(
        programs_per_family=4,
        captures_per_program=1,
    )
    model = train_e1_kernel_v3(dataset, split)
    return dataset, split, model


def test_kernel_model_serializes_reloads_and_predicts_without_targets(
    smoke_bundle: tuple[dict[str, object], dict[str, object], dict[str, object]],
) -> None:
    dataset, _split, model = smoke_bundle
    assert validate_e1_model_v3(model) == []

    reloaded = json.loads(canonical_dumps(model))
    assert validate_e1_model_v3(reloaded) == []
    assert reloaded["integrity"]["modelHash"] == e1_model_hash(reloaded)
    observation = dataset["captures"][0]["input"]
    assert predict_e1_kernel_v3(model, observation) == predict_e1_kernel_v3(reloaded, observation)


def test_rbf_analytic_gradient_matches_finite_difference() -> None:
    point = [0.2, -0.4, 0.9]
    center = [-0.1, -0.3, 0.5]
    bandwidth = 0.8
    _score, gradient = rbf_score_and_gradient(point, center, bandwidth)
    epsilon = 1.0e-6
    for index in range(len(point)):
        left = list(point)
        right = list(point)
        left[index] -= epsilon
        right[index] += epsilon
        left_score = rbf_score_and_gradient(left, center, bandwidth)[0]
        right_score = rbf_score_and_gradient(right, center, bandwidth)[0]
        numeric = (right_score - left_score) / (2.0 * epsilon)
        assert gradient[index] == pytest.approx(numeric, abs=1.0e-7)


def test_e1_evaluator_keeps_package_authority_fail_closed(
    smoke_bundle: tuple[dict[str, object], dict[str, object], dict[str, object]],
) -> None:
    dataset, split, source_model = smoke_bundle
    model = deepcopy(source_model)
    model["calibration"]["confidenceThreshold"] = 0.0
    thresholds = {"e1": _permissive_smoke_thresholds()}

    result = evaluate_e1_v5(model, dataset, split, thresholds)

    assert result["testProgrammeCount"] == 8
    assert result["leakageAudit"]["candidateApiAcceptsTarget"] is False
    assert result["downstream"]["canonicalPackagePublicationRate"] == 0.0
    assert result["acceptance"]["checks"]["canonicalPackage"] is False
    assert result["acceptance"]["learnedRouteDefault"] is False


def _permissive_smoke_thresholds() -> dict[str, object]:
    return {
        "profileId": "closy.e1.smoke",
        "minimumHeldoutProgrammes": 8,
        "minimumRawMacroTop1": 0.0,
        "minimumPerFamilyRecall": 0.0,
        "minimumRecallAt3": 0.0,
        "minimumBaselineBootstrapLower95": -1.0,
        "minimumAcceptedCoverage": 0.0,
        "maximumSelectiveRisk": 1.0,
        "maximumEce": 1.0,
        "maximumBrier": 1.0,
        "minimumOodCorrectAction": 0.0,
        "maximumOodFalseAccept": 1.0,
        "maximumMeanNormalizedParameterMae": 9.0,
        "maximumAxisNormalizedParameterMae": 9.0,
        "maximumDestroyedPixelTop1": 1.0,
        "maximumNuisanceOnlyTop1": 1.0,
        "maximumLabelPermutationTop1": 1.0,
        "maximumParameterDefaultErrorRatio": 9.0,
    }
