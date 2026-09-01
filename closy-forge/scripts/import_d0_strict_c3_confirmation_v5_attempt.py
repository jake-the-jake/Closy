from __future__ import annotations

import argparse
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.strict_c3_confirmation_v5.oracle import validate_oracle_target
from closy_forge.strict_c3_confirmation_v5.protocol import (
    EVIDENCE_ROOT,
    FIXTURE_ROOT,
    document_digest,
    realize_pose_suite,
)


def import_attempt(root: Path, source: Path, authority_job_id: int) -> dict[str, Any]:
    commitments = _mapping(read_json(source / "authority_commitments.json"))
    pose_suite = _mapping(read_json(source / "pose_suite.json"))
    result = _mapping(read_json(source / "strict_c3_result.json"))
    reveal = _mapping(read_json(source / "authority_reveal.json"))
    seed = bytes.fromhex(str(reveal["seedHex"]))
    expected_seed_commitment = sha256_bytes(b"CLOSY_UNIT_N_POSE_SEED_V5\x00" + seed)
    if expected_seed_commitment != commitments.get("seedCommitmentSha256"):
        raise ValueError("unit_n_import_seed_commitment_mismatch")
    if realize_pose_suite(seed) != pose_suite.get("poses"):
        raise ValueError("unit_n_import_pose_suite_not_reproducible")
    if pose_suite.get("poseSuiteDigest") != document_digest(pose_suite, "poseSuiteDigest"):
        raise ValueError("unit_n_import_pose_suite_digest_invalid")
    if commitments.get("commitmentDigest") != document_digest(commitments, "commitmentDigest"):
        raise ValueError("unit_n_import_commitment_digest_invalid")
    if _mapping(result.get("integrity")).get("resultDigest") != document_digest(
        result, "resultDigest"
    ):
        raise ValueError("unit_n_import_result_digest_invalid")
    targets = source / "private_targets"
    committed_targets = {
        str(row["poseId"]): row
        for row in commitments.get("targetCommitments", [])
        if isinstance(row, Mapping)
    }
    for pose in pose_suite["poses"]:
        pose_id = str(pose["poseId"])
        path = targets / f"{pose_id}.json"
        if sha256_file(path) != committed_targets[pose_id].get("sha256"):
            raise ValueError(f"unit_n_import_target_hash_mismatch:{pose_id}")
        target = _mapping(read_json(path))
        issues = validate_oracle_target(target)
        if issues or target.get("pose") != pose:
            raise ValueError(f"unit_n_import_target_invalid:{pose_id}:{','.join(issues)}")
    if result.get("attempt", {}).get("consumed") is not True:
        raise ValueError("unit_n_import_attempt_not_consumed")

    destination = root / EVIDENCE_ROOT
    target_destination = destination / "revealed_oracle_targets"
    target_destination.mkdir(parents=True, exist_ok=True)
    for name in (
        "authority_commitments.json",
        "pose_suite.json",
        "authority_reveal.json",
        "strict_c3_result.json",
    ):
        shutil.copy2(source / name, destination / name)
    for path in sorted(targets.glob("*.json")):
        shutil.copy2(path, target_destination / path.name)
    lifecycle = {
        "schemaVersion": 1,
        "state": "sealed_after_first_external_pose_commitment",
        "authorityRunId": commitments["authorityRunId"],
        "authorityRunAttempt": commitments["authorityRunAttempt"],
        "authorityJob": commitments["authorityJob"],
        "authorityJobId": authority_job_id,
        "authorityHeadSha": commitments["authorityHeadSha"],
        "commitmentDigest": commitments["commitmentDigest"],
        "resultDigest": _mapping(result["integrity"])["resultDigest"],
        "outcome": result["outcome"],
        "poseCount": result["poseCount"],
        "posePassCount": result["posePassCount"],
        "attemptConsumed": True,
        "qualificationRetryAllowed": False,
        "authorityDispatchEnabledAfterSeal": False,
    }
    write_canonical_json(root / FIXTURE_ROOT / "authority_lifecycle.json", lifecycle)
    outcome_report = {
        "schemaVersion": 1,
        "unit": "N",
        "repository": "jake-the-jake/Closy",
        "branch": "codex/closy-forge-d0-strict-c3-confirmation-v5",
        "pullRequest": 51,
        "baseBranch": "codex/closy-forge-d0-disjoint-tshirt-confirmation-v2",
        "baseSha": "552867e96d53e9d4c728f90d12e0c1c9a344ba0d",
        "mergeBase": "552867e96d53e9d4c728f90d12e0c1c9a344ba0d",
        "sourceEvidenceAnchorSha": "ba54ea539e576606f4ace5bc68c1282d84f20d72",
        "publicationHeadSha": "pending_external_attestation",
        "changedFileDelta": "pending_final_commit",
        "authority": {
            "platform": "ubuntu-latest",
            "python": "3.11",
            "runId": commitments["authorityRunId"],
            "runAttempt": commitments["authorityRunAttempt"],
            "jobId": authority_job_id,
            "headSha": commitments["authorityHeadSha"],
        },
        "identities": {
            "candidateId": result["candidateId"],
            "candidatePackageDigest": result["candidatePackageDigest"],
            "sentinelLockDigest": result["sentinelLockDigest"],
            "protocolLockDigest": result["protocolLockDigest"],
            "commitmentDigest": commitments["commitmentDigest"],
            "resultDigest": _mapping(result["integrity"])["resultDigest"],
        },
        "status": {
            "exactScope": result["scope"],
            "literalResult": result["outcome"],
            "attemptState": "consumed_1_of_1",
            "coverageState": "partial",
            "firstUnmetPredicate": None,
            "blockers": [
                "pre_topology_result_requires_rerun_for_any_changed_topology",
                "physical_cloth_and_real_world_deformation_not_measured",
            ],
            "unsupportedEvidenceClasses": [
                "physical_cloth_accuracy",
                "real_world_deformation",
                "real_photo",
                "real_fabric",
                "human_review",
                "private_user",
                "gpu",
                "mobile",
                "production",
                "phy1",
                "z2",
            ],
            "candidateCreated": False,
            "candidateAttemptConsumed": False,
            "topologyStrategyBudgetBefore": 1,
            "topologyStrategyBudgetAfter": 1,
            "runtimeSelected": result["candidateId"],
            "runtimeSelectionReason": "exact_unit_f_sentinel_unchanged_pre_topology",
            "unitOEligible": True,
            "unitPEligible": False,
        },
        "metrics": result["maximums"],
        "poseCount": result["poseCount"],
        "posePassCount": result["posePassCount"],
        "d0Rp08Status": result["d0Rp08Status"],
        "optionalProcessors": {
            "z1": "not_run_dependency_blocked",
            "mt1": "not_run_dependency_blocked",
        },
    }
    write_canonical_json(root / EVIDENCE_ROOT / "outcome_report.json", outcome_report)
    return lifecycle


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and import the one Unit N attempt.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--job-id", type=int, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    lifecycle = import_attempt(root, args.source.resolve(), args.job_id)
    print(
        f"unit_n_import={lifecycle['outcome']} "
        f"poses={lifecycle['posePassCount']}/{lifecycle['poseCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
