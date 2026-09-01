from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.phy1_topology_strategy2_v4.budget import (
    build_budget_classifier,
    validate_budget_classifier,
)

RELATIVE_PATH = Path("fixtures/phy1_topology_strategy2_v4/budget_classifier.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--validate-committed", action="store_true")
    args = parser.parse_args()
    path = args.root.resolve() / RELATIVE_PATH
    expected = build_budget_classifier()
    if args.validate_committed:
        actual = read_json(path)
        if actual != expected or validate_budget_classifier(dict(actual)):
            raise ValueError("unit_i_budget_classifier_not_fresh")
    else:
        write_canonical_json(path, expected)
    print(f"classifier={expected['integrity']['classifierDigest']} status=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
