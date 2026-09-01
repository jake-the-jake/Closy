from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, cast

from closy_forge.geometry.mesh_model import Vec3, sub
from closy_forge.simulation.reference_cloth_solver import (
    DistanceConstraint,
    SupportConstraint,
    _distance_constraint_length,
    _penetration_depth,
    _project_collisions,
    _solve_distance,
    _solve_support,
)


def run_constraint_kernel(
    positions: Sequence[Vec3],
    constraints: list[DistanceConstraint],
    *,
    iterations: int = 5,
    time_step_seconds: float = 0.016666667,
    inverse_masses: Sequence[float] | None = None,
    tangent: Vec3 = (0.0, 1.0, 0.0),
) -> dict[str, Any]:
    current = list(positions)
    masses = list(inverse_masses or [1.0] * len(current))
    initial = [_residual(current, constraint) for constraint in constraints]
    traces: list[dict[str, Any]] = []
    for iteration in range(iterations):
        for ordinal, constraint in enumerate(constraints):
            residual_before = _residual(current, constraint)
            lambda_before = constraint.lagrange_multiplier
            gap_before = _gap(current, constraint)
            _solve_distance(current, masses, constraint, time_step_seconds)
            residual_after = _residual(current, constraint)
            delta_lambda = constraint.lagrange_multiplier - lambda_before
            normal, tangential = _components(gap_before, tangent)
            traces.append(
                {
                    "iteration": iteration,
                    "ordinal": ordinal,
                    "constraintId": constraint.entity_id,
                    "constraintType": constraint.kind,
                    "residualBeforeMeters": residual_before,
                    "residualAfterMeters": residual_after,
                    "seamNormalResidualMeters": normal,
                    "seamTangentialResidualMeters": tangential,
                    "deltaLambda": delta_lambda,
                    "impulseNewtonSeconds": abs(delta_lambda) / time_step_seconds,
                    "storedEnergyJoules": _stored_energy(residual_after, constraint.compliance),
                }
            )
    final = [_residual(current, constraint) for constraint in constraints]
    return {
        "kernel": "reference_cloth_solver._solve_distance",
        "positions": [list(point) for point in current],
        "initialResidualsMeters": initial,
        "finalResidualsMeters": final,
        "maximumInitialResidualMeters": max(initial, default=0.0),
        "maximumFinalResidualMeters": max(final, default=0.0),
        "residualRatio": max(final, default=0.0) / max(max(initial, default=0.0), 1e-15),
        "trace": traces,
        "maximumStoredEnergyJoules": max(
            (float(row["storedEnergyJoules"]) for row in traces), default=0.0
        ),
        "totalAbsoluteImpulseNewtonSeconds": sum(
            float(row["impulseNewtonSeconds"]) for row in traces
        ),
        "ordering": [row["constraintId"] for row in traces],
        "finite": all(math.isfinite(value) for point in current for value in point),
    }


def run_support_kernel(positions: Sequence[Vec3], support: SupportConstraint) -> dict[str, Any]:
    current = list(positions)
    before = _distance(current[support.index], support.target)
    _solve_support(current, support)
    after = _distance(current[support.index], support.target)
    return {
        "kernel": "reference_cloth_solver._solve_support",
        "residualBeforeMeters": before,
        "residualAfterMeters": after,
        "residualReduced": after < before,
    }


def run_contact_kernel(
    positions: Sequence[Vec3], primitives: list[dict[str, Any]], clearance: float
) -> dict[str, Any]:
    current = list(positions)
    previous = list(positions)
    before = [
        _penetration_depth(point, primitives, clearance)  # production signed proxy
        for point in current
    ]
    event_count = _project_collisions(
        current,
        previous,
        primitives,
        clearance,
        0.42,
        0.02,
        0.016666667,
    )
    after = [_penetration_depth(point, primitives, clearance) for point in current]
    return {
        "kernel": "reference_cloth_solver._project_collisions",
        "resolutionOrder": [
            str(item.get("id", item.get("type", "unknown"))) for item in primitives
        ],
        "eventCount": event_count,
        "maximumPenetrationBeforeMeters": max(before, default=0.0),
        "maximumPenetrationAfterMeters": max(after, default=0.0),
        "penetrationResolved": max(after, default=0.0) <= 1e-12,
        "positions": [list(point) for point in current],
    }


def constraint(
    a: int,
    b: int,
    *,
    entity_id: str,
    compliance: float = 1e-9,
    rest_length: float = 0.0,
    a_next: int | None = None,
    b_next: int | None = None,
    a_weight: float = 0.0,
    b_weight: float = 0.0,
    kind: str = "seam",
) -> DistanceConstraint:
    return DistanceConstraint(
        a,
        b,
        rest_length,
        compliance,
        kind,
        entity_id,
        a_next=a_next,
        b_next=b_next,
        a_weight=a_weight,
        b_weight=b_weight,
    )


def _residual(positions: list[Vec3], item: DistanceConstraint) -> float:
    return abs(_distance_constraint_length(positions, item) - item.rest_length)


def _gap(positions: list[Vec3], item: DistanceConstraint) -> Vec3:
    a_next = item.a if item.a_next is None else item.a_next
    b_next = item.b if item.b_next is None else item.b_next
    a = _weighted(positions[item.a], positions[a_next], item.a_weight)
    b = _weighted(positions[item.b], positions[b_next], item.b_weight)
    return sub(b, a)


def _weighted(left: Vec3, right: Vec3, weight: float) -> Vec3:
    return (
        left[0] * (1.0 - weight) + right[0] * weight,
        left[1] * (1.0 - weight) + right[1] * weight,
        left[2] * (1.0 - weight) + right[2] * weight,
    )


def _components(gap: Vec3, tangent: Vec3) -> tuple[float, float]:
    tangent_length = math.sqrt(sum(value * value for value in tangent))
    unit = cast(Vec3, tuple(value / max(tangent_length, 1e-15) for value in tangent))
    tangential = abs(sum(a * b for a, b in zip(gap, unit, strict=True)))
    total_squared = sum(value * value for value in gap)
    return math.sqrt(max(0.0, total_squared - tangential * tangential)), tangential


def _stored_energy(residual: float, compliance: float) -> float:
    return 0.5 * residual * residual / max(compliance, 1e-15)


def _distance(left: Vec3, right: Vec3) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))
