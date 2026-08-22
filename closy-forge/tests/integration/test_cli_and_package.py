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


def test_cli_build_synthetic_capture_workflow(tmp_path) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / "capture_fixture"
    assert main(["capture", "build-synthetic", "--output", str(output), "--json"]) == EXIT_SUCCESS
    record = json.loads((output / "capture_record.json").read_text(encoding="utf-8"))
    quality = json.loads((output / "capture_quality.json").read_text(encoding="utf-8"))
    visual = json.loads((output / "visual_observations.json").read_text(encoding="utf-8"))
    correction = json.loads((output / "correction_record.json").read_text(encoding="utf-8"))
    assert record["recordType"] == "synthetic_fixture_capture"
    assert quality["overallStatus"] == "pass"
    assert quality["sourceRecordHash"] == record["immutability"]["sourceRecordHash"]
    assert visual["sourceRecordHash"] == record["immutability"]["sourceRecordHash"]
    assert correction["visualRecordHash"] == visual["integrity"]["visualRecordHash"]


def test_report_json_is_machine_readable(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    package = tmp_path / "demo_tshirt.closygarment"
    assert main(["demo", "build-tshirt", "--output", str(package)]) == EXIT_SUCCESS
    assert main(["report", str(package), "--json"]) == EXIT_SUCCESS
    captured = capsys.readouterr()
    payload = json.loads(captured.out.splitlines()[-1])
    assert payload["garmentId"] == "garment.demo_tshirt.reference_v1"
    assert payload["capture"]["overallStatus"] == "pass"
    assert payload["visualUnderstanding"]["maskCount"] == 4
    assert payload["fitting"]["status"] == "pass"
    assert payload["texture"]["sourceTextureAvailable"] is False
    assert payload["texture"]["materialRegionCount"] == 2
    assert payload["geometryProposal"]["qualityStatus"] == "accepted_visual_reference"
    assert payload["geometryProposal"]["acceptedForCanonical"] is False
    assert payload["geometryProposal"]["rawProposalAvailable"] is True
    assert payload["providerRegistry"]["selectedProviderId"] == ("closy.manual_local_glb_import.v1")
    assert payload["providerRegistry"]["manualLocalImportAssetAvailable"] is True
    assert payload["binding"]["recordCount"] > 0
