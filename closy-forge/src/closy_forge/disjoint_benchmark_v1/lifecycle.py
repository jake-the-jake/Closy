from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class SeedLifecycleState(StrEnum):
    PRE_AUTHORITY = "pre_authority"
    AUTHORITY_FROZEN_PRE_EVALUATOR = "authority_frozen_pre_evaluator"
    SEALED_POST_EVALUATOR = "sealed_post_evaluator"
    INVALID = "invalid"


@dataclass(frozen=True)
class SeedLifecycleReport:
    state: SeedLifecycleState
    issues: tuple[str, ...]
    authority_run_id: int | None
    authority_job_id: int | None
    sealed_verification_only: bool


# These are the immutable files and first authority tuple published by Unit G v1.
# Sealed validation reads only these bytes; it cannot derive a replacement seed or rerun work.
UNIT_G_V1_FILE_HASHES = {
    "protocol_lock.json": "140a53abd6119880d01d81999a576e410ae4ef1052fd67d2ae5fb4bc4f3a1d7a",
    "development_lock.json": "379228b9783c7e0c3945607f979e9045716ca31a0b84735efc2525a97bedd317",
    "development_summary.json": "a38a5c3c998ac52c169cc0f6b76d86bfdf4caba9916e89926284a9e1a1b01f68",
    "evaluator/seed_authority.json": (
        "842a00b7587aad1850e62f046ad7dae84d35f2b2bfb28d11b86f446c944cc46e"
    ),
    "evaluator/raw_draw_rejection_transcript.json": (
        "2aa9c3d6a6ecf4ca03de1bc7712bdd2dd893b8733d0b0ffc194b5f27e7aa5936"
    ),
    "evaluator/commitments.json": (
        "e03d7744fd2a6d1b4c88bb8151c59c9aae54987fbed8309a9af7747af581a844"
    ),
    "evaluator/predictions.json": (
        "22f7d6a78b9a3abd6c0a58f1e92d8d5e549ce6afab34a6ee3544b4caaf874a87"
    ),
    "evaluator/isolation_report.json": (
        "4a6c87cb1f04b70cc653f6bd80c410df69c04a3a82635b0fe244fd94f1664f07"
    ),
    "evaluator/prediction_freeze.json": (
        "ead7bcb9a9fe29574d2dee3e8915c30662b1987abc8c9f35d439fab5d3d37481"
    ),
    "evaluator/target_reveal.json": (
        "e85dd86ea94fa72e9741afb71e2d64404e208c477a8f07a180966b1bb9da8947"
    ),
    "evaluator/evaluation_attempt_failure.json": (
        "231bf3846066b6022a4093aee3cd87fec749c494d079f9956073e1b0cb828714"
    ),
    "evaluator/benchmark_result.json": (
        "57ff2962f2fa67bc04b28d2dd5f88239ccfba3349a95e3125495478546ad9a31"
    ),
}

UNIT_G_V1_AUTHORITY = {
    "schemaVersion": 1,
    "authorityVersion": "closy.d0_disjoint.seed_authority.v1",
    "lockCommitSha": "77d8b0bd0b98ba78485979708bb2c61bc1e41b7c",
    "firstNonRerunRunId": 33467062432,
    "firstNonRerunJobId": 99729005374,
    "rerunAttempt": 1,
    "derivedSeed": "36bf2d72a4d1c97799df81c01195cc99719236b5bbd7d931e6475bf631a4cd12",
    "replacementHeadsAreAuthorities": False,
    "laterRerunsAreAuthorities": False,
}

_BASE_FILES = (
    "protocol_lock.json",
    "development_lock.json",
    "development_summary.json",
)
_AUTHORITY_FILES = (
    "evaluator/seed_authority.json",
    "evaluator/raw_draw_rejection_transcript.json",
    "evaluator/commitments.json",
)
_SEALED_FILES = (
    "evaluator/predictions.json",
    "evaluator/isolation_report.json",
    "evaluator/prediction_freeze.json",
    "evaluator/target_reveal.json",
    "evaluator/evaluation_attempt_failure.json",
    "evaluator/benchmark_result.json",
)


