from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

TEST_SHARD_COUNT = 4
TEST_SHARD_NAMES = tuple(f"shard-{index}" for index in range(TEST_SHARD_COUNT))


def discover_sharded_tests(forge_root: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.relative_to(forge_root).as_posix()
            for directory in (
                forge_root / "tests" / "unit",
                forge_root / "tests" / "corruption",
            )
            for path in directory.glob("test_*.py")
            if path.is_file()
        )
    )


def assign_test_shards(forge_root: Path) -> dict[str, tuple[str, ...]]:
    discovered = discover_sharded_tests(forge_root)
    return {
        name: discovered[index::TEST_SHARD_COUNT] for index, name in enumerate(TEST_SHARD_NAMES)
    }


def validate_test_shards(forge_root: Path) -> list[str]:
    discovered = discover_sharded_tests(forge_root)
    shards = assign_test_shards(forge_root)
    assigned = tuple(path for name in TEST_SHARD_NAMES for path in shards[name])
    errors: list[str] = []
    if len(assigned) != len(set(assigned)):
        errors.append("duplicate test assignment")
    if set(assigned) != set(discovered):
        errors.append("test shard coverage mismatch")
    errors.extend(f"empty test shard: {name}" for name, paths in shards.items() if not paths)
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a stable Forge unit/corruption test shard.")
    parser.add_argument("--group", choices=TEST_SHARD_NAMES, required=True)
    parser.add_argument("--list", action="store_true", help="List files without running pytest.")
    args = parser.parse_args(argv)
    forge_root = Path(__file__).resolve().parents[3]
    errors = validate_test_shards(forge_root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 2
    paths = assign_test_shards(forge_root)[args.group]
    if args.list:
        print("\n".join(paths))
        return 0
    return subprocess.run(
        [sys.executable, "-m", "pytest", *paths], cwd=forge_root, check=False
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
