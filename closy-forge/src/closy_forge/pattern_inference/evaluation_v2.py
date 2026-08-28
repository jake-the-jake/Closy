from __future__ import annotations

import math
from typing import Any

from .dataset_v2 import feature_vector, samples_for_split
from .grammar_v2 import compile_program, validate_compiled_pattern, validate_program
from .model_v2 import FAMILIES, TARGET_NAMES, decode_prediction, predict_v2

EVALUATION_VERSION = "closy.pattern_inference.evaluation.d0.v1"


def evaluate_model_v2(
    model: dict[str, Any], dataset: dict[str, Any], split: dict[str, Any]
) -> dict[str, Any]:
    test = samples_for_split(dataset, split, "test")
    program_by_id = {program["programId"]: program for program in dataset["programs"]}
    records: list[dict[str, Any]] = []
    grammar_valid = 0
    seam_opening_valid = 0
    family_correct = 0
    top3_correct = 0
    accepted_count = 0
    absolute_errors: dict[str, list[float]] = {name: [] for name in TARGET_NAMES}
    silhouette_errors: list[float] = []
    fit_errors: list[float] = []
    for index, sample in enumerate(test):
        prediction = predict_v2(model, sample["input"])
        expected_family = str(sample["target"]["garmentFamily"])
        predicted_family = prediction.get("family")
        correct = predicted_family == expected_family
        family_correct += int(correct)
        top3_correct += int(expected_family in {item["family"] for item in prediction["topK"]})
        if prediction["status"] == "predicted":
            accepted_count += 1
            program, pattern = decode_prediction(
                prediction,
                program_id=f"evaluation.decode.{index:04d}",
                base_seed=81_000 + index,
            )
            program_ok = not validate_program(program)
            pattern_issues = validate_compiled_pattern(pattern)
            grammar_valid += int(program_ok and not pattern_issues)
            seam_opening_valid += int(
                not any("seam" in issue or "opening" in issue for issue in pattern_issues)
            )
            expected_pattern = compile_program(program_by_id[sample["target"]["programId"]])
            silhouette, fit = _compiled_geometry_errors(expected_pattern, pattern)
            silhouette_errors.append(silhouette)
            fit_errors.append(fit)
        expected_continuous = sample["target"]["continuousParameters"]
        if prediction["continuousParameters"] is not None:
            for name in TARGET_NAMES:
                absolute_errors[name].append(
                    abs(
                        float(prediction["continuousParameters"][name])
                        - float(expected_continuous[name])
                    )
                )
        records.append(
            {
                "sampleId": sample["sampleId"],
                "programGroupId": sample["programGroupId"],
                "expectedFamily": expected_family,
                "predictedFamily": predicted_family,
                "status": prediction["status"],
                "confidence": prediction["confidence"],
                "correct": correct,
            }
        )
    baseline = _evaluate_centroid_baseline(model, test)
    ood = _evaluate_challenges(model, dataset["challengeSet"])
    count = len(test)
    learned_accuracy = family_correct / count
    baseline_accuracy = float(baseline["top1Accuracy"])
    superiority_supported = learned_accuracy > baseline_accuracy
    return {
        "schemaVersion": 1,
        "evaluationVersion": EVALUATION_VERSION,
        "evidenceScope": "identity_disjoint_project_authored_synthetic_d0",
        "heldOutSampleCount": count,
        "heldOutProgramGroupCount": len({sample["programGroupId"] for sample in test}),
        "familyTemplate": {
            "top1Correct": family_correct,
            "top1Accuracy": round(learned_accuracy, 9),
            "top3Correct": top3_correct,
            "top3Accuracy": round(top3_correct / count, 9),
        },
        "continuousParameterMae": {
            name: round(sum(values) / len(values), 9) if values else None
            for name, values in absolute_errors.items()
        },
        "grammarValidity": {
            "validDecodedCount": grammar_valid,
            "acceptedPredictionCount": accepted_count,
            "rate": round(grammar_valid / accepted_count, 9) if accepted_count else 0.0,
        },
        "seamOpeningValidity": {
            "validCount": seam_opening_valid,
            "acceptedPredictionCount": accepted_count,
            "rate": round(seam_opening_valid / accepted_count, 9) if accepted_count else 0.0,
        },
        "postCompileGeometryProxy": {
            "status": "measured_on_actual_compiled_closy_patterns_not_a_settle_claim",
            "meanNormalizedSilhouetteExtentError": _mean(silhouette_errors),
            "meanNormalizedFitExtentError": _mean(fit_errors),
        },
        "postSettleEvaluation": {
            "status": "separate_actual_package_evidence_required",
            "reason": (
                "canonical_model_evaluation_excludes_host_timing_and_" "expensive_package_settle"
            ),
        },
        "calibration": _calibration(records),
        "ood": ood,
        "failureRate": round((count - accepted_count) / count, 9),
        "deterministicTemplateBaseline": baseline,
        "comparison": {
            "learnedTop1Accuracy": round(learned_accuracy, 9),
            "baselineTop1Accuracy": round(baseline_accuracy, 9),
            "learnedSuperioritySupported": superiority_supported,
            "claim": (
                "held_out_learned_improvement_observed"
                if superiority_supported
                else "no_superiority_claim_baseline_equal_or_better"
            ),
        },
        "records": records,
    }


