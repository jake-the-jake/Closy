from __future__ import annotations

import os
import shutil
import stat
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_bytes

DECLARED_OUTPUTS = frozenset({"probe.json", "prediction.json", "lineage.json"})
MAXIMUM_FILES = 8
MAXIMUM_FILE_BYTES = 1_000_000
MAXIMUM_TOTAL_BYTES = 2_000_000


class OutputCollectionError(ValueError):
    """A bounded public error after the complete output root has been quarantined."""


def collect_declared_outputs(
    output_directory: Path,
    *,
    allowed_names: frozenset[str] = DECLARED_OUTPUTS,
    maximum_files: int = MAXIMUM_FILES,
    maximum_file_bytes: int = MAXIMUM_FILE_BYTES,
    maximum_total_bytes: int = MAXIMUM_TOTAL_BYTES,
    after_lstat: Callable[[Path], None] | None = None,
) -> list[dict[str, Any]]:
    root = output_directory.resolve()
    if not root.is_dir():
        raise OutputCollectionError("output_root_missing")
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name)
        if len(entries) > maximum_files:
            raise ValueError("output_file_count_exceeded")
        records: list[dict[str, Any]] = []
        total = 0
        root_descriptor = _open_root_descriptor(root)
        try:
            for entry in entries:
                if entry.parent.resolve() != root or entry.name not in allowed_names:
                    raise ValueError("output_name_or_depth_forbidden")
                before = entry.lstat()
                _validate_metadata(before, entry.name, maximum_file_bytes)
                if after_lstat is not None:
                    after_lstat(entry)
                descriptor = _open_relative(root, root_descriptor, entry.name)
                try:
                    opened = os.fstat(descriptor)
                    _validate_metadata(opened, entry.name, maximum_file_bytes)
                    if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                        raise ValueError("output_inode_or_device_changed")
                    data = _bounded_read(descriptor, maximum_file_bytes)
                    after = os.fstat(descriptor)
                finally:
                    os.close(descriptor)
                if (opened.st_dev, opened.st_ino, opened.st_size) != (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                ) or len(data) != after.st_size:
                    raise ValueError("output_changed_during_collection")
                total += len(data)
                if total > maximum_total_bytes:
                    raise ValueError("output_aggregate_too_large")
                records.append(
                    {
                        "path": entry.name,
                        "byteLength": len(data),
                        "sha256": sha256_bytes(data),
                        "device": int(after.st_dev),
                        "inode": int(after.st_ino),
                        "linkCount": int(after.st_nlink),
                        "fileType": "regular",
                    }
                )
        finally:
            if root_descriptor is not None:
                os.close(root_descriptor)
        return records
    except (OSError, ValueError) as error:
        code = _sanitize_error(error)
        quarantine_output_root(root)
        raise OutputCollectionError(code) from None


def quarantine_output_root(root: Path) -> Path:
    """Atomically hide all outputs and recreate an empty collection root."""
    quarantine = root.with_name(f".{root.name}.quarantine-{uuid.uuid4().hex}")
    try:
        os.replace(root, quarantine)
        root.mkdir(mode=0o700)
    except OSError:
        _destroy_without_following(root)
        root.mkdir(mode=0o700, exist_ok=True)
    return quarantine


