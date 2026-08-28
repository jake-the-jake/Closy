from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_io.paths import validate_package_relpath
from closy_forge.zeroone.tool import PROFILE, REPORT_SCHEMA_VERSION, REQUEST_SCHEMA_VERSION


def inspect_zeroone_namespace(package: Path) -> dict[str, Any]:
    root = package / "zeroone"
    if not root.exists():
        return {"status": "not_present", "reason": "zeroone_derivative_absent"}
    target = root / "static-d0"
    if not target.is_dir():
        return {"status": "derivative_incompatible", "reason": "static_profile_directory_missing"}
    if any(path.is_symlink() for path in root.rglob("*")):
        return {"status": "derivative_corrupt", "reason": "zeroone_namespace_contains_symlink"}
    required = (
        "request.json",
        "processing_report.json",
        "validation_report.json",
        "compatibility.json",
        "provenance.json",
        "derivative/artifact.geomesh",
        "derivative/native/cooked_asset.z1ddc",
        "derivative/native/page_packs/manifest.json",
        "derivative/native/page_packs/packs.bin",
        "derivative/garment/stitch_rows.json",
        "derivative/lod.json",
        "derivative/materials.json",
    )
    missing = [relative for relative in required if not (target / relative).is_file()]
    if missing:
        return {
            "status": "derivative_corrupt",
            "reason": "zeroone_derivative_file_missing",
            "missing": missing,
        }
    try:
        request = _read_object(target / "request.json")
        processing = _read_object(target / "processing_report.json")
        validation = _read_object(target / "validation_report.json")
        compatibility = _read_object(target / "compatibility.json")
        provenance = _read_object(target / "provenance.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return {
            "status": "derivative_corrupt",
            "reason": "zeroone_metadata_unreadable",
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
        or processing.get("actualZeroOneRuntimeExecuted") is not True
        or processing.get("actualZeroOneComputeExecuted") is not True
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
        or provenance.get("actualZeroOneRuntimeExecuted") is not True
        or provenance.get("actualZeroOneComputeExecuted") is not True
        or provenance.get("globalPhase10Complete") is not False
    ):
        return {"status": "derivative_corrupt", "reason": "zeroone_provenance_linkage_invalid"}
    return {
        "status": "derivative_valid",
        "reason": "scoped_d0_cpu_static_derivative_valid",
        "profile": PROFILE,
        "canonicalDerivativeHash": processing.get("canonicalDerivativeHash"),
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
        path = package / relative
        if not path.is_file() or sha256_file(path) != declared:
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
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
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
        path = derivative / relative
        if not path.is_file() or sha256_file(path) != declared:
            return "zeroone_derivative_hash_mismatch"
    return None


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path.name}")
    return value
