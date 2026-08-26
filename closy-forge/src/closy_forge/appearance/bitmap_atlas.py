from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.raster import DecodedPng, decode_png_rgba, encode_png_rgba
from closy_forge.visual_understanding.raster_parser import (
    LEFT_SLEEVE_RGBA,
    LOGO_RGBA,
    RIGHT_SLEEVE_RGBA,
    TORSO_RGBA,
    build_project_authored_tshirt_pixel_views,
)

BITMAP_ATLAS_VERSION = "closy.texture_atlas.decoded_bitmap_pbr.d0_v2"
ATLAS_SIZE = 256

BITMAP_PATHS = {
    "baseColor": "textures/atlas/base_color.png",
    "normal": "textures/atlas/normal.png",
    "roughness": "textures/atlas/roughness.png",
    "occlusion": "textures/atlas/occlusion.png",
    "viewConfidence": "textures/atlas/view_confidence.png",
    "generatedRegionMask": "textures/atlas/generated_region_mask.png",
    "sourceContribution": "textures/atlas/source_contribution.png",
    "logoRegionMask": "textures/atlas/logo_region_mask.png",
    "pbrReport": "textures/bitmap_pbr_report.json",
}


@dataclass(frozen=True)
class BitmapAtlasBundle:
    artifacts: dict[str, bytes | dict[str, Any]]
    report: dict[str, Any]
    decoded_atlas: DecodedPng


