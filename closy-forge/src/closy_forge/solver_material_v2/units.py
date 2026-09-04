from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class MaterialSI:
    warp_stiffness_n_m: float
    weft_stiffness_n_m: float
    shear_stiffness_n_m: float
    bend_stiffness_nm: float
    surface_density_kg_m2: float
    damping_ratio: float
    friction_coefficient: float
    restitution_coefficient: float
    thickness_m: float


@dataclass(frozen=True)
class SpecimenSI:
    length_m: float
    width_m: float
    thickness_m: float
    mesh_columns: int
    mesh_rows: int
    time_step_s: float
    step_count: int
    solver_iterations: int
    force_n: float
    displacement_m: float
    initial_velocity_m_s: float
    acceleration_m_s2: float
    gravity_m_s2: float
    contact_offset_m: float


# These are dimensional protocol ranges, not measured fabric claims.  Normalized
# estimator coordinates map bijectively into explicitly unit-bearing synthetic SI.
FIELD_RANGES: dict[str, tuple[float, float, str]] = {
    "warp": (0.5, 100.0, "N/m"),
    "weft": (0.5, 90.0, "N/m"),
    "shear": (0.25, 40.0, "N/m"),
    "bend": (0.005, 1.0, "N*m"),
    "density": (0.075, 0.360, "kg/m^2"),
    "damping": (0.025, 0.420, "ratio"),
    "friction": (0.08, 0.82, "coefficient"),
    "restitution": (0.0, 0.48, "coefficient"),
}
FIELD_ORDER = tuple(FIELD_RANGES)
SIX_FIELD_ORDER = FIELD_ORDER[:6]


def denormalize_fields(fields: dict[str, float], *, thickness_m: float = 0.0014) -> MaterialSI:
    validate_normalized_fields(fields)
    values = {
        field: low + float(fields[field]) * (high - low)
        for field, (low, high, _unit) in FIELD_RANGES.items()
    }
    return MaterialSI(
        warp_stiffness_n_m=values["warp"],
        weft_stiffness_n_m=values["weft"],
        shear_stiffness_n_m=values["shear"],
        bend_stiffness_nm=values["bend"],
        surface_density_kg_m2=values["density"],
        damping_ratio=values["damping"],
        friction_coefficient=values["friction"],
        restitution_coefficient=values["restitution"],
        thickness_m=thickness_m,
    )


def normalize_material(material: MaterialSI) -> dict[str, float]:
    raw = asdict(material)
    names = {
        "warp": "warp_stiffness_n_m",
        "weft": "weft_stiffness_n_m",
        "shear": "shear_stiffness_n_m",
        "bend": "bend_stiffness_nm",
        "density": "surface_density_kg_m2",
        "damping": "damping_ratio",
        "friction": "friction_coefficient",
        "restitution": "restitution_coefficient",
    }
    return {
        field: (float(raw[name]) - low) / (high - low)
        for field, (low, high, _unit) in FIELD_RANGES.items()
        for name in (names[field],)
    }


def material_to_solver_payload(material: MaterialSI) -> dict[str, float]:
    normalized = normalize_material(material)
    return {
        "surfaceDensityKgM2": material.surface_density_kg_m2,
        "stretchStiffnessNPerM": material.warp_stiffness_n_m,
        "warpStiffnessNPerM": material.warp_stiffness_n_m,
        "weftStiffnessNPerM": material.weft_stiffness_n_m,
        "shearStiffnessNPerM": material.shear_stiffness_n_m,
        "bendStiffnessNm": material.bend_stiffness_nm,
        "dampingRatio": material.damping_ratio,
        "frictionCoefficient": material.friction_coefficient,
        "restitutionCoefficient": material.restitution_coefficient,
        "thicknessMeters": material.thickness_m,
        "collisionClearanceMeters": max(0.001, material.thickness_m * 1.5),
        "selfCollisionThicknessMeters": material.thickness_m,
        "stretchStiffness": 0.15 + 0.80 * normalized["warp"],
        "warpStretchStiffness": 0.15 + 0.80 * normalized["warp"],
        "weftStretchStiffness": 0.15 + 0.80 * normalized["weft"],
        "shearStiffness": 0.12 + 0.82 * normalized["shear"],
        "bendStiffness": 0.08 + 0.84 * normalized["bend"],
    }


def validate_normalized_fields(fields: dict[str, float]) -> None:
    if tuple(fields) != FIELD_ORDER and set(fields) != set(FIELD_ORDER):
        raise ValueError("normalized_material_field_set_invalid")
    if any(
        not isfinite(float(value)) or not 0.0 <= float(value) <= 1.0 for value in fields.values()
    ):
        raise ValueError("normalized_material_field_value_invalid")


def validate_specimen(specimen: SpecimenSI) -> None:
    values = asdict(specimen)
    if any(not isfinite(float(value)) for value in values.values()):
        raise ValueError("specimen_non_finite")
    if min(specimen.length_m, specimen.width_m, specimen.thickness_m) <= 0.0:
        raise ValueError("specimen_dimension_invalid")
    if specimen.mesh_columns < 2 or specimen.mesh_rows < 2:
        raise ValueError("specimen_mesh_resolution_invalid")
    if specimen.time_step_s <= 0.0 or specimen.step_count <= 0 or specimen.solver_iterations <= 0:
        raise ValueError("specimen_time_or_iteration_invalid")
    if specimen.contact_offset_m < 0.0:
        raise ValueError("specimen_contact_offset_invalid")


def unit_registry() -> dict[str, Any]:
    return {
        "coordinate": "m",
        "time": "s",
        "surfaceDensity": "kg/m^2",
        "gsmConversion": "1 kg/m^2 = 1000 g/m^2",
        "force": "N",
        "displacement": "m",
        "velocity": "m/s",
        "acceleration": "m/s^2",
        "warpWeftShearStiffness": "N/m",
        "bendStiffness": "N*m",
        "damping": "dimensionless_ratio",
        "friction": "dimensionless_coefficient",
        "restitution": "dimensionless_coefficient",
        "gravity": "m/s^2",
        "contactOffset": "m",
        "fieldRanges": {
            field: {"minimum": low, "maximum": high, "unit": unit}
            for field, (low, high, unit) in FIELD_RANGES.items()
        },
    }
