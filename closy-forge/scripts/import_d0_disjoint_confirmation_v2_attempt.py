from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.disjoint_confirmation_v2.protocol import FIXTURE_ROOT, load_protocol
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

ROOT = Path(__file__).resolve().parents[1]


def validate(source: Path) -> list[str]:
    issues: list[str] = []
    protocol = load_protocol(ROOT)
    manifest = _mapping(read_json(source / "attempt_manifest.json"))
    result = _mapping(read_json(source / "benchmark_result.json"))
    freeze = _mapping(read_json(source / "prediction_freeze.json"))
    reveal = _mapping(read_json(source / "target_reveal.json"))
    commitments = _mapping(read_json(source / "authority_commitments.json"))
    isolation = _mapping(read_json(source / "isolation_report.json"))
    if manifest.get("protocolLockHash") != protocol.get("lockHash"):
        issues.append("attempt_protocol_lock_mismatch")
    if manifest.get("implementationDigest") != protocol.get("implementationDigest"):
        issues.append("attempt_implementation_digest_mismatch")
    if manifest.get("literalResult") != result.get("outcome"):
        issues.append("attempt_result_mismatch")
    if freeze.get("predictionCount") != 64 or result.get("predictionCount") != 64:
        issues.append("attempt_prediction_denominator_invalid")
    for field, expected in (
        ("fullCompileCount", 48),
        ("primaryCompileRepeatCount", 16),
        ("appearanceEvaluationCount", 24),
        ("primaryAppearanceRepeatCount", 8),
    ):
        if result.get(field) != expected:
            issues.append(f"attempt_denominator_invalid:{field}")
    if commitments.get("eventOrdinal") != 1 or freeze.get("eventOrdinal") != 2:
        issues.append("attempt_event_order_invalid")
    if reveal.get("eventOrdinal") != 3:
        issues.append("attempt_reveal_order_invalid")
    if reveal.get("predictionFreezeHash") != freeze.get("freezeHash"):
        issues.append("attempt_reveal_freeze_join_mismatch")
    if isolation.get("qualifiesD0Rp04") is not True:
        issues.append("attempt_container_isolation_not_enforced")
    if _hash({**freeze, "freezeHash": ""}) != freeze.get("freezeHash"):
        issues.append("attempt_freeze_hash_invalid")
    if _hash({**reveal, "revealHash": ""}) != reveal.get("revealHash"):
        issues.append("attempt_reveal_hash_invalid")
    files = manifest.get("files")
    if not isinstance(files, list):
        issues.append("attempt_manifest_files_missing")
    else:
        for item in files:
            record = _mapping(item)
            path = source / str(record.get("path", ""))
            if not path.is_file() or sha256_file(path) != record.get("sha256"):
                issues.append(f"attempt_file_hash_invalid:{record.get('path')}")
    expected_manifest = _hash({**manifest, "manifestHash": ""})
    if manifest.get("manifestHash") != expected_manifest:
        issues.append("attempt_manifest_hash_invalid")
    return issues


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
            raise ValueError("official_attempt_already_imported")
        shutil.copytree(args.source, target)
    print(json.dumps({"status": "pass", "issues": []}, sort_keys=True))
    return 0


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("confirmation_v2_mapping_required")
    return dict(value)


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
