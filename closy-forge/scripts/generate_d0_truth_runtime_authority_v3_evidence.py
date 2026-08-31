from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.truth_runtime import generate_truth_runtime_evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-anchor", required=True)
    args = parser.parse_args()
    written = generate_truth_runtime_evidence(
        args.root.resolve(), source_anchor_sha=args.source_anchor
    )
    for path in written.values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
