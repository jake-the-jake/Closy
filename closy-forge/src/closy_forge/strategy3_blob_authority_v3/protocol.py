from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.truth_authority_integrity_v3.migration_audit import (
    V2_LOCK_COMMIT,
    audit_v2_lock,
    validate_migration_audit,
)

from .common import canonical_bytes, canonical_digest, mapping, records
from .git_blobs import GitBlobReader, validate_path_set
from .inventory import build_inventory

SCIENTIFIC_SOURCE_COMMIT = V2_LOCK_COMMIT
LOCK_PATH = Path("fixtures/strategy3_blob_authority_v3/repository_blob_lock.json")
OFFICIAL_ROOT = Path("fixtures/strategy3_blob_authority_v3/official_attempt")
OUTCOMES = (
    "strategy3_admitted_repository_blob_authority_v3",
    "strategy3_scientific_admission_failed_v3",
    "strategy3_authority_integrity_error_after_seed_v3",
    "strategy3_dependency_blocked_before_seed_v3",
)
LOCK_COMMIT_ALLOWLIST = (
    "closy-forge/fixtures/strategy3_blob_authority_v3/repository_blob_lock.json",
    "closy-forge/docs/evidence/strategy3_blob_authority_v3/lock_publication.json",
)


def build_lock(repo_root: Path, *, wrapper_source_commit: str) -> dict[str, Any]:
    reader = GitBlobReader(repo_root)
    source = reader.resolve_commit(wrapper_source_commit)
    inventory = build_inventory(
        reader,
        scientific_commit=SCIENTIFIC_SOURCE_COMMIT,
        wrapper_commit=source,
    )
    v2_protocol = mapping(
        json.loads(
            reader.blob_at(
                SCIENTIFIC_SOURCE_COMMIT,
                "closy-forge/fixtures/final_strategy3_v2/final_implementation_lock.json",
            )
        )
    )
    migration = audit_v2_lock(repo_root)
    if validate_migration_audit(migration):
        raise ValueError("strategy3_v3_v2_migration_audit_failed")
    blobs = records(inventory["rows"])
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "lockVersion": "closy.strategy3.repository_blob_authority_lock.v3",
        "repository": "jake-the-jake/Closy",
        "scientificSourceCommit": SCIENTIFIC_SOURCE_COMMIT,
        "scientificSourceTree": inventory["scientificSourceTree"],
        "authorityWrapperSourceCommit": source,
        "authorityWrapperSourceTree": inventory["authorityWrapperSourceTree"],
        "strategyId": v2_protocol["strategyId"],
        "strategyClass": v2_protocol["strategyClass"],
        "strategyAlgorithmChanged": False,
        "topologyStrategyBudgetRestored": False,
        "newStrategyIntroduced": False,
        "frozenScientificImplementationDigestV2": v2_protocol["implementationDigest"],
        "v2MigrationAuditDigest": migration["auditDigest"],
        "v2MigrationClassification": {
            "rawBlobExact": migration["rawBlobExactCount"],
            "lfToCrlfOnly": migration["lfToCrlfOnlyCount"],
            "unexplained": migration["unexplainedMismatchCount"],
        },
        "publicConformance": {
            "fixturePassCount": 8,
            "fixtureDenominator": 8,
            "decisionsUnchanged": migration["publicConformance"]["decisionsUnchanged"],
            "qualificationEligible": False,
        },
        "baseImageDigest": inventory["baseImageDigest"],
        "pinnedActions": inventory["actions"],
        "dockerCopyInputs": inventory["dockerCopyInputs"],
        "blobCount": inventory["blobCount"],
        "executionImageBlobCount": inventory["executionImageBlobCount"],
        "blobs": blobs,
        "inventoryDigest": inventory["inventoryDigest"],
        "protocol": {
            "fixtureStrata": v2_protocol["fixtureStrata"],
            "fixtureDenominator": 8,
            "metrics": v2_protocol["metrics"],
            "mutations": v2_protocol["mutations"],
            "numericPolicy": v2_protocol["numericPolicy"],
            "resourceBudgets": v2_protocol["resourceBudgets"],
            "futurePostTopologyC3": v2_protocol["futurePostTopologyC3"],
            "futureGateZ2Core": v2_protocol["futureGateZ2Core"],
        },
        "isolation": {
            "network": "none",
            "rootFilesystem": "read_only",
            "uid": 65532,
            "capabilities": "all_dropped",
            "noNewPrivileges": True,
            "maximumPids": 128,
            "contestantInputs": ["fixture.json"],
            "forbiddenInputs": [
                "repository",
                "evaluator_target",
                "raw_seed",
                "oracle",
                "docker_socket",
                "host_home",
                "secrets",
                "network",
                "undeclared_environment",
            ],
        },
        "budgets": {
            "seamModelsRemaining": 0,
            "topologyStrategiesAvailable": 0,
            "strategy3Reserved": True,
            "strategy3Consumed": True,
            "strategy3ScientificAdmissionExecuted": False,
            "untouchedConfirmationAttemptConsumed": False,
            "canonicalCandidateAttemptsRemaining": 1,
        },
        "authority": {
            "seedDomain": "closy.phy1.strategy3.repository_blob_authority.v3",
            "seedEntropyBits": 256,
            "commitmentsBeforeContestantJob": True,
            "contestantOutputFrozenBeforeReveal": True,
            "allFailuresRetainedInDenominator": True,
            "rerunAllowed": False,
            "replacementLockAllowed": False,
        },
        "outcomeVocabulary": list(OUTCOMES),
        "lockCommitChangedPathAllowlist": list(LOCK_COMMIT_ALLOWLIST),
        "officialSeedCreated": False,
        "officialFixturePresent": False,
        "officialResultPresent": False,
        "lockDigest": "",
    }
    document["lockDigest"] = canonical_digest(document, "lockDigest")
    issues = validate_lock(repo_root, document, verify_objects=True)
    if issues:
        raise ValueError(";".join(issues))
    return document


