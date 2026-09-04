from __future__ import annotations

import os
from pathlib import Path

import pytest

from closy_forge.capture_reconstruction_v2.safe_private_io import (
    SafePrivateIoError,
    SafePrivateRoot,
    redacted_private_diagnostic,
    validate_private_name,
)


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "../escape",
        "nested/file",
        "nested\\file",
        "C:secret",
        "CON",
        "nul.txt",
        "trailing.",
        "trailing ",
        "e\u0301.json",
        "line\nbreak",
    ],
)
def test_private_names_fail_closed_for_traversal_reserved_and_noncanonical_unicode(
    name: str,
) -> None:
    with pytest.raises(SafePrivateIoError, match="private_name_invalid"):
        validate_private_name(name)


def test_private_root_write_read_enumerate_quarantine_retention_and_idempotent_delete(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    root.mkdir()
    with SafePrivateRoot(root) as private:
        private.write_atomic("capture.json", b"sensitive-pixels")
        assert private.read("capture.json", 64) == b"sensitive-pixels"
        assert private.list_names() == ["capture.json"]
        retention = private.retention_manifest(64)
        assert retention["fileCount"] == 1
        assert retention["byteLength"] == len(b"sensitive-pixels")
        assert retention["privateNamesAndDigestsRedacted"] is True
        assert "capture.json" not in str(retention)
        quarantined = private.quarantine("capture.json")
        assert quarantined.startswith("quarantine-")
        assert "capture" not in quarantined
        private.delete_idempotent(quarantined)
        private.delete_idempotent(quarantined)
        assert private.list_names() == []


def test_private_root_rejects_symlink_and_nested_link_entries_when_supported(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        root.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(SafePrivateIoError):
        SafePrivateRoot(root)

    root.unlink()
    root.mkdir()
    outside_file = outside / "source.bin"
    outside_file.write_bytes(b"secret")
    link = root / "link.bin"
    link.symlink_to(outside_file)
    with SafePrivateRoot(root) as private:
        with pytest.raises(SafePrivateIoError):
            private.read("link.bin", 64)
        with pytest.raises(SafePrivateIoError):
            private.list_names()


def test_private_root_rejects_hard_links_when_supported(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir()
    source = tmp_path / "outside.bin"
    source.write_bytes(b"secret")
    linked = root / "linked.bin"
    try:
        os.link(source, linked)
    except OSError:
        pytest.skip("hard-link creation unavailable")
    with SafePrivateRoot(root) as private:
        with pytest.raises(SafePrivateIoError):
            private.read("linked.bin", 64)
        with pytest.raises(SafePrivateIoError):
            private.list_names()


def test_private_root_detects_named_root_replacement(tmp_path: Path) -> None:
    root = tmp_path / "private"
    moved = tmp_path / "moved"
    root.mkdir()
    private = SafePrivateRoot(root)
    try:
        root.rename(moved)
        root.mkdir()
        with pytest.raises(SafePrivateIoError, match="private_race_detected"):
            private.list_names()
    finally:
        private.close()


def test_attacker_manifest_name_cannot_escape_and_diagnostics_never_echo_secrets(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    root.mkdir()
    secret_name = "private-user-123-photo.png"
    with (
        SafePrivateRoot(root) as private,
        pytest.raises(SafePrivateIoError) as captured,
    ):
        private.read(f"../{secret_name}", 128)
    diagnostic = redacted_private_diagnostic(captured.value)
    assert diagnostic == {
        "code": "private_name_invalid",
        "detail": "redacted_private_storage_failure",
    }
    assert secret_name not in str(diagnostic)


def test_read_size_limit_and_closed_root_fail_safely(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir()
    private = SafePrivateRoot(root)
    private.write_atomic("value.bin", b"123456")
    with pytest.raises(SafePrivateIoError):
        private.read("value.bin", 3)
    private.close()
    if os.name == "nt":
        # Windows uses the named root for each operation and therefore has no
        # persistent descriptor to close.
        return
    with pytest.raises(SafePrivateIoError, match="private_root_invalid"):
        private.read("value.bin", 64)
