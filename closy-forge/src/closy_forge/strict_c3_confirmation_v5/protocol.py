from __future__ import annotations

import hashlib
import hmac
import math
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, canonical_text_bytes, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.recovery_foundation_v1.sentinel import (
    resolve_sentinel,
    validate_sentinel_resolution,
)

LOCK_VERSION = "closy.d0.strict_c3_confirmation.protocol_lock.v5"
FIXTURE_ROOT = Path("fixtures/d0_strict_c3_confirmation_v5")
EVIDENCE_ROOT = Path("docs/evidence/d0_strict_c3_confirmation_v5")
LOCK_PATH = FIXTURE_ROOT / "protocol_lock.json"
SENTINEL_PATH = FIXTURE_ROOT / "sentinel_manifest.json"
H4_RESULT_PATH = Path("docs/evidence/d0_core_runtime_c3_v4/strict_c3_result.json")
H4_LOCK_PATH = Path("fixtures/d0_core_runtime_c3_v4/protocol_lock.json")
UNIT_M_FAILURE_PATH = Path(
    "fixtures/d0_disjoint_tshirt_confirmation_v2/official_attempt_failure.json"
)
UNIT_F_PACKAGE = Path(
    "docs/evidence/d0_texture_rerender_correction_v3/predictions/candidate_package"
)
UNIT_F_RUNTIME = Path(
    "docs/evidence/d0_texture_rerender_correction_v3/predictions/candidate_runtime.closyruntime"
)

POSE_CLASS_ORDER = (
    "neutral",
    "left_arm_elevation",
    "right_arm_elevation",
    "asymmetric_elevation",
    "bend",
    "twist",
    "moderate_stretch",
    "combined_stress",
)

POSE_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "neutral": {
        "leftArmLiftDegrees": (0.0, 0.0),
        "rightArmLiftDegrees": (0.0, 0.0),
        "torsoBendDegrees": (0.0, 0.0),
        "torsoTwistDegrees": (0.0, 0.0),
        "materialStretchU": (1.0002, 1.0008),
    },
    "left_arm_elevation": {
        "leftArmLiftDegrees": (33.0, 44.0),
        "rightArmLiftDegrees": (0.5, 4.0),
        "torsoBendDegrees": (-1.0, 1.0),
        "torsoTwistDegrees": (-2.0, 2.0),
        "materialStretchU": (1.002, 1.008),
    },
    "right_arm_elevation": {
        "leftArmLiftDegrees": (0.5, 4.0),
        "rightArmLiftDegrees": (34.0, 45.0),
        "torsoBendDegrees": (-1.0, 1.0),
        "torsoTwistDegrees": (-2.0, 2.0),
        "materialStretchU": (1.002, 1.008),
    },
    "asymmetric_elevation": {
        "leftArmLiftDegrees": (25.0, 39.0),
        "rightArmLiftDegrees": (8.0, 21.0),
        "torsoBendDegrees": (-2.0, 2.0),
        "torsoTwistDegrees": (3.0, 8.0),
        "materialStretchU": (1.005, 1.015),
    },
    "bend": {
        "leftArmLiftDegrees": (2.0, 7.0),
        "rightArmLiftDegrees": (2.0, 7.0),
        "torsoBendDegrees": (10.0, 16.0),
        "torsoTwistDegrees": (-2.0, 2.0),
        "materialStretchU": (1.005, 1.015),
    },
    "twist": {
        "leftArmLiftDegrees": (2.0, 8.0),
        "rightArmLiftDegrees": (2.0, 8.0),
        "torsoBendDegrees": (-2.0, 2.0),
        "torsoTwistDegrees": (14.0, 21.0),
        "materialStretchU": (1.005, 1.015),
    },
    "moderate_stretch": {
        "leftArmLiftDegrees": (3.0, 9.0),
        "rightArmLiftDegrees": (3.0, 9.0),
        "torsoBendDegrees": (-2.0, 2.0),
        "torsoTwistDegrees": (-3.0, 3.0),
        "materialStretchU": (1.025, 1.045),
    },
    "combined_stress": {
        "leftArmLiftDegrees": (36.0, 44.0),
        "rightArmLiftDegrees": (27.0, 35.0),
        "torsoBendDegrees": (11.0, 15.5),
        "torsoTwistDegrees": (16.0, 20.5),
        "materialStretchU": (1.03, 1.045),
    },
}

