from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.phy1_topology_strategy2_v4.diagnosis import (
    build_general_microfixtures,
    build_pr43_diagnosis,
)

EVIDENCE = Path("docs/evidence/phy1_topology_strategy2_v4")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--validate-committed", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    expected = {
        "diagnosis.json": build_pr43_diagnosis(root),
        "general_microfixtures.json": build_general_microfixtures(),
    }
    for name, document in expected.items():
        path = root / EVIDENCE / name
        if args.validate_committed:
            if read_json(path) != document:
                raise ValueError(f"unit_i_diagnosis_not_fresh:{name}")
        else:
            write_canonical_json(path, document)
    print(f"diagnosis={expected['diagnosis.json']['integrity']['diagnosisDigest']} general=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
