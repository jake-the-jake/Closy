from __future__ import annotations

from closy_forge.bounded_models.integrated_evaluation_v2 import (
    build_integrated_phase14_evaluation,
)


def test_integrated_phase14_keeps_outcomes_out_of_features_and_authority_bounded() -> None:
    result = build_integrated_phase14_evaluation(
        e1={
            "E1": {"status": "partial"},
            "unassisted": {"acceptedCount": 4, "learnedSuccessCount": 2},
        },
        e2={
            "acceptance": {"status": "executed_feasibility_partial"},
            "metrics": {"acceptedCount": 48, "macroStructureTokenF1": 0.5},
        },
        source_context={"fixture": True},
    )
    assert result["dataset"]["preOutcomeFeaturesSeparated"] is True
    assert result["dataset"]["phase9OutcomesUsedAsFeatures"] is False
    assert result["evaluation"]["material"]["topOneCorrect"] == 10
    assert result["evaluation"]["failureAndQuality"]["macroF1"] == 0.704125286478
    assert result["confidenceIntervals"]["materialTopOne95"]["lower"] >= 0.0
    assert result["authority"]["deterministicValidatorsFinal"] is True
    assert result["largeModelBoundary"]["execution"] == "not_run"
    assert result["claims"]["globalPhase14Complete"] is False
