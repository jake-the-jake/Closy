from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file
from closy_forge.security.strict_json import (
    StrictJsonError,
    load_strict_json_object,
    loads_strict_json_object,
)

PINNED_ZEROONE_SOURCE_SHA = "13a844d240f4bbb2cafde105c4a0bdca8d89a06b"
CURRENT_ZEROONE_MASTER_ANCHOR = "a17762bc1fc12fbd33f0488634635a5dcfdf8da3"
REQUEST_SCHEMA_VERSION = "closy.zeroone.static-request.v1"
REPORT_SCHEMA_VERSION = "zeroone.closy.static-report.v1"
PROFILE = "closy-static-d0-cpu-v1"
DYNAMIC_REQUEST_SCHEMA_VERSION = "closy.zeroone.dynamic-request.v1"
DYNAMIC_REPORT_SCHEMA_VERSION = "zeroone.closy.dynamic-report.v1"
DYNAMIC_PROFILE = "closy-dynamic-d0-single-lod-reference-v1"
TOOL_ENV = "CLOSY_ZEROONE_PROCESS"
TRUST_RECORD_ENV = "CLOSY_ZEROONE_TRUSTED_BUILD_RECORD"
TRUST_RECORD_VERSION = "closy.zeroone.trusted-build-record.v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ZeroOneToolResolution:
    available: bool
    reason: str
    executable: Path | None
    executable_sha256: str | None
    version: dict[str, Any] | None
    trusted_build_record: dict[str, Any] | None = None


