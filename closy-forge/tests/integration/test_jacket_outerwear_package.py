from __future__ import annotations

import json

from closy_forge.cli.main import EXIT_SUCCESS, main
from closy_forge.geometry.glb_io import audit_glb, read_glb_meshset
from closy_forge.package_io.hashing import sha256_file
from closy_forge.pipeline.build_jacket_outerwear_demo import build_demo_jacket_outerwear_package
from closy_forge.validation.validator import validate_package
from tests.helpers import build_jacket_outerwear, read_json

GOLDEN_DIGEST = "2ca4a210d560c3452106767dce12c775b9733b9a5e5237d2222026260228101a"


def test_jacket_outerwear_package_is_complete_conventional_and_valid(tmp_path) -> None:
    package = build_jacket_outerwear(tmp_path)
    manifest = read_json(package / "manifest.json")
    quality = read_json(package / "reports/jacket_outerwear_quality.json")
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
        "panelCount": 7,
        "simulationVertexCount": 331,
        "simulationTriangleCount": 324,
        "renderVertexCount": 1944,
        "renderTriangleCount": 1296,
        "bindingRecordCount": 1944,
    }
    assert quality["readiness"]["jacketOuterwearD0Complete"] is True
    assert quality["readiness"]["phase8GloballyComplete"] is False
    assert quality["topology"]["hasSeparateFacings"] is True
    assert quality["topology"]["frontOpeningUsesFacingInnerEdges"] is True
    assert quality["topology"]["outerLayerCollisionOrderValid"] is True
    assert quality["material"]["selectedPresetId"] == "material.heavy_jersey_d0_v1"
    assert motion["readiness"]["cuffsNonCollapsed"] is True
    assert fidelity["acceptedForD0JacketOuterwearFixture"] is True
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


def test_jacket_outerwear_repeated_builds_are_byte_identical(tmp_path) -> None:
    first = tmp_path / "a.closygarment"
    second = tmp_path / "b.closygarment"
    build_demo_jacket_outerwear_package(first)
    build_demo_jacket_outerwear_package(second)
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


def test_jacket_outerwear_cli_build_validate_report_and_diff(tmp_path, capsys) -> None:
    first = tmp_path / "cli_a.closygarment"
    second = tmp_path / "cli_b.closygarment"
    assert (
        main(["demo", "build-jacket-outerwear", "--output", str(first), "--json"]) == EXIT_SUCCESS
    )
    assert (
        main(["demo", "build-jacket-outerwear", "--output", str(second), "--json"]) == EXIT_SUCCESS
    )
    assert main(["packages", "diff", str(first), str(second), "--json"]) == EXIT_SUCCESS
    assert main(["validate", str(first), "--json"]) == EXIT_SUCCESS
    assert main(["report", str(first), "--json"]) == EXIT_SUCCESS
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["garmentClass"] == "jacket_outerwear"
    assert payload["readiness"]["jacketOuterwearD0Complete"] is True


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
