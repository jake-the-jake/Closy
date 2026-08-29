from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_io.managed_output import (
    cleanup_managed_staging,
    create_managed_staging,
    publish_managed_staging,
)
from closy_forge.package_io.paths import assert_safe_child, posix_rel
from closy_forge.security.strict_json import StrictJsonError, loads_strict_json_object
from closy_forge.validation.validator import validate_package
from closy_forge.zeroone.dynamic_processing_surface import prepare_dynamic_processing_surface
from closy_forge.zeroone.namespace import (
    copy_verified_derivative,
    validate_namespace_manifest,
    write_namespace_manifest,
)
from closy_forge.zeroone.request import authority_hashes, build_zeroone_request
from closy_forge.zeroone.tool import (
    PINNED_ZEROONE_SOURCE_SHA,
    REPORT_SCHEMA_VERSION,
    ZeroOneToolResolution,
    minimal_subprocess_environment,
    resolve_zeroone_tool,
)


@dataclass(frozen=True)
class ZeroOneIntegrationResult:
    status: str
    reason: str
    actual_static_cook_executed: bool
    actual_static_artifact_loaded: bool
    cache_validated: bool
    fallback_preserved: bool
    canonical_authority_preserved: bool
    deterministic_derivative: bool
    packaged_derivative: str | None
    tool: ZeroOneToolResolution
    report: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "schemaVersion": 2,
            "contractVersion": "closy.zeroone.integration-result.v2",
            "status": self.status,
            "reason": self.reason,
            "actualZeroOneStaticCookExecutedThisInvocation": self.actual_static_cook_executed,
            "actualZeroOneStaticArtifactLoaded": self.actual_static_artifact_loaded,
            "cacheValidated": self.cache_validated,
            "actualZeroOneDynamicDeformationExecuted": False,
            "actualZeroOneGpuRuntimeExecuted": False,
            "actualZeroOneMobileRuntimeExecuted": False,
            "fallbackPreserved": self.fallback_preserved,
            "canonicalAuthorityPreserved": self.canonical_authority_preserved,
            "deterministicDerivative": self.deterministic_derivative,
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


