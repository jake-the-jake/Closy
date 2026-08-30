from __future__ import annotations

import math
import random
import time
from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .grammar_v2 import FAMILY_SPECS
from .multiview_corpus_v5 import FEATURE_NAMES

MODEL_VERSION = "closy.e1.multiview_rbf_classifier_regressor.cpu.v3"
MODEL_FAMILY = "nonlinear_multiview_rbf_kernel"
AXES = ("length", "width", "ease")


def train_e1_kernel_v3(
    dataset: dict[str, Any], split: dict[str, Any], *, seed: int = 91_337
) -> dict[str, Any]:
    """Fit a nonlinear kernel model using only frozen multiview observables."""

    start = time.perf_counter_ns()
    train = _program_rows(dataset, split, "train")
    validation = _program_rows(dataset, split, "validation")
    raw = [_feature_vector(row["input"]) for row in train]
    means = [sum(row[index] for row in raw) / len(raw) for index in range(len(FEATURE_NAMES))]
    scales = []
    for index, mean in enumerate(means):
        variance = sum((row[index] - mean) ** 2 for row in raw) / len(raw)
        scales.append(max(math.sqrt(variance), 1.0e-6))
    examples = [
        {
            "programIdentity": row["programIdentity"],
            "family": row["family"],
            "features": _round_vector(_normalize(_feature_vector(row["input"]), means, scales)),
            "continuous": deepcopy(row["target"]["continuous"]),
        }
        for row in train
    ]
    trials = []
    selected: tuple[float, int] | None = None
    selected_score = -math.inf
    for bandwidth, neighbours in ((0.55, 5), (0.8, 9), (1.15, 15)):
        provisional = _model_record(
            examples,
            means,
            scales,
            bandwidth=bandwidth,
            neighbours=neighbours,
            confidence_threshold=0.0,
            seed=seed,
        )
        outcomes = [
            (
                _predict_core(provisional, row["input"]),
                str(row["family"]),
            )
            for row in validation
        ]
        accuracy = sum(prediction["family"] == target for prediction, target in outcomes) / len(
            outcomes
        )
        confidence = sum(float(prediction["confidence"]) for prediction, _ in outcomes) / len(
            outcomes
        )
        score = accuracy + 0.01 * confidence
        trials.append(
            {
                "bandwidth": bandwidth,
                "neighbours": neighbours,
                "validationRawTop1": round(accuracy, 9),
                "validationMeanConfidence": round(confidence, 9),
                "selectionScore": round(score, 9),
            }
        )
        if score > selected_score:
            selected_score = score
            selected = (bandwidth, neighbours)
    if selected is None:
        raise RuntimeError("e1_kernel_no_trial_selected")
    model = _model_record(
        examples,
        means,
        scales,
        bandwidth=selected[0],
        neighbours=selected[1],
        confidence_threshold=0.0,
        seed=seed,
    )
    validation_predictions = [_predict_core(model, row["input"]) for row in validation]
    confidence_threshold = _select_confidence_threshold(validation_predictions)
    model["calibration"] = {
        "kind": "validation_only_selective_confidence_threshold",
        "confidenceThreshold": confidence_threshold,
        "validationProgramCount": len(validation),
        "targetCoverage": 0.65,
        "testDataUsed": False,
    }
    model["optimizer"] = {
        "kind": "bounded_validation_grid_search",
        "trials": trials,
        "selectedBandwidth": selected[0],
        "selectedNeighbours": selected[1],
        "seed": seed,
    }
    model["training"]["wallNanoseconds"] = time.perf_counter_ns() - start
    model["integrity"] = {
        "weightsHash": _weights_hash(model),
        "modelHash": "",
    }
    model["integrity"]["modelHash"] = e1_model_hash(model)
    return model


