from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from closy_forge.final_strategy3_v2.protocol import load_protocol, validate_implementation
from closy_forge.package_io.hashing import sha256_file

from .common import load_mapping, records
from .migration_audit import (
    LOCK_PATH,
    V2_LOCK_COMMIT,
    audit_v2_lock,
    validate_audit_digest,
    validate_migration_audit,
)

LOCKED_TEST_NODE = (
    "tests/unit/test_final_strategy3_v2_protocol.py::"
    "test_final_lock_is_self_consistent_when_present"
)


def verify_sealed_v2_failure(repo_root: Path, *, execute_pytest: bool = True) -> dict[str, Any]:
    forge_root = repo_root / "closy-forge"
    audit = audit_v2_lock(repo_root)
    audit_issues = [*validate_migration_audit(audit), *validate_audit_digest(audit)]
    lock = load_mapping(repo_root / LOCK_PATH)
    outcome = load_mapping(forge_root / "docs/evidence/final_strategy3_v2/outcome_report.json")
    expected_worktree_issues = _expected_worktree_issues(forge_root, lock)
    actual_worktree_issues = validate_implementation(forge_root, load_protocol(forge_root))
    immutable_test_blob = _git_blob(
        repo_root,
        "HEAD",
        "closy-forge/tests/unit/test_final_strategy3_v2_protocol.py",
    )
    original_test_blob = _git_blob(
        repo_root,
        V2_LOCK_COMMIT,
        "closy-forge/tests/unit/test_final_strategy3_v2_protocol.py",
    )
    test_execution = _execute_locked_test(forge_root) if execute_pytest else {}
    authority = dict(outcome.get("officialAuthority", {}))
    admission = dict(outcome.get("admission", {}))
    state = {
        "officialSeedCreated": authority.get("officialSeedCreated"),
        "officialFixtureCount": authority.get("officialFixtureCount"),
        "authorityResultPresent": lock.get("officialResultPresent"),
        "candidateCreated": admission.get("confirmationExecuted") is True,
        "attemptConsumed": authority.get("attemptConsumed"),
    }
    pass_ = bool(
        not audit_issues
        and audit.get("pass") is True
        and expected_worktree_issues == actual_worktree_issues
        and len(actual_worktree_issues) in {4, 20}
        and immutable_test_blob == original_test_blob
        and state
        == {
            "officialSeedCreated": False,
            "officialFixtureCount": 0,
            "authorityResultPresent": False,
            "candidateCreated": False,
            "attemptConsumed": False,
        }
        and (
            not execute_pytest
            or (
                test_execution.get("returnCode") == 1
                and test_execution.get("collectedExactlyOne") is True
                and test_execution.get("failedExactlyOne") is True
                and test_execution.get("nodeObserved") is True
                and test_execution.get("unexpectedError") is False
            )
        )
    )
    return {
        "schemaVersion": 1,
        "witnessVersion": "closy.strategy3_v2.sealed_failure_witness.v1",
        "lockedNodeId": LOCKED_TEST_NODE,
        "literalOutcome": outcome.get("literalOutcome"),
        "migrationAuditDigest": audit.get("auditDigest"),
        "migrationClassification": {
            "rawBlobExact": audit.get("rawBlobExactCount"),
            "lfToCrlfOnly": audit.get("lfToCrlfOnlyCount"),
            "unexplained": audit.get("unexplainedMismatchCount"),
        },
        "worktreeMismatchCount": len(actual_worktree_issues),
        "worktreeMismatchSignature": actual_worktree_issues,
        "immutableTestSha256": sha256_file(
            forge_root / "tests/unit/test_final_strategy3_v2_protocol.py"
        ),
        "immutableGitBlobUnchanged": immutable_test_blob == original_test_blob,
        "sealedState": state,
        "testExecution": test_execution,
        "pass": pass_,
    }


def _expected_worktree_issues(forge_root: Path, lock: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for row in records(lock.get("implementationFiles")):
        path = str(row.get("path", ""))
        candidate = (forge_root / path).resolve()
        if not candidate.is_file() or sha256_file(candidate) != row.get("sha256"):
            issues.append(f"final_strategy3_implementation_hash_mismatch:{path}")
    return sorted(issues)


def _execute_locked_test(forge_root: Path) -> dict[str, Any]:
    environment = dict(os.environ)
    source = str(forge_root / "src")
    environment["PYTHONPATH"] = (
        source
        if not environment.get("PYTHONPATH")
        else source + os.pathsep + environment["PYTHONPATH"]
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            LOCKED_TEST_NODE,
            "-vv",
            "--tb=short",
            "-o",
            "console_output_style=classic",
        ],
        cwd=forge_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = (result.stdout + "\n" + result.stderr)[-32_768:]
    return {
        "returnCode": result.returncode,
        "collectedExactlyOne": "collected 1 item" in output,
        "failedExactlyOne": "1 failed" in output and "2 failed" not in output,
        "nodeObserved": "test_final_lock_is_self_consistent_when_present" in output,
        "unexpectedError": " ERROR " in output or "errors during collection" in output,
        "diagnosticByteLength": len(output.encode("utf-8")),
    }


def _git_blob(repo_root: Path, commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "cat-file", "blob", f"{commit}:{path}"], cwd=repo_root)
