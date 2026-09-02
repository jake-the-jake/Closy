from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.disjoint_confirmation_v3.authority import (
    run_official_attempt,
    write_public_failure,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lock-sha", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--workflow-job-id", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    try:
        result = run_official_attempt(
            ROOT,
            output=args.output,
            lock_sha=args.lock_sha,
            workflow_run_id=args.workflow_run_id,
            workflow_job_id=args.workflow_job_id,
            image_reference=args.image,
        )
    except Exception as error:
        seed_created = (args.output / "environment_attestation.json").is_file()
        failure = write_public_failure(
            args.output,
            stage="authority_execution",
            failure_type=type(error).__name__,
            seed_created=seed_created,
            workflow_run_id=args.workflow_run_id,
            workflow_job_id=args.workflow_job_id,
        )
        print(
            json.dumps({"status": "sealed_failure", "outcome": failure["outcome"]}, sort_keys=True)
        )
        return 0 if seed_created else 1
    print(
        json.dumps(
            {
                "status": "completed",
                "outcome": result["outcome"],
                "resultHash": result["resultHash"],
                "successfulPredictionArtifactCount": result["successfulPredictionArtifactCount"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
