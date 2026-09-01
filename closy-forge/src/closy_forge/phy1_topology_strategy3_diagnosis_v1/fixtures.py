from __future__ import annotations

import math
from typing import Any, cast

from closy_forge.phy1_topology_strategy3_diagnosis_v1.production_kernels import (
    constraint,
    run_constraint_kernel,
    run_contact_kernel,
    run_support_kernel,
)
from closy_forge.phy1_topology_strategy3_diagnosis_v1.transfer import (
    apply_revision,
    base_transfer_fixture,
)
from closy_forge.simulation.reference_cloth_solver import SupportConstraint

COMPLIANCE = 1e-9
DT = 0.016666667


def run_fixture_set(revision: int) -> list[dict[str, Any]]:
    fixtures = [
        _normal_separation(),
        _curved_tangential(),
        _unequal_ease(),
        _three_way_junction(),
        _opening_adjacent(),
        _near_contact(),
        _transfer(revision),
    ]
    if [row["ordinal"] for row in fixtures] != list(range(1, 8)):
        raise ValueError("unit_o_fixture_order_invalid")
    return fixtures


def _normal_separation() -> dict[str, Any]:
    positions = [(-0.01, 0.0, 0.0), (-0.01, 0.04, 0.0), (0.01, 0.0, 0.0), (0.01, 0.04, 0.0)]
    constraints = [
        constraint(0, 2, entity_id="seam.normal.0"),
        constraint(1, 3, entity_id="seam.normal.1"),
    ]
    result = run_constraint_kernel(positions, constraints)
    first = result["trace"][0]
    alpha = COMPLIANCE / (DT * DT)
    expected_delta_lambda = -0.02 / (2.0 + alpha)
    expected_first_residual = 0.02 * alpha / (2.0 + alpha)
    expected_first_energy = 0.5 * expected_first_residual**2 / COMPLIANCE
    expected_first_impulse = abs(expected_delta_lambda) / DT
    impulse_error = abs(first["impulseNewtonSeconds"] - expected_first_impulse)
    energy_error = abs(first["storedEnergyJoules"] - expected_first_energy)
    checks = {
        "productionKernel": result["kernel"].endswith("_solve_distance"),
        "residualReduced": result["residualRatio"] <= 0.1,
        "normalMeasuredSeparately": first["seamNormalResidualMeters"] > 0.0,
        "tangentNearZero": first["seamTangentialResidualMeters"] <= 1e-12,
        "impulseAnalytic": abs(first["deltaLambda"] - expected_delta_lambda) <= 1e-12,
        "impulseBalanceWithinInterval": impulse_error <= 1e-9,
        "energyBalanceWithinInterval": energy_error <= 1e-9,
        "finiteComplianceRetained": max(result["finalResidualsMeters"]) > 0.0,
    }
    result["independentAnalyticBounds"] = {
        "expectedFirstResidualMeters": expected_first_residual,
        "expectedFirstImpulseNewtonSeconds": expected_first_impulse,
        "expectedFirstStoredEnergyJoules": expected_first_energy,
        "impulseBalanceErrorNewtonSeconds": impulse_error,
        "energyBalanceErrorJoules": energy_error,
    }
    mutation = _compliance_mutation(positions, 0, 2, result["maximumFinalResidualMeters"])
    return _report(1, "duplicated_seam_normal_separation", result, checks, mutation)


def _curved_tangential() -> dict[str, Any]:
    positions = [
        (0.0, 0.0, 0.0),
        (0.015, 0.02, 0.0),
        (0.004, 0.009, 0.0),
        (0.019, 0.029, 0.0),
    ]
    constraints = [
        constraint(0, 2, entity_id="seam.curved.0"),
        constraint(1, 3, entity_id="seam.curved.1"),
    ]
    tangent = _unit((0.015, 0.02, 0.0))
    result = run_constraint_kernel(positions, constraints, tangent=tangent)
    checks = {
        "residualReduced": result["residualRatio"] <= 0.1,
        "tangentialLoadObserved": max(
            row["seamTangentialResidualMeters"] for row in result["trace"]
        )
        > 0.0,
        "normalAndTangentialReported": all(
            "seamNormalResidualMeters" in row for row in result["trace"]
        ),
        "deterministicOrdering": result["ordering"][:2] == ["seam.curved.0", "seam.curved.1"],
    }
    return _report(
        2,
        "curved_seam_tangential_loading",
        result,
        checks,
        bool(result["residualRatio"] != 1.0),
    )


def _unequal_ease() -> dict[str, Any]:
    positions = [(0.0, 0.0, 0.0), (0.0, 0.03, 0.0), (0.012, 0.0, 0.0), (0.012, 0.018, 0.0)]
    constraints = [
        constraint(
            0,
            2,
            a_next=1,
            b_next=3,
            a_weight=0.65,
            b_weight=0.35,
            entity_id="seam.ease.weighted",
        )
    ]
    result = run_constraint_kernel(positions, constraints)
    checks = {
        "weightedSpansUsed": constraints[0].a_weight != constraints[0].b_weight,
        "residualReduced": result["residualRatio"] <= 0.1,
        "finite": result["finite"],
        "singleSemanticConstraint": len({row["constraintId"] for row in result["trace"]}) == 1,
    }
    return _report(
        3,
        "unequal_discretisation_ease",
        result,
        checks,
        _weight_mutation(result, positions),
    )


