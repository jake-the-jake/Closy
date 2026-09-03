from __future__ import annotations

from math import isfinite, sqrt
from typing import Any

from closy_forge.solver_material_v1.common import rounded
from closy_forge.solver_material_v1.production_solver import (
    PRODUCTION_SOLVER_VERSION,
    run_production_coupon,
)

ESTIMATOR_VERSION = "closy.solver_material.coupled_bounded_estimator.v1"
FIELD_ORDER = (
    "warp",
    "weft",
    "shear",
    "bend",
    "density",
    "damping",
    "friction",
    "restitution",
)
IDENTIFIABLE_FAMILIES = (
    "warp_tensile",
    "weft_tensile",
    "bias_shear",
    "cantilever_bend",
    "gravity_sag",
    "free_decay",
)


def estimate_solver_fields(
    observations: list[dict[str, Any]],
    bounds: dict[str, list[float]],
    solver_contract_version: str,
) -> dict[str, Any]:
    if solver_contract_version != PRODUCTION_SOLVER_VERSION:
        raise ValueError("solver_contract_version_invalid")
    targets = _targets(observations)
    estimate = {field: 0.5 for field in FIELD_ORDER}
    trace: list[dict[str, Any]] = []
    best = _loss(estimate, targets)
    for step in (0.28, 0.14, 0.07, 0.035):
        for field in FIELD_ORDER[:6]:
            candidates = []
            low, high = (float(value) for value in bounds[field])
            for direction in (-1.0, 1.0):
                candidate = dict(estimate)
                candidate[field] = min(high, max(low, estimate[field] + direction * step))
                candidates.append((_loss(candidate, targets), candidate))
            candidate_loss, candidate = min(candidates, key=lambda item: item[0])
            accepted = candidate_loss < best
            if accepted:
                estimate, best = candidate, candidate_loss
            trace.append(
                {
                    "field": field,
                    "step": step,
                    "candidateLoss": rounded(candidate_loss),
                    "accepted": accepted,
                }
            )
    jacobian = _finite_difference_jacobian(estimate, targets)
    singular_values = _singular_values(jacobian)
    active = [value for value in singular_values if value > 1e-7]
    rank = len(active)
    condition = max(active) / min(active) if active else float("inf")
    abstained = ["friction", "restitution"]
    return {
        "estimatorVersion": ESTIMATOR_VERSION,
        "solverContractVersion": solver_contract_version,
        "estimatedFields": {field: rounded(value) for field, value in estimate.items()},
        "abstainedFields": abstained,
        "fixedPriorFields": {field: 0.5 for field in abstained},
        "objective": rounded(best),
        "optimizationTrace": trace,
        "jacobian": [[rounded(value) for value in row] for row in jacobian],
        "singularValues": [rounded(value) for value in singular_values],
        "jacobianRank": rank,
        "conditionNumber": rounded(condition) if isfinite(condition) else "infinite",
        "identifiability": "partial" if abstained else "full",
        "simulatedNumericalUncertaintyOnly": True,
    }


def predict_observations(fields: dict[str, float], metadata: list[dict[str, Any]]) -> list[float]:
    return [
        float(run_production_coupon(fields, str(row["family"]), float(row["load"]))["observable"])
        for row in metadata
    ]


def _targets(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [row for row in observations if row.get("family") in IDENTIFIABLE_FAMILIES]
    if {str(row["family"]) for row in selected} != set(IDENTIFIABLE_FAMILIES):
        raise ValueError("estimator_observation_family_denominator_invalid")
    return selected


def _loss(fields: dict[str, float], targets: list[dict[str, Any]]) -> float:
    predicted = predict_observations(fields, targets)
    residuals = []
    for prediction, target in zip(predicted, targets, strict=True):
        observed = float(target["observable"])
        scale = max(abs(observed), float(target.get("normalizationFloor", 1e-4)))
        residuals.append((prediction - observed) / scale)
    return sum(value * value for value in residuals) / len(residuals)


def _finite_difference_jacobian(
    fields: dict[str, float], targets: list[dict[str, Any]]
) -> list[list[float]]:
    delta = 0.01
    metadata = [{"family": row["family"], "load": row["load"]} for row in targets]
    rows = [[0.0 for _ in FIELD_ORDER] for _ in metadata]
    for column, field in enumerate(FIELD_ORDER):
        lower, upper = dict(fields), dict(fields)
        lower[field] = max(0.0, lower[field] - delta)
        upper[field] = min(1.0, upper[field] + delta)
        span = upper[field] - lower[field]
        below = predict_observations(lower, metadata)
        above = predict_observations(upper, metadata)
        for row, (low_value, high_value) in enumerate(zip(below, above, strict=True)):
            scale = max(abs(float(targets[row]["observable"])), 1e-4)
            rows[row][column] = (high_value - low_value) / span / scale
    return rows


def _singular_values(matrix: list[list[float]]) -> list[float]:
    columns = len(matrix[0])
    gram = [
        [sum(row[left] * row[right] for row in matrix) for right in range(columns)]
        for left in range(columns)
    ]
    eigenvalues = _jacobi_eigenvalues(gram)
    return sorted((sqrt(max(0.0, value)) for value in eigenvalues), reverse=True)


def _jacobi_eigenvalues(matrix: list[list[float]]) -> list[float]:
    values = [list(row) for row in matrix]
    size = len(values)
    for _ in range(size * size * 12):
        p, q = 0, 1
        magnitude = 0.0
        for row in range(size):
            for column in range(row + 1, size):
                if abs(values[row][column]) > magnitude:
                    p, q, magnitude = row, column, abs(values[row][column])
        if magnitude < 1e-12:
            break
        tau = (values[q][q] - values[p][p]) / (2.0 * values[p][q])
        tangent = (1.0 if tau >= 0.0 else -1.0) / (abs(tau) + sqrt(1.0 + tau * tau))
        cosine = 1.0 / sqrt(1.0 + tangent * tangent)
        sine = tangent * cosine
        app, aqq, apq = values[p][p], values[q][q], values[p][q]
        values[p][p] = app - tangent * apq
        values[q][q] = aqq + tangent * apq
        values[p][q] = values[q][p] = 0.0
        for index in range(size):
            if index in (p, q):
                continue
            aip, aiq = values[index][p], values[index][q]
            values[index][p] = values[p][index] = cosine * aip - sine * aiq
            values[index][q] = values[q][index] = sine * aip + cosine * aiq
    return [values[index][index] for index in range(size)]
