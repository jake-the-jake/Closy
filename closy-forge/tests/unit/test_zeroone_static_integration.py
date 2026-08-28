from __future__ import annotations

from pathlib import Path

from closy_forge.garments.sleeveless_top.parameters import SleevelessTopParameters
from closy_forge.package_io.writer import (
    EXCLUDED_FROM_CANONICAL_INVENTORY,
    collect_inventory,
)
from closy_forge.pipeline.build_sleeveless_demo import build_demo_sleeveless_package
from closy_forge.validation.validator import validate_package
from closy_forge.zeroone.integration import integrate_zeroone_static
from closy_forge.zeroone.request import authority_hashes, build_zeroone_request
from closy_forge.zeroone.tool import resolve_zeroone_tool
from closy_forge.zeroone.validation import inspect_zeroone_namespace

CLOSY_SHA = "1" * 40


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
    assert result.to_json()["schemaVersion"] == 1
    assert result.to_json()["contractVersion"] == "closy.zeroone.integration-result.v1"
    assert result.actual_runtime_executed is False
    assert result.actual_compute_executed is False
    assert result.fallback_preserved is True
    assert not (package / "zeroone").exists()


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
