from __future__ import annotations

import hashlib
import hmac
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.recovery_foundation_v2.topology_holdout import generate
from closy_forge.recovery_foundation_v2.topology_holdout_oracle import (
    derive_invariants,
    validate_candidate_report,
)

from .evaluator import validate_report
from .protocol import OUTCOMES, load_protocol, validate_implementation

SEED_DOMAIN = b"closy.phy1.final_strategy3.confirmation.v2"


def run_official_attempt(
    root: Path,
    *,
    output: Path,
    lock_sha: str,
    workflow_run_id: str,
    workflow_job_id: str,
    image_reference: str,
) -> dict[str, Any]:
    if output.exists():
        raise ValueError("final_strategy3_output_must_not_preexist")
    protocol = load_protocol(root)
    implementation_issues = validate_implementation(root, protocol)
    if implementation_issues:
        raise ValueError(";".join(implementation_issues))
    output.mkdir(parents=True)
    private = output / ".authority_private_until_output_freeze"
    private.mkdir()

    entropy = secrets.token_bytes(32)
    seed = hmac.new(entropy, SEED_DOMAIN, hashlib.sha256).digest()
    environment = {
        "schemaVersion": 1,
        "environmentVersion": "closy.final_strategy3.authority_environment.v2",
        "authorityEnvironment": "github_actions_ubuntu_external_authority",
        "platform": platform.platform(),
        "python": sys.version,
        "entropyApi": "python.secrets.token_bytes_32_os_csprng",
        "entropyBits": 256,
        "rawEntropyDigest": sha256_bytes(entropy),
        "seedDomainUtf8Hex": SEED_DOMAIN.hex(),
        "derivedSeedDigest": sha256_bytes(seed),
        "workflowRunId": workflow_run_id,
        "workflowJobId": workflow_job_id,
        "lockSha": lock_sha,
        "containerImage": image_reference,
        "authorityClaim": "procedural_freeze_and_container_isolation_not_cryptographic_secrecy",
    }
    _durable_json(output / "environment_attestation.json", environment, freeze=True)

    fixtures = generate(seed, qualification_eligible=True)
    oracles = [derive_invariants(fixture) for fixture in fixtures]
    _durable_json(private / "fixtures.json", fixtures)
    _durable_json(private / "oracles.json", oracles)
    _durable_bytes(private / "raw_seed.bin", seed)
    commitments = {
        "schemaVersion": 1,
        "commitmentVersion": "closy.final_strategy3.authority_commitments.v2",
        "eventOrdinal": 1,
        "event": "fixture_and_oracle_commitments_fsynced_before_strategy_execution",
        "lockSha": lock_sha,
        "protocolLockHash": protocol["lockHash"],
        "implementationDigest": protocol["implementationDigest"],
        "fixtureCount": len(fixtures),
        "fixtureCommitments": [fixture["commitment"] for fixture in fixtures],
        "oracleCommitments": [_hash(oracle) for oracle in oracles],
        "seedDigest": environment["derivedSeedDigest"],
        "contestantReceivesExpectedAnswers": False,
        "contestantReceivesNonce": False,
        "externallyDownloadableBeforeExecution": False,
        "anchoringLimitation": "workflow_artifact_downloadable_only_after_job_completion",
        "authorityClaim": environment["authorityClaim"],
        "commitmentHash": "",
    }
    commitments["commitmentHash"] = _hash({**commitments, "commitmentHash": ""})
    _durable_json(output / "authority_commitments.json", commitments, freeze=True)

    raw_root = output / "raw_strategy_outputs"
    raw_root.mkdir()
    execution_rows: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for fixture in fixtures:
        report, execution = _run_contestant(
            fixture=fixture,
            image_reference=image_reference,
            output_root=raw_root,
            maximum_seconds=int(protocol["resourceBudgets"]["maximumWallSecondsPerFixture"]),
        )
        reports.append(report)
        execution_rows.append(execution)
    report_set_hash = _hash(reports)
    freeze = {
        "schemaVersion": 1,
        "freezeVersion": "closy.final_strategy3.output_freeze.v2",
        "eventOrdinal": 2,
        "event": "all_eight_raw_strategy_outputs_frozen_before_fixture_or_oracle_reveal",
        "commitmentHash": commitments["commitmentHash"],
        "fixtureDenominator": 8,
        "outputCount": len(reports),
        "reportSetHash": report_set_hash,
        "reportsEditedAfterFreeze": False,
        "contestantTerminated": True,
        "outputFreezeHash": "",
    }
    freeze["outputFreezeHash"] = _hash({**freeze, "outputFreezeHash": ""})
    _durable_json(output / "output_freeze.json", freeze, freeze=True)
    _durable_json(
        output / "isolation_report.json",
        {
            "schemaVersion": 1,
            "executionCount": len(execution_rows),
            "executionDenominator": 8,
            "rows": execution_rows,
            "networkDisabled": all(row["networkDisabled"] for row in execution_rows),
            "readOnlyRoot": all(row["readOnlyRoot"] for row in execution_rows),
            "privateOracleMounted": False,
        },
        freeze=True,
    )

    revealed_fixtures = _records(read_json(private / "fixtures.json"))
    revealed_oracles = _records(read_json(private / "oracles.json"))
    revealed_seed = (private / "raw_seed.bin").read_bytes()
    reveal = {
        "schemaVersion": 1,
        "revealVersion": "closy.final_strategy3.fixture_oracle_reveal.v2",
        "eventOrdinal": 3,
        "event": "seed_nonces_fixtures_and_oracles_revealed_after_output_freeze",
        "outputFreezeHash": freeze["outputFreezeHash"],
        "rawSeedHex": revealed_seed.hex(),
        "fixtures": revealed_fixtures,
        "oracles": revealed_oracles,
        "replacementFixtureGenerated": False,
        "revealHash": "",
    }
    reveal["revealHash"] = _hash({**reveal, "revealHash": ""})
    _durable_json(output / "fixture_oracle_reveal.json", reveal, freeze=True)
    shutil.rmtree(private)

    result = _evaluate(
        fixtures=[_mapping(row) for row in revealed_fixtures],
        oracles=[_mapping(row) for row in revealed_oracles],
        reports=reports,
        protocol=protocol,
    )
    _durable_json(output / "confirmation_result.json", result, freeze=True)
    changed = _changed_path_audit(root, lock_sha, protocol)
    _durable_json(output / "changed_path_audit.json", changed, freeze=True)
    if changed["status"] != "pass" or validate_implementation(root, protocol):
        result = _integrity_override(result, "post_freeze_locked_path_drift")
        _replace_frozen_json(output / "confirmation_result.json", result)
    manifest = _manifest(output, protocol, result, lock_sha, workflow_run_id, workflow_job_id)
    _durable_json(output / "attempt_manifest.json", manifest, freeze=True)
    return result


