from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.pattern_inference.structured_decoder_v2 import (
    decode_structured_program_v2,
    evaluate_structured_decoder_v2,
    reload_structured_model_v2,
    train_structured_decoder_v2,
    validate_structured_model_v2,
)
from closy_forge.pattern_inference.typed_program_v2 import (
    TOKEN_AXES,
    build_typed_dataset_v2,
    validate_typed_program_v2,
)


@pytest.fixture(scope="module")
def structured_run() -> dict[str, Any]:
    dataset = build_typed_dataset_v2()
    model = reload_structured_model_v2(train_structured_decoder_v2(dataset))
    thresholds = read_json(
        Path(__file__).resolve().parents[2]
        / "docs"
        / "phase9_structured_threshold_registry_v3.json"
    )
    return {
        "dataset": dataset,
        "model": model,
        "evaluation": evaluate_structured_decoder_v2(model, dataset, thresholds),
    }


def test_factorized_decoder_persists_atomic_heads_and_reloads(
    structured_run: dict[str, Any],
) -> None:
    model = structured_run["model"]

    assert validate_structured_model_v2(model) == []
    assert set(model["tokenHeads"]) == set(TOKEN_AXES)
    assert all(head["targetKind"] == "one_atomic_token" for head in model["tokenHeads"].values())
    assert "allowedStructures" not in canonical_dumps(model)
    assert "programIdentity" not in canonical_dumps(model)
    assert model["authority"]["proposalOnly"] is True
    assert model["training"]["testDataUsed"] is False


def test_decoder_uses_observables_and_grammar_mask_without_target_lookup(
    structured_run: dict[str, Any],
) -> None:
    dataset = structured_run["dataset"]
    model = structured_run["model"]
    observation = next(
        record["observation"] for record in dataset["records"] if record["split"] == "test"
    )

    first = decode_structured_program_v2(model, observation, proposal_id="alias.one")
    second = decode_structured_program_v2(model, observation, proposal_id="alias.two")

    assert first["program"]["tokens"] == second["program"]["tokens"]
    assert first["program"]["parameters"] == second["program"]["parameters"]
    assert first["targetLookupUsed"] is False
    assert first["grammarMaskApplied"] is True
    assert validate_typed_program_v2(first["program"]) == []


def test_e2_executes_every_candidate_and_records_losing_result_honestly(
    structured_run: dict[str, Any],
) -> None:
    evaluation = structured_run["evaluation"]

    assert evaluation["execution"]["testProgramCount"] == 96
    assert evaluation["execution"]["actualCompilerInvocations"] == 96
    assert evaluation["metrics"]["schemaTypeValidity"] == 1.0
    assert evaluation["metrics"]["compileTopologyValidityWithoutRepair"] == 1.0
    assert evaluation["metrics"]["reference3dExecutionWithoutRepair"] == 1.0
    assert evaluation["metrics"]["garmentMeasurementRelativeError"] <= 1.0
    assert evaluation["acceptance"]["status"] == "failed"
    assert evaluation["acceptance"]["learnedRouteDefault"] is False
    assert evaluation["acceptance"]["oracleFallbackUsed"] is False
    assert evaluation["pairedBootstrap"]["unit"] == "source_program_identity"
    assert evaluation["leakageAudits"]["passed"] is True


def test_model_and_input_corruption_fail_closed(structured_run: dict[str, Any]) -> None:
    model = structured_run["model"]
    dataset = structured_run["dataset"]
    corrupt = deepcopy(model)
    first_class = next(iter(corrupt["tokenHeads"]["base"]["classes"].values()))
    first_class["prototypes"][0][0] = float("nan")
    observation = deepcopy(dataset["records"][0]["observation"])
    observation[next(iter(observation))] = float("nan")

    assert "structured_model_nonfinite_weight" in validate_structured_model_v2(corrupt)
    with pytest.raises(ValueError, match="structured_observable_nonfinite"):
        decode_structured_program_v2(model, observation)
