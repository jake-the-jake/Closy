from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_io.managed_output import ManagedOutputError, read_managed_marker
from closy_forge.package_io.paths import validate_package_relpath
from closy_forge.security.strict_json import StrictJsonError, load_strict_json_object
from closy_forge.zeroone.dynamic_namespace import (
    DYNAMIC_PURPOSE,
    validate_dynamic_namespace_manifest,
)
from closy_forge.zeroone.dynamic_oracle import decode_document, decode_metadata
from closy_forge.zeroone.dynamic_request import (
    DYNAMIC_PROFILE,
    DYNAMIC_REPORT_SCHEMA_VERSION,
    static_derivative_identity_hash,
)
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
        children = {child.name for child in root.iterdir()}
        if children <= {
            "input-z1-v1",
            "input-z2-v1",
            "input-mt1-v2",
            "dynamic-d0-reference",
            "mechanical-reference-v2",
        }:
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


def inspect_zeroone_dynamic_namespace(package: Path) -> dict[str, Any]:
    target = package / "zeroone" / "dynamic-d0-reference"
    if not target.exists():
        return {"status": "not_present", "reason": "zeroone_dynamic_derivative_absent"}
    if not target.is_dir():
        return {
            "status": "derivative_incompatible",
            "reason": "dynamic_profile_directory_invalid",
        }
    try:
        marker = read_managed_marker(target)
        if (
            marker.get("owner") != "closy-forge"
            or marker.get("purpose") != DYNAMIC_PURPOSE
            or marker.get("kind") != "published"
        ):
            raise ManagedOutputError("managed_output_marker_mismatch")
        namespace_manifest = validate_dynamic_namespace_manifest(target)
        capability = _read_object(target / "capability.json")
        request = _read_object(target / "request_summary.json")
        report = _read_object(target / "dynamic_report.json")
        oracle = _read_object(target / "oracle_report.json")
        execution = _read_object(target / "execution.json")
        output_hashes = _read_object(target / "output_hashes.json")
        provenance = _read_object(target / "provenance.json")
        limitations = _read_object(target / "limitations.json")
        dynamic_bytes = read_verified_regular_file(
            target, "derivative/derivative.z1dyn", maximum_bytes=536_870_912
        )
        decoded = decode_document(dynamic_bytes, request=False)
        output_metadata = decode_metadata(decoded)
    except (
        ManagedOutputError,
        NamespaceIntegrityError,
        StrictJsonError,
        OSError,
        ValueError,
    ) as error:
        return {
            "status": "derivative_corrupt",
            "reason": getattr(error, "code", "zeroone_dynamic_metadata_unreadable"),
            "detail": str(error)[:240],
        }
    static = inspect_zeroone_namespace(package)
    if static.get("status") != "derivative_valid":
        return {"status": "derivative_incompatible", "reason": "dynamic_static_parent_invalid"}
    package_manifest = _read_object(package / "manifest.json")
    static_identity_document = _read_object(
        package / "zeroone" / "static-d0" / "derivative" / "derivative.json"
    )
    static_identity = static_derivative_identity_hash(static_identity_document)
    derivative_sha = hashlib.sha256(dynamic_bytes).hexdigest()
    if (
        capability.get("schemaVersion") != "closy.zeroone.dynamic-capability.v1"
        or capability.get("profile") != DYNAMIC_PROFILE
        or capability.get("scopedAcceptance") != "Z2-D0-single-LOD-reference"
        or capability.get("status") != "scoped_pass"
        or capability.get("actualCompiledDeformationExecuted") is not True
        or capability.get("pairingAuthority") != "local_candidate"
        or capability.get("durablePairedZ2Proven") is not False
        or capability.get("physicalQualityClaim") is not False
        or capability.get("productionClaim") is not False
    ):
        return {"status": "derivative_corrupt", "reason": "dynamic_capability_claim_invalid"}
    if (
        request.get("schemaVersion") != "closy.zeroone.dynamic-request-summary.v1"
        or request.get("profile") != DYNAMIC_PROFILE
        or request.get("requestSha256") != report.get("requestSha256")
        or request.get("canonicalPackageDigest") != package_manifest.get("canonicalPackageDigest")
        or request.get("staticDerivativeIdentitySha256") != static_identity
        or _contains_private_path(request)
    ):
        return {"status": "derivative_corrupt", "reason": "dynamic_request_linkage_invalid"}
    if (
        report.get("schemaVersion") != DYNAMIC_REPORT_SCHEMA_VERSION
        or report.get("profile") != DYNAMIC_PROFILE
        or report.get("success") is not True
        or "deform" not in report.get("actualCommandsExecuted", [])
        or report.get("dynamicOutputSha256") != derivative_sha
        or report.get("staticDerivativeIdentitySha256") != static_identity
        or report.get("scopedAcceptance", {}).get("compiledDeformationExecuted") is not True
        or report.get("scopedAcceptance", {}).get("physicalQualityClaim") is not False
    ):
        return {"status": "derivative_corrupt", "reason": "dynamic_process_report_invalid"}
    if (
        output_metadata.get("requestSha256") != request.get("requestSha256")
        or output_metadata.get("profile") != DYNAMIC_PROFILE
        or output_metadata.get("staticDerivativeIdentitySha256") != static_identity
        or output_metadata.get("canonicalPackageDigest")
        != package_manifest.get("canonicalPackageDigest")
    ):
        return {"status": "derivative_corrupt", "reason": "dynamic_binary_linkage_invalid"}
    if (
        oracle.get("schemaVersion") != "closy.zeroone.dynamic-forge-oracle.v1"
        or oracle.get("passed") is not True
        or oracle.get("requestSha256") != request.get("requestSha256")
        or oracle.get("outputSha256") != derivative_sha
        or oracle.get("inputSensitive") is not True
        or oracle.get("culling", {}).get("falseNegativeCount") != 0
        or oracle.get("physicalTruthClaimed") is not False
    ):
        return {"status": "derivative_corrupt", "reason": "dynamic_independent_oracle_invalid"}
    declared_outputs = output_hashes.get("outputs")
    if (
        output_hashes.get("schemaVersion") != "closy.zeroone.dynamic-output-hashes.v1"
        or not isinstance(declared_outputs, list)
        or declared_outputs != [{"path": "derivative/derivative.z1dyn", "sha256": derivative_sha}]
    ):
        return {"status": "derivative_corrupt", "reason": "dynamic_output_hashes_invalid"}
    if (
        execution.get("schemaVersion") != "closy.zeroone.dynamic-paired-execution.v1"
        or execution.get("requestSha256") != request.get("requestSha256")
        or execution.get("outputSha256") != derivative_sha
        or execution.get("deterministicDeleteRebuild") is not True
        or execution.get("inputSensitivityRun") is not True
        or execution.get("fallbackPreserved") is not True
        or execution.get("canonicalAuthorityPreserved") is not True
    ):
        return {"status": "derivative_corrupt", "reason": "dynamic_execution_evidence_invalid"}
    if (
        provenance.get("schemaVersion") != "closy.zeroone.dynamic-provenance.v1"
        or provenance.get("actualZeroOneDynamicDeformationExecuted") is not True
        or provenance.get("actualZeroOneGpuRuntimeExecuted") is not False
        or provenance.get("actualZeroOneMobileRuntimeExecuted") is not False
        or provenance.get("physicalTruth") is not False
        or provenance.get("durablePairedZ2Proven") is not False
        or provenance.get("dynamicOutputSha256") != derivative_sha
        or limitations.get("schemaVersion") != "closy.zeroone.dynamic-limitations.v1"
        or limitations.get("production") is not False
    ):
        return {"status": "derivative_corrupt", "reason": "dynamic_provenance_invalid"}
    return {
        "status": "derivative_valid",
        "reason": "scoped_dynamic_d0_reference_valid",
        "profile": DYNAMIC_PROFILE,
        "requestSha256": request.get("requestSha256"),
        "dynamicOutputSha256": derivative_sha,
        "frameCount": oracle.get("frameCount"),
        "renderVertexCount": oracle.get("renderVertexCount"),
        "triangleCount": oracle.get("triangleCount"),
        "inventoryDigest": namespace_manifest.get("inventoryDigest"),
        "pairingAuthority": "local_candidate",
        "durablePairedZ2Proven": False,
    }


def _contains_private_path(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_private_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_private_path(item) for item in value)
    if not isinstance(value, str):
        return False
    folded = value.replace("\\", "/").casefold()
    return ":/" in folded or folded.startswith("/") or "/users/" in folded


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
