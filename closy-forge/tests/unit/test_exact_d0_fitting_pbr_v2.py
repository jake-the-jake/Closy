from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from closy_forge.appearance.bitmap_atlas import audit_bitmap_atlas_bundle
from closy_forge.appearance.exact_bitmap_atlas import build_exact_d0_bitmap_atlas
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


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
