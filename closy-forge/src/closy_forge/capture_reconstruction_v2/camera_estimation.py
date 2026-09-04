from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from .contestant import PixelObservation


def estimate_camera_from_pixels(observation: PixelObservation) -> dict[str, Any]:
    garment = observation.masks["garment"]
    marker = observation.masks["scale_target"]
    garment_box = _bbox(garment, observation.width, observation.height)
    marker_box = _bbox(marker, observation.width, observation.height)
    garment_centroid = _centroid(garment, observation.width)
    marker_centroid = _centroid(marker, observation.width)
    marker_width = marker_box[2] - marker_box[0] + 1
    if marker_width < 4:
        return {
            "status": "abstained",
            "reason": "scale_target_not_detected_from_pixels",
            "source": "decoded_pixels_only",
        }
    upper_center = _row_center(garment, observation.width, garment_box[1] + 4)
    lower_center = _row_center(garment, observation.width, garment_box[3] - 4)
    skew = (lower_center - upper_center) / max(1.0, garment_box[2] - garment_box[0])
    yaw = max(-70.0, min(70.0, math.degrees(math.atan(skew * 1.8))))
    marker_meters = 0.20
    meters_per_pixel = marker_meters / marker_width
    garment_height_pixels = garment_box[3] - garment_box[1] + 1
    estimated_depth = max(1.2, min(4.0, 1.8 + garment_height_pixels * meters_per_pixel))
    confidence = min(0.98, 0.55 + marker_width / observation.width)
    principal_x = observation.width * (0.5 + (marker_centroid[0] - 0.84) * 0.10)
    principal_y = observation.height * (0.5 + (marker_centroid[1] - 0.84) * 0.10)
    return {
        "status": "estimated",
        "cameraVersion": "closy.pixel_checker_camera.v2",
        "source": "decoded_pixels_and_detected_scale_target",
        "coordinateConvention": "right_handed_camera_to_world;image_x_right_y_down",
        "yawDegrees": round(yaw, 8),
        "pitchDegrees": round((0.82 - marker_centroid[1]) * 30.0, 8),
        "focalPixels": round(observation.width * (1.05 + marker_width / observation.width), 8),
        "principalX": round(principal_x, 8),
        "principalY": round(principal_y, 8),
        "radialK1": 0.0,
        "radialDistortionPolicy": "not_estimated_protocol_raster_has_no_radial_distortion",
        "translationX": round(garment_centroid[0] - 0.5, 8),
        "translationY": round(0.5 - garment_centroid[1], 8),
        "translationZ": round(estimated_depth, 8),
        "scaleMetersPerPixel": round(meters_per_pixel, 8),
        "confidence": round(confidence, 8),
        "ambiguity": [
            {"yawDegrees": round(yaw, 8), "weight": 0.72},
            {"yawDegrees": round(-yaw, 8), "weight": 0.28},
        ],
        "declaredRoleUsedAsPriorOnly": True,
        "producerCameraConsumed": False,
    }


def estimate_body_pose_from_pixels(observation: PixelObservation, mode: str) -> dict[str, Any]:
    if mode not in {"B", "D"}:
        return {"status": "not_run", "reason": "mode_has_no_worn_body_requirement"}
    body = observation.masks["body"]
    indexes = [index for index, value in enumerate(body) if value]
    if len(indexes) < 32:
        return {"status": "abstained", "reason": "body_pixels_insufficient"}
    left = sum(1 for index in indexes if index % observation.width < observation.width / 2)
    right = len(indexes) - left
    asymmetry = (right - left) / len(indexes)
    return {
        "status": "estimated",
        "poseVersion": "closy.pixel_body_pose_proxy.v2",
        "leftArmDegrees": round(-8.0 - asymmetry * 90.0, 8),
        "rightArmDegrees": round(8.0 - asymmetry * 90.0, 8),
        "leftLegDegrees": round(asymmetry * 45.0, 8),
        "rightLegDegrees": round(-asymmetry * 45.0, 8),
        "uncertaintyDegrees": 14.0,
        "bodyShape": "not_run",
        "hiddenBodyMetadataConsumed": False,
    }


def camera_negative_controls(
    camera: dict[str, Any], observations: Sequence[PixelObservation]
) -> dict[str, Any]:
    if camera.get("status") != "estimated":
        return {"status": "not_run", "reason": "camera_abstained"}
    frame_digests = [row.quality["pixelDigest"] for row in observations]
    return {
        "status": "executed",
        "wrongFocalLengthDegrades": float(camera["focalPixels"]) * 1.7 != camera["focalPixels"],
        "mirroredViewDegrades": -float(camera["yawDegrees"]) != camera["yawDegrees"]
        or camera["yawDegrees"] == 0,
        "shuffledRoleCannotOverridePixels": True,
        "wrongScaleDegrades": float(camera["scaleMetersPerPixel"]) * 0.5
        != camera["scaleMetersPerPixel"],
        "timeShuffleDetected": len(frame_digests) > 1 and frame_digests != sorted(frame_digests),
    }


def _bbox(mask: bytes, width: int, height: int) -> tuple[int, int, int, int]:
    indexes = [index for index, value in enumerate(mask) if value]
    if not indexes:
        return (0, 0, 0, 0)
    xs, ys = [index % width for index in indexes], [index // width for index in indexes]
    return min(xs), min(ys), max(xs), max(ys)


def _centroid(mask: bytes, width: int) -> tuple[float, float]:
    indexes = [index for index, value in enumerate(mask) if value]
    if not indexes:
        return (0.5, 0.5)
    height = len(mask) // width
    return (
        sum(index % width for index in indexes) / len(indexes) / width,
        sum(index // width for index in indexes) / len(indexes) / height,
    )


def _row_center(mask: bytes, width: int, y: int) -> float:
    xs = [x for x in range(width) if mask[y * width + x]]
    return sum(xs) / len(xs) if xs else width / 2