def predict_e1_kernel_v3(model: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    """Predict from observable features only; no target/program/family argument exists."""

    prediction = _predict_core(model, deepcopy(observation))
    if prediction["ood"]:
        prediction["status"] = "deferred"
        prediction["reason"] = "observable_outside_training_envelope"
    elif float(prediction["confidence"]) < float(model["calibration"]["confidenceThreshold"]):
        prediction["status"] = "deferred"
        prediction["reason"] = "confidence_below_validation_threshold"
    else:
        prediction["status"] = "predicted"
        prediction["reason"] = "nonlinear_multiview_rbf_prediction"
    return prediction


def validate_e1_model_v3(model: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if model.get("modelVersion") != MODEL_VERSION:
        issues.append("e1_model_version_invalid")
    if tuple(model.get("featureNames", [])) != FEATURE_NAMES:
        issues.append("e1_model_feature_contract_invalid")
    if not model.get("examples"):
        issues.append("e1_model_examples_missing")
    if model.get("integrity", {}).get("weightsHash") != _weights_hash(model):
        issues.append("e1_weights_hash_invalid")
    if model.get("integrity", {}).get("modelHash") != e1_model_hash(model):
        issues.append("e1_model_hash_invalid")
    if "target" in model or "allowedStructures" in model:
        issues.append("e1_hidden_target_surface_present")
    return sorted(set(issues))


def e1_model_hash(model: dict[str, Any]) -> str:
    payload = deepcopy(model)
    payload.setdefault("integrity", {})["modelHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def rbf_score_and_gradient(
    point: list[float], center: list[float], bandwidth: float
) -> tuple[float, list[float]]:
    if len(point) != len(center) or bandwidth <= 0.0:
        raise ValueError("rbf_gradient_shape_or_bandwidth_invalid")
    squared = sum((left - right) ** 2 for left, right in zip(point, center, strict=True))
    score = math.exp(-squared / (2.0 * bandwidth * bandwidth))
    gradient = [
        -score * (left - right) / (bandwidth * bandwidth)
        for left, right in zip(point, center, strict=True)
    ]
    return score, gradient


def aggregate_program_predictions_v3(
    model: dict[str, Any], observations: list[dict[str, Any]]
) -> dict[str, Any]:
    if not observations:
        raise ValueError("e1_program_observations_empty")
    predictions = [predict_e1_kernel_v3(model, observation) for observation in observations]
    families = sorted(FAMILY_SPECS)
    probabilities = {
        family: sum(float(item["probabilities"][family]) for item in predictions) / len(predictions)
        for family in families
    }
    family = max(families, key=lambda name: (probabilities[name], name))
    continuous = {
        axis: {
            field: sum(float(item["continuous"][axis][field]) for item in predictions)
            / len(predictions)
            for field in ("normalized", "value")
        }
        for axis in AXES
    }
    confidence = probabilities[family]
    status = (
        "deferred"
        if all(item["status"] == "deferred" for item in predictions)
        or confidence < float(model["calibration"]["confidenceThreshold"])
        else "predicted"
    )
    return {
        "status": status,
        "family": family,
        "confidence": round(confidence, 9),
        "probabilities": {key: round(value, 9) for key, value in probabilities.items()},
        "top3": sorted(families, key=lambda name: (-probabilities[name], name))[:3],
        "continuous": {
            axis: {key: round(value, 9) for key, value in values.items()}
            for axis, values in continuous.items()
        },
        "capturePredictionCount": len(predictions),
        "allCapturesDeferred": all(item["status"] == "deferred" for item in predictions),
    }


def _predict_core(model: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    row = _normalize(
        _feature_vector(observation),
        list(map(float, model["normalization"]["means"])),
        list(map(float, model["normalization"]["scales"])),
    )
    envelope = model["oodEnvelope"]
    ood = any(
        value < float(envelope["minimums"][index]) - float(envelope["margin"])
        or value > float(envelope["maximums"][index]) + float(envelope["margin"])
        for index, value in enumerate(row)
    )
    distances = sorted(
        (
            sum(
                (value - float(other)) ** 2
                for value, other in zip(row, example["features"], strict=True)
            ),
            index,
        )
        for index, example in enumerate(model["examples"])
    )
    neighbours = distances[: int(model["kernel"]["neighbours"])]
    bandwidth = float(model["kernel"]["bandwidth"])
    weighted = []
    for distance, index in neighbours:
        score = math.exp(-distance / (2.0 * bandwidth * bandwidth))
        weighted.append((max(score, 1.0e-12), model["examples"][index]))
    family_scores = {family: 0.0 for family in FAMILY_SPECS}
    for score, example in weighted:
        family_scores[str(example["family"])] += score
    total = max(sum(family_scores.values()), 1.0e-12)
    probabilities = {family: score / total for family, score in family_scores.items()}
    family = max(probabilities, key=lambda name: (probabilities[name], name))
    family_rows = [(score, example) for score, example in weighted if example["family"] == family]
    if not family_rows:
        family_rows = weighted
    denominator = max(sum(score for score, _ in family_rows), 1.0e-12)
    continuous = {
        axis: {
            field: sum(
                score * float(example["continuous"][axis][field]) for score, example in family_rows
            )
            / denominator
            for field in ("normalized", "value")
        }
        for axis in AXES
    }
    return {
        "family": family,
        "confidence": round(probabilities[family], 9),
        "probabilities": {key: round(value, 9) for key, value in sorted(probabilities.items())},
        "continuous": {
            axis: {key: round(value, 9) for key, value in values.items()}
            for axis, values in continuous.items()
        },
        "ood": ood,
    }


def _model_record(
    examples: list[dict[str, Any]],
    means: list[float],
    scales: list[float],
    *,
    bandwidth: float,
    neighbours: int,
    confidence_threshold: float,
    seed: int,
) -> dict[str, Any]:
    columns = list(zip(*(example["features"] for example in examples), strict=True))
    return {
        "schemaVersion": 1,
        "modelVersion": MODEL_VERSION,
        "modelFamily": MODEL_FAMILY,
        "featureNames": list(FEATURE_NAMES),
        "viewRolePooling": "none_role_keyed_features_remain_distinct",
        "normalization": {
            "means": _round_vector(means),
            "scales": _round_vector(scales),
            "fitSplit": "train_only",
        },
        "kernel": {"kind": "gaussian_rbf", "bandwidth": bandwidth, "neighbours": neighbours},
        "examples": examples,
        "oodEnvelope": {
            "minimums": _round_vector([min(column) for column in columns]),
            "maximums": _round_vector([max(column) for column in columns]),
            "margin": 4.0,
            "action": "defer",
        },
        "calibration": {"confidenceThreshold": confidence_threshold},
        "training": {
            "seed": seed,
            "cpuOnly": True,
            "threadCount": 1,
            "trainingProgramCount": len(examples),
            "testDataUsed": False,
            "externalCheckpoint": None,
            "networkDownload": False,
        },
    }


def _program_rows(
    dataset: dict[str, Any], split: dict[str, Any], split_name: str
) -> list[dict[str, Any]]:
    identities = set(map(str, split["groups"][split_name]))
    captures: dict[str, list[dict[str, float]]] = {}
    for capture in dataset["captures"]:
        identity = str(capture["programIdentity"])
        if identity in identities:
            captures.setdefault(identity, []).append(capture["input"])
    programs = {str(item["programIdentity"]): item for item in dataset["programs"]}
    rows = []
    for identity in sorted(identities):
        observations = captures[identity]
        rows.append(
            {
                "programIdentity": identity,
                "family": programs[identity]["family"],
                "input": {
                    name: sum(float(item[name]) for item in observations) / len(observations)
                    for name in FEATURE_NAMES
                },
                "target": programs[identity]["target"],
            }
        )
    return rows


def _select_confidence_threshold(predictions: list[dict[str, Any]]) -> float:
    values = sorted(float(item["confidence"]) for item in predictions)
    target_accepted = max(1, math.ceil(len(values) * 0.65))
    threshold = values[max(0, len(values) - target_accepted)] - 1.0e-9
    return round(max(0.0, threshold), 9)


def _feature_vector(observation: dict[str, Any]) -> list[float]:
    if tuple(observation) != FEATURE_NAMES:
        raise ValueError("e1_observable_contract_invalid")
    values = [float(observation[name]) for name in FEATURE_NAMES]
    if any(not math.isfinite(value) for value in values):
        raise ValueError("e1_observable_nonfinite")
    return values


def _normalize(values: list[float], means: list[float], scales: list[float]) -> list[float]:
    return [
        (value - mean) / max(scale, 1.0e-9)
        for value, mean, scale in zip(values, means, scales, strict=True)
    ]


def _round_vector(values: list[float] | tuple[float, ...]) -> list[float]:
    return [round(float(value), 12) for value in values]


def _weights_hash(model: dict[str, Any]) -> str:
    payload = {
        "normalization": model.get("normalization"),
        "kernel": model.get("kernel"),
        "examples": model.get("examples"),
        "oodEnvelope": model.get("oodEnvelope"),
        "calibration": model.get("calibration"),
    }
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def deterministic_label_permutations(count: int, *, seeds: tuple[int, ...]) -> list[list[int]]:
    result = []
    for seed in seeds:
        values = list(range(count))
        random.Random(seed).shuffle(values)
        result.append(values)
    return result
