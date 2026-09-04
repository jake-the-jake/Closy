from __future__ import annotations

import io
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter

from .common import sha256_bytes
from .video_mjpeg import decode_mjpeg_avi


@dataclass(frozen=True)
class PixelObservation:
    source_id: str
    frame_index: int
    width: int
    height: int
    rgba: bytes
    masks: dict[str, bytes]
    landmarks: dict[str, tuple[float, float]]
    quality: dict[str, Any]


def decode_public_session(source_root: Path, session: dict[str, Any]) -> list[PixelObservation]:
    observations: list[PixelObservation] = []
    for source in session["sources"]:
        payload = (source_root / str(source["contentAddressedName"])).read_bytes()
        if sha256_bytes(payload) != source["sourceSha256"]:
            raise ValueError("contestant_source_digest_invalid")
        if source["kind"] == "video":
            decoded = decode_mjpeg_avi(payload)
            for frame in decoded.frames:
                observations.append(
                    infer_pixel_observation(
                        str(source["sourceId"]),
                        frame.rgba,
                        frame.width,
                        frame.height,
                        frame_index=frame.index,
                    )
                )
        else:
            with Image.open(io.BytesIO(payload)) as image:
                image.load()
                rgba_image = image.convert("RGBA")
                observations.append(
                    infer_pixel_observation(
                        str(source["sourceId"]),
                        rgba_image.tobytes(),
                        rgba_image.width,
                        rgba_image.height,
                        frame_index=0,
                    )
                )
    return observations


def infer_pixel_observation(
    source_id: str, rgba: bytes, width: int, height: int, *, frame_index: int
) -> PixelObservation:
    if len(rgba) != width * height * 4 or min(width, height) < 256:
        raise ValueError("contestant_decoded_raster_invalid")
    background = _corner_background(rgba, width, height)
    masks = {
        name: bytearray(width * height)
        for name in ("garment", "body", "hair_hands", "occluder", "scale_target")
    }
    luminances: list[float] = []
    for index in range(width * height):
        red, green, blue, alpha = rgba[index * 4 : index * 4 + 4]
        luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        luminances.append(luminance)
        x, y = index % width, index // width
        distance = math.sqrt(
            (red - background[0]) ** 2 + (green - background[1]) ** 2 + (blue - background[2]) ** 2
        )
        saturation = max(red, green, blue) - min(red, green, blue)
        bottom_right = x > width * 0.72 and y > height * 0.72
        skin_like = red > 135 and 65 < green < red and 45 < blue < green + 35
        dark = max(red, green, blue) < 95
        checker_like = bottom_right and (dark or min(red, green, blue) > 215)
        if alpha and checker_like:
            masks["scale_target"][index] = 255
        elif alpha and skin_like:
            masks["body"][index] = 255
            if y > height * 0.48:
                masks["hair_hands"][index] = 255
        elif alpha and distance > 42 and saturation > 32:
            masks["garment"][index] = 255
        elif alpha and distance > 52 and dark:
            masks["occluder"][index] = 255
    garment = bytes(masks["garment"])
    bbox = _bbox(garment, width, height)
    coverage = sum(value > 0 for value in garment) / (width * height)
    focus = _focus_score(luminances, width, height)
    clipped = bbox[0] == 0 or bbox[1] == 0 or bbox[2] == width - 1 or bbox[3] == height - 1
    scale_detected = sum(value > 0 for value in masks["scale_target"]) >= 80
    rejected: list[str] = []
    if coverage < 0.025:
        rejected.append("garment_coverage_low")
    if coverage > 0.72:
        rejected.append("garment_coverage_high")
    if focus < 0.015:
        rejected.append("blur")
    if clipped:
        rejected.append("clipping")
    if not scale_detected:
        rejected.append("scale_target_undetectable")
    uncertain = _boundary(garment, width, height)
    masks["uncertain_boundary"] = bytearray(uncertain)
    landmarks = {
        "shoulderL": (bbox[0] / width, (bbox[1] + 5) / height),
        "shoulderR": (bbox[2] / width, (bbox[1] + 5) / height),
        "waistL": ((bbox[0] * 0.62 + bbox[2] * 0.38) / width, (bbox[3] - 6) / height),
        "waistR": ((bbox[0] * 0.38 + bbox[2] * 0.62) / width, (bbox[3] - 6) / height),
    }
    return PixelObservation(
        source_id,
        frame_index,
        width,
        height,
        rgba,
        {name: bytes(value) for name, value in masks.items()},
        landmarks,
        {
            "decoded": True,
            "accepted": not rejected,
            "rejectionReasons": rejected,
            "focusScore": round(focus, 8),
            "garmentCoverage": round(coverage, 8),
            "scaleTargetDetected": scale_detected,
            "clipped": clipped,
            "pixelDigest": sha256_bytes(rgba),
        },
    )


def qc_denominators(observations: Sequence[PixelObservation]) -> dict[str, Any]:
    accepted = [row for row in observations if row.quality["accepted"]]
    reasons: dict[str, int] = {}
    intersections: dict[str, int] = {}
    for observation in observations:
        row_reasons = sorted(str(value) for value in observation.quality["rejectionReasons"])
        for reason in row_reasons:
            reasons[reason] = reasons.get(reason, 0) + 1
        if len(row_reasons) > 1:
            key = "+".join(row_reasons)
            intersections[key] = intersections.get(key, 0) + 1
    return {
        "attempted": len(observations),
        "decoded": len(observations),
        "accepted": len(accepted),
        "rejected": len(observations) - len(accepted),
        "rejectedByReason": dict(sorted(reasons.items())),
        "rejectionReasonIntersections": dict(sorted(intersections.items())),
    }


def _corner_background(rgba: bytes, width: int, height: int) -> tuple[int, int, int]:
    points = ((0, 0), (width - 1, 0), (0, height - 1))
    colors = [rgba[(y * width + x) * 4 : (y * width + x) * 4 + 3] for x, y in points]
    return tuple(
        round(sum(color[channel] for color in colors) / len(colors)) for channel in range(3)
    )  # type: ignore[return-value]


def _bbox(mask: bytes, width: int, height: int) -> tuple[int, int, int, int]:
    indexes = [index for index, value in enumerate(mask) if value]
    if not indexes:
        return (0, 0, 0, 0)
    xs, ys = [index % width for index in indexes], [index // width for index in indexes]
    return min(xs), min(ys), max(xs), max(ys)


def _focus_score(luminance: Sequence[float], width: int, height: int) -> float:
    samples: list[float] = []
    for y in range(1, height - 1, 3):
        for x in range(1, width - 1, 3):
            index = y * width + x
            laplacian = (
                4 * luminance[index]
                - luminance[index - 1]
                - luminance[index + 1]
                - luminance[index - width]
                - luminance[index + width]
            )
            samples.append(laplacian * laplacian)
    return min(1.0, sum(samples) / max(1, len(samples)) / 12000.0)


def _boundary(mask: bytes, width: int, height: int) -> bytes:
    image = Image.frombytes("L", (width, height), mask)
    expanded = image.filter(ImageFilter.MaxFilter(5)).tobytes()
    eroded = image.filter(ImageFilter.MinFilter(5)).tobytes()
    return bytes(
        255 if outer != inner else 0 for outer, inner in zip(expanded, eroded, strict=True)
    )
