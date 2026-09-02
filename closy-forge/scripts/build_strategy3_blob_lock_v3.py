from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from closy_forge.strategy3_blob_authority_v3.common import write_json
from closy_forge.strategy3_blob_authority_v3.protocol import (
    LOCK_PATH,
    build_lock,
    load_lock,
    validate_lock,
    validate_lock_commit,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FORGE_ROOT = REPO_ROOT / "closy-forge"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wrapper-source")
    parser.add_argument("--lock-commit")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        lock = load_lock(FORGE_ROOT)
        issues = validate_lock(REPO_ROOT, lock, verify_objects=True)
        issues.extend(
            validate_lock_commit(REPO_ROOT, lock, args.lock_commit or _git("rev-parse", "HEAD"))
        )
        print(
            json.dumps({"status": "pass" if not issues else "fail", "issues": sorted(set(issues))})
        )
        return 0 if not issues else 1
    if not args.wrapper_source:
        raise ValueError("--wrapper-source is required when creating the final lock")
    if _git("status", "--porcelain"):
        raise ValueError("strategy3_v3_lock_requires_clean_worktree")
    lock = build_lock(REPO_ROOT, wrapper_source_commit=args.wrapper_source)
    write_json(FORGE_ROOT / LOCK_PATH, lock)
    print(
        json.dumps(
            {
                "status": "pass",
                "lockDigest": lock["lockDigest"],
                "blobCount": lock["blobCount"],
                "wrapperSource": lock["authorityWrapperSourceCommit"],
            },
            sort_keys=True,
        )
    )
    return 0


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
