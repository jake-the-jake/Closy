from __future__ import annotations

import base64
import math
import zlib
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from PIL import Image

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

ATLAS_VERSION = "closy.d0_v4.source_to_panel_uv_atlas.v2"
ATLAS_WIDTH = 256
ATLAS_HEIGHT = 160
PANEL_WIDTH = ATLAS_WIDTH // 2


@dataclass(frozen=True)
class RecoveredAppearance:
    base_color_png: bytes
    roughness_png: bytes
    metalness_png: bytes
    ambient_occlusion_png: bytes
    normal_png: bytes
    lineage_zlib: bytes
    manifest: dict[str, Any]


def recover_source_to_uv(
    front_png: bytes,
    rear_png: bytes | None,
) -> RecoveredAppearance:
    front = _decode(front_png)
    rear = _decode(rear_png) if rear_png is not None else None
    source_sizes = {"front": list(front.size), "rear": list(rear.size) if rear else None}
    if front.size != (128, 160):
        front = front.resize((128, 160), Image.Resampling.BILINEAR)
    if rear is not None and rear.size != (128, 160):
        rear = rear.resize((128, 160), Image.Resampling.BILINEAR)
    front_background = _background(front)
    rear_background = _background(rear) if rear is not None else front_background
    front_raw = _mask(front, front_background)
    front_foreground = _panel_mask(front_raw, PANEL_WIDTH)
    rear_raw = _mask(rear, rear_background) if rear is not None else set()
    rear_foreground = _panel_mask(rear_raw, PANEL_WIDTH) if rear is not None else set()
    if not front_foreground:
        raise ValueError("d0_v4_appearance_front_foreground_missing")
    panel_mappings = {
        "front": _panel_mapping(front_foreground, front_raw, PANEL_WIDTH),
        "rear": (
            _panel_mapping(rear_foreground, rear_raw, PANEL_WIDTH) if rear_foreground else None
        ),
    }
    fill = _dominant_foreground(front, front_foreground)
    atlas = Image.new("RGBA", (ATLAS_WIDTH, ATLAS_HEIGHT), (*fill, 255))
    pixels: Any = atlas.load()
    front_pixels: Any = front.load()
    rear_pixels: Any = rear.load() if rear is not None else None
    lineage = bytearray()
    observed = 0
    generated = 0
    for y in range(ATLAS_HEIGHT):
        for x in range(ATLAS_WIDTH):
            role = 1 if x < 128 else 2
            panel_x = x if role == 1 else x - PANEL_WIDTH
            source_mask = front_foreground if role == 1 else rear_foreground
            raw_mask = front_raw if role == 1 else rear_raw
            source = front_pixels if role == 1 else rear_pixels
            mapping = panel_mappings["front"] if role == 1 else panel_mappings["rear"]
            source_x, source_y = _source_coordinate(panel_x, y, mapping)
            source_index = source_y * PANEL_WIDTH + source_x
            is_observed = source is not None and source_index in source_mask
            if is_observed:
                value = source[source_x, source_y]
                pixels[x, y] = (value[0], value[1], value[2], 255)
                observed += 1
            else:
                generated += 1
            lineage.extend(
                (
                    role if is_observed else 0,
                    source_x,
                    source_y,
                    (255 if source_index in raw_mask else 192) if is_observed else 0,
                    0 if is_observed else 1,
                )
            )
    _blend_panel_seam(atlas, lineage)
    base = _encode(atlas)
    roughness = _constant_map("L", 205)
    metalness = _constant_map("L", 0)
    ambient_occlusion = _constant_map("L", 235)
    normal = _constant_map("RGB", (128, 128, 255))
    compressed_lineage = zlib.compress(bytes(lineage), level=9)
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "atlasVersion": ATLAS_VERSION,
        "dimensions": [ATLAS_WIDTH, ATLAS_HEIGHT],
        "sourceSizes": source_sizes,
        "normalization": "source_capture_resampled_to_declared_128x160_panel_uv_grid",
        "panelMappings": panel_mappings,
        "uvLayout": {
            "frontPanel": [0.0, 0.0, 0.5, 1.0],
            "rearPanel": [0.5, 0.0, 1.0, 1.0],
            "coordinateSemantics": "panel_uv_not_camera_plane",
        },
        "texelCount": ATLAS_WIDTH * ATLAS_HEIGHT,
        "observedTexelCount": observed,
        "generatedControlledFillTexelCount": generated,
        "observedFraction": round(observed / (ATLAS_WIDTH * ATLAS_HEIGHT), 12),
        "generatedFillCannotImproveObservedScore": True,
        "perTexelLineage": {
            "encoding": "zlib(role_u8,source_x_u8,source_y_u8,confidence_u8,generated_u8)",
            "uncompressedBytes": len(lineage),
            "compressedBytes": len(compressed_lineage),
            "sha256": sha256_bytes(compressed_lineage),
        },
        "baseColorSha256": sha256_bytes(base),
        "roughnessSha256": sha256_bytes(roughness),
        "metalnessSha256": sha256_bytes(metalness),
        "ambientOcclusionSha256": sha256_bytes(ambient_occlusion),
        "normalSha256": sha256_bytes(normal),
        "colourTransform": "identity_srgb8_declared_capture_space",
        "seamBlend": "two_column_confidence_weighted_panel_boundary_only",
        "physicalMaterialAccuracyClaimed": False,
        "pbrMapsAreBoundedVisualPresetOnly": True,
        "billboardOrSourcePlaneUsed": False,
        "evaluationTimeReprojectionUsed": False,
        "manifestDigest": "",
    }
    manifest["manifestDigest"] = _digest(manifest, "manifestDigest")
    return RecoveredAppearance(
        base_color_png=base,
        roughness_png=roughness,
        metalness_png=metalness,
        ambient_occlusion_png=ambient_occlusion,
        normal_png=normal,
        lineage_zlib=compressed_lineage,
        manifest=manifest,
    )


