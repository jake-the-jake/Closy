from __future__ import annotations

import hashlib
import hmac
import os
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.final_strategy3_v2.evaluator import validate_report
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.recovery_foundation_v2.topology_holdout import generate
from closy_forge.recovery_foundation_v2.topology_holdout_oracle import (
    derive_invariants,
    validate_candidate_report,
)

from .common import canonical_digest, mapping, records, write_json
from .protocol import OUTCOMES, validate_lock, validate_lock_commit

SEED_DOMAIN = b"closy.phy1.strategy3.repository_blob_authority.v3"


def prepare_authority(
    repo_root: Path,
    lock: Mapping[str, Any],
    *,
    output: Path,
    lock_commit: str,
    workflow_run_id: str,
    workflow_job_id: str,
    preflight_run_id: str,
    image_id: str,
) -> dict[str, Any]:
    _require_new_output(output)
    issues = [
        *validate_lock(repo_root, lock, verify_objects=True),
        *validate_lock_commit(repo_root, lock, lock_commit),
    ]
    if issues:
        raise ValueError(";".join(issues))
    output.mkdir(parents=True)
    private = output / "private_until_output_freeze"
    private.mkdir()
    entropy = secrets.token_bytes(32)
    seed = hmac.new(entropy, SEED_DOMAIN, hashlib.sha256).digest()
    fixtures = generate(seed, qualification_eligible=True)
    oracles = [derive_invariants(fixture) for fixture in fixtures]
    write_json(private / "fixtures.json", fixtures, freeze=True)
    write_json(private / "oracles.json", oracles, freeze=True)
    _write_bytes(private / "raw_seed.bin", seed, freeze=True)
    environment = {
        "schemaVersion": 1,
        "environmentVersion": "closy.strategy3.authority_environment.v3",
        "platform": platform.platform(),
        "python": sys.version,
        "entropyApi": "python.secrets.token_bytes_32_os_csprng",
        "entropyBits": 256,
        "seedDomainUtf8Hex": SEED_DOMAIN.hex(),
        "derivedSeedDigest": sha256_bytes(seed),
        "workflowRunId": workflow_run_id,
        "workflowJobId": workflow_job_id,
        "preflightRunId": preflight_run_id,
        "lockCommit": lock_commit,
        "lockDigest": lock["lockDigest"],
        "imageId": image_id,
    }
    write_json(output / "environment_attestation.json", environment, freeze=True)
    commitments: dict[str, Any] = {
        "schemaVersion": 1,
        "commitmentVersion": "closy.strategy3.authority_commitments.v3",
        "eventOrdinal": 1,
        "event": "seed_fixture_oracle_commitments_frozen_before_contestant_job",
        "workflowRunId": workflow_run_id,
        "lockCommit": lock_commit,
        "lockDigest": lock["lockDigest"],
        "fixtureDenominator": 8,
        "fixtureCommitments": [fixture["commitment"] for fixture in fixtures],
        "oracleCommitments": [_hash(oracle) for oracle in oracles],
        "seedDigest": environment["derivedSeedDigest"],
        "contestantReceivesRawSeed": False,
        "contestantReceivesNonce": False,
        "contestantReceivesOracle": False,
        "commitmentDigest": "",
    }
    commitments["commitmentDigest"] = canonical_digest(commitments, "commitmentDigest")
    write_json(output / "authority_commitments.json", commitments, freeze=True)
    return commitments


def execute_contestant(
    lock: Mapping[str, Any],
    *,
    prepared: Path,
    output: Path,
    image_reference: str,
) -> dict[str, Any]:
    _require_new_output(output)
    commitments = mapping(read_json(prepared / "authority_commitments.json"))
    if commitments.get("lockDigest") != lock.get("lockDigest"):
        raise ValueError("strategy3_v3_precommit_lock_mismatch")
    private = prepared / "private_until_output_freeze"
    fixtures = records(read_json(private / "fixtures.json"))
    if len(fixtures) != 8:
        raise ValueError("strategy3_v3_fixture_denominator_invalid")
    output.mkdir(parents=True)
    reports_root = output / "raw_strategy_outputs"
    reports_root.mkdir()
    execution_rows: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    maximum = int(mapping(lock["protocol"])["resourceBudgets"]["maximumWallSecondsPerFixture"])
    for fixture in fixtures:
        report, execution = _run_contestant(
            fixture,
            image_reference=image_reference,
            output_root=reports_root,
            maximum_seconds=maximum,
        )
        reports.append(report)
        execution_rows.append(execution)
    isolation = {
        "schemaVersion": 1,
        "isolationVersion": "closy.strategy3.official_isolation.v3",
        "executionCount": len(execution_rows),
        "executionDenominator": 8,
        "rows": execution_rows,
        "networkDisabled": all(row["networkDisabled"] for row in execution_rows),
        "readOnlyRoot": all(row["readOnlyRoot"] for row in execution_rows),
        "privateOracleMounted": False,
        "rawSeedMounted": False,
        "repositoryMounted": False,
    }
    write_json(output / "isolation_report.json", isolation, freeze=True)
    freeze: dict[str, Any] = {
        "schemaVersion": 1,
        "freezeVersion": "closy.strategy3.output_freeze.v3",
        "eventOrdinal": 2,
        "event": "all_eight_outputs_frozen_and_contestants_terminated_before_reveal",
        "commitmentDigest": commitments["commitmentDigest"],
        "fixtureDenominator": 8,
        "outputCount": len(reports),
        "reportSetDigest": _hash(reports),
        "contestantsTerminated": True,
        "reportsEditedAfterFreeze": False,
        "outputFreezeDigest": "",
    }
    freeze["outputFreezeDigest"] = canonical_digest(freeze, "outputFreezeDigest")
    write_json(output / "output_freeze.json", freeze, freeze=True)
    shutil.copyfile(prepared / "authority_commitments.json", output / "authority_commitments.json")
    (output / "authority_commitments.json").chmod(0o444)
    return freeze


