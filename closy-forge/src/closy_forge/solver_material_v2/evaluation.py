from __future__ import annotations

import json
from collections import defaultdict
from math import sqrt
from pathlib import Path
from typing import Any

from closy_forge.capture_reconstruction_v2.safe_private_io import SafePrivateRoot

from .common import canonical_bytes, canonical_digest, nearest_rank, read_json, rounded, write_json
from .units import FIELD_ORDER, SIX_FIELD_ORDER

RESULT_LITERAL_FAILED = "source_guarded_synthetic_solver_material_v2_failed"
RESULT_LITERAL_PASSED = "source_guarded_synthetic_solver_material_v2_passed"


def run_locked_evaluation_once(
    protocol: dict[str, Any],
    public_root: Path,
    private_root: Path,
    contestant_output: dict[str, Any],
    *,
    envelope_path: Path,
    disclosure_path: Path,
    source_freeze: dict[str, Any],
    development_studies: dict[str, Any],
) -> dict[str, Any]:
    if envelope_path.exists() or disclosure_path.exists():
        raise ValueError("canonical_solver_material_v2_evaluation_already_published")
    commitments = read_json(public_root / "truth_commitments.json")
    with SafePrivateRoot(private_root) as private:
        if "consumed.json" in private.list_names():
            raise ValueError("canonical_solver_material_v2_evaluation_already_consumed")
        truth_document = json.loads(private.read("truth.json", 128 * 1024 * 1024))
        if not isinstance(truth_document, dict):
            raise ValueError("private_truth_invalid")
        private.write_atomic(
            "consumed.json",
            canonical_bytes(
                {
                    "protocolDigest": protocol["protocolDigest"],
                    "state": "consumed_by_single_canonical_evaluation",
                    "resultPublication": "next_append_only_commit",
                }
            ),
        )
    truth_rows = truth_document.get("rows", [])
    _verify_truth_commitments(truth_rows, commitments)
    result = evaluate_publication(
        protocol,
        contestant_output,
        truth_rows,
        development_studies=development_studies,
    )
    disclosure: dict[str, Any] = {
        "schemaVersion": 2,
        "disclosureVersion": "closy.solver_material_v2_post_result_truth_disclosure.v1",
        "protocolDigest": protocol["protocolDigest"],
        "commitmentDigest": commitments["commitmentDigest"],
        "permanentlyExposed": True,
        "eligibleForSuccessorSelection": False,
        "seedOrCustodyInternalsDisclosed": False,
        "rows": truth_rows,
    }
    disclosure["disclosureDigest"] = canonical_digest(disclosure)
    envelope: dict[str, Any] = {
        "schemaVersion": 2,
        "publicationVersion": "closy.solver_material_v2_immutable_result.v1",
        "protocolId": protocol["protocolId"],
        "protocolDigest": protocol["protocolDigest"],
        "sourceCommit": source_freeze["sourceCommit"],
        "sourceTree": source_freeze["sourceTree"],
        "sourceFreezeDigest": source_freeze["freezeDigest"],
        "contestantOutputDigest": contestant_output["contestantOutputDigest"],
        "commitmentDigest": commitments["commitmentDigest"],
        "result": result,
        "evidenceClass": "same_project_source_guarded_correlated_synthetic",
        "unsupportedEvidence": [
            "real_fabric_calibration",
            "physical_validation",
            "private_user_readiness",
            "mobile_performance",
            "scientific_blind_independent_validation",
            "product_acceptance",
        ],
        "budgetAccounting": {
            "protocolLocalSyntheticSeedConsumed": True,
            "lockedTuplesConsumed": 24,
            "garmentMotionsConsumed": 576,
            "canonicalGeometryCandidateBudgetConsumed": False,
            "y2AuthorityConsumed": False,
            "scientificAttemptConsumed": False,
        },
    }
    envelope["resultDigest"] = canonical_digest(envelope)
    write_json(envelope_path, envelope)
    write_json(disclosure_path, disclosure)
    return {"envelope": envelope, "disclosure": disclosure}


