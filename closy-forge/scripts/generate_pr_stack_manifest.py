from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

REPOSITORY = "jake-the-jake/Closy"
RUN_RE = re.compile(r"/runs/(?P<run>\d+)/job/(?P<job>\d+)")


def _run(*args: str, cwd: Path) -> str:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _pr(number: int, repo_root: Path) -> dict[str, Any]:
    raw = _run(
        "gh",
        "pr",
        "view",
        str(number),
        "--repo",
        REPOSITORY,
        "--json",
        (
            "number,title,headRefName,baseRefName,headRefOid,isDraft,mergeable,"
            "changedFiles,statusCheckRollup,url"
        ),
        cwd=repo_root,
    )
    pr = json.loads(raw)
    base_sha = _run("git", "rev-parse", str(pr["baseRefName"]), cwd=repo_root)
    merge_base = _run(
        "git", "merge-base", str(pr["baseRefName"]), str(pr["headRefOid"]), cwd=repo_root
    )
    ahead_behind = _run(
        "git",
        "rev-list",
        "--left-right",
        "--count",
        f"{base_sha}...{pr['headRefOid']}",
        cwd=repo_root,
    ).split()
    checks = []
    run_id: str | None = None
    for check in pr.get("statusCheckRollup", []):
        if check.get("workflowName") != "Closy Forge":
            continue
        match = RUN_RE.search(str(check.get("detailsUrl", "")))
        if match:
            run_id = match.group("run")
        checks.append(
            {
                "conclusion": check.get("conclusion"),
                "jobId": match.group("job") if match else None,
                "name": check.get("name"),
            }
        )
    exact_run = {"exactHead": True, "jobs": checks, "runId": run_id} if checks and run_id else None
    exception = None
    if number == 10:
        exception = {
            "code": "missing_exact_head_forge_run",
            "descendantEvidenceIsExactHead": False,
            "descendantPr": 11,
            "headSha": pr["headRefOid"],
            "predecessorRunId": "32980095316",
            "predecessorSha": "d49227b3e13ba269dfa33b65c7221a54838631d5",
        }
    return {
        "baseBranch": pr["baseRefName"],
        "baseSha": base_sha,
        "branch": pr["headRefName"],
        "changedFileCount": int(pr["changedFiles"]),
        "directParentMergeBaseVerified": merge_base == base_sha,
        "draft": bool(pr["isDraft"]),
        "headSha": pr["headRefOid"],
        "knownException": exception,
        "latestExactHeadForgeRun": exact_run,
        "layerAhead": int(ahead_behind[1]),
        "layerBehind": int(ahead_behind[0]),
        "layerCommitCount": int(
            _run("git", "rev-list", "--count", f"{base_sha}..{pr['headRefOid']}", cwd=repo_root)
        ),
        "mergeability": pr["mergeable"],
        "number": number,
        "repository": REPOSITORY,
        "title": pr["title"],
        "url": pr["url"],
    }


def _open_forge_pr_numbers(repo_root: Path) -> list[int]:
    raw = _run(
        "gh",
        "pr",
        "list",
        "--repo",
        REPOSITORY,
        "--state",
        "open",
        "--limit",
        "100",
        "--json",
        "number,headRefName",
        cwd=repo_root,
    )
    rows = json.loads(raw)
    return sorted(
        int(row["number"])
        for row in rows
        if str(row.get("headRefName", "")).startswith("codex/closy-forge-")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the read-only Closy draft PR stack.")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    pull_requests = [_pr(number, root) for number in _open_forge_pr_numbers(root)]
    payload = {
        "capturePolicy": "read_only_github_and_local_git_snapshot",
        "repository": REPOSITORY,
        "schemaVersion": 1,
        "sequentialMergeOrder": [row["number"] for row in pull_requests],
        "sequentialMergeRehearsal": {
            "mode": "read_only_direct_parent_merge_base_verification",
            "passed": all(
                row["directParentMergeBaseVerified"] and row["layerBehind"] == 0
                for row in pull_requests
            ),
        },
        "pullRequests": pull_requests,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