def _three_way_junction() -> dict[str, Any]:
    positions = [(0.0, 0.0, 0.0), (0.012, 0.0, 0.0), (0.0, 0.012, 0.0)]
    constraints = [
        constraint(0, 1, entity_id="junction.edge.0"),
        constraint(0, 2, entity_id="junction.edge.1"),
    ]
    result = run_constraint_kernel(positions, constraints, iterations=6)
    checks = {
        "rankAwareSpanningTree": len(constraints) == len(positions) - 1,
        "residualReduced": result["residualRatio"] <= 0.1,
        "allParticipantsFinite": result["finite"],
        "constraintOrderStable": result["ordering"][:2] == ["junction.edge.0", "junction.edge.1"],
    }
    return _report(
        4,
        "three_way_seam_junction",
        result,
        checks,
        len(constraints[:-1]) != len(positions) - 1,
    )


def _opening_adjacent() -> dict[str, Any]:
    opening_cycle = [0, 1, 2, 3]
    positions = [
        (0.0, 0.0, 0.0),
        (0.02, 0.0, 0.0),
        (0.02, 0.02, 0.0),
        (0.0, 0.02, 0.0),
        (0.026, 0.02, 0.0),
    ]
    result = run_constraint_kernel(positions, [constraint(2, 4, entity_id="seam.adjacent")])
    support = run_support_kernel(
        positions, SupportConstraint(0, positions[0], 0.5, "opening.support")
    )
    checks = {
        "openingSimpleCycle": len(opening_cycle) == len(set(opening_cycle)) == 4,
        "openingEdgesNotWelded": 4 not in opening_cycle,
        "adjacentSeamSolved": result["residualRatio"] <= 0.1,
        "supportResidualAccounted": support["residualAfterMeters"] == 0.0,
    }
    measurement = {"constraint": result, "support": support, "openingCycle": opening_cycle}
    return _report(5, "opening_adjacent_to_seam", measurement, checks, len(opening_cycle[:-1]) != 4)


def _near_contact() -> dict[str, Any]:
    positions = [(0.0, 0.0, 0.0), (0.005, 0.0, 0.0)]
    primitives = [
        {
            "id": "body.ellipsoid",
            "type": "ellipsoid",
            "center": [0.0, 0.0, 0.0],
            "radii": [0.01, 0.02, 0.01],
        }
    ]
    contact = run_contact_kernel(positions, primitives, 0.001)
    projected = [tuple(point) for point in contact["positions"]]
    seam = run_constraint_kernel(projected, [constraint(0, 1, entity_id="seam.contact")])
    checks = {
        "contactDetected": contact["eventCount"] > 0,
        "penetrationResolved": contact["penetrationResolved"],
        "resolutionOrderRecorded": contact["resolutionOrder"] == ["body.ellipsoid"],
        "seamEvaluatedAfterContact": seam["kernel"].endswith("_solve_distance"),
        "finite": seam["finite"],
    }
    measurement = {"contact": contact, "seam": seam}
    return _report(
        6,
        "seam_near_body_contact",
        measurement,
        checks,
        bool(contact["maximumPenetrationBeforeMeters"] > 0.0),
    )


def _transfer(revision: int) -> dict[str, Any]:
    source = base_transfer_fixture()
    _, audit = apply_revision(source, revision)
    checks = {
        "massTransfer": audit["checks"]["massConserved"],
        "uvTransfer": audit["checks"]["uvTransferred"],
        "materialTransfer": audit["checks"]["materialTransferred"],
        "sourceTransfer": audit["checks"]["sourceCoordinatesTransferred"],
        "bindingTransfer": audit["checks"]["bindingCoordinatesTransferred"],
        "semanticSeamTransfer": audit["checks"]["semanticSeamCorrespondenceComplete"],
        "openingTransfer": audit["checks"]["openingPreserved"],
        "topology": audit["checks"]["topologyValid"],
        "triangleQuality": audit["checks"]["minimumAngle"],
    }
    return _report(
        7,
        "constrained_remesh_attribute_transfer",
        audit,
        checks,
        bool(audit["provenanceMutationChangesIdentity"] and audit["allNegativeMutationsDetected"]),
    )


def _compliance_mutation(
    positions: list[tuple[float, float, float]], a: int, b: int, baseline: float
) -> bool:
    mutated = run_constraint_kernel(
        positions, [constraint(a, b, entity_id="mutated", compliance=1e3)]
    )
    return bool(mutated["maximumFinalResidualMeters"] > baseline * 1000.0)


def _weight_mutation(baseline: dict[str, Any], positions: list[tuple[float, float, float]]) -> bool:
    mutated = run_constraint_kernel(positions, [constraint(0, 2, entity_id="mutated.weight")])
    return bool(mutated["positions"] != baseline["positions"])


def _report(
    ordinal: int,
    fixture_id: str,
    measurements: dict[str, Any],
    checks: dict[str, bool],
    mutation: bool,
) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "fixtureId": fixture_id,
        "candidateIndependent": True,
        "qualificationEligible": False,
        "productionKernelExecuted": True,
        "measurements": measurements,
        "checks": checks,
        "negativeMutationDetected": mutation,
        "status": "pass" if all(checks.values()) and mutation else "fail",
    }


def _unit(value: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(item * item for item in value))
    return cast(tuple[float, float, float], tuple(item / length for item in value))
