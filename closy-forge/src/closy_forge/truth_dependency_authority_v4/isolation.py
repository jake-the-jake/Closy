from __future__ import annotations

import locale
import os
import platform
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_bytes

PINNED_PYTHON = "3.11.11"
PINNED_BASE_IMAGE = (
    "python:3.11.11-slim-bookworm@sha256:"
    "081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5"
)
FORBIDDEN_GIT_ENV = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CONFIG_COUNT",
    }
)


def scrub_authority_environment(source: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in source.items()
        if key not in FORBIDDEN_GIT_ENV
        and not key.startswith("GIT_CONFIG_KEY_")
        and not key.startswith("GIT_CONFIG_VALUE_")
        and key not in {"GH_TOKEN", "GITHUB_TOKEN"}
    }


def contestant_container_command(
    image: str,
    *,
    input_path: Path,
    output_path: Path,
) -> list[str]:
    return [
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
        "TZ=UTC",
        "--env",
        "OMP_NUM_THREADS=1",
        "--env",
        "OPENBLAS_NUM_THREADS=1",
        "-v",
        f"{input_path.resolve()}:/inputs:ro",
        "-v",
        f"{output_path.resolve()}:/outputs:rw",
        image,
    ]


def verify_git_blob_manifest(
    repo_root: Path, rows: Sequence[Mapping[str, Any]], *, commit: str
) -> list[str]:
    issues: list[str] = []
    for row in rows:
        path = str(row.get("path", ""))
        expected_oid = str(row.get("oid", ""))
        expected_mode = str(row.get("mode", ""))
        expected_length = int(row.get("byteLength", -1))
        expected_sha = str(row.get("sha256", ""))
        try:
            listing = _git(repo_root, "ls-tree", commit, "--", path).split()
            if len(listing) < 4:
                issues.append("blob_path_missing")
                continue
            mode, kind, oid = listing[:3]
            data = subprocess.run(
                ["git", "cat-file", "blob", oid],
                cwd=repo_root,
                check=True,
                capture_output=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            issues.append("blob_materialization_failed")
            continue
        if kind != "blob" or mode != expected_mode:
            issues.append("blob_mode_or_kind_mismatch")
        if oid != expected_oid:
            issues.append("blob_oid_mismatch")
        if len(data) != expected_length:
            issues.append("blob_length_mismatch")
        if sha256_bytes(data) != expected_sha:
            issues.append("blob_sha256_mismatch")
    return sorted(set(issues))


def observed_environment() -> dict[str, Any]:
    return {
        "os": platform.platform(),
        "cpu": platform.processor() or "unreported",
        "python": platform.python_version(),
        "locale": locale.setlocale(locale.LC_ALL, None),
        "timezone": os.environ.get("TZ", "host_uncontrolled"),
        "threadCounts": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"},
        "hostedKernelAndCpuControlled": False,
        "pinnedBaseImage": PINNED_BASE_IMAGE,
    }


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
