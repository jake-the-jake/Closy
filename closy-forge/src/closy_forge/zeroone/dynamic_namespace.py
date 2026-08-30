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
from closy_forge.zeroone.dynamic_request import DYNAMIC_PROFILE
from closy_forge.zeroone.namespace import NamespaceIntegrityError, read_verified_regular_file

DYNAMIC_DIRECTORY = "mechanical-reference-v2"
DYNAMIC_PURPOSE = "zeroone-mechanical-reference-v2"
DYNAMIC_MANIFEST_NAME = "namespace_manifest.json"
DYNAMIC_MANIFEST_VERSION = "closy.zeroone.mechanical-reference-namespace-manifest.v2"
MANAGED_MARKER = ".closy-forge-owned.json"
MAX_FILE_COUNT = 24
MAX_FILE_BYTES = 536_870_912
MAX_TOTAL_BYTES = 536_870_912
FORBIDDEN_SUFFIXES = frozenset(
    {".bat", ".cmd", ".com", ".exe", ".jpeg", ".jpg", ".log", ".ps1", ".py", ".sh"}
)


@dataclass(frozen=True)
class DynamicNamespaceFileSpec:
    path: str
    role: str
    media_type: str
    source_relationship: str


DYNAMIC_PAYLOAD_SPECS = (
    DynamicNamespaceFileSpec(
        "capability.json", "capability", "application/json", "closy_scoped_acceptance"
    ),
    DynamicNamespaceFileSpec(
        "request_summary.json",
        "request_summary",
        "application/json",
        "sanitized_zeroone_request",
    ),
    DynamicNamespaceFileSpec(
        "dynamic_report.json", "dynamic_report", "application/json", "zeroone_process"
    ),
    DynamicNamespaceFileSpec(
        "clip_inventory.json", "clip_inventory", "application/json", "closy_mechanical_clip"
    ),
    DynamicNamespaceFileSpec(
        "influence_lineage.json",
        "influence_lineage",
        "application/json",
        "canonical_binding_projection",
    ),
    DynamicNamespaceFileSpec(
        "bounds.json", "bounds_audit", "application/json", "forge_independent_oracle"
    ),
    DynamicNamespaceFileSpec(
        "normal_tangent.json",
        "normal_tangent_audit",
        "application/json",
        "forge_independent_oracle",
    ),
    DynamicNamespaceFileSpec(
        "oracle_report.json",
        "oracle_report",
        "application/json",
        "forge_independent_oracle",
    ),
    DynamicNamespaceFileSpec(
        "execution.json", "execution", "application/json", "closy_paired_execution"
    ),
    DynamicNamespaceFileSpec(
        "derivative/derivative.z1dyn",
        "dynamic_derivative",
        "application/vnd.zeroone.dynamic-derivative",
        "zeroone_dynamic_output",
    ),
    DynamicNamespaceFileSpec(
        "output_hashes.json", "output_hashes", "application/json", "closy_integrity"
    ),
    DynamicNamespaceFileSpec(
        "provenance.json", "provenance", "application/json", "closy_publication"
    ),
    DynamicNamespaceFileSpec(
        "limitations.json", "limitations", "application/json", "closy_claim_boundary"
    ),
)
DYNAMIC_EXPECTED_PATHS = frozenset(spec.path for spec in DYNAMIC_PAYLOAD_SPECS)
DYNAMIC_EXPECTED_ROLES = frozenset(spec.role for spec in DYNAMIC_PAYLOAD_SPECS)


def write_dynamic_namespace_manifest(root: Path) -> dict[str, Any]:
    rows = [_file_entry(root, spec) for spec in DYNAMIC_PAYLOAD_SPECS]
    manifest = {
        "schemaVersion": 1,
        "manifestVersion": DYNAMIC_MANIFEST_VERSION,
        "profile": DYNAMIC_PROFILE,
        "inventoryDigest": _inventory_digest(rows),
        "files": rows,
    }
    write_canonical_json(root / DYNAMIC_MANIFEST_NAME, manifest)
    return manifest


