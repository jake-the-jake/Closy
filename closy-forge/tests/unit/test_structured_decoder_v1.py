from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from closy_forge.package_io.canonical_json import read_json
from closy_forge.pattern_inference.structured_decoder_v1 import (
    build_structured_dataset_v1,
    compile_structured_ast_v1,
    decode_structured_ast_v1,
    evaluate_structured_decoder_v1,
    structured_ast_hash,
    train_structured_decoder_v1,
    validate_structured_ast_v1,
    validate_structured_dataset_v1,
)


@pytest.fixture(scope="module")
def bundle() -> dict[str, Any]:
    return build_structured_dataset_v1()


@pytest.fixture(scope="module")
def model(bundle: dict[str, Any]) -> dict[str, Any]:
    return train_structured_decoder_v1(bundle)


def _thresholds() -> dict[str, Any]:
    return read_json(
        Path(__file__).resolve().parents[2]
        / "docs"
        / "phase9_structured_threshold_registry_v2.json"
    )


def test_structured_dataset_meets_precommitted_scale_and_holdout_contract(
    bundle: dict[str, Any],
) -> None:
    assert validate_structured_dataset_v1(bundle["dataset"], bundle["split"]) == []
    assert [len(bundle["split"]["groups"][name]) for name in ("train", "validation", "test")] == [
        128,
        32,
        48,
    ]
    assert len(bundle["split"]["heldoutStructuralCompositionGroups"]) == 4
    assert all(
        group["presentInTraining"] is False
        for group in bundle["split"]["heldoutStructuralCompositionGroups"]
    )


def test_trained_decoder_emits_typed_canonical_ast_and_rejects_corruption(
    bundle: dict[str, Any], model: dict[str, Any]
) -> None:
    record = next(
        record
        for record in bundle["dataset"]["records"]
        if record["programIdentity"] in set(bundle["split"]["groups"]["validation"])
    )
    prediction = decode_structured_ast_v1(
        model, record["observation"], program_id="typed.test", seed=4
    )
    assert prediction["status"] == "accepted"
    assert validate_structured_ast_v1(prediction["ast"]) == []
    assert compile_structured_ast_v1(prediction["ast"])["panels"]
    assert structured_ast_hash(prediction["ast"]) == prediction["astHash"]
    corrupt = deepcopy(prediction["ast"])
    corrupt["garmentProgram"]["programVersion"] = "invalid"
    assert "program_program_version_invalid" in validate_structured_ast_v1(corrupt)
    with pytest.raises(ValueError, match="invalid_typed_ast"):
        compile_structured_ast_v1(corrupt)


def test_structured_evaluation_runs_3d_and_reports_truthful_feasibility(
    bundle: dict[str, Any], model: dict[str, Any]
) -> None:
    result = evaluate_structured_decoder_v1(model, bundle, _thresholds())
    assert result["dataset"]["identityDisjoint"] is True
    assert result["dataset"]["train"] == 128
    assert result["dataset"]["validation"] == 32
    assert result["dataset"]["test"] == 48
    assert result["invalidProgramRejection"]["compilerRejected"] is True
    assert result["oodDeferral"]["passed"] is True
    assert result["deterministicReplay"] is True
    assert all(
        record["reference3dExecuted"]
        for record in result["records"]
        if record["status"] == "accepted"
    )
    assert result["acceptance"]["status"] in {"pass", "executed_feasibility_partial"}
    assert result["claims"]["globalE2Complete"] is False
