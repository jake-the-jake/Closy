from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.disjoint_confirmation_v3.evaluator import validate_result
from closy_forge.disjoint_confirmation_v3.protocol import FIXTURE_ROOT, OUTCOMES, load_protocol
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

ROOT = Path(__file__).resolve().parents[1]


def validate(source: Path) -> list[str]:
    issues: list[str] = []
    protocol = load_protocol(ROOT)
    failure_path = source / "public_failure.json"
    if failure_path.is_file():
        failure = _mapping(read_json(failure_path))
        if failure.get("outcome") not in OUTCOMES[-2:]:
            issues.append("d0_v3_failure_outcome_invalid")
        if (
            failure.get("qualificationRetryAllowed") is not False
            and failure.get("officialSeedCreated") is True
        ):
            issues.append("d0_v3_failure_retry_invalid")
        if failure.get("privateArtifactsRemoved") is not True:
            issues.append("d0_v3_failure_private_cleanup_invalid")
        return issues
    manifest = _mapping(read_json(source / "attempt_manifest.json"))
    result = _mapping(read_json(source / "benchmark_result.json"))
    freeze = _mapping(read_json(source / "prediction_freeze.json"))
    reveal = _mapping(read_json(source / "target_reveal.json"))
    commitments = _mapping(read_json(source / "authority_commitments.json"))
    isolation = _mapping(read_json(source / "isolation_report.json"))
    issues.extend(validate_result(result))
    if manifest.get("protocolLockHash") != protocol.get("lockHash"):
        issues.append("d0_v3_import_protocol_lock_mismatch")
    if manifest.get("implementationDigest") != protocol.get("implementationDigest"):
        issues.append("d0_v3_import_implementation_digest_mismatch")
    if manifest.get("literalResult") != result.get("outcome"):
        issues.append("d0_v3_import_result_mismatch")
    if manifest.get("qualificationRetryAllowed") is not False:
        issues.append("d0_v3_import_retry_allowed")
    if freeze.get("attemptRowCount") != 64 or freeze.get("primaryRepeatCount") != 16:
        issues.append("d0_v3_import_prediction_denominator_invalid")
    if (
        commitments.get("eventOrdinal") != 1
        or freeze.get("eventOrdinal") != 2
        or reveal.get("eventOrdinal") != 3
    ):
        issues.append("d0_v3_import_event_order_invalid")
    if reveal.get("predictionFreezeHash") != freeze.get("freezeHash"):
        issues.append("d0_v3_import_freeze_reveal_join_invalid")
    if isolation.get("executionCount") != 80:
        issues.append("d0_v3_import_isolation_denominator_invalid")
    if _hash({**freeze, "freezeHash": ""}) != freeze.get("freezeHash"):
        issues.append("d0_v3_import_freeze_hash_invalid")
    if _hash({**reveal, "revealHash": ""}) != reveal.get("revealHash"):
        issues.append("d0_v3_import_reveal_hash_invalid")
    files = manifest.get("files")
    if not isinstance(files, list):
        issues.append("d0_v3_import_manifest_files_missing")
    else:
        for item in files:
            row = _mapping(item)
            path = source / str(row.get("path", ""))
            if not path.is_file() or sha256_file(path) != row.get("sha256"):
                issues.append(f"d0_v3_import_file_hash_invalid:{row.get('path')}")
    if _hash({**manifest, "manifestHash": ""}) != manifest.get("manifestHash"):
        issues.append("d0_v3_import_manifest_hash_invalid")
    if any(path.name.startswith(".authority_private") for path in source.iterdir()):
        issues.append("d0_v3_import_private_store_present")
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
        target = ROOT / FIXTURE_ROOT / "official_attempt"
        if target.exists():
            raise ValueError("d0_v3_official_attempt_already_imported")
        shutil.copytree(args.source, target)
    print(json.dumps({"status": "pass", "issues": []}, sort_keys=True))
    return 0


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("d0_v3_mapping_required")
    return dict(value)


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
