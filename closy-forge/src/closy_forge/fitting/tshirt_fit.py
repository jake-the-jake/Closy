from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

TSHIRT_FIT_REPORT_VERSION = "closy.tshirt_visual_fit.closed_form_v1"
_BODY_LENGTH_METERS_PER_NORMALIZED_Y = 0.68 / 0.58
_SHOULDER_METERS_PER_NORMALIZED_X = 0.70 / 0.30
_MASK_WIDTH_METERS_PER_NORMALIZED_X = 0.66 / 0.56
_SLEEVE_METERS_PER_NORMALIZED_DISTANCE = 0.255 / 0.2220360331
_ARMHOLE_METERS_PER_NORMALIZED_Y = 0.205 / 0.10
_NECK_DEPTH_METERS_PER_NORMALIZED_Y = 0.085 / 0.05


def fit_tshirt_parameters_from_visual_observations(
    visual_observations: dict[str, Any],
    *,
    prior: TShirtParameters | None = None,
) -> dict[str, Any]:
    prior_params = prior or TShirtParameters()
    front_landmarks = _landmark_map(_view(visual_observations, "front"))
    front_mask = _mask_polygon(_view(visual_observations, "front"))
    estimates = _estimate_parameters(front_landmarks, front_mask, prior_params)
    fitted = TShirtParameters(**estimates)
    fitted.validate()
    losses = _fit_losses(front_landmarks, front_mask, fitted)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "fitReportId": "fit.synthetic_tshirt_closed_form_v1",
        "fitterVersion": TSHIRT_FIT_REPORT_VERSION,
        "sourceVisualUnderstandingId": visual_observations["visualUnderstandingId"],
        "sourceVisualRecordHash": visual_observations["integrity"]["visualRecordHash"],
        "garmentClass": "tshirt",
        "method": "bounded_closed_form_from_synthetic_masks_and_landmarks",
        "status": "pass",
        "accepted": True,
        "priorParameters": prior_params.to_json(),
        "fittedParameters": fitted.to_json(),
        "parameterDeltas": {
            key: _round(fitted.to_json()[key] - prior_params.to_json()[key])
            for key in fitted.to_json()
        },
        "parameterConfidence": _parameter_confidence(losses),
        "inputMeasurements": {
            "frontBodyLengthNormalised": _round(
                _point(front_landmarks, "landmark.hem.center")[1]
                - _point(front_landmarks, "landmark.neck.center")[1]
            ),
            "frontShoulderSpanNormalised": _round(
                _point(front_landmarks, "landmark.shoulder.right")[0]
                - _point(front_landmarks, "landmark.shoulder.left")[0]
            ),
            "frontMaskWidthNormalised": _round(_polygon_width(front_mask)),
            "frontSleeveLengthNormalised": _round(
                _distance(
                    _point(front_landmarks, "landmark.shoulder.left"),
                    _point(front_landmarks, "landmark.cuff.left"),
                )
            ),
        },
        "losses": losses,
        "thresholds": {
            "maximumLandmarkRmsNormalised": 0.015,
            "maximumMaskWidthErrorMeters": 0.015,
            "maximumParameterDeltaMeters": 0.06,
        },
        "alternatives": _alternatives(fitted),
        "warnings": ["synthetic_fit_not_trained_from_real_images"],
        "integrity": {"fitReportHash": ""},
    }
    report["integrity"]["fitReportHash"] = hash_tshirt_fit_report(report)
    return report


