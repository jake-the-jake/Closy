from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any, cast

from closy_forge.phy1_topology_strategy3_diagnosis_v1.production_kernels import (
    constraint,
    run_constraint_kernel,
    run_contact_kernel,
    run_support_kernel,
)
from closy_forge.simulation.reference_cloth_solver import SupportConstraint

Vec3 = tuple[float, float, float]

_PORTABLE_FIELD_CLASSES = {
    "positions": ("meters", 1_000_000_000),
    "initialResidualsMeters": ("meters", 1_000_000_000),
    "finalResidualsMeters": ("meters", 1_000_000_000),
    "maximumInitialResidualMeters": ("meters", 1_000_000_000),
    "maximumFinalResidualMeters": ("meters", 1_000_000_000),
    "residualBeforeMeters": ("meters", 1_000_000_000),
    "residualAfterMeters": ("meters", 1_000_000_000),
    "seamNormalResidualMeters": ("meters", 1_000_000_000),
    "seamTangentialResidualMeters": ("meters", 1_000_000_000),
    "maximumPenetrationBeforeMeters": ("meters", 1_000_000_000),
    "maximumPenetrationAfterMeters": ("meters", 1_000_000_000),
    "storedEnergyJoules": ("joules", 1_000_000_000_000),
    "maximumStoredEnergyJoules": ("joules", 1_000_000_000_000),
    "impulseNewtonSeconds": ("newton_seconds", 1_000_000_000_000),
    "totalAbsoluteImpulseNewtonSeconds": ("newton_seconds", 1_000_000_000_000),
    "deltaLambda": ("solver_lagrange_multiplier", 1_000_000_000_000),
    "residualRatio": ("ratio", 1_000_000_000_000),
}


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
        "numericLayer": "raw_execution_local_binary64",
        "measurements": measurements,
    }


def portable_production_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project raw telemetry into declared portable field classes for committed evidence."""
    converted = _portable_value(dict(report), field_name=None)
    if not isinstance(converted, dict):
        raise ValueError("portable_production_report_invalid")
    converted["numericLayer"] = "portable_fixed_point_committed"
    converted["rawTelemetry"] = {
        "committed": False,
        "scope": "execution_local_noncanonical",
        "reason": "binary64_kernel_telemetry_can_vary_across_supported_runtimes",
    }
    converted["portableNumericPolicy"] = {
        "policyVersion": "closy.production_telemetry.field_class_fixed_point.v1",
        "roundingMode": "ROUND_HALF_EVEN",
        "fieldClasses": {
            key: {"unit": unit, "integerScalePerUnit": scale}
            for key, (unit, scale) in sorted(_PORTABLE_FIELD_CLASSES.items())
        },
    }
    return converted


def _portable_value(value: Any, *, field_name: str | None) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, str | int):
        return value
    if isinstance(value, float):
        if field_name not in _PORTABLE_FIELD_CLASSES:
            raise ValueError(f"unclassified_production_float:{field_name}")
        unit, scale = _PORTABLE_FIELD_CLASSES[field_name]
        with localcontext() as context:
            context.prec = 80
            integer = int(
                (Decimal.from_float(value) * Decimal(scale)).to_integral_value(
                    rounding=ROUND_HALF_EVEN
                )
            )
        return {
            "integerValue": integer,
            "unit": unit,
            "integerScalePerUnit": scale,
        }
    if isinstance(value, Mapping):
        return {str(key): _portable_value(item, field_name=str(key)) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_portable_value(item, field_name=field_name) for item in value]
    raise ValueError(f"unsupported_production_telemetry_type:{type(value).__name__}")
