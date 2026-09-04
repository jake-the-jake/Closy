from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from closy_forge.solver_material_v1.real_coupon import (
    MAX_COUPON_BYTES,
    CouponValidationError,
    import_coupon,
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


def test_canonical_publication_and_manifest_are_independently_consistent() -> None:
    evidence = ROOT / "docs/evidence/phase7_solver_material_v1"
    result = json.loads((evidence / "retrospective_result.json").read_text(encoding="utf-8"))
    manifest = json.loads((evidence / "publication_manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads(
        (evidence / "independent_checker_receipt.json").read_text(encoding="utf-8")
    )
    assert independently_check_result(result)["status"] == "passed"
    assert receipt["resultDigest"] == result["resultDigest"]
    assert receipt["schemaValidation"] == "passed"
    for row in manifest["files"]:
        payload = (evidence / row["path"]).read_bytes()
        assert len(payload) == row["byteCount"]
        assert hashlib.sha256(payload).hexdigest() == row["sha256"]


def test_post_hoc_diagnostics_cannot_upgrade_canonical_result() -> None:
    evidence = ROOT / "docs/evidence/phase7_solver_material_v1"
    diagnostics = json.loads((evidence / "post_hoc_diagnostics.json").read_text())
    assert diagnostics["classification"] == "post_hoc_non_qualification"
    assert diagnostics["changesCanonicalResult"] is False
    assert diagnostics["inactivePathAudit"] == {
        "contactControlAndInclinedContactStateObservableDiagnosticsByteEquivalent": True,
        "contactPairRowCount": 64,
        "frictionDistinctInterventionResponses": 2,
        "frictionTrajectoryResponds": False,
        "restitutionDistinctInterventionResponses": 1,
        "restitutionTrajectoryResponds": False,
        "verticalDropRowCount": 64,
        "verticalDropZeroContactRowCount": 64,
    }
    assert diagnostics["convergenceErratum"]["isConvergenceProof"] is False


def test_real_coupon_import_is_bounded_and_rejects_unknown_formats(tmp_path: Path) -> None:
    unknown = tmp_path / "coupon.txt"
    unknown.write_text("{}", encoding="utf-8")
    with pytest.raises(CouponValidationError, match="coupon_source_format_unsupported"):
        import_coupon(unknown)
    with pytest.raises(CouponValidationError, match="coupon_payload_too_large"):
        parse_json_bytes(b" " * (MAX_COUPON_BYTES + 1))


def test_canonical_publication_regenerates_byte_for_byte() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/evaluate_solver_material_v1.py", "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
