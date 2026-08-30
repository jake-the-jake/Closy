from __future__ import annotations

from pathlib import Path

from closy_forge.bounded_models.integrated_evaluation_v3 import (
    build_integrated_phase14_evaluation_v3,
)
from closy_forge.package_io.canonical_json import read_json


def test_phase14_v3_fixes_ablations_cluster_bootstrap_and_regret_reporting() -> None:
    thresholds = read_json(
        Path(__file__).resolve().parents[2]
        / "docs"
        / "phase9_structured_threshold_registry_v3.json"
    )
    result = build_integrated_phase14_evaluation_v3(
        e1={
            "acceptance": {
                "status": "partial",
                "promotionClass": "losing_experiment",
                "learnedRouteDefault": False,
            }
        },
        e2={
            "acceptance": {"status": "failed", "learnedRouteDefault": False},
            "metrics": {"truePerTokenMacroF1": 0.53},
        },
        source_context={
            "z1": {
                "defaultFamilies": {"passed": 9, "total": 9},
                "parameterBreadth": {"passed": 6, "total": 25},
            },
            "c3": {"status": "scoped_pass_global_partial"},
            "phy1": {"status": "failed"},
        },
        thresholds=thresholds,
    )

    assert result["evaluationCorrections"]["formerAcceptedFilterBugPresent"] is False
    assert result["confidenceIntervals"]["clusterKey"] == "scenarioId"
    assert result["confidenceIntervals"]["correlatedMaterialRowsKeptTogether"] is True
    assert result["evaluation"]["material"]["topOneAccuracy"] == 0.555555555556
    assert result["evaluation"]["material"]["p95NormalizedSelectionRegret"] == 1.0
    assert all(item["predictedCount"] > 0 for item in result["ablations"].values())
    assert all(item["failureMacroF1"] is not None for item in result["ablations"].values())
    assert result["dataset"]["currentExecutablePathSources"]["z1"] == {
        "defaultFamilies": {"passed": 9, "total": 9},
        "parameterBreadth": {"passed": 6, "total": 25},
    }
    assert result["evaluation"]["failureAndQuality"]["perTarget"]["excessiveStrain"]["f1"] == 0.4
    assert result["evaluation"]["failureAndQuality"]["perTarget"]["seamContinuityRisk"]["f1"] == 0.4
    assert result["acceptance"]["status"] == "partial"
    assert result["authority"]["deterministicValidatorsFinal"] is True
    assert result["dataset"]["solverBackedReplacementCorpus"]["status"] == "not_run"
