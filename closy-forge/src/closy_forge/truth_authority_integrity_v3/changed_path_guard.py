from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from .common import canonical_digest, load_mapping, records
from .migration_audit import LOCK_PATH, V2_LOCK_COMMIT


def build_frozen_surface_guard(
    repo_root: Path, *, comparison_commit: str = V2_LOCK_COMMIT, head: str = "HEAD"
) -> dict[str, Any]:
    lock = load_mapping(repo_root / LOCK_PATH)
    rows: list[dict[str, Any]] = []
    for source in records(lock.get("implementationFiles")):
        lock_path = str(source["path"])
        repository_path = (
            lock_path.removeprefix("../")
            if lock_path.startswith("../")
            else f"closy-forge/{lock_path}"
        )
        before = _blob(repo_root, comparison_commit, repository_path)
        after = _blob(repo_root, head, repository_path)
        rows.append(
            {
                "repositoryPath": repository_path,
                "comparisonSha256": hashlib.sha256(before).hexdigest(),
                "headSha256": hashlib.sha256(after).hexdigest(),
                "unchanged": before == after,
            }
        )
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "guardVersion": "closy.strategy3_frozen_surface_guard.v1",
        "comparisonCommit": comparison_commit,
        "head": _text(repo_root, "rev-parse", head).strip(),
        "pathCount": len(rows),
        "rows": rows,
        "strategyAlgorithmChanged": any(not row["unchanged"] for row in rows),
        "topologyStrategyBudgetRestored": False,
        "newStrategyIntroduced": False,
        "pass": all(row["unchanged"] for row in rows),
        "guardDigest": "",
    }
    document["guardDigest"] = canonical_digest(document, "guardDigest")
    return document


def _blob(repo_root: Path, commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "cat-file", "blob", f"{commit}:{path}"], cwd=repo_root)


def _text(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True)
