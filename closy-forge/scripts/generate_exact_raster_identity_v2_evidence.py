from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.capture.exact_raster_evidence import generate_exact_raster_identity_evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-lock-sha", required=True)
    args = parser.parse_args()
    written = generate_exact_raster_identity_evidence(
        package_root=args.root.resolve(), source_lock_sha=args.source_lock_sha
    )
    for path in written.values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
