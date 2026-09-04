from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def render_novel_view_reference(
    family: str, target_parameters: Mapping[str, Any], *, width: int = 96, height: int = 128
) -> dict[str, Any]:
    """Evaluator-only analytic raster; independent from both source producer implementations."""
    body_length = float(target_parameters.get("bodyLength", 0.56))
    body_width = float(target_parameters.get("bodyWidth", 0.50))
    opening = float(target_parameters.get("openingWidth", 0.16))
    color = {
        "tshirt": (54, 126, 196),
        "sleeveless_top": (215, 86, 108),
        "simple_skirt": (124, 91, 179),
    }[family]
    pixels = bytearray(width * height * 4)
    foreground = bytearray(width * height)
    center_x = width * 0.5
    top = height * 0.22
    pixel_height = max(24.0, min(height * 0.62, body_length / 0.82 * height * 0.62))
    half_top = max(9.0, min(width * 0.34, body_width / 0.78 * width * 0.32))
    half_bottom = half_top * (1.12 if family == "simple_skirt" else 0.86)
    for y in range(height):
        t = (y - top) / pixel_height
        if not 0.0 <= t <= 1.0:
            continue
        half = half_top * (1.0 - t) + half_bottom * t
        for x in range(width):
            local = abs(x - center_x)
            neck_cutout = t < 0.12 and local < opening / 0.28 * width * 0.055
            if local <= half and not neck_cutout:
                index = y * width + x
                shade = 0.84 + 0.16 * max(0.0, math.cos((x - center_x) / half * 1.2))
                rgb = tuple(max(0, min(255, round(channel * shade))) for channel in color)
                pixels[index * 4 : index * 4 + 4] = bytes((*rgb, 255))
                foreground[index] = 255
    return {
        "rendererVersion": "closy.independent_evaluator_novel_raster.v2",
        "width": width,
        "height": height,
        "rgba": bytes(pixels),
        "foreground": bytes(foreground),
        "producerRendererImported": False,
        "contestantProjectorImported": False,
    }


def score_atlas_against_novel_view(
    atlas_rgba: bytes, observed_mask: bytes, reference: Mapping[str, Any]
) -> dict[str, float]:
    observed_indices = [index for index, value in enumerate(observed_mask) if value]
    foreground = bytes(reference["foreground"])
    reference_rgba = bytes(reference["rgba"])
    reference_indices = [index for index, value in enumerate(foreground) if value]
    if not observed_indices or not reference_indices:
        return {"deltaEProxy": 1.0, "ssimProxy": 0.0, "edgeFidelity": 0.0}
    atlas_mean = _mean_rgb(atlas_rgba, observed_indices)
    reference_mean = _mean_rgb(reference_rgba, reference_indices)
    delta = math.sqrt(
        sum((left - right) ** 2 for left, right in zip(atlas_mean, reference_mean, strict=True))
    )
    normalized_delta = min(1.0, delta / math.sqrt(3 * 255**2))
    atlas_contrast = _contrast(atlas_rgba, observed_indices, atlas_mean)
    reference_contrast = _contrast(reference_rgba, reference_indices, reference_mean)
    structure = 1.0 - min(1.0, abs(atlas_contrast - reference_contrast) / 90.0)
    return {
        "deltaEProxy": round(normalized_delta, 8),
        "ssimProxy": round(max(0.0, structure * (1.0 - normalized_delta * 0.5)), 8),
        "edgeFidelity": round(
            min(len(observed_indices), len(reference_indices))
            / max(len(observed_indices), len(reference_indices)),
            8,
        ),
    }


def _mean_rgb(rgba: bytes, indexes: list[int]) -> tuple[float, float, float]:
    return tuple(
        sum(rgba[index * 4 + channel] for index in indexes) / len(indexes) for channel in range(3)
    )  # type: ignore[return-value]


def _contrast(rgba: bytes, indexes: list[int], mean: tuple[float, float, float]) -> float:
    variance = sum(
        sum((rgba[index * 4 + channel] - mean[channel]) ** 2 for channel in range(3)) / 3
        for index in indexes
    ) / len(indexes)
    return math.sqrt(variance)
