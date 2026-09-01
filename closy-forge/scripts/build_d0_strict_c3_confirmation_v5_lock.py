from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.recovery_foundation_v1.c3_v5 import run_generic_c3_fixtures
from closy_forge.strict_c3_confirmation_v5.evaluator import run_revealed_h4_diagnostic
from closy_forge.strict_c3_confirmation_v5.protocol import (
    EVIDENCE_ROOT,
    FIXTURE_ROOT,
    H4_LOCK_PATH,
    H4_RESULT_PATH,
    LOCK_PATH,
    SENTINEL_PATH,
    build_protocol_lock,
    build_sentinel_lock,
    validate_protocol_lock,
)


def build(root: Path) -> dict[str, object]:
    sentinel = build_sentinel_lock(root)
    lock = build_protocol_lock(root, sentinel)
    generic = run_generic_c3_fixtures()
    if generic.get("allPassed") is not True:
        raise ValueError("unit_n_generic_c3_fixtures_failed")
    with tempfile.TemporaryDirectory(prefix="closy-unit-n-h4-diagnostic-") as temporary:
        h4_diagnostic = run_revealed_h4_diagnostic(root, lock, Path(temporary))
    h4 = read_json(root / H4_RESULT_PATH)
    preservation = {
        "schemaVersion": 1,
        "v4ResultPath": H4_RESULT_PATH.as_posix(),
        "v4ResultSha256": sha256_file(root / H4_RESULT_PATH),
        "v4LockPath": H4_LOCK_PATH.as_posix(),
        "v4LockSha256": sha256_file(root / H4_LOCK_PATH),
        "v4HeldOutAttemptConsumed": h4["heldOutAttemptConsumed"],
        "v4CompletedPoseCount": h4["completedHeldOutStateCount"],
        "v4RequiredPoseCount": h4["heldOutStateCount"],
        "patchedReplayQualificationAllowed": False,
        "freshV5PoseRealized": False,
    }
    report = {
        "schemaVersion": 1,
        "unit": "N",
        "state": "locked_before_fresh_pose_realisation",
        "repository": "jake-the-jake/Closy",
        "branch": "codex/closy-forge-d0-strict-c3-confirmation-v5",
        "pullRequest": "pending",
        "base": {
            "branch": "codex/closy-forge-d0-disjoint-tshirt-confirmation-v2",
            "sha": "552867e96d53e9d4c728f90d12e0c1c9a344ba0d",
            "mergeBase": "552867e96d53e9d4c728f90d12e0c1c9a344ba0d",
        },
        "sourceEvidenceAnchor": {
            "unit": "F",
            "sha": "ba54ea539e576606f4ace5bc68c1282d84f20d72",
            "candidateId": sentinel["candidateId"],
            "candidatePackageDigest": sentinel["candidatePackageDigest"],
        },
        "parentEvidence": {
            "unit": "M",
            "sha": "552867e96d53e9d4c728f90d12e0c1c9a344ba0d",
            "forgeRunId": 33533707412,
            "forgeRequiredJobId": 99969210563,
            "forgeResult": "29/29 substantive jobs passed after failed-jobs rerun",
            "forgeRunAttempt": 2,
        },
        "sentinel": {
            "resolutionOutcome": sentinel["resolutionOutcome"],
            "candidateId": sentinel["candidateId"],
            "candidatePackageDigest": sentinel["candidatePackageDigest"],
            "sentinelLockDigest": sentinel["sentinelLockDigest"],
        },
        "protocolLockDigest": lock["integrity"]["protocolLockDigest"],
        "poseClassCount": len(lock["poseGenerator"]["classOrder"]),
        "freshPoseRealized": False,
        "genericEvaluatorFixtures": generic,
        "h4Preservation": preservation,
        "optionalProcessors": lock["optionalProcessors"],
        "optionalProcessorAuthority": {
            "path": "docs/evidence/d0_core_runtime_c3_v4/processor_authority_audit.json",
            "sha256": sha256_file(
                root / "docs/evidence/d0_core_runtime_c3_v4/processor_authority_audit.json"
            ),
            "resolution": "no_matching_authenticated_z1_or_mt1_executable",
        },
        "revealedH4Diagnostic": h4_diagnostic,
        "implementationIssues": validate_protocol_lock(root, lock),
    }
    return {
        "sentinel": sentinel,
        "lock": lock,
        "generic": generic,
        "h4_diagnostic": h4_diagnostic,
        "preservation": preservation,
        "report": report,
    }


def write(root: Path, documents: dict[str, object]) -> None:
    write_canonical_json(root / SENTINEL_PATH, documents["sentinel"])
    write_canonical_json(root / LOCK_PATH, documents["lock"])
    write_canonical_json(
        root / FIXTURE_ROOT / "generic_evaluator_fixtures.json", documents["generic"]
    )
    write_canonical_json(root / FIXTURE_ROOT / "h4_preservation.json", documents["preservation"])
    write_canonical_json(
        root / FIXTURE_ROOT / "revealed_h4_diagnostic.json", documents["h4_diagnostic"]
    )
    write_canonical_json(root / EVIDENCE_ROOT / "lock_report.json", documents["report"])


def check(root: Path, documents: dict[str, object]) -> None:
    expected = {
        SENTINEL_PATH: documents["sentinel"],
        LOCK_PATH: documents["lock"],
        FIXTURE_ROOT / "generic_evaluator_fixtures.json": documents["generic"],
        FIXTURE_ROOT / "h4_preservation.json": documents["preservation"],
        FIXTURE_ROOT / "revealed_h4_diagnostic.json": documents["h4_diagnostic"],
        EVIDENCE_ROOT / "lock_report.json": documents["report"],
    }
    for path, document in expected.items():
        if read_json(root / path) != document:
            raise ValueError(f"unit_n_lock_regeneration_drift:{path.as_posix()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify the Unit N pre-pose lock.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    documents = build(root)
    if args.check:
        check(root, documents)
    else:
        write(root, documents)
    print("unit_n_lock=ok fresh_pose_realized=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