def evaluate_authority(
    repo_root: Path,
    lock: Mapping[str, Any],
    *,
    prepared: Path,
    contestant_output: Path,
    output: Path,
    lock_commit: str,
    workflow_run_id: str,
    workflow_job_id: str,
) -> dict[str, Any]:
    _require_new_output(output)
    issues = [
        *validate_lock(repo_root, lock, verify_objects=True),
        *validate_lock_commit(repo_root, lock, lock_commit),
    ]
    output.mkdir(parents=True)
    private = prepared / "private_until_output_freeze"
    fixtures = records(read_json(private / "fixtures.json"))
    oracles = records(read_json(private / "oracles.json"))
    seed = (private / "raw_seed.bin").read_bytes()
    commitments = mapping(read_json(prepared / "authority_commitments.json"))
    freeze = mapping(read_json(contestant_output / "output_freeze.json"))
    reports = [
        mapping(read_json(path))
        for path in sorted((contestant_output / "raw_strategy_outputs").glob("*.json"))
    ]
    if sha256_bytes(seed) != commitments.get("seedDigest"):
        issues.append("strategy3_v3_seed_commitment_mismatch")
    if [fixture.get("commitment") for fixture in fixtures] != commitments.get("fixtureCommitments"):
        issues.append("strategy3_v3_fixture_commitment_mismatch")
    if [_hash(oracle) for oracle in oracles] != commitments.get("oracleCommitments"):
        issues.append("strategy3_v3_oracle_commitment_mismatch")
    if _hash(reports) != freeze.get("reportSetDigest"):
        issues.append("strategy3_v3_output_freeze_mismatch")
    result_rows: list[dict[str, Any]] = []
    for fixture, oracle, report in zip(fixtures, oracles, reports, strict=True):
        row_issues = [
            *validate_candidate_report(fixture, oracle, report),
            *validate_report(report),
        ]
        mass_interval = oracle["massIntervalKg"]
        mass = float(report.get("massKg", -1.0))
        if not float(mass_interval[0]) <= mass <= float(mass_interval[1]):
            row_issues.append("strategy3_v3_mass_interval_failed")
        if report.get("quotientComponentCount") != oracle.get("expectedQuotientComponentCount"):
            row_issues.append("strategy3_v3_quotient_component_failed")
        result_rows.append(
            {
                "fixtureId": fixture["fixtureId"],
                "fixtureType": fixture["fixtureType"],
                "issues": sorted(set(row_issues)),
                "portableDecision": "pass" if not row_issues else "fail",
                "rawReportDigest": report.get("reportDigest"),
                "ambiguityBandEntered": False,
            }
        )
    passed = sum(row["portableDecision"] == "pass" for row in result_rows)
    outcome = OUTCOMES[0] if passed == 8 else OUTCOMES[1]
    if issues:
        outcome = OUTCOMES[2]
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "resultVersion": "closy.strategy3.repository_blob_confirmation_result.v3",
        "literalOutcome": outcome,
        "fixturePassCount": passed,
        "fixtureDenominator": 8,
        "allFailuresRetainedInDenominator": True,
        "portableDecisions": result_rows,
        "integrityIssues": sorted(set(issues)),
        "officialSeedCreated": True,
        "untouchedConfirmationAttemptConsumed": True,
        "canonicalCandidateCreated": False,
        "canonicalCandidateAttemptConsumed": False,
        "topologyStrategiesAvailable": 0,
        "canonicalCandidateAttemptsRemaining": 1,
        "unitZEligible": outcome == OUTCOMES[0],
        "resultDigest": "",
    }
    result["resultDigest"] = canonical_digest(result, "resultDigest")
    reveal: dict[str, Any] = {
        "schemaVersion": 1,
        "revealVersion": "closy.strategy3.fixture_oracle_reveal.v3",
        "eventOrdinal": 3,
        "event": "seed_nonce_fixture_and_oracle_reveal_after_output_freeze",
        "outputFreezeDigest": freeze["outputFreezeDigest"],
        "rawSeedHex": seed.hex(),
        "fixtures": fixtures,
        "oracles": oracles,
        "replacementFixtureGenerated": False,
        "revealDigest": "",
    }
    reveal["revealDigest"] = canonical_digest(reveal, "revealDigest")
    for source in (
        prepared / "environment_attestation.json",
        prepared / "authority_commitments.json",
        contestant_output / "output_freeze.json",
        contestant_output / "isolation_report.json",
    ):
        shutil.copyfile(source, output / source.name)
        (output / source.name).chmod(0o444)
    raw_target = output / "raw_strategy_outputs"
    shutil.copytree(contestant_output / "raw_strategy_outputs", raw_target)
    for path in raw_target.iterdir():
        path.chmod(0o444)
    write_json(output / "fixture_oracle_reveal.json", reveal, freeze=True)
    write_json(output / "confirmation_result.json", result, freeze=True)
    manifest = _attempt_manifest(
        output,
        lock,
        result,
        lock_commit=lock_commit,
        workflow_run_id=workflow_run_id,
        workflow_job_id=workflow_job_id,
    )
    write_json(output / "attempt_manifest.json", manifest, freeze=True)
    return result


