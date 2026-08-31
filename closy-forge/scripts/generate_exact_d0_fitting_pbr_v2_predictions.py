from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.fitting.exact_d0_predictions import generate_exact_d0_predictions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock-commit-sha", required=True)
    parser.add_argument("--implementation-commit-sha", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = generate_exact_d0_predictions(
        root,
        output=args.output,
        lock_commit_sha=args.lock_commit_sha,
        implementation_commit_sha=args.implementation_commit_sha,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