def build_d0_bitmap_atlas(
    capture_record: Mapping[str, Any], visual_observations: Mapping[str, Any]
) -> BitmapAtlasBundle:
    fixture_views = build_project_authored_tshirt_pixel_views(capture_record)
    source_artifacts: dict[str, bytes | dict[str, Any]] = {}
    decoded_views: dict[str, DecodedPng] = {}
    source_records = []
    for view in fixture_views:
        png_bytes = encode_png_rgba(view.width, view.height, view.rgba)
        decoded = decode_png_rgba(png_bytes)
        path = f"source/public_fixture/{_safe_label(view.label)}.png"
        source_artifacts[path] = png_bytes
        decoded_views[view.label] = decoded
        source_records.append(
            {
                "viewId": view.view_id,
                "label": view.label,
                "path": path,
                "sha256": sha256_bytes(png_bytes),
                "decodedPixelHash": _pixel_hash(decoded),
                "width": decoded.width,
                "height": decoded.height,
                "colorSpace": decoded.color_space,
                "channelMeaning": decoded.channel_meaning,
            }
        )
    _verify_visual_pixel_hashes(source_records, visual_observations)
    front = decoded_views["front"]
    rear = decoded_views["back"]
    front_bbox = _target_bbox(visual_observations, "front")
    rear_bbox = _target_bbox(visual_observations, "back")
    rear_shift = _bounded_color_shift(front, rear)
    maps = _project_halves(front, rear, front_bbox, rear_bbox, rear_shift)
    artifacts: dict[str, bytes | dict[str, Any]] = {
        **source_artifacts,
        **{
            path: encode_png_rgba(ATLAS_SIZE, ATLAS_SIZE, maps[key])
            for key, path in BITMAP_PATHS.items()
            if key != "pbrReport"
        },
    }
    map_records = []
    channel_meanings = {
        "baseColor": "sRGB base colour RGBA; source observed or controlled fill",
        "normal": "derived tangent-space XYZ encoded RGB; alpha opaque",
        "roughness": "linear roughness in red; G/B mirror red; alpha opaque",
        "occlusion": "linear ambient occlusion in red; G/B mirror red; alpha opaque",
        "viewConfidence": "linear source confidence in red; G/B mirror red; alpha opaque",
        "generatedRegionMask": "white generated/unseen, black source-observed",
        "sourceContribution": "red front, green rear, yellow seam blend, blue generated fill",
        "logoRegionMask": "white deterministic source logo, black non-logo",
    }
    for key, path in BITMAP_PATHS.items():
        if key == "pbrReport":
            continue
        payload = artifacts[path]
        assert isinstance(payload, bytes)
        map_records.append(
            {
                "mapId": key,
                "path": path,
                "sha256": sha256_bytes(payload),
                "width": ATLAS_SIZE,
                "height": ATLAS_SIZE,
                "colorSpace": "srgb" if key == "baseColor" else "linear_data",
                "channelMeaning": channel_meanings[key],
                "mediaType": "image/png",
            }
        )
    generated_fraction = _white_fraction(maps["generatedRegionMask"])
    source_fraction = 1.0 - generated_fraction
    logo_pixels = _white_count(maps["logoRegionMask"])
    seam_difference = _seam_difference(maps["baseColor"])
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "texture_bitmap_pbr.demo_tshirt_d0_v2",
        "stageVersion": BITMAP_ATLAS_VERSION,
        "status": "pass",
        "atlas": {
            "width": ATLAS_SIZE,
            "height": ATLAS_SIZE,
            "layout": "front_left_half_rear_right_half_panel_uv_v1",
            "colorNormalization": {
                "mode": "bounded_rear_to_front_garment_mean_rgb",
                "maximumAbsoluteChannelShift8bit": 12,
                "appliedRearShift8bit": list(rear_shift),
            },
            "seamBlend": {
                "mode": "four_pixel_confidence_weighted_center_gutter",
                "widthPixels": 4,
                "meanRgbDiscontinuity8bit": _round(seam_difference),
                "maximumMeanRgbDiscontinuity8bit": 18.0,
            },
        },
        "sourceViews": source_records,
        "maps": map_records,
        "coverage": {
            "sourceObservedFraction": _round(source_fraction),
            "generatedControlledFillFraction": _round(generated_fraction),
            "generatedPixelsMarked": True,
            "generatedPixelsLabelledSourceObserved": False,
        },
        "logoPreservation": {
            "sourceView": "front",
            "sourceColorRgba8": list(LOGO_RGBA),
            "atlasPixelCount": logo_pixels,
            "preserved": logo_pixels > 0,
            "generatedOverwriteAllowed": False,
        },
        "pbr": {
            "baseColorAvailable": True,
            "derivedNormalAvailable": True,
            "normalMethod": "bounded_base_colour_luminance_gradient_d0_baseline",
            "roughnessAvailable": True,
            "occlusionAvailable": True,
            "appearancePhysicsSeparated": True,
            "fabricStiffnessDerivedFromColor": False,
        },
        "policy": {
            "publicSyntheticFixturePixelsPackaged": True,
            "privateUserPixelsPackaged": False,
            "containsUserImagery": False,
            "externalApis": False,
            "trainingUse": False,
            "unseenFillMode": "deterministic_bounded_blue_fabric_prior",
        },
        "integrity": {"bitmapPbrReportHash": ""},
    }
    report["integrity"]["bitmapPbrReportHash"] = hash_bitmap_pbr_report(report)
    artifacts[BITMAP_PATHS["pbrReport"]] = report
    audit_bitmap_atlas_bundle(artifacts, report, visual_observations)
    return BitmapAtlasBundle(
        artifacts=artifacts,
        report=report,
        decoded_atlas=decode_png_rgba(_bytes_artifact(artifacts, BITMAP_PATHS["baseColor"])),
    )


