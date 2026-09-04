from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from .common import canonical_digest, read_json, write_json

SOURCE_PREFIXES = (
    "closy-forge/src/closy_forge/solver_material_v2/",
    "closy-forge/scripts/solver_material_v2.py",
    "closy-forge/src/closy_forge/cli/main.py",
    "closy-forge/tests/unit/test_solver_material_v2_",
    "closy-forge/schemas/solver_material_v2/",
    "closy-forge/fixtures/solver_material_v2/protocol.json",
    "closy-forge/fixtures/solver_material_v2/real_coupon_template.csv",
    "closy-forge/docs/evidence/solver_material_v2/",
    "closy-forge/docs/phase7-solver-material-v2.md",
)


def build_source_freeze(repository: Path, source_commit: str, source_tree: str) -> dict[str, Any]:
    protocol = read_json(
        repository / "closy-forge" / "fixtures" / "solver_material_v2" / "protocol.json"
    )
    changed = _git(
        repository, "diff", "--name-only", "fad7ff76b1a92643229c2db1d7fb62b57e4ce90d", source_commit
    ).splitlines()
    paths = sorted(path for path in changed if path.startswith(SOURCE_PREFIXES))
    rows = [_blob_record(repository, source_commit, path) for path in paths]
    freeze: dict[str, Any] = {
        "schemaVersion": 2,
        "freezeVersion": "closy.solver_material_v2_source_freeze.v1",
        "sourceCommit": source_commit,
        "sourceTree": source_tree,
        "protocolId": protocol["protocolId"],
        "protocolDigest": protocol["protocolDigest"],
        "implementationFileCount": len(rows),
        "implementationInventory": rows,
        "implementationInventoryDigest": canonical_digest(rows),
        "frozenProperties": [
            "solver_route",
            "specimens",
            "units",
            "generator",
            "estimator",
            "evaluator",
            "partitions",
            "thresholds",
            "optimizer_budget",
            "stopping_rules",
            "failure_taxonomy",
            "single_seed_rule",
        ],
    }
    freeze["freezeDigest"] = canonical_digest(freeze)
    write_json(
        repository / "closy-forge" / "fixtures" / "solver_material_v2" / "source_freeze.json",
        freeze,
    )
    return freeze


def verify_source_freeze(repository: Path, freeze: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if _git(repository, "rev-parse", f"{freeze['sourceCommit']}^{{tree}}") != freeze.get(
        "sourceTree"
    ):
        failures.append("source_tree_invalid")
    rows = freeze.get("implementationInventory", [])
    for row in rows:
        current = _blob_record(repository, str(freeze["sourceCommit"]), str(row["path"]))
        if current != row:
            failures.append(f"source_blob_invalid:{row['path']}")
        head = _blob_record(repository, "HEAD", str(row["path"]))
        if head != row:
            failures.append(f"post_freeze_source_edit:{row['path']}")
    if freeze.get("implementationInventoryDigest") != canonical_digest(rows):
        failures.append("source_inventory_digest_invalid")
    if freeze.get("freezeDigest") != canonical_digest(freeze, "freezeDigest"):
        failures.append("source_freeze_digest_invalid")
    return sorted(set(failures))


def build_seed_authority(freeze: dict[str, Any], exact_head_run_id: str) -> dict[str, Any]:
    domain = "CLOSY_SOLVER_MATERIAL_V2_LOCKED_TEST_SEED_V1"
    material = f"{domain}|{freeze['sourceTree']}|{exact_head_run_id}".encode()
    authority: dict[str, Any] = {
        "schemaVersion": 2,
        "authorityType": "protocol_local_synthetic_engineering_test_seed",
        "domainSeparator": domain,
        "frozenSourceCommit": freeze["sourceCommit"],
        "frozenSourceTree": freeze["sourceTree"],
        "firstSuccessfulExactHeadRunId": str(exact_head_run_id),
        "derivedSeedCommitment": hashlib.sha256(material).hexdigest(),
        "derivedSeedCount": 1,
        "alternateTriedCount": 0,
        "alternateDiscardedCount": 0,
        "y2AuthorityConsumed": False,
        "canonicalGeometryCandidateBudgetConsumed": False,
        "seedValueDisclosed": False,
    }
    authority["authorityDigest"] = canonical_digest(authority)
    return authority


def derive_private_seed(freeze: dict[str, Any], exact_head_run_id: str) -> str:
    domain = "CLOSY_SOLVER_MATERIAL_V2_LOCKED_TEST_SEED_V1"
    return hashlib.sha256(
        f"{domain}|{freeze['sourceTree']}|{exact_head_run_id}".encode()
    ).hexdigest()


def _blob_record(repository: Path, commit: str, path: str) -> dict[str, Any]:
    oid = _git(repository, "rev-parse", f"{commit}:{path}")
    payload = subprocess.check_output(["git", "cat-file", "blob", oid], cwd=repository)
    return {
        "path": path,
        "gitBlobOid": oid,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }


def _git(repository: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repository, text=True).strip()
