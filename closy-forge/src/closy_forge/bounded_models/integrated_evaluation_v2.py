from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from .contracts import FAILURE_TARGETS
from .dataset import build_phase14_dataset, rows_for_split
from .evaluation import evaluate_phase14_model
from .model import predict_candidate, train_phase14_model

INTEGRATED_EVALUATION_VERSION = "closy.phase14.integrated_advisory_evaluation.synthetic_d0.v2"


def build_integrated_phase14_evaluation(
    *, e1: dict[str, Any], e2: dict[str, Any], source_context: dict[str, Any]
) -> dict[str, Any]:
    dataset = build_phase14_dataset()
    model = train_phase14_model(dataset)
    evaluation = evaluate_phase14_model(dataset, model)
    rows = rows_for_split(dataset, "test")
    intervals = _bootstrap_intervals(rows, model)
    ablations = {
        "scenarioFeaturesHeldAtTrainingMean": _ablation(dataset, model, "scenario"),
        "materialFeaturesHeldAtTrainingMean": _ablation(dataset, model, "material"),
    }
    return {
        "schemaVersion": 1,
        "evaluationVersion": INTEGRATED_EVALUATION_VERSION,
        "model": model,
        "dataset": {
            "datasetVersion": dataset["datasetVersion"],
            "rowCount": len(dataset["rows"]),
            "testRowCount": len(rows),
            "splitPolicy": dataset["splitManifest"]["splitPolicy"],
            "preOutcomeFeaturesSeparated": True,
            "phase9OutcomesUsedAsFeatures": False,
            "currentExecutablePathSources": source_context,
        },
        "evaluation": evaluation,
        "confidenceIntervals": intervals,
        "ablations": ablations,
        "phase9DecisionContext": {
            "e1": {
                "status": e1["E1"]["status"],
                "acceptedCount": e1["unassisted"]["acceptedCount"],
                "learnedSuccessCount": e1["unassisted"]["learnedSuccessCount"],
                "fallbackCountedAsLearned": False,
            },
            "e2": {
                "status": e2["acceptance"]["status"],
                "acceptedCount": e2["metrics"]["acceptedCount"],
                "macroStructureTokenF1": e2["metrics"]["macroStructureTokenF1"],
            },
            "use": "advisory_context_only_not_training_features",
        },
        "authority": {
            "deterministicValidatorsFinal": True,
            "modelMay": [
                "rank_material_presets",
                "predict_failure_risk",
                "recommend_defer_or_fallback",
                "prioritise_correction",
            ],
            "modelMayNot": [
                "override_topology_failure",
                "override_collision_failure",
                "certify_unsupported_data",
                "promote_failed_package_to_canonical_truth",
                "hide_uncertainty",
            ],
        },
        "largeModelBoundary": {
            "execution": "not_run",
            "reason": "no_authorised_model_checkpoint_licence_hardware_privacy_or_deployment_scope",
            "downloadAttempted": False,
            "fineTuneAttempted": False,
        },
        "claims": {
            "realFabricInference": False,
            "providerSuperiority": False,
            "privateUserOutcomes": False,
            "broadVisualGeometryFineTuning": False,
            "productionTraining": False,
            "commercialDeployment": False,
            "globalPhase14Complete": False,
        },
    }


def _bootstrap_intervals(rows: list[dict[str, Any]], model: dict[str, Any]) -> dict[str, Any]:
    predictions = [(row, predict_candidate(model, row["featureSnapshot"])) for row in rows]
    rng = random.Random(142_021)
    macro_f1: list[float] = []
    utility: list[float] = []
    for _ in range(2_000):
        sample = [predictions[rng.randrange(len(predictions))] for _ in predictions]
        macro_f1.append(_failure_macro_f1(sample))
        utility.append(_decision_utility(sample))
    scenario_groups: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for row, prediction in predictions:
        scenario_groups.setdefault(str(row["scenarioId"]), []).append((row, prediction))
    scenarios = sorted(scenario_groups)
    material_accuracy: list[float] = []
    material_regret: list[float] = []
    for _ in range(2_000):
        sampled = [scenario_groups[scenarios[rng.randrange(len(scenarios))]] for _ in scenarios]
        outcomes = [_material_scenario(group) for group in sampled]
        material_accuracy.append(sum(item[0] for item in outcomes) / len(outcomes))
        material_regret.append(sum(item[1] for item in outcomes) / len(outcomes))
    return {
        "method": "deterministic_nonparametric_bootstrap_2000_resamples",
        "materialTopOne95": _interval(material_accuracy),
        "materialSelectionRegret95": _interval(material_regret),
        "failureMacroF195": _interval(macro_f1),
        "decisionUtility95": _interval(utility),
    }


def _ablation(dataset: dict[str, Any], model: dict[str, Any], mode: str) -> dict[str, Any]:
    rows = rows_for_split(dataset, "test")
    means = {
        name: float(value)
        for name, value in zip(model["featureNames"], model["normalization"]["means"], strict=True)
    }
    material_names = {name for name in means if name.startswith("material")}
    predictions = []
    for source in rows:
        row = deepcopy(source)
        features = row["featureSnapshot"]
        for name in means:
            if (mode == "material" and name in material_names) or (
                mode == "scenario" and name not in material_names
            ):
                features[name] = means[name]
        predictions.append((row, predict_candidate(model, features)))
    accepted = [item for item in predictions if item[1]["status"] == "accepted"]
    return {
        "actualExecution": True,
        "mode": mode,
        "acceptedCount": len(accepted),
        "failureMacroF1": _failure_macro_f1(accepted) if accepted else None,
        "decisionUtility": _decision_utility(accepted) if accepted else None,
    }


def _failure_macro_f1(items: list[tuple[dict[str, Any], dict[str, Any]]]) -> float:
    values = []
    for target in FAILURE_TARGETS:
        tp = fp = fn = 0
        for row, prediction in items:
            expected = bool(row["targets"]["failures"][target])
            predicted = float(prediction["failureProbabilities"][target]) >= 0.5
            tp += int(expected and predicted)
            fp += int(not expected and predicted)
            fn += int(expected and not predicted)
        values.append(2.0 * tp / max(2 * tp + fp + fn, 1))
    return sum(values) / len(values)


def _decision_utility(items: list[tuple[dict[str, Any], dict[str, Any]]]) -> float:
    utility = 0.0
    for row, prediction in items:
        for target in FAILURE_TARGETS:
            expected = bool(row["targets"]["failures"][target])
            predicted = float(prediction["failureProbabilities"][target]) >= 0.5
            utility += (
                2.0
                if expected and predicted
                else 0.2
                if not expected and not predicted
                else -1.0
                if predicted
                else -4.0
            )
    return utility / max(len(items) * len(FAILURE_TARGETS), 1)


def _material_scenario(
    items: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[float, float]:
    actual = max(items, key=lambda item: float(item[0]["targets"]["materialQualityScore"]))
    predicted = max(items, key=lambda item: float(item[1]["materialQualityScore"]))
    best = float(actual[0]["targets"]["materialQualityScore"])
    selected = float(predicted[0]["targets"]["materialQualityScore"])
    return float(actual[0]["presetId"] == predicted[0]["presetId"]), best - selected


def _interval(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "lower": round(ordered[49], 12),
        "median": round(ordered[999], 12),
        "upper": round(ordered[1949], 12),
    }
