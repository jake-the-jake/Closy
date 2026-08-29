from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_io.managed_output import ManagedOutputError, read_managed_marker
from closy_forge.package_io.paths import validate_package_relpath
from closy_forge.security.strict_json import StrictJsonError, load_strict_json_object
from closy_forge.zeroone.namespace import (
    DERIVATIVE_SPECS,
    NamespaceIntegrityError,
    read_verified_regular_file,
    validate_namespace_manifest,
)
from closy_forge.zeroone.tool import PROFILE, REPORT_SCHEMA_VERSION, REQUEST_SCHEMA_VERSION


def inspect_zeroone_namespace(package: Path) -> dict[str, Any]:
    root = package / "zeroone"
    if not root.exists():
        return {"status": "not_present", "reason": "zeroone_derivative_absent"}
    target = root / "static-d0"
    if not target.is_dir():
        if (root / "input-z1-v1").is_dir() and all(
            child.name == "input-z1-v1" for child in root.iterdir()
        ):
            return {"status": "not_present", "reason": "zeroone_derivative_absent"}
        return {"status": "derivative_incompatible", "reason": "static_profile_directory_missing"}
    try:
        marker = read_managed_marker(target)
        if (
            marker.get("owner") != "closy-forge"
            or marker.get("purpose") != "zeroone-static-d0"
            or marker.get("kind") != "published"
        ):
            raise ManagedOutputError("managed_output_marker_mismatch")
        namespace_manifest = validate_namespace_manifest(target)
        request = _read_object(target / "request.json")
        processing = _read_object(target / "processing_report.json")
        validation = _read_object(target / "validation_report.json")
        compatibility = _read_object(target / "compatibility.json")
        provenance = _read_object(target / "provenance.json")
    except (ManagedOutputError, NamespaceIntegrityError, StrictJsonError, OSError) as error:
        return {
            "status": "derivative_corrupt",
            "reason": getattr(error, "code", "zeroone_metadata_unreadable"),
            "detail": str(error)[:240],
        }
    if (
        request.get("schemaVersion") != REQUEST_SCHEMA_VERSION
        or processing.get("schemaVersion") != REPORT_SCHEMA_VERSION
        or validation.get("schemaVersion") != REPORT_SCHEMA_VERSION
        or compatibility.get("schemaVersion") != "closy.zeroone.compatibility.v1"
        or processing.get("profile") != PROFILE
        or compatibility.get("profile") != PROFILE
    ):
        return {"status": "derivative_incompatible", "reason": "zeroone_contract_version_mismatch"}
    if (
        processing.get("success") is not True
        or not _static_cook_executed(processing)
        or not _static_artifact_loaded(processing)
        or processing.get("canonicalAuthorityPreserved") is not True
        or processing.get("globalPhase10Complete") is not False
        or validation.get("success") is not True
        or validation.get("validatedNativeDerivative") is not True
    ):
        return {"status": "derivative_corrupt", "reason": "zeroone_success_claim_invalid"}
    authority_issue = _validate_authority(package, request, processing, provenance)
    if authority_issue is not None:
        return {"status": "derivative_corrupt", "reason": authority_issue}
    output_issue = _validate_outputs(target / "derivative", processing, provenance)
    if output_issue is not None:
        return {"status": "derivative_corrupt", "reason": output_issue}
    if (
        compatibility.get("canonicalDerivativeHash") != processing.get("canonicalDerivativeHash")
        or compatibility.get("fallbackRequired") is not True
        or compatibility.get("dynamicDeformationAvailable") is not False
        or provenance.get("zeroOneGitSha") != processing.get("zeroOneGitSha")
        or provenance.get("actualZeroOneStaticCookExecutedThisInvocation") is not True
        or provenance.get("actualZeroOneStaticArtifactLoaded") is not True
        or provenance.get("cacheValidated") is not True
        or provenance.get("actualZeroOneDynamicDeformationExecuted") is not False
        or provenance.get("actualZeroOneGpuRuntimeExecuted") is not False
        or provenance.get("actualZeroOneMobileRuntimeExecuted") is not False
        or provenance.get("globalPhase10Complete") is not False
    ):
        return {"status": "derivative_corrupt", "reason": "zeroone_provenance_linkage_invalid"}
    return {
        "status": "derivative_valid",
        "reason": "scoped_d0_cpu_static_derivative_valid",
        "profile": PROFILE,
        "canonicalDerivativeHash": processing.get("canonicalDerivativeHash"),
        "canonicalInventoryDigest": namespace_manifest["canonicalInventoryDigest"],
        "zeroOneGitSha": processing.get("zeroOneGitSha"),
        "outputCount": len(processing.get("outputHashes", [])),
    }


