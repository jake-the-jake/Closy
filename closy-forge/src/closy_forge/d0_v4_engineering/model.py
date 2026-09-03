from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.disjoint_benchmark_v1.protocol import (
    OBSERVABLE_PARAMETERS,
    PARAMETER_RANGES,
)
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes

from .corpus import observation_for_record
from .observation import FEATURE_NAMES, observation_contract

MODEL_VERSION = "closy.d0_v4.structured_rgb_multitask.v2"
LEGACY_MODEL_VERSION = "closy.d0_v4.structured_rgb_multitask.v1"
MODEL_ROOT = Path("models/d0_v4_engineering")
RIDGE = 0.075


def train_structured_model(
    training_records: Sequence[Mapping[str, Any]],
    validation_records: Sequence[Mapping[str, Any]],
    *,
    trial_id: str,
    seed: int,
) -> dict[str, Any]:
    if len(training_records) < 512 or len(validation_records) != 128:
        raise ValueError("d0_v4_training_inventory_invalid")
    train_observations = [observation_for_record(record) for record in training_records]
    raw_x = [_feature_vector(observation) for observation in train_observations]
    means = [_mean([row[index] for row in raw_x]) for index in range(len(FEATURE_NAMES))]
    scales = [
        max(
            math.sqrt(_mean([(row[index] - means[index]) ** 2 for row in raw_x])),
            1e-6,
        )
        for index in range(len(FEATURE_NAMES))
    ]
    design = [[1.0, *_polynomial_basis(_normalize(row, means, scales))] for row in raw_x]
    targets = [
        [
            _normalized_target(name, float(record["parameters"][name]))
            for name in OBSERVABLE_PARAMETERS
        ]
        for record in training_records
    ]
    weights = _ridge_multitask(design, targets, ridge=RIDGE)
    train_predictions = [
        _predict_parameters(weights, means, scales, observation)
        for observation in train_observations
    ]
    validation_observations = [observation_for_record(record) for record in validation_records]
    validation_predictions = [
        _predict_parameters(weights, means, scales, observation)
        for observation in validation_observations
    ]
    train_metrics = _parameter_metrics(training_records, train_predictions)
    validation_metrics = _parameter_metrics(validation_records, validation_predictions)
    residual_scales = {
        name: round(
            math.sqrt(
                _mean(
                    [
                        (float(prediction[name]) - float(record["parameters"][name])) ** 2
                        for record, prediction in zip(
                            validation_records, validation_predictions, strict=True
                        )
                    ]
                )
            ),
            12,
        )
        for name in OBSERVABLE_PARAMETERS
    }
    model: dict[str, Any] = {
        "schemaVersion": 1,
        "modelVersion": MODEL_VERSION,
        "trialId": trial_id,
        "architecture": "shared_40_feature_degree3_multiview_basis_with_11_bounded_heads",
        "inputEvidence": "actual_front_rear_rgb_pixels_via_frozen_observation_contract",
        "viewValidityMasksIncluded": True,
        "multivariate": True,
        "targetNames": list(OBSERVABLE_PARAMETERS),
        "featureNames": list(FEATURE_NAMES),
        "preprocessing": {
            "observationVersion": observation_contract()["contractVersion"],
            "observationContractDigest": observation_contract()["contractDigest"],
            "means": _round_vector(means),
            "scales": _round_vector(scales),
        },
        "optimizer": {
            "name": "deterministic_full_batch_ridge_normal_equation",
            "ridge": RIDGE,
            "epochs": 1,
            "linearSolveIterations": len(design[0]),
            "seed": seed,
            "seedRole": "recorded_reproducibility_identity_no_stochastic_update",
            "arithmetic": "python_binary64",
        },
        "outputConstraint": {
            "kind": "per_parameter_bounded_normalized_range_transform",
            "safeRanges": {name: list(PARAMETER_RANGES[name]) for name in OBSERVABLE_PARAMETERS},
            "rawUnboundedValuesRetained": True,
            "saturationThreshold": 0.025,
        },
        "weights": [_round_vector(row) for row in weights],
        "residualScales": residual_scales,
        "trainingSampleCount": len(training_records),
        "validationSampleCount": len(validation_records),
        "trainingMetrics": train_metrics,
        "validationMetrics": validation_metrics,
        "learnedWeightsPersisted": True,
        "targetParametersReadAtInference": False,
        "integrity": {
            "weightsSha256": sha256_bytes(
                canonical_dumps([_round_vector(row) for row in weights]).encode("utf-8")
            ),
            "modelSha256": "",
        },
    }
    model["integrity"]["modelSha256"] = model_digest(model)
    if validation_metrics["medianMacroNormalizedError"] >= 0.35:
        raise RuntimeError("d0_v4_model_failed_to_learn_observation_relationship")
    return model


