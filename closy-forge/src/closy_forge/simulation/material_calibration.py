from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from math import sqrt
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.simulation.material_physics import (
    hash_fabric_descriptor,
    validate_fabric_descriptor,
)

CALIBRATION_VERSION = "closy.material_calibration.d0.v1"
CALIBRATION_SOLVER_VERSION = "closy.material_fixture_cpu.v1"


def run_material_calibration(descriptor: dict[str, Any]) -> dict[str, Any]:
    """Execute bounded numerical fixtures that isolate each D0 material response."""

    validate_fabric_descriptor(descriptor)
    fixtures = [
        _sensitivity_fixture(
            fixture_id="calibration.stretch_patch_v1",
            parameter="warpStretchStiffness",
            expected_order="higher_stiffness_reduces_extension",
            simulate=_stretch_response,
            tolerance=1e-12,
        ),
        _sensitivity_fixture(
            fixture_id="calibration.shear_patch_v1",
            parameter="shearStiffness",
            expected_order="higher_stiffness_reduces_shear_displacement",
            simulate=_shear_response,
            tolerance=1e-12,
        ),
        _sensitivity_fixture(
            fixture_id="calibration.bend_cantilever_v1",
            parameter="bendStiffness",
            expected_order="higher_bend_stiffness_reduces_tip_deflection",
            simulate=_bend_response,
            tolerance=1e-12,
        ),
        _sensitivity_fixture(
            fixture_id="calibration.damped_oscillator_v1",
            parameter="dampingRatio",
            expected_order="higher_damping_reduces_residual_amplitude",
            simulate=_damping_response,
            tolerance=1e-12,
        ),
        _sensitivity_fixture(
            fixture_id="calibration.gravity_sag_chain_v1",
            parameter="arealDensity",
            expected_order="higher_density_increases_gravity_sag",
            simulate=_gravity_sag_response,
            tolerance=1e-12,
            increasing=True,
        ),
        _sensitivity_fixture(
            fixture_id="calibration.floor_collision_v1",
            parameter="collisionClearance",
            expected_order="higher_clearance_increases_resting_height",
            simulate=_collision_response,
            tolerance=1e-12,
            increasing=True,
        ),
    ]
    accepted = all(
        fixture["orderingObserved"] and fixture["withinTolerance"] for fixture in fixtures
    )
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "calibrationVersion": CALIBRATION_VERSION,
        "calibrationId": "material_calibration.public_tops_d0_v1",
        "solverVersion": CALIBRATION_SOLVER_VERSION,
        "inputDescriptor": deepcopy(descriptor),
        "inputDescriptorHash": hash_fabric_descriptor(descriptor),
        "fixtures": fixtures,
        "readiness": {
            "actualNumericalFixturesRun": True,
            "acceptedForD0CalibrationFixtures": accepted,
            "acceptedAsMeasuredRealFabric": False,
            "acceptedForProductionGpuSolver": False,
        },
        "truth": {
            "fixtureKind": "deterministic_project_authored_public_numerical_fixture",
            "realFabricMeasurementRun": False,
            "learnedInferenceRun": False,
            "privateUserMaterialEstimationRun": False,
        },
        "integrity": {"reportHash": ""},
    }
    report["integrity"]["reportHash"] = _hash_report(report)
    return report


def _sensitivity_fixture(
    *,
    fixture_id: str,
    parameter: str,
    expected_order: str,
    simulate: Callable[[float], float],
    tolerance: float,
    increasing: bool = False,
) -> dict[str, Any]:
    base = _CALIBRATION_BASE_VALUES[parameter]
    inputs = [base * 0.5, base, base * 2.0]
    responses = [simulate(value) for value in inputs]
    ordered = (
        responses[0] + tolerance < responses[1] and responses[1] + tolerance < responses[2]
        if increasing
        else responses[0] > responses[1] + tolerance and responses[1] > responses[2] + tolerance
    )
    result: dict[str, Any] = {
        "fixtureId": fixture_id,
        "parameterUnderTest": parameter,
        "parameterUnit": _CALIBRATION_UNITS[parameter],
        "parameterValues": [_round(value) for value in inputs],
        "measuredResponse": [_round(value) for value in responses],
        "responseUnit": _RESPONSE_UNITS[fixture_id],
        "expectedQualitativeOrdering": expected_order,
        "orderingObserved": ordered,
        "tolerance": tolerance,
        "withinTolerance": ordered and all(value >= 0.0 for value in responses),
        "settings": {
            "timeStepSeconds": 1.0 / 240.0,
            "stepCount": 720,
            "integration": "semi_implicit_euler_or_bounded_projection",
        },
        "solverVersion": CALIBRATION_SOLVER_VERSION,
        "resultHash": "",
    }
    result["resultHash"] = _hash_result(result)
    return result


