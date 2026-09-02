from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from closy_forge.phy1_topology_strategy3_diagnosis_v1.production_kernels import (
    constraint,
    run_constraint_kernel,
    run_contact_kernel,
    run_support_kernel,
)
from closy_forge.simulation.reference_cloth_solver import SupportConstraint

Vec3 = tuple[float, float, float]


def execute_public_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    fixture_type = str(fixture.get("fixtureType", ""))
    calls: list[str] = []
    positions = [(0.0, 0.0, 0.0), (0.01, 0.02, 0.0), (0.02, 0.0, 0.0)]
    measurements: dict[str, Any] = {}
    if fixture_type == "coupled_seam_body_contact":
        contact = run_contact_kernel(
            positions,
            [
                {
                    "id": "body.ellipsoid",
                    "type": "ellipsoid",
                    "center": [0.0, 0.0, 0.0],
                    "radii": [0.02, 0.02, 0.02],
                }
            ],
            0.002,
        )
        calls.append(str(contact["kernel"]))
        contact_positions = [
            cast(Vec3, tuple(float(value) for value in row)) for row in contact["positions"]
        ]
        seam = run_constraint_kernel(
            contact_positions,
            [constraint(0, 1, entity_id="seam.coupled")],
        )
        calls.append(str(seam["kernel"]))
        support = run_support_kernel(
            contact_positions,
            SupportConstraint(2, positions[2], 1.0, "support.coupled"),
        )
        calls.append(str(support["kernel"]))
        measurements = {"contact": contact, "seam": seam, "support": support}
    elif fixture_type in {
        "duplicated_seam_normal_separation",
        "curved_seam_tangential_loading",
        "unequal_discretisation_and_seam_ease",
        "three_way_seam_junction",
        "semantic_opening_adjacent_to_seam",
    }:
        constraints = [constraint(0, 1, entity_id=f"seam.{fixture_type}.0")]
        if fixture_type == "three_way_seam_junction":
            constraints.append(constraint(1, 2, entity_id=f"seam.{fixture_type}.1"))
        seam = run_constraint_kernel(positions, constraints)
        calls.append(str(seam["kernel"]))
        measurements = {"seam": seam}
    else:
        measurements = {"reason": "production_constraint_path_not_applicable_to_fixture_class"}
    return {
        "fixtureId": fixture.get("fixtureId"),
        "fixtureType": fixture_type,
        "instrumentationVersion": "closy.production_constraint_path.instrumentation.v2",
        "productionCalls": calls,
        "productionPathExecuted": bool(calls),
        "productionPathRequired": fixture_type
        not in {
            "constrained_remesh_attribute_transfer",
            "repeat_portability_mutation_detection",
        },
        "measurements": measurements,
    }
