from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from closy_forge.appearance.bitmap_atlas import audit_bitmap_atlas_bundle
from closy_forge.appearance.exact_bitmap_atlas import build_exact_d0_bitmap_atlas
from closy_forge.dependency_identity import validate_dependency_graph
from closy_forge.fitting.exact_d0_candidate import (
    compile_exact_d0_candidate,
    validate_compiled_candidate_files,
    write_compiled_exact_candidate,
)
from closy_forge.fitting.exact_d0_pixel_controls import (
    execute_exact_d0_pixel_fit_controls,
)
from closy_forge.fitting.tshirt_fit import fit_tshirt_parameters_from_visual_observations
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.security.evidence_hygiene import scan_evidence_files


def test_exact_bitmap_atlas_opens_frozen_bytes_without_evaluator_view() -> None:
    root = Path(__file__).resolve().parents[2]
    fixture_root = root / "fixtures" / "d0_exact_raster_v2"
    manifest = _read(fixture_root / "fixture_manifest.json")
    correction = _read(
        root
        / "docs"
        / "evidence"
        / "d0_exact_raster_identity_v2"
        / "qualification"
        / "correction_evidence.json"
    )
    visual = correction["correctedObservation"]

    bundle = build_exact_d0_bitmap_atlas(
        fixture_root=fixture_root,
        fixture_manifest=manifest,
        visual_observations=visual,
    )

    assert bundle.report["status"] == "pass"
    assert bundle.report["policy"]["fixtureRendererCalled"] is False
    assert bundle.report["policy"]["evaluatorOnlyViewUsed"] is False
    assert {item["label"] for item in bundle.report["sourceViews"]} == {"front", "back"}
    assert all(
        item["sourceMode"] == "opened_frozen_exact_png_bytes"
        for item in bundle.report["sourceViews"]
    )
    assert bundle.report["coverage"]["generatedControlledFillFraction"] > 0.0
    assert bundle.report["pbr"]["normalRoughnessAoPhysicalAccuracy"] == "not_measured"
    assert audit_bitmap_atlas_bundle(bundle.artifacts, bundle.report, visual)["status"] == "pass"


