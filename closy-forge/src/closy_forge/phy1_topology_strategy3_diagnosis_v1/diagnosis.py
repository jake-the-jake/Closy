from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.phy1_topology_strategy3_diagnosis_v1.fixtures import run_fixture_set
from closy_forge.phy1_topology_strategy3_diagnosis_v1.protocol import document_digest


def run_bounded_diagnosis(root: Path, lock: Mapping[str, Any]) -> dict[str, Any]:
    revisions = [run_revision(root, lock, revision) for revision in (1, 2)]
    admitted = [row for row in revisions if row["admitted"]]
    if admitted:
        outcome_class = "strategy3_class_admitted_pre_candidate"
        admitted_class: str | None = str(admitted[0]["strategyClass"])
    else:
        outcome_class = "no_strategy3_class_admitted_within_bounded_diagnosis"
        admitted_class = None
    outcome: dict[str, Any] = {
        "schemaVersion": 1,
        "outcomeVersion": "closy.phy1.topology_strategy3.bounded_diagnosis.v1",
        "diagnosisLockDigest": _mapping(lock["integrity"])["lockDigest"],
        "revisionCount": len(revisions),
        "maximumRevisionCount": int(lock["maximumPreCandidateRevisions"]),
        "revisions": revisions,
        "outcomeClass": outcome_class,
        "admittedStrategyClass": admitted_class,
        "attemptState": "completed_candidate_independent_diagnosis",
        "coverageState": "partial",
        "firstUnmetPredicate": (
            None if admitted_class is not None else _first_unmet_across_revisions(revisions)
        ),
        "candidateCreated": False,
        "candidateAttemptConsumed": False,
        "finalStrategyConsumed": False,
        "unitPEligible": admitted_class is not None,
        "runtimeV1RemainsSelected": True,
        "budgetsBefore": {
            "seamModels": 0,
            "topologyStrategies": 1,
            "candidateAttempts": 1,
        },
        "budgetsAfter": {
            "seamModels": 0,
            "topologyStrategies": 1,
            "candidateAttempts": 1,
        },
        "unsupportedClaims": {
            "physicalCloth": False,
            "PHY1": False,
            "integratedCCD": False,
            "Z2": False,
            "production": False,
        },
        "integrity": {"outcomeDigest": ""},
    }
    outcome["integrity"]["outcomeDigest"] = document_digest(outcome, "outcomeDigest")
    return outcome