def evaluate_publication(
    protocol: dict[str, Any],
    contestant_output: dict[str, Any],
    truth_rows: list[dict[str, Any]],
    *,
    development_studies: dict[str, Any],
) -> dict[str, Any]:
    outputs = {str(row["tupleId"]): row for row in contestant_output.get("rows", [])}
    truths = {str(row["tupleId"]): row for row in truth_rows}
    if len(outputs) != 24 or len(truths) != 24 or set(outputs) != set(truths):
        raise ValueError("locked_tuple_denominator_or_identity_invalid")
    field_errors: dict[str, list[float]] = defaultdict(list)
    row_summaries: list[dict[str, Any]] = []
    prediction_residuals: list[float] = []
    motion_residuals: list[float] = []
    interval_hits: dict[str, list[bool]] = defaultdict(list)
    interval_widths: list[float] = []
    controls: list[dict[str, Any]] = []
    physical_motion_passes = 0
    terminal_counts: dict[str, int] = defaultdict(int)
    baseline_errors: dict[str, list[float]] = defaultdict(list)
    for tuple_id in sorted(truths):
        truth = truths[tuple_id]
        output = outputs[tuple_id]
        estimate = output["estimate"]
        estimated = estimate["estimatedFields"]
        target = truth["normalizedFields"]
        errors = {
            field: abs(float(estimated[field]) - float(target[field])) for field in FIELD_ORDER
        }
        for field, value in errors.items():
            field_errors[field].append(value)
            interval = estimate["intervals"][field]
            hit = float(interval[0]) <= float(target[field]) <= float(interval[1])
            interval_hits[field].append(hit)
            interval_widths.append(float(interval[1]) - float(interval[0]))
        predictions = _match_rows(
            output["withheldPredictions"], truth["withheldPredictions"], "observationId"
        )
        tuple_prediction = []
        for predicted, expected in predictions:
            predicted_value = float(predicted["observables"]["primary"]["value"])
            expected_value = float(expected["observables"]["primary"]["value"])
            residual = (predicted_value - expected_value) / max(abs(expected_value), 1e-4)
            prediction_residuals.append(residual)
            tuple_prediction.append(residual)
        motions = _match_motion_rows(output["garmentMotions"], truth["garmentMotions"])
        tuple_motion = []
        for predicted, expected in motions:
            for metric in sorted(expected["metrics"]):
                predicted_value = float(predicted["metrics"][metric])
                expected_value = float(expected["metrics"][metric])
                residual = (predicted_value - expected_value) / max(abs(expected_value), 1e-4)
                motion_residuals.append(residual)
                tuple_motion.append(residual)
            valid = (
                predicted.get("termination") == "passed"
                and float(predicted["metrics"]["bodyPenetrationMeters"]) <= 0.0005
                and float(predicted["metrics"]["p95Strain"]) <= 0.35
                and float(predicted["metrics"]["seamErrorMeters"]) <= 0.008
            )
            physical_motion_passes += int(valid)
        normal_mean = sum(errors.values()) / len(errors)
        controls.extend(_evaluate_controls(tuple_id, output["controlOutputs"], target, normal_mean))
        baseline_errors["constant_prior"].append(
            sum(abs(0.5 - float(target[field])) for field in FIELD_ORDER) / len(FIELD_ORDER)
        )
        lookup = 0.44 + (sum(tuple_id.encode()) % 9) / 100.0
        baseline_errors["lookup_retrieval"].append(
            sum(abs(lookup - float(target[field])) for field in FIELD_ORDER) / len(FIELD_ORDER)
        )
        baseline_errors["wrong_model"].append(
            sum(
                abs((1.0 - float(estimated[field])) - float(target[field])) for field in FIELD_ORDER
            )
            / len(FIELD_ORDER)
        )
        terminal = str(output.get("terminalState", "failed"))
        terminal_counts[terminal] += 1
        row_summaries.append(
            {
                "tupleId": tuple_id,
                "fieldErrors": {field: rounded(value) for field, value in errors.items()},
                "meanActiveFieldError": rounded(normal_mean),
                "meanSixFieldError": rounded(sum(errors[field] for field in SIX_FIELD_ORDER) / 6.0),
                "withheldPredictionNrmse": rounded(_rms(tuple_prediction)),
                "garmentMotionNrmse": rounded(_rms(tuple_motion)),
                "effectiveRank": estimate["effectiveRank"],
                "conditionNumber": estimate["conditionNumber"],
                "abstainedFields": estimate["abstainedFields"],
                "terminalState": terminal,
            }
        )
    total_field_errors = [value for values in field_errors.values() for value in values]
    per_field = {
        field: {
            "count": len(values),
            "mean": rounded(sum(values) / len(values)),
            "nearestRankP95": rounded(nearest_rank(values, 0.95)),
            "worst": rounded(max(values)),
            "intervalCoverage": rounded(sum(interval_hits[field]) / len(interval_hits[field])),
        }
        for field, values in field_errors.items()
    }
    candidate_mean = sum(total_field_errors) / len(total_field_errors)
    control_passes = sum(bool(row["passed"]) for row in controls)
    convergence = development_studies["convergence"]
    metrics = {
        "meanNormalizedActiveFieldError": rounded(candidate_mean),
        "withheldPredictiveNrmse": rounded(_rms(prediction_residuals)),
        "perActiveFieldMeanMaximum": rounded(max(row["mean"] for row in per_field.values())),
        "perActiveFieldP95Maximum": rounded(
            max(row["nearestRankP95"] for row in per_field.values())
        ),
        "worstRowSixFieldNormalizedError": rounded(
            max(row["meanSixFieldError"] for row in row_summaries)
        ),
        "intervalCoverageOverall": rounded(
            sum(sum(values) for values in interval_hits.values()) / len(total_field_errors)
        ),
        "intervalCoveragePerFieldMinimum": rounded(
            min(row["intervalCoverage"] for row in per_field.values())
        ),
        "medianNormalizedIntervalWidth": rounded(nearest_rank(interval_widths, 0.50)),
        "identifiableFieldRate": rounded(
            sum(
                not row["abstainedFields"] and row["effectiveRank"] == len(FIELD_ORDER)
                for row in row_summaries
            )
            / len(row_summaries)
        ),
        "negativeControlPassRate": rounded(control_passes / len(controls)),
        "convergencePrimaryMaximum": convergence["primaryRelativeErrorMaximum"],
        "convergenceWorstMaximum": convergence["worstRelativeErrorMaximum"],
        "motionTransferNrmse": rounded(_rms(motion_residuals)),
        "motionPhysicalValidityRate": rounded(physical_motion_passes / 576.0),
        "constantPriorImprovement": rounded(
            _mean(baseline_errors["constant_prior"]) - candidate_mean
        ),
        "lookupBaselineImprovement": rounded(
            _mean(baseline_errors["lookup_retrieval"]) - candidate_mean
        ),
        "wrongModelImprovement": rounded(_mean(baseline_errors["wrong_model"]) - candidate_mean),
        "terminalConservation": 1.0 if sum(terminal_counts.values()) == 24 else 0.0,
    }
    predicates = []
    for threshold in protocol["thresholdRegistry"]:
        value = float(metrics[threshold["metric"]])
        limit = float(threshold["limit"])
        passed = value <= limit if threshold["direction"] == "maximum" else value >= limit
        predicates.append({**threshold, "value": rounded(value), "passed": passed})
    first_unmet = next((row["id"] for row in predicates if not row["passed"]), None)
    recovery_pass = all(
        row["passed"] for row in predicates if row["id"] not in {"SMV2-13", "SMV2-14"}
    )
    motion_pass = all(row["passed"] for row in predicates if row["id"] in {"SMV2-13", "SMV2-14"})
    return {
        "literalResult": RESULT_LITERAL_PASSED
        if recovery_pass and motion_pass
        else RESULT_LITERAL_FAILED,
        "synthetic_material_recovery_v2": "passed" if recovery_pass else "failed",
        "garment_motion_transfer": "passed" if motion_pass else "failed",
        "real_coupon_count": 0,
        "real_fabric_calibration": "not_run",
        "physical_validation": "not_run",
        "Phase_7": "partial",
        "firstUnmetPredicate": first_unmet,
        "metrics": metrics,
        "predicates": predicates,
        "perField": per_field,
        "rows": row_summaries,
        "controls": controls,
        "baselines": {
            name: {"meanError": rounded(_mean(values))} for name, values in baseline_errors.items()
        },
        "denominators": {
            "attemptedTuples": 24,
            "terminalTuples": dict(sorted(terminal_counts.items())),
            "estimatedFieldCells": 192,
            "intervalCells": 192,
            "inferenceObservations": 144,
            "withheldLoads": 48,
            "withheldGeometries": 24,
            "withheldPredictions": 96,
            "garmentMotions": 576,
            "garmentMotionsPerFamily": {"tshirt": 192, "sleeveless_top": 192, "simple_skirt": 192},
            "negativeControls": 240,
            "droppedRows": 0,
        },
        "consumption": "locked_seed_tuples_motions_outputs_and_result_exposed_ineligible",
    }


