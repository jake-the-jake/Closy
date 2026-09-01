from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.appearance_correction_v3.known_target import evaluate_known_target_once


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prediction-commit-sha", required=True)
    parser.add_argument("--evaluator-anchor-sha", required=True)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = evaluate_known_target_once(
        root,
        prediction_commit_sha=args.prediction_commit_sha,
        evaluator_anchor_sha=args.evaluator_anchor_sha,
        predictions=args.predictions,
        output=args.output,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