def hash_bitmap_pbr_report(report: Mapping[str, Any]) -> str:
    payload = dict(report)
    payload["integrity"] = dict(_mapping(report.get("integrity")))
    payload["integrity"]["bitmapPbrReportHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def audit_bitmap_atlas_bundle(
    artifacts: Mapping[str, bytes | Mapping[str, Any]],
    report: Mapping[str, Any],
    visual_observations: Mapping[str, Any],
) -> dict[str, Any]:
    if hash_bitmap_pbr_report(report) != _mapping(report.get("integrity")).get(
        "bitmapPbrReportHash"
    ):
        raise ValueError("bitmap_pbr_report_hash_mismatch")
    source_records = report.get("sourceViews", [])
    if not isinstance(source_records, list) or len(source_records) < 2:
        raise ValueError("bitmap_source_views_missing")
    for record in source_records:
        if not isinstance(record, Mapping):
            raise ValueError("bitmap_source_view_invalid")
        path = str(record.get("path", ""))
        source = _bytes_artifact(artifacts, path)
        decoded = decode_png_rgba(source)
        if sha256_bytes(source) != record.get("sha256"):
            raise ValueError("bitmap_source_hash_mismatch")
        if _pixel_hash(decoded) != record.get("decodedPixelHash"):
            raise ValueError("bitmap_source_decoded_hash_mismatch")
        if (decoded.width, decoded.height) != (
            int(record.get("width", -1)),
            int(record.get("height", -1)),
        ):
            raise ValueError("bitmap_source_dimensions_mismatch")
    _verify_visual_pixel_hashes(source_records, visual_observations)
    decoded_maps = {
        key: decode_png_rgba(_bytes_artifact(artifacts, path))
        for key, path in BITMAP_PATHS.items()
        if key != "pbrReport"
    }
    for key, decoded in decoded_maps.items():
        if decoded.width != ATLAS_SIZE or decoded.height != ATLAS_SIZE:
            raise ValueError(f"bitmap_atlas_dimensions_mismatch:{key}")
    map_records = {
        str(item.get("mapId", "")): item
        for item in report.get("maps", [])
        if isinstance(item, Mapping)
    }
    for key, path in BITMAP_PATHS.items():
        if key == "pbrReport":
            continue
        record = map_records.get(key)
        if record is None or record.get("path") != path:
            raise ValueError("bitmap_map_provenance_mismatch")
        if record.get("sha256") != sha256_bytes(_bytes_artifact(artifacts, path)):
            raise ValueError("bitmap_map_hash_mismatch")
    generated = decoded_maps["generatedRegionMask"].rgba
    confidence = decoded_maps["viewConfidence"].rgba
    contribution = decoded_maps["sourceContribution"].rgba
    for offset in range(0, len(generated), 4):
        generated_pixel = generated[offset] >= 128
        source_code = tuple(contribution[offset : offset + 3])
        source_observed = source_code in {(255, 0, 0), (0, 255, 0), (255, 255, 0)}
        if generated_pixel and source_observed:
            raise ValueError("bitmap_generated_provenance_mismatch")
        if generated_pixel and confidence[offset] > 96:
            raise ValueError("bitmap_forged_confidence_mask")
        if not generated_pixel and not source_observed:
            raise ValueError("bitmap_source_provenance_missing")
    logo = decoded_maps["logoRegionMask"].rgba
    base = decoded_maps["baseColor"].rgba
    logo_indices = [offset for offset in range(0, len(logo), 4) if logo[offset] >= 128]
    if not logo_indices:
        raise ValueError("bitmap_logo_missing")
    if any(tuple(base[offset : offset + 4]) != LOGO_RGBA for offset in logo_indices):
        raise ValueError("bitmap_logo_displaced_or_recoloured")
    if _seam_difference(base) > 18.0:
        raise ValueError("bitmap_seam_discontinuity")
    return {
        "status": "pass",
        "decodedSourceCount": len(source_records),
        "decodedMapCount": len(decoded_maps),
        "logoPixelCount": len(logo_indices),
    }


