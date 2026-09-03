from __future__ import annotations

from closy_forge.solver_material_v1.forward_solver import COUPON_FAMILIES, run_forward_coupon
from closy_forge.solver_material_v1.production_solver import run_production_coupon
from closy_forge.solver_material_v1.protocol import load_protocol

FIELDS = {
    "warp": 0.55,
    "weft": 0.45,
    "shear": 0.35,
    "bend": 0.40,
    "density": 0.50,
    "damping": 0.30,
    "friction": 0.45,
    "restitution": 0.20,
}


def test_frozen_protocol_meets_minimum_denominators() -> None:
    protocol = load_protocol()
    assert len(protocol["supportedFields"]) == 8
    assert protocol["denominators"]["developmentTuples"] == 48
    assert protocol["denominators"]["lockedTestTuples"] == 16
    assert protocol["resultClassification"].startswith("solver_space_parameter_recovery")


def test_both_discretizations_execute_finite_trajectories() -> None:
    for family in COUPON_FAMILIES:
        forward = run_forward_coupon(FIELDS, family, 0.55)
        production = run_production_coupon(FIELDS, family, 0.55)
        assert forward["diagnostics"]["finite"] is True
        assert production["diagnostics"]["finite"] is True
        assert forward["trajectoryDigest"] != production["trajectoryDigest"]


def test_parameter_intervention_changes_trajectory() -> None:
    lower = dict(FIELDS, warp=0.2)
    upper = dict(FIELDS, warp=0.8)
    assert (
        run_forward_coupon(lower, "warp_tensile", 0.55)["trajectoryDigest"]
        != (run_forward_coupon(upper, "warp_tensile", 0.55)["trajectoryDigest"])
    )