def validate_dynamic_namespace_manifest(root: Path) -> dict[str, Any]:
    _validate_real_directory(root, "zeroone_dynamic_profile_not_real_directory")
    try:
        manifest = load_strict_json_object(
            root / DYNAMIC_MANIFEST_NAME,
            expected_fields={
                "schemaVersion",
                "manifestVersion",
                "profile",
                "inventoryDigest",
                "files",
            },
        )
    except StrictJsonError as error:
        raise NamespaceIntegrityError(f"zeroone_dynamic_manifest_{error.code}") from error
    if (
        manifest.get("schemaVersion") != 1
        or manifest.get("manifestVersion") != DYNAMIC_MANIFEST_VERSION
        or manifest.get("profile") != DYNAMIC_PROFILE
    ):
        raise NamespaceIntegrityError("zeroone_dynamic_manifest_version_mismatch")
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows or len(rows) > MAX_FILE_COUNT:
        raise NamespaceIntegrityError("zeroone_dynamic_manifest_file_count_invalid")
    by_path = {spec.path: spec for spec in DYNAMIC_PAYLOAD_SPECS}
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
            raise NamespaceIntegrityError("zeroone_dynamic_manifest_entry_invalid")
        relative = row.get("path")
        role = row.get("role")
        if not isinstance(relative, str) or not isinstance(role, str):
            raise NamespaceIntegrityError("zeroone_dynamic_manifest_entry_invalid")
        _validate_relative_identity(relative, normalized=normalized, casefolded=casefolded)
        expected = by_path.get(relative)
        if expected is None or (
            role != expected.role
            or row.get("mediaType") != expected.media_type
            or row.get("sourceRelationship") != expected.source_relationship
            or row.get("required") is not True
        ):
            raise NamespaceIntegrityError("zeroone_dynamic_manifest_role_invalid")
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
            raise NamespaceIntegrityError("zeroone_dynamic_manifest_file_metadata_invalid")
        data = read_verified_regular_file(root, relative, maximum_bytes=MAX_FILE_BYTES)
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise NamespaceIntegrityError("zeroone_dynamic_manifest_file_mismatch")
        paths.append(relative)
        roles.append(role)
        total_size += size
    if set(paths) != DYNAMIC_EXPECTED_PATHS or len(paths) != len(set(paths)):
        raise NamespaceIntegrityError("zeroone_dynamic_manifest_exact_path_set_invalid")
    if set(roles) != DYNAMIC_EXPECTED_ROLES or len(roles) != len(set(roles)):
        raise NamespaceIntegrityError("zeroone_dynamic_manifest_exact_role_set_invalid")
    if total_size > MAX_TOTAL_BYTES:
        raise NamespaceIntegrityError("zeroone_dynamic_manifest_total_size_exceeded")
    if manifest.get("inventoryDigest") != _inventory_digest(rows):
        raise NamespaceIntegrityError("zeroone_dynamic_manifest_inventory_digest_mismatch")
    actual = {
        path.relative_to(root).as_posix() for path in _walk_without_links(root) if path.is_file()
    }
    expected_files = DYNAMIC_EXPECTED_PATHS | {DYNAMIC_MANIFEST_NAME, MANAGED_MARKER}
    if actual != expected_files:
        raise NamespaceIntegrityError("zeroone_dynamic_namespace_exact_inventory_mismatch")
    return manifest


def _file_entry(root: Path, spec: DynamicNamespaceFileSpec) -> dict[str, Any]:
    data = read_verified_regular_file(root, spec.path, maximum_bytes=MAX_FILE_BYTES)
    return {
        "path": spec.path,
        "role": spec.role,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mediaType": spec.media_type,
        "sourceRelationship": spec.source_relationship,
        "required": True,
    }


def _inventory_digest(rows: list[dict[str, Any]]) -> str:
    value = {"schemaVersion": 1, "files": sorted(rows, key=lambda row: str(row["path"]))}
    return hashlib.sha256(canonical_dumps(value).encode("utf-8")).hexdigest()


def _validate_relative_identity(
    relative: str, *, normalized: set[str], casefolded: set[str]
) -> None:
    try:
        validate_package_relpath(relative)
    except ValueError as error:
        raise NamespaceIntegrityError("zeroone_dynamic_manifest_path_unsafe") from error
    if Path(relative).suffix.casefold() in FORBIDDEN_SUFFIXES:
        raise NamespaceIntegrityError("zeroone_dynamic_manifest_forbidden_file_type")
    canonical = unicodedata.normalize("NFC", relative)
    folded = canonical.casefold()
    if canonical != relative or canonical in normalized or folded in casefolded:
        raise NamespaceIntegrityError("zeroone_dynamic_manifest_path_alias")
    normalized.add(canonical)
    casefolded.add(folded)


def _validate_real_directory(path: Path, code: str) -> None:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as error:
        raise NamespaceIntegrityError(code) from error
    if not stat.S_ISDIR(metadata.st_mode) or _is_link_like(metadata):
        raise NamespaceIntegrityError(code)


def _walk_without_links(root: Path) -> list[Path]:
    found: list[Path] = []
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                path = Path(entry.path)
                metadata = path.stat(follow_symlinks=False)
                if _is_link_like(metadata):
                    raise NamespaceIntegrityError("zeroone_dynamic_namespace_link_like_entry")
                if stat.S_ISDIR(metadata.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(metadata.st_mode):
                    if metadata.st_nlink != 1:
                        raise NamespaceIntegrityError("zeroone_dynamic_namespace_hardlink_rejected")
                    found.append(path)
                else:
                    raise NamespaceIntegrityError("zeroone_dynamic_namespace_special_file_rejected")
    return found


def _is_link_like(metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & reparse_flag
    )
