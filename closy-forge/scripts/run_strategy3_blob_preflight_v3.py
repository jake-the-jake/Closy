from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.strategy3_blob_authority_v3.common import write_json
from closy_forge.strategy3_blob_authority_v3.preflight import run_preflight
from closy_forge.strategy3_blob_authority_v3.protocol import load_lock

REPO_ROOT = Path(__file__).resolve().parents[2]
FORGE_ROOT = REPO_ROOT / "closy-forge"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lock-commit", required=True)
    parser.add_argument(
        "--checkout-mode", choices=("normal", "autocrlf_true", "autocrlf_false"), required=True
    )
    parser.add_argument("--build-container", action="store_true")
    parser.add_argument("--image", default="closy-strategy3-v3:locked")
    args = parser.parse_args()
    report = run_preflight(
        REPO_ROOT,
        load_lock(FORGE_ROOT),
        lock_commit=args.lock_commit,
        checkout_mode=args.checkout_mode,
        build_container=args.build_container,
        image_tag=args.image,
    )
    write_json(args.output, report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