def write_public_failure(
    output: Path,
    *,
    seed_created: bool,
    stage: str,
    error: Exception,
    workflow_run_id: str,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    outcome = OUTCOMES[2] if seed_created else OUTCOMES[3]
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "failureVersion": "closy.strategy3.public_failure.v3",
        "literalOutcome": outcome,
        "stage": stage,
        "failureType": type(error).__name__,
        "officialSeedCreated": seed_created,
        "untouchedConfirmationAttemptConsumed": seed_created,
        "qualificationRetryAllowed": False,
        "privateArtifactsIncluded": False,
        "sanitizedDiagnostic": str(error)[:500],
        "workflowRunId": workflow_run_id,
        "failureDigest": "",
    }
    document["failureDigest"] = canonical_digest(document, "failureDigest")
    write_json(output / "public_failure.json", document, freeze=True)
    return document


def _run_contestant(
    fixture: Mapping[str, Any],
    *,
    image_reference: str,
    output_root: Path,
    maximum_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    fixture_id = str(fixture["fixtureId"])
    with tempfile.TemporaryDirectory(prefix=f"closy-v3-{fixture_id}-") as temporary:
        root = Path(temporary)
        inputs = root / "inputs"
        outputs = root / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        outputs.chmod(0o777)
        contestant_fixture = {
            key: value
            for key, value in fixture.items()
            if key not in {"nonce", "commitment", "qualificationEligible"}
        }
        write_json(inputs / "fixture.json", contestant_fixture)
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "768m",
            "--cpus",
            "2",
            "--pids-limit",
            "128",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--env",
            "LANG=C.UTF-8",
            "--env",
            "LC_ALL=C.UTF-8",
            "--env",
            "PYTHONHASHSEED=0",
            "--env",
            "PYTHONPATH=/app/src",
            "-v",
            f"{inputs.resolve()}:/inputs:ro",
            "-v",
            f"{outputs.resolve()}:/outputs:rw",
            image_reference,
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=maximum_seconds,
        )
        report_path = outputs / "report.json"
        if completed.returncode != 0 or not report_path.is_file():
            raise ValueError(f"strategy3_v3_contestant_failed:{fixture_id}")
        if report_path.stat().st_size > 2_000_000:
            raise ValueError(f"strategy3_v3_output_budget_exceeded:{fixture_id}")
        target = output_root / f"{fixture_id}.json"
        _write_bytes(target, report_path.read_bytes(), freeze=True)
        report = mapping(read_json(target))
        return report, {
            "fixtureId": fixture_id,
            "containerReturnCode": completed.returncode,
            "networkDisabled": True,
            "readOnlyRoot": True,
            "capabilitiesDropped": True,
            "inputFiles": ["fixture.json"],
            "nonceMounted": False,
            "oracleMounted": False,
            "seedMounted": False,
            "repositoryMounted": False,
            "reportSha256": sha256_file(target),
        }


def _attempt_manifest(
    output: Path,
    lock: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    lock_commit: str,
    workflow_run_id: str,
    workflow_job_id: str,
) -> dict[str, Any]:
    files = [
        {
            "path": path.relative_to(output).as_posix(),
            "sha256": sha256_file(path),
            "byteLength": path.stat().st_size,
        }
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "attempt_manifest.json"
    ]
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "manifestVersion": "closy.strategy3.attempt_manifest.v3",
        "scientificSourceCommit": lock["scientificSourceCommit"],
        "authorityWrapperSourceCommit": lock["authorityWrapperSourceCommit"],
        "lockCommit": lock_commit,
        "lockDigest": lock["lockDigest"],
        "workflowRunId": workflow_run_id,
        "workflowJobId": workflow_job_id,
        "literalOutcome": result["literalOutcome"],
        "officialSeedCreated": True,
        "qualificationRetryAllowed": False,
        "canonicalCandidateAttemptConsumed": False,
        "files": files,
        "manifestDigest": "",
    }
    document["manifestDigest"] = canonical_digest(document, "manifestDigest")
    return document


def _require_new_output(output: Path) -> None:
    if output.exists():
        raise ValueError("strategy3_v3_output_must_not_preexist")


def _write_bytes(path: Path, payload: bytes, *, freeze: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    if freeze:
        path.chmod(0o444)


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
