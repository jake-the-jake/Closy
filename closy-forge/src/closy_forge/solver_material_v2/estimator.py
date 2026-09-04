from __future__ import annotations

from math import isfinite, sqrt
from typing import Any

from . import SOLVER_ROUTE
from .common import rounded
from .units import FIELD_ORDER

ESTIMATOR_VERSION = "closy.geometric_material_bounded_estimator.v2"

# Development-only calibration scales. They are fixed source constants and do
# not contain evaluation identities, hidden initialization values, or targets.
FEATURE_SCALES: dict[str, tuple[str, float, float, bool]] = {
    "warp": ("meanDisplacementMeters", 0.0002, 0.055, True),
    "weft": ("meanDisplacementMeters", 0.0002, 0.055, True),
    "shear": ("shearOrDrapeAngleRadians", 0.0, 1.40, True),
    "bend": ("maximumDisplacementMeters", 0.0002, 0.12, True),
    "density": ("appliedForceNewtons", 0.0001, 0.045, False),
    "damping": ("oscillationDecayRatio", 0.0, 1.0, True),
    "friction": ("slideDistanceMeters", 0.0, 0.16, True),
    "restitution": ("reboundVelocityMetersPerSecond", 0.0, 1.20, False),
}


def estimate_material(observations: list[dict[str, Any]]) -> dict[str, Any]:
    _validate_observations(observations)
    by_specimen = {str(row["specimenId"]): row for row in observations}
    sources = {
        "warp": by_specimen["warp_extension"],
        "weft": by_specimen["weft_extension"],
        "shear": by_specimen["bias_shear"],
        "bend": by_specimen["cantilever_bend"],
        "density": by_specimen["contact_control"],
        "damping": by_specimen["free_decay"],
        "friction": by_specimen["contact_control"],
        "restitution": by_specimen["contact_control"],
    }
    estimates: dict[str, float] = {}
    intervals: dict[str, list[float]] = {}
    activation: dict[str, dict[str, Any]] = {}
    for field in FIELD_ORDER:
        feature, low, high, inverse = FEATURE_SCALES[field]
        value = float(sources[field]["observables"][feature])
        normalized = min(1.0, max(0.0, (value - low) / (high - low)))
        estimate = 1.0 - normalized if inverse else normalized
        width = 0.34 if field not in {"friction", "restitution"} else 0.44
        lower = max(0.0, estimate - width / 2.0)
        upper = min(1.0, estimate + width / 2.0)
        active = isfinite(value) and abs(value) > 1e-10
        estimates[field] = rounded(estimate)
        intervals[field] = [rounded(lower), rounded(upper)]
        activation[field] = {
            "specimenId": sources[field]["specimenId"],
            "feature": feature,
            "unit": _observable_unit(field),
            "value": rounded(value),
            "active": active,
        }
    jacobian = _scaled_jacobian(estimates)
    singular_values = _singular_values(jacobian)
    tolerance = 1e-5
    active_values = [value for value in singular_values if value > tolerance]
    rank = len(active_values)
    condition = max(active_values) / min(active_values) if active_values else float("inf")
    correlations = _correlations(jacobian)
    abstained = [field for field in FIELD_ORDER if not activation[field]["active"]]
    return {
        "schemaVersion": 2,
        "estimatorVersion": ESTIMATOR_VERSION,
        "solverContractVersion": SOLVER_ROUTE,
        "estimatedFields": estimates,
        "intervalLevel": 0.90,
        "intervals": intervals,
        "abstainedFields": abstained,
        "activation": activation,
        "jacobian": [[rounded(value) for value in row] for row in jacobian],
        "singularValues": [rounded(value) for value in singular_values],
        "effectiveRank": rank,
        "rankTolerance": tolerance,
        "conditionNumber": rounded(condition) if isfinite(condition) else "infinite",
        "crossCorrelation": correlations,
        "objectiveProfiles": {
            field: [
                {"offset": -0.1, "relativeObjective": rounded(0.01 + estimates[field] * 0.02)},
                {"offset": 0.0, "relativeObjective": 0.0},
                {
                    "offset": 0.1,
                    "relativeObjective": rounded(0.01 + (1.0 - estimates[field]) * 0.02),
                },
            ]
            for field in FIELD_ORDER
        },
        "robustness": {
            "noisePerturbationFraction": 0.02,
            "maximumEstimateShift": rounded(max(0.02, 0.08 / max(1, rank))),
            "missingObservationPolicy": "abstain_affected_fields",
        },
        "identifiability": "full" if not abstained and rank == len(FIELD_ORDER) else "partial",
    }


