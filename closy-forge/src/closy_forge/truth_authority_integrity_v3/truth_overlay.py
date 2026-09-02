from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file

from .budget_ledger import budget_mutation_report, build_verified_budget_report
from .changed_path_guard import build_frozen_surface_guard
from .common import canonical_digest, load_mapping, mapping, records
from .migration_audit import audit_v2_lock, validate_audit_digest, validate_migration_audit
from .output_collector import executed_collector_mutation_report
from .successor_evaluator import (
    build_successor_protocol,
    evaluate_successor,
    executed_mutation_report,
    generic_successor_rows,
)
from .typed_inventory import build_typed_record_inventory, validate_typed_record_inventory

UNIT_T_ROOT = Path("fixtures/d0_disjoint_tshirt_confirmation_v3/official_attempt")
UNIT_U_OUTCOME = Path("docs/evidence/final_strategy3_v2/outcome_report.json")
COVERAGE_PATH = Path("docs/blueprint_coverage.json")
MATRIX_V3_PATH = Path(
    "docs/evidence/d0_evidence_integrity_v4/final_d0_research_prototype_matrix_v3.json"
)
EXTERNAL_ATTESTATIONS_PATH = Path(
    "fixtures/truth_authority_integrity_v3/external_exact_head_attestations.json"
)


def build_integrity_report(repo_root: Path) -> dict[str, Any]:
    forge_root = repo_root / "closy-forge"
    migration = audit_v2_lock(repo_root)
    inventory = build_typed_record_inventory(forge_root)
    protocol = build_successor_protocol(forge_root)
    evaluator_result = evaluate_successor(protocol, generic_successor_rows())
    evaluator_mutations = executed_mutation_report(forge_root)
    collector_mutations = executed_collector_mutation_report()
    budget = build_verified_budget_report(forge_root)
    budget_mutations = budget_mutation_report(forge_root)
    frozen_guard = build_frozen_surface_guard(repo_root)
    predicates = {
        "migrationAudit": (
            validate_migration_audit(migration) == []
            and validate_audit_digest(migration) == []
            and migration.get("pass") is True
        ),
        "typedPerRecordInventory": validate_typed_record_inventory(inventory) == [],
        "totalEvaluatorLineage": evaluator_result.get("lineageCompleteCount") == 64,
        "evaluatorMutations": all(evaluator_mutations.values()),
        "outputCollectorMutations": all(collector_mutations.values()),
        "budgetSourceAndOrdering": not budget.get("validationIssues"),
        "budgetMutations": all(budget_mutations.values()),
        "frozenStrategySurface": frozen_guard.get("pass") is True,
        "topologyDeltaMetricRenamed": (
            protocol.get("candidateOracleTopologyMetric") == "candidateOracleTopologyDeltaMeters"
        ),
    }
    subgates = {
        "S-core-truth-successor": {
            "status": "integrity_predicates_pass"
            if all(
                predicates[key]
                for key in (
                    "migrationAudit",
                    "typedPerRecordInventory",
                    "budgetSourceAndOrdering",
                    "budgetMutations",
                )
            )
            else "integrity_predicates_fail",
            "scientificCapabilityClaim": False,
        },
        "S-D0-authority-successor": {
            "status": "integrity_predicates_pass"
            if all(
                predicates[key]
                for key in (
                    "totalEvaluatorLineage",
                    "evaluatorMutations",
                    "outputCollectorMutations",
                )
            )
            else "integrity_predicates_fail",
            "scientificCapabilityClaim": False,
        },
        "S-PHY-authority-successor": {
            "status": "integrity_predicates_pass"
            if all(
                predicates[key]
                for key in (
                    "migrationAudit",
                    "budgetSourceAndOrdering",
                    "frozenStrategySurface",
                    "topologyDeltaMetricRenamed",
                )
            )
            else "integrity_predicates_fail",
            "scientificCapabilityClaim": False,
        },
    }
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "reportVersion": "closy.truth_authority_integrity.successor.v1",
        "predicates": predicates,
        "subgates": subgates,
        "allIntegrityPredicatesPass": all(predicates.values()),
        "scientificAttemptCreated": False,
        "migrationAudit": migration,
        "typedInventory": inventory,
        "evaluator": {
            "protocol": protocol,
            "result": evaluator_result,
            "executedMutations": evaluator_mutations,
        },
        "outputCollector": {"executedMutations": collector_mutations},
        "budget": budget,
        "budgetMutations": budget_mutations,
        "frozenSurfaceGuard": frozen_guard,
        "reportDigest": "",
    }
    document["reportDigest"] = canonical_digest(document, "reportDigest")
    return document


