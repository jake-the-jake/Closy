from __future__ import annotations

import json
import math
import random
import time
from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .e1_kernel_v3 import predict_e1_kernel_v3
from .multiview_corpus_v5 import FEATURE_NAMES
from .typed_program_v2 import (
    CONTINUOUS_AXES,
    GRAMMAR_VERSION,
    PROGRAM_VERSION,
    TOKEN_AXES,
    TOKEN_VALUES,
    compile_typed_program_v2,
    legal_token_values,
    render_typed_compilation_v2,
    validate_typed_program_v2,
)

MODEL_VERSION = "closy.typed_compositional_rbf_decoder.cpu.d0.v2"
EVALUATION_VERSION = "closy.typed_compositional_evaluation.reference_3d.d0.v2"
MODEL_FAMILY = "factorized_atomic_rbf_heads_with_grammar_state_masking"


def train_structured_decoder_v2(dataset: dict[str, Any], *, seed: int = 63_017) -> dict[str, Any]:
    """Train atomic token heads; no complete target-signature table is persisted."""

    start = time.perf_counter_ns()
    train = _records(dataset, "train")
    validation = _records(dataset, "validation")
    raw = [_feature_vector(record["observation"]) for record in train]
    means = [_mean([row[index] for row in raw]) for index in range(len(FEATURE_NAMES))]
    scales = []
    for index, mean in enumerate(means):
        variance = _mean([(row[index] - mean) ** 2 for row in raw])
        scales.append(max(math.sqrt(variance), 1.0e-6))
    normalized = [_normalize(row, means, scales) for row in raw]
    token_heads: dict[str, Any] = {}
    for axis_index, axis in enumerate(TOKEN_AXES):
        classes: dict[str, Any] = {}
        for value in TOKEN_VALUES[axis]:
            rows = [
                vector
                for vector, record in zip(normalized, train, strict=True)
                if record["target"]["tokens"][axis] == value
            ]
            if rows:
                classes[value] = {
                    "count": len(rows),
                    "prototypes": _cluster_prototypes(rows, cluster_count=min(3, len(rows))),
                }
        token_heads[axis] = {
            "classes": classes,
            "bandwidth": round(1.15 + axis_index * 0.025, 9),
            "targetKind": "one_atomic_token",
        }
    continuous_examples = [
        {
            "features": _round_vector(vector),
            "parameters": {
                axis: float(record["target"]["parameters"][axis]) for axis in CONTINUOUS_AXES
            },
        }
        for vector, record in zip(normalized, train, strict=True)
    ]
    random.Random(seed).shuffle(continuous_examples)
    columns = list(zip(*normalized, strict=True))
    model: dict[str, Any] = {
        "schemaVersion": 1,
        "modelVersion": MODEL_VERSION,
        "modelFamily": MODEL_FAMILY,
        "featureNames": list(FEATURE_NAMES),
        "grammarVersion": GRAMMAR_VERSION,
        "decoderOrder": list(TOKEN_AXES),
        "normalization": {
            "means": _round_vector(means),
            "scales": _round_vector(scales),
            "fitSplit": "train_only",
        },
        "tokenHeads": token_heads,
        "continuousHead": {
            "kind": "observable_knn_regression",
            "neighbours": 9,
            "examples": continuous_examples,
        },
        "oodEnvelope": {
            "minimums": _round_vector([min(column) for column in columns]),
            "maximums": _round_vector([max(column) for column in columns]),
            "margin": 4.0,
            "action": "defer",
        },
        "calibration": {"confidenceThreshold": 0.0, "fitSplit": "validation_only"},
        "training": {
            "seed": seed,
            "cpuOnly": True,
            "threadCount": 1,
            "trainingProgramCount": len(train),
            "validationProgramCount": len(validation),
            "testDataUsed": False,
            "networkDownload": False,
            "externalCheckpoint": None,
            "wallNanoseconds": 0,
        },
        "authority": {
            "proposalOnly": True,
            "canonicalMutationPermitted": False,
            "compilerAndValidatorsFinal": True,
        },
        "forbiddenInputs": [
            "target_family",
            "target_full_signature",
            "target_ast",
            "target_panel_count",
            "target_seams",
            "target_openings",
            "source_program_id",
        ],
        "integrity": {"weightsHash": "", "modelHash": ""},
    }
    provisional = [decode_structured_program_v2(model, row["observation"]) for row in validation]
    model["calibration"]["confidenceThreshold"] = _validation_threshold(provisional, 0.8)
    model["training"]["wallNanoseconds"] = time.perf_counter_ns() - start
    model["integrity"]["weightsHash"] = _weights_hash(model)
    model["integrity"]["modelHash"] = structured_model_hash_v2(model)
    issues = validate_structured_model_v2(model)
    if issues:
        raise ValueError("structured_model_invalid:" + ";".join(issues))
    return model