def write_public_failure(
    output: Path,
    *,
    failure_type: str,
    stage: str,
    seed_created: bool,
    workflow_run_id: str,
    workflow_job_id: str,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    private = output / ".authority_private_until_output_freeze"
    if private.exists():
        shutil.rmtree(private)
    outcome = OUTCOMES[2] if seed_created else OUTCOMES[3]
    document = {
        "schemaVersion": 1,
        "failureVersion": "closy.final_strategy3.public_failure.v2",
        "outcome": outcome,
        "stage": stage,
        "failureType": failure_type,
        "officialSeedCreated": seed_created,
        "candidateAttemptConsumed": False,
        "qualificationRetryAllowed": not seed_created,
        "privateArtifactsRemoved": True,
        "rawSeedIncluded": False,
        "nonceIncluded": False,
        "oracleIncluded": False,
        "workflowRunId": workflow_run_id,
        "workflowJobId": workflow_job_id,
        "failureHash": "",
    }
    document["failureHash"] = _hash({**document, "failureHash": ""})
    _durable_json(output / "public_failure.json", document, freeze=True)
    return document


def _run_contestant(
    *, fixture: Mapping[str, Any], image_reference: str, output_root: Path, maximum_seconds: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    fixture_id = str(fixture["fixtureId"])
    with tempfile.TemporaryDirectory(prefix=f"closy-{fixture_id}-") as temporary:
        root = Path(temporary)
        inputs, outputs = root / "inputs", root / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        outputs.chmod(0o777)
        contestant_fixture = {
            key: value
            for key, value in fixture.items()
            if key not in {"nonce", "commitment", "qualificationEligible"}
        }
        _durable_json(inputs / "fixture.json", contestant_fixture)
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
            raise ValueError(f"final_strategy3_contestant_failed:{fixture_id}")
        if report_path.stat().st_size > 2_000_000:
            raise ValueError(f"final_strategy3_output_budget_exceeded:{fixture_id}")
        target = output_root / f"{fixture_id}.json"
        _durable_bytes(target, report_path.read_bytes(), freeze=True)
        report = _mapping(read_json(target))
        return report, {
            "fixtureId": fixture_id,
            "containerReturnCode": completed.returncode,
            "networkDisabled": True,
            "readOnlyRoot": True,
            "capabilitiesDropped": True,
            "inputFiles": ["fixture.json"],
            "nonceMounted": False,
            "oracleMounted": False,
            "reportSha256": sha256_file(target),
        }


def _evaluate(
    *,
    fixtures: list[dict[str, Any]],
    oracles: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for fixture, oracle, report in zip(fixtures, oracles, reports, strict=True):
        issues = [*validate_candidate_report(fixture, oracle, report), *validate_report(report)]
        mass_interval = oracle["massIntervalKg"]
        mass = float(report.get("massKg", -1.0))
        if not float(mass_interval[0]) <= mass <= float(mass_interval[1]):
            issues.append("final_strategy3_mass_interval_failed")
        if report.get("quotientComponentCount") != oracle.get("expectedQuotientComponentCount"):
            issues.append("final_strategy3_quotient_component_failed")
        row = {
            "fixtureId": fixture["fixtureId"],
            "fixtureType": fixture["fixtureType"],
            "issues": sorted(set(issues)),
            "portableDecision": "pass" if not issues else "fail",
            "rawReportDigest": report["reportDigest"],
            "ambiguityBandEntered": False,
        }
        rows.append(row)
    passed = sum(row["portableDecision"] == "pass" for row in rows)
    outcome = OUTCOMES[0] if passed == len(rows) == 8 else OUTCOMES[1]
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "resultVersion": "closy.final_strategy3.confirmation_result.v2",
        "outcome": outcome,
        "fixturePassCount": passed,
        "fixtureDenominator": 8,
        "allFailuresRetainedInDenominator": True,
        "portableDecisions": rows,
        "portableDecisionPolicy": protocol["numericPolicy"],
        "ambiguityBandEntryCount": 0,
        "candidateCreated": False,
        "candidateAttemptConsumed": False,
        "topologyStrategyConsumed": True,
        "unitVEligible": outcome == OUTCOMES[0],
        "resultHash": "",
    }
    document["resultHash"] = _hash({**document, "resultHash": ""})
    return document


def _changed_path_audit(root: Path, lock_sha: str, protocol: Mapping[str, Any]) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", f"{lock_sha}..HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    changed = sorted(line for line in completed.stdout.splitlines() if line)
    locked = {str(_mapping(row)["path"]) for row in protocol["implementationFiles"]}
    overlap = sorted(set(changed) & locked)
    return {
        "schemaVersion": 1,
        "auditVersion": "closy.final_strategy3.changed_path_audit.v2",
        "lockSha": lock_sha,
        "headSha": _git(root, "rev-parse", "HEAD"),
        "changedPathsAfterLock": changed,
        "lockedPathOverlap": overlap,
        "status": "pass" if completed.returncode == 0 and not overlap else "fail",
    }


def _integrity_override(result: Mapping[str, Any], reason: str) -> dict[str, Any]:
    document = {
        **dict(result),
        "outcome": OUTCOMES[2],
        "unitVEligible": False,
        "integrityFailureReason": reason,
        "resultHash": "",
    }
    document["resultHash"] = _hash({**document, "resultHash": ""})
    return document


def _manifest(
    output: Path,
    protocol: Mapping[str, Any],
    result: Mapping[str, Any],
    lock_sha: str,
    run_id: str,
    job_id: str,
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
        "manifestVersion": "closy.final_strategy3.attempt_manifest.v2",
        "lockSha": lock_sha,
        "protocolLockHash": protocol["lockHash"],
        "implementationDigest": protocol["implementationDigest"],
        "workflowRunId": run_id,
        "workflowJobId": job_id,
        "literalOutcome": result["outcome"],
        "officialSeedCreated": True,
        "qualificationRetryAllowed": False,
        "candidateAttemptConsumed": False,
        "files": files,
        "manifestHash": "",
    }
    document["manifestHash"] = _hash({**document, "manifestHash": ""})
    return document


def _durable_json(path: Path, value: Any, *, freeze: bool = False) -> None:
    _durable_bytes(path, (canonical_dumps(value) + "\n").encode("utf-8"), freeze=freeze)


def _replace_frozen_json(path: Path, value: Any) -> None:
    path.chmod(0o644)
    _durable_json(path, value, freeze=True)


def _durable_bytes(path: Path, value: bytes, *, freeze: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(value)
        handle.flush()
        import os

        os.fsync(handle.fileno())
    if freeze:
        path.chmod(0o444)


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("final_strategy3_mapping_required")
    return dict(value)


def _records(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("final_strategy3_records_required")
    return value


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
