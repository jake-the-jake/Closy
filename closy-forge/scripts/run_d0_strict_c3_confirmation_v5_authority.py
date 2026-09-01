from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.strict_c3_confirmation_v5.authority import run_official_attempt


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the one-shot Unit N external pose authority.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = run_official_attempt(root, args.output.resolve())
    print(f"outcome={result['outcome']} poses={result['posePassCount']}/{result['poseCount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
