from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from closy_forge.garments.sleeveless_top.parameters import SleevelessTopParameters
from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_io.writer import (
    EXCLUDED_FROM_CANONICAL_INVENTORY,
    collect_inventory,
)
from closy_forge.pipeline.build_sleeveless_demo import build_demo_sleeveless_package
from closy_forge.validation.validator import validate_package
from closy_forge.zeroone import tool as tool_module
from closy_forge.zeroone.integration import integrate_zeroone_static
from closy_forge.zeroone.request import authority_hashes, build_zeroone_request
from closy_forge.zeroone.tool import resolve_zeroone_tool
from closy_forge.zeroone.validation import inspect_zeroone_namespace

CLOSY_SHA = "1" * 40


def _trusted_record(path: Path, executable: Path) -> Path:
    record = {
        "schemaVersion": 1,
        "recordVersion": "closy.zeroone.trusted-build-record.v1",
        "trustDomain": "local_exact_source_capture",
        "repository": "jake-the-jake/ZeroOne",
        "sourceSha": tool_module.PINNED_ZEROONE_SOURCE_SHA,
        "buildId": "unit-exact-source-build",
        "compiler": "msvc-unit",
        "buildType": "Release",
        "executableRelativeName": executable.name,
        "executableSha256": sha256_file(executable),
        "requestSchemaVersions": ["closy.zeroone.static-request.v1"],
        "reportSchemaVersions": ["zeroone.closy.static-report.v1"],
        "supportedProfiles": ["closy-static-d0-cpu-v1"],
        "attestation": {"available": False, "kind": "unit"},
        "capture": {
            "sourceClean": True,
            "networkAllowed": False,
            "commandTemplate": ["cmake", "--build", "<build>"],
        },
    }
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _package(root: Path) -> Path:
    package = root / "fixture.closygarment"
    build_demo_sleeveless_package(
        package,
        params=SleevelessTopParameters(),
        seed=101,
        force=False,
    )
    return package


def test_closy_builds_strict_zeroone_request_from_canonical_package(tmp_path: Path) -> None:
    package = _package(tmp_path)
    request = build_zeroone_request(
        invocation_root=tmp_path,
        package=package,
        output=tmp_path / "output",
        closy_sha=CLOSY_SHA,
        request_label="unit-contract",
    )

    assert request["schemaVersion"] == "closy.zeroone.static-request.v1"
    assert request["profile"] == "closy-static-d0-cpu-v1"
    assert request["packageRoot"] == "fixture.closygarment"
    assert request["inputAssetPath"] == "render/fallback.glb"
    assert request["semanticIds"]["panels"]
    assert request["semanticIds"]["seams"]
    assert request["semanticIds"]["openings"]
    assert set(authority_hashes(request)) == {
        "appearance",
        "binding",
        "conventional_fallback",
        "pattern",
        "simulation",
        "source",
    }


def test_missing_tool_is_explicit_and_preserves_fallback(tmp_path: Path) -> None:
    package = _package(tmp_path)
    missing = tmp_path / "missing" / "ZeroOneProcess"

    resolution = resolve_zeroone_tool(missing)
    result = integrate_zeroone_static(
        package=package,
        invocation_root=tmp_path,
        closy_sha=CLOSY_SHA,
        executable=missing,
    )

    assert resolution.available is False
    assert resolution.reason == "zeroone_executable_missing"
    assert result.status == "unavailable"
    assert result.to_json()["schemaVersion"] == 2
    assert result.to_json()["contractVersion"] == "closy.zeroone.integration-result.v2"
    assert result.actual_static_cook_executed is False
    assert result.actual_static_artifact_loaded is False
    assert result.cache_validated is False
    assert result.fallback_preserved is True
    assert not (package / "zeroone").exists()


def test_existing_executable_without_independent_build_record_is_untrusted(tmp_path: Path) -> None:
    executable = tmp_path / "ZeroOneProcess.exe"
    executable.write_bytes(b"not-a-trusted-binary")

    resolution = resolve_zeroone_tool(executable)

    assert resolution.available is False
    assert resolution.reason == "zeroone_trusted_build_record_required"
    assert resolution.executable_sha256 is not None


def test_trusted_record_is_cross_checked_against_observed_version_and_minimal_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "ZeroOneProcess.exe"
    executable.write_bytes(b"trusted-unit-binary")
    record = _trusted_record(tmp_path / "trusted.json", executable)
    observed_environment: dict[str, str] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed_environment.update(kwargs["env"])  # type: ignore[arg-type]
        version = {
            "tool": "ZeroOneProcess",
            "zeroOneGitSha": tool_module.PINNED_ZEROONE_SOURCE_SHA,
            "executableSha256": sha256_file(executable),
            "buildConfiguration": "Release",
            "compiler": "msvc-unit",
            "sourceDirty": False,
            "headless": True,
            "cpuOnly": True,
            "requiresGpu": False,
            "requiresWindow": False,
            "requestSchemaVersion": "closy.zeroone.static-request.v1",
            "reportSchemaVersion": "zeroone.closy.static-report.v1",
            "profiles": ["closy-static-d0-cpu-v1"],
            "commands": ["inspect", "cook", "validate", "resume"],
        }
        return subprocess.CompletedProcess([], 0, json.dumps(version), "")

    monkeypatch.setenv("PRIVATE_REPOSITORY_TOKEN", "must-not-leak")
    monkeypatch.setattr(tool_module.subprocess, "run", fake_run)
    resolution = resolve_zeroone_tool(executable, trusted_build_record=record)

    assert resolution.available is True
    assert resolution.reason == "trusted_zeroone_tool_ready"
    assert resolution.trusted_build_record is not None
    assert "PRIVATE_REPOSITORY_TOKEN" not in observed_environment


def test_caller_hash_cannot_override_independent_trusted_record(tmp_path: Path) -> None:
    executable = tmp_path / "ZeroOneProcess.exe"
    executable.write_bytes(b"trusted-unit-binary")
    record = _trusted_record(tmp_path / "trusted.json", executable)

    resolution = resolve_zeroone_tool(
        executable,
        trusted_build_record=record,
        expected_executable_sha256="0" * 64,
    )

    assert resolution.available is False
    assert resolution.reason == "zeroone_caller_hash_disagrees_with_trusted_record"


def test_optional_namespace_fails_closed_when_incompatible_or_corrupt(tmp_path: Path) -> None:
    package = _package(tmp_path)
    namespace = package / "zeroone"
    namespace.mkdir()

    incompatible = inspect_zeroone_namespace(package)
    assert incompatible["status"] == "derivative_incompatible"
    report = validate_package(package)
    assert report["status"] == "failed"
    assert any(issue["code"] == "zeroone_derivative_incompatible" for issue in report["issues"])

    (namespace / "static-d0").mkdir()
    corrupt = inspect_zeroone_namespace(package)
    assert corrupt["status"] == "derivative_corrupt"
    report = validate_package(package)
    assert any(issue["code"] == "zeroone_derivative_corrupt" for issue in report["issues"])


def test_optional_zeroone_namespace_is_excluded_from_canonical_inventory(tmp_path: Path) -> None:
    package = _package(tmp_path)
    before = collect_inventory(package, exclude=EXCLUDED_FROM_CANONICAL_INVENTORY)
    derivative = package / "zeroone" / "static-d0" / "derivative" / "artifact.geomesh"
    derivative.parent.mkdir(parents=True)
    derivative.write_bytes(b"optional-provider-derivative")

    after = collect_inventory(package, exclude=EXCLUDED_FROM_CANONICAL_INVENTORY)

    assert after == before
