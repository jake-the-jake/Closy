from __future__ import annotations

import math
from collections import Counter, deque
from collections.abc import Mapping
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from PIL import Image

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes

OBSERVATION_VERSION = "closy.d0_v4.rgb_observation.v1"
CONTRACT_PATH = Path("docs/evidence/d0_v4_engineering/observation_contract_v1.json")
ROLE_FEATURES = (
    "valid",
    "bbox_width",
    "bbox_height",
    "foreground_fraction",
    "centroid_x",
    "centroid_y",
    "span_q10",
    "span_q20",
    "span_q35",
    "span_q50",
    "span_q70",
    "span_q90",
    "central_gap_width",
    "central_gap_depth",
    "edge_asymmetry",
    "mean_red",
    "mean_green",
    "mean_blue",
    "background_contrast",
    "uncertain_fraction",
)
FEATURE_NAMES = tuple(f"{role}_{name}" for role in ("front", "rear") for name in ROLE_FEATURES)


class ObservationRejected(ValueError):
    """Typed fail-closed observation rejection."""


def observation_contract() -> dict[str, Any]:
    contract: dict[str, Any] = {
        "schemaVersion": 1,
        "contractVersion": OBSERVATION_VERSION,
        "decodedOrientation": "row_major_top_left_origin_x_right_y_down",
        "colourSpace": "srgb8_unpremultiplied",
        "alphaConvention": "alpha_is_advisory_not_foreground_authority",
        "foregroundEvidence": "largest_rgb_background_distinct_component",
        "backgroundEstimator": "dominant_quantized_border_rgb",
        "backgroundDistanceThreshold": 24,
        "cropPolicy": "physical_pixel_crop_with_explicit_output_to_original_affine",
        "paddingPolicy": "declared_solid_background_padding_with_explicit_affine",
        "cameraMetadataRequired": True,
        "viewRoles": ["front", "rear", "missing_rear"],
        "missingRearPolicy": "bounded_front_only_route_or_typed_abstention",
        "landmarkCoordinateFrame": "normalized_decoded_view",
        "occlusionMap": "rgb_uncertainty_mask_excluded_from_foreground_measurements",
        "observationToOriginalTransformRequired": True,
        "sourceIdentity": "domain_separated_sha256_of_public_synthetic_source_bytes",
        "featureNames": list(FEATURE_NAMES),
        "trainingInferenceExtractor": "same_implementation_and_contract_digest",
        "contractDigest": "",
    }
    contract["contractDigest"] = _digest(contract, "contractDigest")
    return contract


def load_observation_contract(root: Path) -> dict[str, Any]:
    value = read_json(root / CONTRACT_PATH)
    if not isinstance(value, dict):
        raise ValueError("d0_v4_observation_contract_mapping_required")
    issues = validate_observation_contract(value)
    if issues:
        raise ValueError("d0_v4_observation_contract_invalid:" + ";".join(issues))
    return value