def rerender_from_persisted_atlas(
    appearance: RecoveredAppearance,
    geometry_mask_png: bytes,
    *,
    role: str,
    output_background: tuple[int, int, int],
    azimuth_degrees: float | None = None,
) -> bytes:
    if role not in {"front", "rear", "novel"}:
        raise ValueError("d0_v4_atlas_render_role_invalid")
    atlas = _decode(appearance.base_color_png)
    geometry = _decode(geometry_mask_png)
    if geometry.size != (128, 160):
        raise ValueError("d0_v4_geometry_mask_size_invalid")
    geometry_background = _background(geometry)
    mask = _mask(geometry, geometry_background)
    geometry_mapping = _panel_mapping(mask, mask, PANEL_WIDTH)
    output = Image.new("RGBA", geometry.size, (*output_background, 255))
    output_pixels: Any = output.load()
    atlas_pixels: Any = atlas.load()
    if role == "novel":
        angle = 45.0 if azimuth_degrees is None else azimuth_degrees
        rear_weight = _clamp(abs(angle) / 180.0, 0.0, 1.0)
    else:
        rear_weight = 0.0 if role == "front" else 1.0
    generated_fill = _atlas_fill_colour(atlas)
    for index in mask:
        x, y = index % PANEL_WIDTH, index // PANEL_WIDTH
        panel_x, panel_y = _panel_coordinate(x, y, geometry_mapping)
        front = atlas_pixels[panel_x, panel_y]
        rear = atlas_pixels[panel_x + PANEL_WIDTH, panel_y]
        colour = tuple(
            round(front[channel] * (1.0 - rear_weight) + rear[channel] * rear_weight)
            for channel in range(3)
        )
        if colour == output_background:
            colour = generated_fill
        output_pixels[x, y] = (colour[0], colour[1], colour[2], 255)
    return _encode(output)


def appearance_json_summary(appearance: RecoveredAppearance) -> dict[str, Any]:
    return {
        "manifest": appearance.manifest,
        "baseColorPngBase64": base64.b64encode(appearance.base_color_png).decode("ascii"),
        "lineageZlibBase64": base64.b64encode(appearance.lineage_zlib).decode("ascii"),
        "pbrPreset": {
            "roughness": 0.80,
            "metalness": 0.0,
            "ambientOcclusion": 0.92,
            "normalScale": 1.0,
            "physicalAccuracyMeasured": False,
        },
    }


def persist_recovered_appearance(
    root: Path, appearance: RecoveredAppearance, artifact_id: str
) -> dict[str, str]:
    directory = root / "docs/evidence/d0_v4_engineering/appearance" / artifact_id
    directory.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "baseColor": ("base-color.png", appearance.base_color_png),
        "roughness": ("roughness.png", appearance.roughness_png),
        "metalness": ("metalness.png", appearance.metalness_png),
        "ambientOcclusion": ("ambient-occlusion.png", appearance.ambient_occlusion_png),
        "normal": ("normal.png", appearance.normal_png),
        "lineage": ("lineage.bin.zlib", appearance.lineage_zlib),
    }
    result = {}
    for name, (filename, payload) in artifacts.items():
        path = directory / filename
        path.write_bytes(payload)
        result[name] = path.relative_to(root).as_posix()
    return result


