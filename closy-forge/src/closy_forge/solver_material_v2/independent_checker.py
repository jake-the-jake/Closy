from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from math import sqrt
from pathlib import Path
from typing import Any

from .common import canonical_digest, nearest_rank, read_json, rounded
from .units import FIELD_ORDER, SIX_FIELD_ORDER


def check_publication_paths(
    protocol_path: Path,
    public_root: Path,
    contestant_path: Path,
    envelope_path: Path,
    disclosure_path: Path,
    development_studies_path: Path,
) -> dict[str, Any]:
    protocol = read_json(protocol_path)
    contestant = read_json(contestant_path)
    envelope = read_json(envelope_path)
    disclosure = read_json(disclosure_path)
    commitments = read_json(public_root / "truth_commitments.json")
    development = read_json(development_studies_path)
    failures: list[str] = []
    if contestant.get("contestantOutputDigest") != canonical_digest(
        contestant, "contestantOutputDigest"
    ):
        failures.append("contestant_digest_invalid")
    if disclosure.get("disclosureDigest") != canonical_digest(disclosure, "disclosureDigest"):
        failures.append("disclosure_digest_invalid")
    if envelope.get("resultDigest") != canonical_digest(envelope, "resultDigest"):
        failures.append("result_digest_invalid")
    commitment_map = {
        str(row["tupleId"]): str(row["truthCommitment"]) for row in commitments["commitments"]
    }
    disclosure_map = {
        str(row["tupleId"]): canonical_digest(row) for row in disclosure.get("rows", [])
    }
    if commitment_map != disclosure_map or len(commitment_map) != 24:
        failures.append("truth_commitment_mismatch")
    recomputed = _recompute(protocol, contestant, disclosure["rows"], development)
    published = envelope.get("result", {})
    if recomputed["metrics"] != published.get("metrics"):
        failures.append("recomputed_metrics_mismatch")
    if recomputed["perField"] != published.get("perField"):
        failures.append("recomputed_field_metrics_mismatch")
    if recomputed["predicates"] != published.get("predicates"):
        failures.append("recomputed_predicates_mismatch")
    if recomputed["controls"] != published.get("controls"):
        failures.append("recomputed_controls_mismatch")
    if recomputed["denominators"] != published.get("denominators"):
        failures.append("recomputed_denominators_mismatch")
    if recomputed["literalResult"] != published.get("literalResult"):
        failures.append("recomputed_classification_mismatch")
    return {
        "schemaVersion": 2,
        "checkerVersion": "closy.solver_material_v2_independent_checker.v1",
        "terminalOutcome": "passed" if not failures else "failed",
        "failures": sorted(set(failures)),
        "estimatorRerun": False,
        "recomputed": {
            "tupleCount": 24,
            "fieldCellCount": 192,
            "predictionCount": 96,
            "garmentMotionCount": 576,
            "controlCount": 240,
            "thresholdCount": len(protocol["thresholdRegistry"]),
        },
        "publicationResultDigest": envelope.get("resultDigest"),
    }