def _project_halves(
    front: DecodedPng,
    rear: DecodedPng,
    front_bbox: tuple[float, float, float, float],
    rear_bbox: tuple[float, float, float, float],
    rear_shift: tuple[int, int, int],
) -> dict[str, bytes]:
    fill = (42, 96, 210, 255)
    base = bytearray(fill * (ATLAS_SIZE * ATLAS_SIZE))
    confidence = bytearray((48, 48, 48, 255) * (ATLAS_SIZE * ATLAS_SIZE))
    generated = bytearray((255, 255, 255, 255) * (ATLAS_SIZE * ATLAS_SIZE))
    contribution = bytearray((0, 0, 255, 255) * (ATLAS_SIZE * ATLAS_SIZE))
    logo = bytearray((0, 0, 0, 255) * (ATLAS_SIZE * ATLAS_SIZE))
    for x_start, source, bbox, source_code, shift in [
        (0, front, front_bbox, (255, 0, 0, 255), (0, 0, 0)),
        (ATLAS_SIZE // 2, rear, rear_bbox, (0, 255, 0, 255), rear_shift),
    ]:
        for y in range(ATLAS_SIZE):
            v = (y + 0.5) / ATLAS_SIZE
            sy = _sample_coordinate(v, bbox[1], bbox[3], source.height)
            for local_x in range(ATLAS_SIZE // 2):
                u = (local_x + 0.5) / (ATLAS_SIZE // 2)
                sx = _sample_coordinate(u, bbox[0], bbox[2], source.width)
                source_offset = (sy * source.width + sx) * 4
                color = tuple(source.rgba[source_offset : source_offset + 4])
                if not _is_garment_color(color):
                    continue
                target_offset = (y * ATLAS_SIZE + x_start + local_x) * 4
                shifted = (
                    _clamp8(color[0] + shift[0]),
                    _clamp8(color[1] + shift[1]),
                    _clamp8(color[2] + shift[2]),
                    255,
                )
                base[target_offset : target_offset + 4] = bytes(shifted)
                confidence[target_offset : target_offset + 4] = bytes((238, 238, 238, 255))
                generated[target_offset : target_offset + 4] = bytes((0, 0, 0, 255))
                contribution[target_offset : target_offset + 4] = bytes(source_code)
                if color == LOGO_RGBA:
                    logo[target_offset : target_offset + 4] = bytes((255, 255, 255, 255))
    _blend_center_seam(base, confidence, generated, contribution)
    normal = _derived_normal(bytes(base))
    roughness = _roughness_map(bytes(base), bytes(logo))
    occlusion = _occlusion_map(bytes(generated))
    return {
        "baseColor": bytes(base),
        "normal": normal,
        "roughness": roughness,
        "occlusion": occlusion,
        "viewConfidence": bytes(confidence),
        "generatedRegionMask": bytes(generated),
        "sourceContribution": bytes(contribution),
        "logoRegionMask": bytes(logo),
    }


def _blend_center_seam(
    base: bytearray,
    confidence: bytearray,
    generated: bytearray,
    contribution: bytearray,
) -> None:
    for y in range(ATLAS_SIZE):
        left_offset = (y * ATLAS_SIZE + 125) * 4
        right_offset = (y * ATLAS_SIZE + 130) * 4
        left = tuple(base[left_offset : left_offset + 4])
        right = tuple(base[right_offset : right_offset + 4])
        blend = tuple(round((left[channel] + right[channel]) / 2) for channel in range(3)) + (255,)
        source_backed = generated[left_offset] == 0 and generated[right_offset] == 0
        for x in range(126, 130):
            offset = (y * ATLAS_SIZE + x) * 4
            base[offset : offset + 4] = bytes(blend)
            if source_backed:
                confidence[offset : offset + 4] = bytes((220, 220, 220, 255))
                generated[offset : offset + 4] = bytes((0, 0, 0, 255))
                contribution[offset : offset + 4] = bytes((255, 255, 0, 255))


def _derived_normal(base: bytes) -> bytes:
    output = bytearray((128, 128, 255, 255) * (ATLAS_SIZE * ATLAS_SIZE))
    for y in range(1, ATLAS_SIZE - 1):
        for x in range(1, ATLAS_SIZE - 1):
            left = _luminance(base, x - 1, y)
            right = _luminance(base, x + 1, y)
            up = _luminance(base, x, y - 1)
            down = _luminance(base, x, y + 1)
            nx = _clamp8(round(128 + (left - right) * 0.18))
            ny = _clamp8(round(128 + (up - down) * 0.18))
            offset = (y * ATLAS_SIZE + x) * 4
            output[offset : offset + 4] = bytes((nx, ny, 255, 255))
    return bytes(output)


def _roughness_map(base: bytes, logo: bytes) -> bytes:
    del base
    output = bytearray()
    for offset in range(0, len(logo), 4):
        value = 196 if logo[offset] >= 128 else 220
        output.extend((value, value, value, 255))
    return bytes(output)


def _occlusion_map(generated: bytes) -> bytes:
    output = bytearray()
    for offset in range(0, len(generated), 4):
        value = 246 if generated[offset] >= 128 else 255
        output.extend((value, value, value, 255))
    return bytes(output)


def _bounded_color_shift(front: DecodedPng, rear: DecodedPng) -> tuple[int, int, int]:
    front_mean = _garment_mean(front)
    rear_mean = _garment_mean(rear)
    return (
        max(-12, min(12, round(front_mean[0] - rear_mean[0]))),
        max(-12, min(12, round(front_mean[1] - rear_mean[1]))),
        max(-12, min(12, round(front_mean[2] - rear_mean[2]))),
    )


def _garment_mean(image: DecodedPng) -> tuple[float, float, float]:
    colors = [
        tuple(image.rgba[offset : offset + 4])
        for offset in range(0, len(image.rgba), 4)
        if _is_garment_color(tuple(image.rgba[offset : offset + 4]))
    ]
    return (
        sum(color[0] for color in colors) / max(1, len(colors)),
        sum(color[1] for color in colors) / max(1, len(colors)),
        sum(color[2] for color in colors) / max(1, len(colors)),
    )


def _target_bbox(
    visual_observations: Mapping[str, Any], label: str
) -> tuple[float, float, float, float]:
    for view in visual_observations.get("views", []):
        if not isinstance(view, Mapping) or view.get("label") != label:
            continue
        for mask in view.get("masks", []):
            if isinstance(mask, Mapping) and mask.get("semanticId") == "component.tshirt":
                bbox = _mapping(mask.get("bbox"))
                return (
                    float(bbox.get("minX", 0.0)),
                    float(bbox.get("minY", 0.0)),
                    float(bbox.get("maxX", 1.0)),
                    float(bbox.get("maxY", 1.0)),
                )
    raise ValueError(f"bitmap_target_bbox_missing:{label}")


def _verify_visual_pixel_hashes(
    source_records: list[dict[str, Any]], visual_observations: Mapping[str, Any]
) -> None:
    expected = {
        str(view.get("label", "")): _mapping(view.get("pixelEvidence")).get("normalizedPixelHash")
        for view in visual_observations.get("views", [])
        if isinstance(view, Mapping)
    }
    for record in source_records:
        if record["decodedPixelHash"] != expected.get(record["label"]):
            raise ValueError(f"bitmap_source_view_role_or_hash_mismatch:{record['label']}")


def _pixel_hash(decoded: DecodedPng) -> str:
    return sha256_bytes(
        b"CLOSY_D0_TSHIRT_NORMALIZED_RGBA_V1"
        + canonical_dumps({"width": decoded.width, "height": decoded.height}).encode("utf-8")
        + decoded.rgba
    )


def _is_garment_color(color: tuple[int, ...]) -> bool:
    return color in {TORSO_RGBA, LEFT_SLEEVE_RGBA, RIGHT_SLEEVE_RGBA, LOGO_RGBA}


def _sample_coordinate(value: float, low: float, high: float, size: int) -> int:
    return max(0, min(size - 1, int((low + value * (high - low)) * size)))


def _luminance(rgba: bytes, x: int, y: int) -> float:
    offset = (y * ATLAS_SIZE + x) * 4
    return rgba[offset] * 0.2126 + rgba[offset + 1] * 0.7152 + rgba[offset + 2] * 0.0722


def _white_fraction(rgba: bytes) -> float:
    return _white_count(rgba) / (len(rgba) // 4)


def _white_count(rgba: bytes) -> int:
    return sum(1 for offset in range(0, len(rgba), 4) if rgba[offset] >= 128)


def _seam_difference(base: bytes) -> float:
    values = []
    for y in range(ATLAS_SIZE):
        left = (y * ATLAS_SIZE + 127) * 4
        right = (y * ATLAS_SIZE + 128) * 4
        values.append(
            sum(abs(base[left + channel] - base[right + channel]) for channel in range(3)) / 3
        )
    return sum(values) / len(values)


def _bytes_artifact(artifacts: Mapping[str, bytes | Mapping[str, Any]], path: str) -> bytes:
    payload = artifacts.get(path)
    if not isinstance(payload, bytes):
        raise ValueError(f"bitmap_artifact_missing_or_not_bytes:{path}")
    return payload


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_label(label: str) -> str:
    return "".join(char if char.isalnum() or char in "_-" else "_" for char in label)


def _clamp8(value: int) -> int:
    return max(0, min(255, value))


def _round(value: float) -> float:
    return round(float(value), 9)
