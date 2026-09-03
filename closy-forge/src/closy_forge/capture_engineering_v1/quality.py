from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PixelObservation:
    width: int
    height: int
    foreground: frozenset[int]
    foreground_bbox: tuple[int, int, int, int]
    foreground_centroid: tuple[float, float]
    focus_score: float
    exposure_balance: float
    clipping_score: float
    foreground_coverage: float
    background_separation: float
    mask_confidence: float
    landmarks: dict[str, tuple[float, float]]

    def portable(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "foregroundPixelCount": len(self.foreground),
            "foregroundBoundingBoxPixels": list(self.foreground_bbox),
            "foregroundCentroidNormalized": [round(value, 8) for value in self.foreground_centroid],
            "quality": {
                "focusScore": round(self.focus_score, 8),
                "exposureBalance": round(self.exposure_balance, 8),
                "clippingScore": round(self.clipping_score, 8),
                "foregroundCoverage": round(self.foreground_coverage, 8),
                "backgroundSeparation": round(self.background_separation, 8),
                "maskConfidence": round(self.mask_confidence, 8),
            },
            "landmarksNormalized": {
                name: [round(point[0], 8), round(point[1], 8)]
                for name, point in sorted(self.landmarks.items())
            },
        }


def observe_pixels(width: int, height: int, rgba: bytes) -> PixelObservation:
    if width <= 1 or height <= 1 or len(rgba) != width * height * 4:
        raise ValueError("rgba_dimensions_invalid")
    background = _background_colour(width, height, rgba)
    distances = [_distance(_rgb(rgba, index), background) for index in range(width * height)]
    # A garment can occupy most of the frame, so a high image-wide percentile can
    # itself be foreground. Cap the adaptive threshold instead of erasing those
    # valid high-coverage captures.
    threshold = max(18.0, min(64.0, _percentile(distances, 0.62) * 0.45))
    foreground = frozenset(
        index for index, distance in enumerate(distances) if distance > threshold
    )
    if not foreground:
        raise ValueError("foreground_not_observed")
    xs = [index % width for index in foreground]
    ys = [index // width for index in foreground]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    centroid = (
        sum(xs) / len(xs) / max(1, width - 1),
        sum(ys) / len(ys) / max(1, height - 1),
    )
    luma = [_luma(_rgb(rgba, index)) for index in range(width * height)]
    focus = _laplacian_focus(width, height, luma)
    mean_luma = sum(luma) / len(luma)
    exposure = max(0.0, 1.0 - abs(mean_luma - 127.5) / 127.5)
    unclipped = sum(8.0 < value < 247.0 for value in luma) / len(luma)
    coverage = len(foreground) / (width * height)
    separation = min(1.0, sum(distances[index] for index in foreground) / len(foreground) / 180.0)
    confidence = min(1.0, separation * min(1.0, coverage / 0.12))
    return PixelObservation(
        width=width,
        height=height,
        foreground=foreground,
        foreground_bbox=bbox,
        foreground_centroid=centroid,
        focus_score=focus,
        exposure_balance=exposure,
        clipping_score=unclipped,
        foreground_coverage=coverage,
        background_separation=separation,
        mask_confidence=confidence,
        landmarks=_landmarks(width, height, bbox),
    )