def test_exact_candidate_is_fresh_topology_v2_and_reloadable(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    fixture_root = root / "fixtures" / "d0_exact_raster_v2"
    manifest = _read(fixture_root / "fixture_manifest.json")
    correction = _read(
        root
        / "docs"
        / "evidence"
        / "d0_exact_raster_identity_v2"
        / "qualification"
        / "correction_evidence.json"
    )
    visual = correction["correctedObservation"]
    atlas = build_exact_d0_bitmap_atlas(
        fixture_root=fixture_root,
        fixture_manifest=manifest,
        visual_observations=visual,
    )
    candidate = compile_exact_d0_candidate(
        contender_id="test_regular",
        parameters=TShirtParameters(),
        visual_observations=visual,
        fixture_root=fixture_root,
        fixture_manifest=manifest,
        atlas=atlas,
    )
    write_compiled_exact_candidate(tmp_path, candidate)

    assert candidate.report["simulation"]["topologyAlgorithm"] == "closy.simulation_topology.v2"
    assert candidate.report["simulation"]["historicalPr39CoordinatesUsed"] is False
    assert candidate.report["binding"]["status"] == "pass"
    assert candidate.report["seams"]["status"] == "pass"
    assert candidate.report["inSampleSourceRerender"]["aggregate"]["allViewsNonBlank"] is True
    assert validate_compiled_candidate_files(tmp_path, candidate.report)["status"] == "pass"


def test_exact_pixel_controls_reparse_refit_and_move_locked_parameters() -> None:
    root = Path(__file__).resolve().parents[2]
    fixture_root = root / "fixtures" / "d0_exact_raster_v2"
    manifest = _read(fixture_root / "fixture_manifest.json")
    qualification = root / "docs/evidence/d0_exact_raster_identity_v2/qualification"
    correction_evidence = _read(qualification / "correction_evidence.json")
    capture = _read(qualification / "capture_record.json")
    lock = _read(root / "fixtures/d0_exact_fitting_v2/evaluation_lock.json")
    prior = TShirtParameters(**lock["templateSet"][0]["prior"])
    baseline_fit = fit_tshirt_parameters_from_visual_observations(
        correction_evidence["correctedObservation"],
        multiview_fusion=correction_evidence["multiviewFusion"],
        prior=prior,
    )

    result = execute_exact_d0_pixel_fit_controls(
        fixture_root=fixture_root,
        fixture_manifest=manifest,
        capture_record=capture,
        selected_correction=correction_evidence["selectedCorrectionRecord"],
        prior=prior,
        baseline_fit=baseline_fit,
        minimum_delta=lock["thresholds"]["fit"]["minimumCausalParameterDeltaMeters"],
    )

    assert result["inputMode"] == (
        "opened_frozen_front_rear_png_bytes_then_controlled_pixel_mutation"
    )
    assert result["fixtureRendererCalled"] is False
    assert result["targetParametersRead"] is False
    assert result["evaluatorOnlyMounted"] is False
    assert result["allDirectionsPassed"] is True
    assert result["allCanonicalQuantisationExceeded"] is True
    assert all(record["observationRecomputed"] for record in result["records"])
    assert all(record["fusionRecomputed"] for record in result["records"])
    assert all(record["fitRecomputed"] for record in result["records"])


def test_exact_post_freeze_evaluation_is_candidate_joined_and_fail_closed() -> None:
    root = Path(__file__).resolve().parents[2]
    evaluation = root / "docs/evidence/d0_fitting_pbr_fidelity_v2/evaluation"
    predictions = root / "docs/evidence/d0_fitting_pbr_fidelity_v2/predictions"
    lock = _read(root / "fixtures/d0_exact_fitting_v2/evaluation_lock.json")
    summary = _read(evaluation / "qualification_summary.json")
    checkpoint = _read(evaluation / "prediction_checkpoint_validation.json")
    matrix = _read(evaluation / "final_d0_research_prototype_matrix_v2.json")
    corruption = _read(evaluation / "corruption_controls.json")
    metrics = _read(evaluation / "metric_applicability.json")
    texture = _read(evaluation / "exact_texture_rerender_evaluation.json")
    neutral = _read(evaluation / "exact_neutral_simulation.json")
    strict_c3 = _read(evaluation / "strict_c3_evaluation.json")
    dependency = _read(evaluation / "candidate_dependency_identity_graph.json")
    prediction_summary = _read(predictions / "prediction_summary.json")

    assert checkpoint["status"] == "pass"
    assert checkpoint["predictionCheckpointSha"] == ("0d54b7e32664eb873e1662c6ca21e46e65e5557f")
    assert checkpoint["predictionFreezeHash"] == prediction_summary["predictionFreezeHash"]
    assert summary["evaluatorImplementationSha"] == ("c9aaa81d1acf1aa79b20555b7ed22890a46a825f")
    assert summary["researchPrototype"] == "partial"
    assert summary["firstUnmetRequirement"]["rowId"] == "D0-RP-07"
    assert matrix["statusCounts"] == {"pass": 7, "fail": 3, "not_run": 5}

    expected_controls = {item["controlId"] for item in lock["corruptionExpectations"]}
    assert {item["controlId"] for item in corruption["records"]} == expected_controls
    assert corruption["allExpectedCorruptionsDetected"] is True
    assert {item["metricId"] for item in metrics["records"]} == {
        item["metricId"] for item in lock["metricApplicability"]
    }
    assert metrics["recordCount"] == len(lock["metricApplicability"])
    assert texture["status"] == "fail"
    assert texture["roughnessNormalAoPhysicalAccuracy"] == "not_measured"
    assert neutral["status"] == "fail"
    assert strict_c3["status"] == "fail"
    validate_dependency_graph(dependency)

    for path in evaluation.glob("*.json"):
        document = _read(path)
        integrity = document.get("integrity", {})
        if "evidenceHash" not in integrity:
            continue
        stored = integrity["evidenceHash"]
        document["integrity"]["evidenceHash"] = ""
        assert stored == sha256_bytes(canonical_dumps(document).encode("utf-8"))
    assert (
        scan_evidence_files(sorted([*evaluation.rglob("*.json"), *evaluation.rglob("*.svg")])) == {}
    )


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
