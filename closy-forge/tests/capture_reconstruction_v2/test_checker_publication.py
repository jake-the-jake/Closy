from __future__ import annotations

import json
from pathlib import Path

from closy_forge.capture_reconstruction_v2.corpus import _truth_observation
from closy_forge.capture_reconstruction_v2.evaluation import (
    _camera_metrics,
    _segmentation_metrics,
)
from closy_forge.capture_reconstruction_v2.evaluator_renderer import (
    render_novel_view_reference,
    score_atlas_against_novel_view,
)
from closy_forge.capture_reconstruction_v2.independent_checker import (
    _appearance_score,
    _camera,
    _recompute_controls,
    _segmentation,
    check_publication_paths,
)
from closy_forge.capture_reconstruction_v2.producer_cross import render_cross_generator
from closy_forge.capture_reconstruction_v2.protocol import build_protocol
from closy_forge.capture_reconstruction_v2.publication import check_generated_freshness
from closy_forge.capture_reconstruction_v2.render_types import mask_runs
from closy_forge.capture_reconstruction_v2.reproducibility import run_development_canary_twice

REPOSITORY = Path(__file__).resolve().parents[3]
FORGE = REPOSITORY / "closy-forge"
FIXTURES = FORGE / "fixtures" / "capture_reconstruction_v2"
EVIDENCE = FORGE / "docs" / "evidence" / "capture_reconstruction_v2"


def _session() -> dict[str, object]:
    return {
        "sessionId": "checker-session",
        "partition": "development",
        "mode": "B",
        "family": "tshirt",
        "stratum": "cross_generator",
        "presentation": "hung",
        "planOrdinal": 0,
        "resolution": [256, 288],
        "weakOrMissingViewIndex": None,
        "expectedSourceCount": 1,
        "expectedVideoFrames": 0,
    }


def test_independent_checker_reimplements_novel_view_scoring_exactly() -> None:
    parameters = {
        "bodyLength": 0.55,
        "bodyWidth": 0.47,
        "openingWidth": 0.15,
        "sleeveLength": 0.21,
        "hemWidth": 0.51,
    }
    rgba = bytes((index * 17 + 13) % 256 for index in range(64 * 64 * 4))
    observed = bytes(255 if index % 5 else 0 for index in range(64 * 64))
    for family in ("tshirt", "sleeveless_top", "simple_skirt"):
        evaluator = score_atlas_against_novel_view(
            rgba, observed, render_novel_view_reference(family, parameters)
        )
        checker = _appearance_score(rgba, observed, family, parameters)
        assert checker["deltaEProxy"] == evaluator["deltaEProxy"]
        assert checker["ssimProxy"] == evaluator["ssimProxy"]


def test_independent_checker_reimplements_segmentation_and_camera_metrics_exactly() -> None:
    rendered = render_cross_generator(_session(), hidden_nonce=987654)
    truth = _truth_observation(rendered, 0)
    predicted_masks = {
        "garment": rendered.masks["garment"],
        "body": rendered.masks["body"],
        "hair_hands": bytes(
            max(left, right)
            for left, right in zip(rendered.masks["hair"], rendered.masks["hands"], strict=True)
        ),
        "occluder": rendered.masks["occluder"],
        "scale_target": rendered.masks["scale_target"],
    }
    observed = {
        "width": rendered.width,
        "height": rendered.height,
        "maskRuns": {name: mask_runs(mask) for name, mask in predicted_masks.items()},
        "landmarks": {name: list(value) for name, value in rendered.landmarks.items()},
        "quality": {"garmentCoverage": sum(rendered.masks["garment"]) / 255 / 256 / 288},
    }
    estimate = {
        "status": "estimated",
        "yawDegrees": rendered.camera["yawDegrees"] + 2.0,
        "pitchDegrees": rendered.camera["pitchDegrees"] - 1.0,
        "focalPixels": rendered.camera["focalPixels"] * 1.03,
        "principalX": rendered.camera["principalX"] + 1.0,
        "principalY": rendered.camera["principalY"] - 1.0,
        "scaleMetersPerPixel": rendered.camera["scaleMetersPerPixel"] * 0.98,
    }
    assert _segmentation(observed, truth) == {
        key: value
        for key, value in _segmentation_metrics(observed, truth).items()
        if key in {"garmentIou", "boundaryFscore", "partAccuracy", "landmarkNormalizedError"}
    }
    assert _camera(estimate, observed, truth) == _camera_metrics(estimate, observed, truth)


def test_independent_checker_recomputes_each_control_predicate() -> None:
    rows = [
        {
            "control": "localized_source_pixel_intervention",
            "terminalOutcome": "failed",
            "measured": {
                "changedTexels": 4,
                "totalTexels": 100,
                "maximumChangedFraction": 0.6,
            },
        },
        {
            "control": "evaluator_hidden_target_mutation",
            "terminalOutcome": "failed",
            "measured": {"outputsBitIdentical": True},
        },
        {
            "control": "estimated_camera_perturbation",
            "terminalOutcome": "failed",
            "measured": {"outputsBitIdentical": False},
        },
        {
            "control": "visibility_occlusion_perturbation",
            "terminalOutcome": "failed",
            "measured": {"baselineObservedSum": 80, "interventionObservedSum": 60},
        },
        {
            "control": "association_mismatch",
            "terminalOutcome": "failed",
            "measured": {"outputsBitIdentical": False},
        },
    ]

    recomputed = _recompute_controls(rows)

    assert [row["terminalOutcome"] for row in recomputed] == ["passed"] * 5


def test_checked_in_protocol_and_source_publications_are_fresh() -> None:
    protocol = json.loads((FIXTURES / "protocol.json").read_text(encoding="utf-8"))
    assert protocol == build_protocol()
    assert check_generated_freshness(REPOSITORY) == []


def test_development_canary_reproduces_in_two_clean_directories(tmp_path: Path) -> None:
    report = run_development_canary_twice(build_protocol(), tmp_path / "canary.json")
    assert report["terminalOutcome"] == "passed"
    assert report["canonicalDigestsReproducible"] is True
    assert report["sessionCountPerRun"] == 10
    assert report["appearanceControlCountPerRun"] == 50
    assert set(report["modeCounts"]) == {"A", "B", "C", "D", "E"}
    assert set(report["familyCounts"]) == {"tshirt", "sleeveless_top", "simple_skirt"}
    assert set(report["stratumCounts"]) == {"in_model", "cross_generator"}


def test_committed_locked_publication_is_independently_recomputable_when_present() -> None:
    envelope = EVIDENCE / "canonical_result_envelope.json"
    if not envelope.exists():
        # The source-freeze CI stage intentionally runs before locked identities exist.
        assert not (EVIDENCE / "synthetic_truth_disclosure.json").exists()
        return
    checker = check_publication_paths(
        FIXTURES / "protocol.json",
        FIXTURES / "locked_observable_manifest.json",
        FIXTURES / "locked_truth_commitments.json",
        EVIDENCE / "contestant_outputs.json",
        envelope,
        EVIDENCE / "synthetic_truth_disclosure.json",
    )
    assert checker["terminalOutcome"] == "passed", checker["failureReasons"]
    assert checker["sessionCount"] == 30
    assert checker["controlCount"] == 150
