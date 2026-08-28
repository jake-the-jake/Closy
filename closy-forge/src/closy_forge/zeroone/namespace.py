from __future__ import annotations

import hashlib
import os
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.paths import validate_package_relpath
from closy_forge.security.strict_json import StrictJsonError, load_strict_json_object

MANIFEST_NAME = "namespace_manifest.json"
MANIFEST_VERSION = "closy.zeroone.namespace-manifest.v1"
MAX_FILE_COUNT = 32
MAX_FILE_BYTES = 67_108_864
MAX_TOTAL_BYTES = 134_217_728
MAX_NESTING_DEPTH = 8
MANAGED_MARKER = ".closy-forge-owned.json"


@dataclass(frozen=True)
class NamespaceFileSpec:
    path: str
    role: str
    media_type: str
    source_relationship: str
    required: bool = True


PAYLOAD_SPECS = (
    NamespaceFileSpec(
        "request.json", "request", "application/json", "closy_canonical_authority_request"
    ),
    NamespaceFileSpec(
        "processing_report.json", "processing_report", "application/json", "zeroone_process"
    ),
    NamespaceFileSpec(
        "validation_report.json", "validation_report", "application/json", "zeroone_validation"
    ),
    NamespaceFileSpec("compatibility.json", "compatibility", "application/json", "closy_contract"),
    NamespaceFileSpec("provenance.json", "provenance", "application/json", "closy_publication"),
    NamespaceFileSpec(
        "derivative/artifact.geomesh",
        "geometry_artifact",
        "application/vnd.zeroone.geomesh",
        "zeroone_static_output",
    ),
    NamespaceFileSpec(
        "derivative/native/cooked_asset.z1ddc",
        "cooked_asset",
        "application/vnd.zeroone.cooked-asset",
        "zeroone_static_output",
    ),
    NamespaceFileSpec(
        "derivative/native/page_packs/manifest.json",
        "page_pack_manifest",
        "application/json",
        "zeroone_static_output",
    ),
    NamespaceFileSpec(
        "derivative/native/page_packs/packs.bin",
        "page_pack_data",
        "application/octet-stream",
        "zeroone_static_output",
    ),
    NamespaceFileSpec(
        "derivative/garment/stitch_rows.json",
        "garment_stitch_rows",
        "application/json",
        "zeroone_static_output",
    ),
    NamespaceFileSpec(
        "derivative/lod.json", "lod_manifest", "application/json", "zeroone_static_output"
    ),
    NamespaceFileSpec(
        "derivative/materials.json",
        "material_manifest",
        "application/json",
        "zeroone_static_output",
    ),
)
DERIVATIVE_SPECS = PAYLOAD_SPECS[5:]
EXPECTED_PATHS = frozenset(spec.path for spec in PAYLOAD_SPECS)
EXPECTED_ROLES = frozenset(spec.role for spec in PAYLOAD_SPECS)
FORBIDDEN_SUFFIXES = frozenset(
    {".bat", ".cmd", ".com", ".exe", ".jpeg", ".jpg", ".log", ".ps1", ".py", ".sh"}
)


class NamespaceIntegrityError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def write_namespace_manifest(root: Path) -> dict[str, Any]:
    files = [_file_entry(root, spec) for spec in PAYLOAD_SPECS]
    manifest = {
        "schemaVersion": 1,
        "manifestVersion": MANIFEST_VERSION,
        "profile": "closy-static-d0-cpu-v1",
        "canonicalInventoryDigest": _inventory_digest(files),
        "files": files,
    }
    write_canonical_json(root / MANIFEST_NAME, manifest)
    return manifest


