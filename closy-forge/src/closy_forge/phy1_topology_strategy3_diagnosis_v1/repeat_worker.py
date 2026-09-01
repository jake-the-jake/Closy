from __future__ import annotations

import argparse
import sys

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.phy1_topology_strategy3_diagnosis_v1.fixtures import run_fixture_set


def main() -> int:
    parser = argparse.ArgumentParser(description="Recompute one Unit O development revision.")
    parser.add_argument("--revision", type=int, required=True)
    args = parser.parse_args()
    payload = canonical_dumps(run_fixture_set(args.revision))
    sys.stdout.write(canonical_dumps({"fixtureDigest": sha256_bytes(payload.encode("utf-8"))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
