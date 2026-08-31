from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.capture.raster_sources import decode_raster_fixture_pixels
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.visual_understanding.raster_parser import (
    RasterFixtureView,
    RasterVisualParseError,
    normalized_raster_pixel_hash,
    parse_tshirt_raster_pixel_views,
)
from closy_forge.visual_understanding.tshirt_observations import hash_visual_observations

PixelMutation = Callable[[int, int, bytes], bytes]


def execute_exact_raster_causal_controls(
    *, manifest: dict[str, Any], input_root: Path, source_record: dict[str, Any]
) -> dict[str, Any]:
    baseline_views = _fit_pixel_views(manifest, input_root, source_record)
    baseline = _parse(baseline_views, source_record)
    blank_rejection = _blank_control(baseline_views, source_record)
    swapped = _parse(
        [
            _replace_pixels(baseline_views[0], baseline_views[1].rgba),
            _replace_pixels(baseline_views[1], baseline_views[0].rgba),
        ],
        source_record,
    )
    shifted_logo = _parse(
        [_mutate_view(baseline_views[0], _shift_logo), baseline_views[1]], source_record
    )
    missing_sleeve = _parse(
        [_mutate_view(baseline_views[0], _remove_left_sleeve), baseline_views[1]],
        source_record,
    )
    baseline_geometry = _geometry_evidence_hash(baseline)
    baseline_appearance = _appearance_evidence_hash(baseline)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "controlVersion": "closy.d0_exact_raster_causal_controls.v2",
        "inputMode": "decoded_frozen_pixels_mutated_in_qualification_scope",
        "fixtureRendererCalled": False,
        "targetParametersRead": False,
        "baseline": _control_identity(baseline),
        "controls": {
            "blankedPixels": blank_rejection,
            "frontRearPixelSwap": {
                "observationRecomputed": True,
                "evidenceMateriallyChanged": (
                    swapped["integrity"]["visualRecordHash"]
                    != baseline["integrity"]["visualRecordHash"]
                ),
                "baselineVisualHash": baseline["integrity"]["visualRecordHash"],
                "controlVisualHash": swapped["integrity"]["visualRecordHash"],
            },
            "shiftedLogo": {
                "observationRecomputed": True,
                "appearanceEvidenceChanged": (
                    _appearance_evidence_hash(shifted_logo) != baseline_appearance
                ),
                "geometryEvidenceInvariant": (
                    _geometry_evidence_hash(shifted_logo) == baseline_geometry
                ),
                "hiddenGeometryLabelsRead": False,
                "appearanceEvidenceHash": _appearance_evidence_hash(shifted_logo),
                "geometryEvidenceHash": _geometry_evidence_hash(shifted_logo),
            },
            "missingLeftSleeve": {
                "observationRecomputed": True,
                "maskEvidenceChanged": (
                    _geometry_evidence_hash(missing_sleeve) != baseline_geometry
                ),
                "missingEvidenceRecorded": bool(missing_sleeve["aggregate"]["missingEvidence"]),
                "controlVisualHash": missing_sleeve["integrity"]["visualRecordHash"],
            },
        },
        "deferredUntilUnitC": {
            "directionalParameterResponse": True,
            "ignoredPerturbationMetricWorsening": True,
            "canonicalQuantisationExceeded": True,
            "reason": "fit_predictions_and_evaluator_are_not_executed_in_unit_b",
        },
        "integrity": {"controlReportHash": ""},
    }
    report["integrity"]["controlReportHash"] = _hash_with_blank(report, "controlReportHash")
    return report


def _fit_pixel_views(
    manifest: dict[str, Any], input_root: Path, source_record: dict[str, Any]
) -> list[RasterFixtureView]:
    sources = {str(source["fixtureId"]): source for source in source_record["acceptedSources"]}
    views: list[RasterFixtureView] = []
    for fixture in manifest["fixtures"]:
        if fixture["role"] not in {"front", "rear"}:
            continue
        decoded = decode_raster_fixture_pixels(
            input_root / str(fixture["relativePath"]), declared_mime="image/png"
        )
        source = sources[str(fixture["fixtureId"])]
        views.append(
            RasterFixtureView(
                view_id=str(fixture["viewId"]),
                label=str(fixture["label"]),
                width=decoded.width,
                height=decoded.height,
                rgba=decoded.rgba,
                source_id=str(source["sourceId"]),
                normalized_pixel_hash=normalized_raster_pixel_hash(
                    decoded.width, decoded.height, decoded.rgba
                ),
            )
        )
    return views


