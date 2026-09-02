from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from closy_forge.d0_v4_engineering.forensic import (
    build_v3_forensic_erratum,
    validate_v3_forensic_erratum,
)

ROOT = Path(__file__).resolve().parents[2]


def test_v3_forensic_erratum_recomputes_required_failure_facts() -> None:
    report = build_v3_forensic_erratum(ROOT)
    assert validate_v3_forensic_erratum(report) == []
    assert report["v3RerunPerformed"] is False
    assert report["v3PredictionEdited"] is False
    assert report["sealedV3OutcomePreserved"] == "completed_benchmark_failed_absolute_gates"
    assert report["strictCandidateCompleteness"]["compileValidCompleteCandidateCount"] == 0
    assert report["observableCoverage"] == {
        "scoredObservableCount": 10,
        "learnedRoutePredictedObservableCount": 4,
        "fixedDefaultObservableCount": 6,
        "fixedDefaultObservables": [
            "shoulder_slope",
            "neckline_width",
            "front_neckline_depth",
            "back_neckline_depth",
            "armhole_depth",
            "sleeve_opening_width",
        ],
    }


def test_v3_forensic_validator_rejects_rehabilitation_and_count_mutations() -> None:
    report = build_v3_forensic_erratum(ROOT)
    mutated = deepcopy(report)
    mutated["sealedV3OutcomePreserved"] = "qualified"
    assert "v3_literal_outcome_changed" in validate_v3_forensic_erratum(mutated)
    mutated = deepcopy(report)
    mutated["opaqueAlphaFailure"]["fullyOpaqueAlphaPlaneCount"] = 29
    assert "v3_opaque_alpha_count_invalid" in validate_v3_forensic_erratum(mutated)
