from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from closy_forge.pattern_inference.grammar_v2 import compile_program
from closy_forge.pattern_inference.raster_dataset_v3 import (
    compare_compiled_pattern_rasters,
    validate_raster_dataset_v3,
)
from closy_forge.pattern_inference.raster_foundation_v3 import (
    build_raster_foundation_v3,
    validate_raster_foundation_v3,
)


@pytest.fixture(scope="module")
def raster_bundle() -> dict[str, Any]:
    return build_raster_foundation_v3()


def test_raster_corpus_uses_phase2_decode_and_identity_disjoint_splits(
    raster_bundle: dict[str, Any],
) -> None:
    dataset = raster_bundle["dataset"]
    split = raster_bundle["split"]

    assert validate_raster_dataset_v3(dataset, split) == []
    assert len(dataset["programs"]) == 96
    assert len(dataset["samples"]) == 384
    assert {name: len(values) for name, values in split["samples"].items()} == {
        "train": 256,
        "validation": 64,
        "test": 64,
    }
    assert all(
        sample["captureAudit"]["decodedBy"]
        == "closy.capture.raster_sources.decode_raster_fixture_pixels"
        for sample in dataset["samples"]
    )
    assert all(
        "seed" not in key.lower() and "family" not in key.lower() and "program" not in key.lower()
        for sample in dataset["samples"]
        for key in sample["input"]
    )
    assert all("baseSeed" not in program["provenance"] for program in dataset["programs"])


def test_split_validator_recomputes_deliberate_identity_leakage(
    raster_bundle: dict[str, Any],
) -> None:
    split = deepcopy(raster_bundle["split"])
    split["groups"]["test"].append(split["groups"]["train"][0])

    issues = validate_raster_dataset_v3(raster_bundle["dataset"], split)

    assert "raster_source_identity_leakage" in issues
    assert "raster_split_sample_membership_invalid" in issues


def test_raster_training_controls_and_reproducibility_are_literal(
    raster_bundle: dict[str, Any],
) -> None:
    assert validate_raster_foundation_v3(raster_bundle) == []
    assert raster_bundle["reproducibility"]["canonicalModelBytesIdentical"] is True
    thresholds = raster_bundle["evaluation"]["controlThresholds"]
    assert thresholds["labelPermutationPass"] is True
    assert thresholds["pixelsDestroyedPass"] is True
    assert thresholds["metadataOnlyPass"] is True
    assert raster_bundle["evaluation"]["leakageAudits"]["rendererFamilyHoldout"] == {
        "status": "not_run",
        "reason": "only_one_genuinely_distinct_renderer_implementation_available",
    }
    assert raster_bundle["gates"]["E2"]["status"] == "not_run"
    assert raster_bundle["gates"]["globalPhase9"] == "partial"


def test_independent_rerender_is_exact_for_identical_compiled_pattern(
    raster_bundle: dict[str, Any], tmp_path: Any
) -> None:
    pattern = compile_program(raster_bundle["dataset"]["programs"][0])

    result = compare_compiled_pattern_rasters(pattern, pattern, work_root=tmp_path)

    assert result["decodedThroughPhase2"] is True
    assert result["viewCount"] == 4
    assert result["meanSilhouetteIoU"] == 1.0
    assert result["meanNormalisedContourDistance"] == 0.0
