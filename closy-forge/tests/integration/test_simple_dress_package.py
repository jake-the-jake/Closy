from __future__ import annotations

import json

from closy_forge.cli.main import EXIT_SUCCESS, main
from closy_forge.geometry.glb_io import audit_glb, read_glb_meshset
from closy_forge.package_io.hashing import sha256_file
from closy_forge.pipeline.build_simple_dress_demo import build_demo_simple_dress_package
from closy_forge.validation.validator import validate_package
from tests.helpers import build_simple_dress, read_json

GOLDEN_DIGEST = "1ca8d89ee5629ebffb9c252724722b8c1418ed0966e48c3b7270024a08de3f40"


def test_simple_dress_package_is_complete_conventional_and_valid(tmp_path) -> None:
    package = build_simple_dress(tmp_path)
    manifest = read_json(package / "manifest.json")
    quality = read_json(package / "reports/simple_dress_quality.json")
    motion = read_json(package / "reports/material_motion_suite.json")
    fidelity = read_json(package / "reports/fidelity/source_render_fidelity.json")

    assert validate_package(package) == {
        "schemaVersion": 1,
        "status": "passed",
        "counts": {"info": 0, "warning": 0, "error": 0, "fatal": 0},
        "issues": [],
    }
    assert manifest["packageDigest"] == GOLDEN_DIGEST, _golden_diagnostics(manifest)
    assert manifest["counts"] == {
        "panelCount": 4,
        "simulationVertexCount": 189,
        "simulationTriangleCount": 181,
        "renderVertexCount": 1086,
        "renderTriangleCount": 724,
        "bindingRecordCount": 1086,
    }
    assert quality["readiness"]["simpleDressD0Complete"] is True
    assert quality["readiness"]["phase8GloballyComplete"] is False
    assert quality["topology"]["waistIsSewnNotOpen"] is True
    assert motion["readiness"]["armholesNonCollapsed"] is True
    assert motion["armholeStress"]["armholeMetrics"]["armholeOpeningCount"] == 2
    assert motion["armholeStress"]["metrics"]["converged"] is False
    assert fidelity["acceptedForD0SimpleDressFixture"] is True
    assert fidelity["aggregate"]["minimumSilhouetteIoU"] == 0.938558559
    for relpath in [
        "simulation/simulation_mesh.glb",
        "render/fallback.glb",
        "render/simulation_fallback.glb",
        "avatar/reference_avatar.glb",
        "avatar/collision.glb",
    ]:
        audit = audit_glb(package / relpath)
        assert audit["validGlb20"] is True
        assert audit["triangleEstimate"] > 0
        assert audit["hasVec4Tangents"] is True
    simulation = read_glb_meshset(package / "simulation/simulation_mesh.glb")
    dense = read_glb_meshset(package / "render/fallback.glb")
    fallback = read_glb_meshset(package / "render/simulation_fallback.glb")
    assert dense.vertex_count > simulation.vertex_count
    assert fallback.vertex_count == simulation.vertex_count


def test_simple_dress_repeated_builds_are_byte_identical(tmp_path) -> None:
    first = tmp_path / "a.closygarment"
    second = tmp_path / "b.closygarment"
    build_demo_simple_dress_package(first)
    build_demo_simple_dress_package(second)
    first_hashes = {
        path.relative_to(first).as_posix(): sha256_file(path)
        for path in sorted(first.rglob("*"))
        if path.is_file()
    }
    second_hashes = {
        path.relative_to(second).as_posix(): sha256_file(path)
        for path in sorted(second.rglob("*"))
        if path.is_file()
    }
    assert first_hashes == second_hashes
    assert read_json(first / "manifest.json")["packageDigest"] == GOLDEN_DIGEST


def test_simple_dress_cli_build_validate_report_and_diff(tmp_path, capsys) -> None:
    first = tmp_path / "cli_a.closygarment"
    second = tmp_path / "cli_b.closygarment"
    assert main(["demo", "build-simple-dress", "--output", str(first), "--json"]) == EXIT_SUCCESS
    assert main(["demo", "build-simple-dress", "--output", str(second), "--json"]) == EXIT_SUCCESS
    assert main(["packages", "diff", str(first), str(second), "--json"]) == EXIT_SUCCESS
    assert main(["validate", str(first), "--json"]) == EXIT_SUCCESS
    assert main(["report", str(first), "--json"]) == EXIT_SUCCESS
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["garmentClass"] == "simple_dress"
    assert payload["readiness"]["simpleDressD0Complete"] is True


def _golden_diagnostics(manifest: dict) -> str:
    return json.dumps(
        {
            "actualDigest": manifest["packageDigest"],
            "inventory": {
                entry["path"]: {
                    "sha256": entry["sha256"],
                    "byteSize": entry["byteSize"],
                    "canonical": entry["canonical"],
                }
                for entry in manifest["inventory"]
            },
        },
        sort_keys=True,
    )
