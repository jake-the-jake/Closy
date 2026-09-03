from __future__ import annotations

from pathlib import Path

from closy_forge.d0_v4_engineering.negative_controls import run_negative_controls
from closy_forge.package_io.canonical_json import write_canonical_json


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = run_negative_controls(
        root,
        root / "models" / "d0_v4_engineering" / "trial-006.json",
    )
    write_canonical_json(
        root / "docs" / "evidence" / "d0_v4_engineering" / "negative_controls.json",
        result,
    )
    print(result["resultDigest"])
    print(result["allPass"])
    return 0 if result["allPass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
