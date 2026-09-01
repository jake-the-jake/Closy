from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

LOCK_VERSION = "closy.d0_core_runtime_c3.protocol_lock.v4"
LOCK_RELATIVE = Path("fixtures/d0_core_runtime_c3_v4/protocol_lock.json")

DEVELOPMENT_STATES = [
    {
        "stateId": "development_identity",
        "leftArmLiftDegrees": 0,
        "rightArmLiftDegrees": 0,
        "torsoBendDegrees": 0,
        "torsoTwistDegrees": 0,
        "materialStretchU": 1.0,
    },
    {
        "stateId": "development_small_lift",
        "leftArmLiftDegrees": 12,
        "rightArmLiftDegrees": 0,
        "torsoBendDegrees": 0,
        "torsoTwistDegrees": 0,
        "materialStretchU": 1.0,
    },
    {
        "stateId": "development_small_bend",
        "leftArmLiftDegrees": 0,
        "rightArmLiftDegrees": 0,
        "torsoBendDegrees": 5,
        "torsoTwistDegrees": 0,
        "materialStretchU": 1.0,
    },
    {
        "stateId": "development_small_stretch",
        "leftArmLiftDegrees": 0,
        "rightArmLiftDegrees": 0,
        "torsoBendDegrees": 0,
        "torsoTwistDegrees": 0,
        "materialStretchU": 1.01,
    },
]

HELD_OUT_STATES = [
    {
        "stateId": "neutral",
        "leftArmLiftDegrees": 0,
        "rightArmLiftDegrees": 0,
        "torsoBendDegrees": 0,
        "torsoTwistDegrees": 0,
        "materialStretchU": 1.0,
    },
    {
        "stateId": "left_arm_lift_47",
        "leftArmLiftDegrees": 47,
        "rightArmLiftDegrees": 0,
        "torsoBendDegrees": 0,
        "torsoTwistDegrees": 0,
        "materialStretchU": 1.0,
    },
    {
        "stateId": "right_arm_lift_49",
        "leftArmLiftDegrees": 0,
        "rightArmLiftDegrees": 49,
        "torsoBendDegrees": 0,
        "torsoTwistDegrees": 0,
        "materialStretchU": 1.0,
    },
    {
        "stateId": "bilateral_arm_lift_46",
        "leftArmLiftDegrees": 46,
        "rightArmLiftDegrees": 46,
        "torsoBendDegrees": 0,
        "torsoTwistDegrees": 0,
        "materialStretchU": 1.0,
    },
    {
        "stateId": "torso_bend_17",
        "leftArmLiftDegrees": 0,
        "rightArmLiftDegrees": 0,
        "torsoBendDegrees": 17,
        "torsoTwistDegrees": 0,
        "materialStretchU": 1.0,
    },
    {
        "stateId": "torso_twist_23",
        "leftArmLiftDegrees": 0,
        "rightArmLiftDegrees": 0,
        "torsoBendDegrees": 0,
        "torsoTwistDegrees": 23,
        "materialStretchU": 1.0,
    },
    {
        "stateId": "anisotropic_panel_stretch_5pct",
        "leftArmLiftDegrees": 0,
        "rightArmLiftDegrees": 0,
        "torsoBendDegrees": 0,
        "torsoTwistDegrees": 0,
        "materialStretchU": 1.05,
    },
    {
        "stateId": "combined_bend_twist",
        "leftArmLiftDegrees": 45,
        "rightArmLiftDegrees": 48,
        "torsoBendDegrees": 16,
        "torsoTwistDegrees": 21,
        "materialStretchU": 1.05,
    },
]


def build_protocol_lock(root: Path, sentinel: dict[str, Any]) -> dict[str, Any]:
    implementation_paths = (
        "src/closy_forge/core_runtime_c3_v4/candidate_deformation.py",
        "src/closy_forge/core_runtime_c3_v4/oracle.py",
        "src/closy_forge/core_runtime_c3_v4/evaluator.py",
        "src/closy_forge/core_runtime_c3_v4/reproducibility.py",
    )
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "lockVersion": LOCK_VERSION,
        "state": "frozen_before_held_out_pose_mount",
        "sentinelManifestDigest": sentinel["integrity"]["sentinelManifestDigest"],
        "candidateId": sentinel["candidateId"],
        "candidatePackageDigest": sentinel["candidatePackageDigest"],
        "bindingAlgorithm": "persisted_sim_triangle_barycentric_v1",
        "bindingStrategyCount": 1,
        "maximumHeldOutBindingAttempts": 1,
        "heldOutBindingAttemptsConsumed": 0,
        "failureStopRule": (
            "first_held_out_attempt_is_final_append_only_no_tuning_retry_or_" "strategy_change"
        ),
        "oracle": {
            "version": "closy.c3.independent_material_shell_oracle.v4",
            "readsCandidateBindingWeights": False,
            "callsCandidateReconstruction": False,
            "directDenseMaterialPanelCoordinateDeformation": True,
        },
        "implementationFiles": [
            {"path": path, "sha256": sha256_file(root / path)} for path in implementation_paths
        ],
        "developmentStates": DEVELOPMENT_STATES,
        "heldOutStates": HELD_OUT_STATES,
        "thresholds": {
            "maximumBindingReconstructionErrorMeters": 0.0001,
            "maximumSeamCrackMeters": 0.002,
            "maximumTangentialSeamSlidingMeters": 0.005,
            "maximumInversionCount": 0,
            "requiredHeldOutPassCount": 8,
            "requiredHeldOutStateCount": 8,
            "maximumNormalLengthError": 0.00001,
            "maximumTangentLengthError": 0.00001,
            "maximumAbsoluteNormalTangentDot": 0.00001,
            "maximumTopologyHashMismatchCount": 0,
            "maximumDeterministicCanonicalOutputMismatchCount": 0,
            "maximumRuntimeSecondsPerPose": 2.0,
            "maximumPeakMemoryMiB": 512.0,
        },
        "applicability": {
            "scope": "pre_topology_exact_sentinel_non_physical_binding_gate",
            "densePathRequired": True,
            "conventionalFallbackPathRequired": True,
            "seamAndOpeningSemanticsRequired": True,
            "physicalClothImplied": False,
            "phy1Implied": False,
            "z2Implied": False,
        },
        "corruptionControls": [
            "binding_weight_mutation_must_fail_candidate_comparison",
            "oracle_target_hash_must_remain_unchanged",
            "binding_and_topology_hash_mismatch_fail_closed",
        ],
        "integrity": {"protocolLockDigest": ""},
    }
    copied = deepcopy(payload)
    copied["integrity"]["protocolLockDigest"] = ""
    payload["integrity"]["protocolLockDigest"] = sha256_bytes(
        canonical_dumps(copied).encode("utf-8")
    )
    return payload
