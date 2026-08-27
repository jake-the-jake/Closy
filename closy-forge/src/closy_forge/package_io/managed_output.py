from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

MARKER_NAME = ".closy-forge-owned.json"
MARKER_VERSION = "closy.forge_owned_output.v1"
_PURPOSE_RE = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")


class ManagedOutputError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def create_managed_staging(
    target: Path,
    *,
    allowed_root: Path,
    purpose: str,
) -> Path:
    root, resolved_target = validate_output_target(
        target, allowed_root=allowed_root, purpose=purpose
    )
    root.mkdir(parents=True, exist_ok=True)
    # Package validators inspect the staging directory before publication, so
    # preserve the target suffix while still using a private sibling name.
    staging = root / (f".{resolved_target.name}.{purpose}.staging{resolved_target.suffix}")
    if staging.exists() or staging.is_symlink():
        _validate_managed_directory(staging, purpose=purpose, kind="staging")
        _remove_validated_tree(staging)
    staging.mkdir()
    _write_marker(staging, purpose=purpose, kind="staging", target_name=resolved_target.name)
    return staging


def publish_managed_staging(
    staging: Path,
    target: Path,
    *,
    allowed_root: Path,
    purpose: str,
    force: bool,
) -> None:
    root, resolved_target = validate_output_target(
        target, allowed_root=allowed_root, purpose=purpose
    )
    resolved_staging = staging.absolute()
    if resolved_staging.parent != root or resolved_staging == resolved_target:
        raise ManagedOutputError("staging_outside_allowed_root")
    staging_marker = _validate_managed_directory(resolved_staging, purpose=purpose, kind="staging")
    if staging_marker.get("targetName") != resolved_target.name:
        raise ManagedOutputError("managed_output_target_name_mismatch")

    backup = root / f".{resolved_target.name}.{purpose}.last-good"
    if backup.exists() or backup.is_symlink():
        _recover_or_reject_stale_backup(backup, resolved_target, purpose=purpose, force=force)

    had_target = resolved_target.exists() or resolved_target.is_symlink()
    if had_target:
        if not force:
            raise FileExistsError(f"managed output already exists: {resolved_target.name}")
        _validate_managed_directory(resolved_target, purpose=purpose, kind="published")
        os.replace(resolved_target, backup)
        _rewrite_marker_kind(backup, purpose=purpose, kind="backup")

    try:
        os.replace(resolved_staging, resolved_target)
        _rewrite_marker_kind(resolved_target, purpose=purpose, kind="published")
    except BaseException:
        if had_target and backup.exists() and not resolved_target.exists():
            _rewrite_marker_kind(backup, purpose=purpose, kind="published")
            os.replace(backup, resolved_target)
        raise

    if backup.exists():
        _validate_managed_directory(backup, purpose=purpose, kind="backup")
        _remove_validated_tree(backup)


def cleanup_managed_staging(
    staging: Path,
    *,
    allowed_root: Path,
    purpose: str,
) -> None:
    root = _resolve_allowed_root(allowed_root)
    candidate = staging.absolute()
    if candidate.parent != root:
        raise ManagedOutputError("staging_outside_allowed_root")
    if not candidate.exists() and not candidate.is_symlink():
        return
    _validate_managed_directory(candidate, purpose=purpose, kind="staging")
    _remove_validated_tree(candidate)


def validate_output_target(
    target: Path,
    *,
    allowed_root: Path,
    purpose: str,
) -> tuple[Path, Path]:
    if not _PURPOSE_RE.fullmatch(purpose):
        raise ManagedOutputError("invalid_output_purpose")
    root = _resolve_allowed_root(allowed_root)
    candidate = target.absolute()
    if candidate.parent != root:
        raise ManagedOutputError("output_must_be_direct_child_of_allowed_root")
    if candidate.name in {"", ".", ".."}:
        raise ManagedOutputError("invalid_output_name")
    if candidate.is_symlink():
        raise ManagedOutputError("output_symlink_rejected")
    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate.parent != root:
        raise ManagedOutputError("output_symlink_escape_rejected")
    _reject_protected_target(resolved_candidate)
    return root, resolved_candidate


