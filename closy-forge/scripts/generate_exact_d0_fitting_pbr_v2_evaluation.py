from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.fitting.exact_d0_evaluation import generate_exact_d0_evaluation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--prediction-commit-sha", required=True)
    parser.add_argument("--evaluator-implementation-sha", required=True)
    args = parser.parse_args()
    result = generate_exact_d0_evaluation(
        args.root,
        prediction_commit_sha=args.prediction_commit_sha,
        evaluator_implementation_sha=args.evaluator_implementation_sha,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
