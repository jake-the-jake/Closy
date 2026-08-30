from __future__ import annotations

import hashlib
import math
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_io.managed_output import (
    cleanup_managed_staging,
    create_managed_staging,
    publish_managed_staging,
)
from closy_forge.package_io.paths import assert_safe_child, posix_rel
from closy_forge.security.strict_json import loads_strict_json_object
from closy_forge.validation.validator import validate_package
from closy_forge.zeroone.dynamic_namespace import (
    DYNAMIC_DIRECTORY,
    DYNAMIC_PURPOSE,
    validate_dynamic_namespace_manifest,
    write_dynamic_namespace_manifest,
)
from closy_forge.zeroone.dynamic_request import (
    DEFAULT_CLIP_SCALE,
    DYNAMIC_PROFILE,
    DYNAMIC_REPORT_SCHEMA_VERSION,
    SCOPED_ACCEPTANCE_PROFILE,
    build_dynamic_request,
    write_dynamic_request,
)
from closy_forge.zeroone.mechanical_reference_oracle import audit_mechanical_reference_files
from closy_forge.zeroone.namespace import read_verified_regular_file
from closy_forge.zeroone.tool import (
    ZeroOneToolResolution,
    minimal_subprocess_environment,
    resolve_zeroone_tool,
)
from closy_forge.zeroone.validation import (
    inspect_zeroone_dynamic_namespace,
    inspect_zeroone_namespace,
)

DEFAULT_ZEROONE_DYNAMIC_SHA = "413aecd24434f90d89ad35c6a8f909de75df34c7"


@dataclass(frozen=True)
class ZeroOneDynamicIntegrationResult:
    status: str
    reason: str
    actual_dynamic_deformation_executed: bool
    deterministic_delete_rebuild: bool
    input_sensitivity_run: bool
    independent_oracle_passed: bool
    fallback_preserved: bool
    canonical_authority_preserved: bool
    packaged_derivative: str | None
    tool: ZeroOneToolResolution
    report: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "contractVersion": "closy.zeroone.dynamic-integration-result.v1",
            "status": self.status,
            "reason": self.reason,
            "actualZeroOneDynamicDeformationExecuted": self.actual_dynamic_deformation_executed,
            "deterministicDeleteRebuild": self.deterministic_delete_rebuild,
            "inputSensitivityRun": self.input_sensitivity_run,
            "independentForgeOraclePassed": self.independent_oracle_passed,
            "fallbackPreserved": self.fallback_preserved,
            "canonicalAuthorityPreserved": self.canonical_authority_preserved,
            "packagedDerivative": self.packaged_derivative,
            "tool": {
                "available": self.tool.available,
                "reason": self.tool.reason,
                "executableSha256": self.tool.executable_sha256,
                "version": self.tool.version,
                "trustedBuildRecord": self.tool.trusted_build_record,
            },
            "report": self.report,
        }


