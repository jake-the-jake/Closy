from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file

IMPLEMENTATION_FREEZE_PATH = Path(
    "fixtures/d0_texture_rerender_correction_v3/implementation_freeze.json"
)


def load_implementation_freeze(root: Path) -> dict[str, Any]:
    path = root / IMPLEMENTATION_FREEZE_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("d0_appearance_implementation_freeze_invalid")
    if payload.get("freezeId") != "closy.d0_texture_rerender.implementation_freeze.v3":
        raise ValueError("d0_appearance_implementation_freeze_id_invalid")
    files = payload.get("implementationFiles")
    if not isinstance(files, list) or not files:
        raise ValueError("d0_appearance_implementation_files_missing")
    for record in files:
        if not isinstance(record, Mapping):
            raise ValueError("d0_appearance_implementation_file_invalid")
        relative = str(record.get("path", ""))
        if sha256_file(root / relative) != record.get("sha256"):
            raise ValueError(f"d0_appearance_implementation_hash_mismatch:{relative}")
    if payload.get("evaluatorOnlyMounted") is not False:
        raise ValueError("d0_appearance_evaluator_mounted_at_implementation_freeze")
    return payload
