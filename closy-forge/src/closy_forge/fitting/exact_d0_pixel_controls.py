from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.capture.raster_sources import decode_raster_fixture_pixels
from closy_forge.fitting.tshirt_fit import fit_tshirt_parameters_from_visual_observations
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.visual_understanding.corrections import (
    apply_correction_operations,
    build_applied_correction_record,
)
from closy_forge.visual_understanding.multiview_fusion import build_multiview_fusion_record
from closy_forge.visual_understanding.raster_parser import (
    BACKGROUND_RGBA,
    BODY_RGBA,
    LEFT_SLEEVE_RGBA,
    LOGO_RGBA,
    RIGHT_SLEEVE_RGBA,
    TORSO_RGBA,
    RasterFixtureView,
    normalized_raster_pixel_hash,
    parse_tshirt_raster_pixel_views,
)
from closy_forge.visual_understanding.tshirt_observations import hash_visual_observations

EXACT_D0_PIXEL_FIT_CONTROL_VERSION = "closy.d0_exact_pixel_fit_controls.v3"
PixelMutation = Callable[[int, int, bytes], bytes]
Rgba = tuple[int, int, int, int]
_GARMENT_COLORS = {TORSO_RGBA, LEFT_SLEEVE_RGBA, RIGHT_SLEEVE_RGBA, LOGO_RGBA}


def execute_exact_d0_pixel_fit_controls(
    *,
    fixture_root: Path,
    fixture_manifest: Mapping[str, Any],
    capture_record: dict[str, Any],
    selected_correction: Mapping[str, Any],
    prior: TShirtParameters,
    baseline_fit: Mapping[str, Any],
    minimum_delta: float,
) -> dict[str, Any]:
    source_views = _source_views(fixture_root, fixture_manifest)
    baseline_parameters = _float_parameters(baseline_fit.get("fittedParameters"))
    controls = [
        ("widened_silhouette", _scale_horizontal(1.10), "half_chest_width", "increase"),
        ("narrowed_silhouette", _scale_horizontal(0.90), "half_chest_width", "decrease"),
        ("changed_sleeve_reach", _extend_sleeves, "sleeve_length", "increase"),
        ("shifted_hem", _lower_hem, "garment_body_length", "increase"),
    ]
    records = []
    for control_id, mutation, parameter, direction in controls:
        views = [_mutate_view(view, mutation) for view in source_views]
        visual = parse_tshirt_raster_pixel_views(
            views,
            source_record_id=str(capture_record["recordId"]),
            source_record_hash=str(capture_record["immutability"]["sourceRecordHash"]),
        )
        _hydrate_camera_metadata(visual, capture_record)
        correction = build_applied_correction_record(
            visual, _rebound_correction_operations(selected_correction, visual)
        )
        corrected_visual = apply_correction_operations(
            visual, list(correction.get("operations", []))
        )
        fusion = build_multiview_fusion_record(capture_record, visual, correction)
        fit = fit_tshirt_parameters_from_visual_observations(
            corrected_visual,
            multiview_fusion=fusion,
            prior=prior,
        )
        fitted = _float_parameters(fit.get("fittedParameters"))
        delta = fitted[parameter] - baseline_parameters[parameter]
        direction_passed = delta > 0.0 if direction == "increase" else delta < 0.0
        records.append(
            {
                "controlId": control_id,
                "sourcePixelsMutated": True,
                "observationRecomputed": True,
                "fusionRecomputed": True,
                "fitRecomputed": True,
                "visualRecordHash": visual["integrity"]["visualRecordHash"],
                "fusionRecordHash": fusion["integrity"]["multiviewFusionRecordHash"],
                "fitReportHash": fit["integrity"]["fitReportHash"],
                "parameter": parameter,
                "baselineValue": baseline_parameters[parameter],
                "controlledValue": fitted[parameter],
                "deltaMeters": round(delta, 9),
                "expectedDirection": direction,
                "directionPassed": direction_passed,
                "canonicalQuantisationExceeded": abs(delta) >= minimum_delta,
                "controlFitAccepted": fit["accepted"],
            }
        )
    return {
        "schemaVersion": 1,
        "controlVersion": EXACT_D0_PIXEL_FIT_CONTROL_VERSION,
        "inputMode": "opened_frozen_front_rear_png_bytes_then_controlled_pixel_mutation",
        "fixtureRendererCalled": False,
        "targetParametersRead": False,
        "evaluatorOnlyMounted": False,
        "records": records,
        "allDirectionsPassed": all(item["directionPassed"] for item in records),
        "allCanonicalQuantisationExceeded": all(
            item["canonicalQuantisationExceeded"] for item in records
        ),
    }


def _source_views(
    fixture_root: Path, fixture_manifest: Mapping[str, Any]
) -> list[RasterFixtureView]:
    fixtures = fixture_manifest.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("exact_d0_control_fixture_manifest_invalid")
    result = []
    for fixture in fixtures:
        if not isinstance(fixture, Mapping) or fixture.get("role") not in {"front", "rear"}:
            continue
        decoded = decode_raster_fixture_pixels(
            fixture_root / str(fixture.get("relativePath", "")), declared_mime="image/png"
        )
        result.append(
            RasterFixtureView(
                view_id=str(fixture.get("viewId", "")),
                label=str(fixture.get("label", "")),
                width=decoded.width,
                height=decoded.height,
                rgba=decoded.rgba,
                source_id=f"source.control.{fixture.get('fixtureId', '')}",
                normalized_pixel_hash=normalized_raster_pixel_hash(
                    decoded.width, decoded.height, decoded.rgba
                ),
            )
        )
    return result