def validate_lock(
    repo_root: Path, lock: Mapping[str, Any], *, verify_objects: bool = True
) -> list[str]:
    issues: list[str] = []
    document = dict(lock)
    if document.get("lockVersion") != "closy.strategy3.repository_blob_authority_lock.v3":
        issues.append("strategy3_v3_lock_version_invalid")
    if document.get("scientificSourceCommit") != SCIENTIFIC_SOURCE_COMMIT:
        issues.append("strategy3_v3_scientific_source_invalid")
    if document.get("outcomeVocabulary") != list(OUTCOMES):
        issues.append("strategy3_v3_outcome_vocabulary_invalid")
    if any(
        document.get(key) is not False
        for key in (
            "strategyAlgorithmChanged",
            "topologyStrategyBudgetRestored",
            "newStrategyIntroduced",
        )
    ):
        issues.append("strategy3_v3_frozen_strategy_claim_invalid")
    classification = mapping(document.get("v2MigrationClassification", {}))
    if classification != {"rawBlobExact": 20, "lfToCrlfOnly": 4, "unexplained": 0}:
        issues.append("strategy3_v3_migration_classification_invalid")
    rows = records(document.get("blobs", []))
    paths = [str(row.get("repositoryPath", "")) for row in rows]
    try:
        validate_path_set(paths)
    except ValueError as error:
        issues.append(str(error))
    if paths != sorted(paths) or [row.get("ordinal") for row in rows] != list(range(len(rows))):
        issues.append("strategy3_v3_blob_order_invalid")
    if document.get("blobCount") != len(rows):
        issues.append("strategy3_v3_blob_count_invalid")
    if document.get("executionImageBlobCount") != sum(
        row.get("entersExecutionImage") is True for row in rows
    ):
        issues.append("strategy3_v3_execution_blob_count_invalid")
    inventory = {
        "inventoryVersion": "closy.strategy3.repository_blob_inventory.v3",
        "repository": document.get("repository"),
        "scientificSourceCommit": document.get("scientificSourceCommit"),
        "scientificSourceTree": document.get("scientificSourceTree"),
        "authorityWrapperSourceCommit": document.get("authorityWrapperSourceCommit"),
        "authorityWrapperSourceTree": document.get("authorityWrapperSourceTree"),
        "baseImageDigest": document.get("baseImageDigest"),
        "actions": document.get("pinnedActions"),
        "dockerCopyInputs": document.get("dockerCopyInputs"),
        "blobCount": document.get("blobCount"),
        "executionImageBlobCount": document.get("executionImageBlobCount"),
        "rows": rows,
        "inventoryDigest": "",
    }
    expected_inventory = hashlib.sha256(canonical_bytes(inventory)).hexdigest()
    if document.get("inventoryDigest") != expected_inventory:
        issues.append("strategy3_v3_inventory_digest_invalid")
    if document.get("lockDigest") != canonical_digest(document, "lockDigest"):
        issues.append("strategy3_v3_lock_digest_invalid")
    if verify_objects:
        try:
            reader = GitBlobReader(repo_root)
            for row in rows:
                identity = reader.identity(str(row["commit"]), str(row["repositoryPath"]))
                expected = {
                    "rootTreeObjectId": identity.root_tree_object_id,
                    "gitMode": identity.git_mode,
                    "objectType": identity.object_type,
                    "rawBlobOid": identity.blob_oid,
                    "rawBlobSha256": identity.sha256,
                    "rawBlobByteLength": identity.byte_length,
                }
                if any(row.get(key) != value for key, value in expected.items()):
                    issues.append(f"strategy3_v3_blob_identity_mismatch:{row['repositoryPath']}")
        except (KeyError, subprocess.CalledProcessError, ValueError) as error:
            issues.append(f"strategy3_v3_object_validation_failed:{type(error).__name__}")
    return sorted(set(issues))


def validate_lock_commit(repo_root: Path, lock: Mapping[str, Any], lock_commit: str) -> list[str]:
    source = str(lock.get("authorityWrapperSourceCommit", ""))
    resolved = GitBlobReader(repo_root).resolve_commit(lock_commit)
    changed = subprocess.run(
        ["git", "diff", "--name-only", source, resolved],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    allowed = set(LOCK_COMMIT_ALLOWLIST)
    issues: list[str] = []
    if not changed or set(changed) - allowed:
        issues.append("strategy3_v3_lock_commit_allowlist_failed")
    if "closy-forge/fixtures/strategy3_blob_authority_v3/repository_blob_lock.json" not in changed:
        issues.append("strategy3_v3_lock_file_not_added_at_lock_commit")
    return issues


def load_lock(forge_root: Path) -> dict[str, Any]:
    return mapping(json.loads((forge_root / LOCK_PATH).read_text(encoding="utf-8")))
