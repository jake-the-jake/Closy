from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from closy_forge.layer_collision.contracts import LayerCollisionError
from closy_forge.layer_collision.fixtures import (
    _accepted_specs,
    build_layer_collision_capability_manifest,
    run_layer_collision_suite,
    validate_layer_report,
)
from closy_forge.layer_collision.solver import run_simultaneous_layer_solve


def test_capability_manifest_is_frozen_and_budgeted() -> None:
    manifest = build_layer_collision_capability_manifest()
    assert len(manifest["acceptedCases"]) == 9
    assert len(manifest["rejectionCases"]) == 4
    assert manifest["strategyBudget"] == {
        "maximumStrategies": 2,
        "executedStrategies": 2,
        "maximumTuningTrialsPerStrategy": 4,
        "executedTuningTrials": 2,
    }


def test_suite_executes_every_simultaneous_case_and_adversarial_rejection() -> None:
    suite = run_layer_collision_suite()
    assert suite["inventoryExact"] is True
    assert suite["summary"]["acceptedPassCount"] == 9
    assert suite["summary"]["rejectionPassCount"] == 4
    assert suite["summary"]["allSimultaneousSolvesExecuted"] is True
    assert suite["summary"]["allDifferentMaterialsExecuted"] is True
    assert suite["summary"]["globalPhase13Accepted"] is False


@pytest.mark.parametrize("spec", _accepted_specs(), ids=lambda item: item.case_id)
def test_simultaneous_solver_preserves_layer_invariants(spec: Any) -> None:
    report = run_simultaneous_layer_solve(spec)
    manifest = build_layer_collision_capability_manifest()
    assert validate_layer_report(report, manifest["thresholds"]) == []
    assert report["simultaneousLayerCount"] >= 2
    assert report["truth"]["realSimultaneousSolve"] is True
    assert report["truth"]["sequentialSingleGarmentSolve"] is False
    assert report["response"]["bothSidesMoved"] is True
    assert report["finalMetrics"]["bridgeConstraintCount"] == 0


def test_no_issue_free_report_is_allowed_when_solver_did_not_execute() -> None:
    report = {
        "solverExecuted": False,
        "finalMetrics": {},
        "response": {},
        "broadPhase": {},
    }
    issues = validate_layer_report(
        report, build_layer_collision_capability_manifest()["thresholds"]
    )
    assert issues == ["simultaneous_solver_not_executed"]


def test_unknown_parent_fails_closed() -> None:
    spec = _accepted_specs()[0]
    bad = replace(
        spec,
        layers=(spec.layers[0], replace(spec.layers[1], parent_layer_id="layer.missing")),
    )
    with pytest.raises(LayerCollisionError, match="missing_parent_layer_id"):
        run_simultaneous_layer_solve(bad)


def test_solver_report_is_deterministic() -> None:
    spec = _accepted_specs()[3]
    first = run_simultaneous_layer_solve(spec)
    second = run_simultaneous_layer_solve(spec)
    assert first["integrity"]["reportHash"] == second["integrity"]["reportHash"]
