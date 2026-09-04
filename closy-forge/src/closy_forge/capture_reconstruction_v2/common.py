from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()


def canonical_digest(value: Any, digest_field: str | None = None) -> str:
    unsigned = dict(value) if isinstance(value, dict) else value
    if digest_field is not None and isinstance(unsigned, dict):
        unsigned = dict(unsigned)
        unsigned.pop(digest_field, None)
    return hashlib.sha256(canonical_bytes(unsigned)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("json_mapping_required")
    return value


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def write_json(path: Path, value: Any) -> None:
    atomic_write(path, canonical_bytes(value))


def rounded(value: float, digits: int = 8) -> float:
    return round(float(value), digits)


def digest_file_set(files: Mapping[str, bytes]) -> str:
    return canonical_digest(
        [
            {"path": path, "byteLength": len(payload), "sha256": sha256_bytes(payload)}
            for path, payload in sorted(files.items())
        ]
    )
