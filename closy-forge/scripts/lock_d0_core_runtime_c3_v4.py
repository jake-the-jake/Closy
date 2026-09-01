from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.core_runtime_c3_v4.protocol import LOCK_RELATIVE, build_protocol_lock
from closy_forge.core_runtime_c3_v4.sentinel import build_sentinel
from closy_forge.package_io.canonical_json import write_canonical_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    sentinel = build_sentinel(root)
    write_canonical_json(root / "fixtures/d0_core_runtime_c3_v4/sentinel_manifest.json", sentinel)
    write_canonical_json(root / LOCK_RELATIVE, build_protocol_lock(root, sentinel))


if __name__ == "__main__":
    main()
