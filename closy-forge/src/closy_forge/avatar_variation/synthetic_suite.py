from __future__ import annotations

from dataclasses import asdict, dataclass
from math import cos, pi, sin, tan
from typing import Any, Literal, cast

AVATAR_CAPABILITY_VERSION = "closy.synthetic_avatar_fit.d0.v1"
Posture = Literal["upright", "forward_8deg", "backward_6deg"]
POSTURES: tuple[Posture, ...] = ("upright", "forward_8deg", "backward_6deg")
DECLARED_RANGES: dict[str, tuple[float, float]] = {
    "height_m": (1.62, 2.02),
    "shoulder_width_m": (0.34, 0.52),
    "chest_circumference_m": (0.72, 1.24),
    "waist_circumference_m": (0.58, 1.18),
    "hip_circumference_m": (0.76, 1.30),
    "arm_length_m": (0.50, 0.70),
    "leg_length_m": (0.78, 1.10),
    "torso_length_m": (0.48, 0.68),
    "shape_chest_depth": (-0.16, 0.16),
    "shape_hip_depth": (-0.16, 0.16),
}
FIT_THRESHOLDS: dict[str, float] = {
    "measurement_abs_m": 0.000_001,
    "measurement_angle_deg": 0.000_001,
    "minimum_top_ease_m": 0.035,
    "maximum_top_ease_m": 0.065,
    "minimum_waist_ease_m": 0.015,
    "minimum_hip_ease_m": 0.020,
    "minimum_radial_clearance_m": 0.0025,
    "maximum_opening_placement_error_m": 0.012,
    "minimum_fit_confidence": 0.90,
}
_SCALAR_FIELDS = tuple(DECLARED_RANGES)


@dataclass(frozen=True)
class AvatarMeasurements:
    height_m: float = 1.82
    shoulder_width_m: float = 0.42
    chest_circumference_m: float = 0.92
    waist_circumference_m: float = 0.76
    hip_circumference_m: float = 0.98
    arm_length_m: float = 0.60
    leg_length_m: float = 0.84
    torso_length_m: float = 0.57
    shape_chest_depth: float = 0.0
    shape_hip_depth: float = 0.0
    posture: Posture = "upright"


@dataclass(frozen=True)
class SyntheticAvatarCase:
    case_id: str
    measurements: AvatarMeasurements
    coverage_kind: Literal["baseline", "boundary", "pairwise", "posture"]
    varied_fields: tuple[str, ...]
    measurement_authority: str = "project_authored_analytic_collision_body_v1"
    confidence: float = 1.0
    correction_operations: tuple[str, ...] = ()
    collision_body_linkage: str = "collision.synthetic_avatar_analytic_v1"
    provenance: str = "project_authored_synthetic_no_private_identity"


def build_frozen_avatar_suite() -> tuple[SyntheticAvatarCase, ...]:
    baseline = AvatarMeasurements()
    cases = [SyntheticAvatarCase("avatar.baseline", baseline, "baseline", ())]
    for field in _SCALAR_FIELDS:
        minimum, maximum = DECLARED_RANGES[field]
        cases.append(
            SyntheticAvatarCase(
                f"avatar.boundary.{field}.min",
                _replace_measurements(baseline, **{field: minimum}),
                "boundary",
                (field,),
            )
        )
        cases.append(
            SyntheticAvatarCase(
                f"avatar.boundary.{field}.max",
                _replace_measurements(baseline, **{field: maximum}),
                "boundary",
                (field,),
            )
        )
    for left_index, left in enumerate(_SCALAR_FIELDS):
        for right_index, right in enumerate(_SCALAR_FIELDS[left_index + 1 :], left_index + 1):
            left_value = DECLARED_RANGES[left][(left_index + right_index) % 2]
            right_value = DECLARED_RANGES[right][(left_index + right_index + 1) % 2]
            candidate = _replace_measurements(baseline, **{left: left_value, right: right_value})
            try:
                _validate_measurements(candidate)
            except ValueError:
                candidate = _replace_measurements(
                    baseline,
                    **{
                        left: DECLARED_RANGES[left][(left_index + right_index + 1) % 2],
                        right: DECLARED_RANGES[right][(left_index + right_index) % 2],
                    },
                )
            cases.append(
                SyntheticAvatarCase(
                    f"avatar.pairwise.{left}.{right}",
                    candidate,
                    "pairwise",
                    (left, right),
                )
            )
    for posture in POSTURES[1:]:
        cases.append(
            SyntheticAvatarCase(
                f"avatar.posture.{posture}",
                _replace_measurements(baseline, posture=posture),
                "posture",
                ("posture",),
            )
        )
        for index, field in enumerate(_SCALAR_FIELDS):
            value = DECLARED_RANGES[field][index % 2]
            cases.append(
                SyntheticAvatarCase(
                    f"avatar.pairwise.{field}.{posture}",
                    _replace_measurements(baseline, posture=posture, **{field: value}),
                    "pairwise",
                    (field, "posture"),
                )
            )
    return tuple(cases)


