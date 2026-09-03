from __future__ import annotations

from pathlib import Path

from closy_forge.d0_v4_engineering.corpus import (
    ARCHIVE_PATH,
    MANIFEST_PATH,
    PUBLIC_TEST_ARCHIVE_PATH,
    PUBLIC_TEST_MANIFEST_PATH,
    generate_corpus,
)
from closy_forge.package_io.canonical_json import write_canonical_json


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    manifest, archive, public_manifest, public_archive = generate_corpus(root)
    (root / ARCHIVE_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / ARCHIVE_PATH).write_bytes(archive)
    write_canonical_json(root / MANIFEST_PATH, manifest)
    (root / PUBLIC_TEST_ARCHIVE_PATH).write_bytes(public_archive)
    write_canonical_json(root / PUBLIC_TEST_MANIFEST_PATH, public_manifest)
    print(manifest["manifestDigest"])
    print(public_manifest["manifestDigest"])
    print(manifest["separation"])
    print(
        {
            role: max(
                record["generatorAttempt"]
                for record in [*manifest["records"], *public_manifest["records"]]
                if record["partition"] == role
            )
            for role in manifest["allPartitionCounts"]
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
