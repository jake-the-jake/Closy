from __future__ import annotations

from pathlib import Path

from closy_forge.package_io.canonical_json import read_json
from closy_forge.phy1_topology_strategy2_v4.evidence import (
    validate_committed_unit_i_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/phy1_topology_strategy2_v4"


def test_consumed_strategy_microfixture_is_literal_and_not_reexecuted() -> None:
    assert validate_committed_unit_i_evidence(ROOT) == []
    result = read_json(EVIDENCE / "strategy_microfixtures.json")
    assert result["status"] == "fail"
    assert set(result["failedChecks"]) == {
        "normalSeparationEquivalent",
        "tangentialSlipEquivalent",
        "storedEnergyEquivalent",
        "impulseEquivalent",
    }
    assert result["equivalence"]["differences"]["positionMeters"] > 1e-12


def test_outcome_m_closes_logical_j_a_and_blocks_j_and_k() -> None:
    outcome = read_json(EVIDENCE / "unit_i_outcome.json")
    closure = read_json(EVIDENCE / "logical_j_a_closure.json")
    assert outcome["outcomeClass"] == "M"
    assert outcome["candidateAttemptConsumed"] is False
    assert outcome["remainingBudgets"] == {"reservedTopologyStrategies": 1, "seamModels": 0}
    assert closure["logicalOutcome"] == "J-A: post_topology_candidate_unavailable"
    assert closure["unitJBranchAuthorized"] is False
    assert closure["unitKEligible"] is False
    assert closure["nextHandoff"]["selection"] == "none_dependency_ready"
