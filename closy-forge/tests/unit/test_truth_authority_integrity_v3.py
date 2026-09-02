from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from closy_forge.truth_authority_integrity_v3.budget_ledger import (
    budget_mutation_report,
    build_verified_budget_report,
)
from closy_forge.truth_authority_integrity_v3.changed_path_guard import (
    build_frozen_surface_guard,
)
from closy_forge.truth_authority_integrity_v3.migration_audit import (
    EXPECTED_CRLF_PATHS,
    audit_v2_lock,
    validate_audit_digest,
    validate_migration_audit,
)
from closy_forge.truth_authority_integrity_v3.output_collector import (
    executed_collector_mutation_report,
)
from closy_forge.truth_authority_integrity_v3.sealed_v2_witness import (
    LOCKED_TEST_NODE,
    verify_sealed_v2_failure,
)
from closy_forge.truth_authority_integrity_v3.successor_evaluator import (
    build_successor_protocol,
    evaluate_successor,
    executed_mutation_report,
    generic_successor_rows,
    validate_successor_rows,
)
from closy_forge.truth_authority_integrity_v3.truth_overlay import validate_truth_overlay
from closy_forge.truth_authority_integrity_v3.typed_inventory import (
    build_typed_record_inventory,
    validate_typed_record_inventory,
)

FORGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = FORGE_ROOT.parent
EVIDENCE = FORGE_ROOT / "docs/evidence/truth_authority_integrity_v3"


def _json(name: str) -> dict[str, object]:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_unit_y0_publication_is_fresh_and_non_scientific() -> None:
    subprocess.run(
        [sys.executable, "scripts/build_truth_authority_integrity_v3.py", "--check"],
        cwd=FORGE_ROOT,
        check=True,
        env={**os.environ, "PYTHONPATH": str(FORGE_ROOT / "src")},
        timeout=30,
    )
    integrity = _json("integrity_report.json")
    assert integrity["allIntegrityPredicatesPass"] is True
    assert integrity["scientificAttemptCreated"] is False
    assert all(integrity["predicates"].values())


def test_truth_overlay_uses_unambiguous_artifact_derived_counts() -> None:
    overlay = _json("truth_overlay.json")
    assert validate_truth_overlay(overlay) == []
    unit_t = overlay["unitT"]
    assert unit_t["attemptsScheduledCount"] == unit_t["attemptsExecutedCount"] == 64
    assert unit_t["predictionArtifactProducedCount"] == 60
    assert unit_t["explicitAbstentionCount"] == 4
    assert unit_t["compileRowsScheduledCount"] == unit_t["compileRowsEvaluatedCount"] == 48
    assert unit_t["legacyFullCompileSuccessCounter"] == 20
    assert unit_t["strictCompletePixelRouteCompileValidCount"] == 0
    assert unit_t["appearanceRowsScheduledCount"] == 24
    assert unit_t["appearanceRowsActuallyEvaluatedCount"] == 8
    assert unit_t["appearanceGatePassCount"] == 0
    assert overlay["unitU"]["literalOutcome"] == "dependency_blocked_before_official_seed_v2"


def test_migration_audit_proves_exact_20_raw_and_4_crlf_signature() -> None:
    audit = audit_v2_lock(REPO_ROOT)
    assert validate_migration_audit(audit) == []
    assert validate_audit_digest(audit) == []
    assert audit["lockedPathCount"] == 24
    assert audit["rawBlobExactCount"] == 20
    assert audit["lfToCrlfOnlyCount"] == 4
    assert {
        row["lockPath"] for row in audit["rows"] if row["materialization"] == "lf_to_crlf_only"
    } == EXPECTED_CRLF_PATHS
    assert all(
        row["astAndTokenEquivalent"] is True
        for row in audit["rows"]
        if row["materialization"] == "lf_to_crlf_only"
    )


