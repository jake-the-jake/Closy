from __future__ import annotations

import os
import re
import secrets
import stat
import unicodedata
from pathlib import Path

PUBLIC_ERROR_CODES = frozenset(
    {
        "unsupported_safe_io",
        "private_root_invalid",
        "private_name_invalid",
        "private_link_forbidden",
        "private_hardlink_forbidden",
        "private_race_detected",
        "private_cross_device_forbidden",
        "private_io_failure",
    }
)
WINDOWS_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.IGNORECASE)
_O_BINARY: int = getattr(os, "O_BINARY", 0)


class SafePrivateIoError(OSError):
    def __init__(self, code: str) -> None:
        safe = code if code in PUBLIC_ERROR_CODES else "private_io_failure"
        super().__init__(safe)
        self.code = safe


class SafePrivateRoot:
    """Single-component private storage with link and root-identity checks.

    POSIX uses descriptor-relative operations with O_NOFOLLOW. Windows has no
    Python openat equivalent, so each bounded operation verifies the root and
    file identities before and after access and rejects all reparse points.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._fd: int | None = None
        self._windows = os.name == "nt"
        if self._windows:
            self._open_windows_root()
            return
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        if not getattr(os, "O_NOFOLLOW", 0) or not getattr(os, "O_DIRECTORY", 0):
            raise SafePrivateIoError("unsupported_safe_io")
        try:
            fd = os.open(root, flags)
            opened = os.fstat(fd)
            named = os.stat(root, follow_symlinks=False)
        except OSError as error:
            raise SafePrivateIoError("private_root_invalid") from error
        if not stat.S_ISDIR(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            named.st_dev,
            named.st_ino,
        ):
            os.close(fd)
            raise SafePrivateIoError("private_race_detected")
        self._fd = fd
        self._device = opened.st_dev
        self._root_identity = (opened.st_dev, opened.st_ino)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> SafePrivateRoot:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def write_atomic(self, name: str, payload: bytes) -> None:
        if self._windows:
            self._windows_write_atomic(name, payload)
            return
        fd = self._require_fd()
        self._verify_posix_root()
        safe_name = validate_private_name(name)
        temporary = f".{safe_name}.partial"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            output = os.open(temporary, flags, 0o600, dir_fd=fd)
            try:
                os.write(output, payload)
                os.fsync(output)
                opened = os.fstat(output)
                if opened.st_nlink != 1:
                    raise SafePrivateIoError("private_hardlink_forbidden")
                if opened.st_dev != self._device:
                    raise SafePrivateIoError("private_cross_device_forbidden")
            finally:
                os.close(output)
            os.replace(temporary, safe_name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
            self._verify_posix_root()
        except SafePrivateIoError:
            self._unlink_if_present(temporary)
            raise
        except OSError as error:
            self._unlink_if_present(temporary)
            raise SafePrivateIoError("private_io_failure") from error

    def read(self, name: str, maximum_bytes: int) -> bytes:
        if maximum_bytes < 0:
            raise SafePrivateIoError("private_io_failure")
        if self._windows:
            return self._windows_read(name, maximum_bytes)
        fd = self._require_fd()
        self._verify_posix_root()
        safe_name = validate_private_name(name)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            source = os.open(safe_name, flags, dir_fd=fd)
            try:
                opened = os.fstat(source)
                if not stat.S_ISREG(opened.st_mode):
                    raise SafePrivateIoError("private_link_forbidden")
                if opened.st_nlink != 1:
                    raise SafePrivateIoError("private_hardlink_forbidden")
                if opened.st_dev != self._device or opened.st_size > maximum_bytes:
                    raise SafePrivateIoError("private_cross_device_forbidden")
                payload = os.read(source, maximum_bytes + 1)
                if len(payload) > maximum_bytes:
                    raise SafePrivateIoError("private_io_failure")
                self._verify_posix_root()
                return payload
            finally:
                os.close(source)
        except SafePrivateIoError:
            raise
        except OSError as error:
            raise SafePrivateIoError("private_io_failure") from error

    def delete_idempotent(self, name: str) -> None:
        safe_name = validate_private_name(name)
        if self._windows:
            self._verify_windows_root()
            path = self._root / safe_name
            try:
                metadata = os.lstat(path)
            except FileNotFoundError:
                return
            self._reject_windows_reparse(metadata)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise SafePrivateIoError("private_link_forbidden")
            try:
                path.unlink()
            except OSError as error:
                raise SafePrivateIoError("private_io_failure") from error
            self._verify_windows_root()
            return
        self._unlink_if_present(safe_name)
        os.fsync(self._require_fd())
        self._verify_posix_root()

    def list_names(self) -> list[str]:
        if self._windows:
            self._verify_windows_root()
            rows = [self._validate_listed_entry(path) for path in self._root.iterdir()]
            self._verify_windows_root()
            return sorted(rows, key=str.casefold)
        fd = self._require_fd()
        # /proc is not a portability contract, so enumeration uses the named
        # root bracketed by descriptor identity checks.
        self._verify_posix_root()
        rows = [self._validate_listed_entry(path) for path in self._root.iterdir()]
        self._verify_posix_root()
        os.fsync(fd)
        return sorted(rows, key=str.casefold)

    def retention_manifest(self, maximum_bytes: int) -> dict[str, object]:
        rows: list[dict[str, object]] = []
        total = 0
        for name in self.list_names():
            payload = self.read(name, maximum_bytes)
            total += len(payload)
            rows.append({"opaqueOrdinal": len(rows), "byteLength": len(payload)})
        return {
            "schemaVersion": 1,
            "fileCount": len(rows),
            "byteLength": total,
            "files": rows,
            "privateNamesAndDigestsRedacted": True,
        }

    def quarantine(self, name: str) -> str:
        safe_name = validate_private_name(name)
        # A random opaque name avoids publishing a reversible dictionary hash of
        # a private filename while keeping the quarantine operation root-local.
        opaque = f"quarantine-{secrets.token_hex(12)}.item"
        if self._windows:
            self._verify_windows_root()
            source = self._root / safe_name
            metadata = os.lstat(source)
            self._reject_windows_reparse(metadata)
            try:
                os.replace(source, self._root / opaque)
            except OSError as error:
                raise SafePrivateIoError("private_io_failure") from error
            self._verify_windows_root()
            return opaque
        try:
            self._verify_posix_root()
            os.replace(
                safe_name, opaque, src_dir_fd=self._require_fd(), dst_dir_fd=self._require_fd()
            )
            os.fsync(self._require_fd())
            self._verify_posix_root()
        except OSError as error:
            raise SafePrivateIoError("private_io_failure") from error
        return opaque

    def _unlink_if_present(self, name: str) -> None:
        try:
            os.unlink(name, dir_fd=self._require_fd())
        except FileNotFoundError:
            return
        except OSError as error:
            raise SafePrivateIoError("private_io_failure") from error

    def _require_fd(self) -> int:
        if self._fd is None:
            raise SafePrivateIoError("private_root_invalid")
        return self._fd

    def _open_windows_root(self) -> None:
        try:
            metadata = os.lstat(self._root)
        except OSError as error:
            raise SafePrivateIoError("private_root_invalid") from error
        self._reject_windows_reparse(metadata)
        if not stat.S_ISDIR(metadata.st_mode):
            raise SafePrivateIoError("private_root_invalid")
        self._device = metadata.st_dev
        self._root_identity = (metadata.st_dev, metadata.st_ino)

    def _verify_windows_root(self) -> None:
        try:
            metadata = os.lstat(self._root)
        except OSError as error:
            raise SafePrivateIoError("private_race_detected") from error
        self._reject_windows_reparse(metadata)
        if (metadata.st_dev, metadata.st_ino) != self._root_identity:
            raise SafePrivateIoError("private_race_detected")

    def _verify_posix_root(self) -> None:
        try:
            named = os.stat(self._root, follow_symlinks=False)
            opened = os.fstat(self._require_fd())
        except OSError as error:
            raise SafePrivateIoError("private_race_detected") from error
        if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
            raise SafePrivateIoError("private_race_detected")

    def _windows_write_atomic(self, name: str, payload: bytes) -> None:
        safe_name = validate_private_name(name)
        self._verify_windows_root()
        temporary = self._root / f".{safe_name}.{os.getpid()}.partial"
        target = self._root / safe_name
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_BINARY, 0o600)
            try:
                written = os.write(descriptor, payload)
                if written != len(payload):
                    raise SafePrivateIoError("private_io_failure")
                os.fsync(descriptor)
                opened = os.fstat(descriptor)
                if opened.st_nlink != 1 or opened.st_dev != self._device:
                    raise SafePrivateIoError("private_hardlink_forbidden")
            finally:
                os.close(descriptor)
            self._verify_windows_root()
            os.replace(temporary, target)
            self._verify_windows_root()
        except SafePrivateIoError:
            temporary.unlink(missing_ok=True)
            raise
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise SafePrivateIoError("private_io_failure") from error

    def _windows_read(self, name: str, maximum_bytes: int) -> bytes:
        safe_name = validate_private_name(name)
        self._verify_windows_root()
        path = self._root / safe_name
        try:
            before = os.lstat(path)
            self._reject_windows_reparse(before)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise SafePrivateIoError("private_link_forbidden")
            if before.st_dev != self._device or before.st_size > maximum_bytes:
                raise SafePrivateIoError("private_cross_device_forbidden")
            descriptor = os.open(path, os.O_RDONLY | _O_BINARY)
            try:
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise SafePrivateIoError("private_race_detected")
                payload = os.read(descriptor, maximum_bytes + 1)
            finally:
                os.close(descriptor)
            if len(payload) > maximum_bytes:
                raise SafePrivateIoError("private_io_failure")
            self._verify_windows_root()
            return payload
        except SafePrivateIoError:
            raise
        except OSError as error:
            raise SafePrivateIoError("private_io_failure") from error

    def _validate_listed_entry(self, path: Path) -> str:
        try:
            metadata = os.lstat(path)
        except OSError as error:
            raise SafePrivateIoError("private_race_detected") from error
        if self._windows:
            self._reject_windows_reparse(metadata)
        elif stat.S_ISLNK(metadata.st_mode):
            raise SafePrivateIoError("private_link_forbidden")
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise SafePrivateIoError("private_link_forbidden")
        return validate_private_name(path.name)

    @staticmethod
    def _reject_windows_reparse(metadata: os.stat_result) -> None:
        attributes = int(getattr(metadata, "st_file_attributes", 0))
        reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
        if attributes & reparse:
            raise SafePrivateIoError("private_link_forbidden")


def validate_private_name(name: str) -> str:
    normalized = unicodedata.normalize("NFC", name)
    if (
        not name
        or normalized != name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or ":" in name
        or name.endswith((".", " "))
        or WINDOWS_RESERVED.match(name)
        or any(ord(character) < 32 for character in name)
    ):
        raise SafePrivateIoError("private_name_invalid")
    return name


def redacted_private_diagnostic(error: BaseException) -> dict[str, str]:
    code = error.code if isinstance(error, SafePrivateIoError) else "private_io_failure"
    return {"code": code, "detail": "redacted_private_storage_failure"}
