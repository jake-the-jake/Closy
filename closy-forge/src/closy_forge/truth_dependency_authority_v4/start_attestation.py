from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def validate_start_attestation(repo_root: Path, attestation: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    source = _mapping(attestation.get("source"))
    source_commit = str(source.get("commit", ""))
    if _git(repo_root, "rev-parse", f"{source_commit}^{{tree}}") != source.get("tree"):
        issues.append("start_source_tree_mismatch")
    main = _mapping(attestation.get("main"))
    if _git(repo_root, "rev-parse", str(main.get("sha", ""))) != main.get("sha"):
        issues.append("start_main_commit_missing")
    for pull_request in _records(attestation.get("pullRequests")):
        base = str(pull_request.get("baseSha", ""))
        head = str(pull_request.get("head", ""))
        if _git(repo_root, "merge-base", base, head) != pull_request.get("mergeBase"):
            issues.append("start_pull_request_merge_base_mismatch")
        if int(_git(repo_root, "rev-list", "--count", f"{base}..{head}")) != int(
            pull_request.get("commitCount", -1)
        ):
            issues.append("start_pull_request_commit_count_mismatch")
        files = _git(repo_root, "diff", "--name-only", f"{base}...{head}").splitlines()
        if len(files) != int(pull_request.get("changedFileCount", -1)):
            issues.append("start_pull_request_file_count_mismatch")
        forge = _mapping(pull_request.get("forge"))
        if int(forge.get("passed", 0)) + int(forge.get("failed", 0)) != int(forge.get("total", -1)):
            issues.append("start_forge_job_total_mismatch")
        if _mapping(pull_request.get("supabase")).get("conclusion") != "SKIPPED":
            issues.append("start_supabase_state_not_separate")
    cumulative = _git(
        repo_root,
        "rev-list",
        "--left-right",
        "--count",
        f"{main.get('sha')}...{source_commit}",
    ).split()
    declared = _mapping(attestation.get("cumulativeAgainstMain"))
    if cumulative != [str(declared.get("behind")), str(declared.get("ahead"))]:
        issues.append("start_cumulative_ahead_behind_mismatch")
    if not _mapping(attestation.get("sealedExperiments")):
        issues.append("start_sealed_experiment_inventory_missing")
    if not attestation.get("dirtyPrimaryWorktreeExclusion"):
        issues.append("start_dirty_exclusion_missing")
    return sorted(set(issues))


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: object) -> list[dict[str, Any]]:
    return [dict(row) for row in value] if isinstance(value, list) else []
