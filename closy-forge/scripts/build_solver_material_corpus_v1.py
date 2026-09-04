from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from closy_forge.solver_material_v1.common import write_json
from closy_forge.solver_material_v1.corpus import build_locked_corpus

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "fixtures" / "solver_material_v1" / "locked_corpus.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="closy-solver-corpus-") as temporary:
            candidate = Path(temporary) / "locked_corpus.json"
            write_json(candidate, build_locked_corpus())
            if not TARGET.exists() or candidate.read_bytes() != TARGET.read_bytes():
                raise SystemExit("solver_material_corpus_stale")
        return 0
    write_json(TARGET, build_locked_corpus())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
