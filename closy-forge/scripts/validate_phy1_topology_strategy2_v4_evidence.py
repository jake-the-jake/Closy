from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.phy1_topology_strategy2_v4.evidence import (
    validate_committed_unit_i_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    issues = validate_committed_unit_i_evidence(args.root.resolve())
    if issues:
        raise ValueError("unit_i_evidence_invalid:" + ",".join(issues))
    print("outcome=M logicalJ=J-A candidate=false validation=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
