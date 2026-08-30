from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from closy_forge.package_io.canonical_json import read_json
from closy_forge.pattern_inference.raster_evaluation_v4 import (
    evaluate_raster_model_v4,
    predict_unassisted,
)
from closy_forge.pattern_inference.raster_execution_v4 import build_unassisted_candidate
from closy_forge.pattern_inference.raster_foundation_v3 import build_raster_foundation_v3
from closy_forge.pattern_inference.reference_3d_v1 import (
    build_reference_geometry,
    compare_reference_geometry,
)


def _thresholds() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "phase9_structured_threshold_registry_v2.json"
    )
    return read_json(path)


@pytest.fixture(scope="module")
def foundation() -> dict[str, Any]:
    return build_raster_foundation_v3()


def test_unassisted_candidate_boundary_has_no_target_or_oracle_fallback(
    foundation: dict[str, Any],
) -> None:
    bundle = foundation
    sample = bundle["dataset"]["samples"][0]
    prediction = predict_unassisted(bundle["model"], sample["input"])
    candidate = build_unassisted_candidate(
        bundle["model"], sample["input"], candidate_id="candidate.boundary.test", seed=1
    )
    assert prediction["family"] == candidate["prediction"]["family"]
    assert "target" not in candidate
    assert "fallback" not in candidate


def test_corrective_evaluation_uses_disjoint_transformed_inputs_and_honest_gate(
    foundation: dict[str, Any],
) -> None:
    bundle = foundation
    result = evaluate_raster_model_v4(
        bundle["model"], bundle["dataset"], bundle["split"], _thresholds()
    )
    assert result["sampleCount"] == 64
    assert result["leakageAudit"]["candidateApiAcceptsTargets"] is False
    assert result["leakageAudit"]["identityDisjoint"] is True
    assert all(item["inputHashesChanged"] for item in result["shiftSuites"])
    assert all(item["trainingIdentityCount"] == 0 for item in result["shiftSuites"])
    assert all(item["inputChanged"] for item in result["ood"]["challenges"])
    assert result["learned"]["outcomes"][0]["fallbackCountedAsLearnedSuccess"] is False
    assert result["claims"]["globalPhase9Complete"] is False


def test_reference_3d_path_builds_dense_binding_and_detects_geometry_change(
    foundation: dict[str, Any],
) -> None:
    bundle = foundation
    program = bundle["dataset"]["programs"][0]
    from closy_forge.pattern_inference.grammar_v2 import compile_program

    pattern = compile_program(program)
    left = build_reference_geometry(program["garmentFamily"], pattern)
    changed = deepcopy(program)
    field = "body_length_meters"
    changed["parameters"][field] = round(float(changed["parameters"][field]) * 1.03, 9)
    changed_pattern = compile_program(changed)
    right = build_reference_geometry(changed["garmentFamily"], changed_pattern)
    comparison = compare_reference_geometry(left, right)
    assert left["audit"]["bindingRecordCount"] == left["audit"]["renderVertexCount"]
    assert left["audit"]["maximumReconstructionError"] <= 1e-6
    assert comparison["viewCount"] == 4
    assert comparison["meanProjectedChamferMeters"] > 0.0
