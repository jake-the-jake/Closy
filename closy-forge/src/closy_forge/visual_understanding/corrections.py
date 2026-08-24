from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.visual_understanding.tshirt_observations import hash_visual_observations

CORRECTION_RECORD_VERSION = "closy.correction_record.applied_v1"
EMPTY_CORRECTION_RECORD_VERSION = "closy.correction_record.empty_v1"

ALLOWED_CORRECTION_OPERATIONS = [
    "mask_include_polygon",
    "mask_exclude_polygon",
    "landmark_move",
    "landmark_add",
    "landmark_remove",
    "semantic_label_override",
    "confidence_override",
    "view_label_correction",
    "left_right_assignment_swap",
    "mark_boundary_missing_or_occluded",
    "preserve_logo_region",
]


class CorrectionReplayError(RuntimeError):
    """Fail-closed correction replay error with no pixel/path leakage."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_empty_correction_record(visual_observations: dict[str, Any]) -> dict[str, Any]:
    record = _base_record(
        visual_observations,
        record_id="correction.synthetic_tshirt_empty_v1",
        record_version=EMPTY_CORRECTION_RECORD_VERSION,
        state="empty_editable_baseline",
        operations=[],
    )
    record["application"] = {
        "status": "not_applied_empty",
        "operationCount": 0,
        "beforeVisualRecordHash": visual_observations["integrity"]["visualRecordHash"],
        "afterVisualRecordHash": visual_observations["integrity"]["visualRecordHash"],
        "affectedSemanticEntities": [],
        "confidenceDelta": 0.0,
        "staleInputConflicts": [],
        "reversible": True,
        "supersedesCorrectionRecordId": None,
    }
    record["integrity"]["correctionRecordHash"] = hash_correction_record(record)
    return record


def build_default_applied_correction_record(
    visual_observations: dict[str, Any],
) -> dict[str, Any]:
    before_hash = str(visual_observations["integrity"]["visualRecordHash"])
    return build_applied_correction_record(
        visual_observations,
        [
            {
                "operationId": "op.0001.exclude.occlusion_from_target",
                "operation": "mask_exclude_polygon",
                "viewId": "view.front",
                "targetMaskId": "mask.front.target_garment",
                "polygon": [[0.580, 0.500], [0.635, 0.500], [0.635, 0.590], [0.580, 0.590]],
                "affectedSemanticEntities": ["component.tshirt", "component.occlusion_uncertainty"],
                "expectedVisualRecordHash": before_hash,
            },
            {
                "operationId": "op.0002.move.hem_center_pixel_snap",
                "operation": "landmark_move",
                "viewId": "view.front",
                "landmarkId": "landmark.hem.center",
                "position2d": [0.500, 0.785],
                "confidence": 0.80,
                "affectedSemanticEntities": ["opening.hem", "landmark.hem.center"],
                "expectedVisualRecordHash": before_hash,
            },
            {
                "operationId": "op.0003.mark.right_quarter_occluded_cuff",
                "operation": "mark_boundary_missing_or_occluded",
                "viewId": "view.right_three_quarter",
                "openingId": "opening.cuff.right",
                "status": "partially_occluded",
                "confidence": 0.58,
                "affectedSemanticEntities": ["opening.cuff.right"],
                "expectedVisualRecordHash": before_hash,
            },
            {
                "operationId": "op.0004.preserve.front_logo_zone",
                "operation": "preserve_logo_region",
                "viewId": "view.front",
                "regionId": "print.region.front_center_demo",
                "polygon": [[0.445, 0.405], [0.555, 0.405], [0.555, 0.510], [0.445, 0.510]],
                "affectedSemanticEntities": [
                    "component.tshirt.torso",
                    "print.region.front_center_demo",
                ],
                "expectedVisualRecordHash": before_hash,
            },
        ],
    )


def build_applied_correction_record(
    visual_observations: dict[str, Any],
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_operations = _ordered_operations(operations)
    before_hash = str(visual_observations["integrity"]["visualRecordHash"])
    corrected = apply_correction_operations(visual_observations, ordered_operations)
    after_hash = hash_visual_observations(corrected)
    affected = sorted(
        {
            str(entity)
            for operation in ordered_operations
            for entity in operation.get("affectedSemanticEntities", [])
        }
    )
    record = _base_record(
        visual_observations,
        record_id="correction.raster_d0_tshirt_applied_v1",
        record_version=CORRECTION_RECORD_VERSION,
        state="edited" if ordered_operations else "empty_editable_baseline",
        operations=ordered_operations,
    )
    record["application"] = {
        "status": "applied" if ordered_operations else "not_applied_empty",
        "operationCount": len(ordered_operations),
        "beforeVisualRecordHash": before_hash,
        "afterVisualRecordHash": after_hash,
        "beforeArtifactHash": _artifact_hash(visual_observations),
        "afterArtifactHash": _artifact_hash(corrected),
        "affectedSemanticEntities": affected,
        "confidenceDelta": _round(
            _mean_confidence(corrected) - _mean_confidence(visual_observations)
        ),
        "staleInputConflicts": [],
        "reversible": True,
        "supersedesCorrectionRecordId": None,
        "resultKind": "structured_visual_evidence_delta",
        "sourcePixelsModified": False,
        "meshSculptingPerformed": False,
    }
    record["privacyAudit"] = {
        "containsUserImagery": False,
        "containsPersonalBodyData": False,
        "authorClass": "project_fixture_author",
        "personalIdentifiersStored": False,
        "rawPixelsStored": False,
        "sourcePathsStored": False,
    }
    record["integrity"]["correctionRecordHash"] = hash_correction_record(record)
    return record


def apply_correction_operations(
    visual_observations: dict[str, Any],
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    corrected = deepcopy(visual_observations)
    base_hash = str(visual_observations["integrity"]["visualRecordHash"])
    for operation in _ordered_operations(operations):
        expected_hash = operation.get("expectedVisualRecordHash")
        if isinstance(expected_hash, str) and expected_hash and expected_hash != base_hash:
            raise CorrectionReplayError("stale_visual_record_hash")
        op_name = str(operation.get("operation", ""))
        if op_name == "mask_include_polygon":
            _mask_polygon_delta(corrected, operation, include=True)
        elif op_name == "mask_exclude_polygon":
            _mask_polygon_delta(corrected, operation, include=False)
        elif op_name == "landmark_move":
            _move_landmark(corrected, operation)
        elif op_name == "landmark_add":
            _add_landmark(corrected, operation)
        elif op_name == "landmark_remove":
            _remove_landmark(corrected, operation)
        elif op_name == "left_right_assignment_swap":
            _swap_landmarks(corrected, operation)
        elif op_name == "mark_boundary_missing_or_occluded":
            _mark_opening(corrected, operation)
        elif op_name == "view_label_correction":
            _correct_view_label(corrected, operation)
        elif op_name == "confidence_override":
            _confidence_override(corrected, operation)
        elif op_name == "semantic_label_override":
            _semantic_label_override(corrected, operation)
        elif op_name == "preserve_logo_region":
            _preserve_logo_region(corrected, operation)
        else:
            raise CorrectionReplayError("unsupported_correction_operation")
    corrected.setdefault("correctionApplications", []).append(
        {
            "operationCount": len(operations),
            "beforeVisualRecordHash": base_hash,
            "afterArtifactHash": _artifact_hash(corrected),
            "source": "structured_bp50_correction_replay",
        }
    )
    corrected["integrity"]["visualRecordHash"] = hash_visual_observations(corrected)
    return corrected


def hash_correction_record(record: dict[str, Any]) -> str:
    payload = deepcopy(record)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["correctionRecordHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _base_record(
    visual_observations: dict[str, Any],
    *,
    record_id: str,
    record_version: str,
    state: str,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "correctionRecordId": record_id,
        "recordVersion": record_version,
        "visualUnderstandingId": visual_observations["visualUnderstandingId"],
        "visualRecordHash": visual_observations["integrity"]["visualRecordHash"],
        "state": state,
        "editable": True,
        "privacy": {
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "allowExternalApis": False,
            "allowTrainingUse": False,
        },
        "allowedOperations": ALLOWED_CORRECTION_OPERATIONS,
        "operations": operations,
        "integrity": {"correctionRecordHash": ""},
    }


def _ordered_operations(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cloned = [deepcopy(operation) for operation in operations]
    for index, operation in enumerate(cloned, start=1):
        operation.setdefault("order", index)
        operation.setdefault("authorClass", "project_fixture_author")
        operation.setdefault("personalIdentifiersStored", False)
        operation.setdefault("reversible", True)
    return sorted(
        cloned, key=lambda item: (int(item.get("order", 0)), str(item.get("operationId", "")))
    )


def _mask_polygon_delta(
    record: dict[str, Any], operation: dict[str, Any], *, include: bool
) -> None:
    mask = _find_mask(
        record, str(operation.get("viewId", "")), str(operation.get("targetMaskId", ""))
    )
    polygon = operation.get("polygon")
    if not isinstance(polygon, list) or not polygon:
        raise CorrectionReplayError("correction_polygon_missing")
    deltas = mask.setdefault("correctionDeltas", [])
    before = int(mask.get("correctedPixelDelta", 0))
    area = _polygon_area_fraction(polygon)
    pixel_delta = max(1, int(round(area * int(mask["rle"]["width"]) * int(mask["rle"]["height"]))))
    after = before + pixel_delta if include else before - pixel_delta
    mask["correctedPixelDelta"] = after
    mask["confidence"] = _round(
        max(0.0, min(1.0, float(mask["confidence"]) + (0.02 if include else -0.03)))
    )
    deltas.append(
        {
            "operationId": operation.get("operationId"),
            "kind": "include" if include else "exclude",
            "polygon": polygon,
            "pixelDelta": pixel_delta if include else -pixel_delta,
        }
    )


def _move_landmark(record: dict[str, Any], operation: dict[str, Any]) -> None:
    landmark = _find_landmark(
        record, str(operation.get("viewId", "")), str(operation.get("landmarkId", ""))
    )
    landmark["position2d"] = _point(operation.get("position2d"))
    landmark["confidence"] = _round(
        float(operation.get("confidence", landmark.get("confidence", 0.9)))
    )
    landmark["source"] = "structured_correction_landmark_move"


def _add_landmark(record: dict[str, Any], operation: dict[str, Any]) -> None:
    view = _find_view(record, str(operation.get("viewId", "")))
    landmark_id = str(operation.get("landmarkId", ""))
    if not landmark_id.startswith("landmark."):
        raise CorrectionReplayError("invalid_landmark_id")
    view.setdefault("landmarks", []).append(
        {
            "id": landmark_id,
            "position2d": _point(operation.get("position2d")),
            "confidence": _round(float(operation.get("confidence", 0.82))),
            "source": "structured_correction_landmark_add",
        }
    )


def _remove_landmark(record: dict[str, Any], operation: dict[str, Any]) -> None:
    view = _find_view(record, str(operation.get("viewId", "")))
    landmark_id = str(operation.get("landmarkId", ""))
    view["landmarks"] = [
        landmark
        for landmark in view.get("landmarks", [])
        if not isinstance(landmark, dict) or landmark.get("id") != landmark_id
    ]


def _swap_landmarks(record: dict[str, Any], operation: dict[str, Any]) -> None:
    view = _find_view(record, str(operation.get("viewId", "")))
    pairs = operation.get("landmarkPairs")
    if not isinstance(pairs, list):
        pairs = [
            ["landmark.shoulder.left", "landmark.shoulder.right"],
            ["landmark.armhole.left", "landmark.armhole.right"],
            ["landmark.cuff.left", "landmark.cuff.right"],
        ]
    landmarks = {
        landmark.get("id"): landmark
        for landmark in view.get("landmarks", [])
        if isinstance(landmark, dict)
    }
    for left_id, right_id in pairs:
        left = landmarks.get(left_id)
        right = landmarks.get(right_id)
        if isinstance(left, dict) and isinstance(right, dict):
            left["position2d"], right["position2d"] = right["position2d"], left["position2d"]
            left["source"] = "structured_correction_left_right_swap"
            right["source"] = "structured_correction_left_right_swap"


def _mark_opening(record: dict[str, Any], operation: dict[str, Any]) -> None:
    view = _find_view(record, str(operation.get("viewId", "")))
    opening_id = str(operation.get("openingId", ""))
    for opening in view.get("openings", []):
        if isinstance(opening, dict) and opening.get("openingId") == opening_id:
            opening["status"] = str(operation.get("status", "missing_or_occluded"))
            opening["confidence"] = _round(float(operation.get("confidence", 0.42)))
            opening["source"] = "structured_correction_boundary_state"
            return
    raise CorrectionReplayError("opening_not_found")


def _correct_view_label(record: dict[str, Any], operation: dict[str, Any]) -> None:
    view = _find_view(record, str(operation.get("viewId", "")))
    label = str(operation.get("label", ""))
    if not label:
        raise CorrectionReplayError("view_label_missing")
    view["label"] = label
    view["labelSource"] = "structured_correction_view_label"


def _confidence_override(record: dict[str, Any], operation: dict[str, Any]) -> None:
    target_id = str(operation.get("targetId", ""))
    confidence = _round(float(operation.get("confidence", 0.5)))
    for view in record.get("views", []):
        if not isinstance(view, dict):
            continue
        for collection_name in ["masks", "landmarks", "openings"]:
            for item in view.get(collection_name, []):
                if isinstance(item, dict) and target_id in {
                    str(item.get("maskId", "")),
                    str(item.get("id", "")),
                    str(item.get("openingId", "")),
                }:
                    item["confidence"] = confidence
                    return
    raise CorrectionReplayError("confidence_target_not_found")


def _semantic_label_override(record: dict[str, Any], operation: dict[str, Any]) -> None:
    mask = _find_mask(
        record, str(operation.get("viewId", "")), str(operation.get("targetMaskId", ""))
    )
    semantic_id = str(operation.get("semanticId", ""))
    if not semantic_id.startswith("component."):
        raise CorrectionReplayError("invalid_semantic_label")
    mask["semanticId"] = semantic_id
    mask["source"] = "structured_correction_semantic_label_override"


def _preserve_logo_region(record: dict[str, Any], operation: dict[str, Any]) -> None:
    view = _find_view(record, str(operation.get("viewId", "")))
    view.setdefault("protectedPrintRegions", []).append(
        {
            "regionId": str(operation.get("regionId", "print.region.unknown")),
            "polygon": operation.get("polygon", []),
            "policy": "preserve_through_future_texture_projection",
            "source": "structured_correction_preserve_logo_region",
        }
    )


def _find_view(record: dict[str, Any], view_id: str) -> dict[str, Any]:
    for view in record.get("views", []):
        if isinstance(view, dict) and view.get("viewId") == view_id:
            return view
    raise CorrectionReplayError("view_not_found")


def _find_mask(record: dict[str, Any], view_id: str, mask_id: str) -> dict[str, Any]:
    view = _find_view(record, view_id)
    for mask in view.get("masks", []):
        if isinstance(mask, dict) and mask.get("maskId") == mask_id:
            return mask
    raise CorrectionReplayError("mask_not_found")


def _find_landmark(record: dict[str, Any], view_id: str, landmark_id: str) -> dict[str, Any]:
    view = _find_view(record, view_id)
    for landmark in view.get("landmarks", []):
        if isinstance(landmark, dict) and landmark.get("id") == landmark_id:
            return landmark
    raise CorrectionReplayError("landmark_not_found")


def _point(value: Any) -> list[float]:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise CorrectionReplayError("point_invalid")
    x = max(0.0, min(1.0, float(value[0])))
    y = max(0.0, min(1.0, float(value[1])))
    return [_round(x), _round(y)]


def _polygon_area_fraction(polygon: list[Any]) -> float:
    points = [_point(point) for point in polygon]
    area = 0.0
    previous = points[-1]
    for point in points:
        area += previous[0] * point[1] - point[0] * previous[1]
        previous = point
    return abs(area) * 0.5


def _artifact_hash(record: dict[str, Any]) -> str:
    payload = {
        "views": record.get("views", []),
        "aggregate": record.get("aggregate", {}),
        "correctionApplications": record.get("correctionApplications", []),
    }
    return sha256_bytes(b"CLOSY_VISUAL_ARTIFACTS_V1" + canonical_dumps(payload).encode("utf-8"))


def _mean_confidence(record: dict[str, Any]) -> float:
    values: list[float] = []
    for view in record.get("views", []):
        if not isinstance(view, dict):
            continue
        for collection_name in ["masks", "landmarks", "openings"]:
            for item in view.get(collection_name, []):
                if isinstance(item, dict) and isinstance(item.get("confidence"), int | float):
                    values.append(float(item["confidence"]))
    return sum(values) / max(1, len(values))


def _round(value: float) -> float:
    return round(float(value), 6)
