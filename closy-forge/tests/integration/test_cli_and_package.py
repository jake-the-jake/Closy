from __future__ import annotations

import json

from closy_forge.cli.main import EXIT_SUCCESS, main
from closy_forge.geometry.glb_io import audit_glb
from closy_forge.validation.validator import validate_package


def test_cli_build_validate_report_workflow(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = tmp_path / "demo_tshirt.closygarment"
    assert main(["demo", "build-tshirt", "--output", str(package), "--json"]) == EXIT_SUCCESS
    assert package.exists()
    assert main(["validate", str(package), "--json"]) == EXIT_SUCCESS
    assert main(["report", str(package)]) == EXIT_SUCCESS
    report = validate_package(package)
    assert report["status"] == "passed"
    assert report["counts"]["warning"] == 1


def test_generated_glbs_are_parseable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = tmp_path / "demo_tshirt.closygarment"
    assert main(["demo", "build-tshirt", "--output", str(package)]) == EXIT_SUCCESS
    for rel in [
        "avatar/reference_avatar.glb",
        "avatar/collision.glb",
        "simulation/simulation_mesh.glb",
        "render/fallback.glb",
    ]:
        audit = audit_glb(package / rel)
        assert audit["validGlb20"] is True
        assert audit["triangleEstimate"] > 0


def test_report_json_is_machine_readable(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    package = tmp_path / "demo_tshirt.closygarment"
    assert main(["demo", "build-tshirt", "--output", str(package)]) == EXIT_SUCCESS
    assert main(["report", str(package), "--json"]) == EXIT_SUCCESS
    captured = capsys.readouterr()
    payload = json.loads(captured.out.splitlines()[-1])
    assert payload["garmentId"] == "garment.demo_tshirt.reference_v1"
    assert payload["binding"]["recordCount"] > 0