def destroy_quarantine(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def validate_mode(mode: int, link_count: int, size: int, maximum_file_bytes: int) -> list[str]:
    issues: list[str] = []
    if stat.S_ISLNK(mode):
        issues.append("output_symlink_forbidden")
    elif not stat.S_ISREG(mode):
        issues.append("output_type_forbidden")
    if link_count != 1:
        issues.append("output_hardlink_forbidden")
    if size < 0 or size > maximum_file_bytes:
        issues.append("output_file_too_large")
    return issues


def executed_collector_mutation_report() -> dict[str, bool]:
    report = {
        "symlink": bool(validate_mode(stat.S_IFLNK | 0o777, 1, 0, MAXIMUM_FILE_BYTES)),
        "fifo": bool(validate_mode(stat.S_IFIFO | 0o600, 1, 0, MAXIMUM_FILE_BYTES)),
        "socket": bool(validate_mode(stat.S_IFSOCK | 0o600, 1, 0, MAXIMUM_FILE_BYTES)),
        "device": bool(validate_mode(stat.S_IFCHR | 0o600, 1, 0, MAXIMUM_FILE_BYTES)),
        "hardlink": bool(validate_mode(stat.S_IFREG | 0o600, 2, 2, MAXIMUM_FILE_BYTES)),
    }
    with tempfile.TemporaryDirectory(prefix="closy-y0-collector-") as temporary:
        base = Path(temporary)
        output = base / "output"
        output.mkdir()
        (output / "probe.json").write_text("{}", encoding="utf-8")
        report["declared_regular_file"] = len(collect_declared_outputs(output)) == 1

        (output / "undeclared.txt").write_text("sensitive", encoding="utf-8")
        report["undeclared_output"] = _fails_and_quarantines(output)

        (output / "probe.json").write_text("{}", encoding="utf-8")
        linked = output / "prediction.json"
        os.link(output / "probe.json", linked)
        report["hardlink_collection"] = _fails_and_quarantines(output)

        (output / "probe.json").write_text("before", encoding="utf-8")

        def replace_after_lstat(path: Path) -> None:
            replacement = path.with_suffix(".replacement")
            replacement.write_text("after", encoding="utf-8")
            os.replace(replacement, path)

        report["race"] = _fails_and_quarantines(output, after_lstat=replace_after_lstat)
    return report


def _validate_metadata(metadata: os.stat_result, name: str, maximum_file_bytes: int) -> None:
    issues = validate_mode(
        metadata.st_mode, metadata.st_nlink, metadata.st_size, maximum_file_bytes
    )
    if issues:
        raise ValueError(f"{issues[0]}:{name}")


def _open_root_descriptor(root: Path) -> int | None:
    if os.open not in os.supports_dir_fd or not hasattr(os, "O_DIRECTORY"):
        return None
    flags = os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0))
    return os.open(root, flags)


def _open_relative(root: Path, root_descriptor: int | None, name: str) -> int:
    flags = os.O_RDONLY | int(getattr(os, "O_NOFOLLOW", 0))
    if root_descriptor is not None:
        return os.open(name, flags, dir_fd=root_descriptor)
    return os.open(root / name, flags)


def _bounded_read(descriptor: int, maximum_file_bytes: int) -> bytes:
    chunks: list[bytes] = []
    read = 0
    while read <= maximum_file_bytes:
        block = os.read(descriptor, min(65_536, maximum_file_bytes + 1 - read))
        if not block:
            break
        chunks.append(block)
        read += len(block)
    if read > maximum_file_bytes:
        raise ValueError("output_file_too_large")
    return b"".join(chunks)


def _destroy_without_following(root: Path) -> None:
    for entry in root.iterdir():
        metadata = entry.lstat()
        if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            shutil.rmtree(entry)
        else:
            entry.unlink(missing_ok=True)


def _sanitize_error(error: BaseException) -> str:
    text = str(error).split(":", 1)[0]
    allowed = {
        "output_aggregate_too_large",
        "output_changed_during_collection",
        "output_file_count_exceeded",
        "output_file_too_large",
        "output_hardlink_forbidden",
        "output_inode_or_device_changed",
        "output_name_or_depth_forbidden",
        "output_symlink_forbidden",
        "output_type_forbidden",
    }
    if text == "output_type_forbidden" and "symlink" in str(error).lower():
        return "output_symlink_forbidden"
    return text if text in allowed else "output_collection_os_error"


def _fails_and_quarantines(
    output: Path, *, after_lstat: Callable[[Path], None] | None = None
) -> bool:
    try:
        collect_declared_outputs(output, after_lstat=after_lstat)
    except OutputCollectionError:
        return output.is_dir() and not any(output.iterdir())
    return False
