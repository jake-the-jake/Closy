"""One cumulative final-code validation with durable bounded process receipts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from closy_forge.ci.test_shards import (
    SEALED_V2_FAILURE_NODE,
    assign_test_shards,
    validate_test_shards,
)
from closy_forge.package_io.hashing import sha256_file

FORGE = Path(__file__).resolve().parents[1]


def write(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(output: Path) -> int:
    if output.exists():
        raise ValueError("cumulative_receipt_directory_must_be_fresh")
    output.mkdir(parents=True)
    sources = {
        p.relative_to(FORGE).as_posix(): sha256_file(p)
        for folder in ("src", "scripts", "tests")
        for p in sorted((FORGE / folder).rglob("*.py"))
    }
    write(output / "source_inventory.json", sources)
    for suite in ("unit", "integration"):
        if validate_test_shards(FORGE, suite):
            raise ValueError("cumulative_shard_inventory_invalid")
    write(
        output / "shard_membership.json",
        {
            "unit": assign_test_shards(FORGE),
            "integration": assign_test_shards(FORGE, "integration"),
            "dedicatedImmutableFailureLane": {
                "node": SEALED_V2_FAILURE_NODE,
                "policy": "same_regular_suite_deselection_as_existing_CI_not_a_new_skip",
                "requiredCheck": "scripts/verify_sealed_v2_failure.py in exact-head remote CI",
            },
        },
    )
    commands = [
        ("format", ["ruff", "format", "--check", ".", "--exclude", ".tmp"], 180),
        ("lint", ["ruff", "check", ".", "--exclude", ".tmp"], 180),
        ("types", ["mypy", "src"], 600),
        ("schemas", ["closy_forge", "schemas", "check", "--schema-dir", "schemas/v1"], 180),
        (
            "unit_inventory",
            ["closy_forge.ci.test_shards", "--group", "shard-0", "--inventory-digest"],
            60,
        ),
        (
            "integration_inventory",
            [
                "closy_forge.ci.test_shards",
                "--suite",
                "integration",
                "--group",
                "shard-0",
                "--inventory-digest",
            ],
            60,
        ),
        ("test_collection", ["pytest", "--collect-only", "-q", "-o", "addopts="], 180),
        (
            "cumulative",
            [
                "pytest",
                "-q",
                "-o",
                "addopts=",
                "--deselect",
                SEALED_V2_FAILURE_NODE,
                f"--junitxml={output / 'cumulative.xml'}",
            ],
            10800,
        ),
    ]
    receipts: list[dict[str, Any]] = []
    env = {**os.environ, "PYTHONPATH": str(FORGE / "src"), "MYPYPATH": str(FORGE / "src")}
    for name, arguments, timeout in commands:
        command = [sys.executable, "-m", *arguments]
        started = time.perf_counter()
        log_path = output / f"{name}.log"
        with log_path.open("w", encoding="utf-8") as log:
            try:
                process = subprocess.run(
                    command,
                    cwd=FORGE,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
                exit_code: int | None = process.returncode
                status = "passed" if exit_code == 0 else "failed"
            except subprocess.TimeoutExpired:
                exit_code, status = None, "timeout"
        receipt = {
            "name": name,
            "command": command,
            "exitCode": exit_code,
            "status": status,
            "wallSeconds": time.perf_counter() - started,
            "logSha256": sha256_file(log_path),
        }
        receipts.append(receipt)
        write(output / "checkpoint.json", receipts)
        print(f"{name}: {status} exit={exit_code}", flush=True)
        if exit_code != 0:
            break  # Diagnose cheap failures before spending hours on the full suite.
        if name == "test_collection":
            ids = [
                line.strip()
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if "::" in line and line.startswith("tests/")
            ]
            if len(ids) != len(set(ids)) or not ids:
                raise ValueError("cumulative_collection_duplicate_or_empty")
            write(output / "unique_test_ids.json", ids)
    fresh = all(sha256_file(FORGE / p) == digest for p, digest in sources.items())
    current_paths = {
        p.relative_to(FORGE).as_posix()
        for folder in ("src", "scripts", "tests")
        for p in (FORGE / folder).rglob("*.py")
    }
    fresh = fresh and current_paths == set(sources)
    passed = (
        fresh and len(receipts) == len(commands) and all(r["status"] == "passed" for r in receipts)
    )
    write(output / "result.json", {"passed": passed, "sourceFresh": fresh, "commands": receipts})
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    return run(args.output.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