def integrate_zeroone_dynamic(
    *,
    package: Path,
    invocation_root: Path,
    closy_sha: str,
    executable: Path | None = None,
    trusted_build_record: Path | None = None,
    expected_executable_sha256: str | None = None,
    expected_zeroone_sha: str = DEFAULT_ZEROONE_DYNAMIC_SHA,
    publish: bool = True,
    replace_existing: bool = False,
    clip_scale: float = DEFAULT_CLIP_SCALE,
) -> ZeroOneDynamicIntegrationResult:
    package_root = package.resolve(strict=True)
    root = invocation_root.resolve(strict=True)
    assert_safe_child(root, package_root)
    before_files = _canonical_package_hashes(package_root)
    fallback_before = _fallback_hash(package_root)
    validation_before = validate_package(package_root)
    if not _validation_passed(validation_before):
        return _unexecuted(
            "request_invalid",
            "canonical_package_validation_failed",
            _resolve_tool(
                executable,
                trusted_build_record,
                expected_executable_sha256,
                expected_zeroone_sha,
            ),
            fallback_before is not None,
            {"packageValidation": validation_before},
        )
    static_audit = inspect_zeroone_namespace(package_root)
    if static_audit.get("status") != "derivative_valid":
        return _unexecuted(
            "request_invalid",
            "paired_static_derivative_invalid",
            _resolve_tool(
                executable,
                trusted_build_record,
                expected_executable_sha256,
                expected_zeroone_sha,
            ),
            fallback_before is not None,
            {"staticAudit": static_audit},
        )
    tool = _resolve_tool(
        executable,
        trusted_build_record,
        expected_executable_sha256,
        expected_zeroone_sha,
    )
    if not tool.available or tool.executable is None:
        return _unexecuted(
            "unavailable",
            tool.reason,
            tool,
            _fallback_hash(package_root) == fallback_before and fallback_before is not None,
            {"staticAudit": static_audit},
        )

    threshold_path = Path(__file__).resolve().parents[3] / "docs" / "threshold_registry_v1.json"
    threshold_registry = _object(threshold_path)
    threshold_profile = threshold_registry["profiles"]["closy.mechanical_reference.mt1.v2"]
    oracle_source_sha = sha256_file(Path(__file__).with_name("mechanical_reference_oracle.py"))
    if threshold_profile.get("oracleVersionHash") != oracle_source_sha:
        return _unexecuted(
            "request_invalid",
            "mechanical_reference_oracle_source_hash_mismatch",
            tool,
            _fallback_hash(package_root) == fallback_before and fallback_before is not None,
            {
                "declaredOracleVersionHash": threshold_profile.get("oracleVersionHash"),
                "observedOracleVersionHash": oracle_source_sha,
            },
        )
    thresholds = threshold_profile["metrics"]
    threshold_sha = sha256_file(threshold_path)
    with tempfile.TemporaryDirectory(prefix=".z1d-", dir=root) as temp_value:
        work = Path(temp_value)
        output = work / "output"
        request_path = work / "request.z1dr"
        bundle = build_dynamic_request(
            package=package_root,
            invocation_root=root,
            static_derivative=package_root / "zeroone" / "static-d0" / "derivative",
            output=output,
            closy_sha=closy_sha,
            clip_scale=clip_scale,
        )
        write_dynamic_request(request_path, bundle)
        inspect = _invoke(tool.executable, "inspect-dynamic", root, request_path)
        if inspect.get("success") is not True:
            return _failed(
                tool,
                package_root,
                fallback_before,
                before_files,
                "dynamic_inspect_failed",
                inspect,
            )
        first = _invoke(tool.executable, "deform", root, request_path, timeout_seconds=180)
        if not _dynamic_success(first):
            return _failed(
                tool,
                package_root,
                fallback_before,
                before_files,
                "dynamic_deform_failed",
                first,
            )
        validate = _invoke(
            tool.executable, "validate-dynamic", root, request_path, timeout_seconds=180
        )
        if validate.get("success") is not True:
            return _failed(
                tool,
                package_root,
                fallback_before,
                before_files,
                "dynamic_validate_failed",
                validate,
            )
        current = output / "current"
        first_bytes = read_verified_regular_file(
            current, "derivative.z1dyn", maximum_bytes=536_870_912
        )
        first_sha = hashlib.sha256(first_bytes).hexdigest()
        first_report = _object(current / "dynamic_report.json")
        cached = _invoke(tool.executable, "deform", root, request_path, timeout_seconds=180)
        cache_valid = (
            _dynamic_success(cached)
            and cached.get("cacheStatus") == "hit"
            and hashlib.sha256(
                read_verified_regular_file(current, "derivative.z1dyn", maximum_bytes=536_870_912)
            ).hexdigest()
            == first_sha
        )
        _remove_task_owned_tree(output / "current", output)
        _remove_task_owned_tree(output / "cache", output)
        rebuilt = _invoke(tool.executable, "deform", root, request_path, timeout_seconds=180)
        rebuilt_bytes = read_verified_regular_file(
            current, "derivative.z1dyn", maximum_bytes=536_870_912
        )
        rebuilt_sha = hashlib.sha256(rebuilt_bytes).hexdigest()
        deterministic = _dynamic_success(rebuilt) and first_bytes == rebuilt_bytes
        if not (cache_valid and deterministic):
            return _failed(
                tool,
                package_root,
                fallback_before,
                before_files,
                "dynamic_determinism_failed",
                {"first": first, "cached": cached, "rebuilt": rebuilt},
            )

        oracle = audit_mechanical_reference_files(
            request_path, current / "derivative.z1dyn", package_root
        )
        oracle["thresholdProfile"] = "closy.mechanical_reference.mt1.v2"
        oracle["thresholdRegistrySha256"] = threshold_sha
        oracle["thresholdRegistryMetrics"] = thresholds
        if oracle.get("passed") is not True:
            return _failed(
                tool,
                package_root,
                fallback_before,
                before_files,
                "dynamic_independent_oracle_failed",
                {"processor": rebuilt, "oracle": oracle},
            )

        sensitivity_output = work / "sensitivity-output"
        sensitivity_path = work / "sensitivity-request.z1dr"
        sensitivity_bundle = build_dynamic_request(
            package=package_root,
            invocation_root=root,
            static_derivative=package_root / "zeroone" / "static-d0" / "derivative",
            output=sensitivity_output,
            closy_sha=closy_sha,
            clip_scale=clip_scale * 0.5,
        )
        write_dynamic_request(sensitivity_path, sensitivity_bundle)
        sensitivity = _invoke(
            tool.executable, "deform", root, sensitivity_path, timeout_seconds=180
        )
        sensitivity_bytes = read_verified_regular_file(
            sensitivity_output / "current",
            "derivative.z1dyn",
            maximum_bytes=536_870_912,
        )
        input_sensitive = (
            _dynamic_success(sensitivity)
            and sensitivity_bundle.request_sha256 != bundle.request_sha256
            and hashlib.sha256(sensitivity_bytes).hexdigest() != rebuilt_sha
        )
        if not input_sensitive:
            return _failed(
                tool,
                package_root,
                fallback_before,
                before_files,
                "dynamic_input_sensitivity_failed",
                {"primary": rebuilt, "sensitivity": sensitivity},
            )

        fallback_preserved = (
            fallback_before is not None and _fallback_hash(package_root) == fallback_before
        )
        canonical_preserved = _canonical_package_hashes(package_root) == before_files
        if not (fallback_preserved and canonical_preserved):
            return _failed(
                tool,
                package_root,
                fallback_before,
                before_files,
                "dynamic_canonical_authority_changed",
                rebuilt,
            )
        packaged: Path | None = None
        if publish:
            packaged = _publish_dynamic(
                package=package_root,
                source=current,
                bundle=bundle,
                processor_report=first_report,
                processor_validation=validate,
                oracle=oracle,
                tool=tool,
                closy_sha=closy_sha,
                threshold_registry_sha256=threshold_sha,
                static_audit=static_audit,
                deterministic=deterministic,
                cache_valid=cache_valid,
                input_sensitive=input_sensitive,
                fallback_preserved=fallback_preserved,
                canonical_preserved=canonical_preserved,
                replace_existing=replace_existing,
            )
            packaged_audit = inspect_zeroone_dynamic_namespace(package_root)
            validation_after = validate_package(package_root)
            if packaged_audit.get("status") != "derivative_valid" or not _validation_passed(
                validation_after
            ):
                return _failed(
                    tool,
                    package_root,
                    fallback_before,
                    before_files,
                    "packaged_dynamic_validation_failed",
                    {
                        "dynamicAudit": packaged_audit,
                        "packageValidation": validation_after,
                    },
                )
        return ZeroOneDynamicIntegrationResult(
            status="executed",
            reason="scoped_mt1_clean_reference_motion_executed",
            actual_dynamic_deformation_executed=True,
            deterministic_delete_rebuild=deterministic,
            input_sensitivity_run=input_sensitive,
            independent_oracle_passed=True,
            fallback_preserved=fallback_preserved,
            canonical_authority_preserved=canonical_preserved,
            packaged_derivative=(
                packaged.relative_to(package_root).as_posix() if packaged is not None else None
            ),
            tool=tool,
            report={
                "requestSha256": bundle.request_sha256,
                "dynamicOutputSha256": rebuilt_sha,
                "inspect": _bounded_report(inspect),
                "deform": _bounded_report(first),
                "cacheHit": _bounded_report(cached),
                "deleteRebuild": _bounded_report(rebuilt),
                "validate": _bounded_report(validate),
                "inputSensitivity": _bounded_report(sensitivity),
                "oracle": oracle,
                "pairingAuthority": "authenticated_exact_head_workflow_artifact",
                "durablePairedZ2Proven": False,
            },
        )


