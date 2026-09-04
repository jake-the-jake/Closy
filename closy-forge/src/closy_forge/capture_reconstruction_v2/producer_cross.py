from __future__ import annotations

import math
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

from .render_types import RenderedObservation


def render_cross_generator(
    session: dict[str, Any],
    *,
    hidden_nonce: int,
    view_index: int = 0,
    frame_index: int = 0,
) -> RenderedObservation:
    """Independent mismatched source: radial contours, alternate camera, no in-model primitives."""
    width, height = (int(value) for value in session["resolution"])
    nonce = hidden_nonce
    canvas = Image.new("RGBA", (width, height), (211, 219 + nonce % 21, 231, 255))
    layers = {
        name: Image.new("L", (width, height), 0)
        for name in (
            "garment",
            "body",
            "hair",
            "hands",
            "occluder",
            "scale_target",
        )
    }
    draw = ImageDraw.Draw(canvas)
    masks = {name: ImageDraw.Draw(layer) for name, layer in layers.items()}
    mode, family = str(session["mode"]), str(session["family"])
    phase = frame_index / 24.0
    pulse = math.sin(phase * math.tau)
    cloth_lift = math.cos(phase * math.tau)
    view_angle = (-31.0, 27.0, 61.0)[view_index % 3] if mode == "C" else pulse * 11.0
    pitch = 6.0 - view_index * 3.5
    focal = 292.0 + (nonce % 11) * 9.0 + view_index * 21.0
    principal_x = width * 0.5 + (nonce % 9) - 4
    principal_y = height * 0.5 + (nonce % 5) - 2
    # Use both periodic components so mirrored sine phases cannot collapse to
    # duplicate MJPEG frames after decoding.
    center = (
        principal_x + pulse * 11.0,
        height * (0.47 + cloth_lift * 0.025) + (principal_y - height * 0.5) + pitch * 0.4,
    )
    if mode in {"B", "D"}:
        _body_silhouette(draw, masks, center, width, height, pulse)
    contour = _radial_contour(
        family, center, width, height, view_angle, pulse, projection_scale=focal / 337.0
    )
    color = {
        "tshirt": (28, 143, 127, 255),
        "sleeveless_top": (222, 96, 174, 255),
        "simple_skirt": (107, 67, 160, 255),
    }[family]
    draw.polygon(contour, fill=color)
    masks["garment"].polygon(contour, fill=255)
    _diamond_scale_target(draw, masks["scale_target"], width, height)
    if mode == "E":
        occluder = [
            (round(width * 0.53), round(height * 0.23)),
            (round(width * 0.82), round(height * 0.29)),
            (round(width * 0.73), round(height * 0.79)),
            (round(width * 0.45), round(height * 0.68)),
        ]
        draw.polygon(occluder, fill=(51, 59, 66, 255))
        masks["occluder"].polygon(occluder, fill=255)
    garment = layers["garment"]
    outer = garment.filter(ImageFilter.MaxFilter(7))
    encoded = {name: layer.tobytes() for name, layer in layers.items()}
    encoded["uncertain_boundary"] = bytes(
        255 if expanded and not inner else 0
        for expanded, inner in zip(outer.tobytes(), garment.tobytes(), strict=True)
    )
    box = garment.getbbox() or (0, 0, 1, 1)
    landmarks = {
        "shoulderL": (box[0] / width, (box[1] + 5) / height),
        "shoulderR": (box[2] / width, (box[1] + 5) / height),
        "waistL": ((box[0] * 0.4 + box[2] * 0.6) / width, (box[3] - 9) / height),
        "waistR": ((box[0] * 0.6 + box[2] * 0.4) / width, (box[3] - 9) / height),
        "scaleCorner": ((width - 64) / width, (height - 50) / height),
    }
    return RenderedObservation(
        width,
        height,
        canvas.tobytes(),
        encoded,
        landmarks,
        {
            "yawDegrees": view_angle,
            "pitchDegrees": pitch,
            "focalPixels": focal,
            "principalX": principal_x,
            "principalY": principal_y,
            "radialK1": 0.0,
            "translationX": pulse * 0.04,
            "translationY": -0.02,
            "translationZ": 2.15 + (nonce % 13) * 0.025,
            "scaleMetersPerPixel": 0.20 / 34.0,
        },
        {
            "leftArmDegrees": -13.0 + pulse * 23.0,
            "rightArmDegrees": 11.0 - pulse * 19.0,
            "leftLegDegrees": pulse * 16.0,
            "rightLegDegrees": -pulse * 15.0,
        },
        {
            "bodyLength": 0.49 + (nonce % 9) * 0.012,
            "bodyWidth": 0.39 + (nonce % 7) * 0.013,
            "openingWidth": 0.12 + (nonce % 4) * 0.012,
            "sleeveLength": 0.24 if family == "tshirt" else 0.0,
            "hemWidth": 0.51 + (nonce % 6) * 0.017,
        },
        {
            "frameIndex": frame_index,
            "timestampNumerator": frame_index,
            "timestampDenominator": 12,
            "posePhase": pulse,
            "clothPhase": cloth_lift,
            "quality": "accepted",
        },
    )


