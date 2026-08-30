from __future__ import annotations

import math
import random
from collections import defaultdict
from copy import deepcopy
from typing import Any

from .contracts import FAILURE_TARGETS
from .dataset import build_phase14_dataset, rows_for_split
from .evaluation import evaluate_phase14_model
from .model import predict_candidate, train_phase14_model

INTEGRATED_EVALUATION_VERSION = "closy.phase14.integrated_advisory_evaluation.synthetic_d0.v3"


def build_integrated_phase14_evaluation_v3(
    *,
    e1: dict[str, Any],
    e2: dict[str, Any],
    source_context: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    dataset = build_phase14_dataset()
    model = train_phase14_model(dataset)
    evaluation = evaluate_phase14_model(dataset, model)
    rows = rows_for_split(dataset, "test")
    predictions = [(row, predict_candidate(model, row["featureSnapshot"])) for row in rows]
    accepted = [item for item in predictions if item[1]["status"] == "predicted"]
    ranking = _normalized_ranking(accepted)
    evaluation["material"].update(ranking)
    intervals = _cluster_bootstrap(predictions)
    ablations = {
        "scenarioFeaturesHeldAtTrainingMean": _ablation(dataset, model, "scenario"),
        "materialFeaturesHeldAtTrainingMean": _ablation(dataset, model, "material"),
    }
    gate = thresholds["phase14"]
    per_target = evaluation["failureAndQuality"]["perTarget"]
    checks = {
        "materialTop1": float(evaluation["material"]["topOneAccuracy"])
        >= float(gate["minimumMaterialTop1"]),
        "meanNormalizedSelectionRegret": ranking["meanNormalizedSelectionRegret"]
        <= float(gate["maximumMeanNormalizedSelectionRegret"]),
        "p95NormalizedSelectionRegret": ranking["p95NormalizedSelectionRegret"]
        <= float(gate["maximumP95NormalizedSelectionRegret"]),
        "failureMacroF1": float(evaluation["failureAndQuality"]["macroF1"])
        >= float(gate["minimumFailureMacroF1"]),
        "everyFailureTargetF1": all(
            float(item["f1"]) >= float(gate["minimumEveryFailureTargetF1"])
            for item in per_target.values()
        ),
        "brier": float(evaluation["calibration"]["brierScore"]) <= float(gate["maximumBrier"]),
        "ece": float(evaluation["calibration"]["expectedCalibrationError"])
        <= float(gate["maximumEce"]),
        "oodCorrectAction": float(evaluation["ood"]["challengeRejectionRate"])
        >= float(gate["minimumOodCorrectAction"]),
        "clusterBootstrapUtility": intervals["utilityDelta95"]["lower"]
        > float(gate["minimumClusterBootstrapUtilityLower95"]),
        "ablationsNonNull": all(
            item["predictedCount"] > 0
            and item["failureMacroF1"] is not None
            and item["decisionUtility"] is not None
            for item in ablations.values()
        ),
    }
    return {
        "schemaVersion": 1,
        "evaluationVersion": INTEGRATED_EVALUATION_VERSION,
        "profileId": gate["profileId"],
        "model": model,
        "dataset": {
            "datasetVersion": dataset["datasetVersion"],
            "rowCount": len(dataset["rows"]),
            "testRowCount": len(rows),
            "scenarioClusterCount": len({str(row["scenarioId"]) for row in rows}),
            "splitPolicy": dataset["splitManifest"]["splitPolicy"],
            "preOutcomeFeaturesSeparated": True,
            "phase9OutcomesUsedAsFeatures": False,
            "currentExecutablePathSources": source_context,
            "solverBackedReplacementCorpus": {
                "status": "not_run",
                "reason": "canonical_solver_topology_not_eligible_before_closy_c_freeze",
                "scalarProxyRowsManufactured": False,
            },
        },
        "evaluation": evaluation,
        "confidenceIntervals": intervals,
        "ablations": ablations,
        "checks": checks,
        "acceptance": {
            "status": "pass" if all(checks.values()) else "partial",
            "passedCount": sum(checks.values()),
            "checkCount": len(checks),
            "authority": "advisory_only",
            "globalPhase14Complete": False,
        },
        "phase9DecisionContext": {
            "e1": _phase9_summary(e1, kind="e1"),
            "e2": _phase9_summary(e2, kind="e2"),
            "use": "advisory_context_only_not_training_features",
        },
        "evaluationCorrections": {
            "ablationStatusFilter": "predicted",
            "formerAcceptedFilterBugPresent": False,
            "bootstrapUnit": "scenario_cluster_including_correlated_material_rows",
            "materialTopOneSeparatedFromRegret": True,
            "normalizedRegretReported": ["mean", "p95", "worst"],
            "perTargetFailureMetricsRetained": list(FAILURE_TARGETS),
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
            "reason": "no_authorised_checkpoint_licence_hardware_privacy_or_deployment_scope",
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


def _normalized_ranking(
    accepted: list[tuple[dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    scenarios = _scenario_groups(accepted)
    regrets = []
    records = []
    for scenario, candidates in sorted(scenarios.items()):
        actual = max(candidates, key=lambda item: float(item[0]["targets"]["materialQualityScore"]))
        predicted = max(candidates, key=lambda item: float(item[1]["materialQualityScore"]))
        scores = [float(item[0]["targets"]["materialQualityScore"]) for item in candidates]
        best = max(scores)
        worst = min(scores)
        selected = float(predicted[0]["targets"]["materialQualityScore"])
        normalized = (best - selected) / max(best - worst, 1.0e-9)
        regrets.append(normalized)
        records.append(
            {
                "scenarioId": scenario,
                "actualPresetId": actual[0]["presetId"],
                "selectedPresetId": predicted[0]["presetId"],
                "topOneCorrect": actual[0]["presetId"] == predicted[0]["presetId"],
                "normalizedRegret": round(normalized, 12),
                "scoreRange": round(best - worst, 12),
            }
        )
    return {
        "normalizedSelectionRegretPolicy": "(best-selected)/max(best-worst,1e-9)_per_scenario",
        "meanNormalizedSelectionRegret": _rounded(_mean(regrets)),
        "p95NormalizedSelectionRegret": _rounded(_percentile(regrets, 0.95)),
        "worstNormalizedSelectionRegret": _rounded(max(regrets, default=0.0)),
        "perScenarioSelection": records,
    }


def _cluster_bootstrap(
    predictions: list[tuple[dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    groups = _scenario_groups(predictions)
    scenarios = sorted(groups)
    rng = random.Random(142_031)
    macro_f1 = []
    learned_utility = []
    utility_delta = []
    top_one = []
    normalized_regret = []
    for _ in range(2_000):
        sampled_groups = [groups[scenarios[rng.randrange(len(scenarios))]] for _ in scenarios]
        sample = [item for group in sampled_groups for item in group]
        predicted_sample = [item for item in sample if item[1]["status"] == "predicted"]
        macro_f1.append(_failure_macro_f1(predicted_sample))
        learned = _decision_utility(predicted_sample)
        baseline = _deterministic_rule_utility(predicted_sample)
        learned_utility.append(learned)
        utility_delta.append(learned - baseline)
        material = [_material_scenario(group) for group in sampled_groups]
        top_one.append(_mean([item[0] for item in material]))
        normalized_regret.append(_mean([item[1] for item in material]))
    return {
        "method": "deterministic_nonparametric_scenario_cluster_bootstrap_2000_resamples",
        "clusterKey": "scenarioId",
        "correlatedMaterialRowsKeptTogether": True,
        "materialTopOne95": _interval(top_one),
        "normalizedSelectionRegret95": _interval(normalized_regret),
        "failureMacroF195": _interval(macro_f1),
        "learnedDecisionUtility95": _interval(learned_utility),
        "utilityDelta95": _interval(utility_delta),
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
    predicted = [item for item in predictions if item[1]["status"] == "predicted"]
    return {
        "actualExecution": True,
        "mode": mode,
        "predictionStatusFilter": "predicted",
        "predictedCount": len(predicted),
        "failureMacroF1": _rounded(_failure_macro_f1(predicted)) if predicted else None,
        "decisionUtility": _rounded(_decision_utility(predicted)) if predicted else None,
    }


def _phase9_summary(value: dict[str, Any], *, kind: str) -> dict[str, Any]:
    acceptance = value.get("acceptance", {})
    if kind == "e1":
        return {
            "status": acceptance.get("status", "unknown"),
            "promotionClass": acceptance.get("promotionClass", "unknown"),
            "learnedRouteDefault": acceptance.get("learnedRouteDefault", False),
        }
    return {
        "status": acceptance.get("status", "unknown"),
        "learnedRouteDefault": acceptance.get("learnedRouteDefault", False),
        "truePerTokenMacroF1": value.get("metrics", {}).get("truePerTokenMacroF1"),
    }


def _scenario_groups(
    items: list[tuple[dict[str, Any], dict[str, Any]]],
) -> dict[str, list[tuple[dict[str, Any], dict[str, Any]]]]:
    result: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for row, prediction in items:
        result[str(row["scenarioId"])].append((row, prediction))
    return result


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
    return _mean(values)


def _decision_utility(items: list[tuple[dict[str, Any], dict[str, Any]]]) -> float:
    utility = 0.0
    for row, prediction in items:
        for target in FAILURE_TARGETS:
            expected = bool(row["targets"]["failures"][target])
            predicted = float(prediction["failureProbabilities"][target]) >= 0.5
            utility += _utility(expected, predicted)
    return utility / max(len(items) * len(FAILURE_TARGETS), 1)


def _deterministic_rule_utility(
    items: list[tuple[dict[str, Any], dict[str, Any]]],
) -> float:
    utility = 0.0
    for row, _prediction in items:
        features = row["featureSnapshot"]
        rules = {
            "settleFailure": features["motionAmplitude"] > 0.78
            and features["programPanelComplexity"] > 0.66,
            "collisionNonconvergence": features["initialPenetrationMeters"] > 0.0065,
            "openingCollapse": features["programOpeningRatio"] < 0.7
            and features["motionAmplitude"] > 0.55,
            "excessiveStrain": features["motionAmplitude"] > 0.82,
            "seamContinuityRisk": features["programSeamDensity"] > 0.77,
            "lowCaptureQuality": features["captureQuality"] < 0.62,
        }
        for target in FAILURE_TARGETS:
            utility += _utility(bool(row["targets"]["failures"][target]), bool(rules[target]))
    return utility / max(len(items) * len(FAILURE_TARGETS), 1)


def _utility(expected: bool, predicted: bool) -> float:
    return (
        2.0
        if expected and predicted
        else 0.2
        if not expected and not predicted
        else -1.0
        if predicted
        else -4.0
    )


def _material_scenario(
    items: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[float, float]:
    actual = max(items, key=lambda item: float(item[0]["targets"]["materialQualityScore"]))
    predicted = max(items, key=lambda item: float(item[1]["materialQualityScore"]))
    scores = [float(item[0]["targets"]["materialQualityScore"]) for item in items]
    best = max(scores)
    selected = float(predicted[0]["targets"]["materialQualityScore"])
    normalized = (best - selected) / max(best - min(scores), 1.0e-9)
    return float(actual[0]["presetId"] == predicted[0]["presetId"]), normalized


def _interval(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "lower": _rounded(ordered[49]),
        "median": _rounded(ordered[999]),
        "upper": _rounded(ordered[1_949]),
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def _mean(values: list[float]) -> float:
    return sum(values) / max(len(values), 1)


def _rounded(value: float) -> float:
    return round(value, 12)
