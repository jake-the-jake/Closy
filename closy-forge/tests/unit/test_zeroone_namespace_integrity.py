from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.managed_output import create_managed_staging
from closy_forge.zeroone import namespace as namespace_module
from closy_forge.zeroone.namespace import (
    MANIFEST_NAME,
    PAYLOAD_SPECS,
    NamespaceIntegrityError,
    validate_namespace_manifest,
    write_namespace_manifest,
)

PURPOSE = "zeroone-static-d0"


def _valid_staging(tmp_path: Path) -> Path:
    allowed = tmp_path / "zeroone"
    staging = create_managed_staging(allowed / "static-d0", allowed_root=allowed, purpose=PURPOSE)
    for spec in PAYLOAD_SPECS:
        path = staging / spec.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"{}\n" if spec.media_type == "application/json" else spec.role.encode())
    write_namespace_manifest(staging)
    assert validate_namespace_manifest(staging)["files"]
    return staging


def test_static_namespace_carries_dynamic_identity_document(tmp_path: Path) -> None:
    staging = _valid_staging(tmp_path)
    manifest = validate_namespace_manifest(staging)

    assert (staging / "derivative" / "derivative.json").is_file()
    assert any(
        row["path"] == "derivative/derivative.json" and row["role"] == "derivative_identity"
        for row in manifest["files"]
    )


@pytest.mark.parametrize(
    "relative",
    ("unexpected.json", "derivative/tool.exe", "derivative/source.jpg", "derivative/raw.log"),
)
def test_namespace_rejects_every_undeclared_file(tmp_path: Path, relative: str) -> None:
    staging = _valid_staging(tmp_path)
    extra = staging / relative
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(b"undeclared")

    with pytest.raises(NamespaceIntegrityError, match="exact_inventory_mismatch"):
        validate_namespace_manifest(staging)


def test_namespace_rejects_missing_and_mutated_files(tmp_path: Path) -> None:
    staging = _valid_staging(tmp_path)
    missing = staging / PAYLOAD_SPECS[-1].path
    missing.unlink()
    with pytest.raises(NamespaceIntegrityError, match="file_missing"):
        validate_namespace_manifest(staging)

    missing.write_bytes(b"changed")
    with pytest.raises(NamespaceIntegrityError, match="file_mismatch"):
        validate_namespace_manifest(staging)


def test_namespace_rejects_wrong_digest_role_and_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = _valid_staging(tmp_path)
    manifest_path = staging / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["sha256"] = "0" * 64
    write_canonical_json(manifest_path, manifest)
    with pytest.raises(NamespaceIntegrityError, match="file_mismatch"):
        validate_namespace_manifest(staging)

    write_namespace_manifest(staging)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["role"] = "forbidden_authority"
    write_canonical_json(manifest_path, manifest)
    with pytest.raises(NamespaceIntegrityError, match="role_invalid"):
        validate_namespace_manifest(staging)

    write_namespace_manifest(staging)
    monkeypatch.setattr(namespace_module, "MAX_FILE_COUNT", 1)
    with pytest.raises(NamespaceIntegrityError, match="file_count_invalid"):
        validate_namespace_manifest(staging)


def test_namespace_rejects_oversized_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = _valid_staging(tmp_path)
    monkeypatch.setattr(namespace_module, "MAX_FILE_BYTES", 1)

    with pytest.raises(NamespaceIntegrityError, match="file_metadata_invalid"):
        validate_namespace_manifest(staging)


def test_namespace_rejects_traversal_and_case_aliases(tmp_path: Path) -> None:
    staging = _valid_staging(tmp_path)
    manifest_path = staging / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    alias = dict(manifest["files"][0])
    alias["path"] = alias["path"].upper()
    manifest["files"].append(alias)
    write_canonical_json(manifest_path, manifest)
    with pytest.raises(NamespaceIntegrityError, match="path_alias"):
        validate_namespace_manifest(staging)

    write_namespace_manifest(staging)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = "../escape.json"
    write_canonical_json(manifest_path, manifest)
    with pytest.raises(NamespaceIntegrityError, match="path_unsafe"):
        validate_namespace_manifest(staging)


def test_namespace_rejects_nested_symlink(tmp_path: Path) -> None:
    staging = _valid_staging(tmp_path)
    victim = staging / PAYLOAD_SPECS[-1].path
    outside = tmp_path / "outside.json"
    outside.write_bytes(victim.read_bytes())
    victim.unlink()
    try:
        victim.symlink_to(outside)
    except OSError:
        pytest.skip("file symlink creation is unavailable on this host")

    with pytest.raises(NamespaceIntegrityError, match="not_regular_file"):
        validate_namespace_manifest(staging)


def test_namespace_rejects_hardlink_unconditionally(tmp_path: Path) -> None:
    staging = _valid_staging(tmp_path)
    victim = staging / PAYLOAD_SPECS[-1].path
    outside = tmp_path / "outside.json"
    outside.write_bytes(victim.read_bytes())
    victim.unlink()
    try:
        os.link(outside, victim)
    except OSError:
        pytest.skip("hardlink creation is unavailable on this host")

    with pytest.raises(NamespaceIntegrityError, match="hardlink_rejected"):
        validate_namespace_manifest(staging)


def test_namespace_rejects_link_like_profile_root(tmp_path: Path) -> None:
    staging = _valid_staging(tmp_path)
    link = tmp_path / "profile-link"
    try:
        link.symlink_to(staging, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable on this host")

    with pytest.raises(NamespaceIntegrityError, match="not_real_directory"):
        validate_namespace_manifest(link)
