from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from closy_forge.avatar_variation import (
    AVATAR_CAPABILITY_VERSION,
    DECLARED_RANGES,
    FIT_THRESHOLDS,
    AvatarFitError,
    AvatarMeasurements,
    SyntheticAvatarCase,
    build_collision_samples,
    build_frozen_avatar_suite,
    fit_avatar_patterns,
    measure_collision_samples,
)
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes


def run_evidence(*, base_sha: str, evidence_anchor_sha: str) -> dict[str, Any]:
    suite = build_frozen_avatar_suite()
    reports = [fit_avatar_patterns(case) for case in suite]
    measurement_errors = [_measurement_error(case) for case in suite]
    monotonic = _monotonic_checks()
    rejected = _unsupported_rejections()
    suite_record = [
        {
            "caseId": case.case_id,
            "coverageKind": case.coverage_kind,
            "variedFields": list(case.varied_fields),
            "measurements": asdict(case.measurements),
            "authority": case.measurement_authority,
            "collisionBodyLinkage": case.collision_body_linkage,
            "provenance": case.provenance,
        }
        for case in suite
    ]
    coverage_counts = {
        kind: sum(case.coverage_kind == kind for case in suite)
        for kind in ("baseline", "boundary", "pairwise", "posture")
    }
    return {
        "schemaVersion": 1,
        "evidenceVersion": "closy.synthetic_avatar_fit.evidence.d0.v1",
        "capabilityVersion": AVATAR_CAPABILITY_VERSION,
        "classification": "source-only-project-authored-synthetic-d0",
        "base": {
            "branch": "codex/closy-forge-phase11-prerequisite-reconciliation-v2",
            "sha": base_sha,
        },
        "evidenceAnchorSha": evidence_anchor_sha,
        "suite": {
            "caseCount": len(suite),
            "coverageCounts": coverage_counts,
            "declaredRanges": {
                key: {"minimum": value[0], "maximum": value[1]}
                for key, value in sorted(DECLARED_RANGES.items())
            },
            "fitThresholds": FIT_THRESHOLDS,
            "suiteDigest": sha256_bytes(canonical_dumps(suite_record).encode()),
        },
        "execution": {
            "acceptedFits": sum(report.status.startswith("accepted_") for report in reports),
            "independentOracleCases": len(measurement_errors),
            "maximumIndependentMeasurementError": max(measurement_errors),
            "minimumFitConfidence": min(report.fit_confidence for report in reports),
            "minimumBodyClearanceMeters": min(min(report.clearance.values()) for report in reports),
            "maximumOpeningPlacementErrorMeters": max(
                max(report.opening_placement.values()) for report in reports
            ),
            "monotonicChecks": monotonic,
            "unsupportedRejections": rejected,
            "fitDigestAggregate": sha256_bytes(
                "\n".join(report.fit_digest for report in reports).encode()
            ),
            "containsPrivateData": any(report.contains_private_data for report in reports),
            "containsStableIdentity": any(report.contains_stable_identity for report in reports),
            "collisionBodyLinkages": sorted({report.collision_body_linkage for report in reports}),
        },
        "truth": {
            "projectAuthoredSyntheticD0Executed": True,
            "phase13GlobalAcceptance": False,
            "multilayerOutfitAcceptance": False,
            "multilayerBlocker": "layer_collision_and_post_z2_integration_not_available",
            "privateUserExecuted": False,
            "personalisedUserClaim": False,
            "licensedBodyExecuted": False,
            "p1Executed": False,
            "humanReviewExecuted": False,
        },
    }


def _measurement_error(case: SyntheticAvatarCase) -> float:
    measured = measure_collision_samples(build_collision_samples(case.measurements))
    expected = case.measurements
    errors = [
        abs(measured.height_m - expected.height_m),
        abs(measured.shoulder_width_m - expected.shoulder_width_m),
        abs(measured.chest_circumference_m - expected.chest_circumference_m),
        abs(measured.waist_circumference_m - expected.waist_circumference_m),
        abs(measured.hip_circumference_m - expected.hip_circumference_m),
        abs(measured.arm_length_m - expected.arm_length_m),
        abs(measured.leg_length_m - expected.leg_length_m),
        abs(measured.torso_length_m - expected.torso_length_m),
    ]
    return round(max(errors), 12)


def _monotonic_checks() -> dict[str, bool]:
    fields = {
        "height_m": ("top_parameters", "bodyLengthMeters"),
        "shoulder_width_m": ("top_parameters", "shoulderHalfWidthMeters"),
        "chest_circumference_m": ("top_parameters", "halfChestWidthMeters"),
        "waist_circumference_m": ("trouser_parameters", "halfWaistWidthMeters"),
        "hip_circumference_m": ("trouser_parameters", "halfHipWidthMeters"),
        "arm_length_m": ("top_parameters", "sleeveLengthMeters"),
        "leg_length_m": ("trouser_parameters", "outseamLengthMeters"),
        "torso_length_m": ("top_parameters", "bodyLengthMeters"),
        "shape_chest_depth": ("top_parameters", "frontDepthAllowanceMeters"),
        "shape_hip_depth": ("trouser_parameters", "seatDepthAllowanceMeters"),
    }
    result: dict[str, bool] = {}
    baseline = AvatarMeasurements()
    for field, (group, output) in fields.items():
        minimum, maximum = DECLARED_RANGES[field]
        low = fit_avatar_patterns(
            SyntheticAvatarCase(
                f"evidence.{field}.low",
                replace(baseline, **{field: minimum}),
                "boundary",
                (field,),
            )
        )
        high = fit_avatar_patterns(
            SyntheticAvatarCase(
                f"evidence.{field}.high",
                replace(baseline, **{field: maximum}),
                "boundary",
                (field,),
            )
        )
        result[field] = getattr(high, group)[output] > getattr(low, group)[output]
    return result


def _unsupported_rejections() -> dict[str, str]:
    cases = {
        "height": replace(AvatarMeasurements(), height_m=1.2),
        "verticalProportion": replace(
            AvatarMeasurements(), height_m=1.62, leg_length_m=1.10, torso_length_m=0.68
        ),
    }
    outcomes: dict[str, str] = {}
    for name, measurements in cases.items():
        try:
            fit_avatar_patterns(
                SyntheticAvatarCase(f"unsupported.{name}", measurements, "boundary", (name,))
            )
        except AvatarFitError as error:
            outcomes[name] = error.code
        else:
            outcomes[name] = "not_rejected"
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--evidence-anchor-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_canonical_json(
        args.output,
        run_evidence(base_sha=args.base_sha, evidence_anchor_sha=args.evidence_anchor_sha),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