def integrate_zeroone_static(
    *,
    package: Path,
    invocation_root: Path,
    closy_sha: str,
    executable: Path | None = None,
    trusted_build_record: Path | None = None,
    expected_executable_sha256: str | None = None,
    expected_zeroone_sha: str = PINNED_ZEROONE_SOURCE_SHA,
    publish: bool = True,
    replace_existing: bool = False,
    dynamic_compatible_surface: bool = False,
) -> ZeroOneIntegrationResult:
    package_root = package.resolve(strict=True)
    root = invocation_root.resolve(strict=True)
    assert_safe_child(root, package_root)
    dynamic_processing_audit: dict[str, Any] | None = None
    if dynamic_compatible_surface:
        dynamic_processing_audit = prepare_dynamic_processing_surface(
            package_root, replace_existing=replace_existing
        )
    before_files = _canonical_package_hashes(package_root)
    fallback_before = _fallback_hash(package_root)
    validation_before = validate_package(package_root)
    if not _validation_passed(validation_before):
        return _unexecuted(
            "request_invalid",
            "canonical_package_validation_failed",
            resolve_zeroone_tool(
                executable,
                trusted_build_record=trusted_build_record,
                expected_executable_sha256=expected_executable_sha256,
                expected_source_sha=expected_zeroone_sha,
            ),
            fallback_before is not None,
            {"packageValidation": validation_before},
        )

    tool = resolve_zeroone_tool(
        executable,
        trusted_build_record=trusted_build_record,
        expected_executable_sha256=expected_executable_sha256,
        expected_source_sha=expected_zeroone_sha,
    )
    if not tool.available or tool.executable is None:
        return _unexecuted(
            "unavailable",
            tool.reason,
            tool,
            _fallback_hash(package_root) == fallback_before and fallback_before is not None,
            {"packageValidation": validation_before},
        )

    # ZeroOne cache paths contain two SHA-256 directory names. Keep task-owned
    # staging names short enough for legacy Win32 path handling.
    with tempfile.TemporaryDirectory(prefix=".z1-", dir=root) as temp_value:
        work = Path(temp_value)
        run_a = _execute_clean_run(
            tool.executable,
            root,
            package_root,
            work / "a",
            work / "a.json",
            closy_sha,
            "closy-phase10-clean-a",
        )
        if not run_a["success"]:
            return _failed(
                tool, package_root, fallback_before, before_files, "process_failed", run_a
            )
        run_a_hit = _invoke(tool.executable, "cook", root, run_a["requestPath"])
        if not _successful_compute_report(run_a_hit) or run_a_hit.get("cacheState") != "hit":
            return _failed(
                tool,
                package_root,
                fallback_before,
                before_files,
                "cache_hit_validation_failed",
                run_a_hit,
            )
        resume_run = _execute_resume_run(
            tool.executable,
            root,
            package_root,
            work / "resume",
            work / "resume.json",
            closy_sha,
        )
        if not resume_run["success"]:
            return _failed(
                tool,
                package_root,
                fallback_before,
                before_files,
                "resume_validation_failed",
                resume_run,
            )
        run_b = _execute_clean_run(
            tool.executable,
            root,
            package_root,
            work / "b",
            work / "b.json",
            closy_sha,
            "closy-phase10-clean-b",
        )
        if not run_b["success"]:
            return _failed(
                tool, package_root, fallback_before, before_files, "process_failed", run_b
            )

        cook_a = run_a["cook"]
        cook_b = run_b["cook"]
        hashes_a = _declared_hashes(cook_a)
        hashes_b = _declared_hashes(cook_b)
        hashes_resumed = _declared_hashes(resume_run["resume"])
        deterministic = (
            bool(hashes_a)
            and hashes_a == hashes_b
            and hashes_a == hashes_resumed
            and cook_a.get("canonicalDerivativeHash") == cook_b.get("canonicalDerivativeHash")
            and cook_a.get("canonicalDerivativeHash")
            == resume_run["resume"].get("canonicalDerivativeHash")
            and cook_a.get("canonicalDerivativeHash") == run_a_hit.get("canonicalDerivativeHash")
        )
        authority_before = authority_hashes(run_a["request"])
        authority_preserved = all(
            report.get("canonicalAuthorityHashesBefore") == authority_before
            and report.get("canonicalAuthorityHashesAfter") == authority_before
            and report.get("canonicalAuthorityPreserved") is True
            for report in (
                cook_a,
                run_a_hit,
                cook_b,
                resume_run["resume"],
                run_a["validate"],
                run_b["validate"],
                resume_run["validate"],
            )
        )
        actual_static_cook = all(_static_cook_executed(report) for report in (cook_a, cook_b))
        actual_static_artifact_loaded = all(
            _static_artifact_loaded(report)
            for report in (cook_a, run_a_hit, cook_b, resume_run["resume"])
        )
        cache_validated = (
            run_a_hit.get("cacheState") == "hit"
            and not _static_cook_executed(run_a_hit)
            and _static_artifact_loaded(run_a_hit)
        )
        if not (
            deterministic
            and authority_preserved
            and actual_static_cook
            and actual_static_artifact_loaded
            and cache_validated
        ):
            return _failed(
                tool,
                package_root,
                fallback_before,
                before_files,
                "derivative_acceptance_failed",
                {
                    "deterministicDerivative": deterministic,
                    "canonicalAuthorityPreserved": authority_preserved,
                    "actualZeroOneStaticCookExecutedThisInvocation": actual_static_cook,
                    "actualZeroOneStaticArtifactLoaded": actual_static_artifact_loaded,
                    "cacheValidated": cache_validated,
                },
            )

        packaged = None
        if publish:
            packaged_path = _publish_derivative(
                package_root,
                run_a["output"] / "current",
                run_a["request"],
                run_a,
                run_a_hit,
                resume_run,
                tool,
                replace_existing=replace_existing,
            )
            packaged = posix_rel(packaged_path, package_root)

    after_files = _canonical_package_hashes(package_root)
    fallback_after = _fallback_hash(package_root)
    validation_after = validate_package(package_root)
    package_preserved = before_files == after_files
    fallback_preserved = fallback_before is not None and fallback_before == fallback_after
    accepted = (
        package_preserved
        and fallback_preserved
        and _validation_passed(validation_after)
        and deterministic
        and authority_preserved
    )
    summary = {
        "profile": cook_a.get("profile"),
        "zeroOneGitSha": cook_a.get("zeroOneGitSha"),
        "executableSha256": tool.executable_sha256,
        "canonicalAuthorityHashes": authority_before,
        "canonicalDerivativeHash": cook_a.get("canonicalDerivativeHash"),
        "outputHashes": cook_a.get("outputHashes"),
        "assetAudit": {
            key: cook_a.get(key)
            for key in (
                "meshCount",
                "primitiveCount",
                "vertexCount",
                "triangleCount",
                "materialCount",
                "panelCount",
                "seamCount",
                "openingCount",
                "clusterCount",
                "hierarchyNodeCount",
                "pageCount",
                "pagePackCount",
                "stitchRowCount",
            )
        },
        "cleanRunA": _bounded_report(run_a),
        "cacheHitRun": _bounded_report(run_a_hit),
        "resumeRun": _bounded_resume_report(resume_run),
        "cleanRunB": _bounded_report(run_b),
        "canonicalPackageBytesUnchanged": package_preserved,
        "validationBefore": validation_before,
        "validationAfter": validation_after,
        "globalPhase10Complete": False,
        "remainingBlockers": cook_a.get("remainingPhase10Blockers", []),
    }
    if dynamic_processing_audit is not None:
        summary["dynamicCompatibleProcessingSurface"] = dynamic_processing_audit
    return ZeroOneIntegrationResult(
        "valid" if accepted else "derivative_corrupt",
        "scoped_d0_cpu_static_derivative_valid" if accepted else "post_package_validation_failed",
        actual_static_cook,
        actual_static_artifact_loaded,
        cache_validated,
        fallback_preserved,
        authority_preserved and package_preserved,
        deterministic,
        packaged,
        tool,
        summary,
    )


