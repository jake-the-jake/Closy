from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.raster import DecodedPng, decode_png_rgba, encode_png_rgba
from closy_forge.visual_understanding.raster_parser import LEFT_SLEEVE_RGBA, TORSO_RGBA

WIDTH: Final = 128
HEIGHT: Final = 160
BACKGROUND: Final = (246, 244, 239, 0)


@dataclass(frozen=True)
class IndependentTargetEvidence:
    family: str
    program_hash: str
    generator_id: str
    views: dict[str, DecodedPng]
    capture_measurements: dict[str, float]


def build_simple_trousers_target(seed: int) -> IndependentTargetEvidence:
    """Create a sealed target without invoking the Closy trousers pattern generator."""

    jitter = ((seed * 17) % 7 - 3) * 0.001
    target = {
        "halfWaist": 0.214 + jitter,
        "halfHip": 0.271 - jitter * 0.5,
        "outseam": 0.978 + jitter,
        "cuff": 0.147 - jitter * 0.25,
        "rise": 0.286,
    }
    front = _trousers_view(target, rear=False)
    back = _trousers_view(target, rear=True)
    return IndependentTargetEvidence(
        family="simple_trousers",
        program_hash=_sealed_program_hash("simple_trousers", seed, target),
        generator_id="closy.hidden_target.trousers_independent_scanline.v1",
        views={"front": front, "back": back},
        capture_measurements={
            "halfWaistMeters": target["halfWaist"],
            "halfHipMeters": target["halfHip"],
            "outseamMeters": target["outseam"],
            "cuffWidthMeters": target["cuff"],
        },
    )


def build_layered_asymmetric_target(seed: int) -> IndependentTargetEvidence:
    """Create a sealed two-layer target from independent silhouette equations."""

    jitter = ((seed * 13) % 9 - 4) * 0.001
    target = {
        "halfWidth": 0.327 + jitter,
        "bodyLength": 0.642 - jitter * 0.5,
        "armholeDepth": 0.226 + jitter * 0.25,
        "outerEase": 0.031,
        "asymmetryDrop": 0.094,
        "innerReveal": 0.026,
    }
    views = {
        label: _layered_view(target, label=label)
        for label in ("front", "back", "left_three_quarter", "right_three_quarter")
    }
    return IndependentTargetEvidence(
        family="layered_asymmetric",
        program_hash=_sealed_program_hash("layered_asymmetric", seed, target),
        generator_id="closy.hidden_target.layered_independent_scanline.v1",
        views=views,
        capture_measurements={
            "halfWidthMeters": target["halfWidth"],
            "bodyLengthMeters": target["bodyLength"],
            "armholeDepthMeters": target["armholeDepth"],
        },
    )


def _trousers_view(target: dict[str, float], *, rear: bool) -> DecodedPng:
    waist = target["halfWaist"] + (0.006 if rear else 0.0)
    hip = target["halfHip"] + (0.008 if rear else 0.0)
    length = target["outseam"]
    rise_y = length - target["rise"]
    gap = 0.034
    cuff = target["cuff"]
    left = [
        (-waist, length),
        (0.0, length),
        (-0.078 if rear else -0.064, rise_y),
        (-gap, 0.0),
        (-(gap + cuff), 0.0),
        (-hip, rise_y),
    ]
    right = [(-x, y) for x, y in reversed(left)]
    return _raster_world_polygons([(left, TORSO_RGBA), (right, TORSO_RGBA)])


def _layered_view(target: dict[str, float], *, label: str) -> DecodedPng:
    side_scale = 0.86 if "three_quarter" in label else 1.0
    direction = -1.0 if label == "left_three_quarter" else 1.0
    half = target["halfWidth"] * side_scale
    length = target["bodyLength"]
    outer_half = half + target["outerEase"]
    outer_drop_left = target["asymmetryDrop"] * (1.0 if direction > 0 else 0.72)
    outer = [
        (-outer_half, -outer_drop_left),
        (outer_half, 0.0),
        (outer_half, length - target["armholeDepth"]),
        (0.30 * side_scale, length - 0.035),
        (0.095, length),
        (0.0, length - (0.095 if label != "back" else 0.038)),
        (-0.095, length),
        (-0.30 * side_scale, length - 0.035),
        (-outer_half, length - target["armholeDepth"]),
    ]
    reveal = target["innerReveal"]
    inner = [
        (-half, -reveal),
        (half, -reveal),
        (half, length - target["armholeDepth"] - 0.012),
        (0.285 * side_scale, length - 0.045),
        (0.088, length - 0.004),
        (0.0, length - (0.09 if label != "back" else 0.035)),
        (-0.088, length - 0.004),
        (-0.285 * side_scale, length - 0.045),
        (-half, length - target["armholeDepth"] - 0.012),
    ]
    # Paint the inner layer first so its hem remains visible below the outer shell.
    return _raster_world_polygons([(inner, LEFT_SLEEVE_RGBA), (outer, TORSO_RGBA)])


def _raster_world_polygons(
    polygons: list[tuple[list[tuple[float, float]], tuple[int, int, int, int]]],
) -> DecodedPng:
    all_points = [point for polygon, _color in polygons for point in polygon]
    projected = [[_project(point) for point in polygon] for polygon, _color in polygons]
    all_projected = [point for polygon in projected for point in polygon]
    center_x = (min(x for x, _y in all_projected) + max(x for x, _y in all_projected)) / 2
    center_y = (min(y for _x, y in all_projected) + max(y for _x, y in all_projected)) / 2
    del all_points
    offset = (WIDTH * 0.5 - center_x, HEIGHT * 0.5 - center_y)
    pixels = bytearray(BACKGROUND * (WIDTH * HEIGHT))
    for projected_polygon, (_world, color) in zip(projected, polygons, strict=True):
        polygon = [(x + offset[0], y + offset[1]) for x, y in projected_polygon]
        _scanline_fill(pixels, polygon, color)
    # Exercise the same PNG boundary used by external capture inputs.
    return decode_png_rgba(encode_png_rgba(WIDTH, HEIGHT, bytes(pixels)))


def _project(point: tuple[float, float]) -> tuple[float, float]:
    return ((0.5 + point[0] * 0.46) * WIDTH, (0.78 - ((0.74 + point[1]) - 1.04) * 1.21) * HEIGHT)


def _scanline_fill(
    pixels: bytearray,
    polygon: list[tuple[float, float]],
    color: tuple[int, int, int, int],
) -> None:
    for y in range(HEIGHT):
        scan_y = y + 0.5
        intersections: list[float] = []
        for first, second in zip(polygon, polygon[1:] + polygon[:1], strict=True):
            if (first[1] > scan_y) == (second[1] > scan_y):
                continue
            ratio = (scan_y - first[1]) / (second[1] - first[1])
            intersections.append(first[0] + ratio * (second[0] - first[0]))
        intersections.sort()
        for left, right in zip(intersections[::2], intersections[1::2], strict=False):
            for x in range(max(0, int(left)), min(WIDTH, int(right + 1))):
                offset = (y * WIDTH + x) * 4
                pixels[offset : offset + 4] = bytes(color)


def _sealed_program_hash(family: str, seed: int, target: dict[str, float]) -> str:
    return sha256_bytes(
        canonical_dumps(
            {
                "generator": "closy.hidden_target_program.v1",
                "family": family,
                "seed": seed,
                "sealedParameters": target,
            }
        ).encode("utf-8")
    )
