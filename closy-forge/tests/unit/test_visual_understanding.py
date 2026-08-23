from __future__ import annotations

from closy_forge.capture import build_synthetic_capture_record
from closy_forge.visual_understanding import (
    REQUIRED_TSHIRT_VISUAL_LANDMARKS,
    build_empty_correction_record,
    build_tshirt_visual_observations,
    hash_correction_record,
    hash_visual_observations,
)


def test_tshirt_visual_observations_include_masks_and_landmarks() -> None:
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)

    assert visual["sourceRecordHash"] == capture["immutability"]["sourceRecordHash"]
    assert visual["integrity"]["visualRecordHash"] == hash_visual_observations(visual)
    assert visual["aggregate"]["maskCount"] == 4
    assert set(REQUIRED_TSHIRT_VISUAL_LANDMARKS).issubset(
        set(visual["aggregate"]["observedLandmarks"])
    )
    assert visual["provider"]["externalApis"] is False


def test_empty_correction_record_is_editable_and_hash_stable() -> None:
    visual = build_tshirt_visual_observations(build_synthetic_capture_record(seed=101))
    correction = build_empty_correction_record(visual)

    assert correction["editable"] is True
    assert correction["operations"] == []
    assert correction["visualRecordHash"] == visual["integrity"]["visualRecordHash"]
    assert correction["integrity"]["correctionRecordHash"] == hash_correction_record(correction)
    assert "mask_polygon_edit" in correction["allowedOperations"]