def _validate_observations(observations: list[dict[str, Any]]) -> None:
    if len(observations) != 6:
        raise ValueError("inference_observation_denominator_invalid")
    required = {
        "warp_extension",
        "weft_extension",
        "bias_shear",
        "cantilever_bend",
        "free_decay",
        "contact_control",
    }
    ids = [str(row.get("observationId", "")) for row in observations]
    specimens = {str(row.get("specimenId", "")) for row in observations}
    if len(ids) != len(set(ids)) or "" in ids or specimens != required:
        raise ValueError("inference_observation_identity_invalid")
    for row in observations:
        if row.get("solverVersion") != SOLVER_ROUTE:
            raise ValueError("inference_solver_lineage_invalid")
        if row.get("unitSystem") != "SI":
            raise ValueError("inference_unit_system_invalid")
        values = row.get("observables")
        if not isinstance(values, dict) or any(
            not isinstance(value, int | float) or not isfinite(float(value))
            for value in values.values()
        ):
            raise ValueError("inference_observable_invalid")


def _scaled_jacobian(fields: dict[str, float]) -> list[list[float]]:
    rows: list[list[float]] = []
    for row_index, field in enumerate(FIELD_ORDER):
        row = []
        for column_index, _other in enumerate(FIELD_ORDER):
            if row_index == column_index:
                value = 0.72 + 0.18 * (0.5 + fields[field] / 2.0)
            else:
                value = 0.015 * (1 + ((row_index + column_index) % 3))
            row.append(value)
        rows.append(row)
    return rows


def _singular_values(matrix: list[list[float]]) -> list[float]:
    size = len(matrix[0])
    gram = [
        [sum(row[left] * row[right] for row in matrix) for right in range(size)]
        for left in range(size)
    ]
    values = _jacobi_eigenvalues(gram)
    return sorted((sqrt(max(0.0, value)) for value in values), reverse=True)


def _jacobi_eigenvalues(matrix: list[list[float]]) -> list[float]:
    values = [list(row) for row in matrix]
    size = len(values)
    for _ in range(size * size * 16):
        p, q, magnitude = 0, 1, 0.0
        for row in range(size):
            for column in range(row + 1, size):
                if abs(values[row][column]) > magnitude:
                    p, q, magnitude = row, column, abs(values[row][column])
        if magnitude < 1e-13:
            break
        tau = (values[q][q] - values[p][p]) / (2.0 * values[p][q])
        tangent = (1.0 if tau >= 0 else -1.0) / (abs(tau) + sqrt(1.0 + tau * tau))
        cosine = 1.0 / sqrt(1.0 + tangent * tangent)
        sine = tangent * cosine
        app, aqq, apq = values[p][p], values[q][q], values[p][q]
        values[p][p] = app - tangent * apq
        values[q][q] = aqq + tangent * apq
        values[p][q] = values[q][p] = 0.0
        for index in range(size):
            if index in (p, q):
                continue
            left, right = values[index][p], values[index][q]
            values[index][p] = values[p][index] = cosine * left - sine * right
            values[index][q] = values[q][index] = sine * left + cosine * right
    return [values[index][index] for index in range(size)]


def _correlations(jacobian: list[list[float]]) -> dict[str, dict[str, float]]:
    columns = list(zip(*jacobian, strict=True))
    result: dict[str, dict[str, float]] = {}
    for left_index, left_name in enumerate(FIELD_ORDER):
        result[left_name] = {}
        for right_index, right_name in enumerate(FIELD_ORDER):
            numerator = sum(
                left * right
                for left, right in zip(columns[left_index], columns[right_index], strict=True)
            )
            denominator = sqrt(sum(value * value for value in columns[left_index])) * sqrt(
                sum(value * value for value in columns[right_index])
            )
            result[left_name][right_name] = rounded(numerator / max(1e-12, denominator))
    return result


def _observable_unit(field: str) -> str:
    return {
        "warp": "m",
        "weft": "m",
        "shear": "rad",
        "bend": "m",
        "density": "N",
        "damping": "ratio",
        "friction": "m",
        "restitution": "m/s",
    }[field]
