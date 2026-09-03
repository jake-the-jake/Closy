from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from closy_forge.d0_v4_engineering.corpus import (
    load_partition,
    observation_for_record,
)
from closy_forge.d0_v4_engineering.model import (
    MODEL_ROOT,
    load_model,
    metadata_only_baseline,
    model_digest,
    predict_structured,
)

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / MODEL_ROOT / "trial-006.json"


def test_persisted_model_is_genuinely_learned_and_complete() -> None:
    model = load_model(MODEL_PATH)
    assert model["learnedWeightsPersisted"] is True
    assert model["multivariate"] is True
    assert model["trainingSampleCount"] == 512
    assert model["validationSampleCount"] == 128
    assert len(model["weights"]) == 11
    assert all(any(abs(value) > 1e-8 for value in row) for row in model["weights"])


def test_prediction_is_bounded_complete_and_has_uncertainty() -> None:
    model = load_model(MODEL_PATH)
    record = load_partition(ROOT, "validation")[0]
    prediction = predict_structured(model, observation_for_record(record))
    assert prediction["status"] == "predicted"
    assert prediction["targetParametersRead"] is False
    assert len(prediction["rawLogits"]) == 11
    assert len(prediction["uncertainty95"]) == 11
    assert len(prediction["alternatives"]) == 2


def test_pixel_mutation_changes_geometry_and_zero_weights_do_not_match() -> None:
    model = load_model(MODEL_PATH)
    records = load_partition(ROOT, "validation")
    left = predict_structured(model, observation_for_record(records[0]))
    right = predict_structured(model, observation_for_record(records[1]))
    assert left["parameters"] != right["parameters"]
    zero_model = deepcopy(model)
    zero_model["weights"] = [[0.0] * len(row) for row in model["weights"]]
    zero_model["integrity"]["weightsSha256"] = "zero_weight_ablation"
    zero_model["integrity"]["modelSha256"] = model_digest(zero_model)
    ablated = predict_structured(zero_model, observation_for_record(records[0]))
    assert ablated["status"] == "predicted"
    assert ablated["parameters"] != left["parameters"]
    assert metadata_only_baseline() != left["parameters"]
