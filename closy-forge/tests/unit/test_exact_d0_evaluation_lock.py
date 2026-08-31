from __future__ import annotations

import json
from pathlib import Path

import pytest

from closy_forge.fitting.exact_d0_lock import (
    EXACT_D0_EVALUATION_LOCK_PATH,
    EXACT_D0_EVALUATION_LOCK_SHA256,
    load_exact_d0_evaluation_lock,
)
from closy_forge.package_io.hashing import sha256_file


def test_exact_d0_evaluation_lock_is_frozen_and_complete() -> None:
    root = Path(__file__).resolve().parents[2]
    lock = load_exact_d0_evaluation_lock(root)

    assert sha256_file(root / EXACT_D0_EVALUATION_LOCK_PATH) == EXACT_D0_EVALUATION_LOCK_SHA256
    assert [item["label"] for item in lock["templateSet"]] == ["regular", "slim", "boxy"]
    assert lock["candidateRepresentation"]["historicalPr39CoordinatesReusable"] is False
    assert lock["candidateRepresentation"]["topologyV1FallbackAfterMetricsAllowed"] is False
    assert lock["heldOutPolicy"]["frontAndRearAreInSample"] is True
    assert lock["heldOutPolicy"]["evaluatorOnlyViewMountedBeforeFreeze"] is False
    assert lock["claims"]["canonicalProductAcceptance"] is False
    assert len(lock["metricApplicability"]) >= 20


def test_exact_d0_evaluation_lock_rejects_mutation(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    destination = tmp_path / EXACT_D0_EVALUATION_LOCK_PATH
    destination.parent.mkdir(parents=True)
    payload = json.loads((root / EXACT_D0_EVALUATION_LOCK_PATH).read_text(encoding="utf-8"))
    payload["thresholds"]["fit"]["minimumMultiviewSilhouetteMeanIoU"] = 0.1
    destination.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="exact_d0_evaluation_lock_hash_mismatch"):
        load_exact_d0_evaluation_lock(tmp_path)