def build_collision_samples(measurements: AvatarMeasurements) -> dict[str, Any]:
    _validate_measurements(measurements)
    floor_y = 0.0
    head_y = measurements.height_m
    hip_y = measurements.leg_length_m
    shoulder_y = min(head_y - 0.10, hip_y + measurements.torso_length_m)
    waist_y = hip_y + measurements.torso_length_m * 0.38
    chest_y = hip_y + measurements.torso_length_m * 0.72
    posture_degrees = {"upright": 0.0, "forward_8deg": 8.0, "backward_6deg": -6.0}[
        measurements.posture
    ]
    chest_z = tan(posture_degrees * pi / 180.0) * (chest_y - hip_y)
    rings = {
        "chest": _ring(
            measurements.chest_circumference_m,
            chest_y,
            chest_z,
            0.72 + measurements.shape_chest_depth,
        ),
        "waist": _ring(measurements.waist_circumference_m, waist_y, chest_z * 0.45, 0.70),
        "hips": _ring(
            measurements.hip_circumference_m,
            hip_y,
            0.0,
            0.74 + measurements.shape_hip_depth,
        ),
    }
    half_shoulder = measurements.shoulder_width_m * 0.5
    arm_drop = measurements.arm_length_m
    half_hip = _ring_half_width(rings["hips"])
    landmarks = {
        "floor": (0.0, floor_y, 0.0),
        "headTop": (chest_z, head_y, 0.0),
        "pelvis": (0.0, hip_y, 0.0),
        "chest": (0.0, chest_y, chest_z),
        "waist": (0.0, waist_y, chest_z * 0.45),
        "shoulderL": (-half_shoulder, shoulder_y, chest_z),
        "shoulderR": (half_shoulder, shoulder_y, chest_z),
        "wristL": (-half_shoulder, shoulder_y - arm_drop, chest_z),
        "wristR": (half_shoulder, shoulder_y - arm_drop, chest_z),
        "hipL": (-half_hip, hip_y, 0.0),
        "hipR": (half_hip, hip_y, 0.0),
        "ankleL": (-half_hip * 0.62, floor_y + 0.07, 0.0),
        "ankleR": (half_hip * 0.62, floor_y + 0.07, 0.0),
    }
    return {
        "schemaVersion": 1,
        "bodyVersion": "closy.synthetic_collision_samples.v1",
        "caseMeasurements": asdict(measurements),
        "landmarks": landmarks,
        "rings": rings,
        "authority": "project_authored_analytic_collision_body_v1",
        "containsPrivateData": False,
        "containsStableIdentity": False,
    }


def _ring(
    circumference: float, y: float, center_z: float, depth_ratio: float
) -> list[tuple[float, float, float]]:
    unit = [(cos(2.0 * pi * index / 64.0), sin(2.0 * pi * index / 64.0)) for index in range(64)]
    perimeter = sum(
        ((unit[(index + 1) % 64][0] - point[0]) ** 2 + (unit[(index + 1) % 64][1] - point[1]) ** 2)
        ** 0.5
        for index, point in enumerate(unit)
    )
    width_scale = circumference / perimeter
    depth_scale = width_scale * depth_ratio
    distorted = [(point[0] * width_scale, point[1] * depth_scale) for point in unit]
    distorted_perimeter = sum(
        (
            (distorted[(index + 1) % 64][0] - point[0]) ** 2
            + (distorted[(index + 1) % 64][1] - point[1]) ** 2
        )
        ** 0.5
        for index, point in enumerate(distorted)
    )
    correction = circumference / distorted_perimeter
    return [(x * correction, y, center_z + z * correction) for x, z in distorted]


def _ring_half_width(ring: list[tuple[float, float, float]]) -> float:
    return (max(point[0] for point in ring) - min(point[0] for point in ring)) * 0.5


def _validate_measurements(measurements: AvatarMeasurements) -> None:
    values = asdict(measurements)
    for field, (minimum, maximum) in DECLARED_RANGES.items():
        value = values[field]
        if not isinstance(value, float) or value < minimum or value > maximum:
            raise ValueError(f"unsupported_avatar_extreme:{field}")
    if measurements.posture not in POSTURES:
        raise ValueError("unsupported_avatar_posture")
    if measurements.leg_length_m + measurements.torso_length_m > measurements.height_m - 0.10:
        raise ValueError("unsupported_avatar_proportion:vertical_sum")


def _replace_measurements(
    baseline: AvatarMeasurements, **updates: float | Posture
) -> AvatarMeasurements:
    values = asdict(baseline)
    values.update(updates)
    return AvatarMeasurements(**cast(Any, values))
