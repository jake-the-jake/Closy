from __future__ import annotations

import argparse
from pathlib import Path

from closy_forge.core_runtime_c3_v4.evaluator import evaluate_strict_c3
from closy_forge.core_runtime_c3_v4.reproducibility import evaluate_core_reproducibility
from closy_forge.core_runtime_c3_v4.sentinel import validate_sentinel
from closy_forge.package_io.canonical_json import read_json, write_canonical_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    sentinel = read_json(root / "fixtures/d0_core_runtime_c3_v4/sentinel_manifest.json")
    lock = read_json(root / "fixtures/d0_core_runtime_c3_v4/protocol_lock.json")
    validate_sentinel(root, sentinel)
    output = root / "docs/evidence/d0_core_runtime_c3_v4"
    write_canonical_json(
        output / "core_reproducibility.json", evaluate_core_reproducibility(root, sentinel)
    )
    write_canonical_json(output / "strict_c3_result.json", evaluate_strict_c3(root, sentinel, lock))


if __name__ == "__main__":
    main()