def _mutate_view(view: RasterFixtureView, mutation: PixelMutation) -> RasterFixtureView:
    rgba = mutation(view.width, view.height, view.rgba)
    return RasterFixtureView(
        view_id=view.view_id,
        label=view.label,
        width=view.width,
        height=view.height,
        rgba=rgba,
        source_id=view.source_id,
        normalized_pixel_hash=normalized_raster_pixel_hash(view.width, view.height, rgba),
    )


def _scale_horizontal(scale: float) -> PixelMutation:
    def mutate(width: int, height: int, rgba: bytes) -> bytes:
        original = _pixels(width, height, rgba)
        output = _clear_garment(original)
        for y in range(height):
            for x in range(width):
                color = original[y][x]
                if color not in _GARMENT_COLORS:
                    continue
                target_x = round((x - width / 2.0) * scale + width / 2.0)
                if 0 <= target_x < width:
                    output[y][target_x] = color
                    if scale > 1.0 and target_x > width // 2 and target_x - 1 >= 0:
                        output[y][target_x - 1] = color
                    if scale > 1.0 and target_x < width // 2 and target_x + 1 < width:
                        output[y][target_x + 1] = color
        return _rgba(output)

    return mutate


def _extend_sleeves(width: int, height: int, rgba: bytes) -> bytes:
    original = _pixels(width, height, rgba)
    output = _clear_colors(original, {LEFT_SLEEVE_RGBA, RIGHT_SLEEVE_RGBA})
    for y in range(height):
        for x in range(width):
            color = original[y][x]
            if color == LEFT_SLEEVE_RGBA:
                target_x = max(0, x - 5)
            elif color == RIGHT_SLEEVE_RGBA:
                target_x = min(width - 1, x + 5)
            else:
                continue
            output[y][target_x] = color
    return _rgba(output)


def _lower_hem(width: int, height: int, rgba: bytes) -> bytes:
    original = _pixels(width, height, rgba)
    output = [row[:] for row in original]
    start = int(height * 0.60)
    for y in range(start, height):
        for x in range(width):
            if original[y][x] in {TORSO_RGBA, LOGO_RGBA}:
                output[y][x] = BODY_RGBA
    for y in range(start, height):
        for x in range(width):
            color = original[y][x]
            if color in {TORSO_RGBA, LOGO_RGBA}:
                output[min(height - 1, y + 5)][x] = color
    return _rgba(output)


def _clear_garment(pixels: list[list[Rgba]]) -> list[list[Rgba]]:
    return _clear_colors(pixels, _GARMENT_COLORS)


def _clear_colors(pixels: list[list[Rgba]], colors: set[Rgba]) -> list[list[Rgba]]:
    height, width = len(pixels), len(pixels[0])
    output = [row[:] for row in pixels]
    for y in range(height):
        for x in range(width):
            if pixels[y][x] in colors:
                output[y][x] = BODY_RGBA if 0.30 * width <= x <= 0.70 * width else BACKGROUND_RGBA
    return output


def _pixels(width: int, height: int, rgba: bytes) -> list[list[Rgba]]:
    return [
        [
            (
                rgba[(y * width + x) * 4],
                rgba[(y * width + x) * 4 + 1],
                rgba[(y * width + x) * 4 + 2],
                rgba[(y * width + x) * 4 + 3],
            )
            for x in range(width)
        ]
        for y in range(height)
    ]


def _rgba(pixels: list[list[Rgba]]) -> bytes:
    return bytes(channel for row in pixels for color in row for channel in color)


def _float_parameters(value: object) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError("exact_d0_control_parameters_missing")
    return {str(key): float(item) for key, item in value.items()}


def _rebound_correction_operations(
    selected_correction: Mapping[str, Any], visual: Mapping[str, Any]
) -> list[dict[str, Any]]:
    operations = selected_correction.get("operations")
    if not isinstance(operations, list):
        raise ValueError("exact_d0_control_correction_operations_missing")
    visual_hash = str(_mapping(visual.get("integrity"))["visualRecordHash"])
    rebound: list[dict[str, Any]] = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, Mapping):
            raise ValueError("exact_d0_control_correction_operation_invalid")
        item = dict(operation)
        item["operationId"] = f"control.replay.{index:04d}"
        item["expectedVisualRecordHash"] = visual_hash
        rebound.append(item)
    return rebound


def _hydrate_camera_metadata(visual: dict[str, Any], capture_record: Mapping[str, Any]) -> None:
    capture_views = capture_record.get("views")
    if not isinstance(capture_views, list):
        raise ValueError("exact_d0_control_capture_views_missing")
    cameras = {
        str(view.get("viewId", "")): deepcopy(view.get("camera"))
        for view in capture_views
        if isinstance(view, Mapping)
    }
    views = visual.get("views")
    if not isinstance(views, list):
        raise ValueError("exact_d0_control_visual_views_missing")
    for view in views:
        if not isinstance(view, dict):
            raise ValueError("exact_d0_control_visual_view_invalid")
        view_id = str(view.get("viewId", ""))
        if view_id not in cameras:
            raise ValueError("exact_d0_control_camera_missing")
        view["camera"] = deepcopy(cameras[view_id])
    visual["integrity"]["visualRecordHash"] = hash_visual_observations(visual)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("exact_d0_control_mapping_missing")
    return value