def validate_observation_contract(contract: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if contract.get("contractVersion") != OBSERVATION_VERSION:
        issues.append("observation_contract_version_invalid")
    if contract.get("alphaConvention") != "alpha_is_advisory_not_foreground_authority":
        issues.append("alpha_convention_invalid")
    if contract.get("featureNames") != list(FEATURE_NAMES):
        issues.append("feature_axis_invalid")
    if contract.get("missingRearPolicy") != "bounded_front_only_route_or_typed_abstention":
        issues.append("missing_rear_policy_invalid")
    if contract.get("observationToOriginalTransformRequired") is not True:
        issues.append("observation_transform_missing")
    if contract.get("contractDigest") != _digest(contract, "contractDigest"):
        issues.append("observation_contract_digest_invalid")
    return sorted(set(issues))


def extract_observation(
    front_png: bytes,
    rear_png: bytes | None,
    *,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    views = {
        "front": _extract_view(front_png, "front", _mapping(metadata.get("front"))),
        "rear": (
            _extract_view(rear_png, "rear", _mapping(metadata.get("rear")))
            if rear_png is not None
            else _missing_view("rear")
        ),
    }
    values = [
        float(views[role]["features"][name]) for role in ("front", "rear") for name in ROLE_FEATURES
    ]
    if any(not math.isfinite(value) for value in values):
        raise ObservationRejected("nonfinite_observation_feature")
    route = "multiview" if rear_png is not None else "front_only_bounded"
    observation: dict[str, Any] = {
        "schemaVersion": 1,
        "observationVersion": OBSERVATION_VERSION,
        "contractDigest": observation_contract()["contractDigest"],
        "route": route,
        "views": views,
        "featureNames": list(FEATURE_NAMES),
        "featureValues": [round(value, 12) for value in values],
        "pixelDerived": True,
        "targetParametersRead": False,
        "observationDigest": "",
    }
    observation["observationDigest"] = _digest(observation, "observationDigest")
    return observation


def apply_crop_and_padding(
    png: bytes,
    *,
    crop_fraction: float,
    padding_fraction: float,
    background_rgb: tuple[int, int, int],
) -> tuple[bytes, dict[str, Any]]:
    if not 0.0 <= crop_fraction <= 0.20 or not 0.0 <= padding_fraction <= 0.20:
        raise ValueError("crop_or_padding_fraction_out_of_range")
    image = _decode_rgba(png)
    width, height = image.size
    crop_x = round(width * crop_fraction)
    crop_y = round(height * crop_fraction)
    if width - 2 * crop_x < 8 or height - 2 * crop_y < 8:
        raise ValueError("crop_removes_observation")
    cropped = image.crop((crop_x, crop_y, width - crop_x, height - crop_y))
    pad_x = round(cropped.width * padding_fraction)
    pad_y = round(cropped.height * padding_fraction)
    output = Image.new(
        "RGBA",
        (cropped.width + 2 * pad_x, cropped.height + 2 * pad_y),
        (*background_rgb, 255),
    )
    output.paste(cropped, (pad_x, pad_y))
    encoded = _encode_png(output)
    transform = {
        "sourceSize": [width, height],
        "outputSize": [output.width, output.height],
        "cropBoxPixels": [crop_x, crop_y, width - crop_x, height - crop_y],
        "paddingPixels": [pad_x, pad_y],
        "outputToOriginalAffine3x3": [
            1.0,
            0.0,
            float(crop_x - pad_x),
            0.0,
            1.0,
            float(crop_y - pad_y),
            0.0,
            0.0,
            1.0,
        ],
        "pixelsChanged": encoded != png,
        "dimensionsChanged": output.size != image.size,
    }
    return encoded, transform


def _extract_view(png: bytes, role: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
    image = _decode_rgba(png)
    width, height = image.size
    if width < 16 or height < 16:
        raise ObservationRejected(f"{role}_image_too_small")
    pixels = list(image.getdata())
    background = _background_rgb(pixels, width, height)
    threshold = int(observation_contract()["backgroundDistanceThreshold"])
    raw_foreground = {
        index
        for index, pixel in enumerate(pixels)
        if _rgb_distance(pixel[:3], background) >= threshold
    }
    uncertain = {
        index
        for index, pixel in enumerate(pixels)
        if 10 <= _rgb_distance(pixel[:3], background) < threshold
    }
    foreground = _largest_component(raw_foreground, width, height)
    if len(foreground) < max(32, round(width * height * 0.01)):
        raise ObservationRejected(f"{role}_foreground_not_found")
    xs = [index % width for index in foreground]
    ys = [index // width for index in foreground]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    spans = _row_spans(foreground, width, min_y, max_y)
    gap_width, gap_depth = _central_gap(foreground, width, min_x, max_x, min_y, max_y)
    colours = [pixels[index][:3] for index in foreground]
    mean_rgb = [
        sum(pixel[channel] for pixel in colours) / (255.0 * len(colours)) for channel in range(3)
    ]
    centre_x = sum(xs) / (len(xs) * max(1, width - 1))
    centre_y = sum(ys) / (len(ys) * max(1, height - 1))
    features = {
        "valid": 1.0,
        "bbox_width": (max_x - min_x + 1) / width,
        "bbox_height": (max_y - min_y + 1) / height,
        "foreground_fraction": len(foreground) / (width * height),
        "centroid_x": centre_x,
        "centroid_y": centre_y,
        **{f"span_q{quantile}": spans[quantile] for quantile in (10, 20, 35, 50, 70, 90)},
        "central_gap_width": gap_width,
        "central_gap_depth": gap_depth,
        "edge_asymmetry": abs((centre_x - min_x / width) - (max_x / width - centre_x)),
        "mean_red": mean_rgb[0],
        "mean_green": mean_rgb[1],
        "mean_blue": mean_rgb[2],
        "background_contrast": sum(
            abs(mean_rgb[channel] - background[channel] / 255.0) for channel in range(3)
        )
        / 3.0,
        "uncertain_fraction": len(uncertain) / (width * height),
    }
    source_hash = sha256_bytes(png)
    transform = metadata.get("observationToOriginalTransform") or {
        "sourceSize": [width, height],
        "outputSize": [width, height],
        "cropBoxPixels": [0, 0, width, height],
        "paddingPixels": [0, 0],
        "outputToOriginalAffine3x3": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        "pixelsChanged": False,
        "dimensionsChanged": False,
    }
    return {
        "role": role,
        "status": "observed",
        "decodedSize": [width, height],
        "orientation": "top_left",
        "colourSpace": "srgb8",
        "alphaFullyOpaque": all(pixel[3] == 255 for pixel in pixels),
        "backgroundRgb": list(background),
        "foregroundPixelCount": len(foreground),
        "uncertainPixelCount": len(uncertain),
        "foregroundMaskDigest": _index_digest(foreground),
        "occlusionConfidenceMapDigest": _index_digest(uncertain),
        "bboxPixels": [min_x, min_y, max_x + 1, max_y + 1],
        "camera": dict(_mapping(metadata.get("camera"))),
        "observationToOriginalTransform": transform,
        "sourceSha256": source_hash,
        "privacySafeIdentity": sha256_bytes(
            b"closy.d0_v4.public_synthetic.source\0" + source_hash.encode("ascii")
        ),
        "features": {name: round(float(features[name]), 12) for name in ROLE_FEATURES},
    }


def _missing_view(role: str) -> dict[str, Any]:
    return {
        "role": role,
        "status": "missing",
        "missingReason": "source_role_not_supplied",
        "features": {name: 0.0 for name in ROLE_FEATURES},
    }


def _decode_rgba(png: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(png)) as image:
            image.load()
            if image.format != "PNG":
                raise ObservationRejected("source_not_png")
            return cast(Image.Image, image.convert("RGBA").copy())
    except ObservationRejected:
        raise
    except Exception as exc:
        raise ObservationRejected("corrupt_png") from exc


def _encode_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _background_rgb(
    pixels: list[tuple[int, int, int, int]], width: int, height: int
) -> tuple[int, int, int]:
    border_indices = set(range(width))
    border_indices.update(range((height - 1) * width, height * width))
    border_indices.update(row * width for row in range(height))
    border_indices.update(row * width + width - 1 for row in range(height))
    quantized = [
        (
            (pixels[index][0] // 8) * 8,
            (pixels[index][1] // 8) * 8,
            (pixels[index][2] // 8) * 8,
        )
        for index in border_indices
    ]
    bucket = Counter(quantized).most_common(1)[0][0]
    candidates: list[tuple[int, int, int]] = [
        (pixels[index][0], pixels[index][1], pixels[index][2])
        for index in border_indices
        if all(abs(pixels[index][channel] - bucket[channel]) < 8 for channel in range(3))
    ]
    if not candidates:
        candidates = [bucket]
    return (
        round(sum(pixel[0] for pixel in candidates) / len(candidates)),
        round(sum(pixel[1] for pixel in candidates) / len(candidates)),
        round(sum(pixel[2] for pixel in candidates) / len(candidates)),
    )


def _largest_component(indices: set[int], width: int, height: int) -> set[int]:
    remaining = set(indices)
    largest: set[int] = set()
    while remaining:
        start = remaining.pop()
        component = {start}
        queue: deque[int] = deque([start])
        while queue:
            index = queue.popleft()
            x, y = index % width, index // width
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                neighbour = ny * width + nx
                if 0 <= nx < width and 0 <= ny < height and neighbour in remaining:
                    remaining.remove(neighbour)
                    component.add(neighbour)
                    queue.append(neighbour)
        if len(component) > len(largest):
            largest = component
    return largest


def _row_spans(foreground: set[int], width: int, min_y: int, max_y: int) -> dict[int, float]:
    result: dict[int, float] = {}
    for quantile in (10, 20, 35, 50, 70, 90):
        y = round(min_y + (max_y - min_y) * quantile / 100.0)
        xs = [index % width for index in foreground if index // width == y]
        result[quantile] = (max(xs) - min(xs) + 1) / width if xs else 0.0
    return result


def _central_gap(
    foreground: set[int], width: int, min_x: int, max_x: int, min_y: int, max_y: int
) -> tuple[float, float]:
    centre = (min_x + max_x) // 2
    best_width = 0
    deepest = min_y
    search_bottom = min(max_y, min_y + max(4, round((max_y - min_y) * 0.28)))
    for y in range(min_y, search_bottom + 1):
        left = centre
        while left >= min_x and y * width + left not in foreground:
            left -= 1
        right = centre
        while right <= max_x and y * width + right not in foreground:
            right += 1
        gap = max(0, right - left - 1)
        if gap > 0:
            best_width = max(best_width, gap)
            deepest = y
    return best_width / width, (deepest - min_y + 1) / max(1, max_y - min_y + 1)


def _rgb_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return max(abs(left[channel] - right[channel]) for channel in range(3))


def _index_digest(indices: set[int]) -> str:
    payload = b"".join(index.to_bytes(4, "big") for index in sorted(indices))
    return sha256_bytes(payload)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _digest(value: Mapping[str, Any], field: str) -> str:
    payload = deepcopy(dict(value))
    payload[field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
