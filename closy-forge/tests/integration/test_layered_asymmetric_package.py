from __future__ import annotations

import json

from closy_forge.cli.main import EXIT_SUCCESS, main
from closy_forge.geometry.glb_io import audit_glb, read_glb_meshset
from closy_forge.package_io.hashing import sha256_file
from closy_forge.pipeline.build_layered_asymmetric_demo import build_demo_layered_asymmetric_package
from closy_forge.validation.validator import validate_package
from tests.helpers import build_layered_asymmetric, read_json

GOLDEN_DIGEST = "1baef98b30384c63d71dd76dea7f25ca9922cbdc1b4b413d86b90841fba7ec2c"


def test_layered_asymmetric_package_is_complete_conventional_and_valid(tmp_path) -> None:
    package = build_layered_asymmetric(tmp_path)
    manifest = read_json(package / "manifest.json")
    quality = read_json(package / "reports/layered_asymmetric_quality.json")
    motion = read_json(package / "reports/material_motion_suite.json")
    fidelity = read_json(package / "reports/fidelity/source_render_fidelity.json")

    assert validate_package(package) == {
        "schemaVersion": 1,
        "status": "passed",
        "counts": {"info": 0, "warning": 0, "error": 0, "fatal": 0},
        "issues": [],
    }
    assert manifest["packageDigest"] == GOLDEN_DIGEST, _golden_diagnostics(manifest)
    assert manifest["garmentClass"] == "layered_asymmetric"
    assert len(manifest["inventory"]) == 41
    assert manifest["counts"] == {
        "panelCount": 4,
        "simulationVertexCount": 256,
        "simulationTriangleCount": 248,
        "renderVertexCount": 1488,
        "renderTriangleCount": 992,
        "bindingRecordCount": 1488,
    }
    assert quality["readiness"]["layeredAsymmetricD0Complete"] is False
    assert quality["readiness"]["phase8FamilyLadderComplete"] is False
    assert quality["readiness"]["phase8GloballyComplete"] is False
    assert quality["layering"] == {
        "layerCount": 2,
        "innerPanelCount": 2,
        "outerPanelCount": 2,
        "interLayerCollisionEnabled": False,
        "interLayerCollisionStatus": "not_executed_reference_solver",
        "minimumDeclaredClearanceMeters": 0.014,
        "restFrontClearanceMeters": 0.02,
        "outerAsymmetricHemDropMeters": 0.09,
        "orderedCollisionLayers": [10, 20],
    }
    assert motion["readiness"]["armholesNonCollapsed"] is True
    assert motion["underarmStress"]["armholeMetrics"]["armholeCount"] == 4
    assert motion["underarmStress"]["armholeMetrics"]["collapsedArmholeCount"] == 0
    assert fidelity["acceptedForD0LayeredAsymmetricFixture"] is True
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


def test_layered_asymmetric_repeated_builds_are_byte_identical(tmp_path) -> None:
    first = tmp_path / "a.closygarment"
    second = tmp_path / "b.closygarment"
    build_demo_layered_asymmetric_package(first)
    build_demo_layered_asymmetric_package(second)
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
    manifest = read_json(first / "manifest.json")
    assert manifest["packageDigest"] == GOLDEN_DIGEST, _golden_diagnostics(manifest)


def test_layered_asymmetric_cli_build_validate_report_and_diff(tmp_path, capsys) -> None:
    first = tmp_path / "cli_a.closygarment"
    second = tmp_path / "cli_b.closygarment"
    assert (
        main(["demo", "build-layered-asymmetric", "--output", str(first), "--json"]) == EXIT_SUCCESS
    )
    assert (
        main(["demo", "build-layered-asymmetric", "--output", str(second), "--json"])
        == EXIT_SUCCESS
    )
    assert main(["packages", "diff", str(first), str(second), "--json"]) == EXIT_SUCCESS
    assert main(["validate", str(first), "--json"]) == EXIT_SUCCESS
    assert main(["report", str(first), "--json"]) == EXIT_SUCCESS
    outputs = capsys.readouterr().out.splitlines()
    payload = json.loads(outputs[-1])
    assert payload["garmentClass"] == "layered_asymmetric"
    assert payload["readiness"]["layeredAsymmetricD0Complete"] is False


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