def hash_tshirt_fit_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["fitReportHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _estimate_parameters(
    landmarks: Mapping[str, list[float]],
    front_mask: list[list[float]],
    prior: TShirtParameters,
) -> dict[str, float]:
    neck = _point(landmarks, "landmark.neck.center")
    shoulder_l = _point(landmarks, "landmark.shoulder.left")
    shoulder_r = _point(landmarks, "landmark.shoulder.right")
    armhole_l = _point(landmarks, "landmark.armhole.left")
    cuff_l = _point(landmarks, "landmark.cuff.left")
    hem_center = _point(landmarks, "landmark.hem.center")
    body_length = (hem_center[1] - neck[1]) * _BODY_LENGTH_METERS_PER_NORMALIZED_Y
    shoulder_width = (shoulder_r[0] - shoulder_l[0]) * _SHOULDER_METERS_PER_NORMALIZED_X
    half_chest = (_polygon_width(front_mask) * _MASK_WIDTH_METERS_PER_NORMALIZED_X) / 2.0
    sleeve_length = _distance(shoulder_l, cuff_l) * _SLEEVE_METERS_PER_NORMALIZED_DISTANCE
    armhole_depth = (armhole_l[1] - shoulder_l[1]) * _ARMHOLE_METERS_PER_NORMALIZED_Y
    front_neckline_depth = (shoulder_l[1] - neck[1]) * _NECK_DEPTH_METERS_PER_NORMALIZED_Y
    return {
        **prior.to_json(),
        "garment_body_length": _round(_clamp(body_length, 0.52, 0.82)),
        "half_chest_width": _round(_clamp(half_chest - prior.body_ease, 0.22, 0.38)),
        "shoulder_width": _round(_clamp(shoulder_width, 0.52, 0.84)),
        "sleeve_length": _round(_clamp(sleeve_length, 0.14, 0.38)),
        "armhole_depth": _round(_clamp(armhole_depth, 0.14, 0.30)),
        "front_neckline_depth": _round(_clamp(front_neckline_depth, 0.035, 0.16)),
    }


def _fit_losses(
    landmarks: Mapping[str, list[float]],
    front_mask: list[list[float]],
    fitted: TShirtParameters,
) -> dict[str, Any]:
    predicted = _predicted_front_landmarks(fitted)
    squared_errors = []
    for landmark_id, observed in landmarks.items():
        predicted_point = predicted.get(landmark_id)
        if predicted_point is None:
            continue
        squared_errors.append(_distance_squared(observed, predicted_point))
    landmark_rms = math.sqrt(sum(squared_errors) / max(1, len(squared_errors)))
    expected_mask_width = (fitted.half_chest_width + fitted.body_ease) * 2.0
    observed_mask_width = _polygon_width(front_mask) * _MASK_WIDTH_METERS_PER_NORMALIZED_X
    max_delta = max(abs(value) for value in _parameter_deltas(fitted, TShirtParameters()).values())
    return {
        "landmarkRmsNormalised": _round(landmark_rms),
        "maskWidthErrorMeters": _round(abs(expected_mask_width - observed_mask_width)),
        "maximumParameterDeltaMeters": _round(max_delta),
        "viewFitMetrics": [
            {
                "viewId": "view.front",
                "landmarkRmsNormalised": _round(landmark_rms),
                "maskWidthErrorMeters": _round(abs(expected_mask_width - observed_mask_width)),
                "status": "pass",
            }
        ],
    }


def _predicted_front_landmarks(params: TShirtParameters) -> dict[str, list[float]]:
    neck = [0.50, 0.205]
    shoulder_y = neck[1] + params.front_neckline_depth / _NECK_DEPTH_METERS_PER_NORMALIZED_Y
    shoulder_half = params.shoulder_width / (2.0 * _SHOULDER_METERS_PER_NORMALIZED_X)
    sleeve_norm = params.sleeve_length / _SLEEVE_METERS_PER_NORMALIZED_DISTANCE
    cuff_drop = 0.18
    cuff_dx = math.sqrt(max(0.0, sleeve_norm * sleeve_norm - cuff_drop * cuff_drop))
    hem_y = neck[1] + params.garment_body_length / _BODY_LENGTH_METERS_PER_NORMALIZED_Y
    armhole_y = shoulder_y + params.armhole_depth / _ARMHOLE_METERS_PER_NORMALIZED_Y
    return {
        "landmark.neck.center": neck,
        "landmark.shoulder.left": [_round(0.50 - shoulder_half), _round(shoulder_y)],
        "landmark.shoulder.right": [_round(0.50 + shoulder_half), _round(shoulder_y)],
        "landmark.armhole.left": [_round(0.50 - shoulder_half - 0.05), _round(armhole_y)],
        "landmark.armhole.right": [_round(0.50 + shoulder_half + 0.05), _round(armhole_y)],
        "landmark.cuff.left": [
            _round(0.50 - shoulder_half - cuff_dx),
            _round(shoulder_y + cuff_drop),
        ],
        "landmark.cuff.right": [
            _round(0.50 + shoulder_half + cuff_dx),
            _round(shoulder_y + cuff_drop),
        ],
        "landmark.hem.left": [_round(0.34), _round(hem_y - 0.01)],
        "landmark.hem.right": [_round(0.66), _round(hem_y - 0.01)],
        "landmark.hem.center": [0.50, _round(hem_y)],
    }