def _stretch_response(stiffness: float) -> float:
    position = 1.0
    velocity = 0.0
    dt = 1.0 / 240.0
    mass = 0.16
    for _ in range(720):
        spring_force = -stiffness * (position - 1.0)
        velocity += (12.0 + spring_force - 0.9 * velocity) / mass * dt
        position += velocity * dt
    return abs(position - 1.0)


def _shear_response(stiffness: float) -> float:
    displacement = 0.0
    velocity = 0.0
    dt = 1.0 / 240.0
    for _ in range(720):
        restoring = -stiffness * displacement
        velocity += (5.0 + restoring - 0.7 * velocity) / 0.12 * dt
        displacement += velocity * dt
    return abs(displacement)


def _bend_response(stiffness: float) -> float:
    # A three-link cantilever projection: bend torque counters a fixed tip load.
    angle = 0.0
    angular_velocity = 0.0
    dt = 1.0 / 240.0
    effective_stiffness = stiffness * 9000.0
    for _ in range(720):
        torque = 0.16 - effective_stiffness * angle - 0.12 * angular_velocity
        angular_velocity += torque / 0.08 * dt
        angle += angular_velocity * dt
    return abs(0.45 * angle)


def _damping_response(damping_ratio: float) -> float:
    position = 0.08
    velocity = 0.0
    dt = 1.0 / 240.0
    stiffness = 18.0
    mass = 0.16
    damping = 2.0 * damping_ratio * sqrt(stiffness * mass)
    peak = 0.0
    for step in range(720):
        velocity += (-stiffness * position - damping * velocity) / mass * dt
        position += velocity * dt
        if step >= 600:
            peak = max(peak, abs(position))
    return peak


def _gravity_sag_response(areal_density: float) -> float:
    nodes = [0.0] * 7
    stiffness = 14.0
    dt = 1.0 / 240.0
    velocities = [0.0] * len(nodes)
    for _ in range(720):
        next_nodes = list(nodes)
        for index in range(1, len(nodes) - 1):
            laplacian = nodes[index - 1] - 2.0 * nodes[index] + nodes[index + 1]
            force = stiffness * laplacian - areal_density * 9.81
            velocities[index] = (velocities[index] + force * dt) * 0.985
            next_nodes[index] += velocities[index] * dt
        nodes = next_nodes
    return abs(min(nodes))


def _collision_response(clearance: float) -> float:
    height = 0.18
    velocity = 0.0
    dt = 1.0 / 240.0
    for _ in range(720):
        velocity -= 9.81 * dt
        height += velocity * dt
        if height < clearance:
            height = clearance
            velocity = 0.0
    return height


_CALIBRATION_BASE_VALUES = {
    "warpStretchStiffness": 550.0,
    "shearStiffness": 120.0,
    "bendStiffness": 0.0018,
    "dampingRatio": 0.18,
    "arealDensity": 0.16,
    "collisionClearance": 0.006,
}

_CALIBRATION_UNITS = {
    "warpStretchStiffness": "N/m",
    "shearStiffness": "N/m",
    "bendStiffness": "N*m",
    "dampingRatio": "ratio",
    "arealDensity": "kg/m^2",
    "collisionClearance": "m",
}

_RESPONSE_UNITS = {
    "calibration.stretch_patch_v1": "m_extension",
    "calibration.shear_patch_v1": "m_lateral_displacement",
    "calibration.bend_cantilever_v1": "m_tip_deflection",
    "calibration.damped_oscillator_v1": "m_residual_amplitude",
    "calibration.gravity_sag_chain_v1": "m_maximum_sag",
    "calibration.floor_collision_v1": "m_resting_height",
}


def _hash_result(result: dict[str, Any]) -> str:
    payload = deepcopy(result)
    payload["resultHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _hash_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    payload["integrity"]["reportHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _round(value: float) -> float:
    return round(float(value), 9)
