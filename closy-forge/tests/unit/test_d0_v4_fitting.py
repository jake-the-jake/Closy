from __future__ import annotations

from pathlib import Path

from closy_forge.d0_v4_engineering.corpus import load_partition
from closy_forge.d0_v4_engineering.fitting import hybrid_for_record
from closy_forge.d0_v4_engineering.model import MODEL_ROOT, load_model

ROOT = Path(__file__).resolve().parents[2]


def test_hybrid_is_bounded_source_conditioned_and_compile_valid() -> None:
    model = load_model(ROOT / MODEL_ROOT / "trial-002.json")
    record = load_partition(ROOT, "validation")[0]
    prediction = hybrid_for_record(model, record)
    assert prediction["status"] == "predicted"
    assert prediction["targetParametersRead"] is False
    assert prediction["fit"]["boundedIterationCount"] == 2
    assert prediction["compile"]["finite"] is True
    assert prediction["compile"]["seamStatus"] == "pass"
    assert prediction["compile"]["bindingStatus"] == "pass"


def test_hybrid_missing_or_corrupt_front_fails_closed() -> None:
    model = load_model(ROOT / MODEL_ROOT / "trial-002.json")
    record = load_partition(ROOT, "validation")[0]
    corrupt = dict(record)
    corrupt["frontPng"] = b"not-png"
    prediction = hybrid_for_record(model, corrupt)
    assert prediction["status"] == "rejected"
    assert prediction["parameters"] is None


def test_ambiguous_arm_span_blends_independent_pixel_evidence() -> None:
    model = load_model(ROOT / MODEL_ROOT / "trial-006.json")
    records = load_partition(ROOT, "validation")
    for ordinal in (91, 93, 99, 111, 119):
        record = records[ordinal]
        prediction = hybrid_for_record(model, record)
        shoulder_low, shoulder_high = (0.55, 0.82)
        predicted = (prediction["parameters"]["shoulder_width"] - shoulder_low) / (
            shoulder_high - shoulder_low
        )
        target = (record["parameters"]["shoulder_width"] - shoulder_low) / (
            shoulder_high - shoulder_low
        )
        assert abs(predicted - target) <= 0.22
        assert prediction["fit"]["trace"][0]["selectionPolicy"].endswith("bounded_blend")