def _recompute(
    protocol: dict[str, Any],
    contestant: dict[str, Any],
    truth_rows: list[dict[str, Any]],
    development: dict[str, Any],
) -> dict[str, Any]:
    outputs = {str(row["tupleId"]): row for row in contestant["rows"]}
    truths = {str(row["tupleId"]): row for row in truth_rows}
    field_errors: dict[str, list[float]] = defaultdict(list)
    interval_hits: dict[str, list[bool]] = defaultdict(list)
    widths: list[float] = []
    prediction_residuals: list[float] = []
    motion_residuals: list[float] = []
    row_six: list[float] = []
    identifiable = 0
    physical = 0
    controls: list[dict[str, Any]] = []
    terminals: dict[str, int] = defaultdict(int)
    baselines: dict[str, list[float]] = defaultdict(list)
    for tuple_id in sorted(truths):
        target = truths[tuple_id]["normalizedFields"]
        output = outputs[tuple_id]
        estimate = output["estimate"]
        errors = {
            field: abs(float(estimate["estimatedFields"][field]) - float(target[field]))
            for field in FIELD_ORDER
        }
        for field in FIELD_ORDER:
            field_errors[field].append(errors[field])
            interval = estimate["intervals"][field]
            interval_hits[field].append(
                float(interval[0]) <= float(target[field]) <= float(interval[1])
            )
            widths.append(float(interval[1]) - float(interval[0]))
        row_six.append(_ordered_sum(errors[field] for field in SIX_FIELD_ORDER) / 6.0)
        identifiable += int(
            not estimate["abstainedFields"] and estimate["effectiveRank"] == len(FIELD_ORDER)
        )
        expected_predictions = {
            str(row["observationId"]): row for row in truths[tuple_id]["withheldPredictions"]
        }
        for predicted in output["withheldPredictions"]:
            expected = expected_predictions[str(predicted["observationId"])]
            left = float(predicted["observables"]["primary"]["value"])
            right = float(expected["observables"]["primary"]["value"])
            prediction_residuals.append((left - right) / max(abs(right), 1e-4))
        expected_motions = {
            (str(row["family"]), str(row["motionId"])): row
            for row in truths[tuple_id]["garmentMotions"]
        }
        for predicted in output["garmentMotions"]:
            expected = expected_motions[(str(predicted["family"]), str(predicted["motionId"]))]
            for metric in sorted(expected["metrics"]):
                left = float(predicted["metrics"][metric])
                right = float(expected["metrics"][metric])
                motion_residuals.append((left - right) / max(abs(right), 1e-4))
            physical += int(
                predicted["termination"] == "passed"
                and float(predicted["metrics"]["bodyPenetrationMeters"]) <= 0.0005
                and float(predicted["metrics"]["p95Strain"]) <= 0.35
                and float(predicted["metrics"]["seamErrorMeters"]) <= 0.008
            )
        normal = _ordered_sum(errors.values()) / len(errors)
        controls.extend(_controls(tuple_id, output["controlOutputs"], target, normal))
        baselines["constant_prior"].append(
            _ordered_sum(abs(0.5 - float(target[field])) for field in FIELD_ORDER)
            / len(FIELD_ORDER)
        )
        lookup = 0.44 + (sum(tuple_id.encode()) % 9) / 100.0
        baselines["lookup_retrieval"].append(
            _ordered_sum(abs(lookup - float(target[field])) for field in FIELD_ORDER)
            / len(FIELD_ORDER)
        )
        baselines["wrong_model"].append(
            _ordered_sum(
                abs((1.0 - float(estimate["estimatedFields"][field])) - float(target[field]))
                for field in FIELD_ORDER
            )
            / len(FIELD_ORDER)
        )
        terminals[str(output.get("terminalState", "failed"))] += 1
    per_field = {
        field: {
            "count": len(values),
            "mean": rounded(_mean(values)),
            "nearestRankP95": rounded(nearest_rank(values, 0.95)),
            "worst": rounded(max(values)),
            "intervalCoverage": rounded(sum(interval_hits[field]) / len(interval_hits[field])),
        }
        for field, values in field_errors.items()
    }
    all_errors = [value for values in field_errors.values() for value in values]
    candidate = _mean(all_errors)
    control_passes = sum(bool(row["passed"]) for row in controls)
    convergence = development["convergence"]
    metrics = {
        "meanNormalizedActiveFieldError": rounded(candidate),
        "withheldPredictiveNrmse": rounded(_rms(prediction_residuals)),
        "perActiveFieldMeanMaximum": rounded(max(row["mean"] for row in per_field.values())),
        "perActiveFieldP95Maximum": rounded(
            max(row["nearestRankP95"] for row in per_field.values())
        ),
        "worstRowSixFieldNormalizedError": rounded(max(row_six)),
        "intervalCoverageOverall": rounded(
            sum(sum(values) for values in interval_hits.values()) / len(all_errors)
        ),
        "intervalCoveragePerFieldMinimum": rounded(
            min(row["intervalCoverage"] for row in per_field.values())
        ),
        "medianNormalizedIntervalWidth": rounded(nearest_rank(widths, 0.50)),
        "identifiableFieldRate": rounded(identifiable / 24.0),
        "negativeControlPassRate": rounded(control_passes / 240.0),
        "convergencePrimaryMaximum": convergence["primaryRelativeErrorMaximum"],
        "convergenceWorstMaximum": convergence["worstRelativeErrorMaximum"],
        "motionTransferNrmse": rounded(_rms(motion_residuals)),
        "motionPhysicalValidityRate": rounded(physical / 576.0),
        "constantPriorImprovement": rounded(_mean(baselines["constant_prior"]) - candidate),
        "lookupBaselineImprovement": rounded(_mean(baselines["lookup_retrieval"]) - candidate),
        "wrongModelImprovement": rounded(_mean(baselines["wrong_model"]) - candidate),
        "terminalConservation": 1.0 if sum(terminals.values()) == 24 else 0.0,
    }
    predicates = []
    for threshold in protocol["thresholdRegistry"]:
        value, limit = float(metrics[threshold["metric"]]), float(threshold["limit"])
        passed = value <= limit if threshold["direction"] == "maximum" else value >= limit
        predicates.append({**threshold, "value": rounded(value), "passed": passed})
    recovery = all(row["passed"] for row in predicates if row["id"] not in {"SMV2-13", "SMV2-14"})
    motion = all(row["passed"] for row in predicates if row["id"] in {"SMV2-13", "SMV2-14"})
    return {
        "literalResult": (
            "source_guarded_synthetic_solver_material_v2_passed"
            if recovery and motion
            else "source_guarded_synthetic_solver_material_v2_failed"
        ),
        "metrics": metrics,
        "perField": per_field,
        "predicates": predicates,
        "controls": controls,
        "denominators": {
            "attemptedTuples": 24,
            "terminalTuples": dict(sorted(terminals.items())),
            "estimatedFieldCells": 192,
            "intervalCells": 192,
            "inferenceObservations": 144,
            "withheldLoads": 48,
            "withheldGeometries": 24,
            "withheldPredictions": 96,
            "garmentMotions": 576,
            "garmentMotionsPerFamily": {
                "tshirt": 192,
                "sleeveless_top": 192,
                "simple_skirt": 192,
            },
            "negativeControls": 240,
            "droppedRows": 0,
        },
    }


