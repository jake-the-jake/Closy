from __future__ import annotations

from pathlib import Path


def posix_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def validate_package_relpath(relpath: str) -> None:
    if relpath.startswith("/") or "\\" in relpath:
        raise ValueError(f"unsafe package path {relpath!r}")
    parts = Path(relpath).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe package path {relpath!r}")


def assert_safe_child(root: Path, child: Path) -> None:
    root_resolved = root.resolve()
    child_resolved = child.resolve(strict=False)
    if root_resolved != child_resolved and root_resolved not in child_resolved.parents:
        raise ValueError(f"path escapes target root: {child}")
