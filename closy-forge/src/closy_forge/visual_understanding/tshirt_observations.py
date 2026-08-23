from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

TSHIRT_VISUAL_OBSERVATION_VERSION = "closy.visual_observations.tshirt.synthetic_v1"
TSHIRT_VISUAL_OBSERVATION_ID = "visual.synthetic_tshirt_reference_v1"

REQUIRED_TSHIRT_VISUAL_LANDMARKS = (
    "landmark.neck.center",
    "landmark.shoulder.left",
    "landmark.shoulder.right",
    "landmark.armhole.left",
    "landmark.armhole.right",
    "landmark.cuff.left",
    "landmark.cuff.right",
    "landmark.hem.left",
    "landmark.hem.right",
    "landmark.hem.center",
)

_MASK_POLYGONS = {
    "front": [[0.34, 0.20], [0.66, 0.20], [0.78, 0.42], [0.67, 0.78], [0.33, 0.78], [0.22, 0.42]],
    "back": [[0.33, 0.21], [0.67, 0.21], [0.77, 0.43], [0.68, 0.79], [0.32, 0.79], [0.23, 0.43]],
    "left_three_quarter": [
        [0.39, 0.21],
        [0.66, 0.22],
        [0.74, 0.43],
        [0.63, 0.78],
        [0.36, 0.77],
        [0.27, 0.43],
    ],
    "right_three_quarter": [
        [0.34, 0.22],
        [0.61, 0.21],
        [0.73, 0.43],
        [0.64, 0.77],
        [0.37, 0.78],
        [0.26, 0.43],
    ],
}

_LANDMARKS = {
    "front": {
        "landmark.neck.center": [0.50, 0.205],
        "landmark.shoulder.left": [0.35, 0.255],
        "landmark.shoulder.right": [0.65, 0.255],
        "landmark.armhole.left": [0.30, 0.355],
        "landmark.armhole.right": [0.70, 0.355],
        "landmark.cuff.left": [0.22, 0.435],
        "landmark.cuff.right": [0.78, 0.435],
        "landmark.hem.left": [0.34, 0.775],
        "landmark.hem.right": [0.66, 0.775],
        "landmark.hem.center": [0.50, 0.785],
    },
    "back": {
        "landmark.neck.center": [0.50, 0.215],
        "landmark.shoulder.left": [0.35, 0.265],
        "landmark.shoulder.right": [0.65, 0.265],
        "landmark.armhole.left": [0.30, 0.365],
        "landmark.armhole.right": [0.70, 0.365],
        "landmark.cuff.left": [0.23, 0.445],
        "landmark.cuff.right": [0.77, 0.445],
        "landmark.hem.left": [0.33, 0.785],
        "landmark.hem.right": [0.67, 0.785],
        "landmark.hem.center": [0.50, 0.795],
    },
    "left_three_quarter": {
        "landmark.neck.center": [0.52, 0.215],
        "landmark.shoulder.left": [0.39, 0.265],
        "landmark.shoulder.right": [0.64, 0.275],
        "landmark.armhole.left": [0.34, 0.370],
        "landmark.armhole.right": [0.68, 0.380],
        "landmark.cuff.left": [0.27, 0.455],
        "landmark.cuff.right": [0.73, 0.455],
        "landmark.hem.left": [0.37, 0.775],
        "landmark.hem.right": [0.64, 0.785],
        "landmark.hem.center": [0.51, 0.790],
    },
    "right_three_quarter": {
        "landmark.neck.center": [0.48, 0.215],
        "landmark.shoulder.left": [0.36, 0.275],
        "landmark.shoulder.right": [0.61, 0.265],
        "landmark.armhole.left": [0.32, 0.380],
        "landmark.armhole.right": [0.66, 0.370],
        "landmark.cuff.left": [0.27, 0.455],
        "landmark.cuff.right": [0.73, 0.455],
        "landmark.hem.left": [0.36, 0.785],
        "landmark.hem.right": [0.63, 0.775],
        "landmark.hem.center": [0.49, 0.790],
    },
}


def build_tshirt_visual_observations(capture_record: dict[str, Any]) -> dict[str, Any]:
    source_hash = str(capture_record["immutability"]["sourceRecordHash"])
    views = [_view_observations(view) for view in _capture_views(capture_record)]
    observed_landmarks = sorted(
        {landmark["id"] for view in views for landmark in view["landmarks"]}
    )
    record: dict[str, Any] = {
        "schemaVersion": 1,
        "visualUnderstandingId": TSHIRT_VISUAL_OBSERVATION_ID,
        "stageVersion": TSHIRT_VISUAL_OBSERVATION_VERSION,
        "sourceRecordId": capture_record["recordId"],
        "sourceRecordHash": source_hash,
        "garmentClass": "tshirt",
        "provider": {
            "type": "deterministic_synthetic_fixture",
            "automaticSegmentation": False,
            "interactiveEditable": True,
            "externalApis": False,
            "trainingUse": False,
        },
        "coordinateSpaces": {
            "image": "normalised_image_uv_top_left_origin",
            "garment": "semantic_tshirt_landmark_ids",
            "world": "closy-rh-yup-plus-z-v1",
        },
        "views": views,
        "aggregate": {
            "requiredLandmarks": list(REQUIRED_TSHIRT_VISUAL_LANDMARKS),
            "observedLandmarks": observed_landmarks,
            "maskCount": sum(len(view["masks"]) for view in views),
            "viewLabels": [str(view["label"]) for view in views],
            "meanMaskConfidence": _round(
                sum(mask["confidence"] for view in views for mask in view["masks"])
                / max(1, sum(len(view["masks"]) for view in views))
            ),
            "meanLandmarkConfidence": _round(
                sum(landmark["confidence"] for view in views for landmark in view["landmarks"])
                / max(1, sum(len(view["landmarks"]) for view in views))
            ),
        },
        "warnings": ["synthetic_visual_observations_not_real_segmentation"],
        "integrity": {"visualRecordHash": ""},
    }
    record["integrity"]["visualRecordHash"] = hash_visual_observations(record)
    return record


def hash_visual_observations(record: dict[str, Any]) -> str:
    payload = deepcopy(record)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["visualRecordHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _view_observations(capture_view: Mapping[str, Any]) -> dict[str, Any]:
    label = str(capture_view.get("label", "front"))
    polygon = _MASK_POLYGONS.get(label, _MASK_POLYGONS["front"])
    landmarks = _LANDMARKS.get(label, _LANDMARKS["front"])
    return {
        "viewId": str(capture_view.get("viewId", "")),
        "label": label,
        "camera": capture_view.get("camera", {}),
        "masks": [
            {
                "maskId": f"mask.{label}.target_garment",
                "semanticId": "component.tshirt",
                "representation": "normalised_polygon",
                "coordinateSpace": "image",
                "polygons": [polygon],
                "confidence": 0.88,
                "editable": True,
                "source": "synthetic_fixture_analytic_silhouette",
            }
        ],
        "landmarks": [
            {
                "id": landmark_id,
                "position2d": point,
                "confidence": 0.90,
                "source": "synthetic_fixture_analytic_landmark",
            }
            for landmark_id, point in landmarks.items()
        ],
    }


def _capture_views(capture_record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    views = capture_record.get("views", [])
    if not isinstance(views, list):
        return []
    return [view for view in views if isinstance(view, Mapping)]


def _round(value: float) -> float:
    return round(value, 6)