def _controls(
    tuple_id: str,
    output_rows: list[dict[str, Any]],
    truth: dict[str, float],
    normal: float,
) -> list[dict[str, Any]]:
    categorical = {
        "wrong_units",
        "duplicated_observations",
        "missing_inference_load",
        "lineage_substitution",
        "target_leakage_import",
    }
    rows = []
    for output in output_rows:
        name = str(output["control"])
        expectation = "categorical_reject" if name in categorical else "numeric_degradation"
        rejected = output["status"] == "rejected"
        if rejected:
            error = degradation = None
        else:
            estimate = output["estimate"]["estimatedFields"]
            error = _mean(
                [abs(float(estimate[field]) - float(truth[field])) for field in FIELD_ORDER]
            )
            degradation = (error - normal) / max(normal, 1e-6)
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
                "normalError": rounded(normal),
                "controlledError": rounded(error) if error is not None else None,
                "relativeDegradation": rounded(degradation) if degradation is not None else None,
                "categoricallyRejected": rejected,
                "passed": passed,
            }
        )
    return rows


def _rms(values: list[float]) -> float:
    return sqrt(_ordered_sum(value * value for value in values) / len(values))


def _mean(values: list[float]) -> float:
    return _ordered_sum(values) / len(values)


def _ordered_sum(values: Iterable[float]) -> float:
    # Python 3.12 changed float sum() to compensated summation. Preserve the
    # canonical Python 3.11 publication's explicit left-to-right accumulation.
    total = 0.0
    for value in values:
        total += value
    return total
