from __future__ import annotations

from closy_forge.capture import (
    build_synthetic_capture_record,
    hash_capture_record,
    score_capture_record,
)


def test_synthetic_capture_record_is_metadata_only_and_hash_stable() -> None:
    first = build_synthetic_capture_record(seed=101)
    second = build_synthetic_capture_record(seed=101)

    assert first == second
    assert first["privacy"]["containsUserImagery"] is False
    assert first["privacy"]["containsPersonalBodyData"] is False
    assert first["privacy"]["allowExternalApis"] is False
    assert first["privacy"]["allowTrainingUse"] is False
    assert all(view["rasterImage"]["available"] is False for view in first["views"])
    assert first["immutability"]["sourceRecordHash"] == hash_capture_record(first)


def test_capture_quality_scores_source_record_and_flags_next_artifacts() -> None:
    record = build_synthetic_capture_record(seed=101)
    quality = score_capture_record(record)

    assert quality["overallStatus"] == "pass"
    assert quality["overallScore"] >= quality["qualityThreshold"]
    assert quality["sourceRecordHash"] == record["immutability"]["sourceRecordHash"]
    assert quality["viewCount"] == 4
    assert quality["policy"]["rasterImagesAvailable"] is False
    assert "editable_mask_records" in quality["nextRequiredArtifacts"]
