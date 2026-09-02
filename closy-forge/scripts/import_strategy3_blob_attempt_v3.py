from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.strategy3_blob_authority_v3.publication import import_attempt

FORGE_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--authority-run-id", required=True)
    args = parser.parse_args()
    outcome = import_attempt(
        FORGE_ROOT,
        args.source,
        authority_run_id=args.authority_run_id,
    )
    print(json.dumps({"status": "pass", **outcome}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
