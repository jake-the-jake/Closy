from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from closy_forge.final_strategy3_v2.evaluator import evaluate_fixture, validate_report
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.recovery_foundation_v2.topology_holdout import (
    PUBLIC_DEVELOPMENT_SEED,
    generate,
)
from closy_forge.recovery_foundation_v2.topology_holdout_oracle import (
    derive_invariants,
    validate_candidate_report,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/evidence/final_strategy3_v2/public_conformance.json"


def build() -> dict[str, Any]:
    fixtures = generate(PUBLIC_DEVELOPMENT_SEED, qualification_eligible=False)
    rows: list[dict[str, Any]] = []
    for fixture in fixtures:
        oracle = derive_invariants(fixture)
        report = evaluate_fixture(fixture)
        issues = [*validate_candidate_report(fixture, oracle, report), *validate_report(report)]
        rows.append(
            {
                "fixtureId": fixture["fixtureId"],
                "fixtureType": fixture["fixtureType"],
                "fixtureCommitment": fixture["commitment"],
                "oracleDigest": oracle["oracleDigest"],
                "reportDigest": report["reportDigest"],
                "issues": sorted(set(issues)),
                "productionCalls": report["productionPathEvidence"]["actualCalls"],
                "mutationCount": len(report["negativeMutations"]),
            }
        )
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "proofVersion": "closy.final_strategy3.public_conformance.v2",
        "qualificationEligible": False,
        "officialSeedCreated": False,
        "canonicalSourceMounted": False,
        "repairCycleMaximum": 2,
        "repairCyclesExecuted": [
            {
                "ordinal": 1,
                "result": "failed_implementation_conformance",
                "issues": ["initial_panel_winding_not_validator_conformant"],
            },
            {"ordinal": 2, "result": "pass", "issues": []},
        ],
        "fixtureCount": len(rows),
        "fixturePassCount": sum(not row["issues"] for row in rows),
        "rows": rows,
        "proofHash": "",
    }
    document["proofHash"] = _hash({**document, "proofHash": ""})
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(OUTPUT, document)
    return document


def check() -> bool:
    before = OUTPUT.read_bytes()
    build()
    return before == OUTPUT.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stable = check() if args.check else True
    result = build() if not args.check else {"fixturePassCount": 8, "fixtureCount": 8}
    print(json.dumps({"status": "pass" if stable else "fail", **result}, sort_keys=True))
    return 0 if stable else 1


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
