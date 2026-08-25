from __future__ import annotations

from closy_forge.binding.benchmark import benchmark_binding_c3
from closy_forge.binding.c3_evidence import hash_motion_state, metric_within_threshold
from closy_forge.binding.production_binding import (
    build_production_binding_c3_report_from_package,
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
    assert manifest["capabilities"]["productionBindingC3EvidenceAvailable"] is True
    assert manifest["capabilities"]["productionBindingC3ProfileAvailable"] is False
    assert contract["authority"]["status"] == "authoritative"
    assert contract["authority"]["routeId"] == "settled_simulation_to_subdivided_render_v1"
    assert contract["destinationRender"]["vertexCount"] == contract["splitMapping"]["recordCount"]
    assert len(contract["records"]) == contract["destinationRender"]["vertexCount"]
    assert contract["safeguards"]["invalidOpeningCrossingCount"] == 0
    assert all(
        abs(sum(record["binding"]["weights"]) - 1.0) <= contract["safeguards"]["weightSumTolerance"]
        for record in contract["records"]
    )
    assert c3_report["readiness"]["gateC3Status"] == "partial"
    assert c3_report["readiness"]["acceptedForD0RuntimeBindingProfile"] is False
    assert c3_report["readiness"]["acceptedForGlobalPhase6"] is False
    assert c3_report["persistedValidation"]["status"] == "pass"
    assert c3_report["motionSuite"]["stateCount"] >= 9
    assert c3_report["aggregate"]["restStateMaxReconstructionErrorMeters"] <= 1e-9
    assert c3_report["execution"]["solverProducedMotionSuiteRun"] is True
    assert c3_report["execution"]["performanceWorkloadProfileRun"] is False
    assert c3_report["performanceProfile"]["repeatCount"] == 0
    assert c3_report["aggregate"]["maxDenseFallbackPanelCentroidDeltaMeters"] > 0.0
    assert (
        c3_report["motionSuite"]["states"][1]["motionTargetComparison"][
            "renderMotionTransformUsedAsOracle"
        ]
        is False
    )
    assert c3_report["motionSuite"]["states"][1]["motionTargetComparison"]["status"] == (
        "not_run_no_independent_motion_oracle"
    )
    fallback = read_json(package / "render" / "simulation_fallback_manifest.json")
    assert fallback["callsDenseReconstruction"] is False
    assert fallback["vertexCount"] != contract["destinationRender"]["vertexCount"]


def test_c3_recompute_does_not_call_legacy_render_motion_transform(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    package = build_demo(tmp_path)

    def forbidden(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("legacy render motion transform called")

    monkeypatch.setattr("closy_forge.binding.production_binding._apply_motion_state", forbidden)
    report = build_production_binding_c3_report_from_package(
        package_dir=package,
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
    )

    assert report["execution"]["solverProducedMotionSuiteRun"] is True


def test_c3_threshold_boundary_is_literal() -> None:
    assert metric_within_threshold(0.009999, 0.01) is True
    assert metric_within_threshold(0.010001, 0.01) is False
    assert metric_within_threshold(float("nan"), 0.01) is False


def test_binding_benchmark_measures_dense_and_independent_fallback(tmp_path) -> None:  # type: ignore[no-untyped-def]
    report = benchmark_binding_c3(build_demo(tmp_path), warmups=1, repeats=3, commit_sha="test")

    assert report["evidenceKind"] == "noncanonical_host_cpu_measurement"
    assert report["repeatCount"] == 3
    assert report["measurements"]["denseFullSuite"]["medianMilliseconds"] > 0.0
    assert report["measurements"]["fallbackFullSuite"]["medianMilliseconds"] > 0.0
    assert "not_mobile_device_performance" in report["limitations"]


def test_conflicting_binding_authority_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_authority.closygarment")
    contract = read_json(corrupt / "binding" / "production_binding_contract.json")
    contract["authority"]["routeId"] = "proposal_runtime_preview_binding_records"
    contract["integrity"]["productionBindingContractHash"] = hash_production_binding_contract(
        contract
    )
    write_json(corrupt / "binding" / "production_binding_contract.json", contract)

    codes = issue_codes(validate_package(corrupt))

    assert "production_binding_authority_conflict" in codes
    assert "production_binding_c3_recompute_mismatch" in codes


def test_forged_solver_state_is_rejected_even_with_refreshed_state_hash(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_motion_state.closygarment")
    path = corrupt / "simulation" / "motion_states" / "forward_bend.json"
    state = read_json(path)
    state["meshes"][0]["positions"][0][0] += 0.001
    state["integrity"]["stateHash"] = hash_motion_state(state)
    write_json(path, state)

    codes = issue_codes(validate_package(corrupt))

    assert "file_hash_mismatch" in codes
    assert "production_binding_c3_recompute_failed" in codes


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
