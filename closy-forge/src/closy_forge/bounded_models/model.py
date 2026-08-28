from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from closy_forge.simulation.material_physics import build_material_preset_registry

from .contracts import (
    FAILURE_TARGETS,
    FEATURE_NAMES,
    MODEL_VERSION,
    TRAINING_CONFIG_VERSION,
    canonical_hash,
    feature_vector,
    rounded,
)
from .dataset import rows_for_split
from .solver_fixtures import confidence_from_margin

TRIAL_CONFIGS: tuple[dict[str, str | float], ...] = (
    {"trialId": "trial.0", "ridgeL2": 0.001, "logisticL2": 0.0005, "learningRate": 0.08},
    {"trialId": "trial.1", "ridgeL2": 0.01, "logisticL2": 0.001, "learningRate": 0.06},
    {"trialId": "trial.2", "ridgeL2": 0.05, "logisticL2": 0.004, "learningRate": 0.04},
)
EPOCHS = 60


def train_phase14_model(dataset: dict[str, Any]) -> dict[str, Any]:
    train_rows = rows_for_split(dataset, "train")
    validation_rows = rows_for_split(dataset, "validation")
    scaler = _fit_scaler(train_rows)
    envelope = _fit_envelope(train_rows, scaler)
    trials: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for config in TRIAL_CONFIGS:
        material_weights = _train_ridge(train_rows, scaler, l2=float(config["ridgeL2"]))
        failure_weights = _train_logistic(
            train_rows,
            scaler,
            learning_rate=float(config["learningRate"]),
            l2=float(config["logisticL2"]),
            epochs=EPOCHS,
        )
        candidate = {
            "materialWeights": material_weights,
            "failureWeights": failure_weights,
        }
        validation = _validation_objective(candidate, scaler, validation_rows)
        trials.append({**config, **validation})
        candidates.append(candidate)
    selected_index = min(
        range(len(trials)), key=lambda index: (float(trials[index]["objective"]), index)
    )
    selected = candidates[selected_index]
    model: dict[str, Any] = {
        "schemaVersion": 1,
        "modelVersion": MODEL_VERSION,
        "modelKind": "bounded_linear_material_ranker_and_multilabel_logistic_warning_model",
        "authority": "advisory_rank_warn_or_fallback_only",
        "deterministicValidatorsRetainFinalAuthority": True,
        "featureNames": list(FEATURE_NAMES),
        "failureTargets": list(FAILURE_TARGETS),
        "normalization": scaler,
        "oodEnvelope": envelope,
        "materialRanker": {
            "weights": selected["materialWeights"],
            "confidenceMinimum": 0.56,
            "fallbackPresetId": "material.cotton_jersey_d0_v1",
        },
        "failurePredictor": {
            "weights": selected["failureWeights"],
            "warningThreshold": 0.5,
            "calibrationKind": "uncalibrated_sigmoid_reported_with_brier_and_ece",
        },
        "training": {
            "configVersion": TRAINING_CONFIG_VERSION,
            "datasetHash": dataset["integrity"]["datasetHash"],
            "trainOnlyPreprocessing": True,
            "trialCount": len(TRIAL_CONFIGS),
            "maximumTrials": 4,
            "epochsPerTrial": EPOCHS,
            "maximumEpochs": 80,
            "selectedTrialId": trials[selected_index]["trialId"],
            "trials": trials,
            "cpuOnly": True,
        },
        "fallbackPolicy": {
            "ood": "deterministic_material_preset",
            "lowConfidence": "deterministic_material_preset",
            "modelError": "deterministic_material_preset_and_validator_only",
        },
        "integrity": {"weightsHash": "", "modelHash": ""},
    }
    model["integrity"]["weightsHash"] = canonical_hash(
        {
            "material": model["materialRanker"]["weights"],
            "failure": model["failurePredictor"]["weights"],
        }
    )
    model["integrity"]["modelHash"] = model_hash(model)
    return model


def predict_candidate(model: dict[str, Any], features: dict[str, float]) -> dict[str, Any]:
    try:
        raw = feature_vector(features)
    except ValueError as error:
        return _fallback_prediction(str(error))
    normalized = _normalize(raw, model["normalization"])
    ood_reasons = _ood_reasons(normalized, model["oodEnvelope"])
    if ood_reasons:
        result = _fallback_prediction("out_of_distribution")
        result["oodReasons"] = ood_reasons
        return result
    row = [1.0, *normalized]
    material_score = _clamp(
        _dot(list(map(float, model["materialRanker"]["weights"])), row), 0.0, 1.0
    )
    probabilities = {
        target: rounded(_sigmoid(_dot(list(map(float, weights)), row)))
        for target, weights in zip(
            FAILURE_TARGETS, model["failurePredictor"]["weights"], strict=True
        )
    }
    return {
        "status": "predicted",
        "fallbackRequired": False,
        "reason": "bounded_advisory_model",
        "materialQualityScore": rounded(material_score),
        "failureProbabilities": probabilities,
        "warnings": sorted(name for name, value in probabilities.items() if value >= 0.5),
        "oodReasons": [],
        "authority": "advisory_only",
    }


