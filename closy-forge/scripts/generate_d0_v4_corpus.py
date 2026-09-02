from __future__ import annotations

from pathlib import Path

from closy_forge.d0_v4_engineering.corpus import ARCHIVE_PATH, MANIFEST_PATH, generate_corpus
from closy_forge.package_io.canonical_json import write_canonical_json


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    manifest, archive = generate_corpus(root)
    (root / ARCHIVE_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / ARCHIVE_PATH).write_bytes(archive)
    write_canonical_json(root / MANIFEST_PATH, manifest)
    print(manifest["manifestDigest"])
    print(manifest["separation"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
