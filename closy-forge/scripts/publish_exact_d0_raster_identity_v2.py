from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.capture.d0_raster_publication import publish_exact_d0_raster_fixture


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the immutable exact D0 raster fixture.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("fixtures/d0_exact_raster_v2"),
    )
    args = parser.parse_args()
    result = publish_exact_d0_raster_fixture(args.output.resolve())
    print(result["fixtureSetHash"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
