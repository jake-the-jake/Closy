from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from closy_forge.package_io.hashing import package_digest, sha256_file
from closy_forge.package_io.managed_output import (
    MARKER_NAME,
    cleanup_managed_staging,
    create_managed_staging,
    publish_managed_staging,
)
from closy_forge.package_io.paths import posix_rel, validate_package_relpath

EXCLUDED_FROM_CANONICAL_INVENTORY = {
    "manifest.json",
    "reports/package_validation.json",
    "reports/summary.json",
    "reports/summary.md",
    "zeroone/static-d0/",
    MARKER_NAME,
}


MEDIA_TYPES = {
    ".json": "application/json",
    ".glb": "model/gltf-binary",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".bin": "application/octet-stream",
    ".md": "text/markdown",
}


def staging_dir_for(target: Path) -> Path:
    return target.with_name(f".{target.name}.canonical-package.staging{target.suffix}")


def prepare_staging(target: Path) -> Path:
    if target.suffix != ".closygarment":
        raise ValueError("output path must end with .closygarment")
    return create_managed_staging(
        target,
        allowed_root=target.parent,
        purpose="canonical-package",
    )


def publish_staging(staging: Path, target: Path, *, force: bool) -> None:
    publish_managed_staging(
        staging,
        target,
        allowed_root=target.parent,
        purpose="canonical-package",
        force=force,
    )


def cleanup_staging(staging: Path) -> None:
    cleanup_managed_staging(
        staging,
        allowed_root=staging.parent,
        purpose="canonical-package",
    )


def collect_inventory(package_dir: Path, *, exclude: Iterable[str] = ()) -> list[dict[str, object]]:
    exclude_set = set(exclude)
    exclude_prefixes = tuple(value for value in exclude_set if value.endswith("/"))
    entries: list[dict[str, object]] = []
    for path in sorted(package_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.is_symlink():
            continue
        rel = posix_rel(path, package_dir)
        if rel in exclude_set or rel.startswith(exclude_prefixes):
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


def _role_for_path(rel: str) -> str:
    if rel.startswith("source/"):
        return "source_capture_contract"
    if rel.startswith("fitting/"):
        return "fit_report"
    if rel.startswith("textures/"):
        return "texture_identity_contract"
    if rel.startswith("proposals/"):
        return "visual_geometry_proposal_contract"
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
        rel.startswith(
            ("source/", "avatar/", "semantic/", "pattern/", "simulation/", "render/", "binding/")
        )
        or rel.startswith("fitting/")
        or rel.startswith("textures/")
        or rel.startswith("proposals/")
        or rel == "provenance.json"
    )
