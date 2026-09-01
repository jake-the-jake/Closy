from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

EVIDENCE_ROOT = Path("docs/evidence/phy1_topology_strategy2_v4")


def validate_committed_unit_i_evidence(root: Path) -> list[str]:
    issues: list[str] = []
    result = _object(root / EVIDENCE_ROOT / "strategy_microfixtures.json")
    registry = _object(root / EVIDENCE_ROOT / "physical_attempt_registry.json")
    outcome = _object(root / EVIDENCE_ROOT / "unit_i_outcome.json")
    closure = _object(root / EVIDENCE_ROOT / "logical_j_a_closure.json")
    manifest = _object(root / EVIDENCE_ROOT / "evidence_manifest.json")
    for document, field, code in (
        (result, "resultDigest", "strategy_result_digest_mismatch"),
        (outcome, "outcomeDigest", "outcome_digest_mismatch"),
        (closure, "closureDigest", "closure_digest_mismatch"),
        (manifest, "manifestDigest", "manifest_digest_mismatch"),
    ):
        if document.get("integrity", {}).get(field) != _digest(document, field):
            issues.append(code)
    record = registry.get("records", [{}])[0]
    copied_record = deepcopy(record)
    copied_record["recordHash"] = ""
    if record.get("recordHash") != _hash(copied_record):
        issues.append("attempt_record_hash_mismatch")
    if registry.get("headHash") != record.get("recordHash") or registry.get("recordCount") != 1:
        issues.append("attempt_registry_chain_mismatch")
    if result.get("status") != "fail" or not result.get("failedChecks"):
        issues.append("strategy_failure_not_preserved")
    if (
        result.get("fullCandidateOpened") is not False
        or result.get("solverStepAdvanced") is not False
    ):
        issues.append("strategy_microfixture_misclassified_as_candidate")
    required_outcome = {
        "outcomeClass": "M",
        "admissibleCanonicalPostTopologyCandidateExists": False,
        "candidateAttemptConsumed": False,
        "neutralExecuted": False,
        "fullPhy1Executed": False,
        "integratedCcdExecuted": False,
        "solverDrivenZ2Executed": False,
        "runtimeV1RemainsSelected": True,
    }
    if any(outcome.get(key) != value for key, value in required_outcome.items()):
        issues.append("unit_i_outcome_boundary_mismatch")
    if closure.get("logicalOutcome") != "J-A: post_topology_candidate_unavailable":
        issues.append("logical_j_a_missing")
    if (
        closure.get("unitJBranchAuthorized") is not False
        or closure.get("unitKEligible") is not False
    ):
        issues.append("downstream_branch_incorrectly_authorized")
    expected_inventory = [
        {"path": path.name, "sha256": sha256_file(path)}
        for path in sorted((root / EVIDENCE_ROOT).glob("*.json"))
        if path.name != "evidence_manifest.json"
    ]
    if manifest.get("inventory") != expected_inventory:
        issues.append("evidence_manifest_inventory_mismatch")
    return issues


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"object_required:{path.as_posix()}")
    return dict(value)


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


def _digest(document: dict[str, Any], field: str) -> str:
    payload = deepcopy(document)
    payload["integrity"][field] = ""
    return _hash(payload)
