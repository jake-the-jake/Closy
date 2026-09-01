from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

RESULT_STATUSES = frozenset({"pass", "fail", "not_run"})
ATTEMPT_STATES = frozenset(
    {
        "completed",
        "attempted_integrity_error",
        "not_attempted",
        "dependency_blocked",
    }
)
PARENT_PUBLICATION_HEAD = "69f17e0bc0d01472eec3aaf244c158181f74febf"
UNIT_I_EVIDENCE_ANCHOR = "854b85ed769bc3e67547e4195f65dfeb78878881"


def build_publication_truth() -> dict[str, Any]:
    closy = [
        _publication(
            46,
            "bc4927fe6d36667b5b236d844b4eff511ef6f987",
            "ba54b17a0aef7518d9acac30c6b7ec6564a38d87",
            "33503777760",
            29,
            historical=[
                {
                    "workflow": "Forge Unit G seed authority",
                    "runId": "33470303645",
                    "headSha": "069707bbd0bfc95eabbc5a3b3045e349d4c0b121",
                    "conclusion": "failure",
                    "attestationClass": "historical",
                    "meaning": "obsolete_pre_authority_assertion_rejected_sealed_state",
                },
                {
                    "workflow": "Forge Unit G seed authority",
                    "runId": "33503777815",
                    "headSha": "bc4927fe6d36667b5b236d844b4eff511ef6f987",
                    "conclusion": "success",
                    "attestationClass": "current",
                    "meaning": "sealed_state_validation_only",
                },
            ],
        ),
        _publication(
            47,
            "e25da69d29eb1b68885b911c7354df085f4a22c0",
            "bc4927fe6d36667b5b236d844b4eff511ef6f987",
            "33505903385",
            29,
        ),
        _publication(
            48,
            PARENT_PUBLICATION_HEAD,
            "e25da69d29eb1b68885b911c7354df085f4a22c0",
            "33511517533",
            29,
        ),
    ]
    zeroone = [
        _external(2, "13a844d240f4bbb2cafde105c4a0bdca8d89a06b", "master", []),
        _external(3, "413aecd24434f90d89ad35c6a8f909de75df34c7", "master", [2]),
        _external(
            4,
            "9cbae4a8e6ef2e61c1839ecbdf8a462aaa560027",
            "codex/closy-zeroone-dynamic-reference-v1",
            [3],
            run_id="33297149608",
            job_count=2,
        ),
    ]
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "publicationTruthVersion": "closy.d0_recovery.publication_truth.v1",
        "sourceEvidenceAnchorSha": UNIT_I_EVIDENCE_ANCHOR,
        "latestFinishedParentPublicationHeadSha": PARENT_PUBLICATION_HEAD,
        "currentUnitHeadAttestation": "pending_external_attestation",
        "attestationClasses": ["internal", "external", "historical", "inherited", "current"],
        "closyActiveTail": closy,
        "zeroOneAuthorities": zeroone,
        "widerHistoryTopology": "explicit_dag_not_one_linear_stack",
        "counts": {
            "activeTailPullRequests": len(closy),
            "zeroOneAuthorities": len(zeroone),
            "authorityRecords": len(closy) + len(zeroone),
        },
        "integrity": {"publicationTruthDigest": ""},
    }
    _rehash(document, "publicationTruthDigest")
    return document