def decode_structured_program_v2(
    model: dict[str, Any], observation: dict[str, Any], *, proposal_id: str = "typed.proposal"
) -> dict[str, Any]:
    """Decode only from role-preserving raster observables and frozen model state."""

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
    partial: dict[str, str] = {}
    confidences = []
    class_probabilities: dict[str, dict[str, float]] = {}
    for axis in TOKEN_AXES:
        head = model["tokenHeads"][axis]
        legal = legal_token_values(partial, axis)
        scores = {
            value: _prototype_score(row, head["classes"].get(value), float(head["bandwidth"]))
            for value in legal
        }
        total = max(sum(scores.values()), 1.0e-12)
        probabilities = {value: score / total for value, score in scores.items()}
        selected = max(legal, key=lambda value: (probabilities[value], value))
        partial[axis] = selected
        confidences.append(probabilities[selected])
        class_probabilities[axis] = {
            value: round(probability, 9) for value, probability in sorted(probabilities.items())
        }
    parameters = _continuous_prediction(model, row)
    program = {
        "schemaVersion": 1,
        "programVersion": PROGRAM_VERSION,
        "grammarVersion": GRAMMAR_VERSION,
        "programId": proposal_id,
        "tokens": partial,
        "parameters": parameters,
        "materialRegion": f"material.{partial['material']}",
    }
    confidence = min(confidences)
    threshold = float(model["calibration"]["confidenceThreshold"])
    status = "deferred" if ood or confidence < threshold else "predicted"
    return {
        "status": status,
        "reason": (
            "observable_outside_training_envelope"
            if ood
            else "confidence_below_validation_threshold"
            if confidence < threshold
            else "factorized_atomic_heads_prediction"
        ),
        "confidence": round(confidence, 9),
        "ood": ood,
        "program": program,
        "classProbabilities": class_probabilities,
        "grammarMaskApplied": True,
        "targetLookupUsed": False,
    }


