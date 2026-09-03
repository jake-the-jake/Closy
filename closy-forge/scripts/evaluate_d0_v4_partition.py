from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.d0_v4_engineering.evaluation import evaluate_partition
from closy_forge.d0_v4_engineering.model import load_model
from closy_forge.d0_v4_engineering.protocol import (
    claim_public_test_execution,
    complete_public_test_execution,
)
from closy_forge.package_io.canonical_json import write_canonical_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--partition", choices=("validation", "public_test"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--authorize-public-test", action="store_true")
    parser.add_argument("--source-head")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    model_path = root / arguments.model
    claimed = False
    if arguments.partition == "public_test":
        if not arguments.authorize_public_test or not arguments.source_head:
            parser.error("public_test requires --authorize-public-test and --source-head")
        model_sha256 = load_model(model_path)["integrity"]["modelSha256"]
        claim_public_test_execution(
            root,
            source_head=arguments.source_head,
            model_sha256=str(model_sha256),
        )
        claimed = True
    try:
        result = evaluate_partition(
            root,
            partition=arguments.partition,
            model_path=model_path,
            allow_public_test=arguments.authorize_public_test,
            workers=arguments.workers,
        )
        write_canonical_json(root / arguments.output, result)
    except Exception as exc:
        if claimed:
            complete_public_test_execution(
                root,
                result_digest=None,
                readiness_pass=False,
                failed_reason=f"{type(exc).__name__}:{exc}",
            )
        raise
    if claimed:
        complete_public_test_execution(
            root,
            result_digest=str(result["resultDigest"]),
            readiness_pass=bool(result["readinessPass"]),
        )
    print(result["resultDigest"])
    print(result["readinessPass"])
    print(result["summary"])
    return 0 if result["readinessPass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
