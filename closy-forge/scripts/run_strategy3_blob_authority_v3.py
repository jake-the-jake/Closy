from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.strategy3_blob_authority_v3.authority import (
    evaluate_authority,
    execute_contestant,
    prepare_authority,
    write_public_failure,
)
from closy_forge.strategy3_blob_authority_v3.protocol import load_lock

REPO_ROOT = Path(__file__).resolve().parents[2]
FORGE_ROOT = REPO_ROOT / "closy-forge"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "contest", "evaluate"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--contestant-output", type=Path)
    parser.add_argument("--lock-commit", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--workflow-job-id", required=True)
    parser.add_argument("--preflight-run-id", default="")
    parser.add_argument("--image", default="")
    parser.add_argument("--image-id", default="")
    args = parser.parse_args()
    lock = load_lock(FORGE_ROOT)
    try:
        if args.phase == "prepare":
            result = prepare_authority(
                REPO_ROOT,
                lock,
                output=args.output,
                lock_commit=args.lock_commit,
                workflow_run_id=args.workflow_run_id,
                workflow_job_id=args.workflow_job_id,
                preflight_run_id=args.preflight_run_id,
                image_id=args.image_id,
            )
        elif args.phase == "contest":
            if args.prepared is None or not args.image:
                raise ValueError("strategy3_v3_contest_inputs_required")
            result = execute_contestant(
                lock,
                prepared=args.prepared,
                output=args.output,
                image_reference=args.image,
            )
        else:
            if args.prepared is None or args.contestant_output is None:
                raise ValueError("strategy3_v3_evaluation_inputs_required")
            result = evaluate_authority(
                REPO_ROOT,
                lock,
                prepared=args.prepared,
                contestant_output=args.contestant_output,
                output=args.output,
                lock_commit=args.lock_commit,
                workflow_run_id=args.workflow_run_id,
                workflow_job_id=args.workflow_job_id,
            )
    except Exception as error:
        seed_created = bool(
            args.prepared and (args.prepared / "environment_attestation.json").is_file()
        )
        if args.phase == "prepare":
            seed_created = (args.output / "environment_attestation.json").is_file()
        public = args.output.parent / f"{args.output.name}-public-failure"
        failure = write_public_failure(
            public,
            seed_created=seed_created,
            stage=args.phase,
            error=error,
            workflow_run_id=args.workflow_run_id,
        )
        print(json.dumps({"status": "sealed_failure", **failure}, sort_keys=True))
        return 0 if seed_created else 1
    print(json.dumps({"status": "pass", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
