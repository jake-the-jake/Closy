from __future__ import annotations

import os
import shutil
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_bytes

PUBLIC_CODES = frozenset(
    {
        "collector_root_invalid",
        "collector_root_indirection_forbidden",
        "collector_name_or_depth_forbidden",
        "collector_file_count_exceeded",
        "collector_symlink_or_reparse_forbidden",
        "collector_nonregular_forbidden",
        "collector_hardlink_forbidden",
        "collector_file_too_large",
        "collector_total_too_large",
        "collector_replacement_race",
        "collector_io_failure",
    }
)


class SecureCollectionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code if code in PUBLIC_CODES else "collector_io_failure")
        self.code = str(self)


class AuthorityOwnedOutput:
    """Output root whose parent and lifetime are owned by the authority process."""

    def __init__(self, prefix: str = "closy-authority-output-") -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix=prefix)
        self.owner = Path(self._temporary.name).resolve()
        self.path = self.owner / "outputs"
        self.path.mkdir(mode=0o700)
        self._descriptor = _open_directory(self.path)
        _validate_root(self.owner, self.path)

    @property
    def descriptor(self) -> int | None:
        return self._descriptor

    def close(self) -> None:
        if self._descriptor is not None:
            os.close(self._descriptor)
            self._descriptor = None
        self._temporary.cleanup()

    def __enter__(self) -> AuthorityOwnedOutput:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def collect_owned_outputs(
    owned: AuthorityOwnedOutput,
    *,
    allowed_names: frozenset[str],
    maximum_files: int = 8,
    maximum_file_bytes: int = 1_000_000,
    maximum_total_bytes: int = 2_000_000,
    after_lstat: Callable[[Path], None] | None = None,
) -> list[dict[str, Any]]:
    try:
        _validate_root(owned.owner, owned.path)
        entries = sorted(owned.path.iterdir(), key=lambda path: path.name)
        if len(entries) > maximum_files:
            raise SecureCollectionError("collector_file_count_exceeded")
        records: list[dict[str, Any]] = []
        total = 0
        for entry in entries:
            if entry.name not in allowed_names or entry.parent != owned.path:
                raise SecureCollectionError("collector_name_or_depth_forbidden")
            before = entry.lstat()
            _validate_entry(before, maximum_file_bytes)
            if after_lstat:
                after_lstat(entry)
            descriptor = _open_child(owned.path, owned.descriptor, entry.name)
            try:
                opened = os.fstat(descriptor)
                _validate_entry(opened, maximum_file_bytes)
                if _identity(before) != _identity(opened):
                    raise SecureCollectionError("collector_replacement_race")
                data = _bounded_read(descriptor, maximum_file_bytes)
                after = os.fstat(descriptor)
            finally:
                os.close(descriptor)
            if _identity(opened) != _identity(after) or len(data) != after.st_size:
                raise SecureCollectionError("collector_replacement_race")
            total += len(data)
            if total > maximum_total_bytes:
                raise SecureCollectionError("collector_total_too_large")
            records.append(
                {"path": entry.name, "byteLength": len(data), "sha256": sha256_bytes(data)}
            )
        return records
    except SecureCollectionError:
        _quarantine_inside_owner(owned)
        raise
    except OSError:
        _quarantine_inside_owner(owned)
        raise SecureCollectionError("collector_io_failure") from None


def _validate_root(owner: Path, root: Path) -> None:
    try:
        owner_stat = owner.lstat()
        root_stat = root.lstat()
    except OSError:
        raise SecureCollectionError("collector_root_invalid") from None
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
        raise SecureCollectionError("collector_root_indirection_forbidden")
    if _is_reparse(root_stat) or os.path.ismount(root):
        raise SecureCollectionError("collector_root_indirection_forbidden")
    if root.parent != owner or root_stat.st_dev != owner_stat.st_dev:
        raise SecureCollectionError("collector_root_indirection_forbidden")


def _validate_entry(metadata: os.stat_result, maximum: int) -> None:
    code = validate_file_metadata(
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        maximum,
        file_attributes=int(getattr(metadata, "st_file_attributes", 0)),
    )
    if code:
        raise SecureCollectionError(code)


def validate_file_metadata(
    mode: int,
    link_count: int,
    size: int,
    maximum: int,
    *,
    file_attributes: int = 0,
) -> str | None:
    if stat.S_ISLNK(mode) or file_attributes & int(
        getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        return "collector_symlink_or_reparse_forbidden"
    if not stat.S_ISREG(mode):
        return "collector_nonregular_forbidden"
    if link_count != 1:
        return "collector_hardlink_forbidden"
    if size < 0 or size > maximum:
        return "collector_file_too_large"
    return None


def _is_reparse(metadata: os.stat_result) -> bool:
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    return bool(attributes & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)))


def _open_directory(path: Path) -> int | None:
    if os.open not in os.supports_dir_fd or not hasattr(os, "O_DIRECTORY"):
        return None
    return os.open(path, os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)))


def _open_child(root: Path, root_descriptor: int | None, name: str) -> int:
    flags = os.O_RDONLY | int(getattr(os, "O_NOFOLLOW", 0))
    if root_descriptor is not None:
        return os.open(name, flags, dir_fd=root_descriptor)
    return os.open(root / name, flags)


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_nlink


def _bounded_read(descriptor: int, maximum: int) -> bytes:
    chunks: list[bytes] = []
    length = 0
    while length <= maximum:
        block = os.read(descriptor, min(65_536, maximum + 1 - length))
        if not block:
            break
        chunks.append(block)
        length += len(block)
    if length > maximum:
        raise SecureCollectionError("collector_file_too_large")
    return b"".join(chunks)


def _quarantine_inside_owner(owned: AuthorityOwnedOutput) -> None:
    root = owned.path
    if root.parent != owned.owner:
        return
    quarantine = owned.owner / "quarantine"
    if quarantine.exists():
        shutil.rmtree(quarantine)
    try:
        os.replace(root, quarantine)
        root.mkdir(mode=0o700)
    except OSError:
        # The authority-owned temporary parent is deleted on close; never recurse elsewhere.
        return
