from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from closy_forge.pattern_inference.correction_session_v2 import (
    record_correction,
    start_correction_session,
    validate_correction_session,
)
from closy_forge.pattern_inference.dataset_v2 import (
    FEATURE_NAMES,
    build_synthetic_dataset_v2,
    validate_dataset_v2,
)
from closy_forge.pattern_inference.grammar_v2 import (
    FAMILY_SPECS,
    compile_program,
    validate_compiled_pattern,
    validate_program,
)
from closy_forge.pattern_inference.learned_foundation import (
    build_learned_pattern_inference_foundation,
    validate_learned_pattern_inference_foundation,
)
from closy_forge.pattern_inference.model_v2 import (
    canonical_model_bytes,
    classification_sample_loss_gradient,
    deterministic_template_fallback,
    predict_v2,
    regression_sample_loss_gradient,
)


@pytest.fixture(scope="module")
def learned_bundle() -> dict[str, Any]:
    return build_learned_pattern_inference_foundation()


def test_dataset_is_large_group_disjoint_and_free_of_target_defining_inputs() -> None:
    dataset, split = build_synthetic_dataset_v2()

    assert validate_dataset_v2(dataset, split) == []
    assert len(dataset["programs"]) == 96
    assert len(dataset["samples"]) == 384
    assert {name: len(ids) for name, ids in split["samples"].items()} == {
        "train": 256,
        "validation": 64,
        "test": 64,
    }
    assert all(tuple(sample["input"]) == FEATURE_NAMES for sample in dataset["samples"])
    assert all(
        forbidden not in key.lower()
        for sample in dataset["samples"]
        for key in sample["input"]
        for forbidden in (
            "family",
            "category",
            "template",
            "panel",
            "opening",
            "target",
            "parameter",
        )
    )


def test_split_validator_recomputes_identity_and_adversarial_leakage() -> None:
    dataset, split = build_synthetic_dataset_v2()
    split["groups"]["test"].append(split["groups"]["train"][0])
    dataset["samples"][0]["input"]["targetFamily"] = "sleeveless_top"

    issues = validate_dataset_v2(dataset, split)

    assert "program_identity_leakage" in issues
    assert "adversarial_feature_leakage_detected" in issues
    assert "capture_feature_set_invalid" in issues


def test_real_grammar_compiles_all_eight_family_programs() -> None:
    dataset, _ = build_synthetic_dataset_v2()
    representatives = {program["garmentFamily"]: program for program in dataset["programs"]}

    assert set(representatives) == set(FAMILY_SPECS)
    for family, program in representatives.items():
        assert validate_program(program) == [], family
        pattern = compile_program(program)
        assert pattern["garmentClass"] == family
        assert validate_compiled_pattern(pattern) == []


def test_grammar_validator_fails_closed_for_required_corruptions() -> None:
    dataset, _ = build_synthetic_dataset_v2()
    base = deepcopy(dataset["programs"][0])
    corruptions: list[tuple[str, Any]] = []

    missing_span = deepcopy(base)
    missing_span["seamPairings"][0]["spans"] = []
    corruptions.append(("seam_spans_missing", missing_span))

    duplicate = deepcopy(base)
    duplicate["openings"][0]["semanticId"] = duplicate["panelNodes"][0]["semanticId"]
    corruptions.append(("duplicate_semantic_id", duplicate))

    seam_cycle = deepcopy(base)
    seam_id = seam_cycle["seamPairings"][0]["semanticId"]
    seam_cycle["seamPairings"][0]["afterSeamIds"] = [seam_id]
    corruptions.append(("impossible_seam_cycle", seam_cycle))

    opening = deepcopy(base)
    opening["openings"][0]["boundaryCurveIds"] = ["edge.missing"]
    corruptions.append(("opening_invalid", opening))

    panel = deepcopy(base)
    panel["panelNodes"][0]["boundaryCurves"][0]["controlPoints"] = [[0.0, 0.0]]
    corruptions.append(("non_simple_panel", panel))

    ease = deepcopy(base)
    ease["seamPairings"][0]["easeRatio"] = 9.0
    corruptions.append(("seam_ease_inconsistent", ease))

    layers = deepcopy(base)
    layer_id = layers["layerOrder"][0]["semanticId"]
    layers["layerOrder"][0]["parentLayerId"] = layer_id
    corruptions.append(("layer_cycle_or_reference_invalid", layers))

    unsupported = deepcopy(base)
    unsupported["shapingFeatures"] = [{"semanticId": "shape.bad", "type": "laser_cut"}]
    corruptions.append(("shaping_feature_unsupported", unsupported))

    parameters = deepcopy(base)
    parameters["parameters"][FAMILY_SPECS[base["garmentFamily"]].length_field] = -1.0
    corruptions.append(("parameter_out_of_range", parameters))

    for expected, document in corruptions:
        assert expected in validate_program(document), expected


