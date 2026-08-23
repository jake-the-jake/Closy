from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def canonical_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def canonical_text_bytes(text: str, *, final_newline: bool = True) -> bytes:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if final_newline:
        normalized = normalized.rstrip("\n") + "\n"
    return normalized.encode("utf-8")


def write_canonical_text(path: Path, text: str, *, final_newline: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_text_bytes(text, final_newline=final_newline))


def write_canonical_json(path: Path, data: Any) -> None:
    write_canonical_text(path, canonical_dumps(data))


def read_json(path: Path) -> Any:
    return json.loads(path.read_bytes().decode("utf-8"))