IMPLEMENTATION_PATHS = (
    "src/closy_forge/strict_c3_confirmation_v5/candidate.py",
    "src/closy_forge/strict_c3_confirmation_v5/oracle.py",
    "src/closy_forge/strict_c3_confirmation_v5/protocol.py",
    "src/closy_forge/strict_c3_confirmation_v5/evaluator.py",
    "src/closy_forge/strict_c3_confirmation_v5/repeat_worker.py",
    "src/closy_forge/strict_c3_confirmation_v5/authority.py",
    "scripts/run_d0_strict_c3_confirmation_v5_authority.py",
)


def build_sentinel_lock(root: Path) -> dict[str, Any]:
    unit_m = _mapping(read_json(root / UNIT_M_FAILURE_PATH))
    if unit_m.get("benchmarkOutcome") != "attempted_integrity_error":
        raise ValueError("unit_n_unit_m_outcome_not_frozen_failure")
    sentinel = resolve_sentinel(root)
    issues = validate_sentinel_resolution(sentinel)
    if issues:
        raise ValueError("unit_n_sentinel_invalid:" + ",".join(issues))
    if sentinel.get("resolutionOutcome") != "unit_f_exact_candidate":
        raise ValueError("unit_n_expected_unit_f_fallback_not_resolved")
    document: dict[str, Any] = {
        **sentinel,
        "selectionRule": (
            "unit_m_fixed_sentinel_if_qualified_else_exact_unit_f_else_dependency_block"
        ),
        "unitMQualified": False,
        "selectedBecause": "unit_m_attempted_integrity_error_exact_unit_f_fallback",
        "resolvedBeforeFreshPoseGeneration": True,
        "sentinelLockDigest": "",
    }
    document["sentinelLockDigest"] = document_digest(document, "sentinelLockDigest")
    return document


