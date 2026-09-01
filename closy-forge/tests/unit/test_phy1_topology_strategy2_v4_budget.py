from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from closy_forge.package_io.canonical_json import read_json
from closy_forge.phy1_topology_strategy2_v4.budget import (
    build_budget_classifier,
    classify_change,
    validate_budget_classifier,
)

ROOT = Path(__file__).resolve().parents[2]


def test_unit_i_budget_classifier_is_frozen_before_strategy_implementation() -> None:
    committed = read_json(ROOT / "fixtures/phy1_topology_strategy2_v4/budget_classifier.json")
    assert committed == build_budget_classifier()
    assert validate_budget_classifier(dict(committed)) == []
    assert (
        classify_change(dict(committed), "topology_or_dof_representation")["authorizedInUnitI"]
        is True
    )
    assert (
        classify_change(dict(committed), "seam_constitutive_or_enforcement_model")[
            "authorizedInUnitI"
        ]
        is False
    )


def test_unit_i_budget_classifier_fails_closed_on_mutation() -> None:
    mutated = deepcopy(build_budget_classifier())
    mutated["budget"]["seamModelsRemaining"] = 1
    assert set(validate_budget_classifier(mutated)) == {
        "classifier_digest_mismatch",
        "seam_budget_reopened",
    }