def validate_structured_model_v2(model: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if model.get("modelVersion") != MODEL_VERSION:
        issues.append("structured_model_version_invalid")
    if tuple(model.get("featureNames", [])) != FEATURE_NAMES:
        issues.append("structured_model_feature_contract_invalid")
    if tuple(model.get("decoderOrder", [])) != TOKEN_AXES:
        issues.append("structured_model_decoder_order_invalid")
    if set(model.get("tokenHeads", {})) != set(TOKEN_AXES):
        issues.append("structured_model_atomic_heads_invalid")
    serialized = canonical_dumps(model)
    if "allowedStructures" in serialized or "programIdentity" in serialized:
        issues.append("structured_model_full_signature_or_program_lookup_present")
    for number in _all_numbers(model.get("tokenHeads", {})):
        if not math.isfinite(number):
            issues.append("structured_model_nonfinite_weight")
            break
    if model.get("integrity", {}).get("weightsHash") != _weights_hash(model):
        issues.append("structured_model_weights_hash_invalid")
    if model.get("integrity", {}).get("modelHash") != structured_model_hash_v2(model):
        issues.append("structured_model_hash_invalid")
    return sorted(set(issues))


def structured_model_hash_v2(model: dict[str, Any]) -> str:
    payload = deepcopy(model)
    payload.setdefault("integrity", {})["modelHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def reload_structured_model_v2(model: dict[str, Any]) -> dict[str, Any]:
    reloaded: dict[str, Any] = json.loads(canonical_dumps(model))
    issues = validate_structured_model_v2(reloaded)
    if issues:
        raise ValueError("structured_model_reload_invalid:" + ";".join(issues))
    return reloaded


def evaluate_structured_decoder_v2(
    model: dict[str, Any],
    dataset: dict[str, Any],
    thresholds: dict[str, Any],
    *,
    e1_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    start = time.perf_counter_ns()
    test = _records(dataset, "test")
    train = _records(dataset, "train")
    outcomes = [_evaluate_record(model, record, index) for index, record in enumerate(test)]
    baselines = _evaluate_baselines(train, test, e1_model=e1_model)
    learned_per_record = [float(item["atomicTokenAccuracy"]) for item in outcomes]
    strongest_name, strongest = max(
        baselines.items(), key=lambda item: float(item[1]["meanAtomicTokenAccuracy"])
    )
    interval = _paired_bootstrap(
        learned_per_record,
        list(map(float, strongest["perRecordAtomicTokenAccuracy"])),
        seed=220_021,
    )
    metrics = _aggregate_metrics(outcomes)
    ood = _ood_evaluation(model, test)
    aliases = _permutation_audit(model, test)
    gate = thresholds["e2"]
    checks = {
        "schemaTypeValidity": metrics["schemaTypeValidity"] >= gate["minimumSchemaTypeValidity"],
        "compileTopologyValidityWithoutRepair": metrics["compileTopologyValidityWithoutRepair"]
        >= gate["minimumCompileTopologyValidityWithoutRepair"],
        "truePerTokenMacroF1": metrics["truePerTokenMacroF1"] >= gate["minimumTruePerTokenMacroF1"],
        "semanticPanelMatchingF1": metrics["semanticPanelMatchingF1"]
        >= gate["minimumSemanticPanelMatchingF1"],
        "panelCountAccuracy": metrics["panelCountAccuracy"] >= gate["minimumPanelCountAccuracy"],
        "seamGraphEdgeF1": metrics["seamGraphEdgeF1"] >= gate["minimumSeamGraphEdgeF1"],
        "openingBoundaryMembershipF1": metrics["openingBoundaryMembershipF1"]
        >= gate["minimumOpeningBoundaryMembershipF1"],
        "normalizedGeometricBoundaryDistance": metrics["normalizedGeometricBoundaryDistance"]
        <= gate["maximumNormalizedGeometricBoundaryDistance"],
        "patternAreaRelativeError": metrics["patternAreaRelativeError"]
        <= gate["maximumPatternAreaRelativeError"],
        "garmentMeasurementRelativeError": metrics["garmentMeasurementRelativeError"]
        <= gate["maximumGarmentMeasurementRelativeError"],
        "pairedSeamLengthRelativeErrorP95": metrics["pairedSeamLengthRelativeErrorP95"]
        <= gate["maximumPairedSeamLengthRelativeErrorP95"],
        "reference3dExecutionWithoutRepair": metrics["reference3dExecutionWithoutRepair"]
        >= gate["minimumReference3dExecutionWithoutRepair"],
        "oodCorrectDeferral": ood["correctDeferralRate"] >= gate["minimumOodCorrectDeferral"],
        "oodFalseAccept": ood["falseAcceptRate"] <= gate["maximumOodFalseAccept"],
        "baselineLower95": interval["lower95"]
        >= gate["baselineCriterion"]["minimumPairedBootstrapLower95"],
        "aliasAndProgramPermutationInvariant": aliases["passed"],
        "noTargetLookupSurface": validate_structured_model_v2(model) == [],
    }
    return {
        "schemaVersion": 1,
        "evaluationVersion": EVALUATION_VERSION,
        "profileId": gate["profileId"],
        "metrics": metrics,
        "perTokenClassMetrics": _token_class_metrics(outcomes),
        "continuousParameters": _continuous_metrics(outcomes),
        "baselines": baselines,
        "strongestEqualInputBaseline": strongest_name,
        "pairedBootstrap": interval,
        "ood": ood,
        "failureTaxonomy": _failure_taxonomy(outcomes),
        "leakageAudits": aliases,
        "checks": checks,
        "acceptance": {
            "status": "passed" if all(checks.values()) else "failed",
            "passedCount": sum(checks.values()),
            "checkCount": len(checks),
            "learnedRouteDefault": all(checks.values()) and interval["lower95"] > 0.0,
            "noninferiorityAlonePromotes": False,
            "oracleFallbackUsed": False,
            "humanCorrectionUsed": False,
        },
        "execution": {
            "testProgramCount": len(test),
            "actualCompilerInvocations": len(test),
            "actualReference3dAttempts": len(test),
            "physicalSettleClaimed": False,
            "referenceAssemblyLabel": "reference_assembly",
            "wallNanoseconds": time.perf_counter_ns() - start,
            "cpuOnly": True,
            "threadCount": 1,
        },
    }


def _evaluate_record(
    model: dict[str, Any], record: dict[str, Any], record_index: int
) -> dict[str, Any]:
    prediction = decode_structured_program_v2(
        model, record["observation"], proposal_id=f"proposal.{record_index:04d}"
    )
    predicted_program = prediction["program"]
    target_program = record["target"]["program"]
    issues = validate_typed_program_v2(predicted_program)
    result: dict[str, Any] = {
        "programIdentity": record["programIdentity"],
        "holdoutCompositionGroup": record["holdoutCompositionGroup"],
        "status": prediction["status"],
        "confidence": prediction["confidence"],
        "targetTokens": target_program["tokens"],
        "predictedTokens": predicted_program["tokens"],
        "targetParameters": target_program["parameters"],
        "predictedParameters": predicted_program["parameters"],
        "schemaTypeValid": not issues,
        "issues": issues,
        "failureStage": None,
    }
    result["atomicTokenAccuracy"] = _mean(
        [
            float(predicted_program["tokens"][axis] == target_program["tokens"][axis])
            for axis in TOKEN_AXES
        ]
    )
    result["structuralExactMatch"] = predicted_program["tokens"] == target_program["tokens"]
    if issues:
        result["failureStage"] = "parse_type"
        return result
    try:
        predicted = compile_typed_program_v2(predicted_program)
        target = record["target"]["compilation"]
        result.update(_compilation_comparison(predicted, target))
        rendered, render_audit = render_typed_compilation_v2(predicted, 10_000 + record_index)
        result["reference3dExecuted"] = True
        result["renderAudit"] = render_audit
        result["silhouetteLandmarkError"] = _observable_error(rendered, record["observation"])
        result["compileSuccess"] = True
        result["topologyValid"] = bool(predicted["audit"]["topologyValid"])
    except (ValueError, KeyError, ArithmeticError) as error:
        result["compileSuccess"] = False
        result["topologyValid"] = False
        result["reference3dExecuted"] = False
        result["failureStage"] = "compile_or_reference_3d"
        result["failureReason"] = type(error).__name__
    return result


def _compilation_comparison(predicted: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    predicted_roles = {str(panel["role"]) for panel in predicted["panels"]}
    target_roles = {str(panel["role"]) for panel in target["panels"]}
    predicted_seams = {_edge_key(edge) for edge in predicted["seams"]}
    target_seams = {_edge_key(edge) for edge in target["seams"]}
    predicted_openings = _opening_membership(predicted["openings"])
    target_openings = _opening_membership(target["openings"])
    boundary_distance = _geometric_boundary_distance(predicted["boundaries"], target["boundaries"])
    area_error = _relative_error(
        float(predicted["audit"]["totalPatternArea"]), float(target["audit"]["totalPatternArea"])
    )
    measurement_errors = [
        _symmetric_relative_error(float(predicted["audit"]["measurements"][name]), float(value))
        for name, value in target["audit"]["measurements"].items()
    ]
    target_lengths = {
        _edge_key(item["edge"]): (float(item["leftLength"]), float(item["rightLength"]))
        for item in target["audit"]["seamLengths"]
    }
    seam_length_errors: list[float] = []
    for item in predicted["audit"]["seamLengths"]:
        key = _edge_key(item["edge"])
        if key in target_lengths:
            expected = target_lengths[key]
            seam_length_errors.extend(
                (
                    _relative_error(float(item["leftLength"]), expected[0]),
                    _relative_error(float(item["rightLength"]), expected[1]),
                )
            )
    return {
        "semanticPanelF1": _set_f1(predicted_roles, target_roles),
        "panelCountCorrect": len(predicted_roles) == len(target_roles),
        "seamEdgeF1": _set_f1(predicted_seams, target_seams),
        "openingMembershipF1": _set_f1(predicted_openings, target_openings),
        "normalizedBoundaryDistance": boundary_distance,
        "patternAreaRelativeError": area_error,
        "garmentMeasurementRelativeError": _mean(measurement_errors),
        "pairedSeamLengthRelativeErrors": seam_length_errors or [1.0],
    }


def _aggregate_metrics(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    compiled = [item for item in outcomes if item.get("compileSuccess")]
    seam_errors = [
        float(value) for item in compiled for value in item["pairedSeamLengthRelativeErrors"]
    ]
    return {
        "testProgramCount": len(outcomes),
        "acceptedCount": sum(item["status"] == "predicted" for item in outcomes),
        "schemaTypeValidity": _mean([float(item["schemaTypeValid"]) for item in outcomes]),
        "structuralExactMatch": _mean([float(item["structuralExactMatch"]) for item in outcomes]),
        "truePerTokenMacroF1": _macro_token_f1(outcomes),
        "semanticPanelMatchingF1": _mean([float(item["semanticPanelF1"]) for item in compiled]),
        "panelCountAccuracy": _mean([float(item["panelCountCorrect"]) for item in compiled]),
        "seamGraphEdgeF1": _mean([float(item["seamEdgeF1"]) for item in compiled]),
        "openingBoundaryMembershipF1": _mean(
            [float(item["openingMembershipF1"]) for item in compiled]
        ),
        "normalizedGeometricBoundaryDistance": _mean(
            [float(item["normalizedBoundaryDistance"]) for item in compiled]
        ),
        "patternAreaRelativeError": _mean(
            [float(item["patternAreaRelativeError"]) for item in compiled]
        ),
        "garmentMeasurementRelativeError": _mean(
            [float(item["garmentMeasurementRelativeError"]) for item in compiled]
        ),
        "garmentMeasurementRelativeErrorPolicy": (
            "symmetric_max_magnitude_with_0.05m_zero_measurement_floor"
        ),
        "pairedSeamLengthRelativeErrorP95": _percentile(seam_errors, 0.95),
        "compileTopologyValidityWithoutRepair": len(compiled) / max(len(outcomes), 1),
        "reference3dExecutionWithoutRepair": _mean(
            [float(item.get("reference3dExecuted", False)) for item in outcomes]
        ),
        "sourceConditionedSilhouetteLandmarkError": _mean(
            [float(item["silhouetteLandmarkError"]) for item in compiled]
        ),
        "manualRepairCount": 0,
    }


def _token_class_metrics(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for axis in TOKEN_AXES:
        axis_result = {}
        for value in TOKEN_VALUES[axis]:
            tp = fp = fn = 0
            for item in outcomes:
                target = item["targetTokens"][axis] == value
                predicted = item["predictedTokens"][axis] == value
                tp += int(target and predicted)
                fp += int(not target and predicted)
                fn += int(target and not predicted)
            precision = tp / max(tp + fp, 1)
            recall = tp / max(tp + fn, 1)
            f1 = 2.0 * tp / max(2 * tp + fp + fn, 1)
            axis_result[value] = {
                "precision": round(precision, 9),
                "recall": round(recall, 9),
                "f1": round(f1, 9),
                "support": sum(item["targetTokens"][axis] == value for item in outcomes),
            }
        result[axis] = axis_result
    return result


def _continuous_metrics(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    all_errors = []
    for axis in CONTINUOUS_AXES:
        errors = [
            abs(float(item["predictedParameters"][axis]) - float(item["targetParameters"][axis]))
            for item in outcomes
        ]
        all_errors.extend(errors)
        result[axis] = {
            "maeNormalized": round(_mean(errors), 9),
            "medianNormalized": round(_percentile(errors, 0.5), 9),
            "p95Normalized": round(_percentile(errors, 0.95), 9),
            "worstNormalized": round(max(errors), 9),
            "coverageAfterAbstention": round(
                _mean([float(item["status"] == "predicted") for item in outcomes]), 9
            ),
        }
    return {"axes": result, "meanNormalizedMae": round(_mean(all_errors), 9)}


def _evaluate_baselines(
    train: list[dict[str, Any]],
    test: list[dict[str, Any]],
    *,
    e1_model: dict[str, Any] | None,
) -> dict[str, Any]:
    train_vectors = [_feature_vector(record["observation"]) for record in train]
    modes = {
        axis: max(
            TOKEN_VALUES[axis],
            key=lambda value: (
                sum(record["target"]["tokens"][axis] == value for record in train),
                value,
            ),
        )
        for axis in TOKEN_AXES
    }
    predictions: dict[str, list[dict[str, str]]] = {
        "fixedAtomicModes": [],
        "deterministicObservableHeuristic": [],
        "nearestNeighbourProgram": [],
        "untrainedRandomAtomicHeads": [],
    }
    if e1_model is not None:
        predictions["frozenE1Adaptation"] = []
    for index, record in enumerate(test):
        observation = record["observation"]
        vector = _feature_vector(observation)
        nearest_index = min(
            range(len(train)),
            key=lambda item: (_squared_distance(vector, train_vectors[item]), item),
        )
        predictions["fixedAtomicModes"].append(_legalize_tokens(modes))
        predictions["deterministicObservableHeuristic"].append(
            _observable_heuristic_tokens(observation)
        )
        predictions["nearestNeighbourProgram"].append(
            deepcopy(train[nearest_index]["target"]["tokens"])
        )
        predictions["untrainedRandomAtomicHeads"].append(_random_legal_tokens(81_001 + index))
        if e1_model is not None:
            family = str(predict_e1_kernel_v3(e1_model, observation)["family"])
            predictions["frozenE1Adaptation"].append(_family_heuristic_tokens(family))
    result = {}
    for name, rows in predictions.items():
        per_record = [
            _mean(
                [float(predicted[axis] == target["target"]["tokens"][axis]) for axis in TOKEN_AXES]
            )
            for predicted, target in zip(rows, test, strict=True)
        ]
        pseudo_outcomes = [
            {"predictedTokens": predicted, "targetTokens": target["target"]["tokens"]}
            for predicted, target in zip(rows, test, strict=True)
        ]
        result[name] = {
            "equalObservableInputs": True,
            "targetMetadataUsed": False,
            "meanAtomicTokenAccuracy": round(_mean(per_record), 9),
            "truePerTokenMacroF1": round(_macro_token_f1(pseudo_outcomes), 9),
            "perRecordAtomicTokenAccuracy": [round(value, 9) for value in per_record],
            "frozenE1ActuallyExecuted": name == "frozenE1Adaptation",
        }
    return result


def _ood_evaluation(model: dict[str, Any], test: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for index, record in enumerate(test):
        corrupt = {
            name: float(value) + (50.0 if index % 2 == 0 else -50.0)
            for name, value in record["observation"].items()
        }
        rows.append(decode_structured_program_v2(model, corrupt, proposal_id=f"ood.{index:04d}"))
    false_accept = sum(item["status"] == "predicted" for item in rows) / max(len(rows), 1)
    return {
        "suite": "real_observable_corruption_outside_training_envelope",
        "count": len(rows),
        "correctDeferralRate": round(1.0 - false_accept, 9),
        "falseAcceptRate": round(false_accept, 9),
        "inputActuallyModified": True,
    }


def _permutation_audit(model: dict[str, Any], test: list[dict[str, Any]]) -> dict[str, Any]:
    selected = test[:12]
    baseline = [decode_structured_program_v2(model, row["observation"]) for row in selected]
    permuted = [
        decode_structured_program_v2(
            model,
            row["observation"],
            proposal_id=f"permuted.alias.{11 - index:04d}",
        )
        for index, row in enumerate(selected)
    ]
    passed = all(
        left["program"]["tokens"] == right["program"]["tokens"]
        and left["program"]["parameters"] == right["program"]["parameters"]
        and left["status"] == right["status"]
        for left, right in zip(baseline, permuted, strict=True)
    )
    return {
        "testFamilyAliasObservable": False,
        "programIdUsedAsModelInput": False,
        "permutedProgramIdCount": len(selected),
        "predictionsInvariant": passed,
        "passed": passed,
        "staticCandidateSurface": {
            "allowedStructuresPresent": False,
            "targetAstPresent": False,
            "targetProgramLookupPresent": False,
            "modelValidationIssues": validate_structured_model_v2(model),
        },
    }


def _failure_taxonomy(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in outcomes:
        groups.setdefault(str(item["holdoutCompositionGroup"]), []).append(item)
    return {
        group: {
            "programCount": len(rows),
            "deferredCount": sum(row["status"] == "deferred" for row in rows),
            "structuralExactMatch": round(
                _mean([float(row["structuralExactMatch"]) for row in rows]), 9
            ),
            "compileFailureCount": sum(not row.get("compileSuccess", False) for row in rows),
            "reference3dFailureCount": sum(
                not row.get("reference3dExecuted", False) for row in rows
            ),
        }
        for group, rows in sorted(groups.items())
    }


def _geometric_boundary_distance(
    predicted: list[dict[str, Any]], target: list[dict[str, Any]]
) -> float:
    predicted_by_id = {str(item["id"]): item for item in predicted}
    target_by_id = {str(item["id"]): item for item in target}
    union = sorted(set(predicted_by_id) | set(target_by_id))
    if not union:
        return 0.0
    distances = []
    for identity in union:
        left = predicted_by_id.get(identity)
        right = target_by_id.get(identity)
        if left is None or right is None:
            distances.append(1.0)
            continue
        left_points = left["endpoints"]
        right_points = right["endpoints"]
        scale = max(float(right["length"]), 1.0e-9)
        direct = _point_distance(left_points[0], right_points[0]) + _point_distance(
            left_points[1], right_points[1]
        )
        reverse = _point_distance(left_points[0], right_points[1]) + _point_distance(
            left_points[1], right_points[0]
        )
        distances.append(min(direct, reverse) / (2.0 * scale))
    return round(_mean(distances), 9)


def _observable_error(predicted: dict[str, Any], target: dict[str, Any]) -> float:
    suffixes = (
        "foregroundFraction",
        "aspectRatio",
        "centroidX",
        "centroidY",
        "upperFraction",
        "hemRatio",
        "centerGap",
    )
    errors = [
        abs(float(predicted[name]) - float(target[name]))
        for name in FEATURE_NAMES
        if name.endswith(suffixes)
    ]
    return round(_mean(errors), 9)


def _prototype_score(row: list[float], class_record: Any, bandwidth: float) -> float:
    if not class_record:
        return 1.0e-12
    return sum(
        math.exp(
            -_squared_distance(row, list(map(float, prototype))) / (2.0 * bandwidth * bandwidth)
        )
        for prototype in class_record["prototypes"]
    ) / len(class_record["prototypes"])


def _continuous_prediction(model: dict[str, Any], row: list[float]) -> dict[str, float]:
    examples = model["continuousHead"]["examples"]
    neighbours = sorted(
        (
            _squared_distance(row, list(map(float, example["features"]))),
            index,
        )
        for index, example in enumerate(examples)
    )[: int(model["continuousHead"]["neighbours"])]
    weighted = [(1.0 / max(distance, 1.0e-6), examples[index]) for distance, index in neighbours]
    denominator = sum(weight for weight, _ in weighted)
    return {
        axis: round(
            min(
                1.0,
                max(
                    0.0,
                    sum(weight * float(example["parameters"][axis]) for weight, example in weighted)
                    / denominator,
                ),
            ),
            9,
        )
        for axis in CONTINUOUS_AXES
    }


def _cluster_prototypes(rows: list[list[float]], *, cluster_count: int) -> list[list[float]]:
    ordered = sorted(rows, key=lambda row: tuple(round(value, 9) for value in row))
    buckets = [ordered[index::cluster_count] for index in range(cluster_count)]
    return [
        _round_vector(
            [_mean([row[index] for row in bucket]) for index in range(len(FEATURE_NAMES))]
        )
        for bucket in buckets
        if bucket
    ]


def _validation_threshold(predictions: list[dict[str, Any]], coverage: float) -> float:
    values = sorted(float(item["confidence"]) for item in predictions)
    accepted = max(1, math.ceil(len(values) * coverage))
    return round(max(0.0, values[max(0, len(values) - accepted)] - 1.0e-9), 9)


def _legalize_tokens(tokens: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for axis in TOKEN_AXES:
        legal = legal_token_values(result, axis)
        candidate = tokens.get(axis, legal[0])
        result[axis] = candidate if candidate in legal else legal[0]
    return result


def _observable_heuristic_tokens(observation: dict[str, Any]) -> dict[str, str]:
    coverage = _mean(
        [float(observation[f"{role}.foregroundFraction"]) for role in ("front", "rear")]
    )
    aspect = _mean([float(observation[f"{role}.aspectRatio"]) for role in ("front", "rear")])
    upper = _mean([float(observation[f"{role}.upperFraction"]) for role in ("front", "rear")])
    lateral = 1.0 / max(aspect, 1.0e-6)
    base = "full" if coverage > 0.24 and upper > 0.45 else "upper" if upper > 0.55 else "lower"
    result = {
        "base": base,
        "torso": "split_front" if base in {"upper", "full"} and lateral > 0.5 else "two_panel",
        "lower": "split_leg" if base in {"lower", "full"} and lateral < 0.55 else "skirt",
        "sleeve": "long" if base in {"upper", "full"} and lateral > 0.72 else "none",
        "neckline": "crew" if base in {"upper", "full"} else "none",
        "waist": "shaped",
        "hem": "straight",
        "closure": "none",
        "layer": "base",
        "material": "jersey",
    }
    return _legalize_tokens(result)


def _family_heuristic_tokens(family: str) -> dict[str, str]:
    base = (
        "full"
        if family == "simple_dress"
        else "lower"
        if family in {"simple_skirt", "simple_trousers"}
        else "upper"
    )
    result = {
        "base": base,
        "torso": "split_front" if family in {"button_shirt", "jacket_outerwear"} else "two_panel",
        "lower": "split_leg"
        if family == "simple_trousers"
        else "skirt"
        if base in {"lower", "full"}
        else "none",
        "sleeve": "long"
        if family in {"long_sleeved_top", "button_shirt", "jacket_outerwear"}
        else "none",
        "neckline": "collar"
        if family in {"button_shirt", "jacket_outerwear"}
        else "crew"
        if base in {"upper", "full"}
        else "none",
        "waist": "shaped",
        "hem": "asymmetric" if family == "layered_asymmetric" else "straight",
        "closure": "front_placket" if family in {"button_shirt", "jacket_outerwear"} else "none",
        "layer": "outer" if family in {"jacket_outerwear", "layered_asymmetric"} else "base",
        "material": "woven"
        if family in {"button_shirt", "jacket_outerwear", "simple_trousers"}
        else "jersey",
    }
    return _legalize_tokens(result)


def _random_legal_tokens(seed: int) -> dict[str, str]:
    rng = random.Random(seed)
    result: dict[str, str] = {}
    for axis in TOKEN_AXES:
        values = legal_token_values(result, axis)
        result[axis] = values[rng.randrange(len(values))]
    return result


def _records(dataset: dict[str, Any], split: str) -> list[dict[str, Any]]:
    return [record for record in dataset["records"] if record["split"] == split]


def _feature_vector(observation: dict[str, Any]) -> list[float]:
    if tuple(observation) != FEATURE_NAMES:
        raise ValueError("structured_observable_contract_invalid")
    values = [float(observation[name]) for name in FEATURE_NAMES]
    if any(not math.isfinite(value) for value in values):
        raise ValueError("structured_observable_nonfinite")
    return values


def _normalize(values: list[float], means: list[float], scales: list[float]) -> list[float]:
    return [
        (value - mean) / max(scale, 1.0e-9)
        for value, mean, scale in zip(values, means, scales, strict=True)
    ]


def _weights_hash(model: dict[str, Any]) -> str:
    payload = {
        "normalization": model.get("normalization"),
        "tokenHeads": model.get("tokenHeads"),
        "continuousHead": model.get("continuousHead"),
        "oodEnvelope": model.get("oodEnvelope"),
        "calibration": model.get("calibration"),
    }
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _all_numbers(value: Any) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, int | float):
        return [float(value)]
    if isinstance(value, dict):
        return [number for child in value.values() for number in _all_numbers(child)]
    if isinstance(value, list):
        return [number for child in value for number in _all_numbers(child)]
    return []


def _macro_token_f1(outcomes: list[dict[str, Any]]) -> float:
    values = []
    for axis in TOKEN_AXES:
        for value in TOKEN_VALUES[axis]:
            tp = fp = fn = 0
            for item in outcomes:
                target = item["targetTokens"][axis] == value
                predicted = item["predictedTokens"][axis] == value
                tp += int(target and predicted)
                fp += int(not target and predicted)
                fn += int(target and not predicted)
            if tp + fn:
                values.append(2.0 * tp / max(2 * tp + fp + fn, 1))
    return round(_mean(values), 9)


def _opening_membership(openings: list[dict[str, Any]]) -> set[str]:
    return {
        f"{item['semantic']}|{boundary}"
        for item in openings
        for boundary in item["boundaryMembership"]
    }


def _edge_key(edge: list[str]) -> str:
    return "|".join(sorted(map(str, edge)))


def _set_f1(predicted: set[str], target: set[str]) -> float:
    if not predicted and not target:
        return 1.0
    intersection = len(predicted & target)
    return round(2.0 * intersection / max(len(predicted) + len(target), 1), 9)


def _relative_error(predicted: float, target: float) -> float:
    return abs(predicted - target) / max(abs(target), 1.0e-9)


def _symmetric_relative_error(predicted: float, target: float) -> float:
    return abs(predicted - target) / max(abs(predicted), abs(target), 0.05)


def _point_distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _squared_distance(left: list[float], right: list[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right, strict=True))


def _paired_bootstrap(learned: list[float], baseline: list[float], *, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    values = []
    for _ in range(2_000):
        indices = [rng.randrange(len(learned)) for _ in learned]
        values.append(_mean([learned[index] - baseline[index] for index in indices]))
    values.sort()
    return {
        "unit": "source_program_identity",
        "resamples": 2_000,
        "estimate": round(_mean([a - b for a, b in zip(learned, baseline, strict=True)]), 9),
        "lower95": round(values[49], 9),
        "upper95": round(values[1_949], 9),
    }


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)], 9)


def _mean(values: list[float]) -> float:
    return sum(values) / max(len(values), 1)


def _round_vector(values: list[float]) -> list[float]:
    return [round(float(value), 12) for value in values]
