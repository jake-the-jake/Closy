from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from .common import canonical_digest, mapping

IDENTITY_FIELDS = (
    "avatarIdentity",
    "garmentIdentity",
    "garmentFamily",
    "appearanceIdentity",
    "captureSession",
    "rendererCameraFamily",
    "physicalMaterialPreset",
)
ALIASES = {"t-shirt": "tshirt", "tee": "tshirt", "millimetre": "mm", "centimetre": "cm"}
UNIT_SCALE = {"m": 1.0, "cm": 0.01, "mm": 0.001}


def canonical_identity_key(record: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(_normalize_token(record.get(field)) for field in IDENTITY_FIELDS)


def audit_identity_splits(
    records: Sequence[Mapping[str, Any]],
    *,
    numeric_fields: Sequence[str],
    normalized_distance_threshold: float,
    raster_hamming_threshold: int,
) -> dict[str, Any]:
    canonical = [canonical_identity_key(row) for row in records]
    exact: list[dict[str, Any]] = []
    near: list[dict[str, Any]] = []
    perceptual: list[dict[str, Any]] = []
    mesh: list[dict[str, Any]] = []
    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            if records[left].get("split") == records[right].get("split"):
                continue
            pair = {"left": left, "right": right}
            if canonical[left] == canonical[right]:
                exact.append(pair)
            distance = _normalized_distance(records[left], records[right], numeric_fields)
            if distance <= normalized_distance_threshold:
                near.append({**pair, "distance": distance})
            left_raster = records[left].get("rasterPath")
            right_raster = records[right].get("rasterPath")
            if isinstance(left_raster, str) and isinstance(right_raster, str):
                hamming = _dhash_hamming(Path(left_raster), Path(right_raster))
                if hamming <= raster_hamming_threshold:
                    perceptual.append({**pair, "dhashHamming": hamming})
            similarity = _mesh_similarity(
                records[left].get("meshSignature"), records[right].get("meshSignature")
            )
            if similarity is not None and similarity >= 0.999:
                mesh.append({**pair, "similarity": similarity})
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "inventoryVersion": "closy.identity_disjoint_inventory.v4",
        "identityFields": list(IDENTITY_FIELDS),
        "normalizedUnits": dict(sorted(UNIT_SCALE.items())),
        "normalizedAliases": dict(sorted(ALIASES.items())),
        "recordCount": len(records),
        "splitMembership": [str(row.get("split", "")) for row in records],
        "exactCrossSplitCollisions": exact,
        "normalizedNearestCollisions": near,
        "perceptualCrossSplitCollisions": perceptual,
        "meshTopologyCrossSplitCollisions": mesh,
        "pr58PublicRowsPolicy": "append_only_forensic_description_only",
        "pr58ForbiddenUses": [
            "training",
            "feature_design",
            "model_selection",
            "threshold_setting",
            "regression_goldens",
            "successor_split_construction",
        ],
        "disjoint": not exact and not near and not perceptual and not mesh,
        "inventoryDigest": "",
    }
    result["inventoryDigest"] = canonical_digest(result, "inventoryDigest")
    return result


def normalize_measurement(value: Mapping[str, Any]) -> float:
    number = float(value["value"])
    unit = ALIASES.get(_normalize_token(value.get("unit")), _normalize_token(value.get("unit")))
    if unit not in UNIT_SCALE or not math.isfinite(number):
        raise ValueError("identity_measurement_invalid")
    return number * UNIT_SCALE[unit]


def _normalize_token(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return ALIASES.get(text, text)


def _normalized_distance(
    left: Mapping[str, Any], right: Mapping[str, Any], fields: Sequence[str]
) -> float:
    if not fields:
        return math.inf
    deltas: list[float] = []
    for field in fields:
        left_value = mapping(left.get("parameters")).get(field)
        right_value = mapping(right.get("parameters")).get(field)
        if not isinstance(left_value, Mapping) or not isinstance(right_value, Mapping):
            return math.inf
        deltas.append(normalize_measurement(left_value) - normalize_measurement(right_value))
    return math.sqrt(sum(delta * delta for delta in deltas))


def _dhash_hamming(left: Path, right: Path) -> int:
    return (_dhash(left) ^ _dhash(right)).bit_count()


def _dhash(path: Path) -> int:
    with Image.open(path) as image:
        pixels = list(image.convert("L").resize((9, 8)).getdata())
    result = 0
    for y in range(8):
        for x in range(8):
            result = (result << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return result


def _mesh_similarity(left: object, right: object) -> float | None:
    if not isinstance(left, Sequence) or not isinstance(right, Sequence) or not left or not right:
        return None
    a = [float(value) for value in left]
    b = [float(value) for value in right]
    if len(a) != len(b):
        return 0.0
    denominator = max(sum(abs(value) for value in a), sum(abs(value) for value in b), 1e-12)
    return max(0.0, 1.0 - sum(abs(x - y) for x, y in zip(a, b, strict=True)) / denominator)
