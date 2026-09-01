from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.disjoint_confirmation_v2.authority import run_official_attempt

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lock-sha", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--workflow-job-id", required=True)
    parser.add_argument("--allow-process-only", action="store_true")
    args = parser.parse_args()
    result = run_official_attempt(
        ROOT,
        output=args.output,
        lock_sha=args.lock_sha,
        workflow_run_id=args.workflow_run_id,
        workflow_job_id=args.workflow_job_id,
        require_container=not args.allow_process_only,
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "outcome": result["outcome"],
                "resultHash": result["resultHash"],
                "predictionCount": result["predictionCount"],
                "fullCompileCount": result["fullCompileCount"],
                "appearanceEvaluationCount": result["appearanceEvaluationCount"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
