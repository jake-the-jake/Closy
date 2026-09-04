from __future__ import annotations

from pathlib import Path

from closy_forge.manual_provider_c3_v1.publication import publish_manual_provider_c3_v1

REPOSITORY = Path(__file__).resolve().parents[2]
PUBLICATION = REPOSITORY / "closy-forge" / "docs" / "evidence" / "manual_provider_c3_v1"


if __name__ == "__main__":
    manifest = publish_manual_provider_c3_v1(REPOSITORY, PUBLICATION)
    print(f"publicationDigest={manifest['publicationDigest']}")
    print(f"resultDigest={manifest['resultDigest']}")
    print(f"checkerDigest={manifest['checkerDigest']}")
