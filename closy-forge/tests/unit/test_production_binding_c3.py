from __future__ import annotations

from closy_forge.binding.production_binding import (
    hash_production_binding_c3_report,
    hash_production_binding_contract,
)
from closy_forge.validation.validator import validate_package
from tests.helpers import build_demo, clone_package, issue_codes, read_json, write_json


def test_demo_package_emits_scoped_production_binding_c3_evidence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = build_demo(tmp_path)
    manifest = read_json(package / "manifest.json")
    contract = read_json(package / "binding" / "production_binding_contract.json")
    c3_report = read_json(package / "reports" / "production_binding_c3.json")
    validation = validate_package(package)

    assert validation["status"] == "passed"
    assert [issue["code"] for issue in validation["issues"]] == [
        "self_collision_unresolved_contacts"
    ]
    assert manifest["capabilities"]["productionBindingContractAvailable"] is True
    assert manifest["capabilities"]["productionBindingC3ProfileAvailable"] is True
    assert contract["destinationRender"]["vertexCount"] == contract["splitMapping"]["recordCount"]
    assert len(contract["records"]) == contract["destinationRender"]["vertexCount"]
    assert contract["safeguards"]["invalidOpeningCrossingCount"] == 0
    assert all(
        abs(sum(record["binding"]["weights"]) - 1.0) <= contract["safeguards"]["weightSumTolerance"]
        for record in contract["records"]
    )
    assert c3_report["readiness"]["gateC3Status"] == ("complete_for_d0_fixed_avatar_tshirt_profile")
    assert c3_report["readiness"]["acceptedForGlobalPhase6"] is False
    assert c3_report["persistedValidation"]["status"] == "pass"
    assert c3_report["motionSuite"]["stateCount"] >= 9
    assert (
        c3_report["aggregate"]["maxReconstructionErrorMeters"]
        <= c3_report["thresholds"]["maxReconstructionErrorMeters"]
    )
    assert c3_report["aggregate"]["maxDenseFallbackParityErrorMeters"] == 0.0


def test_tampered_production_binding_contract_ids_are_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_c3_contract.closygarment")
    contract = read_json(corrupt / "binding" / "production_binding_contract.json")
    contract["records"][0]["renderVertexId"] = contract["records"][1]["renderVertexId"]
    contract["integrity"]["productionBindingContractHash"] = hash_production_binding_contract(
        contract
    )
    write_json(corrupt / "binding" / "production_binding_contract.json", contract)

    codes = issue_codes(validate_package(corrupt))

    assert "file_hash_mismatch" in codes
    assert "production_binding_contract_duplicate_render_vertex_id" in codes
    assert "production_binding_contract_missing_render_vertex_id" in codes
    assert "production_binding_c3_source_hash_mismatch" in codes
    assert "production_binding_c3_recompute_mismatch" in codes


def test_tampered_production_binding_c3_metrics_are_rejected_even_with_fresh_hash(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_c3_report.closygarment")
    report = read_json(corrupt / "reports" / "production_binding_c3.json")
    report["aggregate"]["maxReconstructionErrorMeters"] = 0.25
    report["integrity"]["productionBindingC3ReportHash"] = hash_production_binding_c3_report(report)
    write_json(corrupt / "reports" / "production_binding_c3.json", report)

    codes = issue_codes(validate_package(corrupt))

    assert "file_hash_mismatch" in codes
    assert "production_binding_c3_recompute_mismatch" in codes
