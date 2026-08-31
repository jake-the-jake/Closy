from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.appearance.bitmap_atlas import (
    ATLAS_SIZE,
    BITMAP_PATHS,
    BitmapAtlasBundle,
    _bounded_color_shift,
    _pixel_hash,
    _project_halves,
    _round,
    _seam_difference,
    _target_bbox,
    _white_count,
    _white_fraction,
    audit_bitmap_atlas_bundle,
    hash_bitmap_pbr_report,
)
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.raster import decode_png_rgba, encode_png_rgba
from closy_forge.visual_understanding.raster_parser import LOGO_RGBA

EXACT_BITMAP_ATLAS_VERSION = "closy.texture_atlas.exact_decoded_bitmap_pbr.d0_v3"


def build_exact_d0_bitmap_atlas(
    *,
    fixture_root: Path,
    fixture_manifest: Mapping[str, Any],
    visual_observations: Mapping[str, Any],
) -> BitmapAtlasBundle:
    """Project the frozen front/rear PNG bytes without calling a fixture renderer."""

    source_artifacts: dict[str, bytes | dict[str, Any]] = {}
    decoded_views = {}
    source_records: list[dict[str, Any]] = []
    fixtures = fixture_manifest.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("exact_bitmap_fixture_manifest_invalid")
    for fixture in fixtures:
        if not isinstance(fixture, Mapping) or fixture.get("role") not in {"front", "rear"}:
            continue
        source = fixture_root / str(fixture.get("relativePath", ""))
        payload = source.read_bytes()
        if sha256_bytes(payload) != fixture.get("expectedSha256"):
            raise ValueError("exact_bitmap_source_hash_mismatch")
        decoded = decode_png_rgba(payload)
        label = str(fixture.get("label", ""))
        path = f"source/public_fixture/{label}.png"
        source_artifacts[path] = payload
        decoded_views[label] = decoded
        source_records.append(
            {
                "viewId": str(fixture.get("viewId", "")),
                "label": label,
                "path": path,
                "sha256": sha256_bytes(payload),
                "decodedPixelHash": _pixel_hash(decoded),
                "width": decoded.width,
                "height": decoded.height,
                "colorSpace": decoded.color_space,
                "channelMeaning": decoded.channel_meaning,
                "sourceMode": "opened_frozen_exact_png_bytes",
                "fixtureRendererCalled": False,
            }
        )
    if set(decoded_views) != {"front", "back"}:
        raise ValueError("exact_bitmap_front_rear_missing")

    front, rear = decoded_views["front"], decoded_views["back"]
    rear_shift = _bounded_color_shift(front, rear)
    maps = _project_halves(
        front,
        rear,
        _target_bbox(visual_observations, "front"),
        _target_bbox(visual_observations, "back"),
        rear_shift,
    )
    artifacts: dict[str, bytes | dict[str, Any]] = {
        **source_artifacts,
        **{
            path: encode_png_rgba(ATLAS_SIZE, ATLAS_SIZE, maps[key])
            for key, path in BITMAP_PATHS.items()
            if key != "pbrReport"
        },
    }
    channel_meanings = {
        "baseColor": "sRGB source-observed or controlled-fill base colour RGBA",
        "normal": "uncalibrated D0 tangent-space normal estimate encoded RGB",
        "roughness": "uncalibrated D0 roughness estimate in RGB",
        "occlusion": "uncalibrated D0 ambient-occlusion estimate in RGB",
        "viewConfidence": "linear source confidence in RGB",
        "generatedRegionMask": "white generated/unseen, black source-observed",
        "sourceContribution": "red front, green rear, yellow blend, blue generated fill",
        "logoRegionMask": "white exact observed logo, black non-logo",
    }
    map_records = []
    for key, path in BITMAP_PATHS.items():
        if key == "pbrReport":
            continue
        map_payload = artifacts[path]
        assert isinstance(map_payload, bytes)
        map_records.append(
            {
                "mapId": key,
                "path": path,
                "sha256": sha256_bytes(map_payload),
                "width": ATLAS_SIZE,
                "height": ATLAS_SIZE,
                "colorSpace": "srgb" if key == "baseColor" else "linear_data",
                "channelMeaning": channel_meanings[key],
                "mediaType": "image/png",
            }
        )
    generated_fraction = _white_fraction(maps["generatedRegionMask"])
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "texture_bitmap_pbr.exact_tshirt_d0_v3",
        "stageVersion": EXACT_BITMAP_ATLAS_VERSION,
        "status": "pass",
        "atlas": {
            "width": ATLAS_SIZE,
            "height": ATLAS_SIZE,
            "layout": "front_left_half_rear_right_half_panel_uv_v1",
            "cameraIndependent": True,
            "viewConditionedTextureSelection": False,
            "colorClassification": "uncalibrated_baked_light_source_appearance",
            "colorNormalization": {
                "mode": "bounded_rear_to_front_garment_mean_rgb",
                "maximumAbsoluteChannelShift8bit": 12,
                "appliedRearShift8bit": list(rear_shift),
                "originalSourceEvidenceRetained": True,
            },
            "seamBlend": {
                "mode": "four_pixel_confidence_weighted_center_gutter",
                "widthPixels": 4,
                "meanRgbDiscontinuity8bit": _round(_seam_difference(maps["baseColor"])),
                "maximumMeanRgbDiscontinuity8bit": 18.0,
            },
        },
        "sourceViews": source_records,
        "maps": map_records,
        "coverage": {
            "sourceObservedFraction": _round(1.0 - generated_fraction),
            "generatedControlledFillFraction": _round(generated_fraction),
            "generatedPixelsMarked": True,
            "generatedPixelsLabelledSourceObserved": False,
        },
        "logoPreservation": {
            "sourceView": "front",
            "sourceColorRgba8": list(LOGO_RGBA),
            "atlasPixelCount": _white_count(maps["logoRegionMask"]),
            "preserved": _white_count(maps["logoRegionMask"]) > 0,
            "generatedOverwriteAllowed": False,
        },
        "pbr": {
            "baseColorAvailable": True,
            "baseColorSourceBackedVisibleRegions": True,
            "normalAvailable": True,
            "roughnessAvailable": True,
            "occlusionAvailable": True,
            "normalRoughnessAoPhysicalAccuracy": "not_measured",
            "estimateClassification": "uncalibrated_d0_estimates",
            "metallicFactor": 0.0,
            "appearancePhysicsSeparated": True,
            "fabricStiffnessDerivedFromColor": False,
        },
        "controlledFill": {
            "method": "deterministic_bounded_blue_fabric_prior_v1",
            "seed": 1701,
            "nonEmpty": generated_fraction > 0.0,
            "confidence": "low",
            "warning": "generated_region_not_source_fidelity_evidence",
            "observedPixelsWin": True,
        },
        "policy": {
            "publicSyntheticFixturePixelsPackaged": True,
            "privateUserPixelsPackaged": False,
            "containsUserImagery": False,
            "externalApis": False,
            "trainingUse": False,
            "evaluatorOnlyViewUsed": False,
            "fixtureRendererCalled": False,
        },
        "integrity": {"bitmapPbrReportHash": ""},
    }
    report["integrity"]["bitmapPbrReportHash"] = hash_bitmap_pbr_report(report)
    artifacts[BITMAP_PATHS["pbrReport"]] = report
    audit_bitmap_atlas_bundle(artifacts, report, visual_observations)
    return BitmapAtlasBundle(
        artifacts=artifacts,
        report=report,
        decoded_atlas=decode_png_rgba(_bytes(artifacts[BITMAP_PATHS["baseColor"]])),
    )


def _bytes(value: bytes | dict[str, Any]) -> bytes:
    if not isinstance(value, bytes):
        raise ValueError("exact_bitmap_expected_bytes")
    return value
