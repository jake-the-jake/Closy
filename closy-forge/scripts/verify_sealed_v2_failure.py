from __future__ import annotations

import json
from pathlib import Path

from closy_forge.truth_authority_integrity_v3.sealed_v2_witness import (
    verify_sealed_v2_failure,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    witness = verify_sealed_v2_failure(REPO_ROOT)
    print(json.dumps(witness, sort_keys=True))
    return 0 if witness["pass"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
