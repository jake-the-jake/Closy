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


def test_generated_canonical_text_artifacts_use_lf_bytes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = tmp_path / "demo_tshirt.closygarment"
    assert main(["demo", "build-tshirt", "--output", str(package), "--json"]) == EXIT_SUCCESS
    for path in package.rglob("*"):
        if path.suffix not in {".json", ".svg", ".md"}:
            continue
        data = path.read_bytes()
        assert b"\r\n" not in data, path
        assert b"\r" not in data, path


def test_generated_glbs_are_parseable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = tmp_path / "demo_tshirt.closygarment"
    assert main(["demo", "build-tshirt", "--output", str(package)]) == EXIT_SUCCESS
    for rel in [
        "avatar/reference_avatar.glb",
        "avatar/collision.glb",
        "proposals/manual_raw_visual_proposal.glb",
        "proposals/manual_cleanup_preview.glb",
        "proposals/manual_repair_preview.glb",
        "proposals/manual_runtime_retopology_preview.glb",
        "simulation/simulation_mesh.glb",
        "render/fallback.glb",
    ]:
        audit = audit_glb(package / rel)
        assert audit["validGlb20"] is True
        assert audit["triangleEstimate"] > 0


def test_cli_package_diff_reports_first_changed_file(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    package_a = tmp_path / "demo_a.closygarment"
    package_b = tmp_path / "demo_b.closygarment"
    assert main(["demo", "build-tshirt", "--output", str(package_a), "--json"]) == EXIT_SUCCESS
    assert main(["demo", "build-tshirt", "--output", str(package_b), "--json"]) == EXIT_SUCCESS
    assert main(["packages", "diff", str(package_a), str(package_b), "--json"]) == EXIT_SUCCESS
    changed = package_b / "reports" / "summary.md"
    changed.write_bytes(changed.read_bytes() + b"drift\n")
    assert main(["packages", "diff", str(package_a), str(package_b), "--json"]) != EXIT_SUCCESS
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["status"] == "different"
    assert payload["changed"][0]["path"] == "reports/summary.md"
    assert payload["changed"][0]["firstDifference"]["offset"] > 0


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
    assert payload["rawGeometryTopology"]["componentCount"] == 5
    assert payload["rawGeometryTopology"]["nonManifoldEdgeCount"] == 0
    assert payload["rawGeometryTopology"]["degenerateTriangleCount"] == 0
    assert payload["rawGeometryTopology"]["acceptedForCleanProposal"] is False
    assert payload["geometryCleanupPlan"]["status"] == "blocked_not_executed"
    assert payload["geometryCleanupPlan"]["requiredOperationCount"] == 6
    assert payload["geometryCleanupPlan"]["acceptedForCleanProposal"] is False
    assert payload["geometryCleanupResult"]["status"] == "partial_cleanup_completed"
    assert payload["geometryCleanupResult"]["cleanupRun"] is True
    assert payload["geometryCleanupResult"]["repairRun"] is False
    assert payload["geometryCleanupResult"]["removedDuplicateVertexCount"] > 0
    assert payload["geometryCleanupResult"]["acceptedForCleanProposal"] is False
    assert payload["geometrySemanticTransfer"]["status"] == (
        "semantic_transfer_completed_binding_pending"
    )
    assert payload["geometrySemanticTransfer"]["semanticTransferRun"] is True
    assert payload["geometrySemanticTransfer"]["boundaryClassificationRun"] is True
    assert payload["geometrySemanticTransfer"]["transferredPanelCount"] == 5
    assert payload["geometrySemanticTransfer"]["classifiedBoundaryEdgeCount"] == 218
    assert payload["geometrySemanticTransfer"]["unclassifiedBoundaryEdgeCount"] == 0
    assert payload["geometrySemanticTransfer"]["acceptedForCleanProposal"] is False
    assert payload["geometryBindingCandidate"]["status"] == (
        "binding_candidate_generated_validation_pending"
    )
    assert payload["geometryBindingCandidate"]["candidateBindingRun"] is True
    assert payload["geometryBindingCandidate"]["runtimeBindingWritten"] is False
    assert payload["geometryBindingCandidate"]["cleanupVertexCount"] == 223
    assert payload["geometryBindingCandidate"]["mappedVertexCount"] == 223
    assert payload["geometryBindingCandidate"]["unmappedVertexCount"] == 0
    assert payload["geometryBindingCandidate"]["candidateCompleteness"] == 1.0
    assert payload["geometryBindingCandidate"]["acceptedForCleanProposal"] is False
    assert payload["geometryBindingValidation"]["status"] == (
        "deformation_validation_failed_runtime_binding_rejected"
    )
    assert payload["geometryBindingValidation"]["deformationValidationRun"] is True
    assert payload["geometryBindingValidation"]["runtimeBindingAccepted"] is False
    assert payload["geometryBindingValidation"]["validationRecordCount"] == 223
    assert payload["geometryBindingValidation"]["failedCheckCount"] == 1
    assert payload["geometryBindingValidation"]["notRunCheckCount"] == 4
    assert payload["geometryBindingValidation"]["maxCleanupToSettledOffsetMeters"] == 0.944948063
    assert payload["geometryBindingValidation"]["acceptedForCleanProposal"] is False
    assert payload["geometryRepairRetopologyPlan"]["status"] == (
        "repair_retopology_plan_generated_execution_pending"
    )
    assert payload["geometryRepairRetopologyPlan"]["repairRetopologyPlanGenerated"] is True
    assert payload["geometryRepairRetopologyPlan"]["repairRun"] is False
    assert payload["geometryRepairRetopologyPlan"]["retopologyRun"] is False
    assert payload["geometryRepairRetopologyPlan"]["seamSplitRun"] is False
    assert payload["geometryRepairRetopologyPlan"]["requiredOperationCount"] == 8
    assert payload["geometryRepairRetopologyPlan"]["deformationFailedVertexCount"] == 210
    assert (
        payload["geometryRepairRetopologyPlan"]["estimatedRepairComplexity"]
        == "retopology_required"
    )
    assert payload["geometryRepairRetopologyPlan"]["acceptedForCleanProposal"] is False
    assert payload["geometryRepairResult"]["status"] == (
        "partial_repair_completed_retopology_pending"
    )
    assert payload["geometryRepairResult"]["repairResultGenerated"] is True
    assert payload["geometryRepairResult"]["deformationReprojectionRun"] is True
    assert payload["geometryRepairResult"]["repairRun"] is True
    assert payload["geometryRepairResult"]["retopologyRun"] is False
    assert payload["geometryRepairResult"]["seamSplitRun"] is False
    assert payload["geometryRepairResult"]["movedVertexCount"] == 223
    assert payload["geometryRepairResult"]["unmappedVertexCount"] == 0
    assert payload["geometryRepairResult"]["deferredOperationCount"] == 7
    assert payload["geometryRepairResult"]["maxOutputToSettledOffsetMeters"] == 0.0
    assert payload["geometryRepairResult"]["acceptedForCleanProposal"] is False
    assert payload["geometryRuntimeBindingResult"]["status"] == (
        "runtime_binding_ready_clean_acceptance_pending"
    )
    assert payload["geometryRuntimeBindingResult"]["retopologyRun"] is True
    assert payload["geometryRuntimeBindingResult"]["seamSplitRun"] is True
    assert payload["geometryRuntimeBindingResult"]["componentStitchingRun"] is True
    assert payload["geometryRuntimeBindingResult"]["runtimeBindingWritten"] is True
    assert payload["geometryRuntimeBindingResult"]["runtimeBindingAccepted"] is True
    assert payload["geometryRuntimeBindingResult"]["runtimeBindingRecordCount"] == 1308
    assert payload["geometryRuntimeBindingResult"]["maxReconstructionError"] == 0.0
    assert payload["geometryRuntimeBindingResult"]["acceptedForCleanProposal"] is False
    assert payload["cleanGeometryProposal"]["qualityStatus"] == "rejected"
    assert payload["cleanGeometryProposal"]["cleanProposalAvailable"] is False
    assert payload["cleanGeometryProposal"]["acceptedForCanonical"] is False
    assert payload["cleanGeometryProposal"]["topologyDiagnosticsRun"] is True
    assert payload["cleanGeometryProposal"]["cleanupPlanGenerated"] is True
    assert payload["cleanGeometryProposal"]["cleanupRun"] is True
    assert payload["cleanGeometryProposal"]["semanticTransferReportGenerated"] is True
    assert payload["cleanGeometryProposal"]["semanticTransferRun"] is True
    assert payload["cleanGeometryProposal"]["bindingCandidateReportGenerated"] is True
    assert payload["cleanGeometryProposal"]["bindingValidationReportGenerated"] is True
    assert payload["cleanGeometryProposal"]["repairRetopologyPlanGenerated"] is True
    assert payload["cleanGeometryProposal"]["partialRepairResultGenerated"] is True
    assert payload["cleanGeometryProposal"]["runtimeBindingResultGenerated"] is True
    assert payload["cleanGeometryProposal"]["candidateBindingRun"] is True
    assert payload["cleanGeometryProposal"]["deformationValidationRun"] is True
    assert payload["cleanGeometryProposal"]["deformationReprojectionRun"] is True
    assert payload["cleanGeometryProposal"]["simulationBindingRun"] is True
    assert payload["cleanGeometryProposal"]["runtimeBindingAccepted"] is True
    assert payload["providerRegistry"]["selectedProviderId"] == ("closy.manual_local_glb_import.v1")
    assert payload["providerRegistry"]["manualLocalImportAssetAvailable"] is True
    assert payload["binding"]["recordCount"] > 0
