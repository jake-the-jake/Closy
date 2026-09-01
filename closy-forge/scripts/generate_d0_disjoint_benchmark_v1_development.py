from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.disjoint_benchmark_v1.development import generate_development_lock

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-anchor-sha", required=True)
    args = parser.parse_args()
    generate_development_lock(ROOT, source_anchor_sha=args.source_anchor_sha)


if __name__ == "__main__":
    main()
