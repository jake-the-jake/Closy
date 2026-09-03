from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from closy_forge.capture_engineering_v1.common import sha256_bytes
from closy_forge.capture_engineering_v1.corpus import build_public_fixture_corpus
from closy_forge.capture_engineering_v1.evidence import (
    build_development_evidence,
    verify_generated_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "evidence" / "capture_camera_material_engineering_v1"


def build(output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    corpus = build_public_fixture_corpus(output / "corpus")
    with tempfile.TemporaryDirectory(prefix="closy-capture-packages-") as temporary:
        build_development_evidence(
            corpus,
            corpus_root=output / "corpus",
            output_root=output,
            package_scratch=Path(temporary),
        )
    issues = verify_generated_evidence(output)
    if issues:
        raise SystemExit("generated_capture_evidence_invalid:" + ";".join(issues))


def tree_digest(root: Path) -> str:
    rows = [
        f"{path.relative_to(root).as_posix()}:{sha256_bytes(path.read_bytes())}"
        for path in sorted(path for path in root.rglob("*") if path.is_file())
    ]
    return sha256_bytes("\n".join(rows).encode("utf-8"))


def check() -> None:
    if not OUTPUT.exists():
        raise SystemExit("capture_evidence_missing")
    with tempfile.TemporaryDirectory(prefix="closy-capture-evidence-check-") as temporary:
        candidate = Path(temporary) / "evidence"
        build(candidate)
        if tree_digest(candidate) != tree_digest(OUTPUT):
            raise SystemExit("capture_evidence_stale")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else build(OUTPUT)


if __name__ == "__main__":
    main()