def build_protocol_lock(root: Path, sentinel: Mapping[str, Any]) -> dict[str, Any]:
    h4_result = _mapping(read_json(root / H4_RESULT_PATH))
    h4_lock = _mapping(read_json(root / H4_LOCK_PATH))
    if h4_result.get("heldOutAttemptConsumed") is not True:
        raise ValueError("unit_n_h4_attempt_not_preserved_consumed")
    thresholds = {
        "maximumBindingReconstructionErrorMeters": 0.0001,
        "maximumSemanticSeamCrackMeters": 0.002,
        "maximumTangentialSeamSlidingMeters": 0.005,
        "maximumInvertedTriangleCount": 0,
        "requiredPosePassCount": 8,
        "requiredPoseCount": 8,
        "maximumNormalLengthError": 0.00001,
        "maximumTangentLengthError": 0.00001,
        "maximumAbsoluteNormalTangentDot": 0.00001,
        "maximumWholeEvaluationSecondsPerPose": 2.0,
        "maximumWholeEvaluationPeakMemoryMiB": 512.0,
    }
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "lockVersion": LOCK_VERSION,
        "state": "frozen_before_fresh_pose_parameter_or_target_realisation",
        "sentinelLockDigest": sentinel["sentinelLockDigest"],
        "candidateId": sentinel["candidateId"],
        "candidatePackageDigest": sentinel["candidatePackageDigest"],
        "runtimePackageDigest": sentinel["runtimePackageDigest"],
        "binding": {
            "strategy": "persisted_sim_triangle_barycentric_v1",
            "weightsFrozen": True,
            "tuningAllowed": False,
            "path": (UNIT_F_PACKAGE / "binding/sim_to_render.bin").as_posix(),
            "sha256": sha256_file(root / UNIT_F_PACKAGE / "binding/sim_to_render.bin"),
        },
        "frozenInputs": {
            "simulationMesh": _identity(root, UNIT_F_PACKAGE / "simulation/settled_mesh.glb"),
            "semanticSeamGraph": _identity(root, UNIT_F_PACKAGE / "simulation/constraints.json"),
            "renderMesh": _identity(root, UNIT_F_PACKAGE / "render/render_mesh.glb"),
            "bindingManifest": _identity(root, UNIT_F_PACKAGE / "binding/binding_manifest.json"),
            "normalsTangents": _identity(root, UNIT_F_PACKAGE / "render/render_mesh.glb"),
            "runtimeDescriptor": _identity(root, UNIT_F_RUNTIME / "manifest.json"),
            "conventionalFallback": _identity(
                root, UNIT_F_RUNTIME / "assets/conventional_fallback.glb"
            ),
        },
        "evaluator": {
            "version": "closy.d0.strict_c3_binding_evaluator.v5",
            "frameAdapter": "closy.c3.frame_metrics.v5",
            "semanticSeamMetric": "candidate_minus_oracle_seam_delta_decomposed_by_oracle_tangent",
            "wholeEvaluationResourceBoundary": True,
        },
        "oracle": {
            "version": "closy.c3.independent_material_coordinate_oracle.v5",
            "readsCandidateBindingWeights": False,
            "callsCandidateReconstruction": False,
            "sourceAndDataFrozenBeforePoseRealisation": True,
            "evidenceClass": "project_authored_analytic_synthetic_pose_field",
            "correlationLimitation": "shares_frozen_pose_semantics_not_physical_ground_truth",
        },
        "poseGenerator": {
            "version": "closy.c3.pose_authority.hmac_sha256_ranges.v5",
            "seedBits": 256,
            "seedAuthority": "first_external_github_actions_workflow_run",
            "classOrder": list(POSE_CLASS_ORDER),
            "ranges": {
                key: {field: list(bounds) for field, bounds in value.items()}
                for key, value in POSE_RANGES.items()
            },
            "poseCount": 8,
            "oldH4ExactParametersForbidden": True,
            "freshPoseParametersRealized": False,
        },
        "thresholds": thresholds,
        "metricUnits": {
            "bindingReconstruction": "meters",
            "semanticSeamCrack": "meters",
            "tangentialSeamSliding": "meters",
            "frameNormalAndTangent": "dimensionless_absolute_error",
            "wholeEvaluationRuntime": "seconds_per_pose",
            "wholeEvaluationPeakMemory": "mebibytes_per_pose",
        },
        "determinism": {
            "canonicalVertexPrecisionDecimalPlaces": 9,
            "sameProcessRepeatRequired": True,
            "freshProcessRepeatCount": 2,
            "freshProcessCanonicalOutputEqualityRequired": True,
        },
        "attemptPolicy": {
            "maximumFreshConfirmationAttempts": 1,
            "attemptConsumedAfterFirstPoseCommitment": True,
            "rerollOrReplacementAllowed": False,
            "patchedReplayMayQualify": False,
        },
        "h4Preservation": {
            "result": _identity(root, H4_RESULT_PATH),
            "protocolLock": _identity(root, H4_LOCK_PATH),
            "heldOutAttemptConsumed": True,
            "completedPoseCount": 0,
            "requiredPoseCount": 8,
            "qualificationReplayAllowed": False,
            "oldProtocolDigest": h4_lock.get("integrity", {}).get("protocolLockDigest"),
        },
        "mutationControls": [
            "binding_weight_mutation_must_exceed_reconstruction_limit",
            "oracle_target_digest_must_remain_unchanged",
            "simulation_and_render_topology_hash_mutations_fail_closed",
            "frame_metric_alias_unknown_missing_nonfinite_ambiguity_fail_closed",
            "two_fresh_subprocess_outputs_must_match_canonical_evaluation_output",
        ],
        "optionalProcessors": {
            "z1": "not_run_dependency_blocked_no_matching_authenticated_executable",
            "mt1": "not_run_dependency_blocked_no_matching_authenticated_executable",
            "maximumRecoveryAttemptsPerSourcePlatform": 1,
            "totalWallClockBudgetMinutes": 60,
        },
        "scope": {
            "syntheticBindingReconstruction": True,
            "preTopology": True,
            "physicalClothAccuracy": False,
            "realWorldDeformation": False,
            "phy1": False,
            "z2": False,
        },
        "implementationHashMode": "utf8_canonical_lf_final_newline",
        "implementationFiles": [
            {"path": path, "sha256": canonical_source_sha256(root / path)}
            for path in IMPLEMENTATION_PATHS
        ],
        "integrity": {"protocolLockDigest": ""},
    }
    document["integrity"]["protocolLockDigest"] = document_digest(document, "protocolLockDigest")
    return document