def _radial_contour(
    family: str,
    center: tuple[float, float],
    width: int,
    height: int,
    yaw: float,
    pulse: float,
    *,
    projection_scale: float,
) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    count = 28
    for index in range(count):
        angle = index * math.tau / count
        vertical = math.sin(angle)
        horizontal = math.cos(angle)
        if family == "simple_skirt":
            radius_x = width * (0.12 + 0.08 * max(0.0, vertical)) * projection_scale
            radius_y = height * 0.22 * projection_scale
            y_offset = height * 0.16
        else:
            shoulder = 0.17 if family == "tshirt" else 0.135
            radius_x = width * (0.10 + shoulder * max(0.0, -vertical) ** 3) * projection_scale
            radius_y = height * 0.20 * projection_scale
            y_offset = 0.0
        x = center[0] + horizontal * radius_x + yaw * 0.09 * (1.0 + vertical) + pulse * 4
        y = center[1] + y_offset + vertical * radius_y
        points.append((round(x), round(y)))
    return points


def _body_silhouette(
    draw: ImageDraw.ImageDraw,
    masks: dict[str, ImageDraw.ImageDraw],
    center: tuple[float, float],
    width: int,
    height: int,
    pulse: float,
) -> None:
    skin = (185, 139, 113, 255)
    cx, cy = center
    head = (cx - width * 0.052, cy - height * 0.38, cx + width * 0.052, cy - height * 0.24)
    draw.ellipse(head, fill=skin)
    masks["body"].ellipse(head, fill=255)
    hair = (head[0] - 2, head[1] - 2, head[2] + 2, head[1] + height * 0.055)
    draw.pieslice(hair, 180, 360, fill=(37, 33, 31, 255))
    masks["hair"].pieslice(hair, 180, 360, fill=255)
    torso = [
        (round(cx - width * 0.11), round(cy - height * 0.22)),
        (round(cx + width * 0.11), round(cy - height * 0.22)),
        (round(cx + width * 0.08), round(cy + height * 0.28)),
        (round(cx - width * 0.08), round(cy + height * 0.28)),
    ]
    draw.polygon(torso, fill=skin)
    masks["body"].polygon(torso, fill=255)
    for sign in (-1, 1):
        shoulder = (cx + sign * width * 0.10, cy - height * 0.18)
        hand = (cx + sign * width * (0.24 + pulse * 0.03), cy + height * 0.22)
        draw.line((shoulder, hand), fill=skin, width=max(8, width // 28))
        masks["body"].line((shoulder, hand), fill=255, width=max(8, width // 28))
        hand_box = (hand[0] - 6, hand[1] - 7, hand[0] + 6, hand[1] + 7)
        draw.ellipse(hand_box, fill=skin)
        masks["hands"].ellipse(hand_box, fill=255)


def _diamond_scale_target(
    draw: ImageDraw.ImageDraw, mask: ImageDraw.ImageDraw, width: int, height: int
) -> None:
    cx, cy, radius = width - 47, height - 43, 24
    for ring in range(4, 0, -1):
        r = radius * ring / 4
        polygon = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
        fill = (238, 240, 232, 255) if ring % 2 else (18, 27, 30, 255)
        draw.polygon(polygon, fill=fill)
        mask.polygon(polygon, fill=255)
