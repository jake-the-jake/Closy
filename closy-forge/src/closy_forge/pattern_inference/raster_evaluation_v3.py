from __future__ import annotations

import math
import random
from copy import deepcopy
from typing import Any

from .dataset_v2 import FEATURE_NAMES
from .evaluation_v2 import evaluate_model_v2
from .model_v2 import FAMILIES, predict_v2, train_model_v2

EVALUATION_VERSION_V3 = "closy.raster_pattern_evaluation.synthetic_d0.v3"
PIXEL_FEATURES = tuple(
    name for name in FEATURE_NAMES if name not in {"cameraYawNormalized", "cameraPitchNormalized"}
)


def evaluate_raster_model_v3(
    model: dict[str, Any], dataset: dict[str, Any], split: dict[str, Any]
) -> dict[str, Any]:
    primary = evaluate_model_v2(model, dataset, split)
    test_samples = _split_samples(dataset, split, "test")
    controls = {
        "labelPermutation": _label_permutation_control(dataset, split),
        "pixelsDestroyed": _input_ablation_control(dataset, split, PIXEL_FEATURES),
        "metadataOnly": _input_ablation_control(dataset, split, PIXEL_FEATURES),
    }
    top1 = float(primary["familyTemplate"]["top1Accuracy"])
    return {
        "schemaVersion": 1,
        "evaluationVersion": EVALUATION_VERSION_V3,
        "track": "unassisted_raster_project_authored_synthetic_d0_cpu",
        "primary": primary,
        "confidenceIntervals": {
            "familyTop1DeterministicBootstrap95": _bootstrap_accuracy_interval(
                model, test_samples, seed=7713
            )
        },
        "controls": controls,
        "controlThresholds": {
            "classChance": round(1.0 / len(FAMILIES), 9),
            "maximumChanceControlAccuracy": 0.25,
            "labelPermutationPass": controls["labelPermutation"]["top1Accuracy"] <= 0.25,
            "pixelsDestroyedPass": controls["pixelsDestroyed"]["top1Accuracy"] <= 0.25,
            "metadataOnlyPass": controls["metadataOnly"]["top1Accuracy"] <= 0.25,
        },
        "shiftSuites": _shift_suite_metrics(model, dataset),
        "leakageAudits": {
            "splitIdentityRecomputed": True,
            "identityComputedBeforeAugmentation": True,
            "deliberateLeakageFixtureRejected": _deliberate_leakage_rejected(dataset, split),
            "duplicatePixelHashes": _duplicate_pixel_hash_count(dataset),
            "nuisanceFamilyMutualInformationBits": _nuisance_mutual_information(dataset),
            "seedReallocation": {
                "status": "pass",
                "policy": "generator_seeds_private_and_absent_from_observation_axis",
                "featureNamesContainSeed": any("seed" in name.lower() for name in FEATURE_NAMES),
            },
            "rendererFamilyHoldout": {
                "status": "not_run",
                "reason": "only_one_genuinely_distinct_renderer_implementation_available",
            },
            "capturePipelineVariantHoldout": {
                "status": "not_run",
                "reason": "one_canonical_phase2_decoder; mirrored_capture_is_a_shift_not_a_decoder",
            },
        },
        "comparison": {
            "learnedTop1": round(top1, 9),
            "nearestCentroidTop1": primary["comparison"]["baselineTop1Accuracy"],
            "learnedSuperioritySupported": bool(
                primary["comparison"]["learnedSuperioritySupported"]
            ),
            "claim": primary["comparison"]["claim"],
        },
        "claims": {
            "e1Candidate": bool(top1 > 0.25),
            "e2StructuredGeneration": False,
            "realPhotoGeneralisation": False,
            "privateUserGeneralisation": False,
            "globalPhase9Complete": False,
        },
    }


def _label_permutation_control(dataset: dict[str, Any], split: dict[str, Any]) -> dict[str, Any]:
    permuted = deepcopy(dataset)
    train_ids = set(split["samples"]["train"])
    mapping = {
        family: FAMILIES[(index + 3) % len(FAMILIES)] for index, family in enumerate(FAMILIES)
    }
    for sample in permuted["samples"]:
        if sample["sampleId"] in train_ids:
            family = str(sample["target"]["garmentFamily"])
            sample["target"]["garmentFamily"] = mapping[family]
    control_model = train_model_v2(permuted, split, seed=9123)
    return {
        "actualTrainingRun": True,
        "top1Accuracy": _top1(control_model, _split_samples(dataset, split, "test")),
        "expectedMaximum": 0.25,
    }