def _execute_clean_run(
    executable: Path,
    invocation_root: Path,
    package: Path,
    output: Path,
    request_path: Path,
    closy_sha: str,
    label: str,
) -> dict[str, Any]:
    request = build_zeroone_request(
        invocation_root=invocation_root,
        package=package,
        output=output,
        closy_sha=closy_sha,
        request_label=label,
    )
    write_canonical_json(request_path, request)
    inspect = _invoke(executable, "inspect", invocation_root, request_path)
    if inspect.get("success") is not True:
        return {"success": False, "stage": "inspect", "report": inspect}
    cook = _invoke(executable, "cook", invocation_root, request_path)
    if not _successful_compute_report(cook):
        return {"success": False, "stage": "cook", "report": cook}
    validate = _invoke(executable, "validate", invocation_root, request_path)
    if validate.get("success") is not True or validate.get("validatedNativeDerivative") is not True:
        return {"success": False, "stage": "validate", "report": validate}
    return {
        "success": True,
        "request": request,
        "requestPath": request_path,
        "output": output,
        "inspect": inspect,
        "cook": cook,
        "validate": validate,
    }


def _execute_resume_run(
    executable: Path,
    invocation_root: Path,
    package: Path,
    output: Path,
    request_path: Path,
    closy_sha: str,
) -> dict[str, Any]:
    request = build_zeroone_request(
        invocation_root=invocation_root,
        package=package,
        output=output,
        closy_sha=closy_sha,
        request_label="closy-phase10-interrupted-resume",
    )
    write_canonical_json(request_path, request)
    inspect = _invoke(executable, "inspect", invocation_root, request_path)
    if inspect.get("success") is not True:
        return {"success": False, "stage": "inspect", "report": inspect}
    interrupted = _invoke(
        executable,
        "cook",
        invocation_root,
        request_path,
        extra_args=("--fault-test", "before-publication"),
    )
    if (
        interrupted.get("success") is not False
        or interrupted.get("diagnostic") != "E_INJECTED_INTERRUPTION_BEFORE_PUBLICATION"
    ):
        return {"success": False, "stage": "interruption", "report": interrupted}
    resumed = _invoke(executable, "resume", invocation_root, request_path)
    if not _successful_compute_report(resumed) or resumed.get("resumeState") != "matched":
        return {"success": False, "stage": "resume", "report": resumed}
    validate = _invoke(executable, "validate", invocation_root, request_path)
    if validate.get("success") is not True or validate.get("validatedNativeDerivative") is not True:
        return {"success": False, "stage": "validate", "report": validate}
    return {
        "success": True,
        "request": request,
        "requestPath": request_path,
        "output": output,
        "inspect": inspect,
        "interrupted": interrupted,
        "resume": resumed,
        "validate": validate,
    }


