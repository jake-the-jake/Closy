from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from closy_forge.raster import DecodedPng, encode_png_rgba


@dataclass(frozen=True)
class SourceCapture:
    png: bytes
    mask: tuple[int, ...]
    landmarks: dict[str, tuple[float, float]]
    camera: dict[str, Any]


def render_source_capture(
    parameters: Mapping[str, Any],
    appearance: Mapping[str, Any],
    capture: Mapping[str, Any],
    *,
    role: str,
) -> SourceCapture:
    """Rasterize permitted source roles; this implementation is not used by target rendering."""
    width, height = (int(value) for value in capture["imageSize"])
    projection = _source_projection(parameters, capture, role)
    rgba = bytearray((236, 234, 228, 255) * (width * height))
    mask: list[int] = []
    base = tuple(int(value) for value in appearance["baseColorSrgb"])
    for y in range(height):
        py = (y + 0.5) / height
        for x in range(width):
            px = (x + 0.5) / width
            if _inside_source_shape(px, py, projection):
                index = y * width + x
                mask.append(index)
                colour = base
                if role == "front" and _inside_logo(px, py, appearance, projection):
                    colour = tuple(int(value) for value in appearance["logoColorSrgb"])
                offset = index * 4
                rgba[offset : offset + 4] = bytes((*colour, 255))
    _apply_capture_obstruction(rgba, width, height, capture)
    landmarks = _source_landmarks(projection)
    return SourceCapture(
        png=encode_png_rgba(width, height, bytes(rgba)),
        mask=tuple(mask),
        landmarks=landmarks,
        camera=dict(capture),
    )


def render_evaluator_target(
    parameters: Mapping[str, Any],
    appearance: Mapping[str, Any],
    camera: Mapping[str, Any],
) -> DecodedPng:
    """Independent evaluator renderer with a separate projection and inclusion implementation."""
    width, height = (int(value) for value in camera["imageSize"])
    centre_x = float(camera["principalPointNormalized"][0])
    top = 0.14 + float(camera["principalPointNormalized"][1]) - 0.5
    scale = 0.88 / float(camera["orthographicScale"])
    yaw = math.radians(float(camera["azimuthDegrees"]))
    foreshorten = 0.82 + 0.18 * abs(math.cos(yaw))
    body_half = (float(parameters["half_chest_width"]) + float(parameters["body_ease"])) * 0.50
    shoulder_half = float(parameters["shoulder_width"]) * 0.245
    body_bottom = top + float(parameters["garment_body_length"]) * 0.68 * scale
    sleeve_reach = float(parameters["sleeve_length"]) * 0.48 * scale
    sleeve_drop = float(parameters["armhole_depth"]) * 0.62 * scale
    rgba = bytearray((236, 234, 228, 255) * (width * height))
    base = tuple(int(value) for value in appearance["baseColorSrgb"])
    for y in range(height):
        ny = (y + 0.5) / height
        for x in range(width):
            nx = (x + 0.5) / width
            torso_t = min(1.0, max(0.0, (ny - top) / max(1e-9, body_bottom - top)))
            local_half = (shoulder_half * (1.0 - torso_t) + body_half * torso_t) * foreshorten
            torso = top <= ny <= body_bottom and abs(nx - centre_x) <= local_half
            sleeve_y = top + 0.055 * scale
            left_sleeve = (
                centre_x - shoulder_half * foreshorten - sleeve_reach
                <= nx
                <= centre_x - shoulder_half * foreshorten
                and sleeve_y <= ny <= sleeve_y + sleeve_drop
            )
            right_sleeve = (
                centre_x + shoulder_half * foreshorten
                <= nx
                <= centre_x + shoulder_half * foreshorten + sleeve_reach
                and sleeve_y <= ny <= sleeve_y + sleeve_drop
            )
            neck_rx = float(parameters["neckline_width"]) * 0.27 * foreshorten
            neck_ry = float(parameters["front_neckline_depth"]) * 0.32 * scale
            neck = ((nx - centre_x) / max(neck_rx, 1e-9)) ** 2 + (
                (ny - top) / max(neck_ry, 1e-9)
            ) ** 2 <= 1.0
            if (torso or left_sleeve or right_sleeve) and not neck:
                colour = base
                if _target_logo(nx, ny, appearance, centre_x, top, body_bottom):
                    colour = tuple(int(value) for value in appearance["logoColorSrgb"])
                offset = (y * width + x) * 4
                rgba[offset : offset + 4] = bytes((*colour, 255))
    return DecodedPng(width, height, bytes(rgba))


def source_features(capture: SourceCapture, *, role: str) -> dict[str, Any]:
    width, height = (int(value) for value in capture.camera["imageSize"])
    points = capture.landmarks
    return {
        "role": role,
        "imageSize": [width, height],
        "maskPixelCount": len(capture.mask),
        "maskCoverage": round(len(capture.mask) / (width * height), 9),
        "landmarks": {name: [round(x, 9), round(y, 9)] for name, (x, y) in points.items()},
        "camera": capture.camera,
    }