def predict_structured(model: Mapping[str, Any], observation: Mapping[str, Any]) -> dict[str, Any]:
    issues = validate_model(model)
    if issues:
        return _rejection("model_invalid", issues)
    try:
        means = [float(value) for value in _mapping(model["preprocessing"])["means"]]
        scales = [float(value) for value in _mapping(model["preprocessing"])["scales"]]
        weights = [
            [float(value) for value in row] for row in model["weights"] if isinstance(row, list)
        ]
        values, logits = _predict_parameters_and_logits(weights, means, scales, observation)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return _rejection("observation_invalid", [f"{type(exc).__name__}:{exc}"])
    if any(not math.isfinite(value) for value in values.values()):
        return _rejection("nonfinite_prediction", [])
    residuals = _mapping(model.get("residualScales"))
    uncertainties = {
        name: round(
            min(
                PARAMETER_RANGES[name][1] - PARAMETER_RANGES[name][0],
                max(float(residuals.get(name, 0.01)) * 1.96, 1e-6),
            ),
            9,
        )
        for name in OBSERVABLE_PARAMETERS
    }
    alternatives = []
    for direction in (-1.0, 1.0):
        alternatives.append(
            {
                name: round(
                    _clamp(
                        values[name] + direction * uncertainties[name],
                        *PARAMETER_RANGES[name],
                    ),
                    9,
                )
                for name in OBSERVABLE_PARAMETERS
            }
        )
    saturation = {
        name: logits[name] < 0.025 or logits[name] > 0.975 for name in OBSERVABLE_PARAMETERS
    }
    parameters = {**values, **_fixed_parameters()}
    TShirtParameters(**parameters).validate()
    confidence = max(
        0.0,
        1.0
        - _mean(
            [
                uncertainties[name] / (PARAMETER_RANGES[name][1] - PARAMETER_RANGES[name][0])
                for name in OBSERVABLE_PARAMETERS
            ]
        ),
    )
    return {
        "status": "predicted",
        "parameters": parameters,
        "rawLogits": {name: round(logits[name], 12) for name in OBSERVABLE_PARAMETERS},
        "constraintSaturation": saturation,
        "uncertainty95": uncertainties,
        "confidence": round(confidence, 9),
        "alternatives": [{**alternative, **_fixed_parameters()} for alternative in alternatives],
        "evidenceClass": "learned_multiview_rgb_pixels",
        "targetParametersRead": False,
        "modelSha256": _mapping(model["integrity"])["modelSha256"],
    }


def metadata_only_baseline() -> dict[str, float]:
    parameters = {
        name: round((low + high) / 2.0, 9) for name, (low, high) in PARAMETER_RANGES.items()
    }
    parameters.update(_fixed_parameters())
    return parameters


def load_model(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError("d0_v4_model_mapping_required")
    issues = validate_model(value)
    if issues:
        raise ValueError("d0_v4_model_invalid:" + ";".join(issues))
    return value


def validate_model(model: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    version = model.get("modelVersion")
    if version not in {MODEL_VERSION, LEGACY_MODEL_VERSION}:
        issues.append("model_version_invalid")
    if model.get("featureNames") != list(FEATURE_NAMES):
        issues.append("feature_axis_invalid")
    if model.get("targetNames") != list(OBSERVABLE_PARAMETERS):
        issues.append("target_axis_invalid")
    preprocessing = _mapping(model.get("preprocessing"))
    if preprocessing.get("observationContractDigest") != observation_contract()["contractDigest"]:
        issues.append("observation_contract_mismatch")
    weights = model.get("weights")
    expected_width = (
        len(FEATURE_NAMES) * 3 + 1 if version == MODEL_VERSION else len(FEATURE_NAMES) + 1
    )
    if (
        not isinstance(weights, list)
        or len(weights) != len(OBSERVABLE_PARAMETERS)
        or any(not isinstance(row, list) or len(row) != expected_width for row in weights)
    ):
        issues.append("weight_shape_invalid")
    integrity = _mapping(model.get("integrity"))
    if integrity.get("modelSha256") != model_digest(model):
        issues.append("model_digest_invalid")
    return sorted(set(issues))


def model_digest(model: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(model))
    integrity = _mapping(payload.get("integrity"))
    integrity["modelSha256"] = ""
    payload["integrity"] = integrity
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _ridge_multitask(
    design: Sequence[Sequence[float]],
    targets: Sequence[Sequence[float]],
    *,
    ridge: float,
) -> list[list[float]]:
    width = len(design[0])
    target_count = len(targets[0])
    normal = [[0.0 for _ in range(width)] for _ in range(width)]
    rhs = [[0.0 for _ in range(target_count)] for _ in range(width)]
    for row, target in zip(design, targets, strict=True):
        for left in range(width):
            for right in range(width):
                normal[left][right] += row[left] * row[right]
            for output in range(target_count):
                rhs[left][output] += row[left] * target[output]
    for index in range(1, width):
        normal[index][index] += ridge
    solved = _gauss_jordan(normal, rhs)
    return [[solved[feature][target] for feature in range(width)] for target in range(target_count)]


def _gauss_jordan(matrix: list[list[float]], rhs: list[list[float]]) -> list[list[float]]:
    width = len(matrix)
    augmented = [matrix[index][:] + rhs[index][:] for index in range(width)]
    for column in range(width):
        pivot = max(range(column, width), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise RuntimeError("d0_v4_singular_training_system")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(width):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column], strict=True)
            ]
    return [row[width:] for row in augmented]