def _publish_dynamic(
    *,
    package: Path,
    source: Path,
    bundle: Any,
    processor_report: dict[str, Any],
    processor_validation: dict[str, Any],
    oracle: dict[str, Any],
    tool: ZeroOneToolResolution,
    closy_sha: str,
    threshold_registry_sha256: str,
    static_audit: dict[str, Any],
    deterministic: bool,
    cache_valid: bool,
    input_sensitive: bool,
    fallback_preserved: bool,
    canonical_preserved: bool,
    replace_existing: bool,
) -> Path:
    namespace = package / "zeroone"
    target = namespace / DYNAMIC_DIRECTORY
    assert_safe_child(package, target)
    if target.exists() and not replace_existing:
        raise FileExistsError(f"optional ZeroOne dynamic derivative already exists: {target}")
    namespace.mkdir(parents=True, exist_ok=True)
    staging = create_managed_staging(target, allowed_root=namespace, purpose=DYNAMIC_PURPOSE)
    try:
        derivative = read_verified_regular_file(
            source, "derivative.z1dyn", maximum_bytes=536_870_912
        )
        derivative_target = staging / "derivative" / "derivative.z1dyn"
        derivative_target.parent.mkdir(parents=True, exist_ok=True)
        with derivative_target.open("xb") as stream:
            stream.write(derivative)
        output_sha = hashlib.sha256(derivative).hexdigest()
        request_summary = {
            "schemaVersion": "closy.zeroone.dynamic-request-summary.v1",
            "profile": DYNAMIC_PROFILE,
            "garmentId": bundle.metadata["garmentId"],
            "requestSha256": bundle.request_sha256,
            "canonicalPackageDigest": bundle.metadata["canonicalPackageDigest"],
            "staticDerivativeIdentitySha256": bundle.metadata["staticDerivativeIdentitySha256"],
            "staticClusterInventorySha256": bundle.metadata["staticClusterInventorySha256"],
            "simulationTopologySha256": bundle.metadata["simulationTopologySha256"],
            "renderTopologySha256": bundle.metadata["renderTopologySha256"],
            "bindingContractSha256": bundle.metadata["bindingContractSha256"],
            "sourceToClusterMapSha256": bundle.metadata["sourceToClusterMapSha256"],
            "coordinateConventionId": bundle.metadata["coordinateConventionId"],
            "unitScaleMetres": bundle.metadata["unitScaleMetres"],
            "frameCount": bundle.clip_inventory["frameCount"],
            "clipPayloadSha256": bundle.clip_inventory["clipPayloadSha256"],
            "provenanceClassification": bundle.metadata["provenance"]["classification"],
            "physicalTruth": False,
            "privatePathsPersisted": False,
        }
        capability = {
            "schemaVersion": "closy.zeroone.dynamic-capability.v1",
            "profile": DYNAMIC_PROFILE,
            "scopedAcceptance": SCOPED_ACCEPTANCE_PROFILE,
            "status": "clean_reference_pass",
            "actualCompiledDeformationExecuted": True,
            "independentForgeOraclePassed": True,
            "deterministicDeleteRebuild": deterministic,
            "inputSensitivityPassed": input_sensitive,
            "fallbackPreserved": fallback_preserved,
            "canonicalAuthorityPreserved": canonical_preserved,
            "pairingAuthority": "authenticated_exact_head_workflow_artifact",
            "durablePairedZ2Proven": False,
            "globalZ2": "partial",
            "phase11": "partial",
            "dynamicMultiLod": "not_run",
            "gpu": "not_run",
            "mobile": "not_run",
            "physicalQualityClaim": False,
            "productionClaim": False,
            "thresholdRegistrySha256": threshold_registry_sha256,
        }
        execution = {
            "schemaVersion": "closy.zeroone.dynamic-paired-execution.v1",
            "closyGitSha": closy_sha,
            "zeroOneGitSha": processor_report.get("zeroOneGitSha"),
            "zeroOneExecutableSha256": tool.executable_sha256,
            "compiler": processor_report.get("compiler"),
            "buildConfiguration": processor_report.get("buildConfiguration"),
            "sourceClean": processor_report.get("zeroOneBuildDirty") is False,
            "headless": tool.version.get("headless") if tool.version else None,
            "cpuOnly": tool.version.get("cpuOnly") if tool.version else None,
            "requestSha256": bundle.request_sha256,
            "outputSha256": output_sha,
            "commands": ["inspect-dynamic", "deform", "validate-dynamic", "deform"],
            "cacheHitValidated": cache_valid,
            "deterministicDeleteRebuild": deterministic,
            "inputSensitivityRun": input_sensitive,
            "fallbackPreserved": fallback_preserved,
            "canonicalAuthorityPreserved": canonical_preserved,
            "environmentProfile": (
                "windows-msvc-release-headless-cpu-authenticated-workflow-artifact"
            ),
            "crossRepositoryWorkflowAuthorityAvailable": True,
        }
        provenance = {
            "schemaVersion": "closy.zeroone.dynamic-provenance.v1",
            "closyGitSha": closy_sha,
            "zeroOneGitSha": processor_report.get("zeroOneGitSha"),
            "zeroOneExecutableSha256": tool.executable_sha256,
            "requestSha256": bundle.request_sha256,
            "dynamicOutputSha256": output_sha,
            "staticDerivativeIdentitySha256": bundle.metadata["staticDerivativeIdentitySha256"],
            "staticNamespaceInventoryDigest": static_audit.get("canonicalInventoryDigest"),
            "actualZeroOneDynamicDeformationExecuted": True,
            "actualZeroOneGpuRuntimeExecuted": False,
            "actualZeroOneMobileRuntimeExecuted": False,
            "physicalTruth": False,
            "pairingAuthority": "authenticated_exact_head_workflow_artifact",
            "durablePairedZ2Proven": False,
            "canonicalAuthorityMutated": False,
        }
        limitations = {
            "schemaVersion": "closy.zeroone.dynamic-limitations.v1",
            "singleLodReferenceOnly": True,
            "multiLod": False,
            "gpu": False,
            "mobile": False,
            "physicalClothTruth": False,
            "solverDrivenPhysicalQuality": False,
            "allFamilyBreadth": False,
            "currentMaster": False,
            "production": False,
            "durableCrossRepositoryPairing": False,
            "notes": [
                "mechanical_reference_clip_not_physical_motion_truth",
                "authenticated_zeroone_exact_head_artifact_paired_to_closy_candidate",
                "representative_tshirt_d0_only",
            ],
        }
        write_canonical_json(staging / "capability.json", capability)
        write_canonical_json(staging / "request_summary.json", request_summary)
        write_canonical_json(staging / "dynamic_report.json", processor_report)
        write_canonical_json(staging / "clip_inventory.json", bundle.clip_inventory)
        write_canonical_json(staging / "influence_lineage.json", bundle.influence_inventory)
        write_canonical_json(
            staging / "bounds.json",
            {
                "schemaVersion": "closy.zeroone.dynamic-bounds-audit.v1",
                "clusterBoundContainmentFailures": oracle["clusterBoundContainmentFailures"],
                "parentBoundContainmentFailures": oracle["parentBoundContainmentFailures"],
                "culling": oracle["culling"],
                "processorBoundsAudit": processor_report.get("boundsAudit"),
                "passed": oracle["boundsPassed"],
            },
        )
        write_canonical_json(
            staging / "normal_tangent.json",
            {
                "schemaVersion": "closy.zeroone.dynamic-normal-tangent-audit.v1",
                "maximumNormalAngleDegrees": oracle["maximumNormalAngleDegrees"],
                "maximumTangentAngleDegrees": oracle["maximumTangentAngleDegrees"],
                "tangentHandednessMismatchCount": oracle["tangentHandednessMismatchCount"],
                "passed": oracle["normalTangentPassed"],
            },
        )
        write_canonical_json(staging / "oracle_report.json", oracle)
        write_canonical_json(staging / "execution.json", execution)
        write_canonical_json(
            staging / "output_hashes.json",
            {
                "schemaVersion": "closy.zeroone.dynamic-output-hashes.v1",
                "outputs": [{"path": "derivative/derivative.z1dyn", "sha256": output_sha}],
            },
        )
        write_canonical_json(staging / "provenance.json", provenance)
        write_canonical_json(staging / "limitations.json", limitations)
        write_dynamic_namespace_manifest(staging)
        validate_dynamic_namespace_manifest(staging)
        publish_managed_staging(
            staging,
            target,
            allowed_root=namespace,
            purpose=DYNAMIC_PURPOSE,
            force=replace_existing,
        )
    except BaseException:
        cleanup_managed_staging(staging, allowed_root=namespace, purpose=DYNAMIC_PURPOSE)
        raise
    validate_dynamic_namespace_manifest(target)
    return target


