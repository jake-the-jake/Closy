from __future__ import annotations

import math
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

from .render_types import RenderedObservation

ROLES = ("garment", "body", "hair", "hands", "occluder", "scale_target")


def render_in_model(
    session: dict[str, Any],
    *,
    hidden_nonce: int,
    view_index: int = 0,
    frame_index: int = 0,
) -> RenderedObservation:
    width, height = (int(value) for value in session["resolution"])
    nonce = hidden_nonce
    background = (222 + nonce % 19, 226 + nonce % 13, 218 + nonce % 17, 255)
    image = Image.new("RGBA", (width, height), background)
    masks = {role: Image.new("L", (width, height), 0) for role in ROLES}
    drawers = {role: ImageDraw.Draw(mask) for role, mask in masks.items()}
    draw = ImageDraw.Draw(image)
    mode, family = str(session["mode"]), str(session["family"])
    motion = math.sin(frame_index * math.tau / 24.0) if mode == "D" else 0.0
    cloth_lift = math.cos(frame_index * math.tau / 24.0) if mode == "D" else 0.0
    yaw = (-24.0, 18.0, 48.0)[view_index % 3] if mode == "C" else 7.0 * motion
    focal = 330.0 + (nonce % 7) * 11.0 + view_index * 17.0
    pitch = -3.0 + view_index * 2.0
    principal_x = width / 2 + (nonce % 5) - 2
    principal_y = height / 2 + (nonce % 7) - 3
    projection_scale = focal / 363.0
    center_x = round(principal_x + motion * 9.0 + (view_index - 1) * 5)
    # The orthogonal cloth phase keeps all 24 decoded frames causally distinct;
    # a sine-only cycle would repeat geometry at mirrored timestamps.
    top = round(
        height * 0.20
        + abs(yaw) * 0.05
        + cloth_lift * height * 0.025
        + (principal_y - height / 2)
        + pitch * 0.35
    )
    body_required = mode in {"B", "D"}
    if body_required:
        _draw_body(draw, drawers, center_x, top, width, height, motion)
    garment_polygon = _garment_polygon(
        family,
        center_x,
        top,
        width,
        height,
        presentation=str(session["presentation"]),
        yaw=yaw,
        motion=motion,
        projection_scale=projection_scale,
    )
    garment_color = {
        "tshirt": (42, 104 + nonce % 60, 188, 255),
        "sleeveless_top": (196, 72 + nonce % 40, 154, 255),
        "simple_skirt": (66, 82, 126 + nonce % 80, 255),
    }[family]
    draw.polygon(garment_polygon, fill=garment_color)
    drawers["garment"].polygon(garment_polygon, fill=255)
    if family == "tshirt":
        sleeve_width = max(12, width // 13)
        sleeve_y = top + height // 11
        for direction in (-1, 1):
            sleeve = [
                (center_x + direction * width // 9, sleeve_y),
                (center_x + direction * width // 5, sleeve_y + round(motion * 7 * direction)),
                (center_x + direction * (width // 5 + sleeve_width), sleeve_y + height // 12),
                (center_x + direction * width // 10, sleeve_y + height // 10),
            ]
            draw.polygon(sleeve, fill=garment_color)
            drawers["garment"].polygon(sleeve, fill=255)
    _draw_scale_target(draw, drawers["scale_target"], width, height, nonce)
    if mode == "E":
        box = (center_x - width // 4, top + height // 6, center_x + width // 20, top + height // 2)
        draw.rectangle(box, fill=(82, 72, 64, 255))
        drawers["occluder"].rectangle(box, fill=255)
    uncertain = masks["garment"].filter(ImageFilter.MaxFilter(5))
    uncertain_bytes = bytes(
        255 if outer and not inner else 0
        for outer, inner in zip(uncertain.tobytes(), masks["garment"].tobytes(), strict=True)
    )
    mask_bytes = {role: mask.tobytes() for role, mask in masks.items()}
    mask_bytes["uncertain_boundary"] = uncertain_bytes
    garment_box = masks["garment"].getbbox() or (0, 0, 1, 1)
    landmarks = {
        "shoulderL": (garment_box[0] / width, (garment_box[1] + 8) / height),
        "shoulderR": (garment_box[2] / width, (garment_box[1] + 8) / height),
        "waistL": ((center_x - width * 0.10) / width, (garment_box[3] - 8) / height),
        "waistR": ((center_x + width * 0.10) / width, (garment_box[3] - 8) / height),
        "scaleCorner": ((width - 54) / width, (height - 54) / height),
    }
    return RenderedObservation(
        width,
        height,
        image.tobytes(),
        mask_bytes,
        landmarks,
        {
            "yawDegrees": yaw,
            "pitchDegrees": pitch,
            "focalPixels": focal,
            "principalX": principal_x,
            "principalY": principal_y,
            "radialK1": 0.0,
            "translationX": (center_x - width / 2) / width,
            "translationY": 0.0,
            "translationZ": 2.4 + (nonce % 9) * 0.03,
            "scaleMetersPerPixel": 0.20 / 36.0,
        },
        {
            "leftArmDegrees": -8.0 + motion * 18.0,
            "rightArmDegrees": 8.0 - motion * 18.0,
            "leftLegDegrees": motion * 12.0,
            "rightLegDegrees": -motion * 12.0,
        },
        _parameters(family, nonce),
        {
            "frameIndex": frame_index,
            "timestampNumerator": frame_index,
            "timestampDenominator": 12,
            "posePhase": motion,
            "clothPhase": cloth_lift,
            "quality": "accepted",
        },
    )


def _draw_body(
    draw: ImageDraw.ImageDraw,
    masks: dict[str, ImageDraw.ImageDraw],
    center_x: int,
    top: int,
    width: int,
    height: int,
    motion: float,
) -> None:
    skin = (207, 164, 134, 255)
    head = (center_x - width // 16, top - height // 7, center_x + width // 16, top)
    draw.ellipse(head, fill=skin)
    masks["body"].ellipse(head, fill=255)
    hair = (head[0], head[1], head[2], head[1] + height // 18)
    draw.ellipse(hair, fill=(58, 42, 36, 255))
    masks["hair"].ellipse(hair, fill=255)
    torso = (center_x - width // 9, top, center_x + width // 9, top + height // 2)
    draw.rounded_rectangle(torso, radius=width // 14, fill=skin)
    masks["body"].rounded_rectangle(torso, radius=width // 14, fill=255)
    for direction in (-1, 1):
        hand_x = center_x + direction * (width // 5 + round(motion * 8))
        arm = (center_x + direction * width // 10, top + height // 14, hand_x, top + height // 2)
        draw.line(arm, fill=skin, width=max(9, width // 24))
        masks["body"].line(arm, fill=255, width=max(9, width // 24))
        hand = (hand_x - 6, top + height // 2 - 6, hand_x + 6, top + height // 2 + 6)
        draw.ellipse(hand, fill=skin)
        masks["hands"].ellipse(hand, fill=255)


def _draw_scale_target(
    draw: ImageDraw.ImageDraw, mask: ImageDraw.ImageDraw, width: int, height: int, nonce: int
) -> None:
    left, top, cell = width - 54, height - 54, 9
    for row in range(4):
        for column in range(4):
            color = (245, 245, 235, 255) if (row + column + nonce) % 2 else (25, 25, 28, 255)
            box = (
                left + column * cell,
                top + row * cell,
                left + (column + 1) * cell - 1,
                top + (row + 1) * cell - 1,
            )
            draw.rectangle(box, fill=color)
            mask.rectangle(box, fill=255)


def _garment_polygon(
    family: str,
    center_x: int,
    top: int,
    width: int,
    height: int,
    *,
    presentation: str,
    yaw: float,
    motion: float,
    projection_scale: float,
) -> list[tuple[int, int]]:
    skew = round(yaw * 0.12)
    sway = round(motion * 8)
    if family == "simple_skirt":
        waist, hem, length = width // 9, width // 5, height // 3
        points = [
            (center_x - waist + skew, top + height // 4),
            (center_x + waist + skew, top + height // 4),
            (center_x + hem + sway, top + height // 4 + length),
            (center_x - hem + sway, top + height // 4 + length),
        ]
    else:
        shoulder = width // (7 if family == "tshirt" else 8)
        waist = width // 10
        length = height // 3 + (height // 18 if presentation == "hung" else 0)
        points = [
            (center_x - shoulder + skew, top + height // 18),
            (center_x + shoulder + skew, top + height // 18),
            (center_x + waist + sway, top + length),
            (center_x - waist + sway, top + length),
        ]
    return [
        (
            center_x + round((x - center_x) * projection_scale),
            top + round((y - top) * projection_scale),
        )
        for x, y in points
    ]


def _parameters(family: str, nonce: int) -> dict[str, float]:
    return {
        "bodyLength": 0.52 + (nonce % 7) * 0.01,
        "bodyWidth": 0.42 + (nonce % 5) * 0.012,
        "openingWidth": 0.13 + (nonce % 3) * 0.01,
        "sleeveLength": 0.21 if family == "tshirt" else 0.0,
        "hemWidth": 0.48 + (nonce % 4) * 0.015,
    }