def rank_material_presets(
    model: dict[str, Any], scenario_features: dict[str, float]
) -> dict[str, Any]:
    registry = build_material_preset_registry()
    ranked: list[dict[str, Any]] = []
    for descriptor in registry["presets"]:
        features = {**scenario_features, **_material_features(descriptor)}
        prediction = predict_candidate(model, features)
        if prediction["fallbackRequired"]:
            return _material_fallback(model, str(prediction["reason"]))
        ranked.append(
            {
                "presetId": descriptor["presetId"],
                "predictedQualityScore": prediction["materialQualityScore"],
            }
        )
    ranked.sort(key=lambda item: (-float(item["predictedQualityScore"]), str(item["presetId"])))
    margin = float(ranked[0]["predictedQualityScore"]) - float(ranked[1]["predictedQualityScore"])
    confidence = confidence_from_margin(margin, out_of_domain=False)
    if confidence < float(model["materialRanker"]["confidenceMinimum"]):
        return _material_fallback(model, "low_ranking_confidence")
    selected = next(
        item for item in registry["presets"] if item["presetId"] == ranked[0]["presetId"]
    )
    fields = selected["fields"]
    stiffness = 0.5 * (
        float(fields["warpStretchStiffness"]["value"])
        + float(fields["weftStretchStiffness"]["value"])
    )
    return {
        "status": "ranked",
        "selectedPresetId": selected["presetId"],
        "ranked": ranked,
        "confidence": confidence,
        "fallbackRequired": False,
        "priors": {
            "stiffnessNPerM": rounded(stiffness),
            "complianceMetersPerNewton": rounded(1.0 / stiffness),
            "dampingRatio": fields["dampingRatio"]["value"],
            "thicknessMeters": fields["thickness"]["value"],
        },
        "authority": "advisory_initialization_only",
    }


def model_hash(model: dict[str, Any]) -> str:
    payload = deepcopy(model)
    payload.setdefault("integrity", {})["modelHash"] = ""
    return canonical_hash(payload)


