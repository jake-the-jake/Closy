from __future__ import annotations

from pathlib import Path

from closy_forge.d0_v4_engineering.evaluation import (
    _mask_landmark_error,
    validate_evaluation,
)
from closy_forge.package_io.canonical_json import read_json

ROOT = Path(__file__).resolve().parents[2]


def test_mask_landmark_proxy_is_independent_and_normalized() -> None:
    target = {4 * 10 + x for x in range(2, 8)} | {5 * 10 + x for x in range(2, 8)}
    translated = {index + 1 for index in target}
    assert _mask_landmark_error(target, target, width=10, height=10) == 0.0
    assert 0.0 < _mask_landmark_error(translated, target, width=10, height=10) < 0.14
    assert _mask_landmark_error(set(), target, width=10, height=10) == 1.0


def test_final_validation_reconciles_all_rows_and_readiness_gates() -> None:
    result = read_json(
        ROOT / "docs" / "evidence" / "d0_v4_engineering" / "validation_trial_006_final.json"
    )
    assert validate_evaluation(result) == []


def test_lifecycle_validation_is_order_independent_but_exact() -> None:
    result = read_json(
        ROOT / "docs" / "evidence" / "d0_v4_engineering" / "validation_trial_006_final.json"
    )
    first = result["records"][0]["lifecycle"]
    result["records"][0]["lifecycle"] = dict(reversed(list(first.items())))
    assert "lifecycle_axis_invalid" not in validate_evaluation(result)
    result["records"][0]["lifecycle"]["invented"] = False
    assert "lifecycle_axis_invalid" in validate_evaluation(result)
    assert len(result["records"]) == 128
    assert result["summary"]["predictionCount"] == 128
    assert result["summary"]["canonicalCompileSuccess"] >= 126
    assert result["summary"]["parameterBootstrap"]["resamples"] == 10_000
    assert result["summary"]["silhouetteBootstrap"]["resamples"] == 10_000
    assert result["readinessPass"] is True
    assert all(result["gates"].values())
