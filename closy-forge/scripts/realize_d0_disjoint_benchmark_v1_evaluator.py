from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.disjoint_benchmark_v1.evaluator import realize_evaluator_commitments

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock-sha", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--job-id", required=True, type=int)
    args = parser.parse_args()
    realize_evaluator_commitments(
        ROOT, lock_sha=args.lock_sha, run_id=args.run_id, job_id=args.job_id
    )


if __name__ == "__main__":
    main()