def validate_namespace_manifest(root: Path) -> dict[str, Any]:
    _validate_real_directory(root, "zeroone_profile_not_real_directory")
    try:
        manifest = load_strict_json_object(
            root / MANIFEST_NAME,
            expected_fields={
                "schemaVersion",
                "manifestVersion",
                "profile",
                "canonicalInventoryDigest",
                "files",
            },
        )
    except StrictJsonError as error:
        raise NamespaceIntegrityError(f"zeroone_manifest_{error.code}") from error
    if (
        manifest.get("schemaVersion") != 1
        or manifest.get("manifestVersion") != MANIFEST_VERSION
        or manifest.get("profile") != "closy-static-d0-cpu-v1"
    ):
        raise NamespaceIntegrityError("zeroone_manifest_version_mismatch")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) > MAX_FILE_COUNT:
        raise NamespaceIntegrityError("zeroone_manifest_file_count_invalid")
    paths: list[str] = []
    roles: list[str] = []
    normalized: set[str] = set()
    casefolded: set[str] = set()
    total_size = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "path",
            "role",
            "size",
            "sha256",
            "mediaType",
            "sourceRelationship",
            "required",
        }:
            raise NamespaceIntegrityError("zeroone_manifest_entry_invalid")
        relative = row.get("path")
        role = row.get("role")
        if not isinstance(relative, str) or not isinstance(role, str):
            raise NamespaceIntegrityError("zeroone_manifest_entry_invalid")
        _validate_relative_identity(relative, normalized=normalized, casefolded=casefolded)
        paths.append(relative)
        roles.append(role)
        expected = next((spec for spec in PAYLOAD_SPECS if spec.path == relative), None)
        if expected is None or (
            role != expected.role
            or row.get("mediaType") != expected.media_type
            or row.get("sourceRelationship") != expected.source_relationship
            or row.get("required") is not expected.required
        ):
            raise NamespaceIntegrityError("zeroone_manifest_role_invalid")
        size = row.get("size")
        digest = row.get("sha256")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or size > MAX_FILE_BYTES
            or not isinstance(digest, str)
            or len(digest) != 64
        ):
            raise NamespaceIntegrityError("zeroone_manifest_file_metadata_invalid")
        observed = read_verified_regular_file(root, relative, maximum_bytes=MAX_FILE_BYTES)
        if len(observed) != size or hashlib.sha256(observed).hexdigest() != digest:
            raise NamespaceIntegrityError("zeroone_manifest_file_mismatch")
        total_size += size
    if set(paths) != EXPECTED_PATHS or len(paths) != len(set(paths)):
        raise NamespaceIntegrityError("zeroone_manifest_exact_path_set_invalid")
    if set(roles) != EXPECTED_ROLES or len(roles) != len(set(roles)):
        raise NamespaceIntegrityError("zeroone_manifest_exact_role_set_invalid")
    if total_size > MAX_TOTAL_BYTES:
        raise NamespaceIntegrityError("zeroone_manifest_total_size_exceeded")
    if manifest.get("canonicalInventoryDigest") != _inventory_digest(rows):
        raise NamespaceIntegrityError("zeroone_manifest_inventory_digest_mismatch")
    actual = {
        path.relative_to(root).as_posix() for path in _walk_without_links(root) if path.is_file()
    }
    expected_files = EXPECTED_PATHS | {MANIFEST_NAME, MANAGED_MARKER}
    if actual != expected_files:
        raise NamespaceIntegrityError("zeroone_namespace_exact_inventory_mismatch")
    return manifest


def copy_verified_derivative(source: Path, destination: Path) -> None:
    for spec in DERIVATIVE_SPECS:
        source_relative = spec.path.removeprefix("derivative/")
        data = read_verified_regular_file(source, source_relative, maximum_bytes=MAX_FILE_BYTES)
        target = destination / spec.path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)


def read_verified_regular_file(root: Path, relative: str, *, maximum_bytes: int) -> bytes:
    validate_package_relpath(relative)
    if len(Path(relative).parts) > MAX_NESTING_DEPTH:
        raise NamespaceIntegrityError("zeroone_namespace_depth_exceeded")
    _validate_real_directory(root, "zeroone_namespace_root_not_real_directory")
    path = root / relative
    _validate_parent_chain(root, path.parent)
    try:
        lexical = path.stat(follow_symlinks=False)
    except OSError as error:
        raise NamespaceIntegrityError("zeroone_namespace_file_missing") from error
    _validate_file_stat(lexical)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise NamespaceIntegrityError("zeroone_namespace_safe_open_failed") from error
    try:
        opened = os.fstat(descriptor)
        if not _same_identity(lexical, opened):
            raise NamespaceIntegrityError("zeroone_namespace_identity_changed")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1_048_576, maximum_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise NamespaceIntegrityError("zeroone_namespace_file_too_large")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if not _same_identity(opened, after) or opened.st_size != after.st_size:
            raise NamespaceIntegrityError("zeroone_namespace_file_mutated")
    finally:
        os.close(descriptor)
    try:
        final = path.stat(follow_symlinks=False)
    except OSError as error:
        raise NamespaceIntegrityError("zeroone_namespace_file_replaced") from error
    if not _same_identity(opened, final) or opened.st_size != final.st_size:
        raise NamespaceIntegrityError("zeroone_namespace_file_replaced")
    return b"".join(chunks)