def _evaluate_thresholds(
    raw: dict[str, Any], thresholds: dict[str, Any], threshold_sha: str
) -> dict[str, Any]:
    normal_angle = _vector_error_angle(float(raw["maximumNormalError"]))
    tangent_angle = _vector_error_angle(float(raw["maximumTangentError"]))
    bounds_passed = (
        raw["clusterBoundContainmentFailures"] == 0 and raw["parentBoundContainmentFailures"] == 0
    )
    normal_tangent_passed = (
        normal_angle <= float(thresholds["maximumNormalAngleDegrees"])
        and tangent_angle <= float(thresholds["maximumTangentAngleDegrees"])
        and raw["tangentHandednessMismatchCount"] == 0
    )
    threshold_results = {
        "minimumFrameCount": raw["frameCount"] >= int(thresholds["minimumFrameCount"]),
        "maximumPositionErrorMeters": raw["maximumPositionErrorMetres"]
        <= float(thresholds["maximumPositionErrorMeters"]),
        "p95PositionErrorMeters": raw["p95PositionErrorMetres"]
        <= float(thresholds["p95PositionErrorMeters"]),
        "restIdentity": raw["restIdentityMaximumErrorMetres"]
        <= float(thresholds["maximumPositionErrorMeters"]),
        "inputSensitivity": raw["inputSensitive"] is True,
        "normalTangent": normal_tangent_passed,
        "bounds": bounds_passed,
        "culling": raw["culling"]["falseNegativeCount"]
        <= int(thresholds["cullingFalseNegativeCount"]),
        "temporalInversion": raw["trueTemporalInversionCount"] == 0,
        "denseSelfIntersection": max(raw["denseSelfIntersectionCountByFrame"]) == 0,
        "simulationReconstructionSelfIntersection": max(
            raw["simulationSelfIntersectionCountByFrame"]
        )
        == 0,
        "semanticOpeningOrder": raw["semanticOpeningOrderPreserved"] is True,
    }
    return {
        **raw,
        "schemaVersion": "closy.zeroone.dynamic-forge-oracle.v1",
        "thresholdProfile": "closy.dynamic_reference.z2.v1",
        "thresholdRegistrySha256": threshold_sha,
        "maximumNormalAngleDegrees": normal_angle,
        "maximumTangentAngleDegrees": tangent_angle,
        "boundsPassed": bounds_passed,
        "normalTangentPassed": normal_tangent_passed,
        "thresholdResults": threshold_results,
        "physicalTruthClaimed": False,
        "passed": raw.get("passed") is True and all(threshold_results.values()),
    }


