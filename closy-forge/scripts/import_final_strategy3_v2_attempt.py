from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.final_strategy3_v2.protocol import OFFICIAL_PATH, OUTCOMES, load_protocol
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

ROOT = Path(__file__).resolve().parents[1]


def validate(source: Path) -> list[str]:
    issues: list[str] = []
    protocol = load_protocol(ROOT)
    failure_path = source / "public_failure.json"
    if failure_path.is_file():
        failure = _mapping(read_json(failure_path))
        if failure.get("outcome") not in OUTCOMES[2:]:
            issues.append("final_strategy3_failure_outcome_invalid")
        if (
            failure.get("officialSeedCreated") is True
            and failure.get("qualificationRetryAllowed") is not False
        ):
            issues.append("final_strategy3_failure_retry_invalid")
        if failure.get("privateArtifactsRemoved") is not True:
            issues.append("final_strategy3_failure_private_cleanup_invalid")
        if any(
            failure.get(field) is True
            for field in ("rawSeedIncluded", "nonceIncluded", "oracleIncluded")
        ):
            issues.append("final_strategy3_failure_private_data_leaked")
        return sorted(set(issues))
    manifest = _mapping(read_json(source / "attempt_manifest.json"))
    result = _mapping(read_json(source / "confirmation_result.json"))
    commitments = _mapping(read_json(source / "authority_commitments.json"))
    freeze = _mapping(read_json(source / "output_freeze.json"))
    reveal = _mapping(read_json(source / "fixture_oracle_reveal.json"))
    isolation = _mapping(read_json(source / "isolation_report.json"))
    if result.get("outcome") not in OUTCOMES[:3]:
        issues.append("final_strategy3_result_outcome_invalid")
    if result.get("fixtureDenominator") != 8 or result.get("fixturePassCount") not in range(9):
        issues.append("final_strategy3_result_denominator_invalid")
    if (
        result.get("candidateCreated") is not False
        or result.get("candidateAttemptConsumed") is not False
    ):
        issues.append("final_strategy3_candidate_budget_corrupted")
    if manifest.get("protocolLockHash") != protocol.get("lockHash"):
        issues.append("final_strategy3_manifest_protocol_mismatch")
    if manifest.get("implementationDigest") != protocol.get("implementationDigest"):
        issues.append("final_strategy3_manifest_implementation_mismatch")
    if manifest.get("literalOutcome") != result.get("outcome"):
        issues.append("final_strategy3_manifest_outcome_mismatch")
    if manifest.get("qualificationRetryAllowed") is not False:
        issues.append("final_strategy3_manifest_retry_invalid")
    if [
        commitments.get("eventOrdinal"),
        freeze.get("eventOrdinal"),
        reveal.get("eventOrdinal"),
    ] != [1, 2, 3]:
        issues.append("final_strategy3_lifecycle_order_invalid")
    if reveal.get("outputFreezeHash") != freeze.get("outputFreezeHash"):
        issues.append("final_strategy3_freeze_reveal_join_invalid")
    if isolation.get("executionCount") != 8 or isolation.get("privateOracleMounted") is not False:
        issues.append("final_strategy3_isolation_invalid")
    if _hash({**freeze, "outputFreezeHash": ""}) != freeze.get("outputFreezeHash"):
        issues.append("final_strategy3_output_freeze_hash_invalid")
    if _hash({**reveal, "revealHash": ""}) != reveal.get("revealHash"):
        issues.append("final_strategy3_reveal_hash_invalid")
    if _hash({**result, "resultHash": ""}) != result.get("resultHash"):
        issues.append("final_strategy3_result_hash_invalid")
    if _hash({**manifest, "manifestHash": ""}) != manifest.get("manifestHash"):
        issues.append("final_strategy3_manifest_hash_invalid")
    files = manifest.get("files")
    if not isinstance(files, list):
        issues.append("final_strategy3_manifest_files_missing")
    else:
        for item in files:
            row = _mapping(item)
            path = source / str(row.get("path", ""))
            if not path.is_file() or sha256_file(path) != row.get("sha256"):
                issues.append(f"final_strategy3_manifest_file_invalid:{row.get('path')}")
    if any(path.name.startswith(".authority_private") for path in source.iterdir()):
        issues.append("final_strategy3_private_store_present")
    return sorted(set(issues))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    issues = validate(args.source)
    if issues:
        print(json.dumps({"status": "fail", "issues": issues}, sort_keys=True))
        return 1
    if not args.check:
        target = ROOT / OFFICIAL_PATH
        if target.exists():
            raise ValueError("final_strategy3_official_attempt_already_imported")
        shutil.copytree(args.source, target)
    print(json.dumps({"status": "pass", "issues": []}, sort_keys=True))
    return 0


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("final_strategy3_mapping_required")
    return dict(value)


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