def inspect_seed_lifecycle(fixture_root: Path) -> SeedLifecycleReport:
    issues: list[str] = []
    required: tuple[str, ...]
    present = {
        relative
        for relative in (*_BASE_FILES, *_AUTHORITY_FILES, *_SEALED_FILES)
        if (fixture_root / relative).is_file()
    }
    authority_present = any(item in present for item in _AUTHORITY_FILES)
    sealed_present = any(item in present for item in _SEALED_FILES)

    if not authority_present and not sealed_present:
        state = SeedLifecycleState.PRE_AUTHORITY
        required = _BASE_FILES
    elif all(item in present for item in _AUTHORITY_FILES) and not sealed_present:
        state = SeedLifecycleState.AUTHORITY_FROZEN_PRE_EVALUATOR
        required = (*_BASE_FILES, *_AUTHORITY_FILES)
    elif all(item in present for item in (*_AUTHORITY_FILES, *_SEALED_FILES)):
        state = SeedLifecycleState.SEALED_POST_EVALUATOR
        required = (*_BASE_FILES, *_AUTHORITY_FILES, *_SEALED_FILES)
    else:
        state = SeedLifecycleState.INVALID
        required = (*_BASE_FILES, *_AUTHORITY_FILES, *_SEALED_FILES)
        issues.append("unit_g_lifecycle_incomplete_or_reordered_inventory")

    for relative in required:
        path = fixture_root / relative
        if not path.is_file():
            issues.append(f"unit_g_lifecycle_missing:{relative}")
            continue
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != UNIT_G_V1_FILE_HASHES[relative]:
            issues.append(f"unit_g_lifecycle_hash_mismatch:{relative}")

    authority_paths = sorted(
        path.relative_to(fixture_root).as_posix()
        for path in fixture_root.rglob("seed_authority*.json")
    )
    expected_authority_count = 0 if state == SeedLifecycleState.PRE_AUTHORITY else 1
    if len(authority_paths) != expected_authority_count:
        issues.append("unit_g_lifecycle_conflicting_or_second_authority")
    if authority_paths and authority_paths != ["evaluator/seed_authority.json"]:
        issues.append("unit_g_lifecycle_unexpected_authority_path")

    authority_run_id: int | None = None
    authority_job_id: int | None = None
    if state in {
        SeedLifecycleState.AUTHORITY_FROZEN_PRE_EVALUATOR,
        SeedLifecycleState.SEALED_POST_EVALUATOR,
    }:
        authority = _load_mapping(fixture_root / "evaluator/seed_authority.json", issues)
        if authority != UNIT_G_V1_AUTHORITY:
            issues.append("unit_g_lifecycle_authority_tuple_mismatch")
        authority_run_id = _optional_int(authority.get("firstNonRerunRunId"))
        authority_job_id = _optional_int(authority.get("firstNonRerunJobId"))

    if state == SeedLifecycleState.SEALED_POST_EVALUATOR:
        _validate_sealed_chronology(fixture_root, issues)

    if issues:
        state = SeedLifecycleState.INVALID
    return SeedLifecycleReport(
        state=state,
        issues=tuple(sorted(set(issues))),
        authority_run_id=authority_run_id,
        authority_job_id=authority_job_id,
        sealed_verification_only=state == SeedLifecycleState.SEALED_POST_EVALUATOR,
    )