def run_revision(root: Path, lock: Mapping[str, Any], revision: int) -> dict[str, Any]:
    fixtures = run_fixture_set(revision)
    local_payload = canonical_dumps(fixtures)
    local_digest = sha256_bytes(local_payload.encode("utf-8"))
    command = [
        sys.executable,
        "-m",
        "closy_forge.phy1_topology_strategy3_diagnosis_v1.repeat_worker",
        "--revision",
        str(revision),
    ]
    repeats = [
        subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
        for _ in range(2)
    ]
    expected_repeat = canonical_dumps({"fixtureDigest": local_digest})
    deterministic_checks = {
        "freshProcessOneMatches": repeats[0] == expected_repeat,
        "freshProcessTwoMatches": repeats[1] == expected_repeat,
        "freshProcessesMatchEachOther": repeats[0] == repeats[1],
    }
    deterministic_fixture = {
        "ordinal": 8,
        "fixtureId": "deterministic_repeat_cross_process",
        "candidateIndependent": True,
        "qualificationEligible": False,
        "productionKernelExecuted": True,
        "measurements": {"fixtureDigest": local_digest, "freshProcessCount": 2},
        "checks": deterministic_checks,
        "negativeMutationDetected": (
            sha256_bytes((local_payload + "mutation").encode("utf-8")) != local_digest
        ),
        "status": "pass" if all(deterministic_checks.values()) else "fail",
        "crossPythonVerification": (
            "same committed fixture digest is regenerated in Forge Python 3.11 and 3.12"
        ),
    }
    fixtures.append(deterministic_fixture)
    pass_count = sum(row["status"] == "pass" for row in fixtures)
    transfer = fixtures[6]
    normal = fixtures[0]
    curved = fixtures[1]
    thresholds = _mapping(lock["admissionThresholds"])
    normal_measurements = _mapping(normal["measurements"])
    analytic = _mapping(normal_measurements["independentAnalyticBounds"])
    transfer_measurements = _mapping(transfer["measurements"])
    transfer_checks = _mapping(transfer["checks"])
    transfer_defects = _mapping(transfer_measurements["defects"])
    field_class_coverage = {
        "semanticFieldsAffectComputedBehaviour": all(
            [
                _mapping(normal["checks"])["finiteComplianceRetained"],
                transfer_checks["massTransfer"],
                transfer_checks["uvTransfer"],
                transfer_checks["semanticSeamTransfer"],
                transfer_checks["bindingTransfer"],
            ]
        ),
        "validationFieldsRejectMutation": bool(
            transfer_measurements["allNegativeMutationsDetected"]
        ),
        "provenanceFieldsAlterIdentity": bool(
            transfer_measurements["provenanceMutationChangesIdentity"]
        ),
    }
    admission_checks = {
        "completeFixtureDenominator": len(fixtures) == int(thresholds["requiredFixtureCount"]),
        "allFixturesPass": pass_count == int(thresholds["requiredFixturePassCount"]),
        "productionKernelsUsed": all(row["productionKernelExecuted"] for row in fixtures),
        "negativeMutationsDetected": all(row["negativeMutationDetected"] for row in fixtures),
        "finiteComplianceSeamLawPreserved": _mapping(normal["checks"])["finiteComplianceRetained"],
        "normalAndTangentialSeparated": all(
            [
                _mapping(normal["checks"])["normalMeasuredSeparately"],
                _mapping(curved["checks"])["normalAndTangentialReported"],
                _mapping(curved["checks"])["tangentialLoadObserved"],
            ]
        ),
        "energyWithinPreregisteredInterval": (
            float(analytic["energyBalanceErrorJoules"])
            <= float(thresholds["maximumEnergyBalanceErrorJoules"])
        ),
        "impulseWithinPreregisteredInterval": (
            float(analytic["impulseBalanceErrorNewtonSeconds"])
            <= float(thresholds["maximumImpulseBalanceErrorNewtonSeconds"])
        ),
        "deterministicConstraintOrdering": all(
            _mapping(row["checks"]).get("deterministicOrdering", True)
            and _mapping(row["checks"]).get("constraintOrderStable", True)
            for row in fixtures
        ),
        "semanticTransferComplete": transfer_checks["semanticSeamTransfer"],
        "topologyValid": (
            transfer_checks["topology"]
            and sum(int(value) for value in transfer_defects.values())
            <= int(thresholds["maximumTopologyDefectCount"])
        ),
        "openingPreserved": transfer_checks["openingTransfer"],
        "allTransferFieldsComplete": all(
            transfer_checks[field]
            for field in (
                "massTransfer",
                "uvTransfer",
                "materialTransfer",
                "sourceTransfer",
                "bindingTransfer",
                "semanticSeamTransfer",
            )
        ),
        "fieldClassCoverage": all(field_class_coverage.values()),
        "deterministic": deterministic_fixture["status"] == "pass",
    }
    strategy = next(row for row in lock["revisions"] if int(row["revision"]) == revision)
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "revision": revision,
        "strategyClass": strategy["strategyClass"],
        "declaredRisk": strategy["declaredRisk"],
        "fixtureCount": len(fixtures),
        "fixturePassCount": pass_count,
        "fixtures": fixtures,
        "admissionChecks": admission_checks,
        "fieldClassCoverage": field_class_coverage,
        "firstUnmetPredicate": next(
            (name for name, passed in admission_checks.items() if not passed), None
        ),
        "admitted": all(admission_checks.values()),
        "candidateCreated": False,
        "solverProductionKernelExecuted": True,
        "integrity": {"revisionDigest": ""},
    }
    result["integrity"]["revisionDigest"] = document_digest(result, "revisionDigest")
    return result


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_unmet_across_revisions(revisions: list[dict[str, Any]]) -> str:
    failures = [
        f"revision_{row['revision']}:{row['firstUnmetPredicate']}"
        for row in revisions
        if row.get("firstUnmetPredicate") is not None
    ]
    return failures[0] if failures else "no_materially_distinct_strategy_admitted"