def _validate_authority(
    package: Path,
    request: dict[str, Any],
    processing: dict[str, Any],
    provenance: dict[str, Any],
) -> str | None:
    expected: dict[str, str] = {}
    fallback_seen = False
    for entry in request.get("canonicalAuthority", []):
        if not isinstance(entry, dict):
            return "zeroone_authority_entry_invalid"
        role = entry.get("role")
        relative = entry.get("path")
        declared = entry.get("sha256")
        if (
            not isinstance(role, str)
            or not isinstance(relative, str)
            or not isinstance(declared, str)
        ):
            return "zeroone_authority_entry_invalid"
        try:
            validate_package_relpath(relative)
        except ValueError:
            return "zeroone_authority_path_unsafe"
        if role in expected:
            return "zeroone_authority_role_duplicate"
        path = package / relative
        if not path.is_file() or path.is_symlink() or sha256_file(path) != declared:
            return "zeroone_canonical_authority_changed"
        expected[role] = declared
        fallback_seen = fallback_seen or role == "conventional_fallback"
    if not fallback_seen:
        return "zeroone_fallback_authority_missing"
    if (
        processing.get("canonicalAuthorityHashesBefore") != expected
        or processing.get("canonicalAuthorityHashesAfter") != expected
        or provenance.get("canonicalAuthorityHashes") != expected
    ):
        return "zeroone_authority_report_mismatch"
    return None


def _validate_outputs(
    derivative: Path, processing: dict[str, Any], provenance: dict[str, Any]
) -> str | None:
    rows = processing.get("outputHashes")
    if not isinstance(rows, list) or not rows:
        return "zeroone_output_hashes_missing"
    if provenance.get("outputHashes") != rows:
        return "zeroone_output_provenance_mismatch"
    expected_paths = {spec.path.removeprefix("derivative/") for spec in DERIVATIVE_SPECS}
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            return "zeroone_output_hash_entry_invalid"
        relative = row.get("path")
        declared = row.get("sha256")
        if not isinstance(relative, str) or not isinstance(declared, str):
            return "zeroone_output_hash_entry_invalid"
        try:
            validate_package_relpath(relative)
        except ValueError:
            return "zeroone_output_path_unsafe"
        if relative in seen:
            return "zeroone_output_path_duplicate"
        seen.add(relative)
        try:
            data = read_verified_regular_file(derivative, relative, maximum_bytes=67_108_864)
        except NamespaceIntegrityError as error:
            return error.code
        if hashlib.sha256(data).hexdigest() != declared:
            return "zeroone_derivative_hash_mismatch"
    if seen != expected_paths:
        return "zeroone_output_exact_inventory_mismatch"
    return None


def _static_cook_executed(report: dict[str, Any]) -> bool:
    explicit = report.get("actualZeroOneStaticCookExecutedThisInvocation")
    if isinstance(explicit, bool):
        return explicit
    # Legacy report compatibility never promotes a cache hit to a fresh cook.
    return (
        report.get("cacheState") == "miss"
        and report.get("actualZeroOneRuntimeExecuted") is True
        and report.get("actualZeroOneComputeExecuted") is True
    )


def _static_artifact_loaded(report: dict[str, Any]) -> bool:
    explicit = report.get("actualZeroOneStaticArtifactLoaded")
    if isinstance(explicit, bool):
        return explicit
    return (
        report.get("actualZeroOneRuntimeExecuted") is True
        and report.get("actualZeroOneComputeExecuted") is True
    )


def _read_object(path: Path) -> dict[str, Any]:
    return load_strict_json_object(path)
