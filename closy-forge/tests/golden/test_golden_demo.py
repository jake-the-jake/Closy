from __future__ import annotations

from pathlib import Path

from closy_forge.package_io.canonical_json import read_json
from closy_forge.pipeline.build_tshirt_demo import build_demo_tshirt_package
from closy_forge.validation.validator import validate_package


def test_demo_package_matches_structural_golden(tmp_path) -> None:  # type: ignore[no-untyped-def]
    golden_path = Path(__file__).with_name("expected_demo_summary.json")
    expected = read_json(golden_path)
    package = tmp_path / "demo_tshirt.closygarment"
    build_demo_tshirt_package(package)
    manifest = read_json(package / "manifest.json")
    summary = read_json(package / "reports" / "summary.json")
    pattern = read_json(package / "pattern" / "pattern.json")
    validation = validate_package(package)

    assert manifest["canonicalPackageDigest"] == expected["canonicalPackageDigest"]
    assert manifest["hashes"]["simulationTopologyHash"] == expected["simulationTopologyHash"]
    assert manifest["hashes"]["renderTopologyHash"] == expected["renderTopologyHash"]
    for key, value in expected["requiredCapabilities"].items():
        assert manifest["capabilities"][key] is value
    for key, value in expected["capture"].items():
        assert summary["capture"][key] == value
    for key, value in expected["visualUnderstanding"].items():
        assert summary["visualUnderstanding"][key] == value
    for key, value in expected["fitting"].items():
        assert summary["fitting"][key] == value
    for key, value in expected["texture"].items():
        assert summary["texture"][key] == value
    for key, value in expected["geometryProposal"].items():
        assert summary["geometryProposal"][key] == value
    for key, value in expected["rawGeometryTopology"].items():
        assert summary["rawGeometryTopology"][key] == value
    for key, value in expected["geometryCleanupPlan"].items():
        assert summary["geometryCleanupPlan"][key] == value
    for key, value in expected["geometryCleanupResult"].items():
        assert summary["geometryCleanupResult"][key] == value
    for key, value in expected["geometrySemanticTransfer"].items():
        assert summary["geometrySemanticTransfer"][key] == value
    for key, value in expected["geometryBindingCandidate"].items():
        assert summary["geometryBindingCandidate"][key] == value
    for key, value in expected["geometryBindingValidation"].items():
        assert summary["geometryBindingValidation"][key] == value
    for key, value in expected["geometryRepairRetopologyPlan"].items():
        assert summary["geometryRepairRetopologyPlan"][key] == value
    for key, value in expected["geometryRepairResult"].items():
        assert summary["geometryRepairResult"][key] == value
    for key, value in expected["geometryRuntimeBindingResult"].items():
        assert summary["geometryRuntimeBindingResult"][key] == value
    for key, value in expected["geometryStitchedShell"].items():
        assert summary["geometryStitchedShell"][key] == value
    for key, value in expected["geometryVisualShellReview"].items():
        assert summary["geometryVisualShellReview"][key] == value
    for key, value in expected["inspectionArtifacts"].items():
        assert summary["inspectionArtifacts"][key] == value
    for key, value in expected["geometryCleanAcceptanceGate"].items():
        assert summary["geometryCleanAcceptanceGate"][key] == value
    for key, value in expected["cleanGeometryProposal"].items():
        assert summary["cleanGeometryProposal"][key] == value
    for key, value in expected["providerRegistry"].items():
        assert summary["providerRegistry"][key] == value
    assert summary["settle"]["convergenceState"] == expected["settle"]["convergenceState"]
    assert summary["settle"]["solverVersion"] == expected["settle"]["solverVersion"]
    for key, value in expected["counts"].items():
        assert summary["counts"][key] == value
    assert [panel["id"] for panel in pattern["panels"]] == expected["semanticIds"]["panels"]
    assert [seam["id"] for seam in pattern["seams"]] == expected["semanticIds"]["seams"]
    assert [opening["id"] for opening in pattern["openings"]] == expected["semanticIds"]["openings"]
    assert validation["status"] == "passed"
    assert [issue["code"] for issue in validation["issues"]] == expected["bindingWarningCodes"]
