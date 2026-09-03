from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from closy_forge.solver_material_v1.real_coupon import (
    CouponValidationError,
    parse_csv_bytes,
    parse_json_bytes,
)
from closy_forge.solver_material_v1.result_decoder import independently_check_result
from closy_forge.solver_material_v1.retrospective_evaluator import evaluate_retrospective

ROOT = Path(__file__).resolve().parents[2]


def test_retrospective_evaluator_conserves_every_terminal_cell() -> None:
    result = evaluate_retrospective(ROOT / "fixtures/solver_material_v1/locked_corpus.json")
    assert result["engineeringAcceptance"] == "failed"
    assert result["scientificQualification"] == "ineligible_test_exposed_before_estimator"
    assert result["denominators"] == {
        "tupleRows": 16,
        "estimatedFieldCells": 96,
        "abstainedFieldCells": 32,
        "unsupportedCapabilityCells": 16,
        "totalTerminalCells": 144,
        "droppedRows": 0,
    }
    assert result["terminalConservation"]["conserved"] is True
    assert independently_check_result(result)["status"] == "passed"


def test_empty_real_coupon_templates_parse_without_fabricating_measurements() -> None:
    fixture = ROOT / "fixtures/real_coupon_v1"
    assert parse_csv_bytes((fixture / "empty_template.csv").read_bytes()) == []
    assert parse_json_bytes((fixture / "empty_template.json").read_bytes()) == []


def test_real_coupon_corruption_cases_fail_closed() -> None:
    fixture = ROOT / "fixtures/real_coupon_v1/corruption_cases.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        with pytest.raises(CouponValidationError, match=case["expected"]):
            parse_json_bytes(case["payload"].encode())


def test_retrospective_rejects_lineage_and_denominator_corruption(tmp_path: Path) -> None:
    source = json.loads(
        (ROOT / "fixtures/solver_material_v1/locked_corpus.json").read_text(encoding="utf-8")
    )
    cases = []
    wrong_solver = deepcopy(source)
    wrong_solver["rows"][48]["coupons"][0]["solverVersion"] = "wrong"
    cases.append((wrong_solver, "forward_solver_version_invalid"))
    duplicate = deepcopy(source)
    duplicate["rows"][49]["tupleId"] = duplicate["rows"][48]["tupleId"]
    cases.append((duplicate, "locked_tuple_denominator_invalid"))
    extra = deepcopy(source)
    extra["rows"][48]["unexpectedTruth"] = 1
    cases.append((extra, "unexpected_truth_or_metadata_field"))
    non_finite = deepcopy(source)
    non_finite["rows"][48]["coupons"][0]["observable"] = "NaN"
    cases.append((non_finite, "coupon_numeric_non_finite"))
    for index, (payload, reason) in enumerate(cases):
        payload["corpusDigest"] = "200060cb27440b53ee823eecabe822e21bb540bc205d340c46f72c82f010f068"
        path = tmp_path / f"case-{index}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match=reason):
            evaluate_retrospective(path)
