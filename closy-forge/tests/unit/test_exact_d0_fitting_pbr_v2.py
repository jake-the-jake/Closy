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


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