def _vector_error_angle(error: float) -> float:
    return math.degrees(2.0 * math.asin(min(1.0, max(0.0, error) * 0.5)))


def _resolve_tool(
    executable: Path | None,
    trusted_build_record: Path | None,
    expected_executable_sha256: str | None,
    expected_zeroone_sha: str,
) -> ZeroOneToolResolution:
    return resolve_zeroone_tool(
        executable,
        trusted_build_record=trusted_build_record,
        expected_executable_sha256=expected_executable_sha256,
        expected_source_sha=expected_zeroone_sha,
        capability="dynamic",
    )


def _invoke(
    executable: Path,
    command: str,
    root: Path,
    request: Path,
    *,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            str(executable),
            command,
            "--request",
            str(request),
            "--root",
            str(root),
            "--timeout-ms",
            str(timeout_seconds * 1000),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds + 15,
        cwd=root,
        env=minimal_subprocess_environment(),
    )
    report = _last_json_object(completed.stdout)
    report["observedReturnCode"] = completed.returncode
    if completed.stderr.strip():
        report["stderrPresent"] = True
    return report


def _last_json_object(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError("zeroone_dynamic_tool_produced_no_json")
    return loads_strict_json_object(lines[-1])


def _dynamic_success(report: dict[str, Any]) -> bool:
    return (
        report.get("schemaVersion") == DYNAMIC_REPORT_SCHEMA_VERSION
        and report.get("success") is True
        and report.get("profile") == DYNAMIC_PROFILE
        and report.get("processorMechanicalValidation", {}).get("compiledDeformationExecuted")
        is True
        and report.get("processorMechanicalValidation", {}).get("passed") is True
    )


def _remove_task_owned_tree(path: Path, allowed_root: Path) -> None:
    assert_safe_child(allowed_root, path)
    if not path.exists():
        return
    if path.is_symlink() or not path.is_dir():
        raise ValueError("dynamic_cleanup_target_invalid")
    for candidate in path.rglob("*"):
        metadata = candidate.stat(follow_symlinks=False)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(metadata.st_mode) or bool(
            getattr(metadata, "st_file_attributes", 0) & reparse
        ):
            raise ValueError("dynamic_cleanup_link_rejected")
    shutil.rmtree(path)


def _canonical_package_hashes(package: Path) -> dict[str, str]:
    return {
        posix_rel(path, package): sha256_file(path)
        for path in sorted(package.rglob("*"))
        if path.is_file()
        and not path.is_symlink()
        and not posix_rel(path, package).startswith("zeroone/")
    }


def _fallback_hash(package: Path) -> str | None:
    path = package / "render" / "fallback.glb"
    return sha256_file(path) if path.is_file() else None


def _validation_passed(report: dict[str, Any]) -> bool:
    counts = report.get("counts", {})
    return int(counts.get("error", 0)) == 0 and int(counts.get("fatal", 0)) == 0


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"dynamic_json_object_required:{path.name}")
    return value


