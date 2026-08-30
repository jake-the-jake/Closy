from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from .contracts import FAILURE_TARGETS, FEATURE_NAMES, canonical_hash, rounded
from .dataset import rows_for_split, validate_split_manifest
from .model import predict_candidate, validate_model


def evaluate_phase14_model(dataset: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    rows = rows_for_split(dataset, "test")
    predictions = [(row, predict_candidate(model, row["featureSnapshot"])) for row in rows]
    accepted = [
        (row, prediction) for row, prediction in predictions if not prediction["fallbackRequired"]
    ]
    if not accepted:
        raise RuntimeError("all_in_distribution_test_predictions_rejected")

    material_mae = sum(
        abs(
            float(prediction["materialQualityScore"])
            - float(row["targets"]["materialQualityScore"])
        )
        for row, prediction in accepted
    ) / len(accepted)
    ranking = _ranking_metrics(accepted)
    failures = _failure_metrics(accepted)
    baseline = _baseline_metrics(rows)
    ood = _ood_evaluation(model, rows)
    leakage = _leakage_audit(dataset)
    evaluation: dict[str, Any] = {
        "schemaVersion": 1,
        "evaluationVersion": "closy.phase14.bounded_model_evaluation.d0.v1",
        "testRowCount": len(rows),
        "acceptedTestRowCount": len(accepted),
        "material": {"meanAbsoluteError": rounded(material_mae), **ranking},
        "failureAndQuality": failures,
        "deterministicBaselines": baseline,
        "calibration": {
            "method": "fixed_sigmoid_no_post_test_fit",
            "brierScore": failures["macroBrierScore"],
            "expectedCalibrationError": failures["macroExpectedCalibrationError"],
        },
        "ood": ood,
        "decisionUtility": {
            "learnedWarningUtility": failures["decisionUtility"],
            "deterministicRuleUtility": baseline["failureRuleDecisionUtility"],
            "utilityDelta": rounded(
                float(failures["decisionUtility"]) - float(baseline["failureRuleDecisionUtility"])
            ),
        },
        "leakageAudit": leakage,
        "modelIssues": validate_model(model),
        "datasetIssues": validate_split_manifest(dataset),
        "truth": {
            "deterministicValidatorsRetainFinalAuthority": True,
            "productionSolverOutcomeClaim": False,
            "realFabricDataUsed": False,
            "privateUserDataUsed": False,
            "broadVisualGeometryFineTuningRun": False,
        },
        "integrity": {"evaluationHash": ""},
    }
    evaluation["integrity"]["evaluationHash"] = evaluation_hash(evaluation)
    return evaluation


def evaluation_hash(evaluation: dict[str, Any]) -> str:
    payload = deepcopy(evaluation)
    payload.setdefault("integrity", {})["evaluationHash"] = ""
    return canonical_hash(payload)


def _ranking_metrics(accepted: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    scenarios: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for row, prediction in accepted:
        scenarios[str(row["scenarioId"])].append((row, prediction))
    top_one = 0
    regrets: list[float] = []
    baseline_regrets: list[float] = []
    for candidates in scenarios.values():
        actual_best = max(
            candidates, key=lambda item: float(item[0]["targets"]["materialQualityScore"])
        )
        predicted_best = max(candidates, key=lambda item: float(item[1]["materialQualityScore"]))
        baseline = next(
            item for item in candidates if item[0]["presetId"] == "material.cotton_jersey_d0_v1"
        )
        top_one += int(predicted_best[0]["presetId"] == actual_best[0]["presetId"])
        best_score = float(actual_best[0]["targets"]["materialQualityScore"])
        regrets.append(best_score - float(predicted_best[0]["targets"]["materialQualityScore"]))
        baseline_regrets.append(best_score - float(baseline[0]["targets"]["materialQualityScore"]))
    return {
        "scenarioCount": len(scenarios),
        "topOneCorrect": top_one,
        "topOneAccuracy": rounded(top_one / len(scenarios)),
        "meanSelectionRegret": rounded(sum(regrets) / len(regrets)),
        "deterministicPresetMeanRegret": rounded(sum(baseline_regrets) / len(baseline_regrets)),
    }


def _failure_metrics(accepted: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    per_target: dict[str, dict[str, Any]] = {}
    briers: list[float] = []
    eces: list[float] = []
    total_utility = 0.0
    for name in FAILURE_TARGETS:
        pairs = [
            (
                float(prediction["failureProbabilities"][name]),
                bool(row["targets"]["failures"][name]),
            )
            for row, prediction in accepted
        ]
        tp = sum(probability >= 0.5 and label for probability, label in pairs)
        fp = sum(probability >= 0.5 and not label for probability, label in pairs)
        fn = sum(probability < 0.5 and label for probability, label in pairs)
        tn = sum(probability < 0.5 and not label for probability, label in pairs)
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        f1 = 2.0 * precision * recall / max(1e-12, precision + recall)
        brier = sum((probability - float(label)) ** 2 for probability, label in pairs) / len(pairs)
        ece = _ece(pairs)
        utility = tp * 2.0 + tn * 0.2 - fp * 1.0 - fn * 4.0
        total_utility += utility
        briers.append(brier)
        eces.append(ece)
        per_target[name] = {
            "truePositive": tp,
            "falsePositive": fp,
            "falseNegative": fn,
            "trueNegative": tn,
            "f1": rounded(f1),
            "brierScore": rounded(brier),
            "expectedCalibrationError": rounded(ece),
        }
    return {
        "perTarget": per_target,
        "macroF1": rounded(
            sum(float(item["f1"]) for item in per_target.values()) / len(per_target)
        ),
        "macroBrierScore": rounded(sum(briers) / len(briers)),
        "macroExpectedCalibrationError": rounded(sum(eces) / len(eces)),
        "decisionUtility": rounded(total_utility / (len(accepted) * len(FAILURE_TARGETS))),
    }


def _baseline_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    utility = 0.0
    for row in rows:
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
        for name in FAILURE_TARGETS:
            predicted = rules[name]
            label = bool(row["targets"]["failures"][name])
            utility += (
                2.0
                if predicted and label
                else 0.2
                if not predicted and not label
                else -1.0
                if predicted
                else -4.0
            )
    return {
        "materialPresetId": "material.cotton_jersey_d0_v1",
        "failureRuleKind": "frozen_pre_solve_threshold_rules",
        "failureRuleDecisionUtility": rounded(utility / (len(rows) * len(FAILURE_TARGETS))),
    }


def _ood_evaluation(model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    id_rejected = sum(
        predict_candidate(model, row["featureSnapshot"])["fallbackRequired"] for row in rows
    )
    challenges: list[dict[str, float]] = []
    base = dict(rows[0]["featureSnapshot"])
    for index, name in enumerate(FEATURE_NAMES):
        low = dict(base)
        high = dict(base)
        low[name] = float(model["normalization"]["means"][index]) - 12.0 * float(
            model["normalization"]["scales"][index]
        )
        high[name] = float(model["normalization"]["means"][index]) + 12.0 * float(
            model["normalization"]["scales"][index]
        )
        challenges.extend((low, high))
    rejected = sum(
        predict_candidate(model, challenge)["fallbackRequired"] for challenge in challenges
    )
    return {
        "challengeCount": len(challenges),
        "challengeRejected": rejected,
        "challengeRejectionRate": rounded(rejected / len(challenges)),
        "inDistributionCount": len(rows),
        "inDistributionRejected": id_rejected,
        "inDistributionAcceptanceRate": rounded((len(rows) - id_rejected) / len(rows)),
    }


def _leakage_audit(dataset: dict[str, Any]) -> dict[str, Any]:
    intersections = dataset["splitManifest"]["intersections"]
    forbidden_fixture = dict(dataset["rows"][0]["featureSnapshot"])
    forbidden_fixture["finalValidatorOutcome"] = 1.0
    from .contracts import validate_feature_snapshot

    deliberate_issues = validate_feature_snapshot(forbidden_fixture)
    return {
        "featureFreezeBeforeSolver": True,
        "featureSnapshotHashesVerified": all(
            canonical_hash(row["featureSnapshot"]) == row["featureSnapshotHash"]
            for row in dataset["rows"]
        ),
        "sourceGroupIntersection": intersections["sourceGroups"],
        "programGroupIntersection": intersections["programGroups"],
        "avatarGroupIntersection": intersections["avatarGroups"],
        "trainOnlyPreprocessing": True,
        "deliberatePostOutcomeFeatureRejected": any(
            issue.startswith("post_outcome_feature_forbidden") for issue in deliberate_issues
        ),
        "forbiddenFixtureIssues": deliberate_issues,
        "accepted": not any(intersections.values()) and bool(deliberate_issues),
    }


def _ece(pairs: list[tuple[float, bool]]) -> float:
    total = len(pairs)
    error = 0.0
    for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
        upper = lower + 0.2
        bucket = [
            item for item in pairs if lower <= item[0] < upper or upper == 1.0 and item[0] == 1.0
        ]
        if not bucket:
            continue
        confidence = sum(item[0] for item in bucket) / len(bucket)
        accuracy = sum(float(item[1]) for item in bucket) / len(bucket)
        error += len(bucket) / total * abs(confidence - accuracy)
    return error
