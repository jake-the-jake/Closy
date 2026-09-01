from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.disjoint_benchmark_v1.lifecycle import (
    SeedLifecycleState,
    inspect_seed_lifecycle,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "fixtures/d0_disjoint_tshirt_benchmark_v1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the immutable Unit G seed lifecycle")
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--expect",
        choices=[
            state.value for state in SeedLifecycleState if state != SeedLifecycleState.INVALID
        ],
    )
    args = parser.parse_args()
    report = inspect_seed_lifecycle(args.fixture_root.resolve())
    payload = {
        "state": report.state.value,
        "issueCount": len(report.issues),
        "issues": list(report.issues),
        "authorityRunId": report.authority_run_id,
        "authorityJobId": report.authority_job_id,
        "sealedVerificationOnly": report.sealed_verification_only,
        "seedDerivationPerformed": False,
        "evaluatorDispatchPerformed": False,
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    if report.state == SeedLifecycleState.INVALID:
        return 1
    if args.expect is not None and report.state.value != args.expect:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
