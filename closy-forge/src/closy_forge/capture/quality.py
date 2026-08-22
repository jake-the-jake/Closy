from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from closy_forge.capture.source_records import hash_capture_record

CAPTURE_QUALITY_SCORER_VERSION = "closy.capture_quality_scorer.v1"
CAPTURE_QUALITY_THRESHOLD = 0.70

_DIMENSION_WEIGHTS = {
    "garmentCoverage": 0.20,
    "focusSharpness": 0.12,
    "exposureReliability": 0.10,
    "backgroundSeparation": 0.10,
    "occlusionSafety": 0.12,
    "semanticLandmarkCoverage": 0.16,
    "scaleObservability": 0.10,
    "viewDiversity": 0.10,
}


def score_capture_record(record: dict[str, Any]) -> dict[str, Any]:
    views = _views(record)
    source_hash = hash_capture_record(record)
    dimension_scores = _dimension_scores(views)
    weighted_score = sum(dimension["score"] * dimension["weight"] for dimension in dimension_scores)
    overall_score = _round(weighted_score)
    overall_status = (
        "pass"
        if overall_score >= CAPTURE_QUALITY_THRESHOLD
        and all(dimension["status"] != "fail" for dimension in dimension_scores)
        else "fail"
    )
    return {
        "schemaVersion": 1,
        "qualityReportId": "capture_quality.synthetic_tshirt_reference_v1",
        "scorerVersion": CAPTURE_QUALITY_SCORER_VERSION,
        "sourceRecordId": str(record.get("recordId", "")),
        "sourceRecordHash": source_hash,
        "overallStatus": overall_status,
        "overallScore": overall_score,
        "qualityThreshold": CAPTURE_QUALITY_THRESHOLD,
        "viewCount": len(views),
        "viewScores": [_view_score(view) for view in views],
        "dimensionScores": dimension_scores,
        "policy": {
            "requiresUserConsent": False,
            "externalApiUseAllowed": False,
            "trainingUseAllowed": False,
            "rasterImagesAvailable": False,
        },
        "warnings": ["raster_images_unavailable_phase_02"],
        "nextRequiredArtifacts": [
            "editable_mask_records",
            "source_landmark_observations",
            "texture_projection_evidence",
        ],
    }


def _dimension_scores(views: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    scores = {
        "garmentCoverage": _mean_measurement(views, "garmentCoverage"),
        "focusSharpness": _mean_measurement(views, "blurScore"),
        "exposureReliability": _mean_measurement(views, "exposureBalance"),
        "backgroundSeparation": _mean_measurement(views, "backgroundSeparation"),
        "occlusionSafety": 1.0 - _mean_measurement(views, "occlusionFraction"),
        "semanticLandmarkCoverage": _mean_measurement(views, "landmarkVisibility"),
        "scaleObservability": _mean_measurement(views, "scaleConfidence"),
        "viewDiversity": _view_diversity_score(views),
    }
    return [
        {
            "id": key,
            "score": _round(_clamp(scores[key])),
            "weight": weight,
            "status": _status(scores[key]),
        }
        for key, weight in _DIMENSION_WEIGHTS.items()
    ]


def _view_score(view: Mapping[str, Any]) -> dict[str, Any]:
    measurements = _mapping(view.get("qualityMeasurements"))
    occlusion_safety = 1.0 - _number(measurements.get("occlusionFraction"), 1.0)
    score = (
        _number(measurements.get("garmentCoverage"), 0.0) * 0.25
        + _number(measurements.get("blurScore"), 0.0) * 0.15
        + _number(measurements.get("exposureBalance"), 0.0) * 0.12
        + _number(measurements.get("backgroundSeparation"), 0.0) * 0.12
        + occlusion_safety * 0.16
        + _number(measurements.get("landmarkVisibility"), 0.0) * 0.12
        + _number(measurements.get("scaleConfidence"), 0.0) * 0.08
    )
    return {
        "viewId": str(view.get("viewId", "")),
        "label": str(view.get("label", "")),
        "score": _round(_clamp(score)),
        "status": _status(score),
    }


def _view_diversity_score(views: list[Mapping[str, Any]]) -> float:
    if len(views) < 2:
        return 0.0
    azimuths = [_number(_mapping(view.get("camera")).get("azimuthDegrees"), 0.0) for view in views]
    span = max(azimuths) - min(azimuths)
    label_count = len({str(view.get("label", "")) for view in views})
    span_score = min(1.0, span / 220.0)
    label_score = min(1.0, label_count / 4.0)
    return span_score * 0.7 + label_score * 0.3


def _mean_measurement(views: list[Mapping[str, Any]], key: str) -> float:
    if not views:
        return 0.0
    values = [_number(_mapping(view.get("qualityMeasurements")).get(key), 0.0) for view in views]
    return sum(values) / len(values)


def _views(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_views = record.get("views")
    if not isinstance(raw_views, list):
        return []
    return [_mapping(view) for view in raw_views]


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _number(value: object, fallback: float) -> float:
    if isinstance(value, int | float):
        return float(value)
    return fallback


def _status(score: float) -> str:
    if score >= CAPTURE_QUALITY_THRESHOLD:
        return "pass"
    if score >= 0.55:
        return "warn"
    return "fail"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _round(value: float) -> float:
    return round(value, 6)
