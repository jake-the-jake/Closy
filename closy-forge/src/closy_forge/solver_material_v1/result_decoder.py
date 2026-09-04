from __future__ import annotations

from math import ceil
from typing import Any

from closy_forge.solver_material_v1.common import digest


def independently_check_result(result: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    rows = result.get("rows", [])
    if not isinstance(rows, list) or len(rows) != 16:
        failures.append("tuple_row_denominator_invalid")
        rows = []
    estimated = [
        float(value) for row in rows for value in row.get("estimatedFieldErrors", {}).values()
    ]
    abstained = [
        float(value) for row in rows for value in row.get("abstainedFieldErrors", {}).values()
    ]
    if len(estimated) != 96:
        failures.append("estimated_cell_denominator_invalid")
    if len(abstained) != 32:
        failures.append("abstained_cell_denominator_invalid")
    if len({row.get("tupleId") for row in rows}) != len(rows):
        failures.append("tuple_identity_duplicate")
    conservation = result.get("terminalConservation", {})
    terminal_sum = sum(
        int(conservation.get(key, -1000))
        for key in (
            "estimated",
            "abstained",
            "unsupported",
            "failed",
            "nonFinite",
            "timeout",
            "divergent",
        )
    )
    if terminal_sum != 144 or conservation.get("expected") != 144:
        failures.append("terminal_conservation_invalid")
    if estimated:
        ordered = sorted(estimated)
        expected_mean = sum(estimated) / len(estimated)
        expected_p95 = ordered[ceil(0.95 * len(ordered)) - 1]
        aggregate = result["aggregate"]["sixField"]
        if abs(float(aggregate["mean"]) - expected_mean) > 5e-9:
            failures.append("mean_six_field_error_invalid")
        if abs(float(aggregate["p95NearestRank"]) - expected_p95) > 5e-9:
            failures.append("p95_six_field_error_invalid")
    unsigned = dict(result)
    observed_digest = str(unsigned.pop("resultDigest", ""))
    if digest(unsigned) != observed_digest:
        failures.append("result_digest_invalid")
    if result.get("engineeringAcceptance") != "failed":
        failures.append("engineering_acceptance_not_failed")
    if result.get("scientificQualification") != "ineligible_test_exposed_before_estimator":
        failures.append("scientific_qualification_invalid")
    predicates = result.get("acceptancePredicates", [])
    negative = [row for row in predicates if row.get("predicate") == "negativeControlsMustDegrade"]
    if len(negative) != 1 or negative[0].get("status") != "not_run_unsatisfied":
        failures.append("negative_control_classification_invalid")
    return {
        "checkerVersion": "closy.solver_material.independent_result_checker.v1",
        "failureCount": len(failures),
        "failures": failures,
        "status": "passed" if not failures else "integrity_error",
    }