def validate_model(model: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if model.get("modelVersion") != MODEL_VERSION:
        issues.append("model_version_invalid")
    if model.get("featureNames") != list(FEATURE_NAMES):
        issues.append("model_feature_axis_invalid")
    if model.get("failureTargets") != list(FAILURE_TARGETS):
        issues.append("model_target_axis_invalid")
    if model.get("deterministicValidatorsRetainFinalAuthority") is not True:
        issues.append("validator_authority_invalid")
    training = model.get("training", {})
    if int(training.get("trialCount", 99)) > 4 or int(training.get("epochsPerTrial", 99)) > 80:
        issues.append("training_budget_exceeded")
    if model.get("integrity", {}).get("weightsHash") != canonical_hash(
        {
            "material": model.get("materialRanker", {}).get("weights"),
            "failure": model.get("failurePredictor", {}).get("weights"),
        }
    ):
        issues.append("model_weights_hash_mismatch")
    if model.get("integrity", {}).get("modelHash") != model_hash(model):
        issues.append("model_hash_mismatch")
    return issues


def _fit_scaler(rows: list[dict[str, Any]]) -> dict[str, list[float]]:
    vectors = [feature_vector(row["featureSnapshot"]) for row in rows]
    means = [
        sum(row[index] for row in vectors) / len(vectors) for index in range(len(FEATURE_NAMES))
    ]
    scales: list[float] = []
    for index, mean in enumerate(means):
        variance = sum((row[index] - mean) ** 2 for row in vectors) / len(vectors)
        scales.append(max(math.sqrt(variance), 1e-9))
    return {
        "means": [rounded(value) for value in means],
        "scales": [rounded(value) for value in scales],
    }


def _fit_envelope(rows: list[dict[str, Any]], scaler: dict[str, list[float]]) -> dict[str, Any]:
    normalized = [_normalize(feature_vector(row["featureSnapshot"]), scaler) for row in rows]
    minimums = [min(row[index] for row in normalized) for index in range(len(FEATURE_NAMES))]
    maximums = [max(row[index] for row in normalized) for index in range(len(FEATURE_NAMES))]
    return {
        "minimums": [rounded(value) for value in minimums],
        "maximums": [rounded(value) for value in maximums],
        "margin": 0.75,
        "action": "reject_and_use_deterministic_preset",
    }


def _train_ridge(
    rows: list[dict[str, Any]], scaler: dict[str, list[float]], *, l2: float
) -> list[float]:
    x = [[1.0, *_normalize(feature_vector(row["featureSnapshot"]), scaler)] for row in rows]
    y = [float(row["targets"]["materialQualityScore"]) for row in rows]
    width = len(FEATURE_NAMES) + 1
    matrix = [[0.0 for _ in range(width)] for _ in range(width)]
    target = [0.0 for _ in range(width)]
    for values, expected in zip(x, y, strict=True):
        for i in range(width):
            target[i] += values[i] * expected
            for j in range(width):
                matrix[i][j] += values[i] * values[j]
    for index in range(1, width):
        matrix[index][index] += l2 * len(rows)
    return [rounded(value) for value in _solve_linear_system(matrix, target)]


def _train_logistic(
    rows: list[dict[str, Any]],
    scaler: dict[str, list[float]],
    *,
    learning_rate: float,
    l2: float,
    epochs: int,
) -> list[list[float]]:
    x = [[1.0, *_normalize(feature_vector(row["featureSnapshot"]), scaler)] for row in rows]
    width = len(FEATURE_NAMES) + 1
    weights = [[0.0 for _ in range(width)] for _ in FAILURE_TARGETS]
    for _epoch in range(epochs):
        gradients = [[0.0 for _ in range(width)] for _ in FAILURE_TARGETS]
        for values, source in zip(x, rows, strict=True):
            labels = source["targets"]["failures"]
            for target_index, name in enumerate(FAILURE_TARGETS):
                residual = _sigmoid(_dot(weights[target_index], values)) - float(labels[name])
                for feature_index, value in enumerate(values):
                    gradients[target_index][feature_index] += residual * value
        for target_index in range(len(FAILURE_TARGETS)):
            for feature_index in range(width):
                penalty = 0.0 if feature_index == 0 else l2 * weights[target_index][feature_index]
                weights[target_index][feature_index] -= learning_rate * (
                    gradients[target_index][feature_index] / len(rows) + penalty
                )
    return [[rounded(value) for value in row] for row in weights]


def _validation_objective(
    candidate: dict[str, Any], scaler: dict[str, list[float]], rows: list[dict[str, Any]]
) -> dict[str, float]:
    material_error = 0.0
    log_loss = 0.0
    for source in rows:
        row = [1.0, *_normalize(feature_vector(source["featureSnapshot"]), scaler)]
        material_error += abs(
            _dot(candidate["materialWeights"], row)
            - float(source["targets"]["materialQualityScore"])
        )
        for weights, name in zip(candidate["failureWeights"], FAILURE_TARGETS, strict=True):
            probability = _clamp(_sigmoid(_dot(weights, row)), 1e-9, 1.0 - 1e-9)
            expected = float(source["targets"]["failures"][name])
            log_loss -= expected * math.log(probability) + (1.0 - expected) * math.log(
                1.0 - probability
            )
    material_mae = material_error / len(rows)
    failure_log_loss = log_loss / (len(rows) * len(FAILURE_TARGETS))
    return {
        "materialMae": rounded(material_mae),
        "failureLogLoss": rounded(failure_log_loss),
        "objective": rounded(material_mae + 0.2 * failure_log_loss),
    }


def _normalize(values: list[float], scaler: dict[str, list[float]]) -> list[float]:
    return [
        (value - mean) / scale
        for value, mean, scale in zip(values, scaler["means"], scaler["scales"], strict=True)
    ]


def _ood_reasons(normalized: list[float], envelope: dict[str, Any]) -> list[str]:
    margin = float(envelope["margin"])
    return [
        FEATURE_NAMES[index]
        for index, value in enumerate(normalized)
        if value < float(envelope["minimums"][index]) - margin
        or value > float(envelope["maximums"][index]) + margin
    ]


def _solve_linear_system(matrix: list[list[float]], target: list[float]) -> list[float]:
    width = len(target)
    augmented = [row[:] + [target[index]] for index, row in enumerate(matrix)]
    for column in range(width):
        pivot = max(range(column, width), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise RuntimeError("ridge_normal_equation_singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(width):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column], strict=True)
            ]
    return [augmented[index][-1] for index in range(width)]


def _material_features(descriptor: dict[str, Any]) -> dict[str, float]:
    fields = descriptor["fields"]
    return {
        "materialWarpStiffnessNPerM": float(fields["warpStretchStiffness"]["value"]),
        "materialWeftStiffnessNPerM": float(fields["weftStretchStiffness"]["value"]),
        "materialShearStiffnessNPerM": float(fields["shearStiffness"]["value"]),
        "materialBendStiffnessNm": float(fields["bendStiffness"]["value"]),
        "materialDampingRatio": float(fields["dampingRatio"]["value"]),
        "materialThicknessMeters": float(fields["thickness"]["value"]),
        "materialCollisionClearanceMeters": float(fields["collisionClearance"]["value"]),
        "materialArealDensityKgM2": float(fields["arealDensity"]["value"]),
    }


def _fallback_prediction(reason: str) -> dict[str, Any]:
    return {
        "status": "deferred",
        "fallbackRequired": True,
        "reason": reason,
        "materialQualityScore": None,
        "failureProbabilities": None,
        "warnings": [],
        "oodReasons": [],
        "authority": "deterministic_fallback_required",
    }


def _material_fallback(model: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "status": "fallback",
        "selectedPresetId": model["materialRanker"]["fallbackPresetId"],
        "ranked": [],
        "confidence": 0.0,
        "fallbackRequired": True,
        "reason": reason,
        "priors": None,
        "authority": "deterministic_preset_fallback",
    }


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        inverse = math.exp(-min(value, 60.0))
        return 1.0 / (1.0 + inverse)
    positive = math.exp(max(value, -60.0))
    return positive / (1.0 + positive)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
