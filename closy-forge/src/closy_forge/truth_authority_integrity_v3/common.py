from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes


def load_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"mapping_required:{path.name}")
    return value


def canonical_digest(document: Mapping[str, Any], field: str) -> str:
    payload = deepcopy(dict(document))
    payload[field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def records(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [mapping(item) for item in value]