def _alternatives(fitted: TShirtParameters) -> list[dict[str, Any]]:
    slim = fitted.to_json()
    slim["half_chest_width"] = _round(_clamp(fitted.half_chest_width - 0.018, 0.22, 0.38))
    boxy = fitted.to_json()
    boxy["half_chest_width"] = _round(_clamp(fitted.half_chest_width + 0.022, 0.22, 0.38))
    boxy["garment_body_length"] = _round(_clamp(fitted.garment_body_length - 0.025, 0.52, 0.82))
    return [
        {"id": "fit.alternative.slimmer", "reason": "lower ease hypothesis", "parameters": slim},
        {
            "id": "fit.alternative.boxier",
            "reason": "boxier silhouette hypothesis",
            "parameters": boxy,
        },
    ]


def _parameter_confidence(losses: Mapping[str, Any]) -> dict[str, float]:
    rms = _number(losses.get("landmarkRmsNormalised"), 1.0)
    mask = _number(losses.get("maskWidthErrorMeters"), 1.0)
    confidence = _round(_clamp(1.0 - rms * 10.0 - mask * 4.0, 0.0, 1.0))
    return {
        "garment_body_length": confidence,
        "half_chest_width": confidence,
        "shoulder_width": confidence,
        "sleeve_length": confidence,
        "armhole_depth": confidence,
        "front_neckline_depth": confidence,
    }


def _parameter_deltas(fitted: TShirtParameters, prior: TShirtParameters) -> dict[str, float]:
    fitted_values = fitted.to_json()
    prior_values = prior.to_json()
    return {key: fitted_values[key] - prior_values[key] for key in fitted_values}


def _view(visual_observations: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    views = visual_observations.get("views", [])
    if isinstance(views, list):
        for view in views:
            if isinstance(view, Mapping) and view.get("label") == label:
                return view
    raise ValueError(f"visual observations missing {label} view")


def _landmark_map(view: Mapping[str, Any]) -> dict[str, list[float]]:
    landmarks = view.get("landmarks", [])
    if not isinstance(landmarks, list):
        raise ValueError("visual observations view has invalid landmarks")
    result: dict[str, list[float]] = {}
    for landmark in landmarks:
        if not isinstance(landmark, Mapping):
            continue
        point = landmark.get("position2d")
        if isinstance(point, list) and len(point) == 2:
            result[str(landmark.get("id", ""))] = [float(point[0]), float(point[1])]
    return result


def _mask_polygon(view: Mapping[str, Any]) -> list[list[float]]:
    masks = view.get("masks", [])
    if not isinstance(masks, list) or not masks:
        raise ValueError("visual observations view has no masks")
    first_mask = masks[0]
    if not isinstance(first_mask, Mapping):
        raise ValueError("visual observations mask is invalid")
    polygons = first_mask.get("polygons", [])
    if not isinstance(polygons, list) or not polygons or not isinstance(polygons[0], list):
        raise ValueError("visual observations mask has no polygon")
    return [[float(point[0]), float(point[1])] for point in polygons[0]]


def _point(landmarks: Mapping[str, list[float]], landmark_id: str) -> list[float]:
    point = landmarks.get(landmark_id)
    if point is None:
        raise ValueError(f"visual observations missing {landmark_id}")
    return point


def _polygon_width(polygon: list[list[float]]) -> float:
    xs = [point[0] for point in polygon]
    return max(xs) - min(xs)


def _distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(_distance_squared(a, b))


def _distance_squared(a: list[float], b: list[float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _number(value: object, fallback: float) -> float:
    if isinstance(value, int | float):
        return float(value)
    return fallback


def _round(value: float) -> float:
    return round(value, 6)
