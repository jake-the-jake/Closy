from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file

BENCHMARK_VERSION = "closy.d0_disjoint_tshirt_benchmark.v1"
FIXTURE_ROOT = Path("fixtures/d0_disjoint_tshirt_benchmark_v1")
PROTOCOL_PATH = FIXTURE_ROOT / "protocol_lock.json"
DEVELOPMENT_LOCK_PATH = FIXTURE_ROOT / "development_lock.json"

OBSERVABLE_PARAMETERS: tuple[str, ...] = (
    "garment_body_length",
    "half_chest_width",
    "body_ease",
    "shoulder_width",
    "shoulder_slope",
    "neckline_width",
    "front_neckline_depth",
    "back_neckline_depth",
    "armhole_depth",
    "sleeve_length",
    "sleeve_opening_width",
)

FIXED_PARAMETERS: dict[str, float] = {
    "sleeve_cap_height": 0.105,
    "hem_allowance": 0.025,
    "neckband_width": 0.035,
    "neckband_length_ease_ratio": 0.92,
    "target_panel_edge_length": 0.045,
}

PARAMETER_RANGES: dict[str, tuple[float, float]] = {
    "garment_body_length": (0.54, 0.80),
    "half_chest_width": (0.235, 0.365),
    "body_ease": (0.012, 0.105),
    "shoulder_width": (0.55, 0.82),
    "shoulder_slope": (0.018, 0.075),
    "neckline_width": (0.135, 0.265),
    "front_neckline_depth": (0.045, 0.145),
    "back_neckline_depth": (0.018, 0.072),
    "armhole_depth": (0.155, 0.285),
    "sleeve_length": (0.155, 0.365),
    "sleeve_opening_width": (0.13, 0.265),
}


def load_protocol_lock(root: Path) -> dict[str, Any]:
    payload = _mapping(json.loads((root / PROTOCOL_PATH).read_text(encoding="utf-8")))
    if payload.get("benchmarkVersion") != BENCHMARK_VERSION:
        raise ValueError("d0_disjoint_protocol_version_invalid")
    if payload.get("evaluatorIdentityCount") != 16 or payload.get("developmentIdentityCount") != 8:
        raise ValueError("d0_disjoint_corpus_size_invalid")
    if payload.get("evaluatorIdentitiesRealized") is not False:
        raise ValueError("d0_disjoint_protocol_contains_evaluator_identity")
    return payload


def validate_frozen_implementation(root: Path, lock: Mapping[str, Any]) -> None:
    files = lock.get("implementationFiles")
    if not isinstance(files, list) or not files:
        raise ValueError("d0_disjoint_implementation_inventory_missing")
    for item in files:
        record = _mapping(item)
        relative = str(record.get("path", ""))
        if sha256_file(root / relative) != record.get("sha256"):
            raise ValueError(f"d0_disjoint_implementation_hash_mismatch:{relative}")


def normalized_parameter_vector(parameters: Mapping[str, Any]) -> tuple[float, ...]:
    return tuple(
        (float(parameters[name]) - PARAMETER_RANGES[name][0])
        / (PARAMETER_RANGES[name][1] - PARAMETER_RANGES[name][0])
        for name in OBSERVABLE_PARAMETERS
    )


def normalized_distance(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    a = normalized_parameter_vector(left)
    b = normalized_parameter_vector(right)
    squared = math.fsum((x - y) ** 2 for x, y in zip(a, b, strict=True))
    return math.sqrt(squared / len(a))


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("d0_disjoint_mapping_required")
    return dict(value)
