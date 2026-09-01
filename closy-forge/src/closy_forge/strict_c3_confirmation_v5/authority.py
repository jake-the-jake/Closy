from __future__ import annotations

import os
import secrets
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.strict_c3_confirmation_v5.evaluator import evaluate_confirmation
from closy_forge.strict_c3_confirmation_v5.oracle import generate_oracle_target
from closy_forge.strict_c3_confirmation_v5.protocol import (
    LOCK_PATH,
    SENTINEL_PATH,
    UNIT_F_PACKAGE,
    document_digest,
    realize_pose_suite,
    validate_protocol_lock,
)

AUTHORITY_VERSION = "closy.d0.strict_c3.external_pose_authority.v5"


def run_official_attempt(root: Path, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise ValueError("unit_n_authority_output_not_empty")
    output.mkdir(parents=True, exist_ok=True)
    lock = _mapping(read_json(root / LOCK_PATH))
    sentinel = _mapping(read_json(root / SENTINEL_PATH))
    issues = validate_protocol_lock(root, lock)
    if issues:
        raise ValueError("unit_n_authority_lock_invalid:" + ",".join(issues))
    if sentinel.get("sentinelLockDigest") != lock.get("sentinelLockDigest"):
        raise ValueError("unit_n_authority_sentinel_lock_mismatch")

    seed = secrets.token_bytes(32)
    seed_commitment = sha256_bytes(b"CLOSY_UNIT_N_POSE_SEED_V5\x00" + seed)
    poses = realize_pose_suite(seed)
    pose_document: dict[str, Any] = {
        "schemaVersion": 1,
        "generatorVersion": _mapping(lock["poseGenerator"])["version"],
        "poseCount": len(poses),
        "poses": poses,
        "poseSuiteDigest": "",
    }
    pose_document["poseSuiteDigest"] = document_digest(pose_document, "poseSuiteDigest")

    package = root / UNIT_F_PACKAGE
    simulation = read_glb_meshset(package / "simulation/settled_mesh.glb")
    dense = read_glb_meshset(package / "render/render_mesh.glb")
    target_dir = output / "private_targets"
    target_dir.mkdir(parents=True, exist_ok=False)
    target_paths: list[Path] = []
    target_commitments: list[dict[str, Any]] = []
    for pose in poses:
        target_path = target_dir / f"{pose['poseId']}.json"
        write_canonical_json(target_path, generate_oracle_target(simulation, dense, pose))
        target_paths.append(target_path)
        target_commitments.append(
            {
                "poseId": pose["poseId"],
                "sha256": sha256_file(target_path),
                "byteLength": target_path.stat().st_size,
            }
        )

    commitments: dict[str, Any] = {
        "schemaVersion": 1,
        "authorityVersion": AUTHORITY_VERSION,
        "authorityRunId": os.environ.get("GITHUB_RUN_ID", "local_forbidden_for_qualification"),
        "authorityRunAttempt": os.environ.get("GITHUB_RUN_ATTEMPT", "0"),
        "authorityJob": os.environ.get("GITHUB_JOB", "local"),
        "authorityHeadSha": os.environ.get("GITHUB_SHA", "local"),
        "seedCommitmentSha256": seed_commitment,
        "poseSuiteDigest": pose_document["poseSuiteDigest"],
        "targetCommitments": target_commitments,
        "candidateId": lock["candidateId"],
        "candidatePackageDigest": lock["candidatePackageDigest"],
        "sentinelLockDigest": lock["sentinelLockDigest"],
        "protocolLockDigest": _mapping(lock["integrity"])["protocolLockDigest"],
        "chronology": [
            "lock_and_sentinel_validated",
            "random_256_bit_seed_accepted",
            "eight_pose_parameters_realized",
            "oracle_targets_generated_without_candidate_binding",
            "commitments_published_before_evaluation",
        ],
        "commitmentDigest": "",
    }
    commitments["commitmentDigest"] = document_digest(commitments, "commitmentDigest")
    write_canonical_json(output / "authority_commitments.json", commitments)
    write_canonical_json(output / "pose_suite.json", pose_document)
    print(f"unit_n_commitment={commitments['commitmentDigest']}", flush=True)

    try:
        evaluation = evaluate_confirmation(root, lock, poses, target_paths)
        outcome = str(evaluation["resultStatus"])
        failure: dict[str, Any] | None = None
    except Exception as error:  # preserve a consumed post-commitment harness failure
        evaluation = {
            "schemaVersion": 1,
            "resultStatus": "integrity_error",
            "d0Rp08Status": "fail",
            "poseCount": 8,
            "posePassCount": 0,
            "attemptConsumed": True,
            "error": {
                "exceptionType": type(error).__name__,
                "reason": str(error),
                "stage": "post_commitment_evaluation",
            },
        }
        outcome = "integrity_error"
        failure = _mapping(evaluation["error"])

    result: dict[str, Any] = {
        **evaluation,
        "authority": {
            "runId": commitments["authorityRunId"],
            "runAttempt": commitments["authorityRunAttempt"],
            "job": commitments["authorityJob"],
            "headSha": commitments["authorityHeadSha"],
            "commitmentDigest": commitments["commitmentDigest"],
            "seedCommitmentSha256": seed_commitment,
        },
        "attempt": {
            "freshConfirmationAttemptNumber": 1,
            "maximumFreshConfirmationAttempts": 1,
            "consumed": True,
            "rerollAllowed": False,
        },
        "outcome": outcome,
        "failure": failure,
        "integrity": {"resultDigest": ""},
    }
    result["integrity"]["resultDigest"] = document_digest(result, "resultDigest")
    write_canonical_json(output / "strict_c3_result.json", result)
    reveal: dict[str, Any] = {
        "schemaVersion": 1,
        "seedHex": seed.hex(),
        "seedCommitmentSha256": seed_commitment,
        "poseSuiteDigest": pose_document["poseSuiteDigest"],
        "targetCommitmentDigest": sha256_bytes(canonical_dumps(target_commitments).encode("utf-8")),
        "revealedOnlyAfterResultFinalized": True,
        "revealDigest": "",
    }
    reveal["revealDigest"] = document_digest(reveal, "revealDigest")
    write_canonical_json(output / "authority_reveal.json", reveal)
    return result


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
