from __future__ import annotations

import json

from closy_forge.pattern_inference.foundation import (
    build_pattern_inference_foundation,
    rank_templates,
    validate_pattern_inference_foundation,
    write_pattern_inference_foundation,
)


def test_foundation_is_deterministic_disjoint_and_explicitly_not_learned() -> None:
    first = build_pattern_inference_foundation()
    second = build_pattern_inference_foundation()

    assert first == second
    assert validate_pattern_inference_foundation(first) == []
    assert len(first["grammar"]["productions"]) == 8
    assert len(first["dataset"]["samples"]) == 24
    assert {len(first["split"][name]) for name in ("train", "validation", "test")} == {8}
    assert first["benchmark"]["top1Correct"] == 24
    assert first["benchmark"]["top1Accuracy"] == 1.0
    assert first["split"]["identityLeakage"] is True
    assert first["correction"]["humanCorrectionRecord"] is False
    assert first["correction"]["simulatedCorrectionFixture"] is True
    assert first["evidenceTier"]["trainedModelRun"] is False
    assert first["evidenceTier"]["learnedAccuracyClaimed"] is False


def test_retrieval_ranking_is_deterministic_and_variable_panel_aware() -> None:
    ranking = rank_templates({"category": "outerwear", "panelCount": 7, "openings": 5})

    assert ranking[0]["templateId"] == "template.jacket_outerwear"
    assert ranking[0]["score"] == 0
    assert [item["score"] for item in ranking] == sorted(item["score"] for item in ranking)


def test_foundation_writer_persists_six_canonical_documents(tmp_path) -> None:
    bundle = write_pattern_inference_foundation(tmp_path / "foundation")
    files = sorted(path.name for path in (tmp_path / "foundation").iterdir())

    assert files == [
        "benchmark.json",
        "correction_record.json",
        "foundation.json",
        "grammar.json",
        "split.json",
        "synthetic_dataset.json",
    ]
    persisted = json.loads((tmp_path / "foundation/foundation.json").read_text(encoding="utf-8"))
    assert persisted == bundle


def test_corrupted_split_benchmark_and_evidence_tier_fail_closed() -> None:
    bundle = build_pattern_inference_foundation()
    bundle["split"]["test"] = bundle["split"]["validation"][:]
    bundle["benchmark"]["top1Correct"] = 23
    bundle["evidenceTier"]["trainedModelRun"] = True

    issues = validate_pattern_inference_foundation(bundle)

    assert "pattern_dataset_split_invalid" in issues
    assert "template_retrieval_benchmark_recompute_mismatch" in issues
    assert "pattern_inference_evidence_tier_overclaim" in issues
    assert "pattern_inference_bundle_hash_mismatch" in issues