def apply_corrections(
    observation: PixelObservation, corrections: Sequence[Mapping[str, Any]]
) -> PixelObservation:
    bbox = observation.foreground_bbox
    landmarks = dict(observation.landmarks)
    for correction in corrections:
        operation = str(correction.get("operation", ""))
        if operation == "replace_bbox":
            values = correction.get("value")
            if (
                not isinstance(values, Sequence)
                or isinstance(values, str | bytes)
                or len(values) != 4
            ):
                raise ValueError("correction_bbox_invalid")
            bbox = tuple(int(value) for value in values)  # type: ignore[assignment]
            if not (0 <= bbox[0] <= bbox[2] < observation.width):
                raise ValueError("correction_bbox_x_invalid")
            if not (0 <= bbox[1] <= bbox[3] < observation.height):
                raise ValueError("correction_bbox_y_invalid")
        elif operation == "replace_landmark":
            name = str(correction.get("name", ""))
            values = correction.get("value")
            if (
                not name
                or not isinstance(values, Sequence)
                or isinstance(values, str | bytes)
                or len(values) != 2
            ):
                raise ValueError("correction_landmark_invalid")
            point = (float(values[0]), float(values[1]))
            if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in point):
                raise ValueError("correction_landmark_out_of_range")
            landmarks[name] = point
        else:
            raise ValueError("correction_operation_unsupported")
    centroid = (
        (bbox[0] + bbox[2]) / 2 / max(1, observation.width - 1),
        (bbox[1] + bbox[3]) / 2 / max(1, observation.height - 1),
    )
    return PixelObservation(
        width=observation.width,
        height=observation.height,
        foreground=observation.foreground,
        foreground_bbox=bbox,
        foreground_centroid=centroid,
        focus_score=observation.focus_score,
        exposure_balance=observation.exposure_balance,
        clipping_score=observation.clipping_score,
        foreground_coverage=observation.foreground_coverage,
        background_separation=observation.background_separation,
        mask_confidence=observation.mask_confidence,
        landmarks=landmarks,
    )


def quality_acceptance(
    observation: PixelObservation, thresholds: Mapping[str, object]
) -> dict[str, Any]:
    checks = {
        "focus": observation.focus_score >= _number(thresholds["minimumFocusScore"]),
        "exposure": observation.exposure_balance >= _number(thresholds["minimumExposureBalance"]),
        "foreground": observation.foreground_coverage
        >= _number(thresholds["minimumForegroundCoverage"]),
        "background": observation.background_separation
        >= _number(thresholds["minimumBackgroundSeparation"]),
    }
    return {
        "status": "accepted" if all(checks.values()) else "rejected",
        "checks": checks,
        "reasons": sorted(name for name, passed in checks.items() if not passed),
    }


def view_consistency(observations: Sequence[PixelObservation]) -> float:
    if len(observations) < 2:
        return 1.0
    coverages = [item.foreground_coverage for item in observations]
    spread = max(coverages) - min(coverages)
    return max(0.0, 1.0 - spread / max(0.01, sum(coverages) / len(coverages)))


def _background_colour(width: int, height: int, rgba: bytes) -> tuple[float, float, float]:
    corners = (0, width - 1, (height - 1) * width, width * height - 1)
    channels = list(zip(*(_rgb(rgba, index) for index in corners), strict=True))
    return (
        sum(channels[0]) / len(channels[0]),
        sum(channels[1]) / len(channels[1]),
        sum(channels[2]) / len(channels[2]),
    )


def _rgb(rgba: bytes, index: int) -> tuple[int, int, int]:
    offset = index * 4
    return (rgba[offset], rgba[offset + 1], rgba[offset + 2])


def _distance(left: tuple[int, int, int], right: tuple[float, float, float]) -> float:
    return math.sqrt(sum((float(a) - b) ** 2 for a, b in zip(left, right, strict=True)))


def _luma(rgb: tuple[int, int, int]) -> float:
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722


def _laplacian_focus(width: int, height: int, luma: Sequence[float]) -> float:
    values: list[float] = []
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            index = y * width + x
            laplacian = (
                4 * luma[index]
                - luma[index - 1]
                - luma[index + 1]
                - luma[index - width]
                - luma[index + width]
            )
            values.append(laplacian)
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return min(1.0, variance / 2_500.0)


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _landmarks(
    width: int, height: int, bbox: tuple[int, int, int, int]
) -> dict[str, tuple[float, float]]:
    left, top, right, bottom = bbox
    center = (left + right) / 2
    box_height = max(1, bottom - top)

    def normalized_point(x: float, y: float) -> tuple[float, float]:
        return (x / max(1, width - 1), y / max(1, height - 1))

    return {
        "neckCenter": normalized_point(center, top),
        "shoulderL": normalized_point(left, top + box_height * 0.14),
        "shoulderR": normalized_point(right, top + box_height * 0.14),
        "waistL": normalized_point(left + (right - left) * 0.12, top + box_height * 0.72),
        "waistR": normalized_point(right - (right - left) * 0.12, top + box_height * 0.72),
        "hemCenter": normalized_point(center, bottom),
    }


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("quality_threshold_not_numeric")
    return float(value)
