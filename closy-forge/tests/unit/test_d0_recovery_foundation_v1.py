from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path

import pytest

from closy_forge.package_io.hashing import sha256_file
from closy_forge.phy1_topology_strategy2_v4.diagnosis import (
    RECOMPUTATION_ULP_POLICY,
    _compare_recomputed_diagnosis,
)
from closy_forge.recovery_foundation_v1.c3_v5 import (
    adapt_frame_metrics,
    run_generic_c3_fixtures,
)
from closy_forge.recovery_foundation_v1.contestant_boundary import (
    build_boundary_capability,
    execute_contestant,
    validate_output_path,
)
from closy_forge.recovery_foundation_v1.contracts import (
    build_budget_authority,
    build_publication_truth,
    build_result_semantics,
    validate_budget_authority,
    validate_publication_truth,
    validate_result_semantics,
)
from closy_forge.recovery_foundation_v1.evaluator_v2 import (
    audit_contestant_source,
    audit_disjointness,
    evaluate_generic_rows,
    generic_protocol,
    generic_rows,
    load_declared_artifact,
    run_generic_mutation_fixtures,
)
from closy_forge.recovery_foundation_v1.sentinel import (
    REQUIRED_PATHS,
    resolve_sentinel,
    validate_sentinel_resolution,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FORGE_ROOT = REPO_ROOT / "closy-forge"
FROZEN_DIAGNOSIS = FORGE_ROOT / "docs/evidence/phy1_topology_strategy2_v4/diagnosis.json"
FROZEN_DIAGNOSIS_SHA256 = "45ff32d3bf655a129ac01b9a6e47e8bdde4518e4701385a786b265f2c6884454"


def test_publication_truth_separates_anchors_heads_runs_and_check_classes() -> None:
    truth = build_publication_truth()

    assert validate_publication_truth(truth) == []
    assert truth["sourceEvidenceAnchorSha"] != truth["latestFinishedParentPublicationHeadSha"]
    assert truth["currentUnitHeadAttestation"] == "pending_external_attestation"
    assert truth["counts"] == {
        "activeTailPullRequests": len(truth["closyActiveTail"]),
        "zeroOneAuthorities": len(truth["zeroOneAuthorities"]),
        "authorityRecords": len(truth["closyActiveTail"]) + len(truth["zeroOneAuthorities"]),
    }
    unit_g = next(row for row in truth["closyActiveTail"] if row["pullRequest"] == 46)
    assert {row["conclusion"] for row in unit_g["historicalRuns"]} == {"failure", "success"}
    assert {row["pullRequest"] for row in truth["zeroOneAuthorities"]} == {2, 3, 4}


@pytest.mark.parametrize(
    ("mutation", "issue"),
    [
        (
            lambda value: value["closyActiveTail"][0]["currentForgeRun"].update(
                {"headSha": "0" * 40}
            ),
            "exact_head_sha_mismatch:pr46",
        ),
        (
            lambda value: value["closyActiveTail"][0]["aggregateChecks"].update(
                {"successfulChecks": 30}
            ),
            "skipped_counted_as_success:pr46",
        ),
        (
            lambda value: value.update(
                {"latestFinishedParentPublicationHeadSha": value["sourceEvidenceAnchorSha"]}
            ),
            "inherited_anchor_presented_as_publication_head",
        ),
    ],
)
def test_publication_truth_mutations_fail_closed(mutation: object, issue: str) -> None:
    truth = build_publication_truth()
    assert callable(mutation)
    mutation(truth)
    assert issue in validate_publication_truth(truth)


def test_result_semantics_keep_result_attempt_and_coverage_disjoint() -> None:
    semantics = build_result_semantics()

    assert validate_result_semantics(semantics) == []
    rp04 = next(row for row in semantics["rows"] if row["rowId"] == "D0-RP-04")
    assert rp04 == {
        "rowId": "D0-RP-04",
        "result": "fail",
        "attemptState": "attempted_integrity_error",
        "coverage": "partial",
        "reason": "unit_g_evaluator_harness_failed_before_worker_dispatch",
    }
    assert semantics["strictC3"]["legacyC3BindingD0MaySatisfyD0Rp08"] is False

    mutated = deepcopy(semantics)
    rp04_mutated = next(row for row in mutated["rows"] if row["rowId"] == "D0-RP-04")
    rp04_mutated["result"] = "partial"
    assert "result_enum_invalid:D0-RP-04" in validate_result_semantics(mutated)


def test_global_physical_chain_and_budgets_are_hash_linked_and_separate() -> None:
    authority = build_budget_authority(FORGE_ROOT)

    assert validate_budget_authority(authority) == []
    assert authority["attempts"][0]["historicalLinkState"] == "historical_unlinked_root"
    assert authority["budgets"]["seamModelsRemaining"] == 0
    assert authority["budgets"]["topologyStrategiesRemainingBeforeUnitP"] == 1
    assert authority["budgets"]["unitODiagnosisConsumesStrategy"] is False
    assert authority["budgets"]["strategySlotClosed"] is False
    assert authority["budgets"]["candidateAttemptConsumed"] is False

    mutated = deepcopy(authority)
    mutated["attempts"][1]["previousIndexEntryHash"] = "0" * 64
    assert "physical_chain_link_invalid:2" in validate_budget_authority(mutated)


def test_ulp_policy_is_pointer_specific_bounded_and_preserves_frozen_digest() -> None:
    pointer = "/deformationByPanel/0/areaRatio/minimum"
    values = RECOMPUTATION_ULP_POLICY["pointers"][pointer]["documentedValues"]
    state = {"allowedExceptionsUsed": 0}
    issues: list[str] = []

    _compare_recomputed_diagnosis(values[0], values[1], pointer, issues, state)
    assert issues == []
    assert state["allowedExceptionsUsed"] == 1

    second_issues: list[str] = []
    _compare_recomputed_diagnosis(values[0], values[1], "/energy/value", second_issues, state)
    assert second_issues == ["diagnosis_value_differs:/energy/value"]

    large_issues: list[str] = []
    _compare_recomputed_diagnosis(
        values[0], values[0] + 4 * math.ulp(values[0]), pointer, large_issues, state
    )
    assert large_issues == [f"diagnosis_value_differs:{pointer}"]

    nonfinite_issues: list[str] = []
    _compare_recomputed_diagnosis(math.inf, math.inf, pointer, nonfinite_issues, state)
    assert nonfinite_issues == [f"diagnosis_value_differs:{pointer}"]
    assert sha256_file(FROZEN_DIAGNOSIS) == FROZEN_DIAGNOSIS_SHA256


def test_evaluator_v2_loads_declared_shapes_and_runs_every_gate_mutation(tmp_path: Path) -> None:
    mapping = tmp_path / "mapping.json"
    sequence = tmp_path / "list.json"
    mapping.write_text('{"kind":"mapping"}', encoding="utf-8")
    sequence.write_text('[{"kind":"list"}]', encoding="utf-8")

    assert load_declared_artifact(mapping, declared_shape="mapping") == {"kind": "mapping"}
    assert load_declared_artifact(sequence, declared_shape="list") == [{"kind": "list"}]
    with pytest.raises(ValueError, match="mapping_artifact_required"):
        load_declared_artifact(sequence, declared_shape="mapping")

    report = run_generic_mutation_fixtures()
    assert report["allPassed"] is True
    assert report["freshEvaluatorIdentityRealized"] is False
    assert report["freshTargetRealized"] is False
    assert set(report["gateFamilyMutations"]) == {
        "pattern",
        "seam",
        "opening",
        "topology",
        "simulation",
        "binding",
        "source_silhouette",
        "landmark",
        "appearance",
        "texture_identity",
        "pbr_integrity",
        "reproducibility",
    }


def test_evaluator_v2_retains_failures_rejects_leakage_and_derives_contribution() -> None:
    rows = generic_rows()
    rows.pop()
    result = evaluate_generic_rows(generic_protocol(), rows)

    assert len(result["records"]) == 48
    assert len(result["missingItems"]) == 1
    assert result["failuresRetainedInDenominator"] is True
    assert result["rowDecisions"]["D0-RP-03"] in {"pass", "fail"}
    assert result["rowDecisions"]["D0-RP-06"] in {"pass", "fail"}
    assert audit_contestant_source("TARGET_UV_BOUNDS = [0, 1]") == [
        "forbidden_target_feature_token:target_uv_bounds"
    ]

    inventories = {
        "unit_f": [{"identity": "a", "geometryHash": "g1", "pixelHash": "p1"}],
        "phase9": [{"identity": "b", "geometryHash": "g2", "pixelHash": "p2"}],
        "fresh_candidate": [{"identity": "c", "geometryHash": "g1", "pixelHash": "p3"}],
    }
    audit = audit_disjointness(inventories)
    assert audit["allDisjoint"] is False
    assert audit["duplicateFields"]["geometryHash"] == ["g1"]


def test_contestant_boundary_is_deny_by_default_and_honestly_scoped(tmp_path: Path) -> None:
    good = tmp_path / "good.py"
    good.write_text(
        "import json,sys\nsource=json.load(open(sys.argv[1], encoding='utf-8'))\n"
        "json.dump({'roleCount':len(source['roles']),'env':sorted(__import__('os').environ)},"
        "open(sys.argv[2],'w',encoding='utf-8'))\n",
        encoding="utf-8",
    )
    output, report = execute_contestant(
        contestant=good, source_roles={"front.png": b"synthetic"}, config={"route": "fixture"}
    )
    assert output["roleCount"] == 1
    assert set(output["env"]) <= {
        "CLOSY_CONTESTANT",
        "PYTHONDONTWRITEBYTECODE",
        "SYSTEMROOT",
    }
    assert report["status"] == "pass"
    assert report["allOpenedFilesAllowed"] is True
    assert report["qualificationD0Rp04IsolationPass"] is False
    assert report["isolationClass"] == "application_process_isolation_only"
    assert build_boundary_capability()["currentCanonicalQualificationIsolationPass"] is False

    outside = tmp_path / "outside.txt"
    outside.write_text("target", encoding="utf-8")
    attacker = tmp_path / "attacker.py"
    attacker.write_text(f"open({str(outside)!r}, encoding='utf-8').read()\n", encoding="utf-8")
    _, denied = execute_contestant(
        contestant=attacker, source_roles={"front.png": b"synthetic"}, config={}
    )
    assert denied["status"] == "fail"
    assert "PermissionError:contestant_read_outside_allowlist" in denied["failureClass"]

    with pytest.raises(ValueError, match="outside_workspace"):
        validate_output_path(tmp_path / "workspace", Path("../escape.json"))


def test_c3_v5_generic_fixtures_and_schema_fail_closed() -> None:
    report = run_generic_c3_fixtures()

    assert report["allPassed"] is True
    assert report["freshHeldOutPoseRealized"] is False
    assert report["qualificationAttemptConsumed"] is False
    assert report["oracle"]["callsCandidateReconstruction"] is False
    with pytest.raises(ValueError, match="source_version_unsupported"):
        adapt_frame_metrics({}, source_version="unknown")


def test_sentinel_resolver_reopens_required_blobs_and_executes_pr43_fallback() -> None:
    unit_f = resolve_sentinel(FORGE_ROOT)
    fallback = resolve_sentinel(FORGE_ROOT, force_unit_f_failure=True)

    assert validate_sentinel_resolution(unit_f) == []
    assert validate_sentinel_resolution(fallback) == []
    assert unit_f["resolutionOutcome"] == "unit_f_exact_candidate"
    assert fallback["resolutionOutcome"] == "pr43_exact_candidate_fallback"
    assert {row["path"] for row in unit_f["requiredAncestorBlobs"]} == set(REQUIRED_PATHS)
    assert unit_f["unitGCandidatesEligible"] is False