def validate_publication_truth(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if _digest(document, "publicationTruthDigest") != _integrity(document).get(
        "publicationTruthDigest"
    ):
        issues.append("publication_truth_digest_invalid")
    closy = _records(document.get("closyActiveTail"))
    external = _records(document.get("zeroOneAuthorities"))
    counts = _mapping(document.get("counts"))
    if counts != {
        "activeTailPullRequests": len(closy),
        "zeroOneAuthorities": len(external),
        "authorityRecords": len(closy) + len(external),
    }:
        issues.append("publication_counts_not_derived")
    for row in closy:
        current = _mapping(row.get("currentForgeRun"))
        if current.get("headSha") != row.get("publicationHeadSha"):
            issues.append(f"exact_head_sha_mismatch:pr{row.get('pullRequest')}")
        if current.get("forgeSuccessfulJobs") != current.get("forgeTotalJobs"):
            issues.append(f"forge_success_count_invalid:pr{row.get('pullRequest')}")
        aggregate = _mapping(row.get("aggregateChecks"))
        if aggregate.get("skippedNonForgeChecks") != 1:
            issues.append(f"skipped_check_missing:pr{row.get('pullRequest')}")
        if aggregate.get("successfulChecks") != int(current.get("forgeSuccessfulJobs", -1)):
            issues.append(f"skipped_counted_as_success:pr{row.get('pullRequest')}")
    if {int(row.get("pullRequest", -1)) for row in external} != {2, 3, 4}:
        issues.append("zeroone_authority_inventory_invalid")
    if document.get("latestFinishedParentPublicationHeadSha") == UNIT_I_EVIDENCE_ANCHOR:
        issues.append("inherited_anchor_presented_as_publication_head")
    if document.get("currentUnitHeadAttestation") != "pending_external_attestation":
        issues.append("recursive_current_head_claim")
    return sorted(set(issues))


def build_result_semantics() -> dict[str, Any]:
    rows = [
        _result("D0-RP-03", "fail", "completed", "partial", "unit_g_zero_compiles"),
        _result(
            "D0-RP-04",
            "fail",
            "attempted_integrity_error",
            "partial",
            "unit_g_evaluator_harness_failed_before_worker_dispatch",
        ),
        _result("D0-RP-06", "fail", "completed", "partial", "identity_disjoint_scope_failed"),
        _result("D0-RP-07", "fail", "completed", "partial", "zero_appearance_evaluations"),
        _result("D0-RP-08", "fail", "attempted_integrity_error", "partial", "unit_h_h4_0_of_8"),
    ]
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "semanticsVersion": "closy.d0_recovery.result_semantics.v1",
        "allowedResultStatuses": sorted(RESULT_STATUSES),
        "unitG": {
            "outcome": "benchmark_failed_fixed_inventory_unfinished",
            "predictions": 64,
            "canonicalCompiles": 0,
            "appearanceEvaluations": 0,
            "preservationGreenDoesNotMeanCapabilityPass": True,
        },
        "strictC3": {
            "legacyC3BindingD0MaySatisfyD0Rp08": False,
            "unitHResult": "fail",
            "unitHAttemptConsumed": True,
            "heldOutPasses": 0,
            "heldOutDenominator": 8,
        },
        "unitI": {
            "outcomeClass": "M",
            "logicalJOutcome": "J-A_post_topology_candidate_unavailable",
            "candidateAttemptConsumed": False,
        },
        "rows": rows,
        "integrity": {"resultSemanticsDigest": ""},
    }
    _rehash(document, "resultSemanticsDigest")
    return document


def validate_result_semantics(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if _digest(document, "resultSemanticsDigest") != _integrity(document).get(
        "resultSemanticsDigest"
    ):
        issues.append("result_semantics_digest_invalid")
    for row in _records(document.get("rows")):
        if row.get("result") not in RESULT_STATUSES:
            issues.append(f"result_enum_invalid:{row.get('rowId')}")
        if row.get("attemptState") not in ATTEMPT_STATES:
            issues.append(f"attempt_state_invalid:{row.get('rowId')}")
        if row.get("result") == row.get("coverage"):
            issues.append(f"coverage_used_as_result:{row.get('rowId')}")
    rp04 = next(
        (row for row in _records(document.get("rows")) if row.get("rowId") == "D0-RP-04"), {}
    )
    if rp04.get("result") != "fail" or rp04.get("attemptState") != "attempted_integrity_error":
        issues.append("unit_g_rp04_semantics_invalid")
    strict = _mapping(document.get("strictC3"))
    if strict.get("legacyC3BindingD0MaySatisfyD0Rp08") is not False:
        issues.append("legacy_c3_promoted_to_strict")
    if (
        _mapping(document.get("unitG")).get("preservationGreenDoesNotMeanCapabilityPass")
        is not True
    ):
        issues.append("failed_result_summarized_as_capability_pass")
    return sorted(set(issues))


def build_budget_authority(root: Path) -> dict[str, Any]:
    sources = [
        "docs/evidence/phy1_topology_v2/phy1_experiment.json",
        "docs/evidence/phy1_seam_support_v3/neutral_preflight.json",
        "docs/evidence/phy1_topology_strategy2_v4/physical_attempt_registry.json",
    ]
    attempts: list[dict[str, Any]] = []
    previous = ""
    for ordinal, relative in enumerate(sources, start=1):
        path = root / relative
        entry: dict[str, Any] = {
            "ordinal": ordinal,
            "sourcePath": relative,
            "sourceSha256": sha256_file(path),
            "historicalLinkState": "historical_unlinked_root"
            if ordinal == 1
            else "successor_index_link",
            "previousIndexEntryHash": previous,
            "entryHash": "",
        }
        entry["entryHash"] = sha256_bytes(
            canonical_dumps({**entry, "entryHash": ""}).encode("utf-8")
        )
        previous = entry["entryHash"]
        attempts.append(entry)
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "authorityVersion": "closy.global_physical_attempt_chain.v1",
        "appendOnlyFromUnitL": True,
        "historicalLinksNotFabricated": True,
        "attempts": attempts,
        "headHash": previous,
        "budgets": {
            "seamModelsRemaining": 0,
            "topologyStrategiesRemainingBeforeUnitP": 1,
            "unitODiagnosisConsumesStrategy": False,
            "unitPStrategiesMaximum": 1,
            "unitPCandidatesMaximum": 1,
            "strategySlotClosed": False,
            "candidateAttemptConsumed": False,
            "ccdStrategiesRemainSeparatelyClassified": True,
        },
        "labelReconciliation": {
            "reservedFinalStrategyId": "PHY1-V5-S3-CONSTRAINED-REMESH-TRANSFER",
            "oldStrategy3LabelsSubstitutable": False,
        },
        "integrity": {"budgetAuthorityDigest": ""},
    }
    _rehash(document, "budgetAuthorityDigest")
    return document


