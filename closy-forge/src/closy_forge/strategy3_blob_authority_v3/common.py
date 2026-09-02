from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()


def canonical_digest(value: Any, digest_field: str) -> str:
    document = dict(mapping(value))
    document[digest_field] = ""
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("strategy3_v3_mapping_required")
    return dict(value)


def records(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("strategy3_v3_records_required")
    return [mapping(row) for row in value]


def load_json(path: Path) -> dict[str, Any]:
    return mapping(json.loads(path.read_text(encoding="utf-8")))


def write_json(path: Path, value: Any, *, freeze: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True).encode() + b"\n"
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    if freeze:
        path.chmod(0o444)