def minimal_subprocess_environment() -> dict[str, str]:
    allowed = ("SystemRoot", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP", "LANG", "LC_ALL")
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def resolve_zeroone_tool(
    executable: Path | None = None,
    *,
    trusted_build_record: Path | None = None,
    expected_executable_sha256: str | None = None,
    expected_source_sha: str = PINNED_ZEROONE_SOURCE_SHA,
    capability: str = "static",
) -> ZeroOneToolResolution:
    if capability not in {"static", "dynamic"}:
        raise ValueError("zeroone_capability_invalid")
    configured = executable or _configured_path(TOOL_ENV)
    if configured is None:
        return ZeroOneToolResolution(False, "zeroone_tool_not_configured", None, None, None)
    path = configured.expanduser().resolve(strict=False)
    if not path.is_file():
        return ZeroOneToolResolution(False, "zeroone_executable_missing", path, None, None)
    actual_hash = sha256_file(path)
    configured_record = trusted_build_record or _configured_path(TRUST_RECORD_ENV)
    if configured_record is None:
        return ZeroOneToolResolution(
            False, "zeroone_trusted_build_record_required", path, actual_hash, None
        )
    try:
        record = load_strict_json_object(
            configured_record.expanduser().resolve(strict=True),
            expected_fields={
                "schemaVersion",
                "recordVersion",
                "trustDomain",
                "repository",
                "sourceSha",
                "buildId",
                "compiler",
                "buildType",
                "executableRelativeName",
                "executableSha256",
                "requestSchemaVersions",
                "reportSchemaVersions",
                "supportedProfiles",
                "attestation",
                "capture",
            },
        )
    except (OSError, StrictJsonError):
        return ZeroOneToolResolution(
            False, "zeroone_trusted_build_record_invalid", path, actual_hash, None
        )
    record_issue = _validate_trusted_build_record(record, expected_source_sha, capability)
    if record_issue is not None:
        return ZeroOneToolResolution(False, record_issue, path, actual_hash, None, record)
    expected_hash = str(record["executableSha256"])
    if (
        expected_executable_sha256 is not None
        and expected_executable_sha256.lower() != expected_hash
    ):
        return ZeroOneToolResolution(
            False,
            "zeroone_caller_hash_disagrees_with_trusted_record",
            path,
            actual_hash,
            None,
            record,
        )
    if actual_hash != expected_hash:
        return ZeroOneToolResolution(
            False, "zeroone_executable_hash_mismatch", path, actual_hash, None, record
        )
    try:
        completed = subprocess.run(
            [str(path), "version-json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=path.parent,
            env=minimal_subprocess_environment(),
        )
        version = _last_json_object(completed.stdout)
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return ZeroOneToolResolution(
            False, "zeroone_version_query_failed", path, actual_hash, None, record
        )
    if completed.returncode != 0:
        return ZeroOneToolResolution(
            False, "zeroone_version_query_failed", path, actual_hash, version, record
        )
    reason = _validate_version(version, actual_hash, record, capability)
    return ZeroOneToolResolution(
        reason is None,
        reason or "trusted_zeroone_tool_ready",
        path,
        actual_hash,
        version,
        record,
    )


def _configured_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def _last_json_object(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError("tool produced no JSON")
    return loads_strict_json_object(lines[-1])


def _validate_trusted_build_record(
    record: dict[str, Any], expected_source_sha: str, capability: str
) -> str | None:
    if record.get("schemaVersion") != 1 or record.get("recordVersion") != TRUST_RECORD_VERSION:
        return "zeroone_trusted_build_record_version_mismatch"
    if record.get("trustDomain") not in {
        "verified_workflow_artifact",
        "owner_controlled_registry",
        "local_exact_source_capture",
    }:
        return "zeroone_trusted_build_domain_invalid"
    if record.get("repository") != "jake-the-jake/ZeroOne":
        return "zeroone_trusted_build_repository_mismatch"
    if record.get("sourceSha") != expected_source_sha:
        return "zeroone_trusted_build_source_mismatch"
    if record.get("buildType") != "Release":
        return "zeroone_trusted_build_type_invalid"
    if not SHA256_RE.fullmatch(str(record.get("executableSha256", ""))):
        return "zeroone_trusted_build_hash_invalid"
    executable_name = str(record.get("executableRelativeName", ""))
    if Path(executable_name).name != executable_name:
        return "zeroone_trusted_build_executable_name_invalid"
    request_schema = (
        DYNAMIC_REQUEST_SCHEMA_VERSION if capability == "dynamic" else REQUEST_SCHEMA_VERSION
    )
    report_schema = (
        DYNAMIC_REPORT_SCHEMA_VERSION if capability == "dynamic" else REPORT_SCHEMA_VERSION
    )
    profile = DYNAMIC_PROFILE if capability == "dynamic" else PROFILE
    if request_schema not in record.get("requestSchemaVersions", []):
        return "zeroone_trusted_build_request_schema_unsupported"
    if report_schema not in record.get("reportSchemaVersions", []):
        return "zeroone_trusted_build_report_schema_unsupported"
    if profile not in record.get("supportedProfiles", []):
        return "zeroone_trusted_build_profile_unsupported"
    capture = record.get("capture")
    if not isinstance(capture, dict) or (
        capture.get("sourceClean") is not True
        or capture.get("networkAllowed") is not False
        or not isinstance(capture.get("commandTemplate"), list)
    ):
        return "zeroone_trusted_build_capture_invalid"
    if not isinstance(record.get("attestation"), dict):
        return "zeroone_trusted_build_attestation_invalid"
    return None


def _validate_version(
    version: dict[str, Any],
    executable_hash: str,
    trusted_record: dict[str, Any],
    capability: str,
) -> str | None:
    if version.get("tool") != "ZeroOneProcess":
        return "zeroone_tool_identity_mismatch"
    if version.get("zeroOneGitSha") != trusted_record.get("sourceSha"):
        return "zeroone_source_sha_mismatch"
    if version.get("executableSha256") != executable_hash:
        return "zeroone_reported_executable_hash_mismatch"
    if version.get("buildConfiguration") != trusted_record.get("buildType"):
        return "zeroone_reported_build_type_mismatch"
    if version.get("compiler") != trusted_record.get("compiler"):
        return "zeroone_reported_compiler_mismatch"
    if version.get("sourceDirty") is not False:
        return "zeroone_source_dirty"
    if version.get("headless") is not True or version.get("cpuOnly") is not True:
        return "zeroone_not_headless_cpu"
    if version.get("requiresGpu") is not False or version.get("requiresWindow") is not False:
        return "zeroone_has_interactive_runtime_dependency"
    request_key = (
        "dynamicRequestSchemaVersion" if capability == "dynamic" else "requestSchemaVersion"
    )
    report_key = "dynamicReportSchemaVersion" if capability == "dynamic" else "reportSchemaVersion"
    request_schema = (
        DYNAMIC_REQUEST_SCHEMA_VERSION if capability == "dynamic" else REQUEST_SCHEMA_VERSION
    )
    report_schema = (
        DYNAMIC_REPORT_SCHEMA_VERSION if capability == "dynamic" else REPORT_SCHEMA_VERSION
    )
    profile = DYNAMIC_PROFILE if capability == "dynamic" else PROFILE
    required_commands = (
        {"deform", "validate-dynamic", "inspect-dynamic", "resume-dynamic"}
        if capability == "dynamic"
        else {"inspect", "cook", "validate", "resume"}
    )
    if version.get(request_key) != request_schema:
        return "zeroone_request_schema_unsupported"
    if version.get(report_key) != report_schema:
        return "zeroone_report_schema_unsupported"
    if profile not in version.get("profiles", []):
        return "zeroone_profile_unsupported"
    commands = set(version.get("commands", []))
    if not required_commands.issubset(commands):
        return "zeroone_command_contract_incomplete"
    return None