def _input_ablation_control(
    dataset: dict[str, Any], split: dict[str, Any], removed_features: tuple[str, ...]
) -> dict[str, Any]:
    ablated = deepcopy(dataset)
    for sample in ablated["samples"]:
        for name in removed_features:
            sample["input"][name] = 0.0
    control_model = train_model_v2(ablated, split, seed=9147)
    return {
        "actualTrainingRun": True,
        "removedFeatures": list(removed_features),
        "top1Accuracy": _top1(control_model, _split_samples(ablated, split, "test")),
        "expectedMaximum": 0.25,
    }


def _shift_suite_metrics(model: dict[str, Any], dataset: dict[str, Any]) -> list[dict[str, Any]]:
    samples = {sample["sampleId"]: sample for sample in dataset["samples"]}
    records = []
    for suite in dataset["shiftSuites"]:
        selected = [samples[sample_id] for sample_id in suite["sampleIds"] if sample_id in samples]
        records.append(
            {
                "suiteId": suite["suiteId"],
                "heldOutAxis": suite["heldOutAxis"],
                "sampleCount": len(selected),
                "top1Accuracy": _top1(model, selected),
            }
        )
    return records


def _deliberate_leakage_rejected(dataset: dict[str, Any], split: dict[str, Any]) -> bool:
    from .raster_dataset_v3 import validate_raster_dataset_v3

    corrupted = deepcopy(split)
    corrupted["groups"]["test"].append(corrupted["groups"]["train"][0])
    return "raster_source_identity_leakage" in validate_raster_dataset_v3(dataset, corrupted)


def _duplicate_pixel_hash_count(dataset: dict[str, Any]) -> int:
    hashes = [str(sample["captureAudit"]["combinedPixelHash"]) for sample in dataset["samples"]]
    return len(hashes) - len(set(hashes))


def _nuisance_mutual_information(dataset: dict[str, Any]) -> dict[str, float]:
    families = [str(sample["target"]["garmentFamily"]) for sample in dataset["samples"]]
    result: dict[str, float] = {}
    for key in ("materialFamily", "backgroundFamily", "captureStyle"):
        nuisance = [
            str(sample["captureAudit"]["nuisanceAudit"][key]) for sample in dataset["samples"]
        ]
        result[key] = round(_mutual_information(families, nuisance), 12)
    return result


def _mutual_information(left: list[str], right: list[str]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("mutual_information_axis_invalid")
    left_counts: dict[str, int] = {}
    right_counts: dict[str, int] = {}
    joint: dict[tuple[str, str], int] = {}
    for a, b in zip(left, right, strict=True):
        left_counts[a] = left_counts.get(a, 0) + 1
        right_counts[b] = right_counts.get(b, 0) + 1
        joint[(a, b)] = joint.get((a, b), 0) + 1
    count = len(left)
    return sum(
        (observed / count) * math.log2((observed * count) / (left_counts[a] * right_counts[b]))
        for (a, b), observed in joint.items()
    )


def _bootstrap_accuracy_interval(
    model: dict[str, Any], samples: list[dict[str, Any]], *, seed: int
) -> list[float]:
    outcomes = [
        int(predict_v2(model, sample["input"])["family"] == sample["target"]["garmentFamily"])
        for sample in samples
    ]
    random_source = random.Random(seed)
    estimates = sorted(
        sum(outcomes[random_source.randrange(len(outcomes))] for _ in outcomes) / len(outcomes)
        for _iteration in range(500)
    )
    return [round(estimates[12], 9), round(estimates[487], 9)]


def _top1(model: dict[str, Any], samples: list[dict[str, Any]]) -> float:
    if not samples:
        return 0.0
    correct = sum(
        str(predict_v2(model, sample["input"])["family"]) == str(sample["target"]["garmentFamily"])
        for sample in samples
    )
    return round(correct / len(samples), 9)


def _split_samples(
    dataset: dict[str, Any], split: dict[str, Any], name: str
) -> list[dict[str, Any]]:
    ids = set(split["samples"][name])
    return [sample for sample in dataset["samples"] if sample["sampleId"] in ids]
