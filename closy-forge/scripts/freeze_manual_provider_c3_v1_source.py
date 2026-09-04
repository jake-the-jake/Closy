from __future__ import annotations

from pathlib import Path

from closy_forge.manual_provider_c3_v1.source_freeze import create_source_freeze

REPOSITORY = Path(__file__).resolve().parents[2]
OUTPUT = REPOSITORY / "closy-forge" / "fixtures" / "manual_provider_c3_v1" / "source_freeze.json"


if __name__ == "__main__":
    freeze = create_source_freeze(REPOSITORY, OUTPUT)
    print(f"sourceCommit={freeze['sourceCommit']}")
    print(f"sourceTree={freeze['sourceTree']}")
    print(f"sourceFreezeDigest={freeze['sourceFreezeDigest']}")