def _blank_control(views: list[RasterFixtureView], source_record: dict[str, Any]) -> dict[str, Any]:
    background = views[0].rgba[:4]
    blank = _replace_pixels(views[0], background * (views[0].width * views[0].height))
    try:
        _parse([blank, views[1]], source_record)
    except RasterVisualParseError as error:
        return {
            "observationRecomputed": True,
            "rejected": True,
            "reasonCode": error.code,
        }
    return {"observationRecomputed": True, "rejected": False}


def _parse(views: list[RasterFixtureView], source_record: dict[str, Any]) -> dict[str, Any]:
    result = parse_tshirt_raster_pixel_views(
        views,
        source_record_id=str(source_record["recordId"]),
        source_record_hash=str(source_record["integrity"]["sourceRecordHash"]),
    )
    result["integrity"]["visualRecordHash"] = hash_visual_observations(result)
    return result


def _mutate_view(view: RasterFixtureView, mutation: PixelMutation) -> RasterFixtureView:
    return _replace_pixels(view, mutation(view.width, view.height, view.rgba))


def _replace_pixels(view: RasterFixtureView, rgba: bytes) -> RasterFixtureView:
    return RasterFixtureView(
        view_id=view.view_id,
        label=view.label,
        width=view.width,
        height=view.height,
        rgba=rgba,
        source_id=view.source_id,
        normalized_pixel_hash=normalized_raster_pixel_hash(view.width, view.height, rgba),
    )


def _shift_logo(width: int, height: int, rgba: bytes) -> bytes:
    pixels = bytearray(rgba)
    logo: list[tuple[int, int, bytes]] = []
    for y in range(height):
        for x in range(width):
            offset = (y * width + x) * 4
            colour = bytes(pixels[offset : offset + 4])
            if colour[0] > 200 and 120 < colour[1] < 220 and colour[2] < 100:
                logo.append((x, y, colour))
    if not logo:
        raise RasterVisualParseError("shifted_logo_source_region_missing")
    for x, y, _colour in logo:
        offset = (y * width + x) * 4
        replacement_x = max(0, x - 2)
        replacement = (y * width + replacement_x) * 4
        pixels[offset : offset + 4] = pixels[replacement : replacement + 4]
    for x, y, colour in logo:
        shifted_x = min(width - 1, x + 4)
        offset = (y * width + shifted_x) * 4
        pixels[offset : offset + 4] = colour
    return bytes(pixels)


def _remove_left_sleeve(width: int, height: int, rgba: bytes) -> bytes:
    pixels = bytearray(rgba)
    background = rgba[:4]
    changed = 0
    for y in range(height):
        for x in range(width // 2):
            offset = (y * width + x) * 4
            red, green, blue, _alpha = pixels[offset : offset + 4]
            if red < 100 and green > 100 and blue > 180:
                pixels[offset : offset + 4] = background
                changed += 1
    if changed == 0:
        raise RasterVisualParseError("missing_sleeve_control_region_missing")
    return bytes(pixels)


def _control_identity(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "visualRecordHash": value["integrity"]["visualRecordHash"],
        "geometryEvidenceHash": _geometry_evidence_hash(value),
        "appearanceEvidenceHash": _appearance_evidence_hash(value),
    }


def _geometry_evidence_hash(value: dict[str, Any]) -> str:
    payload = [
        {
            "viewId": view["viewId"],
            "masks": [
                {
                    "semanticId": mask["semanticId"],
                    "pixelCount": mask["pixelCount"],
                    "bbox": mask["bbox"],
                }
                for mask in view["masks"]
            ],
            "landmarks": [
                {"id": landmark["id"], "position2d": landmark["position2d"]}
                for landmark in view["landmarks"]
            ],
            "openings": [
                {"openingId": opening["openingId"], "points": opening["points"]}
                for opening in view["openings"]
            ],
        }
        for view in value["views"]
    ]
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _appearance_evidence_hash(value: dict[str, Any]) -> str:
    payload = [
        {
            "viewId": view["viewId"],
            "normalizedPixelHash": view["pixelEvidence"]["normalizedPixelHash"],
            "partColours": [part["colorEvidence"] for part in view["semanticParts"]],
        }
        for view in value["views"]
    ]
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _hash_with_blank(value: dict[str, Any], key: str) -> str:
    payload = deepcopy(value)
    payload["integrity"][key] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
