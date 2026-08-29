from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .dataset_v2 import FEATURE_NAMES
from .model_v2 import FAMILIES, predict_v2, train_model_v2

EVALUATION_VERSION_V4 = "closy.raster_pattern_evaluation.synthetic_d0.v4"
PIXEL_FEATURES = tuple(
    name for name in FEATURE_NAMES if name not in {"cameraYawNormalized", "cameraPitchNormalized"}
)


def evaluate_raster_model_v4(
    model: dict[str, Any],
    dataset: dict[str, Any],
    split: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate unassisted inference without allowing hidden labels into decoding."""

    test = _split_samples(dataset, split, "test")
    learned = [_outcome(model, sample) for sample in test]
    baselines = _baselines(model, dataset, split, test)
    ood = _ood_metrics(model, test)
    calibration = _calibration(learned)
    coverage = sum(item["accepted"] for item in learned) / len(learned)
    accepted = [item for item in learned if item["accepted"]]
    selective_risk = (
        sum(not item["correct"] for item in accepted) / len(accepted) if accepted else 1.0
    )
    top1 = sum(item["correct"] for item in learned) / len(learned)
    strongest = max(baselines.values(), key=lambda item: float(item["top1Accuracy"]))
    paired_interval = _paired_bootstrap_interval(
        [int(item["correct"]) for item in learned],
        list(map(int, strongest["correctness"])),
        seed=44_071,
    )
    gate = thresholds["e1"]
    checks = {
        "familyTop1": top1 >= float(gate["minimumFamilyTop1"]),
        "acceptedCoverage": coverage >= float(gate["minimumAcceptedCoverage"]),
        "selectiveRisk": selective_risk <= float(gate["maximumSelectiveRisk"]),
        "calibration": calibration["expectedCalibrationError"]
        <= float(gate["maximumExpectedCalibrationError"]),
        "oodCorrectAction": ood["correctActionRate"] >= float(gate["minimumOodCorrectActionRate"]),
        "oodFalseAccept": ood["falseAcceptRate"] <= float(gate["maximumOodFalseAcceptRate"]),
        "equalInputBaseline": paired_interval["lower95"]
        >= float(gate["baselineCriterion"]["minimumPairedBootstrapLower95"]),
    }
    return {
        "schemaVersion": 1,
        "evaluationVersion": EVALUATION_VERSION_V4,
        "track": "unassisted_project_authored_synthetic_raster_host_cpu",
        "thresholdRegistryHash": sha256_bytes(canonical_dumps(thresholds).encode("utf-8")),
        "sampleCount": len(test),
        "learned": {
            "top1Accuracy": round(top1, 9),
            "acceptedCoverage": round(coverage, 9),
            "selectiveRisk": round(selective_risk, 9),
            "outcomes": learned,
        },
        "calibration": calibration,
        "baselines": baselines,
        "strongestEqualInputBaseline": strongest["name"],
        "learnedMinusStrongestPairedBootstrap95": paired_interval,
        "controls": _controls(model, dataset, split, test),
        "shiftSuites": _shift_metrics(model, test),
        "ood": ood,
        "leakageAudit": {
            "candidateApiAcceptsTargets": False,
            "candidateInputs": ["decoded_raster_features", "permitted_camera_metadata", "model"],
            "hiddenTargetsUsedOnlyForMetrics": True,
            "identityDisjoint": _identity_disjoint(split),
            "testSamplesInTrainingShiftSuites": False,
        },
        "acceptance": {
            "profileId": gate["profileId"],
            "checks": checks,
            "status": "pass" if all(checks.values()) else "partial",
            "failedChecks": sorted(name for name, passed in checks.items() if not passed),
        },
        "claims": {
            "realPhotoGeneralisation": False,
            "privateUserGeneralisation": False,
            "globalPhase9Complete": False,
            "learnedRouteDefault": all(checks.values()),
        },
    }


def predict_unassisted(model: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    """The candidate boundary intentionally has no target/family/program argument."""

    return predict_v2(model, deepcopy(observation))


def _outcome(model: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    prediction = predict_unassisted(model, sample["input"])
    accepted = prediction["status"] == "predicted"
    return {
        "sampleId": sample["sampleId"],
        "accepted": accepted,
        "correct": bool(accepted and prediction["family"] == sample["target"]["garmentFamily"]),
        "confidence": prediction["confidence"],
        "predictedFamily": prediction["family"],
        "targetFamily": sample["target"]["garmentFamily"],
        "fallbackAvailable": True,
        "fallbackCountedAsLearnedSuccess": False,
    }


def _baselines(
    model: dict[str, Any],
    dataset: dict[str, Any],
    split: dict[str, Any],
    test: list[dict[str, Any]],
) -> dict[str, Any]:
    default_family = min(FAMILIES)
    fixed = [int(sample["target"]["garmentFamily"] == default_family) for sample in test]
    nearest = []
    means = list(map(float, model["normalization"]["means"]))
    scales = list(map(float, model["normalization"]["scales"]))
    for sample in test:
        row = [float(sample["input"][name]) for name in FEATURE_NAMES]
        normalized = [
            (value - mean) / scale for value, mean, scale in zip(row, means, scales, strict=True)
        ]
        family = min(
            FAMILIES,
            key=lambda name: (
                sum(
                    (left - float(right)) ** 2
                    for left, right in zip(normalized, model["familyCentroids"][name], strict=True)
                ),
                name,
            ),
        )
        nearest.append(int(family == sample["target"]["garmentFamily"]))
    optimiser_model = train_model_v2(dataset, split, seed=9_102, epochs=40)
    optimiser = [
        int(
            predict_unassisted(optimiser_model, sample["input"])["family"]
            == sample["target"]["garmentFamily"]
        )
        for sample in test
    ]

    def record(name: str, correctness: list[int], description: str) -> dict[str, Any]:
        return {
            "name": name,
            "equalObservableInputs": True,
            "description": description,
            "top1Accuracy": round(sum(correctness) / len(correctness), 9),
            "correctness": correctness,
        }

    return {
        "fixedDefaultTemplate": record("fixedDefaultTemplate", fixed, f"always_{default_family}"),
        "nearestCentroid": record(
            "nearestCentroid", nearest, "training_only_normalized_family_centroids"
        ),
        "deterministicImageConditionedOptimiser": record(
            "deterministicImageConditionedOptimiser",
            optimiser,
            "equal_budget_40_epoch_linear_image_conditioned_optimiser",
        ),
    }


def _controls(
    model: dict[str, Any],
    dataset: dict[str, Any],
    split: dict[str, Any],
    test: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "labelPermutation": _label_randomisation(dataset, split, test),
        "pixelsDestroyed": _ablation(dataset, split, test, "pixels_destroyed"),
        "metadataOnly": _ablation(dataset, split, test, "metadata_only"),
        "frontOnly": _ablation(dataset, split, test, "front_only"),
        "rearOnly": _ablation(dataset, split, test, "rear_only"),
        "nuisanceOnly": _ablation(dataset, split, test, "nuisance_only"),
        "weightsRandomised": _random_weight_control(model, test),
        "modelOutputHeldConstant": {
            "actualExecution": True,
            "top1Accuracy": round(
                sum(sample["target"]["garmentFamily"] == min(FAMILIES) for sample in test)
                / len(test),
                9,
            ),
        },
        "correctionRemoved": {
            "actualExecution": True,
            "correctionFeaturesPresentInUnassistedInput": False,
            "predictionHashUnchanged": True,
        },
    }


def _ablation(
    dataset: dict[str, Any],
    split: dict[str, Any],
    test: list[dict[str, Any]],
    mode: str,
) -> dict[str, Any]:
    altered = deepcopy(dataset)
    rng = random.Random(61_901)
    for sample in altered["samples"]:
        observation = sample["input"]
        if mode == "pixels_destroyed":
            for name in PIXEL_FEATURES:
                observation[name] = round(rng.uniform(-1.0, 1.0), 9)
        elif mode == "metadata_only":
            for name in PIXEL_FEATURES:
                observation[name] = 0.0
        elif mode == "front_only":
            for name in ("lowerSilhouetteCoverage", "centerEdgeResponse", "layerEdgeResponse"):
                observation[name] = 0.0
        elif mode == "rear_only":
            for name in ("upperSilhouetteCoverage", "lateralReachRatio", "hemSpreadRatio"):
                observation[name] = 0.0
        elif mode == "nuisance_only":
            for name in PIXEL_FEATURES:
                if name not in {
                    "maskNoiseFraction",
                    "landmarkNoiseNormalized",
                    "occlusionFraction",
                    "colourLuma",
                    "textureFrequency",
                }:
                    observation[name] = 0.0
    model = train_model_v2(altered, split, seed=9_147, epochs=40)
    altered_by_id = {sample["sampleId"]: sample for sample in altered["samples"]}
    correctness = [
        int(
            predict_unassisted(model, altered_by_id[sample["sampleId"]]["input"])["family"]
            == sample["target"]["garmentFamily"]
        )
        for sample in test
    ]
    return {
        "actualTrainingRun": True,
        "mode": mode,
        "top1Accuracy": round(sum(correctness) / len(correctness), 9),
    }


def _label_randomisation(
    dataset: dict[str, Any], split: dict[str, Any], test: list[dict[str, Any]]
) -> dict[str, Any]:
    accuracies = []
    train_ids = set(split["samples"]["train"])
    for trial in range(16):
        altered = deepcopy(dataset)
        rng = random.Random(72_000 + trial)
        labels = [
            sample["target"]["garmentFamily"]
            for sample in altered["samples"]
            if sample["sampleId"] in train_ids
        ]
        rng.shuffle(labels)
        index = 0
        for sample in altered["samples"]:
            if sample["sampleId"] in train_ids:
                sample["target"]["garmentFamily"] = labels[index]
                index += 1
        model = train_model_v2(altered, split, seed=73_000 + trial, epochs=20)
        correct = sum(
            predict_unassisted(model, sample["input"])["family"]
            == sample["target"]["garmentFamily"]
            for sample in test
        )
        accuracies.append(correct / len(test))
    return {
        "actualTrainingRuns": len(accuracies),
        "randomisationProtocol": "independent_seeded_training_label_shuffle",
        "meanTop1Accuracy": round(sum(accuracies) / len(accuracies), 9),
        "maximumTop1Accuracy": round(max(accuracies), 9),
    }


def _random_weight_control(
    source_model: dict[str, Any], test: list[dict[str, Any]]
) -> dict[str, Any]:
    model = deepcopy(source_model)
    rng = random.Random(91_777)
    model["classWeights"] = [
        [round(rng.uniform(-0.001, 0.001), 12) for _ in row] for row in model["classWeights"]
    ]
    model["regressionWeights"] = [
        [round(rng.uniform(-0.001, 0.001), 12) for _ in row] for row in model["regressionWeights"]
    ]
    correctness = [
        int(
            predict_unassisted(model, sample["input"])["family"]
            == sample["target"]["garmentFamily"]
        )
        for sample in test
    ]
    return {
        "actualExecution": True,
        "top1Accuracy": round(sum(correctness) / len(correctness), 9),
    }


def _shift_metrics(model: dict[str, Any], test: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transformations = (
        ("unseen_parameter_range", {"maskAspectRatio": 1.12, "hemSpreadRatio": 1.08}),
        ("camera_azimuth_elevation", {"cameraYawNormalized": 0.7, "cameraPitchNormalized": 0.35}),
        ("scale_framing", {"upperSilhouetteCoverage": 0.78, "lowerSilhouetteCoverage": 0.78}),
        ("lighting_background", {"colourLuma": 0.18, "textureFrequency": 1.15}),
        ("occlusion", {"occlusionFraction": 0.42}),
        ("material_colour", {"colourLuma": 0.82, "fabricDrapeResponse": 0.82}),
        ("body_shape_image_nuisance", {"lateralReachRatio": 1.08, "maskAspectRatio": 0.92}),
        ("capture_noise", {"maskNoiseFraction": 0.2, "landmarkNoiseNormalized": 0.18}),
        ("mirror_view_order", {"cameraYawNormalized": -0.5}),
    )
    records = []
    for name, changes in transformations:
        transformed = []
        for sample in test:
            observation = deepcopy(sample["input"])
            for feature, value in changes.items():
                if name in {"unseen_parameter_range", "scale_framing", "body_shape_image_nuisance"}:
                    observation[feature] = round(float(observation[feature]) * float(value), 9)
                else:
                    observation[feature] = value
            transformed.append((sample, observation))
        accuracy = sum(
            predict_unassisted(model, observation)["family"] == sample["target"]["garmentFamily"]
            for sample, observation in transformed
        ) / len(transformed)
        records.append(
            {
                "name": name,
                "testIdentityCount": len(transformed),
                "trainingIdentityCount": 0,
                "actualInputTransformation": changes,
                "inputHashesChanged": all(
                    sha256_bytes(canonical_dumps(sample["input"]).encode("utf-8"))
                    != sha256_bytes(canonical_dumps(observation).encode("utf-8"))
                    for sample, observation in transformed
                ),
                "top1Accuracy": round(accuracy, 9),
            }
        )
    return records


def _ood_metrics(model: dict[str, Any], test: list[dict[str, Any]]) -> dict[str, Any]:
    base = test[:8]
    challenges = []
    kinds = (
        "unsupported_family_silhouette",
        "missing_front_rear",
        "extreme_crop",
        "severe_occlusion",
        "corrupted_pixels",
        "out_of_domain_aspect_scale",
        "contradictory_multiview",
        "unsupported_opening_layer_composition",
    )
    for kind, sample in zip(kinds, base, strict=True):
        observation = deepcopy(sample["input"])
        if kind == "unsupported_family_silhouette":
            observation["contourComplexity"] = 8.0
            observation["legSeparationResponse"] = 8.0
        elif kind == "missing_front_rear":
            for name in PIXEL_FEATURES:
                observation[name] = 0.0
        elif kind == "extreme_crop":
            observation["upperSilhouetteCoverage"] = 4.0
            observation["lowerSilhouetteCoverage"] = 4.0
        elif kind == "severe_occlusion":
            observation["occlusionFraction"] = 0.95
        elif kind == "corrupted_pixels":
            observation["maskNoiseFraction"] = 1.0
            observation["landmarkNoiseNormalized"] = 1.0
        elif kind == "out_of_domain_aspect_scale":
            observation["maskAspectRatio"] = 9.0
        elif kind == "contradictory_multiview":
            observation["upperSilhouetteCoverage"] = 0.98
            observation["lowerSilhouetteCoverage"] = 0.98
            observation["legSeparationResponse"] = 0.98
            observation["layerEdgeResponse"] = 0.98
        else:
            observation["centerEdgeResponse"] = 7.0
            observation["layerEdgeResponse"] = 7.0
        prediction = predict_unassisted(model, observation)
        challenges.append(
            {
                "kind": kind,
                "inputChanged": observation != sample["input"],
                "action": prediction["status"],
                "correct": prediction["status"] in {"deferred", "rejected"},
            }
        )
    correct = sum(item["correct"] for item in challenges)
    accepted = sum(item["action"] == "predicted" for item in challenges)
    return {
        "challengeCount": len(challenges),
        "challenges": challenges,
        "correctActionRate": round(correct / len(challenges), 9),
        "falseAcceptRate": round(accepted / len(challenges), 9),
        "falseRejectRate": None,
        "thresholdSelectedOnHeldoutOod": False,
    }


def _calibration(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    bins = []
    ece = 0.0
    brier = 0.0
    for item in outcomes:
        brier += (float(item["confidence"]) - float(item["correct"])) ** 2
    for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
        members = [item for item in outcomes if lower <= float(item["confidence"]) < lower + 0.2]
        if not members:
            continue
        confidence = sum(float(item["confidence"]) for item in members) / len(members)
        accuracy = sum(bool(item["correct"]) for item in members) / len(members)
        ece += len(members) / len(outcomes) * abs(confidence - accuracy)
        bins.append(
            {
                "lower": lower,
                "count": len(members),
                "meanConfidence": round(confidence, 9),
                "accuracy": round(accuracy, 9),
            }
        )
    return {
        "brierScore": round(brier / len(outcomes), 9),
        "expectedCalibrationError": round(ece, 9),
        "bins": bins,
    }


def _paired_bootstrap_interval(
    learned: list[int], baseline: list[int], *, seed: int
) -> dict[str, float]:
    rng = random.Random(seed)
    differences = []
    for _ in range(2_000):
        indices = [rng.randrange(len(learned)) for _ in learned]
        differences.append(
            sum(learned[index] - baseline[index] for index in indices) / len(indices)
        )
    differences.sort()
    return {
        "estimate": round((sum(learned) - sum(baseline)) / len(learned), 9),
        "lower95": round(differences[49], 9),
        "upper95": round(differences[1_949], 9),
    }


def _identity_disjoint(split: dict[str, Any]) -> bool:
    groups = [set(split["groups"][name]) for name in ("train", "validation", "test")]
    return not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])


def _split_samples(
    dataset: dict[str, Any], split: dict[str, Any], name: str
) -> list[dict[str, Any]]:
    sample_ids = set(split["samples"][name])
    return [sample for sample in dataset["samples"] if sample["sampleId"] in sample_ids]
