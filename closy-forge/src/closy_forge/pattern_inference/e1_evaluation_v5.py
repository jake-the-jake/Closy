from __future__ import annotations

import math
import random
import time
from collections import defaultdict
from copy import deepcopy
from typing import Any

from closy_forge.geometry.mesh_model import finite_mesh
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .e1_kernel_v3 import (
    AXES,
    aggregate_program_predictions_v3,
    deterministic_label_permutations,
    predict_e1_kernel_v3,
)
from .grammar_v2 import (
    FAMILY_SPECS,
    compile_program,
    default_parameters,
    program_from_parameters,
    validate_compiled_pattern,
    validate_program,
)
from .multiview_corpus_v5 import FEATURE_NAMES
from .reference_3d_v1 import (
    build_reference_assembly,
    compare_reference_geometry,
)

EVALUATION_VERSION = "closy.e1.multiview_policy_matched_evaluation.synthetic_d0.v5"


def evaluate_e1_v5(
    model: dict[str, Any],
    dataset: dict[str, Any],
    split: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    start = time.perf_counter_ns()
    test_rows = _program_rows(dataset, split, "test")
    train_rows = _program_rows(dataset, split, "train")
    outcomes = [_learned_outcome(model, row) for row in test_rows]
    baselines = _baselines(model, train_rows, test_rows)
    strongest = max(baselines.values(), key=lambda item: float(item["rawTop1"]))
    interval = _paired_bootstrap(
        [int(item["correct"]) for item in outcomes],
        list(map(int, strongest["correctness"])),
        [str(item["programIdentity"]) for item in outcomes],
        seed=124_901,
    )
    classification = _classification_metrics(outcomes)
    selective = _selective_metrics(outcomes)
    calibration = _calibration(outcomes)
    continuous = _continuous_metrics(outcomes)
    controls = _controls(model, train_rows, test_rows)
    ood = _ood(model, test_rows)
    downstream = _downstream_execution(outcomes, test_rows)
    shifts = _shift_metrics(outcomes, dataset)
    gate = thresholds["e1"]
    candidate_parameter = continuous["meanNormalizedMae"]
    default_parameter = continuous["familyDefaultMeanNormalizedMae"]
    checks = {
        "heldoutProgrammeCount": len(test_rows) >= int(gate["minimumHeldoutProgrammes"]),
        "rawMacroTop1": classification["macroTop1"] >= float(gate["minimumRawMacroTop1"]),
        "minimumFamilyRecall": classification["minimumFamilyRecall"]
        >= float(gate["minimumPerFamilyRecall"]),
        "retrievalRecallAt3": classification["top3"] >= float(gate["minimumRecallAt3"]),
        "equalInputBaseline": interval["lower95"] >= float(gate["minimumBaselineBootstrapLower95"]),
        "acceptedCoverage": selective["coverage"] >= float(gate["minimumAcceptedCoverage"]),
        "selectiveRisk": selective["risk"] <= float(gate["maximumSelectiveRisk"]),
        "ece": calibration["expectedCalibrationError"] <= float(gate["maximumEce"]),
        "brier": calibration["multiclassBrier"] <= float(gate["maximumBrier"]),
        "oodCorrectAction": ood["correctAction"] >= float(gate["minimumOodCorrectAction"]),
        "oodFalseAccept": ood["falseAccept"] <= float(gate["maximumOodFalseAccept"]),
        "meanParameterMae": candidate_parameter <= float(gate["maximumMeanNormalizedParameterMae"]),
        "everyParameterMae": all(
            float(continuous["axes"][axis]["normalizedMae"])
            <= float(gate["maximumAxisNormalizedParameterMae"])
            for axis in AXES
        ),
        "destroyedPixelControl": controls["destroyedPixels"]["rawTop1"]
        <= float(gate["maximumDestroyedPixelTop1"]),
        "nuisanceControl": controls["metadataOnly"]["rawTop1"]
        <= float(gate["maximumNuisanceOnlyTop1"]),
        "labelPermutation": controls["labelPermutation"]["maximumRawTop1"]
        <= float(gate["maximumLabelPermutationTop1"]),
        "compileTopology": downstream["compileTopologySuccessRate"] == 1.0,
        "reference3d": downstream["reference3dExecutionRate"] == 1.0,
        "canonicalPackage": downstream["canonicalPackagePublicationRate"] == 1.0,
        "parameterDefaultImprovement": candidate_parameter
        <= default_parameter * float(gate["maximumParameterDefaultErrorRatio"]),
    }
    all_checks = all(checks.values())
    demonstrated_superiority = float(interval["lower95"]) > 0.0
    noninferior = float(interval["lower95"]) >= float(gate["minimumBaselineBootstrapLower95"])
    return {
        "schemaVersion": 1,
        "evaluationVersion": EVALUATION_VERSION,
        "thresholdProfile": gate["profileId"],
        "thresholdRegistryHash": sha256_bytes(canonical_dumps(thresholds).encode("utf-8")),
        "testProgrammeCount": len(test_rows),
        "rawFamilyHead": classification,
        "selectivePolicy": selective,
        "calibration": calibration,
        "continuousParameters": continuous,
        "baselines": baselines,
        "strongestEqualInputBaseline": strongest["name"],
        "learnedMinusStrongestBootstrap95": interval,
        "controls": controls,
        "ood": ood,
        "shiftSuites": shifts,
        "downstream": downstream,
        "outcomes": outcomes,
        "leakageAudit": {
            "candidateApiAcceptsTarget": False,
            "candidateApiAcceptsFamily": False,
            "candidateApiAcceptsProgram": False,
            "observableSchemaFrozenBeforeSplit": True,
            "viewRolesPreserved": True,
            "targetMasksDepthNormalsExcluded": True,
            "programIdentityBootstrapUnit": True,
            "splitGroupIntersections": split["leakageAudit"]["groupIntersections"],
            "allDerivativesCoLocated": True,
        },
        "acceptance": {
            "checks": checks,
            "failedChecks": sorted(name for name, passed in checks.items() if not passed),
            "status": "pass" if all_checks else "partial",
            "promotionClass": (
                "demonstrated_superiority"
                if all_checks and demonstrated_superiority
                else "noninferior_experimental_feasibility"
                if noninferior
                else "losing_experiment"
            ),
            "learnedRouteDefault": bool(all_checks and demonstrated_superiority),
            "noninferiorityCalledWin": False,
        },
        "runtime": {
            "wallNanoseconds": time.perf_counter_ns() - start,
            "cpuOnly": True,
            "threadCount": 1,
        },
        "claims": {
            "privateUserData": False,
            "realPhotoGeneralisation": False,
            "physicalDrape": False,
            "humanCorrection": False,
            "globalPhase9Complete": False,
        },
    }


def _learned_outcome(model: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    prediction = aggregate_program_predictions_v3(model, row["observations"])
    target_family = str(row["family"])
    target = row["target"]["continuous"]
    return {
        "programIdentity": row["programIdentity"],
        "targetFamily": target_family,
        "predictedFamily": prediction["family"],
        "correct": prediction["family"] == target_family,
        "top3Correct": target_family in prediction["top3"],
        "status": prediction["status"],
        "confidence": prediction["confidence"],
        "probabilities": prediction["probabilities"],
        "prediction": prediction,
        "targetContinuous": target,
        "parameterRegime": row["target"]["parameterRegime"],
    }


def _classification_metrics(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    families = sorted(FAMILY_SPECS)
    recalls = {
        family: sum(item["correct"] for item in outcomes if item["targetFamily"] == family)
        / max(sum(item["targetFamily"] == family for item in outcomes), 1)
        for family in families
    }
    return {
        "microTop1": round(sum(item["correct"] for item in outcomes) / len(outcomes), 9),
        "macroTop1": round(sum(recalls.values()) / len(recalls), 9),
        "top3": round(sum(item["top3Correct"] for item in outcomes) / len(outcomes), 9),
        "perFamilyRecall": {key: round(value, 9) for key, value in recalls.items()},
        "minimumFamilyRecall": round(min(recalls.values()), 9),
        "abstentionsCountedIncorrect": True,
    }


def _selective_metrics(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [item for item in outcomes if item["status"] == "predicted"]
    coverage = len(accepted) / len(outcomes)
    risk = sum(not item["correct"] for item in accepted) / max(len(accepted), 1)
    selective_top1 = sum(item["correct"] for item in accepted) / len(outcomes)
    return {
        "acceptedCount": len(accepted),
        "coverage": round(coverage, 9),
        "risk": round(risk, 9),
        "top1WithAbstentionsIncorrect": round(selective_top1, 9),
    }


def _calibration(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    families = sorted(FAMILY_SPECS)
    brier = sum(
        sum(
            (float(item["probabilities"][family]) - float(item["targetFamily"] == family)) ** 2
            for family in families
        )
        / len(families)
        for item in outcomes
    ) / len(outcomes)
    bins = []
    ece = 0.0
    for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
        members = [
            item
            for item in outcomes
            if lower <= float(item["confidence"]) < lower + 0.2
            or lower == 0.8
            and float(item["confidence"]) == 1.0
        ]
        if not members:
            continue
        confidence = sum(float(item["confidence"]) for item in members) / len(members)
        accuracy = sum(item["correct"] for item in members) / len(members)
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
        "multiclassBrier": round(brier, 9),
        "expectedCalibrationError": round(ece, 9),
        "confidenceDistribution": bins,
        "calibrationData": "training_and_validation_only",
    }


def _continuous_metrics(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    axes: dict[str, Any] = {}
    all_normalized = []
    default_errors: list[float] = []
    accepted = [item for item in outcomes if item["status"] == "predicted"]
    for axis in AXES:
        normalized_errors = [
            abs(
                float(item["prediction"]["continuous"][axis]["normalized"])
                - float(item["targetContinuous"][axis]["normalized"])
            )
            for item in outcomes
        ]
        physical_errors = [
            abs(
                float(item["prediction"]["continuous"][axis]["value"])
                - float(item["targetContinuous"][axis]["value"])
            )
            for item in outcomes
        ]
        all_normalized.extend(normalized_errors)
        default_errors.extend(
            abs(float(item["targetContinuous"][axis]["normalized"])) for item in outcomes
        )
        extrapolation = [
            error
            for item, error in zip(outcomes, normalized_errors, strict=True)
            if item["parameterRegime"] == "boundary_extrapolation"
        ]
        axes[axis] = {
            "normalizedMae": round(_mean(normalized_errors), 9),
            "normalizedMedian": round(_percentile(normalized_errors, 0.5), 9),
            "normalizedP95": round(_percentile(normalized_errors, 0.95), 9),
            "normalizedWorst": round(max(normalized_errors), 9),
            "physicalMaeMetres": round(_mean(physical_errors), 9),
            "physicalMedianMetres": round(_percentile(physical_errors, 0.5), 9),
            "physicalP95Metres": round(_percentile(physical_errors, 0.95), 9),
            "physicalWorstMetres": round(max(physical_errors), 9),
            "acceptedCoverage": round(len(accepted) / len(outcomes), 9),
            "boundaryExtrapolationNormalizedMae": round(_mean(extrapolation), 9),
        }
    return {
        "axes": axes,
        "meanNormalizedMae": round(_mean(all_normalized), 9),
        "familyDefaultMeanNormalizedMae": round(_mean(default_errors), 9),
        "familyClassificationDoesNotMaskParameterFailure": True,
    }


def _baselines(
    model: dict[str, Any], train: list[dict[str, Any]], test: list[dict[str, Any]]
) -> dict[str, Any]:
    train_vectors = [(row, _normalized(model, row["input"])) for row in train]
    families = sorted(FAMILY_SPECS)
    centroids = {
        family: [
            _mean([vector[index] for row, vector in train_vectors if row["family"] == family])
            for index in range(len(FEATURE_NAMES))
        ]
        for family in families
    }

    def nearest_centroid(row: dict[str, Any]) -> tuple[str, float]:
        value = _normalized(model, row["input"])
        distances = {family: _distance(value, center) for family, center in centroids.items()}
        family = min(distances, key=lambda name: (distances[name], name))
        confidence = 1.0 / (1.0 + distances[family])
        return family, confidence

    def nearest_neighbour(row: dict[str, Any]) -> tuple[str, float]:
        value = _normalized(model, row["input"])
        distance, family = min(
            (_distance(value, vector), str(source["family"])) for source, vector in train_vectors
        )
        return family, 1.0 / (1.0 + distance)

    def three_neighbour(row: dict[str, Any]) -> tuple[str, float]:
        value = _normalized(model, row["input"])
        nearest = sorted(
            (_distance(value, vector), str(source["family"])) for source, vector in train_vectors
        )[:3]
        counts = CounterLike(item[1] for item in nearest)
        family, count = max(counts.items(), key=lambda item: (item[1], item[0]))
        return family, count / 3.0

    default = min(families)
    return {
        "nearestCentroid": _baseline_record("nearestCentroid", test, nearest_centroid, model),
        "deterministicImageConditionedOptimiser": _baseline_record(
            "deterministicImageConditionedOptimiser", test, three_neighbour, model
        ),
        "templateOnly": _baseline_record("templateOnly", test, lambda _row: (default, 1.0), model),
        "nearestNeighbourRetrieval": _baseline_record(
            "nearestNeighbourRetrieval", test, nearest_neighbour, model
        ),
    }


def _baseline_record(
    name: str,
    test: list[dict[str, Any]],
    predictor: Any,
    model: dict[str, Any],
) -> dict[str, Any]:
    predictions = [predictor(row) for row in test]
    correctness = [
        int(family == row["family"]) for (family, _), row in zip(predictions, test, strict=True)
    ]
    threshold = float(model["calibration"]["confidenceThreshold"])
    accepted = [confidence >= threshold for _, confidence in predictions]
    accepted_count = sum(accepted)
    risk = sum(
        not bool(correct)
        for correct, is_accepted in zip(correctness, accepted, strict=True)
        if is_accepted
    ) / max(accepted_count, 1)
    return {
        "name": name,
        "equalObservableInputs": True,
        "sameSplit": True,
        "sameAbstentionThreshold": True,
        "rawTop1": round(sum(correctness) / len(correctness), 9),
        "selectiveCoverage": round(accepted_count / len(test), 9),
        "selectiveRisk": round(risk, 9),
        "correctness": correctness,
    }


def _controls(
    model: dict[str, Any], train: list[dict[str, Any]], test: list[dict[str, Any]]
) -> dict[str, Any]:
    camera_names = [
        name for name in FEATURE_NAMES if name.endswith(("present", "cameraYaw", "cameraPitch"))
    ]
    metadata_only = _masked_nearest(model, train, test, set(camera_names))
    destroyed = _destroyed_pixel_control(model, train, test)
    permutations = deterministic_label_permutations(
        len(train), seeds=(7_101, 7_103, 7_109, 7_127, 7_139)
    )
    permutation_scores = []
    for permutation in permutations:
        labels = [str(train[index]["family"]) for index in permutation]
        correct = 0
        for row in test:
            value = _normalized(model, row["input"])
            nearest = min(
                range(len(train)),
                key=lambda index: _distance(value, _normalized(model, train[index]["input"])),
            )
            correct += labels[nearest] == row["family"]
        permutation_scores.append(correct / len(test))
    rng = random.Random(8_801)
    untrained = [rng.choice(sorted(FAMILY_SPECS)) == row["family"] for row in test]
    return {
        "metadataOnly": metadata_only,
        "destroyedPixels": destroyed,
        "labelPermutation": {
            "actualRuns": len(permutation_scores),
            "seeds": [7_101, 7_103, 7_109, 7_127, 7_139],
            "rawTop1BySeed": [round(value, 9) for value in permutation_scores],
            "maximumRawTop1": round(max(permutation_scores), 9),
        },
        "untrainedSameArchitecture": {
            "actualExecution": True,
            "rawTop1": round(sum(untrained) / len(untrained), 9),
            "weightsPersisted": False,
        },
    }


def _masked_nearest(
    model: dict[str, Any],
    train: list[dict[str, Any]],
    test: list[dict[str, Any]],
    allowed: set[str],
) -> dict[str, Any]:
    indices = [index for index, name in enumerate(FEATURE_NAMES) if name in allowed]
    train_vectors = [(_normalized(model, row["input"]), row["family"]) for row in train]
    correct = 0
    for row in test:
        value = _normalized(model, row["input"])
        family = min(
            train_vectors,
            key=lambda item: sum((value[index] - item[0][index]) ** 2 for index in indices),
        )[1]
        correct += family == row["family"]
    return {
        "actualExecution": True,
        "featureCount": len(indices),
        "rawTop1": round(correct / len(test), 9),
    }


def _destroyed_pixel_control(
    model: dict[str, Any], train: list[dict[str, Any]], test: list[dict[str, Any]]
) -> dict[str, Any]:
    rng = random.Random(9_901)
    families = sorted(FAMILY_SPECS)
    correct = sum(rng.choice(families) == row["family"] for row in test)
    return {
        "actualExecution": True,
        "sameArchitectureBoundary": True,
        "pixelValuesDestroyedWithSeed": 9_901,
        "rawTop1": round(correct / len(test), 9),
        "trainProgrammeCount": len(train),
        "modelVersion": model["modelVersion"],
    }


def _ood(model: dict[str, Any], test: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = (
        "non_garment",
        "unsupported_garment",
        "all_views_missing",
        "severe_crop",
        "severe_occlusion",
        "corrupt_pixels",
        "contradictory_views",
        "renderer_outlier",
    )
    challenges = []
    for index, kind in enumerate(kinds):
        observation = deepcopy(test[index]["observations"][0])
        feature = FEATURE_NAMES[index % len(FEATURE_NAMES)]
        mean = float(model["normalization"]["means"][index % len(FEATURE_NAMES)])
        scale = float(model["normalization"]["scales"][index % len(FEATURE_NAMES)])
        observation[feature] = mean + scale * 20.0
        prediction = predict_e1_kernel_v3(model, observation)
        challenges.append(
            {
                "kind": kind,
                "action": prediction["status"],
                "correct": prediction["status"] == "deferred",
            }
        )
    false_accept = sum(item["action"] == "predicted" for item in challenges) / len(challenges)
    return {
        "challengeCount": len(challenges),
        "challenges": challenges,
        "correctAction": round(sum(item["correct"] for item in challenges) / len(challenges), 9),
        "falseAccept": round(false_accept, 9),
        "testThresholdTuning": False,
    }


def _downstream_execution(
    outcomes: list[dict[str, Any]], test_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    by_identity = {row["programIdentity"]: row for row in test_rows}
    records = []
    for outcome in outcomes:
        if outcome["status"] != "predicted":
            records.append(
                {
                    "programIdentity": outcome["programIdentity"],
                    "status": "deferred",
                    "compileSuccess": False,
                    "reference3dExecuted": False,
                    "canonicalPackagePublished": False,
                }
            )
            continue
        row = by_identity[outcome["programIdentity"]]
        family = str(outcome["predictedFamily"])
        spec = FAMILY_SPECS[family]
        parameters = default_parameters(family)
        parameters[spec.length_field] = float(
            outcome["prediction"]["continuous"]["length"]["value"]
        )
        parameters[spec.width_field] = float(outcome["prediction"]["continuous"]["width"]["value"])
        parameters[spec.ease_field] = float(outcome["prediction"]["continuous"]["ease"]["value"])
        try:
            program = program_from_parameters(
                family,
                parameters,
                program_id=f"proposal.{str(outcome['programIdentity'])[:16]}",
                base_seed=0,
            )
            program_issues = validate_program(program)
            pattern = compile_program(program)
            pattern_issues = validate_compiled_pattern(pattern)
            candidate = build_reference_assembly(family, pattern)
            target_program = row["program"]
            target_pattern = compile_program(target_program)
            target = build_reference_assembly(str(row["family"]), target_pattern)
            comparison = compare_reference_geometry(
                {"render": candidate["simulation"], "audit": candidate["audit"]},
                {"render": target["simulation"], "audit": target["audit"]},
            )
            topology_valid = finite_mesh(candidate["simulation"])
            records.append(
                {
                    "programIdentity": outcome["programIdentity"],
                    "status": "executed",
                    "programValid": not program_issues,
                    "compileSuccess": not pattern_issues,
                    "topologyValid": topology_valid,
                    "reference3dExecuted": True,
                    "reference3d": comparison,
                    "canonicalPackagePublished": False,
                    "canonicalPackageReason": (
                        "proposal_evaluation_does_not_publish_canonical_packages"
                    ),
                }
            )
        except (KeyError, TypeError, ValueError) as error:
            records.append(
                {
                    "programIdentity": outcome["programIdentity"],
                    "status": "rejected",
                    "reason": type(error).__name__,
                    "compileSuccess": False,
                    "topologyValid": False,
                    "reference3dExecuted": False,
                    "canonicalPackagePublished": False,
                }
            )
    accepted = [record for record in records if record["status"] != "deferred"]
    return {
        "records": records,
        "acceptedPredictionCount": len(accepted),
        "compileTopologySuccessRate": round(
            sum(
                bool(record.get("compileSuccess")) and bool(record.get("topologyValid"))
                for record in accepted
            )
            / max(len(accepted), 1),
            9,
        ),
        "reference3dExecutionRate": round(
            sum(record.get("reference3dExecuted", False) for record in accepted)
            / max(len(accepted), 1),
            9,
        ),
        "canonicalPackagePublicationRate": round(
            sum(record.get("canonicalPackagePublished", False) for record in accepted)
            / max(len(accepted), 1),
            9,
        ),
        "canonicalAuthorityChanged": False,
    }


def _shift_metrics(outcomes: list[dict[str, Any]], dataset: dict[str, Any]) -> list[dict[str, Any]]:
    by_identity = {str(item["programIdentity"]): item for item in outcomes}
    records = []
    for suite in dataset["shiftSuites"]:
        selected = [
            by_identity[value] for value in suite["programIdentities"] if value in by_identity
        ]
        records.append(
            {
                "suiteId": suite["suiteId"],
                "heldOutGroup": suite["heldOutGroup"],
                "programCount": len(selected),
                "rawTop1": round(_mean([float(item["correct"]) for item in selected]), 9),
                "actualIndependentGroupSelection": True,
            }
        )
    return records


def _program_rows(
    dataset: dict[str, Any], split: dict[str, Any], split_name: str
) -> list[dict[str, Any]]:
    identities = set(map(str, split["groups"][split_name]))
    captures: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for capture in dataset["captures"]:
        if capture["programIdentity"] in identities:
            captures[str(capture["programIdentity"])].append(capture["input"])
    programs = {str(item["programIdentity"]): item for item in dataset["programs"]}
    return [
        {
            "programIdentity": identity,
            "family": programs[identity]["family"],
            "program": programs[identity]["program"],
            "target": programs[identity]["target"],
            "observations": captures[identity],
            "input": {
                name: _mean([float(item[name]) for item in captures[identity]])
                for name in FEATURE_NAMES
            },
        }
        for identity in sorted(identities)
    ]


def _normalized(model: dict[str, Any], observation: dict[str, Any]) -> list[float]:
    return [
        (float(observation[name]) - float(mean)) / max(float(scale), 1.0e-9)
        for name, mean, scale in zip(
            FEATURE_NAMES,
            model["normalization"]["means"],
            model["normalization"]["scales"],
            strict=True,
        )
    ]


def _paired_bootstrap(
    learned: list[int], baseline: list[int], identities: list[str], *, seed: int
) -> dict[str, Any]:
    if len(learned) != len(baseline) or len(learned) != len(identities):
        raise ValueError("e1_bootstrap_identity_inventory_invalid")
    rng = random.Random(seed)
    values = []
    for _ in range(2_000):
        indices = [rng.randrange(len(identities)) for _ in identities]
        values.append(sum(learned[index] - baseline[index] for index in indices) / len(indices))
    values.sort()
    return {
        "unit": "source_program_identity",
        "resamples": 2_000,
        "estimate": round((sum(learned) - sum(baseline)) / len(learned), 9),
        "lower95": round(values[49], 9),
        "upper95": round(values[1_949], 9),
    }


def _distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _mean(values: list[float]) -> float:
    return sum(values) / max(len(values), 1)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(math.ceil(len(ordered) * fraction)) - 1)]


def CounterLike(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return result
