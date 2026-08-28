from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

UNIT_TEST_SHARD_COUNT = 4
INTEGRATION_TEST_SHARD_COUNT = 2
SHARD_COUNTS = {
    "unit": UNIT_TEST_SHARD_COUNT,
    "integration": INTEGRATION_TEST_SHARD_COUNT,
}
TEST_SHARD_NAMES = tuple(f"shard-{index}" for index in range(UNIT_TEST_SHARD_COUNT))


def discover_sharded_tests(forge_root: Path, suite: str = "unit") -> tuple[str, ...]:
    directories = {
        "unit": (forge_root / "tests" / "unit", forge_root / "tests" / "corruption"),
        "integration": (forge_root / "tests" / "integration", forge_root / "tests" / "golden"),
    }[suite]
    return tuple(
        sorted(
            path.relative_to(forge_root).as_posix()
            for directory in directories
            for path in directory.glob("test_*.py")
            if path.is_file()
        )
    )


def assign_test_shards(forge_root: Path, suite: str = "unit") -> dict[str, tuple[str, ...]]:
    discovered = discover_sharded_tests(forge_root, suite)
    shard_count = SHARD_COUNTS[suite]
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a stable Forge unit/corruption test shard.")
    parser.add_argument("--suite", choices=sorted(SHARD_COUNTS), default="unit")
    parser.add_argument("--group", choices=TEST_SHARD_NAMES, required=True)
    parser.add_argument("--list", action="store_true", help="List files without running pytest.")
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
    if args.list:
        print("\n".join(paths))
        return 0
    return subprocess.run(
        [sys.executable, "-m", "pytest", *paths], cwd=forge_root, check=False
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
