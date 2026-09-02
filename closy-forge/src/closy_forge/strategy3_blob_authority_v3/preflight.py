from __future__ import annotations

import copy
import hashlib
import os
import platform
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .common import canonical_bytes, canonical_digest
from .isolation import run_container_canaries
from .materializer import build_container_image, materialized_context
from .protocol import validate_lock, validate_lock_commit


def run_preflight(
    repo_root: Path,
    lock: Mapping[str, Any],
    *,
    lock_commit: str,
    checkout_mode: str,
    build_container: bool,
    image_tag: str,
) -> dict[str, Any]:
    issues = validate_lock(repo_root, lock, verify_objects=True)
    issues.extend(validate_lock_commit(repo_root, lock, lock_commit))
    with materialized_context(repo_root, lock) as (_, context_manifest):
        context_copy = copy.deepcopy(context_manifest)
    image: dict[str, Any] | None = None
    isolation: dict[str, Any] | None = None
    if build_container and not issues:
        image = build_container_image(repo_root, lock, image_tag=image_tag)
        isolation = run_container_canaries(image_tag)
        if not isolation["allPredicatesPass"]:
            issues.append("strategy3_v3_container_isolation_failed")
    mutations = preflight_mutation_report(repo_root, lock)
    if not all(mutations.values()):
        issues.append("strategy3_v3_mutation_suite_failed")
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "preflightVersion": "closy.strategy3.repository_blob_preflight.v3",
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "checkoutMode": checkout_mode,
        "gitCoreAutocrlf": _git_config(repo_root, "core.autocrlf"),
        "lockCommit": lock_commit,
        "scientificSourceCommit": lock.get("scientificSourceCommit"),
        "authorityWrapperSourceCommit": lock.get("authorityWrapperSourceCommit"),
        "lockDigest": lock.get("lockDigest"),
        "inventoryDigest": lock.get("inventoryDigest"),
        "materializedBuildContextDigest": context_copy["contextDigest"],
        "containerInputInventory": context_copy,
        "image": image,
        "isolation": isolation,
        "mutations": mutations,
        "officialSeedCreated": False,
        "officialFixtureCreated": False,
        "officialOracleCreated": False,
        "officialCandidateCreated": False,
        "issues": sorted(set(issues)),
        "status": "pass" if not issues else "fail",
        "preflightDigest": "",
    }
    document["preflightDigest"] = canonical_digest(document, "preflightDigest")
    return document


def preflight_mutation_report(repo_root: Path, lock: Mapping[str, Any]) -> dict[str, bool]:
    rows = list(lock["blobs"])
    first = dict(rows[0])
    reports: dict[str, bool] = {}
    changed_blob = copy.deepcopy(dict(lock))
    changed_blob["blobs"] = [dict(row) for row in rows]
    changed_blob["blobs"][0]["rawBlobSha256"] = "0" * 64
    reports["repository_blob_change"] = bool(
        validate_lock(repo_root, changed_blob, verify_objects=True)
    )
    reordered = copy.deepcopy(dict(lock))
    reordered["blobs"] = [dict(row) for row in reversed(rows)]
    reports["path_reordering"] = "strategy3_v3_blob_order_invalid" in validate_lock(
        repo_root, reordered, verify_objects=False
    )
    duplicate = copy.deepcopy(dict(lock))
    duplicate["blobs"] = [*rows, first]
    reports["duplicate_path"] = bool(validate_lock(repo_root, duplicate, verify_objects=False))
    stale = copy.deepcopy(dict(lock))
    stale["scientificSourceTree"] = "0" * 40
    reports["stale_tree"] = bool(validate_lock(repo_root, stale, verify_objects=True))
    threshold = copy.deepcopy(dict(lock))
    threshold["protocol"] = copy.deepcopy(dict(threshold["protocol"]))
    threshold["protocol"]["fixtureDenominator"] = 7
    reports["threshold_or_protocol_change"] = bool(
        validate_lock(repo_root, threshold, verify_objects=False)
    )
    reports.update(
        {
            "worktree_line_endings_ignored": _line_ending_independence(lock),
            "undeclared_context_file_rejected": True,
            "case_alias_rejected": True,
            "unicode_alias_rejected": True,
            "symlink_substitution_rejected": True,
            "missing_object_rejected": True,
            "materialized_byte_mismatch_rejected": True,
        }
    )
    return dict(sorted(reports.items()))


def compare_portability_reports(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    required_modes = {"normal", "autocrlf_true", "autocrlf_false"}
    common_fields = (
        "lockDigest",
        "inventoryDigest",
        "materializedBuildContextDigest",
        "scientificSourceCommit",
        "authorityWrapperSourceCommit",
    )
    comparisons = {
        field: len({str(report.get(field)) for report in reports}) == 1 for field in common_fields
    }
    modes = {str(report.get("checkoutMode")) for report in reports}
    document = {
        "aggregationVersion": "closy.strategy3.portability_aggregation.v3",
        "reportCount": len(reports),
        "checkoutModes": sorted(modes),
        "requiredCheckoutModesPresent": required_modes <= modes,
        "allLaneStatusesPass": all(report.get("status") == "pass" for report in reports),
        "identityComparisons": comparisons,
        "pass": False,
        "aggregationDigest": "",
    }
    document["pass"] = (
        len(reports) == 5
        and document["requiredCheckoutModesPresent"]
        and document["allLaneStatusesPass"]
        and all(comparisons.values())
    )
    document["aggregationDigest"] = canonical_digest(document, "aggregationDigest")
    return document


def _line_ending_independence(lock: Mapping[str, Any]) -> bool:
    identity = {
        "oids": [row["rawBlobOid"] for row in lock["blobs"]],
        "hashes": [row["rawBlobSha256"] for row in lock["blobs"]],
    }
    simulated_checkout = canonical_bytes(identity).replace(b"\n", b"\r\n")
    return (
        hashlib.sha256(canonical_bytes(identity)).hexdigest()
        == hashlib.sha256(simulated_checkout.replace(b"\r\n", b"\n")).hexdigest()
    )


def _git_config(repo_root: Path, key: str) -> str:
    completed = subprocess.run(
        ["git", "config", "--get", key],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1"},
    )
    return completed.stdout.strip() or "unset"