def _evaluate_controls(
    tuple_id: str,
    control_outputs: list[dict[str, Any]],
    truth: dict[str, float],
    normal_error: float,
) -> list[dict[str, Any]]:
    names = (
        "shuffled_observations",
        "wrong_orientation",
        "wrong_units",
        "wrong_family",
        "time_shuffled_damping",
        "contact_disabled_friction_restitution",
        "duplicated_observations",
        "missing_inference_load",
        "lineage_substitution",
        "target_leakage_import",
    )
    outputs = {str(row["control"]): row for row in control_outputs}
    if len(outputs) != 10 or set(outputs) != set(names):
        raise ValueError("negative_control_denominator_or_identity_invalid")
    rows = []
    for name in names:
        expectation = (
            "categorical_reject"
            if name
            in {
                "wrong_units",
                "duplicated_observations",
                "missing_inference_load",
                "lineage_substitution",
                "target_leakage_import",
            }
            else "numeric_degradation"
        )
        output = outputs[name]
        rejected = output.get("status") == "rejected"
        if not rejected:
            estimate = output["estimate"]
            error = _mean(
                [
                    abs(float(estimate["estimatedFields"][field]) - float(truth[field]))
                    for field in FIELD_ORDER
                ]
            )
            degradation = (error - normal_error) / max(normal_error, 1e-6)
        else:
            error, degradation, rejected = None, None, True
        passed = (
            rejected
            if expectation == "categorical_reject"
            else (not rejected and float(degradation or 0.0) >= 0.20)
        )
        rows.append(
            {
                "tupleId": tuple_id,
                "control": name,
                "expectation": expectation,
                "normalError": rounded(normal_error),
                "controlledError": rounded(error) if error is not None else None,
                "relativeDegradation": rounded(degradation) if degradation is not None else None,
                "categoricallyRejected": rejected,
                "passed": passed,
            }
        )
    return rows


