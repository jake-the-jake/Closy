from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PrivacyBoundaryError(RuntimeError):
    pass


PORTABLE_SOURCE_FIELDS = frozenset(
    {
        "sourceId",
        "mime",
        "decodedWidth",
        "decodedHeight",
        "viewRole",
        "evidenceTier",
        "publicFixtureDigest",
    }
)
DIAGNOSTIC_ALLOWLIST = frozenset(
    {
        "errorCode",
        "sourceId",
        "sessionId",
        "stage",
        "mime",
        "decodedWidth",
        "decodedHeight",
    }
)


@dataclass
class OwnedCaptureSession:
    owner: Path
    root: Path

    @classmethod
    def create(cls) -> OwnedCaptureSession:
        owner = Path(tempfile.mkdtemp(prefix="closy-capture-owner-"))
        root = owner / "session"
        root.mkdir()
        return cls(owner=owner, root=root)

    def delete(self) -> dict[str, Any]:
        owner = self.owner.resolve()
        root = self.root.resolve()
        if root.parent != owner or self.root.is_symlink():
            raise PrivacyBoundaryError("owned_session_root_invalid")
        removed = sum(1 for path in self.root.rglob("*") if path.is_file())
        shutil.rmtree(self.root)
        with suppress(OSError):
            self.owner.rmdir()
        return {"status": "deleted", "removedFileCount": removed, "ownedRootOnly": True}

    def __enter__(self) -> OwnedCaptureSession:
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if self.owner.exists():
            shutil.rmtree(self.owner)


def portable_source_record(private_record: dict[str, Any]) -> dict[str, Any]:
    evidence_tier = str(private_record.get("evidenceTier", ""))
    result = {
        key: value
        for key, value in private_record.items()
        if key in PORTABLE_SOURCE_FIELDS and key != "publicFixtureDigest"
    }
    if evidence_tier == "public_project_fixture":
        result["publicFixtureDigest"] = private_record.get("sourceByteSha256")
    result["absolutePathPersisted"] = False
    result["exifFieldsPersisted"] = []
    result["privateRegistrySeparated"] = True
    return result


def sanitize_diagnostic(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key in DIAGNOSTIC_ALLOWLIST}


def assert_portable_record(record: dict[str, Any]) -> None:
    serialized = repr(record)
    if any(token in serialized for token in (":\\", "/Users/", "/home/", "GPS", "owner")):
        raise PrivacyBoundaryError("portable_record_private_field_detected")
    forbidden = {"absolutePath", "sourceByteSha256", "device", "owner", "gps"}
    if forbidden & set(record):
        raise PrivacyBoundaryError("portable_record_forbidden_key")


def secure_write(root: Path, relative_path: str, data: bytes) -> Path:
    if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
        raise PrivacyBoundaryError("owned_write_path_invalid")
    root_resolved = root.resolve()
    destination = (root / relative_path).resolve()
    try:
        destination.relative_to(root_resolved)
    except ValueError as error:
        raise PrivacyBoundaryError("owned_write_path_escape") from error
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return destination
