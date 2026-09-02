from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from closy_forge.final_strategy3_v2.protocol import (
    LOCK_PATH,
    WORKFLOW_PATH,
    build_protocol,
    validate_implementation,
    validate_protocol,
)
from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_file

ROOT = Path(__file__).resolve().parents[1]


def build(*, preflight_run_id: str, preflight_image_id: str) -> dict[str, Any]:
    implementation = _implementation_inventory()
    protocol = build_protocol(
        ROOT,
        implementation_files=implementation,
        preflight_run_id=preflight_run_id,
        preflight_image_id=preflight_image_id,
    )
    issues = validate_protocol(ROOT, protocol)
    if issues:
        raise ValueError(";".join(issues))
    target = ROOT / LOCK_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(target, protocol)
    implementation_issues = validate_implementation(ROOT, protocol)
    if implementation_issues:
        raise ValueError(";".join(implementation_issues))
    return protocol


def check() -> list[str]:
    path = ROOT / LOCK_PATH
    protocol = json.loads(path.read_text(encoding="utf-8"))
    issues = validate_protocol(ROOT, protocol)
    issues.extend(validate_implementation(ROOT, protocol))
    return sorted(set(issues))


def _implementation_inventory() -> list[dict[str, Any]]:
    paths = [
        *sorted((ROOT / "src/closy_forge/final_strategy3_v2").glob("*.py")),
        *sorted((ROOT / "src/closy_forge/recovery_foundation_v2").glob("topology_holdout*.py")),
        ROOT / "src/closy_forge/simulation/reference_cloth_solver.py",
        ROOT / "src/closy_forge/simulation/self_collision.py",
        ROOT / "tests/unit/test_final_strategy3_v2.py",
        ROOT / "tests/unit/test_final_strategy3_v2_protocol.py",
        ROOT / "scripts/build_final_strategy3_v2_public_proof.py",
        ROOT / "scripts/run_final_strategy3_v2_preflight.py",
        ROOT / "scripts/build_final_strategy3_v2_lock.py",
        ROOT / "scripts/run_final_strategy3_v2_authority.py",
        ROOT / "scripts/import_final_strategy3_v2_attempt.py",
        ROOT / "docker/final_strategy3_v2/Dockerfile",
        ROOT / "docker/final_strategy3_v2/entrypoint.sh",
        ROOT / "docker/final_strategy3_v2/runner.py",
        ROOT / WORKFLOW_PATH,
    ]
    unique = sorted({path.resolve() for path in paths}, key=lambda path: path.as_posix())
    missing = [path for path in unique if not path.is_file()]
    if missing:
        raise ValueError(f"final_strategy3_inventory_missing:{missing}")
    return [
        {"path": _relative(path), "sha256": sha256_file(path), "byteLength": path.stat().st_size}
        for path in unique
    ]


def _relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return "../" + path.relative_to(ROOT.parent).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-run-id")
    parser.add_argument("--preflight-image-id")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        issues = check()
        print(json.dumps({"status": "pass" if not issues else "fail", "issues": issues}))
        return 0 if not issues else 1
    if not args.preflight_run_id or not args.preflight_image_id:
        raise ValueError("final_strategy3_preflight_identity_required")
    protocol = build(
        preflight_run_id=args.preflight_run_id,
        preflight_image_id=args.preflight_image_id,
    )
    print(json.dumps({"status": "pass", "lockHash": protocol["lockHash"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