def _verify_truth_commitments(
    truth_rows: list[dict[str, Any]], commitments: dict[str, Any]
) -> None:
    expected = {
        str(row["tupleId"]): str(row["truthCommitment"]) for row in commitments["commitments"]
    }
    actual = {str(row["tupleId"]): canonical_digest(row) for row in truth_rows}
    if len(expected) != 24 or expected != actual:
        raise ValueError("truth_commitment_mismatch")


def _match_rows(
    left: list[dict[str, Any]], right: list[dict[str, Any]], key: str
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    left_map = {str(row[key]): row for row in left}
    right_map = {str(row[key]): row for row in right}
    if len(left_map) != 4 or left_map.keys() != right_map.keys():
        raise ValueError("withheld_prediction_identity_invalid")
    return [(left_map[identity], right_map[identity]) for identity in sorted(left_map)]


def _match_motion_rows(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    def identity(row: dict[str, Any]) -> tuple[str, str]:
        return str(row["family"]), str(row["motionId"])

    left_map = {identity(row): row for row in left}
    right_map = {identity(row): row for row in right}
    if len(left_map) != 24 or left_map.keys() != right_map.keys():
        raise ValueError("garment_motion_identity_invalid")
    return [(left_map[key], right_map[key]) for key in sorted(left_map)]


def _rms(values: list[float]) -> float:
    return sqrt(sum(value * value for value in values) / len(values)) if values else float("inf")


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("inf")
