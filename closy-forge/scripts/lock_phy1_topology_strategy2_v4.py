from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.phy1_topology_strategy2_v4.strategy import (
    build_strategy_lock,
    validate_strategy_lock,
)

RELATIVE_PATH = Path("fixtures/phy1_topology_strategy2_v4/strategy_lock.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--validate-committed", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    expected = build_strategy_lock(root)
    path = root / RELATIVE_PATH
    if args.validate_committed:
        actual = read_json(path)
        issues = validate_strategy_lock(root, dict(actual))
        if issues:
            raise ValueError("unit_i_strategy_lock_invalid:" + ",".join(issues))
    else:
        write_canonical_json(path, expected)
    print(
        f"strategy={expected['strategy']['strategyId']} lock={expected['integrity']['lockDigest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