def test_optimizer_gradients_match_finite_differences() -> None:
    class_weights = [[0.1, -0.2, 0.3], [-0.3, 0.2, -0.1]]
    row = [1.0, 0.4, -0.7]
    _, class_gradient = classification_sample_loss_gradient(class_weights, row, 1, l2=0.03)
    epsilon = 1e-6
    for class_index in range(2):
        for feature_index in range(3):
            plus = deepcopy(class_weights)
            minus = deepcopy(class_weights)
            plus[class_index][feature_index] += epsilon
            minus[class_index][feature_index] -= epsilon
            plus_loss, _ = classification_sample_loss_gradient(plus, row, 1, l2=0.03)
            minus_loss, _ = classification_sample_loss_gradient(minus, row, 1, l2=0.03)
            numeric = (plus_loss - minus_loss) / (2 * epsilon)
            assert class_gradient[class_index][feature_index] == pytest.approx(numeric, abs=1e-7)

    regression_weights = [0.2, -0.1, 0.4]
    _, regression_gradient = regression_sample_loss_gradient(regression_weights, row, 0.8, l2=0.02)
    for feature_index in range(3):
        plus = regression_weights[:]
        minus = regression_weights[:]
        plus[feature_index] += epsilon
        minus[feature_index] -= epsilon
        plus_loss, _ = regression_sample_loss_gradient(plus, row, 0.8, l2=0.02)
        minus_loss, _ = regression_sample_loss_gradient(minus, row, 0.8, l2=0.02)
        numeric = (plus_loss - minus_loss) / (2 * epsilon)
        assert regression_gradient[feature_index] == pytest.approx(numeric, abs=1e-7)


def test_actual_training_is_reproducible_evaluated_and_honest(
    learned_bundle: dict[str, Any],
) -> None:
    assert validate_learned_pattern_inference_foundation(learned_bundle) == []
    model = learned_bundle["model"]
    curve = model["trainingCurve"]
    assert curve[-1]["totalLoss"] < curve[0]["totalLoss"]
    assert any(abs(value) > 1e-6 for row in model["classWeights"] for value in row)
    assert learned_bundle["reproducibility"]["canonicalModelBytesIdentical"] is True
    assert learned_bundle["evaluation"]["familyTemplate"]["top1Accuracy"] == 1.0
    assert learned_bundle["evaluation"]["grammarValidity"]["rate"] == 1.0
    assert learned_bundle["evaluation"]["comparison"]["learnedSuperioritySupported"] is False
    assert learned_bundle["evaluation"]["comparison"]["claim"].startswith("no_superiority")
    assert learned_bundle["evidenceTier"]["globalPhase9Status"] == "partial"


def test_ood_defers_and_deterministic_fallback_stays_compilable(
    learned_bundle: dict[str, Any],
) -> None:
    model = learned_bundle["model"]
    corrupted = learned_bundle["dataset"]["challengeSet"][3]
    prediction = predict_v2(model, corrupted["input"])

    assert prediction["status"] == "rejected"
    first_program, first_pattern, first_reason = deterministic_template_fallback(
        model, corrupted["input"], program_id="fallback.test", base_seed=3
    )
    second_program, second_pattern, second_reason = deterministic_template_fallback(
        model, corrupted["input"], program_id="fallback.test", base_seed=3
    )
    assert (first_program, first_pattern, first_reason) == (
        second_program,
        second_pattern,
        second_reason,
    )
    assert validate_program(first_program) == []
    assert validate_compiled_pattern(first_pattern) == []


def test_bounded_correction_records_acceptance_rejection_and_rebuild(
    learned_bundle: dict[str, Any],
) -> None:
    model = learned_bundle["model"]
    observation = learned_bundle["dataset"]["samples"][0]["input"]
    session = start_correction_session(model, observation, session_id="session.test", seed=11)
    rejected = record_correction(
        session,
        field="easeNormalized",
        value=0.4,
        accepted=False,
        reason_code="simulated_reject",
    )
    accepted = record_correction(
        rejected,
        field="widthScale",
        value=1.01,
        accepted=True,
        reason_code="simulated_accept",
    )

    assert accepted["correctionEvents"][0]["accepted"] is False
    assert accepted["correctionEvents"][1]["accepted"] is True
    assert accepted["deterministicRebuildVerified"] is True
    assert accepted["humanReviewStatus"] == "not_run"
    assert validate_correction_session(accepted) == []
    assert canonical_model_bytes(model) == canonical_model_bytes(learned_bundle["model"])