def _source_projection(
    parameters: Mapping[str, Any], camera: Mapping[str, Any], role: str
) -> dict[str, float]:
    scale = 0.88 / float(camera["orthographicScale"])
    centre_x = float(camera["principalPointNormalized"][0])
    top = 0.14 + float(camera["principalPointNormalized"][1]) - 0.5
    yaw = math.radians(float(camera["azimuthDegrees"]) - (180.0 if role == "rear" else 0.0))
    width_scale = 0.97 + 0.03 * math.cos(yaw)
    shoulder_half = float(parameters["shoulder_width"]) * 0.245 * width_scale
    chest_half = (
        (float(parameters["half_chest_width"]) + float(parameters["body_ease"]))
        * 0.50
        * width_scale
    )
    bottom = top + float(parameters["garment_body_length"]) * 0.68 * scale
    return {
        "cx": centre_x,
        "top": top,
        "bottom": bottom,
        "shoulderHalf": shoulder_half,
        "chestHalf": chest_half,
        "shoulderDrop": float(parameters["shoulder_slope"]) * 0.52 * scale,
        "armholeDrop": float(parameters["armhole_depth"]) * 0.62 * scale,
        "sleeveReach": float(parameters["sleeve_length"]) * 0.48 * scale,
        "sleeveOpening": float(parameters["sleeve_opening_width"]) * 0.36 * scale,
        "neckHalf": float(parameters["neckline_width"]) * 0.27 * width_scale,
        "neckDepth": float(
            parameters["back_neckline_depth"]
            if role == "rear"
            else parameters["front_neckline_depth"]
        )
        * 0.32
        * scale,
        "scale": scale,
        "widthScale": width_scale,
    }


def _inside_source_shape(x: float, y: float, p: Mapping[str, float]) -> bool:
    torso_t = min(1.0, max(0.0, (y - p["top"]) / max(1e-9, p["bottom"] - p["top"])))
    local_half = p["shoulderHalf"] * (1.0 - torso_t) + p["chestHalf"] * torso_t
    torso = p["top"] <= y <= p["bottom"] and abs(x - p["cx"]) <= local_half
    sleeve_top = p["top"] + p["shoulderDrop"]
    sleeve_bottom = sleeve_top + max(p["armholeDrop"], p["sleeveOpening"])
    left = (
        p["cx"] - p["shoulderHalf"] - p["sleeveReach"] <= x <= p["cx"] - p["shoulderHalf"]
        and sleeve_top <= y <= sleeve_bottom
    )
    right = (
        p["cx"] + p["shoulderHalf"] <= x <= p["cx"] + p["shoulderHalf"] + p["sleeveReach"]
        and sleeve_top <= y <= sleeve_bottom
    )
    neck = ((x - p["cx"]) / max(p["neckHalf"], 1e-9)) ** 2 + (
        (y - p["top"]) / max(p["neckDepth"], 1e-9)
    ) ** 2 <= 1.0
    return (torso or left or right) and not neck


def _source_landmarks(p: Mapping[str, float]) -> dict[str, tuple[float, float]]:
    shoulder_y = p["top"] + p["shoulderDrop"]
    armhole_y = shoulder_y + p["armholeDrop"]
    return {
        "neck.center": (p["cx"], p["top"]),
        "neck.left": (p["cx"] - p["neckHalf"], p["top"]),
        "neck.bottom": (p["cx"], p["top"] + p["neckDepth"]),
        "shoulder.left": (p["cx"] - p["shoulderHalf"], shoulder_y),
        "shoulder.right": (p["cx"] + p["shoulderHalf"], shoulder_y),
        "armhole.left": (p["cx"] - p["shoulderHalf"], armhole_y),
        "armhole.right": (p["cx"] + p["shoulderHalf"], armhole_y),
        "cuff.left": (p["cx"] - p["shoulderHalf"] - p["sleeveReach"], shoulder_y),
        "cuff.right": (p["cx"] + p["shoulderHalf"] + p["sleeveReach"], shoulder_y),
        "cuff.opening": (
            p["cx"] + p["shoulderHalf"] + p["sleeveReach"],
            shoulder_y + p["sleeveOpening"],
        ),
        "hem.left": (p["cx"] - p["chestHalf"], p["bottom"]),
        "hem.right": (p["cx"] + p["chestHalf"], p["bottom"]),
        "hem.center": (p["cx"], p["bottom"]),
    }


def _inside_logo(
    x: float, y: float, appearance: Mapping[str, Any], projection: Mapping[str, float]
) -> bool:
    shape = str(appearance["logoShape"])
    if shape == "none":
        return False
    u, v = (float(value) for value in appearance["logoCenterNormalized"])
    cx = projection["cx"] + (u - 0.5) * projection["chestHalf"] * 1.55
    cy = projection["top"] + v * (projection["bottom"] - projection["top"])
    size = float(appearance["logoScaleNormalized"]) * 0.5
    dx, dy = abs(x - cx), abs(y - cy)
    return {
        "circle": dx * dx + dy * dy <= size * size,
        "diamond": dx + dy <= size * 1.25,
        "bar": dx <= size * 1.4 and dy <= size * 0.45,
    }.get(shape, False)


def _target_logo(
    x: float,
    y: float,
    appearance: Mapping[str, Any],
    centre_x: float,
    top: float,
    bottom: float,
) -> bool:
    if appearance["logoShape"] == "none":
        return False
    u, v = (float(value) for value in appearance["logoCenterNormalized"])
    cx = centre_x + (u - 0.5) * 0.42
    cy = top + v * (bottom - top)
    radius = float(appearance["logoScaleNormalized"]) * 0.5
    dx, dy = abs(x - cx), abs(y - cy)
    if appearance["logoShape"] == "circle":
        return dx * dx + dy * dy <= radius * radius
    if appearance["logoShape"] == "diamond":
        return dx + dy <= radius * 1.25
    return dx <= radius * 1.4 and dy <= radius * 0.45


def _apply_capture_obstruction(
    rgba: bytearray, width: int, height: int, capture: Mapping[str, Any]
) -> None:
    fraction = float(capture.get("occlusionFraction", 0.0))
    if fraction <= 0.0:
        return
    band = max(1, round(width * fraction))
    start = width // 2 - band // 2
    for y in range(round(height * 0.69), round(height * 0.81)):
        for x in range(start, min(width, start + band)):
            offset = (y * width + x) * 4
            rgba[offset : offset + 4] = bytes((188, 184, 177, 255))