def build_truth_overlay(repo_root: Path, integrity: Mapping[str, Any]) -> dict[str, Any]:
    forge_root = repo_root / "closy-forge"
    unit_t = _unit_t(forge_root)
    unit_u = _unit_u(forge_root)
    coverage = load_mapping(forge_root / COVERAGE_PATH)
    matrix = load_mapping(forge_root / MATRIX_V3_PATH)
    attestations = load_mapping(forge_root / EXTERNAL_ATTESTATIONS_PATH)
    coverage_counts = Counter(str(row.get("status", "")) for row in records(coverage.get("rows")))
    supplemental = {
        str(row.get("rowId")): str(row.get("resultStatus"))
        for row in records(matrix.get("rows"))
        if row.get("summaryClass") == "supplemental"
    }
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "overlayVersion": "closy.blueprint_truth_overlay.successor.v1",
        "consumerPolicy": "prefer_this_overlay_without_mutating_historical_keys",
        "historicalFieldPolicy": {
            "supersededKeysRetained": True,
            "reason": "legacy names conflate scheduling, execution, artifact, and gate success",
        },
        "coverage": {
            "sourcePath": COVERAGE_PATH.as_posix(),
            "sourceDigest": sha256_file(forge_root / COVERAGE_PATH),
            "rowCount": len(records(coverage.get("rows"))),
            "statusCounts": dict(sorted(coverage_counts.items())),
            "phase00": "complete",
            "phases01Through14": "partial",
        },
        "researchPrototype": {
            "core": {
                "passCount": 7,
                "failCount": 4,
                "notRunCount": 0,
                "failures": ["D0-RP-03", "D0-RP-06", "D0-RP-07", "D0-RP-15"],
            },
            "supplemental": {
                "passCount": sum(value == "pass" for value in supplemental.values()),
                "failCount": sum(value == "fail" for value in supplemental.values()),
                "notRunCount": sum(value == "not_run" for value in supplemental.values()),
                "passes": sorted(key for key, value in supplemental.items() if value == "pass"),
                "notRun": sorted(key for key, value in supplemental.items() if value == "not_run"),
            },
        },
        "unitT": unit_t,
        "unitU": unit_u,
        "budgetStateBeforeSuccessorAuthority": mapping(integrity.get("budget")),
        "unitSSuccessor": {
            "subgates": mapping(integrity.get("subgates")),
            "scientificAttemptCreated": False,
            "supersedesShallowPassDerivation": True,
        },
        "scopeSeparation": {
            "preTopologyC3": "scoped_pass_not_post_topology",
            "staticZ1": "scoped_static_pass_not_dynamic_or_physical",
            "Z2": "failed_non_solver_evidence_only",
            "globalGates": "unproven",
        },
        "externalExactHeadAttestations": attestations.get("attestations"),
        "nextAction": (
            "publish Unit Y0 integrity hardening, require exact-head Forge plus sealed-v2 lane, "
            "then create Unit Y1 repository-blob authority from that final head"
        ),
        "overlayDigest": "",
    }
    document["overlayDigest"] = canonical_digest(document, "overlayDigest")
    return document