def realize_pose_suite(seed: bytes) -> list[dict[str, Any]]:
    if len(seed) != 32:
        raise ValueError("unit_n_authority_seed_must_be_256_bits")
    poses: list[dict[str, Any]] = []
    for class_index, class_id in enumerate(POSE_CLASS_ORDER):
        values: dict[str, Any] = {
            "poseClass": class_id,
            "poseId": f"pose.{class_index:02d}.{_digest_bytes(seed, class_id, 'id').hex()[:16]}",
        }
        for field, (minimum, maximum) in POSE_RANGES[class_id].items():
            fraction = int.from_bytes(_digest_bytes(seed, class_id, field)[:8], "big") / (2**64 - 1)
            value = minimum + (maximum - minimum) * fraction
            values[field] = round(value, 9)
        poses.append(values)
    validate_pose_suite(poses)
    return poses


def validate_pose_suite(poses: list[dict[str, Any]]) -> None:
    if len(poses) != 8 or [pose.get("poseClass") for pose in poses] != list(POSE_CLASS_ORDER):
        raise ValueError("unit_n_pose_class_denominator_invalid")
    if len({pose.get("poseId") for pose in poses}) != 8:
        raise ValueError("unit_n_pose_ids_not_unique")
    for pose in poses:
        class_id = str(pose["poseClass"])
        for field, (minimum, maximum) in POSE_RANGES[class_id].items():
            value = pose.get(field)
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ValueError(f"unit_n_pose_value_invalid:{class_id}:{field}")
            if not math.isfinite(value) or not minimum <= float(value) <= maximum:
                raise ValueError(f"unit_n_pose_out_of_range:{class_id}:{field}")


def validate_protocol_lock(root: Path, document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if document.get("lockVersion") != LOCK_VERSION:
        issues.append("protocol_lock_version_mismatch")
    integrity = document.get("integrity")
    if not isinstance(integrity, Mapping) or integrity.get("protocolLockDigest") != document_digest(
        dict(document), "protocolLockDigest"
    ):
        issues.append("protocol_lock_digest_mismatch")
    for record in document.get("implementationFiles", []):
        if not isinstance(record, Mapping):
            issues.append("implementation_record_invalid")
            continue
        path = root / str(record.get("path"))
        if not path.is_file() or canonical_source_sha256(path) != record.get("sha256"):
            issues.append(f"implementation_hash_mismatch:{record.get('path')}")
    if document.get("poseGenerator", {}).get("freshPoseParametersRealized") is not False:
        issues.append("fresh_pose_realized_in_lock")
    return sorted(set(issues))


def canonical_source_sha256(path: Path) -> str:
    text = path.read_bytes().decode("utf-8")
    return sha256_bytes(canonical_text_bytes(text))


def document_digest(document: dict[str, Any], field: str) -> str:
    payload = deepcopy(document)
    if field in payload:
        payload[field] = ""
    elif isinstance(payload.get("integrity"), dict):
        payload["integrity"][field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _identity(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    return {
        "path": relative.as_posix(),
        "sha256": sha256_file(path),
        "byteLength": path.stat().st_size,
    }


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _digest_bytes(seed: bytes, class_id: str, field: str) -> bytes:
    return hmac.new(seed, f"{class_id}:{field}".encode(), hashlib.sha256).digest()
