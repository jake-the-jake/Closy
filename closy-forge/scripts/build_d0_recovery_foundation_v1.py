from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from closy_forge.fitting.exact_d0_candidate import inventory_digest, package_inventory
from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.phy1_topology_strategy2_v4.diagnosis import RECOMPUTATION_ULP_POLICY
from closy_forge.recovery_foundation_v1.c3_v5 import run_generic_c3_fixtures
from closy_forge.recovery_foundation_v1.contestant_boundary import (
    build_boundary_capability,
    run_boundary_fixtures,
)
from closy_forge.recovery_foundation_v1.contracts import (
    build_budget_authority,
    build_publication_truth,
    build_result_semantics,
    validate_budget_authority,
    validate_publication_truth,
    validate_result_semantics,
)
from closy_forge.recovery_foundation_v1.evaluator_v2 import run_generic_mutation_fixtures
from closy_forge.recovery_foundation_v1.sentinel import (
    resolve_sentinel,
    validate_sentinel_resolution,
)

EVIDENCE_RELATIVE = Path("docs/evidence/d0_recovery_foundation_v1")
IMPLEMENTATION_PATHS = (
    "src/closy_forge/recovery_foundation_v1/contracts.py",
    "src/closy_forge/recovery_foundation_v1/evaluator_v2.py",
    "src/closy_forge/recovery_foundation_v1/contestant_boundary.py",
    "src/closy_forge/recovery_foundation_v1/c3_v5.py",
    "src/closy_forge/recovery_foundation_v1/sentinel.py",
    "src/closy_forge/phy1_topology_strategy2_v4/diagnosis.py",
)


def build_reports(root: Path) -> dict[str, dict[str, Any]]:
    publication = build_publication_truth()
    semantics = build_result_semantics()
    budget = build_budget_authority(root)
    evaluator = run_generic_mutation_fixtures()
    boundary = run_boundary_fixtures()
    c3 = run_generic_c3_fixtures()
    sentinel = resolve_sentinel(root)
    sentinel_fallback = resolve_sentinel(root, force_unit_f_failure=True)
    issues = {
        "publication": validate_publication_truth(publication),
        "resultSemantics": validate_result_semantics(semantics),
        "physicalBudget": validate_budget_authority(budget),
        "sentinel": validate_sentinel_resolution(sentinel),
        "sentinelFallback": validate_sentinel_resolution(sentinel_fallback),
    }
    all_passed = (
        not any(issues.values())
        and evaluator["allPassed"] is True
        and boundary["allPassed"] is True
        and c3["allPassed"] is True
    )
    outcome = {
        "schemaVersion": 1,
        "outcomeVersion": "closy.d0_recovery_foundation.unit_l_outcome.v1",
        "scope": "candidate_independent_recovery_foundation_no_confirmation_execution",
        "result": "pass" if all_passed else "fail",
        "attemptState": "completed",
        "coverageState": "partial",
        "firstUnmetPredicate": None if all_passed else "unit_l_generic_foundation_validation",
        "issues": issues,
        "freshEvaluatorIdentityRealized": False,
        "freshEvaluatorTargetRealized": False,
        "freshHeldOutPoseRealized": False,
        "candidateCreated": False,
        "candidateAttemptConsumed": False,
        "topologyStrategyConsumed": False,
        "seamModelsRemaining": 0,
        "topologyStrategiesRemaining": 1,
        "runtimeSelected": "runtime_v1",
        "nextEligibleUnit": "unit_m_identity_disjoint_confirmation_v2",
        "unsupportedEvidenceClasses": [
            "identity_disjoint_v2_qualification",
            "strict_c3_v5_confirmation",
            "new_topology_candidate",
            "full_PHY1",
            "integrated_CCD",
            "solver_driven_Z2",
            "private_user",
            "real_photo",
            "real_fabric",
            "GPU",
            "mobile",
            "Alpha",
            "Beta",
            "Production",
        ],
    }
    return {
        "publication_truth.json": publication,
        "result_semantics.json": semantics,
        "physical_budget_authority.json": budget,
        "ulp_recomputation_policy.json": dict(RECOMPUTATION_ULP_POLICY),
        "evaluator_v2_generic_fixtures.json": evaluator,
        "contestant_boundary_capability.json": build_boundary_capability(),
        "contestant_boundary_generic_fixtures.json": boundary,
        "c3_v5_generic_fixtures.json": c3,
        "sentinel_resolution.json": sentinel,
        "sentinel_fallback_fixture.json": sentinel_fallback,
        "unit_l_outcome.json": outcome,
    }


def write_reports(root: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    reports = build_reports(root)
    for name, document in reports.items():
        write_canonical_json(output / name, document)
    inventory = package_inventory(output, exclude={"evidence_manifest.json"})
    manifest = {
        "schemaVersion": 1,
        "manifestVersion": "closy.d0_recovery_foundation.evidence_manifest.v1",
        "sourceEvidenceAnchorSha": "854b85ed769bc3e67547e4195f65dfeb78878881",
        "latestParentPublicationHeadSha": "69f17e0bc0d01472eec3aaf244c158181f74febf",
        "currentUnitFinalHead": "pending_external_attestation",
        "implementationFiles": [
            {"path": path, "sha256": sha256_file(root / path)} for path in IMPLEMENTATION_PATHS
        ],
        "inventory": inventory,
        "evidenceDigest": inventory_digest(inventory),
    }
    write_canonical_json(output / "evidence_manifest.json", manifest)


def check_reports(root: Path, committed: Path) -> list[str]:
    with TemporaryDirectory(prefix="closy-l-evidence-check-") as temporary:
        generated = Path(temporary) / "evidence"
        write_reports(root, generated)
        expected = {path.name: path.read_bytes() for path in generated.glob("*.json")}
    actual = {path.name: path.read_bytes() for path in committed.glob("*.json")}
    issues = []
    if set(actual) != set(expected):
        issues.append("unit_l_evidence_inventory_mismatch")
    for name in sorted(set(actual) & set(expected)):
        if actual[name] != expected[name]:
            issues.append(f"unit_l_evidence_bytes_mismatch:{name}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify Unit L recovery evidence.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    evidence = root / EVIDENCE_RELATIVE
    if args.check:
        issues = check_reports(root, evidence)
        print(json.dumps({"status": "pass" if not issues else "fail", "issues": issues}))
        return 1 if issues else 0
    write_reports(root, evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
