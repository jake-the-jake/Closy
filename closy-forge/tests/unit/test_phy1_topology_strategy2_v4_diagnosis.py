from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from closy_forge.package_io.canonical_json import read_json
from closy_forge.phy1_topology_strategy2_v4.diagnosis import (
    build_general_microfixtures,
    validate_pr43_diagnosis,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/phy1_topology_strategy2_v4"


def test_pr43_diagnosis_reopens_immutable_trajectory_without_rerun() -> None:
    actual = read_json(EVIDENCE / "diagnosis.json")
    assert validate_pr43_diagnosis(ROOT, dict(actual)) == []
    assert actual["observability"]["persistedTrajectoryFrames"] == 49
    assert actual["observability"]["perConstraintResidualByClassAndIteration"]["status"] == (
        "historical_only_not_persisted"
    )
    assert actual["seams"]["maximumNormalResidualMeters"] == 0.041513220488
    assert actual["contacts"]["finalSelf"]["unresolvedContactCount"] == 242
    assert len(actual["deformationByPanel"]) == 5
    corrupted = deepcopy(actual)
    corrupted["deformationByPanel"][0]["areaRatio"]["minimum"] += 1e-6
    assert set(validate_pr43_diagnosis(ROOT, corrupted)) == {
        "committed_diagnosis_digest_invalid",
        "diagnosis_value_differs:/deformationByPanel/0/areaRatio/minimum",
    }


def test_candidate_independent_general_microfixtures_are_fresh() -> None:
    expected = build_general_microfixtures()
    assert read_json(EVIDENCE / "general_microfixtures.json") == expected
    assert expected["candidateIndependent"] is True
    assert expected["status"] == "pass"
    assert all(expected["corruptionControls"].values())