def validate_budget_authority(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    previous = ""
    for expected, row in enumerate(_records(document.get("attempts")), start=1):
        if row.get("ordinal") != expected or row.get("previousIndexEntryHash") != previous:
            issues.append(f"physical_chain_link_invalid:{expected}")
        actual = sha256_bytes(canonical_dumps({**row, "entryHash": ""}).encode("utf-8"))
        if row.get("entryHash") != actual:
            issues.append(f"physical_chain_entry_hash_invalid:{expected}")
        previous = str(row.get("entryHash", ""))
    if document.get("headHash") != previous:
        issues.append("physical_chain_head_invalid")
    budget = _mapping(document.get("budgets"))
    expected_budget = {
        "seamModelsRemaining": 0,
        "topologyStrategiesRemainingBeforeUnitP": 1,
        "unitODiagnosisConsumesStrategy": False,
        "unitPStrategiesMaximum": 1,
        "unitPCandidatesMaximum": 1,
        "strategySlotClosed": False,
        "candidateAttemptConsumed": False,
        "ccdStrategiesRemainSeparatelyClassified": True,
    }
    if budget != expected_budget:
        issues.append("physical_budget_invalid")
    if (
        _mapping(document.get("labelReconciliation")).get("oldStrategy3LabelsSubstitutable")
        is not False
    ):
        issues.append("old_strategy3_alias_allowed")
    if _digest(document, "budgetAuthorityDigest") != _integrity(document).get(
        "budgetAuthorityDigest"
    ):
        issues.append("budget_authority_digest_invalid")
    return sorted(set(issues))


def _publication(
    number: int,
    head: str,
    parent: str,
    run_id: str,
    jobs: int,
    *,
    historical: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "repository": "jake-the-jake/Closy",
        "pullRequest": number,
        "sourceEvidenceAnchorSha": UNIT_I_EVIDENCE_ANCHOR if number == 48 else head,
        "publicationHeadSha": head,
        "exactParentHeadSha": parent,
        "attestationClass": "current",
        "currentForgeRun": {
            "runId": run_id,
            "headSha": head,
            "conclusion": "success",
            "forgeSuccessfulJobs": jobs,
            "forgeTotalJobs": jobs,
        },
        "aggregateChecks": {
            "successfulChecks": jobs,
            "skippedNonForgeChecks": 1,
            "failedChecks": 0,
        },
        "historicalRuns": historical or [],
    }


def _external(
    number: int,
    head: str,
    base: str,
    dependencies: list[int],
    *,
    run_id: str | None = None,
    job_count: int = 0,
) -> dict[str, Any]:
    return {
        "repository": "jake-the-jake/ZeroOne",
        "pullRequest": number,
        "publicationHeadSha": head,
        "baseBranch": base,
        "logicalDependencies": dependencies,
        "attestationClass": "external",
        "exactHeadRun": None
        if run_id is None
        else {"runId": run_id, "headSha": head, "conclusion": "success", "jobCount": job_count},
    }


def _result(row: str, result: str, attempt: str, coverage: str, reason: str) -> dict[str, str]:
    return {
        "rowId": row,
        "result": result,
        "attemptState": attempt,
        "coverage": coverage,
        "reason": reason,
    }


def _rehash(document: dict[str, Any], field: str) -> None:
    document["integrity"][field] = _digest(document, field)


def _digest(document: Mapping[str, Any], field: str) -> str:
    payload = deepcopy(dict(document))
    integrity = _mapping(payload.get("integrity"))
    integrity[field] = ""
    payload["integrity"] = integrity
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _integrity(document: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping(document.get("integrity"))


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: object) -> list[dict[str, Any]]:
    return [_mapping(item) for item in value] if isinstance(value, list) else []
