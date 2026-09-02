from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file

from .common import canonical_digest, load_json, records, write_json
from .protocol import OFFICIAL_ROOT, OUTCOMES, load_lock

EVIDENCE_ROOT = Path("docs/evidence/strategy3_blob_authority_v3")


def validate_attempt(source: Path, lock: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    required = {
        "attempt_manifest.json",
        "authority_commitments.json",
        "confirmation_result.json",
        "environment_attestation.json",
        "fixture_oracle_reveal.json",
        "isolation_report.json",
        "output_freeze.json",
    }
    if not required <= {path.name for path in source.iterdir() if path.is_file()}:
        return ["strategy3_v3_attempt_files_missing"]
    manifest = load_json(source / "attempt_manifest.json")
    result = load_json(source / "confirmation_result.json")
    commitments = load_json(source / "authority_commitments.json")
    freeze = load_json(source / "output_freeze.json")
    reveal = load_json(source / "fixture_oracle_reveal.json")
    isolation = load_json(source / "isolation_report.json")
    if manifest.get("lockDigest") != lock.get("lockDigest"):
        issues.append("strategy3_v3_attempt_lock_mismatch")
    if manifest.get("literalOutcome") != result.get("literalOutcome"):
        issues.append("strategy3_v3_attempt_outcome_mismatch")
    if result.get("literalOutcome") not in OUTCOMES:
        issues.append("strategy3_v3_attempt_outcome_invalid")
    if result.get("resultDigest") != canonical_digest(result, "resultDigest"):
        issues.append("strategy3_v3_result_digest_invalid")
    if commitments.get("eventOrdinal") != 1 or freeze.get("eventOrdinal") != 2:
        issues.append("strategy3_v3_attempt_chronology_invalid")
    if reveal.get("eventOrdinal") != 3:
        issues.append("strategy3_v3_attempt_reveal_order_invalid")
    if freeze.get("commitmentDigest") != commitments.get("commitmentDigest"):
        issues.append("strategy3_v3_commitment_freeze_link_invalid")
    if reveal.get("outputFreezeDigest") != freeze.get("outputFreezeDigest"):
        issues.append("strategy3_v3_freeze_reveal_link_invalid")
    if isolation.get("networkDisabled") is not True or isolation.get("privateOracleMounted"):
        issues.append("strategy3_v3_attempt_isolation_invalid")
    if any(path.name.startswith("private_until") for path in source.rglob("*")):
        issues.append("strategy3_v3_private_store_present")
    for row in records(manifest.get("files", [])):
        path = source / str(row.get("path", ""))
        if (
            not path.is_file()
            or sha256_file(path) != row.get("sha256")
            or path.stat().st_size != row.get("byteLength")
        ):
            issues.append(f"strategy3_v3_manifest_file_invalid:{row.get('path')}")
    if manifest.get("manifestDigest") != canonical_digest(manifest, "manifestDigest"):
        issues.append("strategy3_v3_attempt_manifest_digest_invalid")
    return sorted(set(issues))


def import_attempt(forge_root: Path, source: Path, *, authority_run_id: str) -> dict[str, Any]:
    lock = load_lock(forge_root)
    issues = validate_attempt(source, lock)
    if issues:
        raise ValueError(";".join(issues))
    target = forge_root / OFFICIAL_ROOT
    if target.exists():
        raise ValueError("strategy3_v3_official_attempt_already_imported")
    shutil.copytree(source, target)
    result = load_json(target / "confirmation_result.json")
    outcome: dict[str, Any] = {
        "schemaVersion": 1,
        "outcomeVersion": "closy.strategy3.repository_blob_outcome.v3",
        "literalOutcome": result["literalOutcome"],
        "authorityRunId": authority_run_id,
        "scientificSourceCommit": lock["scientificSourceCommit"],
        "authorityWrapperSourceCommit": lock["authorityWrapperSourceCommit"],
        "lockDigest": lock["lockDigest"],
        "fixturePassCount": result["fixturePassCount"],
        "fixtureDenominator": result["fixtureDenominator"],
        "officialSeedCreated": result["officialSeedCreated"],
        "untouchedConfirmationAttemptConsumed": result["untouchedConfirmationAttemptConsumed"],
        "canonicalCandidateCreated": False,
        "canonicalCandidateAttemptConsumed": False,
        "topologyStrategiesAvailable": 0,
        "canonicalCandidateAttemptsRemaining": 1,
        "unitZEligible": result["unitZEligible"],
        "outcomeDigest": "",
    }
    outcome["outcomeDigest"] = canonical_digest(outcome, "outcomeDigest")
    write_json(forge_root / EVIDENCE_ROOT / "outcome_report.json", outcome)
    ledger: dict[str, Any] = {
        "schemaVersion": 1,
        "ledgerVersion": "closy.strategy3.repository_blob_attempt_ledger.v3",
        "events": [
            {
                "ordinal": 0,
                "event": "successor_authority_attempt_consumed",
                "authorityRunId": authority_run_id,
                "officialSeedCreated": True,
                "literalOutcome": result["literalOutcome"],
                "topologyStrategiesAvailableAfter": 0,
                "canonicalCandidateAttemptsRemainingAfter": 1,
            }
        ],
        "ledgerDigest": "",
    }
    ledger["ledgerDigest"] = canonical_digest(ledger, "ledgerDigest")
    write_json(forge_root / EVIDENCE_ROOT / "attempt_ledger.json", ledger)
    return outcome