def test_sealed_witness_proves_state_without_reopening_authority() -> None:
    witness = verify_sealed_v2_failure(REPO_ROOT, execute_pytest=False)
    assert witness["pass"] is True
    assert witness["lockedNodeId"] == LOCKED_TEST_NODE
    assert witness["migrationClassification"] == {
        "rawBlobExact": 20,
        "lfToCrlfOnly": 4,
        "unexplained": 0,
    }
    assert witness["sealedState"] == {
        "officialSeedCreated": False,
        "officialFixtureCount": 0,
        "authorityResultPresent": False,
        "candidateCreated": False,
        "attemptConsumed": False,
    }


def test_successor_evaluator_has_total_lineage_and_executed_mutations() -> None:
    protocol = build_successor_protocol(FORGE_ROOT)
    rows = generic_successor_rows()
    assert validate_successor_rows(protocol, rows) == []
    result = evaluate_successor(protocol, rows)
    assert result["lineageCompleteCount"] == 64
    assert result["compilerEnteredCount"] == 48
    assert result["appearanceActuallyEvaluatedCount"] == 24
    assert executed_mutation_report(FORGE_ROOT) == {
        "denominator_integrity": True,
        "hardcoded_contribution": True,
        "missing_pbr": True,
        "row_linkage": True,
        "self_declared_evidence_class": True,
        "target_derived_crop": True,
        "worst_error": True,
    }
    mutated = deepcopy(rows)
    mutated[1]["compiler"]["semanticSeamCrackMeters"] = 0.0
    assert "candidate_oracle_delta_mislabeled_as_physical_crack" in validate_successor_rows(
        protocol, mutated
    )


def test_typed_inventory_materializes_nominal_and_unique_records() -> None:
    inventory = build_typed_record_inventory(FORGE_ROOT)
    assert validate_typed_record_inventory(inventory) == []
    by_id = {row["groupId"]: row for row in inventory["groups"]}
    assert by_id["public_pixel_training"]["nominalRecordCount"] == 24
    assert by_id["public_pixel_training"]["uniqueRecordCount"] == 8
    assert by_id["d0_v3_official_qualification"]["nominalRecordCount"] == 16
    assert inventory["unrecoverableV2OpaqueCohort"]["disjointnessClaim"] == "unverified"


def test_budget_sources_order_and_all_mutation_classes_fail_closed() -> None:
    report = build_verified_budget_report(FORGE_ROOT)
    assert report["validationIssues"] == []
    assert report["derived"]["remaining"] == {
        "canonical_candidate": 1,
        "seam_model": 0,
        "topology_strategy": 0,
    }
    assert report["strategy3Reserved"] is True
    assert report["strategy3Consumed"] is True
    assert report["strategy3ScientificAdmissionExecuted"] is False
    assert all(budget_mutation_report(FORGE_ROOT).values())


def test_collector_mutations_are_executed_and_frozen_strategy_bytes_unchanged() -> None:
    assert all(executed_collector_mutation_report().values())
    guard = build_frozen_surface_guard(REPO_ROOT)
    assert guard["pathCount"] == 24
    assert guard["pass"] is True
    assert guard["strategyAlgorithmChanged"] is False
    assert guard["topologyStrategyBudgetRestored"] is False
    assert guard["newStrategyIntroduced"] is False
    for row in guard["rows"]:
        assert row["comparisonSha256"] == row["headSha256"]


def test_immutable_locked_test_git_blob_has_not_changed() -> None:
    path = "closy-forge/tests/unit/test_final_strategy3_v2_protocol.py"
    before = subprocess.check_output(
        ["git", "cat-file", "blob", f"d76916461d3e96b037fbc31b646319effef7a264:{path}"],
        cwd=REPO_ROOT,
    )
    current = subprocess.check_output(["git", "cat-file", "blob", f"HEAD:{path}"], cwd=REPO_ROOT)
    assert hashlib.sha256(before).digest() == hashlib.sha256(current).digest()