def _invoke(
    executable: Path,
    command: str,
    root: Path,
    request: Path,
    *,
    extra_args: tuple[str, ...] = (),
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            str(executable),
            command,
            "--root",
            str(root),
            "--request",
            str(request),
            *extra_args,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
        cwd=root,
        env=minimal_subprocess_environment(),
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return {
            "schemaVersion": REPORT_SCHEMA_VERSION,
            "success": False,
            "exitCode": completed.returncode,
            "diagnostic": "zeroone_report_missing",
            "stderrTail": completed.stderr[-1024:],
        }
    try:
        report = loads_strict_json_object(lines[-1])
    except (json.JSONDecodeError, StrictJsonError):
        return {
            "schemaVersion": REPORT_SCHEMA_VERSION,
            "success": False,
            "exitCode": completed.returncode,
            "diagnostic": "zeroone_report_invalid_json",
        }
    if report.get("exitCode") != completed.returncode:
        report = dict(report)
        report["success"] = False
        report["diagnostic"] = "zeroone_exit_code_mismatch"
    return report


def _successful_compute_report(report: dict[str, Any]) -> bool:
    return (
        report.get("schemaVersion") == REPORT_SCHEMA_VERSION
        and report.get("success") is True
        and _static_artifact_loaded(report)
        and report.get("canonicalAuthorityPreserved") is True
        and report.get("globalPhase10Complete") is False
    )


def _static_cook_executed(report: dict[str, Any]) -> bool:
    if report.get("cacheState") == "hit":
        return False
    explicit = report.get("actualZeroOneStaticCookExecutedThisInvocation")
    if isinstance(explicit, bool):
        return explicit
    # Historical processors used two ambiguous booleans; cache state narrows them to static truth.
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


def _publish_derivative(
    package: Path,
    source: Path,
    request: dict[str, Any],
    clean_run: dict[str, Any],
    cache_hit: dict[str, Any],
    resume_run: dict[str, Any],
    tool: ZeroOneToolResolution,
    *,
    replace_existing: bool,
) -> Path:
    namespace = package / "zeroone"
    target = namespace / "static-d0"
    assert_safe_child(package, target)
    if target.exists() and not replace_existing:
        raise FileExistsError(f"optional ZeroOne derivative already exists: {target}")
    namespace.mkdir(parents=True, exist_ok=True)
    staging = create_managed_staging(target, allowed_root=namespace, purpose="zeroone-static-d0")
    try:
        copy_verified_derivative(source, staging)
        write_canonical_json(staging / "request.json", request)
        write_canonical_json(staging / "processing_report.json", clean_run["cook"])
        write_canonical_json(staging / "validation_report.json", clean_run["validate"])
        write_canonical_json(
            staging / "compatibility.json",
            {
                "schemaVersion": "closy.zeroone.compatibility.v1",
                "profile": clean_run["cook"].get("profile"),
                "requestSchemaVersion": request.get("schemaVersion"),
                "reportSchemaVersion": clean_run["cook"].get("schemaVersion"),
                "canonicalDerivativeHash": clean_run["cook"].get("canonicalDerivativeHash"),
                "fallbackRequired": True,
                "dynamicDeformationAvailable": False,
            },
        )
        write_canonical_json(
            staging / "provenance.json",
            {
                "schemaVersion": "closy.zeroone.provenance.v1",
                "closyGitSha": request.get("producer", {}).get("closyGitSha"),
                "zeroOneGitSha": clean_run["cook"].get("zeroOneGitSha"),
                "executableSha256": tool.executable_sha256,
                "canonicalAuthorityHashes": authority_hashes(request),
                "outputHashes": clean_run["cook"].get("outputHashes"),
                "cacheMissState": clean_run["cook"].get("cacheState"),
                "cacheHitState": cache_hit.get("cacheState"),
                "actualZeroOneStaticCookExecutedThisInvocation": True,
                "actualZeroOneStaticArtifactLoaded": True,
                "cacheValidated": True,
                "resumeValidated": resume_run["resume"].get("resumeState") == "matched",
                "actualZeroOneDynamicDeformationExecuted": False,
                "actualZeroOneGpuRuntimeExecuted": False,
                "actualZeroOneMobileRuntimeExecuted": False,
                "globalPhase10Complete": False,
            },
        )
        write_namespace_manifest(staging)
        validate_namespace_manifest(staging)
        publish_managed_staging(
            staging,
            target,
            allowed_root=namespace,
            purpose="zeroone-static-d0",
            force=replace_existing,
        )
    except BaseException:
        cleanup_managed_staging(staging, allowed_root=namespace, purpose="zeroone-static-d0")
        raise
    validate_namespace_manifest(target)
    return target


def _declared_hashes(report: dict[str, Any]) -> dict[str, str]:
    return {
        str(entry["path"]): str(entry["sha256"])
        for entry in report.get("outputHashes", [])
        if isinstance(entry, dict)
    }


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


def _bounded_report(value: dict[str, Any]) -> dict[str, Any]:
    report = value.get("cook", value)
    bounded = {
        key: report.get(key)
        for key in (
            "success",
            "exitCode",
            "diagnostic",
            "cacheState",
            "canonicalDerivativeHash",
            "canonicalAuthorityPreserved",
            "timingsMs",
            "peakMemoryBytes",
        )
    }
    bounded["actualZeroOneStaticCookExecutedThisInvocation"] = _static_cook_executed(report)
    bounded["actualZeroOneStaticArtifactLoaded"] = _static_artifact_loaded(report)
    return bounded


def _bounded_resume_report(value: dict[str, Any]) -> dict[str, Any]:
    resumed = _bounded_report(value["resume"])
    resumed.update(
        {
            "interruptionDiagnostic": value["interrupted"].get("diagnostic"),
            "resumeState": value["resume"].get("resumeState"),
            "validatedNativeDerivative": value["validate"].get("validatedNativeDerivative"),
        }
    )
    return resumed


def _unexecuted(
    status: str,
    reason: str,
    tool: ZeroOneToolResolution,
    fallback_preserved: bool,
    report: dict[str, Any],
) -> ZeroOneIntegrationResult:
    return ZeroOneIntegrationResult(
        status,
        reason,
        False,
        False,
        False,
        fallback_preserved,
        fallback_preserved,
        False,
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
) -> ZeroOneIntegrationResult:
    fallback_preserved = fallback_before is not None and _fallback_hash(package) == fallback_before
    package_preserved = _canonical_package_hashes(package) == before_files
    return ZeroOneIntegrationResult(
        "process_failed",
        reason,
        False,
        False,
        False,
        fallback_preserved,
        package_preserved,
        False,
        None,
        tool,
        report,
    )
