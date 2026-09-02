from __future__ import annotations

import argparse
import json
from pathlib import Path

from closy_forge.strategy3_blob_authority_v3.common import write_json
from closy_forge.strategy3_blob_authority_v3.materializer import (
    build_container_image,
    materialized_context,
)
from closy_forge.strategy3_blob_authority_v3.protocol import load_lock

REPO_ROOT = Path(__file__).resolve().parents[2]
FORGE_ROOT = REPO_ROOT / "closy-forge"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--build-image")
    args = parser.parse_args()
    lock = load_lock(FORGE_ROOT)
    if args.build_image:
        report = build_container_image(REPO_ROOT, lock, image_tag=args.build_image)
    else:
        with materialized_context(REPO_ROOT, lock) as (_, manifest):
            report = manifest
    write_json(args.manifest, report)
    print(json.dumps({"status": "pass", **report}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
