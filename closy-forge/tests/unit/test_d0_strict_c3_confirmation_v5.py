from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from closy_forge.package_io.canonical_json import read_json
from closy_forge.strict_c3_confirmation_v5.protocol import (
    EVIDENCE_ROOT,
    FIXTURE_ROOT,
    LOCK_PATH,
    POSE_CLASS_ORDER,
    POSE_RANGES,
    SENTINEL_PATH,
    build_protocol_lock,
    build_sentinel_lock,
    document_digest,
    validate_protocol_lock,
)

ROOT = Path(__file__).resolve().parents[2]


def test_unit_n_resolves_exact_unit_f_sentinel_before_any_fresh_pose() -> None:
    sentinel = read_json(ROOT / SENTINEL_PATH)

    assert sentinel == build_sentinel_lock(ROOT)
    assert sentinel["resolutionOutcome"] == "unit_f_exact_candidate"
    assert sentinel["unitMQualified"] is False
    assert sentinel["resolvedBeforeFreshPoseGeneration"] is True
    assert sentinel["candidateId"] == "candidate.d0_texture_rerender_v3.49161d8adafb514e5a04b1a9"
    assert sentinel["candidatePackageDigest"] == (
        "c338762915d390a22e879f588e0f01a4b6ed586b9ff045eb0a039888ace8223b"
    )


def test_protocol_is_fresh_and_freezes_eight_classes_without_pose_instances() -> None:
    sentinel = read_json(ROOT / SENTINEL_PATH)
    lock = read_json(ROOT / LOCK_PATH)

    assert lock == build_protocol_lock(ROOT, sentinel)
    assert validate_protocol_lock(ROOT, lock) == []
    assert lock["state"] == "frozen_before_fresh_pose_parameter_or_target_realisation"
    assert lock["poseGenerator"]["classOrder"] == list(POSE_CLASS_ORDER)
    assert lock["poseGenerator"]["poseCount"] == 8
    assert lock["poseGenerator"]["freshPoseParametersRealized"] is False
    assert "poses" not in lock["poseGenerator"]
    assert set(lock["poseGenerator"]["ranges"]) == set(POSE_RANGES)
    assert lock["binding"]["tuningAllowed"] is False


def test_h4_failure_and_attempt_counter_remain_immutable() -> None:
    preservation = read_json(ROOT / FIXTURE_ROOT / "h4_preservation.json")
    h4 = read_json(ROOT / "docs/evidence/d0_core_runtime_c3_v4/strict_c3_result.json")

    assert preservation["v4HeldOutAttemptConsumed"] is True
    assert preservation["v4CompletedPoseCount"] == 0
    assert preservation["v4RequiredPoseCount"] == 8
    assert preservation["patchedReplayQualificationAllowed"] is False
    assert preservation["freshV5PoseRealized"] is False
    assert h4["heldOutAttemptConsumed"] is True
    assert h4["completedHeldOutStateCount"] == 0


def test_revealed_h4_diagnostic_exercises_full_path_but_cannot_qualify() -> None:
    diagnostic = read_json(ROOT / FIXTURE_ROOT / "revealed_h4_diagnostic.json")

    assert diagnostic["usesRevealedH4Parameters"] is True
    assert diagnostic["freshV5PoseRealized"] is False
    assert diagnostic["qualificationEligible"] is False
    assert diagnostic["qualificationAttemptConsumed"] is False
    assert diagnostic["poseCount"] == 8
    assert diagnostic["posePassCount"] == 8
    assert diagnostic["diagnosticResult"] == "pass"
    assert diagnostic["mutationStatus"] == "pass"


def test_lock_digest_and_every_frozen_implementation_hash_fail_closed() -> None:
    lock = read_json(ROOT / LOCK_PATH)
    mutation = deepcopy(lock)
    mutation["thresholds"]["maximumBindingReconstructionErrorMeters"] = 0.1

    assert mutation["integrity"]["protocolLockDigest"] != document_digest(
        mutation, "protocolLockDigest"
    )
    assert "protocol_lock_digest_mismatch" in validate_protocol_lock(ROOT, mutation)
    assert len(lock["implementationFiles"]) == 7


def test_generic_v5_evaluator_fixtures_are_non_qualifying_and_complete() -> None:
    generic = read_json(ROOT / FIXTURE_ROOT / "generic_evaluator_fixtures.json")

    assert generic["allPassed"] is True
    assert generic["freshHeldOutPoseRealized"] is False
    assert generic["qualificationAttemptConsumed"] is False
    assert generic["oracle"]["readsCandidateBindingWeights"] is False
    assert generic["oracle"]["callsCandidateReconstruction"] is False


def test_optional_exact_processors_remain_literal_not_run() -> None:
    lock = read_json(ROOT / LOCK_PATH)

    assert lock["optionalProcessors"]["z1"].startswith("not_run_dependency_blocked")
    assert lock["optionalProcessors"]["mt1"].startswith("not_run_dependency_blocked")
    assert lock["optionalProcessors"]["maximumRecoveryAttemptsPerSourcePlatform"] == 1


def test_imported_attempt_is_sealed_and_exact_when_present() -> None:
    lifecycle_path = ROOT / FIXTURE_ROOT / "authority_lifecycle.json"
    if not lifecycle_path.exists():
        return
    lifecycle = read_json(lifecycle_path)
    result = read_json(ROOT / EVIDENCE_ROOT / "strict_c3_result.json")

    assert lifecycle["state"] == "sealed_after_first_external_pose_commitment"
    assert lifecycle["attemptConsumed"] is True
    assert lifecycle["qualificationRetryAllowed"] is False
    assert lifecycle["authorityDispatchEnabledAfterSeal"] is False
    assert result["poseCount"] == 8
    assert result["attempt"]["consumed"] is True
    assert result["integrity"]["resultDigest"] == document_digest(result, "resultDigest")
