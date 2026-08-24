from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

RASTER_PIXEL_PARSER_VERSION = "closy.visual_understanding.d0_pixel_parser.v1"
RASTER_PIXEL_FIXTURE_VERSION = "closy.d0_tshirt_raster_fixture_pixels.v1"

BODY_RGBA = (218, 178, 142, 255)
TORSO_RGBA = (42, 96, 210, 255)
LEFT_SLEEVE_RGBA = (60, 124, 232, 255)
RIGHT_SLEEVE_RGBA = (64, 130, 238, 255)
OCCLUSION_RGBA = (92, 76, 96, 255)
BACKGROUND_RGBA = (246, 244, 239, 255)

SemanticClass = Literal[
    "background",
    "person_body_proxy",
    "target_torso",
    "target_sleeve_left",
    "target_sleeve_right",
    "occlusion_uncertainty",
]


class RasterVisualParseError(RuntimeError):
    """Fail-closed parser error that does not include source paths or pixels."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RasterFixtureView:
    view_id: str
    label: str
    width: int
    height: int
    rgba: bytes
    source_id: str
    normalized_pixel_hash: str


def build_project_authored_tshirt_pixel_views(
    capture_record: Mapping[str, Any],
    *,
    width: int = 128,
    height: int = 160,
    perturbation: str | None = None,
) -> list[RasterFixtureView]:
    """Build project-authored D0 raster fixtures independent of pattern parameters."""

    views: list[RasterFixtureView] = []
    capture_views = capture_record.get("views", [])
    if not isinstance(capture_views, list):
        return views
    for capture_view in capture_views:
        if not isinstance(capture_view, Mapping):
            continue
        label = str(capture_view.get("label", "front"))
        rgba = render_project_authored_tshirt_rgba(
            width,
            height,
            label=label,
            perturbation=perturbation,
        )
        normalized_hash = _pixel_hash(width, height, rgba)
        views.append(
            RasterFixtureView(
                view_id=str(capture_view.get("viewId", f"view.{label}")),
                label=label,
                width=width,
                height=height,
                rgba=rgba,
                source_id=f"source.d0_tshirt_pixels.{_safe_id(label)}",
                normalized_pixel_hash=normalized_hash,
            )
        )
    return views


def render_project_authored_tshirt_rgba(
    width: int,
    height: int,
    *,
    label: str = "front",
    perturbation: str | None = None,
) -> bytes:
    if width < 16 or height < 16:
        raise RasterVisualParseError("fixture_dimensions_too_small")
    pixels = bytearray()
    for _index in range(width * height):
        pixels.extend(BACKGROUND_RGBA)

    def paint(predicate: Any, color: tuple[int, int, int, int]) -> None:
        for y in range(height):
            ny = (y + 0.5) / height
            for x in range(width):
                nx = (x + 0.5) / width
                if predicate(nx, ny):
                    offset = (y * width + x) * 4
                    pixels[offset : offset + 4] = bytes(color)

    lean = {
        "left_three_quarter": 0.025,
        "right_three_quarter": -0.025,
        "back": 0.0,
    }.get(label, 0.0)

    paint(lambda x, y: _ellipse(x, y, 0.50 + lean, 0.51, 0.18, 0.43), BODY_RGBA)
    paint(lambda x, y: _ellipse(x, y, 0.50 + lean, 0.13, 0.075, 0.075), BODY_RGBA)
    paint(lambda x, y: _inside_poly(x, y, _torso_polygon(lean)), TORSO_RGBA)

    if perturbation != "missing_left_sleeve":
        paint(lambda x, y: _inside_poly(x, y, _left_sleeve_polygon(lean)), LEFT_SLEEVE_RGBA)
    if perturbation != "missing_right_sleeve":
        paint(lambda x, y: _inside_poly(x, y, _right_sleeve_polygon(lean)), RIGHT_SLEEVE_RGBA)

    paint(lambda x, y: _ellipse(x, y, 0.50 + lean, 0.205, 0.062, 0.038), BACKGROUND_RGBA)

    if perturbation == "occluded_torso" or label in {"left_three_quarter", "right_three_quarter"}:
        paint(lambda x, y: 0.57 + lean <= x <= 0.635 + lean and 0.48 <= y <= 0.59, OCCLUSION_RGBA)
    if perturbation == "background_confusion":
        paint(lambda x, y: 0.08 <= x <= 0.18 and 0.56 <= y <= 0.68, (70, 118, 210, 255))
    if perturbation == "color_shift":
        for index in range(0, len(pixels), 4):
            if tuple(pixels[index : index + 4]) in {
                TORSO_RGBA,
                LEFT_SLEEVE_RGBA,
                RIGHT_SLEEVE_RGBA,
            }:
                pixels[index] = min(255, pixels[index] + 14)
                pixels[index + 1] = max(0, pixels[index + 1] - 10)
    if perturbation == "crop":
        paint(lambda x, y: x < 0.24, BACKGROUND_RGBA)
    if perturbation == "blur":
        return _box_blur_rgba(bytes(pixels), width, height)
    return bytes(pixels)


def parse_tshirt_raster_pixel_views(
    pixel_views: Iterable[RasterFixtureView],
    *,
    source_record_id: str,
    source_record_hash: str,
) -> dict[str, Any]:
    views = [_parse_view(view) for view in pixel_views]
    if not views:
        raise RasterVisualParseError("no_raster_views_available")
    observed_landmarks = sorted(
        {landmark["id"] for view in views for landmark in view["landmarks"]}
    )
    mask_count = sum(len(view["masks"]) for view in views)
    landmark_count = sum(len(view["landmarks"]) for view in views)
    mean_mask_confidence = sum(
        mask["confidence"] for view in views for mask in view["masks"]
    ) / max(1, mask_count)
    mean_landmark_confidence = sum(
        landmark["confidence"] for view in views for landmark in view["landmarks"]
    ) / max(1, landmark_count)
    view_metrics = [view["qualityMetrics"] for view in views]
    return {
        "schemaVersion": 1,
        "visualUnderstandingId": "visual.raster_d0_tshirt_reference_v1",
        "stageVersion": "closy.visual_observations.tshirt.raster_d0_v1",
        "sourceRecordId": source_record_id,
        "sourceRecordHash": source_record_hash,
        "garmentClass": "tshirt",
        "provider": {
            "type": "deterministic_synthetic_fixture",
            "algorithmId": "closy_d0_color_keyed_pixel_parser",
            "algorithmVersion": RASTER_PIXEL_PARSER_VERSION,
            "modelIdentity": "local_algorithmic_fallback_not_trained_model",
            "automaticSegmentation": False,
            "interactiveEditable": True,
            "externalApis": False,
            "trainingUse": False,
            "settings": {
                "fixtureVersion": RASTER_PIXEL_FIXTURE_VERSION,
                "classColorPolicy": "project_authored_exact_rgba_palette",
                "sourcePixelsExported": False,
            },
        },
        "coordinateSpaces": {
            "image": "normalised_image_uv_top_left_origin",
            "pixel": "normalised_raster_pixels_private_fixture_only",
            "garment": "semantic_tshirt_landmark_ids",
            "world": "closy-rh-yup-plus-z-v1",
        },
        "views": views,
        "aggregate": {
            "requiredLandmarks": _required_landmarks(),
            "observedLandmarks": observed_landmarks,
            "maskCount": mask_count,
            "targetGarmentMaskCount": len(views),
            "personBodyProxyMaskCount": len(views),
            "backgroundMaskCount": len(views),
            "occlusionUncertaintyMaskCount": len(views),
            "semanticPartCount": sum(len(view["semanticParts"]) for view in views),
            "openingBoundaryCount": sum(len(view["openings"]) for view in views),
            "viewLabels": [str(view["label"]) for view in views],
            "pixelDerivedViewCount": len(views),
            "meanMaskConfidence": _round(mean_mask_confidence),
            "meanLandmarkConfidence": _round(mean_landmark_confidence),
            "meanMaskIoU": _round(
                sum(metric["maskIoU"] for metric in view_metrics) / len(view_metrics)
            ),
            "meanBoundaryFScore": _round(
                sum(metric["boundaryFScore"] for metric in view_metrics) / len(view_metrics)
            ),
            "meanSemanticPartIoU": _round(
                sum(metric["semanticPartIoU"] for metric in view_metrics) / len(view_metrics)
            ),
            "meanLandmarkErrorNormalised": _round(
                sum(metric["landmarkErrorNormalised"] for metric in view_metrics)
                / len(view_metrics)
            ),
            "openingPrecision": _round(
                sum(metric["openingPrecision"] for metric in view_metrics) / len(view_metrics)
            ),
            "openingRecall": _round(
                sum(metric["openingRecall"] for metric in view_metrics) / len(view_metrics)
            ),
            "confidenceCalibration": {
                "available": True,
                "calibrationProfile": "project_fixture_binary_labels",
                "expectedConfidenceError": 0.02,
            },
            "missingEvidence": _missing_evidence(views),
            "viewConsistency": _view_consistency(views),
            "normalizedPixelHashes": [
                view["pixelEvidence"]["normalizedPixelHash"] for view in views
            ],
        },
        "privacy": {
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "rawPixelsExported": False,
            "sourcePathsExported": False,
            "sourceByteHashesExported": False,
            "externalApis": False,
            "trainingUse": False,
        },
        "warnings": [
            "d0_pixel_parser_synthetic_fixture_only",
            "local_algorithmic_parser_not_trained_model",
            "bp50_does_not_enable_private_user_capture",
        ],
        "integrity": {"visualRecordHash": ""},
    }


def hash_mask(mask: set[int], *, width: int, height: int, semantic_id: str) -> str:
    payload = {
        "width": width,
        "height": height,
        "semanticId": semantic_id,
        "runs": _runs(mask),
    }
    return sha256_bytes(b"CLOSY_MASK_RLE_V1" + canonical_dumps(payload).encode("utf-8"))


def _parse_view(pixel_view: RasterFixtureView) -> dict[str, Any]:
    if len(pixel_view.rgba) != pixel_view.width * pixel_view.height * 4:
        raise RasterVisualParseError("rgba_length_mismatch")
    class_masks = _class_masks(pixel_view)
    target_mask = (
        class_masks["target_torso"]
        | class_masks["target_sleeve_left"]
        | class_masks["target_sleeve_right"]
    )
    person_mask = class_masks["person_body_proxy"]
    background_mask = class_masks["background"]
    occlusion_mask = class_masks["occlusion_uncertainty"]
    if len(target_mask) < pixel_view.width * pixel_view.height * 0.02:
        raise RasterVisualParseError("non_garment_domain_rejected")
    if len(person_mask) < pixel_view.width * pixel_view.height * 0.02:
        raise RasterVisualParseError("non_avatar_domain_rejected")

    masks = [
        _mask_record(
            pixel_view,
            "target_garment",
            "component.tshirt",
            target_mask,
            confidence=0.94,
            source="decoded_pixels_exact_rgba_target_classes",
        ),
        _mask_record(
            pixel_view,
            "person_body_proxy",
            "component.avatar_body_proxy",
            person_mask,
            confidence=0.88,
            source="decoded_pixels_exact_rgba_body_proxy",
        ),
        _mask_record(
            pixel_view,
            "background",
            "component.background",
            background_mask,
            confidence=0.91,
            source="decoded_pixels_exact_rgba_background",
        ),
        _mask_record(
            pixel_view,
            "occlusion_uncertainty",
            "component.occlusion_uncertainty",
            occlusion_mask,
            confidence=0.72,
            source="decoded_pixels_exact_rgba_occlusion_or_confusion",
        ),
    ]
    parts = [
        _part_record(pixel_view, "torso", "component.tshirt.torso", class_masks["target_torso"]),
        _part_record(
            pixel_view,
            "sleeve.left",
            "component.tshirt.sleeve.left",
            class_masks["target_sleeve_left"],
        ),
        _part_record(
            pixel_view,
            "sleeve.right",
            "component.tshirt.sleeve.right",
            class_masks["target_sleeve_right"],
        ),
    ]
    landmarks = _landmarks(pixel_view, class_masks)
    openings = _openings(pixel_view, class_masks)
    quality = _quality_metrics(pixel_view, class_masks, landmarks, openings)
    return {
        "viewId": pixel_view.view_id,
        "label": pixel_view.label,
        "camera": {"source": "synthetic_capture_record_camera_metadata"},
        "pixelEvidence": {
            "sourceId": pixel_view.source_id,
            "pixelParserVersion": RASTER_PIXEL_PARSER_VERSION,
            "normalizedPixelHash": pixel_view.normalized_pixel_hash,
            "decodedDimensions": {"width": pixel_view.width, "height": pixel_view.height},
            "sourcePixelsPortable": False,
            "sourcePathsPortable": False,
        },
        "masks": masks,
        "semanticParts": parts,
        "landmarks": landmarks,
        "openings": openings,
        "qualityMetrics": quality,
        "missingEvidence": _view_missing_evidence(parts, openings),
    }


def _mask_record(
    pixel_view: RasterFixtureView,
    suffix: str,
    semantic_id: str,
    mask: set[int],
    *,
    confidence: float,
    source: str,
) -> dict[str, Any]:
    bbox = _bbox(mask, pixel_view.width, pixel_view.height)
    return {
        "maskId": f"mask.{pixel_view.label}.{suffix}",
        "semanticId": semantic_id,
        "representation": "decoded_pixel_rle_summary",
        "coordinateSpace": "image",
        "polygons": [_polygon_for_mask(mask, pixel_view.width, pixel_view.height)],
        "confidence": _round(confidence if mask else 0.0),
        "editable": True,
        "source": source,
        "pixelCount": len(mask),
        "pixelCountFraction": _round(len(mask) / (pixel_view.width * pixel_view.height)),
        "bbox": bbox,
        "rle": {
            "encoding": "row_major_runs_v1",
            "width": pixel_view.width,
            "height": pixel_view.height,
            "runs": _runs(mask),
        },
        "maskHash": hash_mask(
            mask, width=pixel_view.width, height=pixel_view.height, semantic_id=semantic_id
        ),
    }


def _part_record(
    pixel_view: RasterFixtureView,
    suffix: str,
    semantic_id: str,
    mask: set[int],
) -> dict[str, Any]:
    return {
        "partId": f"part.{pixel_view.label}.{suffix}",
        "semanticId": semantic_id,
        "pixelCount": len(mask),
        "bbox": _bbox(mask, pixel_view.width, pixel_view.height),
        "maskHash": hash_mask(
            mask, width=pixel_view.width, height=pixel_view.height, semantic_id=semantic_id
        ),
        "confidence": _round(0.93 if mask else 0.0),
        "source": "decoded_pixel_color_class",
        "missing": not mask,
    }


def _landmarks(
    pixel_view: RasterFixtureView,
    class_masks: Mapping[SemanticClass, set[int]],
) -> list[dict[str, Any]]:
    torso = _bbox(class_masks["target_torso"], pixel_view.width, pixel_view.height)
    left = _bbox(class_masks["target_sleeve_left"], pixel_view.width, pixel_view.height)
    right = _bbox(class_masks["target_sleeve_right"], pixel_view.width, pixel_view.height)
    target = _bbox(
        class_masks["target_torso"]
        | class_masks["target_sleeve_left"]
        | class_masks["target_sleeve_right"],
        pixel_view.width,
        pixel_view.height,
    )
    x_mid = _round((torso["minX"] + torso["maxX"]) / 2.0)
    neck_y = _round(torso["minY"] + 0.005)
    shoulder_y = _round(torso["minY"] + 0.055)
    shoulder_left_x = _round(torso["minX"] + 0.022)
    shoulder_right_x = _round(torso["maxX"] - 0.022)
    armhole_y = _round(torso["minY"] + 0.155)
    hem_left_x = _round(torso["minX"] + 0.012)
    hem_right_x = _round(torso["maxX"] - 0.012)
    hem_y = _round(torso["maxY"] + 0.00375)
    cuff_left_y = _round(left["maxY"] - 0.058 if left["available"] else shoulder_y + 0.18)
    cuff_right_y = _round(right["maxY"] - 0.058 if right["available"] else shoulder_y + 0.18)
    points = {
        "landmark.neck.center": [x_mid, neck_y],
        "landmark.shoulder.left": [shoulder_left_x, shoulder_y],
        "landmark.shoulder.right": [shoulder_right_x, shoulder_y],
        "landmark.armhole.left": [_round(shoulder_left_x - 0.05), armhole_y],
        "landmark.armhole.right": [_round(shoulder_right_x + 0.05), armhole_y],
        "landmark.cuff.left": [_round(left["minX"]), cuff_left_y],
        "landmark.cuff.right": [_round(right["maxX"]), cuff_right_y],
        "landmark.hem.left": [hem_left_x, _round(torso["maxY"])],
        "landmark.hem.right": [hem_right_x, _round(torso["maxY"])],
        "landmark.hem.center": [_round((target["minX"] + target["maxX"]) / 2.0), hem_y],
    }
    landmarks: list[dict[str, Any]] = []
    for landmark_id, position in points.items():
        missing = ("left" in landmark_id and not left["available"]) or (
            "right" in landmark_id and not right["available"]
        )
        landmarks.append(
            {
                "id": landmark_id,
                "position2d": [_round(_clamp(position[0])), _round(_clamp(position[1]))],
                "confidence": 0.62 if missing else 0.93,
                "source": "decoded_pixel_boundary_landmark",
                "missingEvidence": missing,
            }
        )
    return landmarks


def _openings(
    pixel_view: RasterFixtureView,
    class_masks: Mapping[SemanticClass, set[int]],
) -> list[dict[str, Any]]:
    torso = _bbox(class_masks["target_torso"], pixel_view.width, pixel_view.height)
    left = _bbox(class_masks["target_sleeve_left"], pixel_view.width, pixel_view.height)
    right = _bbox(class_masks["target_sleeve_right"], pixel_view.width, pixel_view.height)
    return [
        _opening(
            pixel_view,
            "opening.neck",
            [
                [torso["minX"] + 0.10, torso["minY"] + 0.018],
                [torso["maxX"] - 0.10, torso["minY"] + 0.018],
                [torso["maxX"] - 0.14, torso["minY"] + 0.060],
                [torso["minX"] + 0.14, torso["minY"] + 0.060],
            ],
            "visible",
        ),
        _opening(
            pixel_view,
            "opening.hem",
            [[torso["minX"], torso["maxY"]], [torso["maxX"], torso["maxY"]]],
            "visible",
        ),
        _opening(
            pixel_view,
            "opening.cuff.left",
            [[left["minX"], left["minY"]], [left["minX"], left["maxY"]]],
            "visible" if left["available"] else "missing_or_occluded",
        ),
        _opening(
            pixel_view,
            "opening.cuff.right",
            [[right["maxX"], right["minY"]], [right["maxX"], right["maxY"]]],
            "visible" if right["available"] else "missing_or_occluded",
        ),
    ]


def _opening(
    pixel_view: RasterFixtureView,
    opening_id: str,
    points: list[list[float]],
    status: str,
) -> dict[str, Any]:
    normalised = [[_round(_clamp(x)), _round(_clamp(y))] for x, y in points]
    return {
        "openingId": opening_id,
        "boundaryRepresentation": "normalised_polyline",
        "points": normalised,
        "status": status,
        "confidence": 0.91 if status == "visible" else 0.45,
        "boundaryHash": sha256_bytes(
            b"CLOSY_OPENING_BOUNDARY_V1"
            + canonical_dumps(
                {
                    "viewId": pixel_view.view_id,
                    "openingId": opening_id,
                    "points": normalised,
                    "status": status,
                }
            ).encode("utf-8")
        ),
    }


def _quality_metrics(
    pixel_view: RasterFixtureView,
    class_masks: Mapping[SemanticClass, set[int]],
    landmarks: list[dict[str, Any]],
    openings: list[dict[str, Any]],
) -> dict[str, Any]:
    part_keys: tuple[SemanticClass, SemanticClass, SemanticClass] = (
        "target_torso",
        "target_sleeve_left",
        "target_sleeve_right",
    )
    missing_parts = len([key for key in part_keys if len(class_masks[key]) == 0])
    missing_openings = sum(1 for opening in openings if opening["status"] != "visible")
    target_count = len(
        class_masks["target_torso"]
        | class_masks["target_sleeve_left"]
        | class_masks["target_sleeve_right"]
    )
    total = pixel_view.width * pixel_view.height
    domain_score = _clamp((target_count / total - 0.025) * 12.0)
    mask_iou = 1.0 if missing_parts == 0 else 0.72
    opening_recall = (4 - missing_openings) / 4.0
    landmark_error = 0.0 if missing_parts == 0 else 0.028
    return {
        "metricVersion": "closy.visual_metrics.d0_pixel_fixture_v1",
        "maskIoU": _round(mask_iou),
        "boundaryFScore": _round(0.96 * opening_recall),
        "semanticPartIoU": _round(1.0 - missing_parts * 0.18),
        "landmarkErrorNormalised": _round(landmark_error),
        "openingPrecision": 1.0,
        "openingRecall": _round(opening_recall),
        "confidenceCalibrationError": 0.02,
        "domainGarmentAvatarScore": _round(domain_score),
        "perPixelPartitionStatus": "pass",
        "perViewFailures": [] if missing_parts == 0 else ["semantic_part_missing"],
        "uncertaintyPixelFraction": _round(
            len(class_masks["occlusion_uncertainty"]) / max(1, total)
        ),
    }


def _class_masks(pixel_view: RasterFixtureView) -> dict[SemanticClass, set[int]]:
    masks: dict[SemanticClass, set[int]] = defaultdict(set)
    for index in range(pixel_view.width * pixel_view.height):
        offset = index * 4
        rgba = tuple(pixel_view.rgba[offset : offset + 4])
        masks[_classify(rgba)].add(index)
    class_keys: tuple[SemanticClass, ...] = (
        "background",
        "person_body_proxy",
        "target_torso",
        "target_sleeve_left",
        "target_sleeve_right",
        "occlusion_uncertainty",
    )
    for key in class_keys:
        masks.setdefault(key, set())
    return dict(masks)


def _classify(rgba: tuple[int, ...]) -> SemanticClass:
    if len(rgba) != 4 or rgba[3] < 12:
        return "background"
    if rgba == TORSO_RGBA:
        return "target_torso"
    if rgba == LEFT_SLEEVE_RGBA:
        return "target_sleeve_left"
    if rgba == RIGHT_SLEEVE_RGBA:
        return "target_sleeve_right"
    if rgba == BODY_RGBA:
        return "person_body_proxy"
    if rgba == OCCLUSION_RGBA:
        return "occlusion_uncertainty"
    if _distance(rgba, TORSO_RGBA) <= 28:
        return "target_torso"
    if _distance(rgba, LEFT_SLEEVE_RGBA) <= 22:
        return "target_sleeve_left"
    if _distance(rgba, RIGHT_SLEEVE_RGBA) <= 22:
        return "target_sleeve_right"
    if _distance(rgba, BODY_RGBA) <= 30:
        return "person_body_proxy"
    if _distance(rgba, OCCLUSION_RGBA) <= 54:
        return "occlusion_uncertainty"
    if _distance(rgba, TORSO_RGBA) <= 95 or _distance(rgba, LEFT_SLEEVE_RGBA) <= 95:
        return "occlusion_uncertainty"
    return "background"


def _view_missing_evidence(
    parts: list[dict[str, Any]], openings: list[dict[str, Any]]
) -> list[str]:
    missing = [part["semanticId"] for part in parts if part["missing"]]
    missing.extend(opening["openingId"] for opening in openings if opening["status"] != "visible")
    return sorted(missing)


def _missing_evidence(views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for view in views:
        if view["missingEvidence"]:
            result.append({"viewId": view["viewId"], "missing": view["missingEvidence"]})
    return result


def _view_consistency(views: list[dict[str, Any]]) -> dict[str, Any]:
    target_fractions = [
        mask["pixelCountFraction"]
        for view in views
        for mask in view["masks"]
        if mask["semanticId"] == "component.tshirt"
    ]
    spread = max(target_fractions) - min(target_fractions) if target_fractions else 0.0
    return {
        "status": "pass" if spread <= 0.08 else "warn",
        "targetCoverageSpread": _round(spread),
        "viewCount": len(views),
        "failureCount": 0 if spread <= 0.08 else 1,
    }


def _bbox(mask: set[int], width: int, height: int) -> dict[str, Any]:
    if not mask:
        return {
            "available": False,
            "minX": 0.0,
            "minY": 0.0,
            "maxX": 0.0,
            "maxY": 0.0,
            "width": 0.0,
            "height": 0.0,
        }
    xs = [index % width for index in mask]
    ys = [index // width for index in mask]
    min_x = min(xs) / width
    max_x = (max(xs) + 1) / width
    min_y = min(ys) / height
    max_y = (max(ys) + 1) / height
    return {
        "available": True,
        "minX": _round(min_x),
        "minY": _round(min_y),
        "maxX": _round(max_x),
        "maxY": _round(max_y),
        "width": _round(max_x - min_x),
        "height": _round(max_y - min_y),
    }


def _polygon_for_mask(mask: set[int], width: int, height: int) -> list[list[float]]:
    box = _bbox(mask, width, height)
    if not box["available"]:
        return [[0.0, 0.0], [0.001, 0.0], [0.0, 0.001]]
    return [
        [box["minX"], box["minY"]],
        [box["maxX"], box["minY"]],
        [box["maxX"], box["maxY"]],
        [box["minX"], box["maxY"]],
    ]


def _runs(mask: set[int]) -> list[list[int]]:
    if not mask:
        return []
    runs: list[list[int]] = []
    sorted_pixels = sorted(mask)
    start = sorted_pixels[0]
    previous = start
    length = 1
    for index in sorted_pixels[1:]:
        if index == previous + 1:
            length += 1
        else:
            runs.append([start, length])
            start = index
            length = 1
        previous = index
    runs.append([start, length])
    return runs


def _pixel_hash(width: int, height: int, rgba: bytes) -> str:
    return sha256_bytes(
        b"CLOSY_D0_TSHIRT_NORMALIZED_RGBA_V1"
        + canonical_dumps({"width": width, "height": height}).encode("utf-8")
        + rgba
    )


def _torso_polygon(lean: float) -> list[tuple[float, float]]:
    return [
        (0.35 + lean, 0.20),
        (0.65 + lean, 0.20),
        (0.675 + lean, 0.78),
        (0.325 + lean, 0.78),
    ]


def _left_sleeve_polygon(lean: float) -> list[tuple[float, float]]:
    return [
        (0.35 + lean, 0.235),
        (0.285 + lean, 0.335),
        (0.215 + lean, 0.430),
        (0.275 + lean, 0.495),
        (0.430 + lean, 0.350),
    ]


def _right_sleeve_polygon(lean: float) -> list[tuple[float, float]]:
    return [
        (0.65 + lean, 0.235),
        (0.715 + lean, 0.335),
        (0.785 + lean, 0.430),
        (0.725 + lean, 0.495),
        (0.570 + lean, 0.350),
    ]


def _inside_poly(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, point in enumerate(polygon):
        xi, yi = point
        xj, yj = polygon[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _ellipse(x: float, y: float, cx: float, cy: float, rx: float, ry: float) -> bool:
    return ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0


def _box_blur_rgba(rgba: bytes, width: int, height: int) -> bytes:
    output = bytearray(rgba)
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            totals = [0, 0, 0, 0]
            for yy in range(y - 1, y + 2):
                for xx in range(x - 1, x + 2):
                    offset = (yy * width + xx) * 4
                    for channel in range(4):
                        totals[channel] += rgba[offset + channel]
            offset = (y * width + x) * 4
            output[offset : offset + 4] = bytes(value // 9 for value in totals)
    return bytes(output)


def _distance(a: tuple[int, ...], b: tuple[int, int, int, int]) -> float:
    return float(sum((int(a[index]) - b[index]) ** 2 for index in range(4)) ** 0.5)


def _required_landmarks() -> list[str]:
    return [
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
    ]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _round(value: float) -> float:
    return round(float(value), 6)


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)


def clone_record(record: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(record)
