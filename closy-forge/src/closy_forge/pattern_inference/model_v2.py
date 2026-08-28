from __future__ import annotations

import math
import random
from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .dataset_v2 import FEATURE_NAMES, feature_vector, samples_for_split
from .grammar_v2 import FAMILY_SPECS, compile_program, default_parameters, program_from_parameters

MODEL_VERSION = "closy.pattern_inference.linear_multitask.d0.v1"
FAMILIES = tuple(FAMILY_SPECS)
TARGET_NAMES = ("lengthScale", "widthScale", "easeNormalized")
MULTITASK_REGRESSION_WEIGHT = 0.35


def train_model_v2(
    dataset: dict[str, Any],
    split: dict[str, Any],
    *,
    seed: int = 9102,
    epochs: int = 80,
    learning_rate: float = 0.16,
    regression_learning_rate: float = 0.45,
    l2: float = 0.0008,
) -> dict[str, Any]:
    train = samples_for_split(dataset, split, "train")
    if not train:
        raise ValueError("training_split_empty")
    raw_x = [feature_vector(sample["input"]) for sample in train]
    means = [sum(row[index] for row in raw_x) / len(raw_x) for index in range(len(FEATURE_NAMES))]
    scales = []
    for index, mean in enumerate(means):
        variance = sum((row[index] - mean) ** 2 for row in raw_x) / len(raw_x)
        scales.append(max(math.sqrt(variance), 1e-6))
    x = [_normalized_with_bias(row, means, scales) for row in raw_x]
    labels = [FAMILIES.index(str(sample["target"]["garmentFamily"])) for sample in train]
    targets = [
        [float(sample["target"]["continuousParameters"][name]) for name in TARGET_NAMES]
        for sample in train
    ]
    width = len(FEATURE_NAMES) + 1
    random_source = random.Random(seed)
    class_weights = [[random_source.uniform(-0.001, 0.001) for _ in range(width)] for _ in FAMILIES]
    regression_weights = [
        [random_source.uniform(-0.001, 0.001) for _ in range(width)] for _ in TARGET_NAMES
    ]
    curve: list[dict[str, float | int]] = []
    for epoch in range(epochs + 1):
        class_gradient = [[0.0 for _ in range(width)] for _ in FAMILIES]
        regression_gradient = [[0.0 for _ in range(width)] for _ in TARGET_NAMES]
        cross_entropy = 0.0
        squared_error = 0.0
        for row, label, target in zip(x, labels, targets, strict=True):
            probabilities = _softmax([_dot(weights, row) for weights in class_weights])
            cross_entropy -= math.log(max(probabilities[label], 1e-15))
            for class_index, probability in enumerate(probabilities):
                residual = probability - (1.0 if class_index == label else 0.0)
                for feature_index, value in enumerate(row):
                    class_gradient[class_index][feature_index] += residual * value
            for target_index, expected in enumerate(target):
                predicted = _dot(regression_weights[target_index], row)
                residual = predicted - expected
                squared_error += residual * residual
                for feature_index, value in enumerate(row):
                    regression_gradient[target_index][feature_index] += 2.0 * residual * value
        sample_count = len(x)
        cross_entropy /= sample_count
        mean_squared_error = squared_error / (sample_count * len(TARGET_NAMES))
        regularization = l2 * (
            sum(value * value for weights in class_weights for value in weights[1:])
            + sum(value * value for weights in regression_weights for value in weights[1:])
        )
        total_loss = (
            cross_entropy + MULTITASK_REGRESSION_WEIGHT * mean_squared_error + regularization
        )
        if epoch % 10 == 0 or epoch == epochs:
            curve.append(
                {
                    "epoch": epoch,
                    "crossEntropy": round(cross_entropy, 12),
                    "meanSquaredError": round(mean_squared_error, 12),
                    "regularization": round(regularization, 12),
                    "totalLoss": round(total_loss, 12),
                }
            )
        if epoch == epochs:
            break
        for class_index in range(len(FAMILIES)):
            for feature_index in range(width):
                penalty = (
                    0.0
                    if feature_index == 0
                    else 2.0 * l2 * class_weights[class_index][feature_index]
                )
                class_weights[class_index][feature_index] -= learning_rate * (
                    class_gradient[class_index][feature_index] / sample_count + penalty
                )
        for target_index in range(len(TARGET_NAMES)):
            for feature_index in range(width):
                penalty = (
                    0.0
                    if feature_index == 0
                    else 2.0 * l2 * regression_weights[target_index][feature_index]
                )
                regression_weights[target_index][feature_index] -= regression_learning_rate * (
                    MULTITASK_REGRESSION_WEIGHT
                    * regression_gradient[target_index][feature_index]
                    / (sample_count * len(TARGET_NAMES))
                    + penalty
                )

    centroids = _family_centroids(train, means, scales)
    validation = samples_for_split(dataset, split, "validation")
    validation_distances = [
        min(
            _squared_distance(_normalize(feature_vector(item["input"]), means, scales), centroid)
            for centroid in centroids.values()
        )
        for item in validation
    ]
    distance_threshold = max(validation_distances, default=1.0) * 1.8 + 0.05
    model: dict[str, Any] = {
        "schemaVersion": 1,
        "modelVersion": MODEL_VERSION,
        "modelKind": "project_owned_multitask_linear_softmax_and_regression",
        "seed": seed,
        "optimizer": {
            "name": "full_batch_gradient_descent",
            "epochs": epochs,
            "classificationLearningRate": learning_rate,
            "regressionLearningRate": regression_learning_rate,
            "l2": l2,
            "declaredLoss": "cross_entropy + 0.35 * parameter_mse + l2",
            "regressionLossWeight": MULTITASK_REGRESSION_WEIGHT,
            "parameterMseReduction": "mean_over_samples_and_three_targets",
            "seed": seed,
            "seedUse": "deterministic_uniform_weight_initialization",
        },
        "numericPolicy": {
            "trainingArithmetic": "python_binary64",
            "canonicalWeightDigits": 12,
            "canonicalPredictionDigits": 9,
        },
        "featureNames": list(FEATURE_NAMES),
        "families": list(FAMILIES),
        "targetNames": list(TARGET_NAMES),
        "normalization": {
            "means": _round_vector(means),
            "scales": _round_vector(scales),
        },
        "classWeights": [_round_vector(weights) for weights in class_weights],
        "regressionWeights": [_round_vector(weights) for weights in regression_weights],
        "familyCentroids": {family: _round_vector(centroids[family]) for family in FAMILIES},
        "oodPolicy": {
            "minimumConfidence": 0.52,
            "maximumNormalizedDistanceSquared": round(distance_threshold, 12),
            "nonFiniteAction": "reject",
            "outOfEnvelopeAction": "defer_to_template_baseline",
        },
        "trainingCurve": curve,
        "trainingSampleCount": len(train),
        "learnedParametersPersisted": True,
        "integrity": {
            "weightsHash": "",
            "modelHash": "",
            "modelHashSemantics": "canonical_model_bytes_with_modelHash_field_blank",
        },
    }
    weights_payload = {
        "classWeights": model["classWeights"],
        "regressionWeights": model["regressionWeights"],
    }
    model["integrity"]["weightsHash"] = sha256_bytes(
        canonical_dumps(weights_payload).encode("utf-8")
    )
    model["integrity"]["modelHash"] = _model_hash(model)
    if curve[-1]["totalLoss"] >= curve[0]["totalLoss"]:
        raise RuntimeError("training_loss_did_not_decrease")
    if not any(abs(value) > 1e-8 for weights in class_weights for value in weights):
        raise RuntimeError("classification_parameters_not_learned")
    return model


