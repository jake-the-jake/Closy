from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

from closy_forge.package_io.hashing import package_digest, sha256_file
from closy_forge.package_io.paths import assert_safe_child, posix_rel, validate_package_relpath

EXCLUDED_FROM_CANONICAL_INVENTORY = {
    "manifest.json",
    "reports/package_validation.json",
    "reports/summary.json",
    "reports/summary.md",
}


MEDIA_TYPES = {
    ".json": "application/json",
    ".glb": "model/gltf-binary",
    ".svg": "image/svg+xml",
    ".bin": "application/octet-stream",
    ".md": "text/markdown",
}


def staging_dir_for(target: Path) -> Path:
    return target.with_name(f".{target.name}.staging.closygarment")


def prepare_staging(target: Path) -> Path:
    if target.suffix != ".closygarment":
        raise ValueError("output path must end with .closygarment")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = staging_dir_for(target)
    _safe_remove_staging(staging)
    staging.mkdir(parents=True)
    return staging


def publish_staging(staging: Path, target: Path, *, force: bool) -> None:
    if target.exists():
        if not force:
            raise FileExistsError(
                f"{target} already exists; pass --force to replace only this package"
            )
        assert_safe_child(target.parent, target)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    staging.replace(target)


def cleanup_staging(staging: Path) -> None:
    _safe_remove_staging(staging)


def collect_inventory(package_dir: Path, *, exclude: Iterable[str] = ()) -> list[dict[str, object]]:
    exclude_set = set(exclude)
    entries: list[dict[str, object]] = []
    for path in sorted(package_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.is_symlink():
            continue
        rel = posix_rel(path, package_dir)
        if rel in exclude_set:
            continue
        validate_package_relpath(rel)
        entries.append(
            {
                "path": rel,
                "role": _role_for_path(rel),
                "canonical": _is_canonical(rel),
                "required": True,
                "mediaType": MEDIA_TYPES.get(path.suffix, "application/octet-stream"),
                "byteSize": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return entries


def canonical_package_digest(inventory: list[dict[str, object]]) -> str:
    return package_digest(inventory)


def _safe_remove_staging(staging: Path) -> None:
    if not staging.exists():
        return
    if not staging.name.startswith(".") or not staging.name.endswith(".staging.closygarment"):
        raise ValueError(f"refusing to remove non-Forge staging path: {staging}")
    assert_safe_child(staging.parent, staging)
    shutil.rmtree(staging)


def _role_for_path(rel: str) -> str:
    if rel.startswith("avatar/"):
        return "avatar_contract_or_fixture"
    if rel.startswith("semantic/"):
        return "semantic_contract"
    if rel.startswith("pattern/"):
        return "pattern_contract"
    if rel.startswith("simulation/"):
        return "simulation_contract_or_asset"
    if rel.startswith("render/"):
        return "render_contract_or_asset"
    if rel.startswith("binding/"):
        return "sim_to_render_binding"
    if rel.startswith("reports/"):
        return "quality_or_validation_report"
    if rel == "provenance.json":
        return "provenance"
    return "package_file"


def _is_canonical(rel: str) -> bool:
    return (
        rel.startswith(("avatar/", "semantic/", "pattern/", "simulation/", "render/", "binding/"))
        or rel == "provenance.json"
    )
