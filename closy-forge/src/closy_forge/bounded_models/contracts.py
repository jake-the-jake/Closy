from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any, cast

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

DATASET_VERSION = "closy.phase14.solver_fixture_dataset.d0.v1"
MODEL_VERSION = "closy.phase14.bounded_advisory_models.d0.v1"
SOLVER_FIXTURE_VERSION = "closy.phase14.project_authored_settle_fixture.d0.v1"
TRAINING_CONFIG_VERSION = "closy.phase14.training_config.d0.v1"

FEATURE_NAMES = (
    "programPanelComplexity",
    "programOpeningRatio",
    "programSeamDensity",
    "avatarShoulderRatio",
    "avatarHipRatio",
    "motionAmplitude",
    "captureQuality",
    "initialPenetrationMeters",
    "materialWarpStiffnessNPerM",
    "materialWeftStiffnessNPerM",
    "materialShearStiffnessNPerM",
    "materialBendStiffnessNm",
    "materialDampingRatio",
    "materialThicknessMeters",
    "materialCollisionClearanceMeters",
    "materialArealDensityKgM2",
)

FAILURE_TARGETS = (
    "settleFailure",
    "collisionNonconvergence",
    "openingCollapse",
    "excessiveStrain",
    "seamContinuityRisk",
    "lowCaptureQuality",
)

FORBIDDEN_FEATURE_TOKENS = (
    "accepted",
    "collapse",
    "converged",
    "failure",
    "final",
    "label",
    "outcome",
    "residual",
    "risk",
    "settled",
    "target",
    "validator",
)


def validate_feature_snapshot(features: Mapping[str, object]) -> list[str]:
    issues: list[str] = []
    if tuple(features) != FEATURE_NAMES:
        issues.append("feature_axis_contract_invalid")
    for name, value in features.items():
        lowered = name.lower()
        if any(token in lowered for token in FORBIDDEN_FEATURE_TOKENS):
            issues.append(f"post_outcome_feature_forbidden:{name}")
        if isinstance(value, bool) or not isinstance(value, int | float):
            issues.append(f"feature_not_numeric:{name}")
        elif not isfinite(float(value)):
            issues.append(f"feature_not_finite:{name}")
    return sorted(set(issues))


def feature_vector(features: Mapping[str, object]) -> list[float]:
    issues = validate_feature_snapshot(features)
    if issues:
        raise ValueError(issues[0])
    return [float(cast(int | float, features[name])) for name in FEATURE_NAMES]


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


def rounded(value: float) -> float:
    return round(float(value), 12)
