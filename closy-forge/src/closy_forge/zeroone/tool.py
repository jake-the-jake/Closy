from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file

PINNED_ZEROONE_SOURCE_SHA = "c6388cbbf53ba8a47831ec25e83808e1edf32194"
REQUEST_SCHEMA_VERSION = "closy.zeroone.static-request.v1"
REPORT_SCHEMA_VERSION = "zeroone.closy.static-report.v1"
PROFILE = "closy-static-d0-cpu-v1"
TOOL_ENV = "CLOSY_ZEROONE_PROCESS"
TOOL_HASH_ENV = "CLOSY_ZEROONE_EXECUTABLE_SHA256"


@dataclass(frozen=True)
class ZeroOneToolResolution:
    available: bool
    reason: str
    executable: Path | None
    executable_sha256: str | None
    version: dict[str, Any] | None


def resolve_zeroone_tool(
    executable: Path | None = None,
    *,
    expected_executable_sha256: str | None = None,
    expected_source_sha: str = PINNED_ZEROONE_SOURCE_SHA,
) -> ZeroOneToolResolution:
    configured = executable or _configured_path()
    if configured is None:
        return ZeroOneToolResolution(False, "zeroone_tool_not_configured", None, None, None)
    path = configured.expanduser().resolve(strict=False)
    if not path.is_file():
        return ZeroOneToolResolution(False, "zeroone_executable_missing", path, None, None)
    actual_hash = sha256_file(path)
    expected_hash = expected_executable_sha256 or os.environ.get(TOOL_HASH_ENV)
    if expected_hash is not None and actual_hash != expected_hash.lower():
        return ZeroOneToolResolution(
            False, "zeroone_executable_hash_mismatch", path, actual_hash, None
        )
    try:
        completed = subprocess.run(
            [str(path), "version-json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        version = _last_json_object(completed.stdout)
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return ZeroOneToolResolution(False, "zeroone_version_query_failed", path, actual_hash, None)
    if completed.returncode != 0:
        return ZeroOneToolResolution(
            False, "zeroone_version_query_failed", path, actual_hash, version
        )
    reason = _validate_version(version, actual_hash, expected_source_sha)
    return ZeroOneToolResolution(
        reason is None, reason or "pinned_zeroone_tool_ready", path, actual_hash, version
    )


def _configured_path() -> Path | None:
    value = os.environ.get(TOOL_ENV)
    return Path(value) if value else None


def _last_json_object(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError("tool produced no JSON")
    value = json.loads(lines[-1])
    if not isinstance(value, dict):
        raise ValueError("tool JSON root is not an object")
    return value


def _validate_version(
    version: dict[str, Any], executable_hash: str, expected_source_sha: str
) -> str | None:
    if version.get("tool") != "ZeroOneProcess":
        return "zeroone_tool_identity_mismatch"
    if version.get("zeroOneGitSha") != expected_source_sha:
        return "zeroone_source_sha_mismatch"
    if version.get("executableSha256") != executable_hash:
        return "zeroone_reported_executable_hash_mismatch"
    if version.get("sourceDirty") is not False:
        return "zeroone_source_dirty"
    if version.get("headless") is not True or version.get("cpuOnly") is not True:
        return "zeroone_not_headless_cpu"
    if version.get("requiresGpu") is not False or version.get("requiresWindow") is not False:
        return "zeroone_has_interactive_runtime_dependency"
    if version.get("requestSchemaVersion") != REQUEST_SCHEMA_VERSION:
        return "zeroone_request_schema_unsupported"
    if version.get("reportSchemaVersion") != REPORT_SCHEMA_VERSION:
        return "zeroone_report_schema_unsupported"
    if PROFILE not in version.get("profiles", []):
        return "zeroone_profile_unsupported"
    commands = set(version.get("commands", []))
    if not {"inspect", "cook", "validate", "resume"}.issubset(commands):
        return "zeroone_command_contract_incomplete"
    return None