def predict_v2(model: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = feature_vector(observation)
    except (KeyError, TypeError, ValueError):
        return _rejected_prediction("corrupted_capture")
    if any(not math.isfinite(value) for value in raw):
        return _rejected_prediction("nonfinite_capture")
    means = list(map(float, model["normalization"]["means"]))
    scales = list(map(float, model["normalization"]["scales"]))
    normalized = _normalize(raw, means, scales)
    row = [1.0, *normalized]
    probabilities = _softmax([_dot(weights, row) for weights in model["classWeights"]])
    ranked_indices = sorted(
        range(len(FAMILIES)), key=lambda index: (-probabilities[index], FAMILIES[index])
    )
    family = FAMILIES[ranked_indices[0]]
    confidence = probabilities[ranked_indices[0]]
    distances = {
        name: _squared_distance(normalized, list(map(float, centroid)))
        for name, centroid in model["familyCentroids"].items()
    }
    nearest_distance = min(distances.values())
    out_of_envelope = any(abs(value) > 7.5 for value in normalized)
    deferred = (
        confidence < float(model["oodPolicy"]["minimumConfidence"])
        or nearest_distance > float(model["oodPolicy"]["maximumNormalizedDistanceSquared"])
        or out_of_envelope
    )
    continuous = {
        name: round(_dot(weights, row), 9)
        for name, weights in zip(TARGET_NAMES, model["regressionWeights"], strict=True)
    }
    return {
        "status": "deferred" if deferred else "predicted",
        "family": family,
        "confidence": round(confidence, 9),
        "topK": [
            {"family": FAMILIES[index], "probability": round(probabilities[index], 9)}
            for index in ranked_indices[:3]
        ],
        "continuousParameters": continuous,
        "nearestCentroidDistanceSquared": round(nearest_distance, 9),
        "fallbackRequired": deferred,
        "reason": "out_of_domain_or_ambiguous" if deferred else "learned_model",
    }


def decode_prediction(
    prediction: dict[str, Any], *, program_id: str, base_seed: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    if prediction.get("status") != "predicted":
        raise ValueError("prediction_must_be_accepted_before_grammar_decode")
    family = str(prediction["family"])
    spec = FAMILY_SPECS[family]
    values = default_parameters(family)
    continuous = prediction["continuousParameters"]
    length_scale = _clamp(float(continuous["lengthScale"]), 0.90, 1.10)
    width_scale = _clamp(float(continuous["widthScale"]), 0.93, 1.07)
    ease_normalized = _clamp(float(continuous["easeNormalized"]), -0.84, 0.84)
    values[spec.length_field] = round(float(values[spec.length_field]) * length_scale, 9)
    values[spec.width_field] = round(float(values[spec.width_field]) * width_scale, 9)
    values[spec.ease_field] = round(float(values[spec.ease_field]) + ease_normalized * 0.012, 9)
    program = program_from_parameters(
        family,
        values,
        program_id=program_id,
        base_seed=base_seed,
    )
    return program, compile_program(program)


def deterministic_template_fallback(
    model: dict[str, Any], observation: dict[str, Any], *, program_id: str, base_seed: int
) -> tuple[dict[str, Any], dict[str, Any], str]:
    try:
        raw = feature_vector(observation)
        if any(not math.isfinite(value) for value in raw):
            raise ValueError
        means = list(map(float, model["normalization"]["means"]))
        scales = list(map(float, model["normalization"]["scales"]))
        normalized = _normalize(raw, means, scales)
        family = min(
            FAMILIES,
            key=lambda name: (
                _squared_distance(normalized, list(map(float, model["familyCentroids"][name]))),
                name,
            ),
        )
        reason = "nearest_training_centroid_template_baseline"
    except (KeyError, TypeError, ValueError):
        family = FAMILIES[0]
        reason = "corrupt_capture_safe_default_template"
    program = program_from_parameters(
        family,
        default_parameters(family),
        program_id=program_id,
        base_seed=base_seed,
    )
    return program, compile_program(program), reason


def canonical_model_bytes(model: dict[str, Any]) -> bytes:
    return canonical_dumps(model).encode("utf-8")


def classification_sample_loss_gradient(
    weights: list[list[float]], row: list[float], label: int, *, l2: float
) -> tuple[float, list[list[float]]]:
    probabilities = _softmax([_dot(class_weights, row) for class_weights in weights])
    penalty = l2 * sum(value * value for class_weights in weights for value in class_weights[1:])
    gradient = []
    for class_index, class_weights in enumerate(weights):
        residual = probabilities[class_index] - (1.0 if class_index == label else 0.0)
        gradient.append(
            [
                residual * value
                + (0.0 if feature_index == 0 else 2.0 * l2 * class_weights[feature_index])
                for feature_index, value in enumerate(row)
            ]
        )
    return -math.log(max(probabilities[label], 1e-15)) + penalty, gradient


def regression_sample_loss_gradient(
    weights: list[float], row: list[float], target: float, *, l2: float
) -> tuple[float, list[float]]:
    residual = _dot(weights, row) - target
    loss = residual * residual + l2 * sum(value * value for value in weights[1:])
    gradient = [
        2.0 * residual * value + (0.0 if index == 0 else 2.0 * l2 * weights[index])
        for index, value in enumerate(row)
    ]
    return loss, gradient


def multitask_sample_loss_gradient(
    class_weights: list[list[float]],
    regression_weights: list[list[float]],
    row: list[float],
    label: int,
    targets: list[float],
    *,
    l2: float,
    regression_weight: float = MULTITASK_REGRESSION_WEIGHT,
) -> tuple[float, list[list[float]], list[list[float]]]:
    if len(regression_weights) != len(targets) or not targets:
        raise ValueError("multitask_target_axis_invalid")
    probabilities = _softmax([_dot(weights, row) for weights in class_weights])
    class_gradient: list[list[float]] = []
    for class_index, weights in enumerate(class_weights):
        residual = probabilities[class_index] - (1.0 if class_index == label else 0.0)
        class_gradient.append(
            [
                residual * value + (0.0 if index == 0 else 2.0 * l2 * weights[index])
                for index, value in enumerate(row)
            ]
        )
    regression_gradient: list[list[float]] = []
    squared_error = 0.0
    for weights, target in zip(regression_weights, targets, strict=True):
        residual = _dot(weights, row) - target
        squared_error += residual * residual
        regression_gradient.append(
            [
                regression_weight * 2.0 * residual * value / len(targets)
                + (0.0 if index == 0 else 2.0 * l2 * weights[index])
                for index, value in enumerate(row)
            ]
        )
    regularization = l2 * (
        sum(value * value for weights in class_weights for value in weights[1:])
        + sum(value * value for weights in regression_weights for value in weights[1:])
    )
    loss = (
        -math.log(max(probabilities[label], 1e-15))
        + regression_weight * squared_error / len(targets)
        + regularization
    )
    return loss, class_gradient, regression_gradient


def validate_model_v2(model: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if model.get("modelVersion") != MODEL_VERSION:
        issues.append("model_version_invalid")
    if model.get("featureNames") != list(FEATURE_NAMES) or model.get("families") != list(FAMILIES):
        issues.append("model_axis_contract_invalid")
    expected_width = len(FEATURE_NAMES) + 1
    class_weights = model.get("classWeights", [])
    regression_weights = model.get("regressionWeights", [])
    if len(class_weights) != len(FAMILIES) or any(
        len(row) != expected_width for row in class_weights
    ):
        issues.append("classification_weights_invalid")
    if len(regression_weights) != len(TARGET_NAMES) or any(
        len(row) != expected_width for row in regression_weights
    ):
        issues.append("regression_weights_invalid")
    curve = model.get("trainingCurve", [])
    if not curve or float(curve[-1].get("totalLoss", math.inf)) >= float(
        curve[0].get("totalLoss", -math.inf)
    ):
        issues.append("training_optimization_evidence_invalid")
    weights_payload = {
        "classWeights": class_weights,
        "regressionWeights": regression_weights,
    }
    if model.get("integrity", {}).get("weightsHash") != sha256_bytes(
        canonical_dumps(weights_payload).encode("utf-8")
    ):
        issues.append("model_weights_hash_mismatch")
    if model.get("integrity", {}).get("modelHash") != _model_hash(model):
        issues.append("model_hash_mismatch")
    return issues


def _family_centroids(
    samples: list[dict[str, Any]], means: list[float], scales: list[float]
) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for family in FAMILIES:
        vectors = [
            _normalize(feature_vector(sample["input"]), means, scales)
            for sample in samples
            if sample["target"]["garmentFamily"] == family
        ]
        result[family] = [
            sum(vector[index] for vector in vectors) / len(vectors)
            for index in range(len(FEATURE_NAMES))
        ]
    return result


def _rejected_prediction(reason: str) -> dict[str, Any]:
    return {
        "status": "rejected",
        "family": None,
        "confidence": 0.0,
        "topK": [],
        "continuousParameters": None,
        "nearestCentroidDistanceSquared": None,
        "fallbackRequired": True,
        "reason": reason,
    }


def _normalized_with_bias(
    values: list[float], means: list[float], scales: list[float]
) -> list[float]:
    return [1.0, *_normalize(values, means, scales)]


def _normalize(values: list[float], means: list[float], scales: list[float]) -> list[float]:
    return [
        (value - mean) / scale for value, mean, scale in zip(values, means, scales, strict=True)
    ]


def _softmax(scores: list[float]) -> list[float]:
    offset = max(scores)
    exponentials = [math.exp(score - offset) for score in scores]
    total = sum(exponentials)
    return [value / total for value in exponentials]


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _squared_distance(left: list[float], right: list[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right, strict=True))


def _round_vector(values: list[float]) -> list[float]:
    return [round(value, 12) for value in values]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _model_hash(model: dict[str, Any]) -> str:
    payload = deepcopy(model)
    payload.setdefault("integrity", {})["modelHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
