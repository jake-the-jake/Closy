from __future__ import annotations

import copy
import subprocess
from pathlib import Path

import pytest

from closy_forge.strategy3_blob_authority_v3.git_blobs import (
    GitBlobReader,
    normalize_repository_path,
    validate_path_set,
)
from closy_forge.strategy3_blob_authority_v3.materializer import materialized_context
from closy_forge.strategy3_blob_authority_v3.protocol import build_lock, validate_lock

FORGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = FORGE_ROOT.parent


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.mark.parametrize(
    "path",
    ["../secret", "/absolute", "folder\\alias.py", "folder//double.py", "a/../b.py"],
)
def test_unsafe_repository_paths_are_rejected(path: str) -> None:
    with pytest.raises(ValueError):
        normalize_repository_path(path)


def test_case_and_unicode_aliases_are_rejected() -> None:
    with pytest.raises(ValueError, match="collision"):
        validate_path_set(["closy-forge/A.py", "closy-forge/a.py"])
    with pytest.raises(ValueError, match="not_nfc"):
        validate_path_set(["closy-forge/cafe\u0301.py"])


def test_symlink_and_missing_objects_fail_closed() -> None:
    reader = GitBlobReader(REPO_ROOT)
    with pytest.raises(ValueError):
        reader.identity(_head(), ".git")
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        reader.blob("0" * 40)


def test_mutated_blob_tree_order_and_duplicate_fail_lock_validation() -> None:
    lock = build_lock(REPO_ROOT, wrapper_source_commit=_head())
    changed_blob = copy.deepcopy(lock)
    changed_blob["blobs"][0]["rawBlobOid"] = "0" * 40
    assert validate_lock(REPO_ROOT, changed_blob, verify_objects=True)
    stale_tree = copy.deepcopy(lock)
    stale_tree["authorityWrapperSourceTree"] = "0" * 40
    assert validate_lock(REPO_ROOT, stale_tree, verify_objects=True)
    reordered = copy.deepcopy(lock)
    reordered["blobs"] = list(reversed(reordered["blobs"]))
    assert "strategy3_v3_blob_order_invalid" in validate_lock(
        REPO_ROOT, reordered, verify_objects=False
    )
    duplicate = copy.deepcopy(lock)
    duplicate["blobs"].append(copy.deepcopy(duplicate["blobs"][0]))
    assert validate_lock(REPO_ROOT, duplicate, verify_objects=False)


def test_materialized_byte_mismatch_fails_before_context_is_yielded() -> None:
    lock = build_lock(REPO_ROOT, wrapper_source_commit=_head())
    mutated = copy.deepcopy(lock)
    execution_row = next(row for row in mutated["blobs"] if row["entersExecutionImage"])
    execution_row["rawBlobSha256"] = "f" * 64
    with (
        pytest.raises(ValueError, match="materialized_sha_mismatch"),
        materialized_context(REPO_ROOT, mutated),
    ):
        raise AssertionError("mutated context must not be yielded")