def _validate_sealed_chronology(fixture_root: Path, issues: list[str]) -> None:
    protocol = _load_mapping(fixture_root / "protocol_lock.json", issues)
    lock = _load_mapping(fixture_root / "development_lock.json", issues)
    commitments = _load_mapping(fixture_root / "evaluator/commitments.json", issues)
    predictions = _load_mapping(fixture_root / "evaluator/predictions.json", issues)
    freeze = _load_mapping(fixture_root / "evaluator/prediction_freeze.json", issues)
    reveal = _load_mapping(fixture_root / "evaluator/target_reveal.json", issues)
    failure = _load_mapping(fixture_root / "evaluator/evaluation_attempt_failure.json", issues)
    result = _load_mapping(fixture_root / "evaluator/benchmark_result.json", issues)

    _expect(
        protocol.get("evaluatorIdentitiesRealized") is False, "protocol_identity_freeze", issues
    )
    _expect(protocol.get("targetContentsMounted") is False, "protocol_target_freeze", issues)
    _expect(lock.get("evaluatorIdentitiesRealized") is False, "lock_identity_freeze", issues)
    _expect(lock.get("targetContentsMounted") is False, "lock_target_freeze", issues)

    commitment_ids = _identity_ids(commitments)
    reveal_ids = _identity_ids(reveal)
    _expect(commitments.get("identityCount") == 16, "commitment_denominator", issues)
    _expect(len(commitment_ids) == 16 and len(set(commitment_ids)) == 16, "commitment_ids", issues)
    _expect(commitments.get("targetsPresent") is False, "commitment_targets", issues)
    _expect(commitments.get("noncesPresent") is False, "commitment_nonces", issues)
    _expect(commitments.get("targetParametersPresent") is False, "commitment_parameters", issues)
    _expect(commitments.get("allOpaque") is True, "commitment_opacity", issues)
    _expect(reveal_ids == commitment_ids, "reveal_identity_order", issues)
    _expect(reveal.get("allCommitmentsValid") is True, "reveal_commitments", issues)

    _expect(predictions.get("identityCount") == 16, "prediction_identity_denominator", issues)
    _expect(predictions.get("routeCount") == 4, "prediction_route_denominator", issues)
    _expect(predictions.get("predictionCount") == 64, "prediction_denominator", issues)
    _expect(predictions.get("targetsMounted") is False, "prediction_targets", issues)
    _expect(predictions.get("targetParametersRead") is False, "prediction_parameters", issues)
    _expect(predictions.get("thirdViewsMounted") is False, "prediction_third_views", issues)
    _expect(
        freeze.get("predictionSetHash") == predictions.get("predictionSetHash"),
        "prediction_freeze_hash",
        issues,
    )
    _expect(
        freeze.get("commitmentsHash") == UNIT_G_V1_FILE_HASHES["evaluator/commitments.json"],
        "commitments_freeze_hash",
        issues,
    )
    _expect(freeze.get("predictionIdentityCount") == 64, "freeze_denominator", issues)
    _expect(freeze.get("targetContentsMounted") is False, "freeze_target_mount", issues)
    _expect(
        reveal.get("predictionFreezeHash") == freeze.get("freezeHash"), "reveal_freeze_hash", issues
    )

    _expect(failure.get("status") == "fail", "failure_status", issues)
    _expect(failure.get("attemptId") == "attempt.g.evaluator.001", "failure_attempt", issues)
    _expect(failure.get("retryAllowed") is False, "failure_retry", issues)
    _expect(failure.get("workerDispatched") is False, "failure_dispatch", issues)
    _expect(failure.get("fullCompileCount") == 0, "failure_compile_count", issues)
    _expect(failure.get("appearanceEvaluationCount") == 0, "failure_appearance_count", issues)
    _expect(
        failure.get("predictionFreezeHash") == freeze.get("freezeHash"),
        "failure_freeze_hash",
        issues,
    )
    _expect(
        failure.get("targetRevealHash") == UNIT_G_V1_FILE_HASHES["evaluator/target_reveal.json"],
        "failure_reveal_hash",
        issues,
    )
    _expect(
        result.get("outcome") == "benchmark_failed_fixed_inventory_unfinished",
        "result_outcome",
        issues,
    )
    _expect(result.get("failureAttemptId") == failure.get("attemptId"), "result_attempt", issues)
    _expect(result.get("predictionCount") == 64, "result_prediction_count", issues)
    _expect(result.get("fullCompileCount") == 0, "result_compile_count", issues)
    _expect(result.get("appearanceEvaluationCount") == 0, "result_appearance_count", issues)
    _expect(result.get("targetCommitmentsValid") is True, "result_commitments", issues)


def _load_mapping(path: Path, issues: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        issues.append(f"unit_g_lifecycle_unreadable_json:{path.name}")
        return {}
    if not isinstance(value, dict):
        issues.append(f"unit_g_lifecycle_mapping_required:{path.name}")
        return {}
    return value


def _identity_ids(value: dict[str, Any]) -> list[str]:
    identities = value.get("identities")
    if not isinstance(identities, list):
        return []
    return [
        str(item.get("opaqueId"))
        for item in identities
        if isinstance(item, dict) and isinstance(item.get("opaqueId"), str)
    ]


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _expect(condition: bool, label: str, issues: list[str]) -> None:
    if not condition:
        issues.append(f"unit_g_lifecycle_chronology_mismatch:{label}")
