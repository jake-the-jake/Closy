from __future__ import annotations

from math import ceil, isfinite, sqrt
from pathlib import Path
from typing import Any

from closy_forge.solver_material_v1.common import digest, read_json, rounded
from closy_forge.solver_material_v1.estimator import (
    FIELD_ORDER,
    estimate_solver_fields,
    predict_observations,
)
from closy_forge.solver_material_v1.estimator_inputs import strip_truth_for_estimator
from closy_forge.solver_material_v1.forward_solver import FORWARD_SOLVER_VERSION
from closy_forge.solver_material_v1.production_solver import PRODUCTION_SOLVER_VERSION
from closy_forge.solver_material_v1.protocol import load_protocol

RESULT_VERSION = "closy.solver_material.retrospective_result.v1"
CORPUS_DIGEST = "200060cb27440b53ee823eecabe822e21bb540bc205d340c46f72c82f010f068"
ANCHORS = {
    "forwardSource": "e8568100257b4bea87ce831e1320371bf9354d3f",
    "corpusLock": "bbbc48aaf016ef704c4a43aede3cf337df81de40",
    "estimatorSource": "4835f9ce13dde54eb1aeaa6c68a35b05c4f361cb",
}
ESTIMATED_FIELDS = FIELD_ORDER[:6]
ABSTAINED_FIELDS = FIELD_ORDER[6:]


def evaluate_retrospective(corpus_path: Path) -> dict[str, Any]:
    protocol = load_protocol()
    corpus = read_json(corpus_path)
    _validate_corpus(corpus, protocol)
    bounds = {field: [0.0, 1.0] for field in FIELD_ORDER}
    rows: list[dict[str, Any]] = []
    all_estimated_errors: list[float] = []
    all_eight_errors: list[float] = []
    for source in [row for row in corpus["rows"] if row["partition"] == "locked_test"]:
        observations = strip_truth_for_estimator(source)
        estimate = estimate_solver_fields(observations, bounds, PRODUCTION_SOLVER_VERSION)
        field_errors = {
            field: abs(float(estimate["estimatedFields"][field]) - float(source["fields"][field]))
            / (bounds[field][1] - bounds[field][0])
            for field in ESTIMATED_FIELDS
        }
        abstained_errors = {
            field: abs(float(estimate["fixedPriorFields"][field]) - float(source["fields"][field]))
            for field in ABSTAINED_FIELDS
        }
        fitted = [row for row in observations if row["family"] in _fit_families()]
        predicted = predict_observations(estimate["estimatedFields"], fitted)
        residuals = [
            (prediction - float(observation["observable"]))
            / max(abs(float(observation["observable"])), 1e-4)
            for prediction, observation in zip(predicted, fitted, strict=True)
        ]
        reconstruction_nrmse = sqrt(sum(value * value for value in residuals) / len(residuals))
        estimated_values = list(field_errors.values())
        all_estimated_errors.extend(estimated_values)
        all_eight_errors.extend(estimated_values + list(abstained_errors.values()))
        rows.append(
            {
                "tupleId": source["tupleId"],
                "inputObservationIdentities": [
                    coupon["trajectoryDigest"] for coupon in source["coupons"]
                ],
                "estimates": estimate["estimatedFields"],
                "estimatedFieldErrors": {
                    field: rounded(value) for field, value in field_errors.items()
                },
                "abstainedFields": list(ABSTAINED_FIELDS),
                "abstainedFieldErrors": {
                    field: rounded(value) for field, value in abstained_errors.items()
                },
                "unsupportedCapability": {
                    "field": "compression_thickness",
                    "status": "unsupported",
                    "reason": protocol["unsupportedModes"]["compression_thickness"],
                },
                "meanSixFieldError": rounded(_mean(estimated_values)),
                "p95SixFieldError": rounded(_nearest_rank(estimated_values, 0.95)),
                "worstSixFieldError": rounded(max(estimated_values)),
                "predictiveNrmse": rounded(reconstruction_nrmse),
                "predictiveNrmseSemanticErratum": (
                    "same_observation_reconstruction_not_withheld_prediction"
                ),
                "jacobianRank": estimate["jacobianRank"],
                "conditionNumber": estimate["conditionNumber"],
                "singularValues": estimate["singularValues"],
                "normalizedJacobian": estimate["jacobian"],
                "terminalCategoryCounts": {"estimated": 6, "abstained": 2, "unsupported": 1},
                "failures": [],
            }
        )
    per_field = {
        field: _distribution(
            [float(row["estimatedFieldErrors"][field]) for row in rows],
            field,
        )
        for field in ESTIMATED_FIELDS
    }
    mean_error = _mean(all_estimated_errors)
    mean_reconstruction = _mean([float(row["predictiveNrmse"]) for row in rows])
    acceptance_rows = [
        {
            "predicate": "meanSixFieldNormalizedError",
            "status": "passed"
            if mean_error <= float(protocol["acceptance"]["maxMeanNormalizedFieldError"])
            else "failed",
            "observed": rounded(mean_error),
            "limit": protocol["acceptance"]["maxMeanNormalizedFieldError"],
        },
        {
            "predicate": "historicalPredictiveNrmse",
            "status": "passed"
            if mean_reconstruction <= float(protocol["acceptance"]["maxPrimaryPredictiveNrmse"])
            else "failed",
            "observed": rounded(mean_reconstruction),
            "limit": protocol["acceptance"]["maxPrimaryPredictiveNrmse"],
            "semanticErratum": "same_observation_reconstruction_not_withheld_prediction",
        },
        {
            "predicate": "jacobianRank",
            "status": "passed"
            if min(int(row["jacobianRank"]) for row in rows)
            >= int(protocol["acceptance"]["minJacobianRank"])
            else "failed",
            "observedMinimum": min(int(row["jacobianRank"]) for row in rows),
            "limit": protocol["acceptance"]["minJacobianRank"],
        },
        {
            "predicate": "conditionNumber",
            "status": "passed"
            if all(
                isinstance(row["conditionNumber"], float)
                and row["conditionNumber"] <= protocol["acceptance"]["maxConditionNumber"]
                for row in rows
            )
            else "failed",
            "limit": protocol["acceptance"]["maxConditionNumber"],
        },
        {
            "predicate": "negativeControlsMustDegrade",
            "status": "not_run_unsatisfied",
            "reason": "no_negative_controls_preregistered_before_test_exposure",
        },
    ]
    first_unmet = next(row["predicate"] for row in acceptance_rows if row["status"] != "passed")
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "resultVersion": RESULT_VERSION,
        "classification": "retrospective_contaminated_engineering_evaluation",
        "evidenceClass": "project_authored_same_author_correlated_scalar_solver_engineering",
        "anchors": ANCHORS,
        "protocolDigest": protocol["protocolDigest"],
        "corpusDigest": corpus["corpusDigest"],
        "denominators": {
            "tupleRows": 16,
            "estimatedFieldCells": 96,
            "abstainedFieldCells": 32,
            "unsupportedCapabilityCells": 16,
            "totalTerminalCells": 144,
            "droppedRows": 0,
        },
        "terminalConservation": {
            "estimated": 96,
            "abstained": 32,
            "unsupported": 16,
            "failed": 0,
            "nonFinite": 0,
            "timeout": 0,
            "divergent": 0,
            "sum": 144,
            "expected": 144,
            "conserved": True,
        },
        "aggregate": {
            "sixField": _distribution(all_estimated_errors, "all_estimated_fields"),
            "allEightFieldIncludingFixedPriorAbstentions": _distribution(
                all_eight_errors, "all_fields_including_abstentions"
            ),
            "meanHistoricalPredictiveNrmse": rounded(mean_reconstruction),
            "passingTupleCount": sum(
                row["meanSixFieldError"] <= protocol["acceptance"]["maxMeanNormalizedFieldError"]
                and row["predictiveNrmse"] <= protocol["acceptance"]["maxPrimaryPredictiveNrmse"]
                for row in rows
            ),
        },
        "perField": per_field,
        "rows": rows,
        "acceptancePredicates": acceptance_rows,
        "firstUnmetPredicate": first_unmet,
        "engineeringAcceptance": "failed" if first_unmet else "passed",
        "scientificQualification": "ineligible_test_exposed_before_estimator",
        "confidenceIntervals": "not_run",
        "realCouponCount": 0,
        "realFabricCalibration": "not_run",
        "budgetConsumption": {
            "scientificAttempt": False,
            "seed": False,
            "authority": False,
            "candidate": False,
            "topologyStrategy": False,
        },
    }
    result["resultDigest"] = digest(result)
    return result


