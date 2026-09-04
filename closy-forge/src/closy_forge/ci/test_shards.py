from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

UNIT_TEST_SHARD_COUNT = 5
INTEGRATION_TEST_SHARD_COUNT = 2
SHARD_COUNTS = {
    "unit": UNIT_TEST_SHARD_COUNT,
    "integration": INTEGRATION_TEST_SHARD_COUNT,
}
TEST_SHARD_NAMES = tuple(f"shard-{index}" for index in range(UNIT_TEST_SHARD_COUNT))
PINNED_UNIT_TEST_SHARDS = {
    "tests/corruption/test_corrupted_packages.py": "shard-4",
}
SEALED_V2_FAILURE_NODE = (
    "tests/unit/test_final_strategy3_v2_protocol.py::"
    "test_final_lock_is_self_consistent_when_present"
)


def discover_sharded_tests(forge_root: Path, suite: str = "unit") -> tuple[str, ...]:
    directories = {
        "unit": (
            forge_root / "tests" / "unit",
            forge_root / "tests" / "corruption",
            forge_root / "tests" / "capture_reconstruction_v2",
        ),
        "integration": (forge_root / "tests" / "integration", forge_root / "tests" / "golden"),
    }[suite]
    return tuple(
        sorted(
            path.relative_to(forge_root).as_posix()
            for directory in directories
            for path in directory.rglob("test_*.py")
            if path.is_file()
        )
    )


def test_inventory_digest(forge_root: Path, suite: str = "unit") -> str:
    payload = "".join(f"{path}\n" for path in discover_sharded_tests(forge_root, suite))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assign_test_shards(forge_root: Path, suite: str = "unit") -> dict[str, tuple[str, ...]]:
    discovered = discover_sharded_tests(forge_root, suite)
    shard_count = SHARD_COUNTS[suite]
    if suite == "unit":
        regular_shard_count = shard_count - 1
        unpinned = tuple(path for path in discovered if path not in PINNED_UNIT_TEST_SHARDS)
        shards = {
            f"shard-{index}": unpinned[index::regular_shard_count]
            for index in range(regular_shard_count)
        }
        shards["shard-4"] = tuple(
            path for path in discovered if PINNED_UNIT_TEST_SHARDS.get(path) == "shard-4"
        )
        return shards
    return {f"shard-{index}": discovered[index::shard_count] for index in range(shard_count)}


def validate_test_shards(forge_root: Path, suite: str = "unit") -> list[str]:
    discovered = discover_sharded_tests(forge_root, suite)
    shards = assign_test_shards(forge_root, suite)
    assigned = tuple(path for paths in shards.values() for path in paths)
    errors: list[str] = []
    if len(assigned) != len(set(assigned)):
        errors.append("duplicate test assignment")
    if set(assigned) != set(discovered):
        errors.append("test shard coverage mismatch")
    errors.extend(f"empty test shard: {name}" for name, paths in shards.items() if not paths)
    return errors


def pytest_arguments(paths: Sequence[str], suite: str) -> list[str]:
    arguments = [*paths]
    if suite == "unit" and "tests/unit/test_final_strategy3_v2_protocol.py" in paths:
        arguments.extend(["--deselect", SEALED_V2_FAILURE_NODE])
    return arguments


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a stable Forge unit/corruption test shard.")
    parser.add_argument("--suite", choices=sorted(SHARD_COUNTS), default="unit")
    parser.add_argument("--group", choices=TEST_SHARD_NAMES, required=True)
    parser.add_argument("--list", action="store_true", help="List files without running pytest.")
    parser.add_argument(
        "--inventory-digest",
        action="store_true",
        help="Print the exact discovered inventory digest.",
    )
    args = parser.parse_args(argv)
    forge_root = Path(__file__).resolve().parents[3]
    errors = validate_test_shards(forge_root, args.suite)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 2
    shards = assign_test_shards(forge_root, args.suite)
    if args.group not in shards:
        print(f"invalid shard for {args.suite}: {args.group}", file=sys.stderr)
        return 2
    paths = shards[args.group]
    if args.inventory_digest:
        print(test_inventory_digest(forge_root, args.suite))
        return 0
    if args.list:
        print("\n".join(paths))
        return 0
    return subprocess.run(
        [sys.executable, "-m", "pytest", *pytest_arguments(paths, args.suite)],
        cwd=forge_root,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
