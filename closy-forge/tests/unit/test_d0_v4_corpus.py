from __future__ import annotations

from pathlib import Path

import pytest

from closy_forge.d0_v4_engineering.corpus import (
    PARTITION_COUNTS,
    PublicTestAccessDenied,
    load_manifest,
    load_partition,
    observation_for_record,
)

ROOT = Path(__file__).resolve().parents[2]


def test_corpus_has_exact_disjoint_inventory_and_two_renderers() -> None:
    manifest = load_manifest(ROOT)
    assert manifest["partitionCounts"] == PARTITION_COUNTS
    assert manifest["separation"]["status"] == "pass"
    assert manifest["separation"]["uniqueCounts"]["identity"] == 768
    assert set(manifest["rendererFamilies"]) == {
        "polygon_scanline_v1",
        "supersampled_antialias_v1",
    }
    assert manifest["lostOpaqueV2Relation"] == "unverified"


def test_training_and_validation_use_same_pixel_observation_entrypoint() -> None:
    training = load_partition(ROOT, "train")
    validation = load_partition(ROOT, "validation")
    assert len(training) == 512
    assert len(validation) == 128
    official = next(record for record in training if record["capture"]["cropFraction"] == 0.0)
    observation = observation_for_record(official)
    assert observation["pixelDerived"] is True
    assert observation["views"]["front"]["decodedSize"] == [128, 160]
    assert observation["views"]["front"]["alphaFullyOpaque"] is True


def test_public_test_targets_are_fail_closed_outside_one_shot_evaluator() -> None:
    with pytest.raises(PublicTestAccessDenied):
        load_partition(ROOT, "public_test")


def test_variation_axes_include_crop_occlusion_logo_and_missing_rear() -> None:
    records = load_partition(ROOT, "validation")
    assert any(record["capture"]["cropFraction"] > 0.0 for record in records)
    assert any(record["capture"]["occlusionFraction"] > 0.0 for record in records)
    assert any(record["capture"]["rearMissing"] for record in records)
    assert {record["appearance"]["logoShape"] for record in records} == {
        "none",
        "circle",
        "diamond",
        "bar",
    }
