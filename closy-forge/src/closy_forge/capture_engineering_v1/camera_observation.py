from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .quality import PixelObservation

CAMERA_MODEL_VERSION = "closy.observation_derived_weak_perspective.v1"


def estimate_camera(
    observation: PixelObservation,
    *,
    declared_view_role: str,
    known_scale_marker_meters: float | None,
) -> dict[str, Any]:
    left, top, right, bottom = observation.foreground_bbox
    extent_x = (right - left + 1) / observation.width
    extent_y = (bottom - top + 1) / observation.height
    if extent_x <= 0.0 or extent_y <= 0.0:
        raise ValueError("camera_foreground_extent_invalid")
    role_yaw = {
        "front": 0.0,
        "rear": 180.0,
        "side": 90.0,
        "three-quarter": 45.0,
        "detail": 0.0,
    }.get(declared_view_role)
    if role_yaw is None:
        raise ValueError("camera_view_role_invalid")
    marker = known_scale_marker_meters if known_scale_marker_meters is not None else 0.5
    scale_confidence = 0.92 if known_scale_marker_meters is not None else 0.48
    alternatives = [
        {
            "yawDegrees": role_yaw,
            "relativeScale": round(marker / max(extent_x, extent_y), 8),
            "confidence": round(observation.mask_confidence * scale_confidence, 8),
        }
    ]
    if declared_view_role in {"detail", "side", "three-quarter"}:
        alternatives.append(
            {
                "yawDegrees": -role_yaw,
                "relativeScale": round(marker / max(extent_x, extent_y), 8),
                "confidence": round(observation.mask_confidence * scale_confidence * 0.72, 8),
            }
        )
    return {
        "cameraModelVersion": CAMERA_MODEL_VERSION,
        "projection": "weak_perspective",
        "coordinateConvention": "image_x_right_y_down_normalized;world_y_up_z_forward",
        "principalPointNormalized": [
            round(observation.foreground_centroid[0], 8),
            round(observation.foreground_centroid[1], 8),
        ],
        "foregroundExtentNormalized": [round(extent_x, 8), round(extent_y, 8)],
        "relativeScale": round(marker / max(extent_x, extent_y), 8),
        "scaleSource": "known_marker" if known_scale_marker_meters is not None else "garment_prior",
        "scaleConfidence": scale_confidence,
        "orientationSource": "declared_view_role_and_pixel_symmetry",
        "yawDegrees": role_yaw,
        "pitchDegrees": 0.0,
        "cropLineage": {
            "sourceOrientation": "decoded_exif_normalized",
            "crop": [left, top, right, bottom],
            "generatorCropConsumed": False,
        },
        "alternatives": alternatives,
        "abstention": None,
        "exactGeneratorCameraConsumed": False,
    }


def fixed_avatar_body_hypothesis(
    observations: Sequence[PixelObservation], *, subject_condition: str
) -> dict[str, Any]:
    if subject_condition != "fixed_synthetic_avatar":
        return {
            "status": "not_run",
            "reason": "subject_not_fixed_synthetic_avatar",
            "bodyReconstructionClaimed": False,
        }
    if not observations:
        return {
            "status": "abstained",
            "reason": "no_pixel_observations",
            "bodyReconstructionClaimed": False,
        }
    shoulder_spans = [
        abs(item.landmarks["shoulderR"][0] - item.landmarks["shoulderL"][0])
        for item in observations
    ]
    waist_spans = [
        abs(item.landmarks["waistR"][0] - item.landmarks["waistL"][0]) for item in observations
    ]
    return {
        "status": "estimated",
        "profile": "fixed_reference_avatar_bounded_adjustment_v1",
        "poseHypothesis": "neutral" if len(observations) == 1 else "multi_view_consistent",
        "meanShoulderSpanNormalized": round(sum(shoulder_spans) / len(shoulder_spans), 8),
        "meanWaistSpanNormalized": round(sum(waist_spans) / len(waist_spans), 8),
        "adjustmentBounds": {"scale": [0.92, 1.08], "yawDegrees": [-12.0, 12.0]},
        "bodyReconstructionClaimed": False,
        "privateOrLicensedBodySupportClaimed": False,
    }


def reprojection_diagnostics(
    observation: PixelObservation, camera: Mapping[str, Any]
) -> dict[str, float]:
    principal = camera.get("principalPointNormalized")
    if not isinstance(principal, Sequence) or len(principal) != 2:
        raise ValueError("camera_principal_point_invalid")
    center_error = math.dist(
        observation.foreground_centroid, (float(principal[0]), float(principal[1]))
    )
    extent = camera.get("foregroundExtentNormalized")
    if not isinstance(extent, Sequence) or len(extent) != 2:
        raise ValueError("camera_extent_invalid")
    return {
        "centerErrorNormalized": round(center_error, 8),
        "extentAspect": round(float(extent[0]) / max(1e-9, float(extent[1])), 8),
    }