def _bounded_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key)
        for key in (
            "success",
            "exitCode",
            "diagnostic",
            "cacheStatus",
            "requestSha256",
            "dynamicOutputSha256",
            "actualCommandsExecuted",
            "deformationMedianMs",
            "deformationP95Ms",
            "frameThroughputPerSecond",
            "peakMemoryBytes",
            "timingsMs",
            "validatedDynamicDerivative",
        )
    }


def _unexecuted(
    status: str,
    reason: str,
    tool: ZeroOneToolResolution,
    fallback_preserved: bool,
    report: dict[str, Any],
) -> ZeroOneDynamicIntegrationResult:
    return ZeroOneDynamicIntegrationResult(
        status,
        reason,
        False,
        False,
        False,
        False,
        fallback_preserved,
        fallback_preserved,
        None,
        tool,
        report,
    )


def _failed(
    tool: ZeroOneToolResolution,
    package: Path,
    fallback_before: str | None,
    before_files: dict[str, str],
    reason: str,
    report: dict[str, Any],
) -> ZeroOneDynamicIntegrationResult:
    fallback_preserved = fallback_before is not None and _fallback_hash(package) == fallback_before
    canonical_preserved = _canonical_package_hashes(package) == before_files
    return ZeroOneDynamicIntegrationResult(
        "process_failed",
        reason,
        False,
        False,
        False,
        False,
        fallback_preserved,
        canonical_preserved,
        None,
        tool,
        report,
    )