def _evaluate_centroid_baseline(
    model: dict[str, Any], samples: list[dict[str, Any]]
) -> dict[str, Any]:
    means = list(map(float, model["normalization"]["means"]))
    scales = list(map(float, model["normalization"]["scales"]))
    correct = 0
    parameter_errors: dict[str, list[float]] = {name: [] for name in TARGET_NAMES}
    for sample in samples:
        normalized = [
            (value - mean) / scale
            for value, mean, scale in zip(
                feature_vector(sample["input"]), means, scales, strict=True
            )
        ]
        selected = min(
            FAMILIES,
            key=lambda family: (
                sum(
                    (left - right) ** 2
                    for left, right in zip(
                        normalized,
                        model["familyCentroids"][family],
                        strict=True,
                    )
                ),
                family,
            ),
        )
        correct += int(selected == sample["target"]["garmentFamily"])
        defaults = {"lengthScale": 1.0, "widthScale": 1.0, "easeNormalized": 0.0}
        for name in TARGET_NAMES:
            parameter_errors[name].append(
                abs(defaults[name] - float(sample["target"]["continuousParameters"][name]))
            )
    return {
        "name": "nearest_training_centroid_plus_default_parameters",
        "usesTargetDefiningInputFields": False,
        "top1Correct": correct,
        "top1Accuracy": round(correct / len(samples), 9),
        "continuousParameterMae": {
            name: round(sum(values) / len(values), 9) for name, values in parameter_errors.items()
        },
    }


def _evaluate_challenges(model: dict[str, Any], challenges: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    correct = 0
    for challenge in challenges:
        prediction = predict_v2(model, challenge["input"])
        actual_action = (
            "reject"
            if prediction["status"] == "rejected"
            else ("defer" if prediction["fallbackRequired"] else "accept")
        )
        expected = challenge["expectedAction"]
        accepted = actual_action == expected or (expected == "defer" and actual_action == "reject")
        correct += int(accepted)
        records.append(
            {
                "challengeId": challenge["challengeId"],
                "kind": challenge["kind"],
                "expectedAction": expected,
                "actualAction": actual_action,
                "passed": accepted,
            }
        )
    return {
        "challengeCount": len(records),
        "correctActionCount": correct,
        "rejectionAccuracy": round(correct / len(records), 9),
        "records": records,
    }


def _calibration(records: list[dict[str, Any]]) -> dict[str, Any]:
    bins = []
    weighted_error = 0.0
    for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
        upper = lower + 0.2
        members = [
            record
            for record in records
            if lower <= float(record["confidence"]) <= upper + (1e-12 if upper == 1.0 else 0.0)
        ]
        if not members:
            continue
        confidence = sum(float(record["confidence"]) for record in members) / len(members)
        accuracy = sum(bool(record["correct"]) for record in members) / len(members)
        weighted_error += len(members) / len(records) * abs(confidence - accuracy)
        bins.append(
            {
                "lower": lower,
                "upper": round(upper, 1),
                "count": len(members),
                "meanConfidence": round(confidence, 9),
                "accuracy": round(accuracy, 9),
            }
        )
    return {"expectedCalibrationError": round(weighted_error, 9), "bins": bins}


def _compiled_geometry_errors(
    expected: dict[str, Any], predicted: dict[str, Any]
) -> tuple[float, float]:
    expected_bounds = _pattern_bounds(expected)
    predicted_bounds = _pattern_bounds(predicted)
    expected_width = max(expected_bounds[2] - expected_bounds[0], 1e-9)
    expected_height = max(expected_bounds[3] - expected_bounds[1], 1e-9)
    predicted_width = predicted_bounds[2] - predicted_bounds[0]
    predicted_height = predicted_bounds[3] - predicted_bounds[1]
    silhouette = (
        abs(predicted_width - expected_width) / expected_width
        + abs(predicted_height - expected_height) / expected_height
    ) / 2
    expected_aspect = expected_height / expected_width
    predicted_aspect = predicted_height / max(predicted_width, 1e-9)
    fit = abs(predicted_aspect - expected_aspect) / max(expected_aspect, 1e-9)
    return silhouette, fit


def _pattern_bounds(pattern: dict[str, Any]) -> tuple[float, float, float, float]:
    points = [
        point
        for panel in pattern["panels"]
        for edge in panel["boundary"]
        for point in edge["curve"]["points"]
    ]
    return (
        min(float(point[0]) for point in points),
        min(float(point[1]) for point in points),
        max(float(point[0]) for point in points),
        max(float(point[1]) for point in points),
    )


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    value = sum(values) / len(values)
    if not math.isfinite(value):
        raise ValueError("nonfinite_evaluation_metric")
    return round(value, 9)
