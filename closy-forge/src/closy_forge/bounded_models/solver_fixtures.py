from __future__ import annotations

from math import exp
from typing import Any

from .contracts import SOLVER_FIXTURE_VERSION, canonical_hash, feature_vector, rounded

STEP_COUNT = 180
TIME_STEP_SECONDS = 1.0 / 240.0


def run_project_authored_settle_fixture(features: dict[str, float]) -> dict[str, Any]:
    """Execute a bounded scalar cloth fixture; it is not a production cloth solver."""

    feature_vector(features)
    complexity = features["programPanelComplexity"]
    opening = features["programOpeningRatio"]
    seams = features["programSeamDensity"]
    motion = features["motionAmplitude"]
    shoulder = features["avatarShoulderRatio"]
    hip = features["avatarHipRatio"]
    capture = features["captureQuality"]
    penetration = max(
        0.0,
        features["initialPenetrationMeters"] - 0.35 * features["materialCollisionClearanceMeters"],
    )
    warp = features["materialWarpStiffnessNPerM"]
    weft = features["materialWeftStiffnessNPerM"]
    shear = features["materialShearStiffnessNPerM"]
    bend = features["materialBendStiffnessNm"]
    damping = features["materialDampingRatio"]
    thickness = features["materialThicknessMeters"]
    density = features["materialArealDensityKgM2"]

    stretch_response = 1.0 / (1.0 + (warp + weft) / 720.0)
    shear_response = 1.0 / (1.0 + shear / 150.0)
    bend_response = 1.0 / (1.0 + bend * 520.0)
    clearance = features["materialCollisionClearanceMeters"]

    strain = 0.025 + 0.03 * complexity
    seam_gap = 0.001 + 0.002 * seams
    opening_retention = 1.0
    velocity = motion * (0.04 + 0.05 * complexity)
    energy = velocity * velocity + penetration * 4.0
    maximum_strain = strain
    maximum_seam_gap = seam_gap

    for step in range(STEP_COUNT):
        phase = (step % 24) / 24.0
        forcing = motion * (0.34 + 0.52 * complexity) * (0.72 + 0.28 * phase)
        body_mismatch = abs(shoulder - 1.0) * 0.42 + abs(hip - 1.0) * 0.34
        target_strain = (
            0.018
            + forcing * (0.12 + 0.22 * stretch_response)
            + body_mismatch * 0.11
            + density * 0.025
        )
        relaxation = 0.045 + damping * 0.24
        velocity += (target_strain - strain) * (0.30 + shear_response * 0.16)
        velocity *= max(0.72, 1.0 - relaxation)
        strain += velocity * TIME_STEP_SECONDS * 18.0
        strain = max(0.0, strain)

        correction = clearance * (0.0009 + 0.0014 * (1.0 - stretch_response))
        correction *= 0.75 + 0.25 * capture
        penetration = max(
            0.0,
            penetration * (0.995 + 0.003 * shear_response)
            - correction
            + max(0.0, strain - 0.16) * thickness * 0.04,
        )

        opening_loss = max(0.0, strain - 0.055) * (0.007 + 0.012 * bend_response)
        opening_loss += max(0.0, 0.72 - opening) * 0.0008
        opening_retention = max(0.0, opening_retention - opening_loss)

        seam_target = 0.0012 + seams * 0.005 + strain * (0.018 + 0.016 * shear_response)
        seam_gap += (seam_target - seam_gap) * (0.025 + 0.08 * damping)
        energy = abs(velocity) * 0.42 + penetration * 5.5 + abs(target_strain - strain) * 0.18
        maximum_strain = max(maximum_strain, strain)
        maximum_seam_gap = max(maximum_seam_gap, seam_gap)

    validators = {
        "settled": energy <= 0.016,
        "collisionConverged": penetration <= 0.0012,
        "openingPreserved": opening_retention >= 0.78,
        "strainAccepted": maximum_strain <= 0.22,
        "seamContinuityAccepted": maximum_seam_gap <= 0.009,
        "captureQualityAccepted": capture >= 0.62,
    }
    failures = {
        "settleFailure": not validators["settled"],
        "collisionNonconvergence": not validators["collisionConverged"],
        "openingCollapse": not validators["openingPreserved"],
        "excessiveStrain": not validators["strainAccepted"],
        "seamContinuityRisk": not validators["seamContinuityAccepted"],
        "lowCaptureQuality": not validators["captureQualityAccepted"],
    }
    penalties = (
        min(1.0, energy / 0.04) * 0.18
        + min(1.0, penetration / 0.004) * 0.22
        + min(1.0, max(0.0, 0.9 - opening_retention) / 0.25) * 0.18
        + min(1.0, maximum_strain / 0.32) * 0.18
        + min(1.0, maximum_seam_gap / 0.014) * 0.16
        + (0.08 if capture < 0.62 else 0.0)
    )
    quality_score = max(0.0, min(1.0, 1.0 - penalties))
    result: dict[str, Any] = {
        "fixtureVersion": SOLVER_FIXTURE_VERSION,
        "stepCount": STEP_COUNT,
        "timeStepSeconds": TIME_STEP_SECONDS,
        "metrics": {
            "terminalEnergy": rounded(energy),
            "residualPenetrationMeters": rounded(penetration),
            "openingRetention": rounded(opening_retention),
            "maximumStrain": rounded(maximum_strain),
            "maximumSeamGapMeters": rounded(maximum_seam_gap),
        },
        "deterministicValidators": validators,
        "failureLabels": failures,
        "materialQualityScore": rounded(quality_score),
        "authority": "project_authored_numerical_fixture_validators",
        "productionPhysicalClaim": False,
        "integrity": {"resultHash": ""},
    }
    result["integrity"]["resultHash"] = canonical_hash({**result, "integrity": {"resultHash": ""}})
    return result


def confidence_from_margin(margin: float, *, out_of_domain: bool) -> float:
    if out_of_domain:
        return 0.0
    return rounded(max(0.0, min(0.99, 0.5 + 0.48 * (1.0 - exp(-8.0 * max(0.0, margin))))))
