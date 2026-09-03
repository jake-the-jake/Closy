from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .common import canonical_digest, read_mapping

PROTOCOL_VERSION = "closy.capture_camera_material_engineering.development.v1"
DEFAULT_PROTOCOL = (
    Path(__file__).resolve().parents[3]
    / "fixtures/capture_engineering_v1/development_acceptance_manifest.json"
)


def load_frozen_protocol(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    protocol = read_mapping(path)
    issues = validate_protocol(protocol)
    if issues:
        raise ValueError("invalid_capture_protocol:" + ";".join(issues))
    return protocol


def validate_protocol(protocol: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if protocol.get("protocolVersion") != PROTOCOL_VERSION:
        issues.append("protocol_version_invalid")
    if protocol.get("evidenceClass") != "project_authored_development_only":
        issues.append("evidence_class_invalid")
    if protocol.get("frozenBeforeValidation") is not True:
        issues.append("protocol_not_frozen")
    counts = _mapping(protocol.get("counts"))
    expected = {
        "uniqueCaptureSessions": 80,
        "primaryMode": {"A": 20, "B": 16, "C": 16, "D": 12, "E": 16},
        "sceneCondition": {"flat": 18, "hung": 18, "unknown": 16, "worn": 28},
        "acquisitionPattern": {
            "guided_multi_image": 34,
            "guided_video": 12,
            "single_image": 34,
        },
        "family": {"simple_skirt": 24, "sleeveless_top": 24, "tshirt": 32},
        "split": {"development": 60, "validation": 20},
        "renderer": {"cpu_triangle_zbuffer": 40, "independent_ray_triangle": 40},
        "avatar": {"fixed_avatar_alpha": 40, "fixed_avatar_beta": 40},
        "avatarShapeFamily": {
            "fixed_alpha_development": 40,
            "fixed_beta_development": 20,
            "fixed_beta_holdout": 20,
        },
        "appearanceFamily": {
            "plain_development": 40,
            "print_beta_development": 20,
            "print_beta_holdout": 20,
        },
        "rendererCameraFamily": {
            "cpu_zbuffer_development": 40,
            "ray_triangle_development": 20,
            "ray_triangle_holdout": 20,
        },
        "poseFamily": {
            "neutral_development": 40,
            "varied_development": 20,
            "varied_holdout": 20,
        },
    }
    for key, value in expected.items():
        if counts.get(key) != value:
            issues.append(f"count_{key}_invalid")
    denominators = _mapping(protocol.get("denominators"))
    minimums = {
        "encodedVideoClips": 12,
        "sourceFramesPerVideo": 24,
        "heldOutIdentityGroups": 20,
        "pixelDrivenSleevelessIdentities": 8,
        "pixelDrivenSimpleSkirtIdentities": 8,
        "corruptionAttempts": 16,
    }
    for key, minimum in minimums.items():
        value = denominators.get(key)
        if not isinstance(value, int) or value < minimum:
            issues.append(f"denominator_{key}_below_minimum")
    grouping = _mapping(protocol.get("grouping"))
    if grouping.get("partitionKey") != "identityGroupId":
        issues.append("identity_partition_key_invalid")
    if grouping.get("derivativesRemainCoPartitioned") is not True:
        issues.append("derivative_partition_policy_missing")
    failure_states = set(map(str, _sequence(protocol.get("failureAccounting"))))
    required_failures = {
        "decode_failure",
        "qc_rejection",
        "abstention",
        "compile_failure",
        "topology_failure",
        "solver_failure",
        "invalid_package",
    }
    if not required_failures.issubset(failure_states):
        issues.append("failure_accounting_incomplete")
    unsupported = set(map(str, _sequence(protocol.get("unsupportedEvidenceTiers"))))
    if unsupported != {"future_licensed_public", "future_private_authorized"}:
        issues.append("unsupported_evidence_tiers_invalid")
    if not _mapping(protocol.get("thresholds")):
        issues.append("thresholds_missing")
    if not _mapping(protocol.get("baselines")):
        issues.append("baselines_missing")
    if not _mapping(protocol.get("stoppingRules")):
        issues.append("stopping_rules_missing")
    if not _mapping(protocol.get("resourceLimits")):
        issues.append("resource_limits_missing")
    if not _sequence(protocol.get("allowedContestantMetadata")):
        issues.append("allowed_metadata_missing")
    digest = protocol.get("protocolDigest")
    if not isinstance(digest, str) or digest != canonical_digest(dict(protocol), "protocolDigest"):
        issues.append("protocol_digest_invalid")
    return sorted(set(issues))


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, str | bytes) else ()
