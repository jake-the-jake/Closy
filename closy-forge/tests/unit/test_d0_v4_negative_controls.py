from __future__ import annotations

from pathlib import Path

from closy_forge.d0_v4_engineering.negative_controls import run_negative_controls

ROOT = Path(__file__).resolve().parents[2]


def test_required_validation_negative_controls_fail_closed_and_are_causal() -> None:
    result = run_negative_controls(
        ROOT,
        ROOT / "models" / "d0_v4_engineering" / "trial-006.json",
    )
    assert result["partition"] == "validation"
    assert result["publicTestRead"] is False
    assert result["allPass"] is True
    assert set(result["controls"]) == {
        "missingPixels",
        "shuffledPixels",
        "wrongModel",
        "removedLogo",
        "translatedLogo",
        "alteredCrop",
        "corruptPng",
        "missingRear",
        "targetAccess",
        "evaluatorAccess",
    }