def read_managed_marker(path: Path) -> dict[str, Any]:
    marker = path / MARKER_NAME
    if marker.is_symlink() or not marker.is_file():
        raise ManagedOutputError("managed_output_marker_missing")
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManagedOutputError("managed_output_marker_invalid") from error
    if not isinstance(value, dict):
        raise ManagedOutputError("managed_output_marker_invalid")
    return value


def _resolve_allowed_root(path: Path) -> Path:
    lexical = path.absolute()
    if lexical.is_symlink():
        raise ManagedOutputError("allowed_root_symlink_rejected")
    lexical.mkdir(parents=True, exist_ok=True)
    resolved = lexical.resolve()
    if not resolved.is_dir():
        raise ManagedOutputError("allowed_root_not_directory")
    _reject_protected_target(resolved)
    return resolved


def _reject_protected_target(path: Path) -> None:
    anchor = Path(path.anchor)
    home = Path.home().resolve()
    source_file = Path(__file__).resolve()
    forge_root = source_file.parents[3]
    repository_root = source_file.parents[4]
    protected = (anchor, home, forge_root, repository_root)
    for item in protected:
        if path == item or _is_relative_to(item, path):
            raise ManagedOutputError("protected_output_target_rejected")


def _validate_managed_directory(path: Path, *, purpose: str, kind: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_dir():
        raise ManagedOutputError("managed_output_not_real_directory")
    marker = read_managed_marker(path)
    if marker.get("schemaVersion") != 1 or marker.get("markerVersion") != MARKER_VERSION:
        raise ManagedOutputError("managed_output_marker_version_mismatch")
    if marker.get("owner") != "closy-forge":
        raise ManagedOutputError("managed_output_owner_mismatch")
    if marker.get("purpose") != purpose:
        raise ManagedOutputError("managed_output_purpose_mismatch")
    if marker.get("kind") != kind:
        raise ManagedOutputError("managed_output_kind_mismatch")
    if kind == "staging" and marker.get("targetName") is None:
        raise ManagedOutputError("managed_output_target_name_missing")
    for child in path.rglob("*"):
        if child.is_symlink():
            raise ManagedOutputError("managed_output_nested_symlink_rejected")
    return marker


def _write_marker(path: Path, *, purpose: str, kind: str, target_name: str) -> None:
    payload = {
        "kind": kind,
        "markerVersion": MARKER_VERSION,
        "owner": "closy-forge",
        "purpose": purpose,
        "schemaVersion": 1,
    }
    if kind == "staging":
        payload["targetName"] = target_name
    (path / MARKER_NAME).write_text(
        json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _rewrite_marker_kind(path: Path, *, purpose: str, kind: str) -> None:
    marker = read_managed_marker(path)
    if marker.get("markerVersion") != MARKER_VERSION or marker.get("purpose") != purpose:
        raise ManagedOutputError("managed_output_marker_mismatch")
    _write_marker(
        path,
        purpose=purpose,
        kind=kind,
        target_name=str(marker.get("targetName", path.name)),
    )


def _recover_or_reject_stale_backup(
    backup: Path, target: Path, *, purpose: str, force: bool
) -> None:
    _validate_managed_directory(backup, purpose=purpose, kind="backup")
    if target.exists() or target.is_symlink():
        if not force:
            raise ManagedOutputError("stale_backup_requires_force")
        _validate_managed_directory(target, purpose=purpose, kind="published")
        _remove_validated_tree(backup)
        return
    _rewrite_marker_kind(backup, purpose=purpose, kind="published")
    os.replace(backup, target)


def _remove_validated_tree(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ManagedOutputError("managed_output_not_real_directory")
    shutil.rmtree(path)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