def _validate_corpus(corpus: dict[str, Any], protocol: dict[str, Any]) -> None:
    if corpus.get("corpusDigest") != CORPUS_DIGEST:
        raise ValueError("corpus_lineage_digest_invalid")
    if corpus.get("protocolDigest") != protocol["protocolDigest"]:
        raise ValueError("protocol_lineage_digest_invalid")
    rows = corpus.get("rows")
    if not isinstance(rows, list):
        raise ValueError("corpus_rows_invalid")
    locked = [row for row in rows if row.get("partition") == "locked_test"]
    ids = [row.get("tupleId") for row in locked]
    if len(locked) != 16 or len(set(ids)) != 16:
        raise ValueError("locked_tuple_denominator_invalid")
    for row in locked:
        if set(row) != {
            "tupleId",
            "partition",
            "wholeMaterialHoldout",
            "fields",
            "coupons",
            "failures",
        }:
            raise ValueError("unexpected_truth_or_metadata_field")
        if set(row["fields"]) != set(FIELD_ORDER):
            raise ValueError("truth_field_set_invalid")
        if not all(isfinite(float(value)) for value in row["fields"].values()):
            raise ValueError("truth_field_non_finite")
        families = [coupon.get("family") for coupon in row["coupons"]]
        if len(families) != 10 or len(set(families)) != 10:
            raise ValueError("coupon_family_identity_invalid")
        if row["failures"]:
            raise ValueError("frozen_solver_failure_present")
        for coupon in row["coupons"]:
            if coupon.get("solverVersion") != FORWARD_SOLVER_VERSION:
                raise ValueError("forward_solver_version_invalid")
            if not isfinite(float(coupon.get("load", float("nan")))) or not isfinite(
                float(coupon.get("observable", float("nan")))
            ):
                raise ValueError("coupon_numeric_non_finite")
            if coupon.get("diagnostics", {}).get("finite") is not True:
                raise ValueError("coupon_divergent_or_non_finite")


def _fit_families() -> set[str]:
    return {
        "warp_tensile",
        "weft_tensile",
        "bias_shear",
        "cantilever_bend",
        "gravity_sag",
        "free_decay",
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, ceil(percentile * len(ordered)) - 1)]


def _distribution(values: list[float], label: str) -> dict[str, Any]:
    return {
        "label": label,
        "count": len(values),
        "mean": rounded(_mean(values)),
        "p95NearestRank": rounded(_nearest_rank(values, 0.95)),
        "worst": rounded(max(values)),
        "tiePolicy": "stable_field_then_tuple_order;nearest_rank_ceil",
    }