def _blend_panel_seam(atlas: Image.Image, lineage: bytearray) -> None:
    pixels: Any = atlas.load()
    for y in range(ATLAS_HEIGHT):
        left = pixels[127, y]
        right = pixels[128, y]
        average = tuple(round((left[channel] + right[channel]) / 2.0) for channel in range(3))
        pixels[127, y] = (average[0], average[1], average[2], 255)
        pixels[128, y] = (average[0], average[1], average[2], 255)
        for x in (127, 128):
            offset = (y * ATLAS_WIDTH + x) * 5
            lineage[offset + 3] = min(lineage[offset + 3], 192)


def _decode(png: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(png)) as image:
            image.load()
            if image.format != "PNG":
                raise ValueError("d0_v4_appearance_source_not_png")
            return cast(Image.Image, image.convert("RGBA").copy())
    except OSError as exc:
        raise ValueError("d0_v4_appearance_source_corrupt") from exc


def _background(image: Image.Image) -> tuple[int, int, int]:
    pixels: Any = image.load()
    width, height = image.size
    corners = [pixels[0, 0], pixels[width - 1, 0], pixels[0, height - 1], pixels[-1, -1]]
    return tuple(
        round(math.fsum(pixel[channel] for pixel in corners) / len(corners)) for channel in range(3)
    )  # type: ignore[return-value]


def _mask(image: Image.Image | None, background: tuple[int, int, int]) -> set[int]:
    if image is None:
        return set()
    pixels = list(image.getdata())
    return {
        index
        for index, pixel in enumerate(pixels)
        if max(abs(pixel[channel] - background[channel]) for channel in range(3)) >= 24
    }


def _panel_mask(mask: set[int], width: int) -> set[int]:
    rows: dict[int, list[int]] = {}
    for index in mask:
        rows.setdefault(index // width, []).append(index % width)
    filled: set[int] = set()
    all_xs = [index % width for index in mask]
    centre = (min(all_xs) + max(all_xs)) / 2.0
    for y, xs in rows.items():
        radius = max(abs(min(xs) - centre), abs(max(xs) - centre))
        left = max(0, math.floor(centre - radius))
        right = min(width - 1, math.ceil(centre + radius))
        filled.update(y * width + x for x in range(left, right + 1))
    return filled


def _panel_mapping(mask: set[int], raw_mask: set[int], width: int) -> dict[str, Any]:
    if not mask:
        raise ValueError("d0_v4_panel_mapping_mask_empty")
    xs = [index % width for index in mask]
    ys = [index // width for index in mask]
    return {
        "sourceBoundsPixels": [min(xs), min(ys), max(xs) + 1, max(ys) + 1],
        "observedPanelPixelCount": len(mask),
        "directContrastPixelCount": len(raw_mask),
        "mapping": "normalized_panel_bounds_nearest_texel",
    }


def _source_coordinate(
    panel_x: int, panel_y: int, mapping: Mapping[str, Any] | None
) -> tuple[int, int]:
    if mapping is None:
        return panel_x, panel_y
    left, top, right, bottom = (int(value) for value in mapping["sourceBoundsPixels"])
    source_x = left + round(panel_x / max(1, PANEL_WIDTH - 1) * max(0, right - left - 1))
    source_y = top + round(panel_y / max(1, ATLAS_HEIGHT - 1) * max(0, bottom - top - 1))
    return source_x, source_y


def _panel_coordinate(x: int, y: int, mapping: Mapping[str, Any]) -> tuple[int, int]:
    left, top, right, bottom = (int(value) for value in mapping["sourceBoundsPixels"])
    panel_x = round((x - left) / max(1, right - left - 1) * (PANEL_WIDTH - 1))
    panel_y = round((y - top) / max(1, bottom - top - 1) * (ATLAS_HEIGHT - 1))
    return (
        int(_clamp(panel_x, 0, PANEL_WIDTH - 1)),
        int(_clamp(panel_y, 0, ATLAS_HEIGHT - 1)),
    )


def _dominant_foreground(image: Image.Image, mask: set[int]) -> tuple[int, int, int]:
    pixels = list(image.getdata())
    colours = Counter((pixels[index][0], pixels[index][1], pixels[index][2]) for index in mask)
    return colours.most_common(1)[0][0]


def _atlas_fill_colour(atlas: Image.Image) -> tuple[int, int, int]:
    pixels = list(atlas.getdata())
    colours = Counter((pixel[0], pixel[1], pixel[2]) for pixel in pixels)
    return colours.most_common(1)[0][0]


def _constant_map(mode: str, value: int | tuple[int, int, int]) -> bytes:
    return _encode(Image.new(mode, (ATLAS_WIDTH, ATLAS_HEIGHT), value))


def _encode(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _digest(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload[field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))