def _predict_parameters(
    weights: Sequence[Sequence[float]],
    means: Sequence[float],
    scales: Sequence[float],
    observation: Mapping[str, Any],
) -> dict[str, float]:
    values, _ = _predict_parameters_and_logits(weights, means, scales, observation)
    return values


def _predict_parameters_and_logits(
    weights: Sequence[Sequence[float]],
    means: Sequence[float],
    scales: Sequence[float],
    observation: Mapping[str, Any],
) -> tuple[dict[str, float], dict[str, float]]:
    normalized = _normalize(_feature_vector(observation), means, scales)
    polynomial_model = len(weights[0]) == len(FEATURE_NAMES) * 3 + 1
    row = [1.0, *_polynomial_basis(normalized)] if polynomial_model else [1.0, *normalized]
    logits = {name: _dot(weights[index], row) for index, name in enumerate(OBSERVABLE_PARAMETERS)}
    values = {
        name: round(
            low
            + (high - low)
            * (_clamp(logits[name], 0.0, 1.0) if polynomial_model else _sigmoid(logits[name])),
            9,
        )
        for name, (low, high) in PARAMETER_RANGES.items()
    }
    return values, logits


def _parameter_metrics(
    records: Sequence[Mapping[str, Any]], predictions: Sequence[Mapping[str, float]]
) -> dict[str, Any]:
    rows = []
    for record, prediction in zip(records, predictions, strict=True):
        errors = {
            name: abs(float(prediction[name]) - float(record["parameters"][name]))
            / (PARAMETER_RANGES[name][1] - PARAMETER_RANGES[name][0])
            for name in OBSERVABLE_PARAMETERS
        }
        rows.append(
            {
                "macro": _mean(list(errors.values())),
                "worst": max(errors.values()),
            }
        )
    macros = sorted(float(row["macro"]) for row in rows)
    return {
        "recordCount": len(rows),
        "meanMacroNormalizedError": round(_mean(macros), 12),
        "medianMacroNormalizedError": round(
            (macros[(len(macros) - 1) // 2] + macros[len(macros) // 2]) / 2.0,
            12,
        ),
        "worstNormalizedError": round(max(float(row["worst"]) for row in rows), 12),
        "finitePredictionRate": 1.0,
        "safeDomainRate": 1.0,
    }


def _feature_vector(observation: Mapping[str, Any]) -> list[float]:
    names = observation.get("featureNames")
    values = observation.get("featureValues")
    if names != list(FEATURE_NAMES) or not isinstance(values, list) or len(values) != 40:
        raise ValueError("d0_v4_observation_feature_axis_invalid")
    result = [float(value) for value in values]
    if any(not math.isfinite(value) for value in result):
        raise ValueError("d0_v4_observation_nonfinite")
    return result


def _normalized_target(name: str, value: float) -> float:
    low, high = PARAMETER_RANGES[name]
    return _clamp((value - low) / (high - low), 0.001, 0.999)


def _fixed_parameters() -> dict[str, float]:
    return {
        "sleeve_cap_height": 0.105,
        "hem_allowance": 0.025,
        "neckband_width": 0.035,
        "neckband_length_ease_ratio": 0.92,
        "target_panel_edge_length": 0.075,
    }


def _normalize(
    values: Sequence[float], means: Sequence[float], scales: Sequence[float]
) -> list[float]:
    return [
        (value - mean) / scale for value, mean, scale in zip(values, means, scales, strict=True)
    ]


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return math.fsum(a * b for a, b in zip(left, right, strict=True))


def _polynomial_basis(values: Sequence[float]) -> list[float]:
    clipped = [_clamp(value, -8.0, 8.0) for value in values]
    return [
        *clipped,
        *[value * value for value in clipped],
        *[value**3 for value in clipped],
    ]


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        exponent = math.exp(-min(value, 700.0))
        return 1.0 / (1.0 + exponent)
    exponent = math.exp(max(value, -700.0))
    return exponent / (1.0 + exponent)


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / max(1, len(values))


def _round_vector(values: Sequence[float]) -> list[float]:
    return [round(value, 12) for value in values]


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _rejection(reason: str, issues: Sequence[str]) -> dict[str, Any]:
    return {
        "status": "rejected",
        "reason": reason,
        "issues": list(issues),
        "parameters": None,
        "targetParametersRead": False,
    }


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
