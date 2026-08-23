from __future__ import annotations

from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_io.paths import posix_rel


def compare_package_trees(left: Path, right: Path) -> dict[str, Any]:
    left_files = _file_hashes(left)
    right_files = _file_hashes(right)
    left_paths = set(left_files)
    right_paths = set(right_files)
    missing_from_left = sorted(right_paths - left_paths)
    missing_from_right = sorted(left_paths - right_paths)
    changed = [
        {
            "path": path,
            "leftSha256": left_files[path],
            "rightSha256": right_files[path],
            "firstDifference": _first_difference(left / path, right / path),
        }
        for path in sorted(left_paths & right_paths)
        if left_files[path] != right_files[path]
    ]
    return {
        "status": "identical"
        if not missing_from_left and not missing_from_right and not changed
        else "different",
        "left": str(left),
        "right": str(right),
        "leftFileCount": len(left_files),
        "rightFileCount": len(right_files),
        "missingFromLeft": missing_from_left,
        "missingFromRight": missing_from_right,
        "changed": changed,
    }


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        posix_rel(path, root): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _first_difference(left: Path, right: Path) -> dict[str, Any]:
    left_bytes = left.read_bytes()
    right_bytes = right.read_bytes()
    for index, (left_byte, right_byte) in enumerate(zip(left_bytes, right_bytes, strict=False)):
        if left_byte != right_byte:
            return {
                "offset": index,
                "leftByte": left_byte,
                "rightByte": right_byte,
                "leftContextHex": _context_hex(left_bytes, index),
                "rightContextHex": _context_hex(right_bytes, index),
            }
    return {
        "offset": min(len(left_bytes), len(right_bytes)),
        "leftByte": None,
        "rightByte": None,
        "leftSize": len(left_bytes),
        "rightSize": len(right_bytes),
    }


def _context_hex(data: bytes, index: int, *, radius: int = 12) -> str:
    start = max(0, index - radius)
    end = min(len(data), index + radius + 1)
    return data[start:end].hex()