def _file_entry(root: Path, spec: NamespaceFileSpec) -> dict[str, Any]:
    data = read_verified_regular_file(root, spec.path, maximum_bytes=MAX_FILE_BYTES)
    return {
        "path": spec.path,
        "role": spec.role,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mediaType": spec.media_type,
        "sourceRelationship": spec.source_relationship,
        "required": spec.required,
    }


def _inventory_digest(rows: list[dict[str, Any]]) -> str:
    inventory = {"schemaVersion": 1, "files": sorted(rows, key=lambda row: str(row["path"]))}
    return hashlib.sha256(canonical_dumps(inventory).encode("utf-8")).hexdigest()


def _validate_relative_identity(
    relative: str, *, normalized: set[str], casefolded: set[str]
) -> None:
    try:
        validate_package_relpath(relative)
    except ValueError as error:
        raise NamespaceIntegrityError("zeroone_manifest_path_unsafe") from error
    if Path(relative).suffix.casefold() in FORBIDDEN_SUFFIXES:
        raise NamespaceIntegrityError("zeroone_manifest_forbidden_file_type")
    canonical = unicodedata.normalize("NFC", relative)
    folded = canonical.casefold()
    if canonical != relative:
        raise NamespaceIntegrityError("zeroone_manifest_unicode_alias")
    if canonical in normalized or folded in casefolded:
        raise NamespaceIntegrityError("zeroone_manifest_path_alias")
    normalized.add(canonical)
    casefolded.add(folded)


def _validate_real_directory(path: Path, code: str) -> None:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as error:
        raise NamespaceIntegrityError(code) from error
    if not stat.S_ISDIR(metadata.st_mode) or _is_link_like(metadata):
        raise NamespaceIntegrityError(code)


def _validate_parent_chain(root: Path, parent: Path) -> None:
    current = root
    try:
        relative = parent.relative_to(root)
    except ValueError as error:
        raise NamespaceIntegrityError("zeroone_namespace_path_escape") from error
    for part in relative.parts:
        current /= part
        _validate_real_directory(current, "zeroone_namespace_parent_not_real_directory")


def _validate_file_stat(metadata: os.stat_result) -> None:
    if not stat.S_ISREG(metadata.st_mode) or _is_link_like(metadata):
        raise NamespaceIntegrityError("zeroone_namespace_not_regular_file")
    if metadata.st_nlink != 1:
        raise NamespaceIntegrityError("zeroone_namespace_hardlink_rejected")
    if metadata.st_size > MAX_FILE_BYTES:
        raise NamespaceIntegrityError("zeroone_namespace_file_too_large")


def _is_link_like(metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & reparse_flag
    )


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
    )


def _walk_without_links(root: Path) -> list[Path]:
    found: list[Path] = []
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                path = Path(entry.path)
                # DirEntry.stat reports st_nlink=0 on some Windows/Python builds.
                metadata = path.stat(follow_symlinks=False)
                if _is_link_like(metadata):
                    raise NamespaceIntegrityError("zeroone_namespace_link_like_entry")
                if stat.S_ISDIR(metadata.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(metadata.st_mode):
                    if metadata.st_nlink != 1:
                        raise NamespaceIntegrityError("zeroone_namespace_hardlink_rejected")
                    found.append(path)
                else:
                    raise NamespaceIntegrityError("zeroone_namespace_special_file_rejected")
    return found