def validate_truth_overlay(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    coverage = mapping(document.get("coverage"))
    if coverage.get("rowCount") != 101 or coverage.get("statusCounts") != {
        "complete": 20,
        "discovery_pending": 11,
        "not_started": 7,
        "partial": 63,
    }:
        issues.append("truth_overlay_coverage_invalid")
    unit_t = mapping(document.get("unitT"))
    expected_t = {
        "identities": 16,
        "attemptsScheduledCount": 64,
        "attemptsExecutedCount": 64,
        "predictionArtifactProducedCount": 60,
        "explicitAbstentionCount": 4,
        "compileRowsScheduledCount": 48,
        "compileRowsEvaluatedCount": 48,
        "legacyFullCompileSuccessCounter": 20,
        "strictCompletePixelRouteCompileValidCount": 0,
        "primaryCompileRepeatRowsEvaluatedCount": 16,
        "primaryCompileRepeatSameFailureOrOutputClassCount": 2,
        "appearanceRowsScheduledCount": 24,
        "appearanceRowsActuallyEvaluatedCount": 8,
        "appearanceGatePassCount": 0,
        "primaryAppearanceRepeatRowsEvaluatedCount": 8,
        "primaryAppearanceRepeatGatePassCount": 0,
    }
    if any(unit_t.get(key) != value for key, value in expected_t.items()):
        issues.append("truth_overlay_unit_t_counts_invalid")
    unit_u = mapping(document.get("unitU"))
    if (
        unit_u.get("literalOutcome") != "dependency_blocked_before_official_seed_v2"
        or unit_u.get("officialSeedCreated") is not False
        or unit_u.get("untouchedFixtureCreated") is not False
        or unit_u.get("canonicalCandidateCreated") is not False
    ):
        issues.append("truth_overlay_unit_u_state_invalid")
    supplemental = mapping(mapping(document.get("researchPrototype")).get("supplemental"))
    if supplemental.get("passes") != ["D0-RP-09", "D0-RP-14"] or supplemental.get("notRun") != [
        "D0-RP-10",
        "D0-RP-11",
    ]:
        issues.append("truth_overlay_supplemental_identity_invalid")
    budget = mapping(mapping(document.get("budgetStateBeforeSuccessorAuthority")).get("derived"))
    if budget.get("remaining") != {
        "canonical_candidate": 1,
        "seam_model": 0,
        "topology_strategy": 0,
    }:
        issues.append("truth_overlay_budget_invalid")
    if document.get("overlayDigest") != canonical_digest(document, "overlayDigest"):
        issues.append("truth_overlay_digest_invalid")
    return sorted(set(issues))


def _unit_t(forge_root: Path) -> dict[str, Any]:
    benchmark = load_mapping(forge_root / UNIT_T_ROOT / "benchmark_result.json")
    predictions = load_mapping(forge_root / UNIT_T_ROOT / "predictions.json")
    commitments = load_mapping(forge_root / UNIT_T_ROOT / "authority_commitments.json")
    records_ = records(benchmark.get("records"))
    attempt_rows = records(predictions.get("attemptRows"))
    strict_pixel_valid = [
        row
        for row in records_
        if str(row.get("routeId", "")).startswith("pixel_")
        and mapping(row.get("worker")).get("compile") is not None
        and all(
            mapping(row.get("gateFamilies")).get(key) is True
            for key in (
                "binding",
                "landmark",
                "opening",
                "pattern",
                "pbr_integrity",
                "seam",
                "simulation",
                "source_silhouette",
                "texture_identity",
                "topology",
            )
        )
    ]
    appearances = [mapping(row.get("appearance")) for row in records_ if row.get("appearance")]
    return {
        "artifactRoot": UNIT_T_ROOT.as_posix(),
        "literalOutcome": benchmark.get("outcome"),
        "scientificFailure": True,
        "preSeedInfrastructureFailure": False,
        "identities": commitments.get("acceptedIdentityCount"),
        "attemptsScheduledCount": benchmark.get("predictionDenominator"),
        "attemptsExecutedCount": len(attempt_rows),
        "predictionArtifactProducedCount": sum(
            row.get("status") == "pass" and isinstance(row.get("predictionArtifact"), str)
            for row in attempt_rows
        ),
        "explicitAbstentionCount": sum(row.get("status") != "pass" for row in attempt_rows),
        "compileRowsScheduledCount": benchmark.get("fullCompileDenominator"),
        "compileRowsEvaluatedCount": len(records_),
        "legacyFullCompileSuccessCounter": benchmark.get("fullCompileSuccessCount"),
        "legacyFieldSupersededBy": [
            "strictCompletePixelRouteCompileValidCount",
            "compileRowsEvaluatedCount",
        ],
        "strictCompletePixelRouteCompileValidCount": len(strict_pixel_valid),
        "primaryCompileRepeatRowsEvaluatedCount": benchmark.get("primaryCompileRepeatCount"),
        "primaryCompileRepeatSameFailureOrOutputClassCount": benchmark.get(
            "primaryCompileRepeatSuccessCount"
        ),
        "appearanceRowsScheduledCount": benchmark.get("appearanceDenominator"),
        "appearanceRowsActuallyEvaluatedCount": len(appearances),
        "appearanceGatePassCount": sum(row.get("status") == "pass" for row in appearances),
        "primaryAppearanceRepeatRowsEvaluatedCount": benchmark.get("primaryAppearanceRepeatCount"),
        "primaryAppearanceRepeatGatePassCount": benchmark.get(
            "primaryAppearanceRepeatSuccessCount"
        ),
        "primaryRelativeParameterImprovement": benchmark.get("primaryRelativeParameterImprovement"),
        "primaryAbsoluteSilhouetteImprovement": benchmark.get(
            "primaryAbsoluteSilhouetteImprovement"
        ),
        "rowResults": benchmark.get("rowDecisions"),
        "routePromoted": mapping(benchmark.get("routePromotion")).get("promoted"),
        "sourceEvidenceAnchor": "7aae56b050e72e51916b592423f63d859f166117",
        "finalPublicationHead": "0c45587371165f1c5f3e33934ee2cbf5156f9e02",
        "authorityRun": "33621365050",
        "exactHeadCiRun": "33624168164",
    }


def _unit_u(forge_root: Path) -> dict[str, Any]:
    outcome = load_mapping(forge_root / UNIT_U_OUTCOME)
    authority = mapping(outcome.get("officialAuthority"))
    admission = mapping(outcome.get("admission"))
    budgets = mapping(outcome.get("budgetsAfter"))
    return {
        "artifactPath": UNIT_U_OUTCOME.as_posix(),
        "literalOutcome": outcome.get("literalOutcome"),
        "scientificFailure": False,
        "preSeedInfrastructureFailure": True,
        "authorityAttemptsScheduledCount": 1,
        "authorityAttemptsExecutedCount": 0,
        "officialSeedCreated": authority.get("officialSeedCreated"),
        "untouchedFixtureCreated": authority.get("officialFixtureCount", 0) > 0,
        "oracleRevealed": False,
        "scientificAdmissionExecuted": admission.get("confirmationExecuted"),
        "untouchedConfirmationAttemptConsumed": authority.get("attemptConsumed"),
        "canonicalCandidateCreated": False,
        "topologyStrategiesRemaining": budgets.get("topologyStrategies"),
        "canonicalCandidateAttemptsRemaining": budgets.get("candidateAttempts"),
        "sourceEvidenceAnchor": "d76916461d3e96b037fbc31b646319effef7a264",
        "finalPublicationHead": "f56fc44ccf7173155186a30b4f4978454fb3debf",
        "exactHeadCi": {
            "run": "33635092644",
            "result": "completed_failure",
            "passedJobs": 25,
            "failedJobs": 4,
        },
    }
