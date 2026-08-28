from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, dist
from typing import Any


@dataclass(frozen=True)
class IndependentMeasurementReport:
    height_m: float
    shoulder_width_m: float
    chest_circumference_m: float
    waist_circumference_m: float
    hip_circumference_m: float
    arm_length_m: float
    leg_length_m: float
    torso_length_m: float
    posture_degrees: float
    authority: str = "independent_collision_sample_geometry_oracle_v1"


def measure_collision_samples(samples: dict[str, Any]) -> IndependentMeasurementReport:
    landmarks = _mapping(samples.get("landmarks"))
    rings = _mapping(samples.get("rings"))
    floor = _point(landmarks.get("floor"))
    head = _point(landmarks.get("headTop"))
    pelvis = _point(landmarks.get("pelvis"))
    chest = _point(landmarks.get("chest"))
    shoulder_left = _point(landmarks.get("shoulderL"))
    shoulder_right = _point(landmarks.get("shoulderR"))
    wrist_left = _point(landmarks.get("wristL"))
    return IndependentMeasurementReport(
        height_m=round(head[1] - floor[1], 9),
        shoulder_width_m=round(dist(shoulder_left, shoulder_right), 9),
        chest_circumference_m=_perimeter(_ring(rings.get("chest"))),
        waist_circumference_m=_perimeter(_ring(rings.get("waist"))),
        hip_circumference_m=_perimeter(_ring(rings.get("hips"))),
        arm_length_m=round(dist(shoulder_left, wrist_left), 9),
        leg_length_m=round(pelvis[1] - floor[1], 9),
        torso_length_m=round(shoulder_left[1] - pelvis[1], 9),
        posture_degrees=round(degrees(atan2(chest[2] - pelvis[2], chest[1] - pelvis[1])), 9),
    )


def _perimeter(points: list[tuple[float, float, float]]) -> float:
    return round(
        sum(dist(point, points[(index + 1) % len(points)]) for index, point in enumerate(points)), 9
    )


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("measurement_oracle_mapping_invalid")
    return value


def _point(value: object) -> tuple[float, float, float]:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise ValueError("measurement_oracle_point_invalid")
    point = tuple(float(component) for component in value)
    return (point[0], point[1], point[2])


def _ring(value: object) -> list[tuple[float, float, float]]:
    if not isinstance(value, list) or len(value) < 8:
        raise ValueError("measurement_oracle_ring_invalid")
    return [_point(point) for point in value]
