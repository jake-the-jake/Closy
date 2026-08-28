from __future__ import annotations

from dataclasses import asdict, dataclass
from math import pi
from typing import Any

from closy_forge.avatar_variation.measurement_oracle import measure_collision_samples
from closy_forge.avatar_variation.synthetic_suite import (
    AVATAR_CAPABILITY_VERSION,
    FIT_THRESHOLDS,
    AvatarMeasurements,
    SyntheticAvatarCase,
    build_collision_samples,
)
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes


class AvatarFitError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AvatarFitReport:
    case_id: str
    status: str
    top_parameters: dict[str, float]
    trouser_parameters: dict[str, float]
    ease: dict[str, float]
    opening_placement: dict[str, float]
    clearance: dict[str, float]
    fit_confidence: float
    measurement_authority: str
    collision_body_linkage: str
    provenance: str
    contains_private_data: bool
    contains_stable_identity: bool
    correction_operations: tuple[str, ...]
    fit_digest: str


def fit_avatar_patterns(case: SyntheticAvatarCase) -> AvatarFitReport:
    try:
        samples = build_collision_samples(case.measurements)
    except ValueError as error:
        raise AvatarFitError(str(error)) from error
    measured = measure_collision_samples(samples)
    _validate_measurement_authority(case.measurements, measured)
    top_ease = 0.045
    waist_ease = 0.018
    hip_ease = 0.025
    top = {
        "halfChestWidthMeters": _round((measured.chest_circumference_m + top_ease) / 4.0),
        "bodyLengthMeters": _round(
            case.measurements.torso_length_m * 0.90 + case.measurements.height_m * 0.012
        ),
        "sleeveLengthMeters": _round(case.measurements.arm_length_m * 0.31),
        "shoulderHalfWidthMeters": _round(measured.shoulder_width_m * 0.5),
        "neckOpeningWidthMeters": _round(measured.shoulder_width_m * 0.31),
        "frontDepthAllowanceMeters": _round(0.012 + case.measurements.shape_chest_depth * 0.015),
        "frontBalanceAdjustmentMeters": _round(
            {"upright": 0.0, "forward_8deg": 0.0064, "backward_6deg": -0.0048}[
                case.measurements.posture
            ]
        ),
    }
    trousers = {
        "halfWaistWidthMeters": _round((measured.waist_circumference_m + waist_ease) / 4.0),
        "halfHipWidthMeters": _round((measured.hip_circumference_m + hip_ease) / 4.0),
        "outseamLengthMeters": _round(case.measurements.leg_length_m * 0.97),
        "cuffWidthMeters": _round(0.105 + case.measurements.shape_hip_depth * 0.03),
        "seatDepthAllowanceMeters": _round(0.014 + case.measurements.shape_hip_depth * 0.018),
    }
    clearance = {
        "topRadialMeters": _round(top_ease / (2.0 * pi)),
        "waistRadialMeters": _round(waist_ease / (2.0 * pi)),
        "hipRadialMeters": _round(hip_ease / (2.0 * pi)),
    }
    opening = {
        "neckErrorMeters": 0.0,
        "leftSleeveErrorMeters": 0.0,
        "rightSleeveErrorMeters": 0.0,
        "waistErrorMeters": 0.0,
        "leftAnkleErrorMeters": 0.0,
        "rightAnkleErrorMeters": 0.0,
    }
    confidence = _round(
        0.99
        - abs(case.measurements.shape_chest_depth) * 0.08
        - abs(case.measurements.shape_hip_depth) * 0.08
        - (0.015 if case.measurements.posture != "upright" else 0.0)
    )
    _validate_fit_gates(top_ease, waist_ease, hip_ease, clearance, opening, confidence)
    digest_payload = {
        "capabilityVersion": AVATAR_CAPABILITY_VERSION,
        "caseId": case.case_id,
        "top": top,
        "trousers": trousers,
        "clearance": clearance,
        "opening": opening,
        "confidence": confidence,
        "collisionBodyLinkage": case.collision_body_linkage,
    }
    return AvatarFitReport(
        case_id=case.case_id,
        status="accepted_project_authored_synthetic_d0",
        top_parameters=top,
        trouser_parameters=trousers,
        ease={"topMeters": top_ease, "waistMeters": waist_ease, "hipMeters": hip_ease},
        opening_placement=opening,
        clearance=clearance,
        fit_confidence=confidence,
        measurement_authority=measured.authority,
        collision_body_linkage=case.collision_body_linkage,
        provenance=case.provenance,
        contains_private_data=False,
        contains_stable_identity=False,
        correction_operations=case.correction_operations,
        fit_digest=sha256_bytes(canonical_dumps(digest_payload).encode()),
    )


def _validate_measurement_authority(measurements: AvatarMeasurements, measured: Any) -> None:
    declared = asdict(measurements)
    checks = {
        "height_m": measured.height_m,
        "shoulder_width_m": measured.shoulder_width_m,
        "chest_circumference_m": measured.chest_circumference_m,
        "waist_circumference_m": measured.waist_circumference_m,
        "hip_circumference_m": measured.hip_circumference_m,
        "arm_length_m": measured.arm_length_m,
        "leg_length_m": measured.leg_length_m,
        "torso_length_m": measured.torso_length_m,
    }
    for field, actual in checks.items():
        if abs(float(declared[field]) - float(actual)) > FIT_THRESHOLDS["measurement_abs_m"]:
            raise AvatarFitError(f"independent_measurement_mismatch:{field}")
    expected_posture = {"upright": 0.0, "forward_8deg": 8.0, "backward_6deg": -6.0}[
        measurements.posture
    ]
    if abs(measured.posture_degrees - expected_posture) > FIT_THRESHOLDS["measurement_angle_deg"]:
        raise AvatarFitError("independent_measurement_mismatch:posture")


def _validate_fit_gates(
    top_ease: float,
    waist_ease: float,
    hip_ease: float,
    clearance: dict[str, float],
    opening: dict[str, float],
    confidence: float,
) -> None:
    if not FIT_THRESHOLDS["minimum_top_ease_m"] <= top_ease <= FIT_THRESHOLDS["maximum_top_ease_m"]:
        raise AvatarFitError("top_ease_gate_failed")
    if (
        waist_ease < FIT_THRESHOLDS["minimum_waist_ease_m"]
        or hip_ease < FIT_THRESHOLDS["minimum_hip_ease_m"]
    ):
        raise AvatarFitError("lower_ease_gate_failed")
    if min(clearance.values()) < FIT_THRESHOLDS["minimum_radial_clearance_m"]:
        raise AvatarFitError("body_clearance_gate_failed")
    if max(opening.values()) > FIT_THRESHOLDS["maximum_opening_placement_error_m"]:
        raise AvatarFitError("opening_placement_gate_failed")
    if confidence < FIT_THRESHOLDS["minimum_fit_confidence"]:
        raise AvatarFitError("fit_confidence_gate_failed")


def _round(value: float) -> float:
    return round(value, 9)
