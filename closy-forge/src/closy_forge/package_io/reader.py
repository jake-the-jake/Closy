from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical_json import read_json


def read_package_manifest(package_dir: Path) -> dict[str, Any]:
    manifest = read_json(package_dir / "manifest.json")
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must contain an object")
    return manifest
