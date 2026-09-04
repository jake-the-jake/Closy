from __future__ import annotations

from closy_forge.simulation.reference_cloth_solver import SOLVER_VERSION
from closy_forge.solver_material_v2.specimens import (
    default_specimen,
    run_garment_motion,
    run_specimen,
)
from closy_forge.solver_material_v2.units import FIELD_ORDER, denormalize_fields


def test_coupon_executes_canonical_geometric_xpbd_route() -> None:
    material = denormalize_fields({field: 0.5 for field in FIELD_ORDER})
    specimen = default_specimen(
        "warp_extension",
        load_scale=1.0,
        mesh=(3, 3),
        time_step_s=1 / 60,
        step_count=3,
        solver_iterations=2,
    )
    row = run_specimen(
        "warp_extension",
        material,
        specimen,
        tuple_id="test-tuple",
        observation_id="test-observation",
        canonical_digits=8,
    )
    assert row["solverVersion"] == SOLVER_VERSION
    assert row["mesh"]["vertexCount"] == 9
    assert row["mesh"]["triangleCount"] == 8
    assert row["initialStateMeters"] != row["finalStateMeters"]
    assert row["diagnostics"]["solverTermination"] == "completed"
    assert row["observables"]["appliedForceNewtons"] > 0.0


def test_contact_specimens_are_distinct_and_restitution_is_active() -> None:
    low = {field: 0.5 for field in FIELD_ORDER}
    high = dict(low)
    low["restitution"], high["restitution"] = 0.1, 0.9
    specimen = default_specimen(
        "impact_rebound",
        load_scale=1.0,
        mesh=(3, 3),
        time_step_s=1 / 60,
        step_count=3,
        solver_iterations=2,
    )
    rows = [
        run_specimen(
            "impact_rebound",
            denormalize_fields(fields),
            specimen,
            tuple_id="contact",
            observation_id=f"contact-{index}",
            canonical_digits=8,
        )
        for index, fields in enumerate((low, high))
    ]
    assert (
        rows[1]["observables"]["reboundVelocityMetersPerSecond"]
        > rows[0]["observables"]["reboundVelocityMetersPerSecond"]
    )
    assert rows[0]["diagnostics"]["contactEventCount"] > 0


def test_all_three_garments_retain_solver_trajectory_and_package_identity() -> None:
    material = denormalize_fields({field: 0.5 for field in FIELD_ORDER})
    for family in ("tshirt", "sleeveless_top", "simple_skirt"):
        motion = run_garment_motion(
            family,
            "motion-00",
            material,
            tuple_id="test-motion",
            canonical_digits=8,
        )
        assert motion["trajectoryMeters"]
        assert motion["packageIdentity"]
        assert motion["solverVersion"] == SOLVER_VERSION
        assert motion["packageProvenance"]["canonicalFamily"] == family
