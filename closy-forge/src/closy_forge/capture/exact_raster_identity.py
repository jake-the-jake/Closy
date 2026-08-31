from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.capture.raster_sources import RasterIngestResult, build_raster_fixture_records
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.visual_understanding.tshirt_observations import (
    REQUIRED_TSHIRT_VISUAL_LANDMARKS,
    build_tshirt_visual_observations_from_ingested_rasters,
    validate_evaluator_only_ingested_raster,
)

EXACT_RASTER_LINEAGE_VERSION = "closy.d0_exact_raster_lineage.v2"
EXACT_RASTER_QUALITY_VERSION = "closy.d0_exact_raster_quality.v2"


class ExactRasterIdentityError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def load_exact_raster_manifest(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ExactRasterIdentityError("exact_manifest_invalid")
    if value.get("manifestId") != "exact_public_tshirt_front_rear_eval_v2":
        raise ExactRasterIdentityError("exact_manifest_identity_invalid")
    policy = value.get("policy")
    boundary = value.get("informationBoundary")
    if not isinstance(policy, dict) or not isinstance(boundary, dict):
        raise ExactRasterIdentityError("exact_manifest_policy_missing")
    required_false = (
        "allowTrainingUse",
        "allowExternalApis",
        "allowNetwork",
        "containsUserImagery",
        "containsRealPerson",
        "containsBiometricIdentity",
        "genericFailureUploadRawBytes",
    )
    if any(policy.get(key) is not False for key in required_false):
        raise ExactRasterIdentityError("exact_manifest_policy_unsafe")
    if policy.get("publicFixtureException") is not True:
        raise ExactRasterIdentityError("exact_manifest_public_exception_missing")
    if boundary.get("fitRoles") != ["front", "rear"] or boundary.get("evaluatorOnlyRoles") != [
        "evaluator_only_three_quarter"
    ]:
        raise ExactRasterIdentityError("exact_manifest_information_boundary_invalid")
    fixtures = value.get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) != 3:
        raise ExactRasterIdentityError("exact_manifest_fixture_inventory_invalid")
    if [item.get("role") for item in fixtures if isinstance(item, dict)] != [
        "front",
        "rear",
        "evaluator_only_three_quarter",
    ]:
        raise ExactRasterIdentityError("exact_manifest_role_order_invalid")
    return value


def build_exact_raster_lineage(
    *, manifest_path: Path, input_root: Path, threshold_path: Path
) -> dict[str, Any]:
    manifest = load_exact_raster_manifest(manifest_path)
    thresholds = read_json(threshold_path)
    if not isinstance(thresholds, dict) or thresholds.get("registryId") != (
        "closy.d0_exact_raster_quality_thresholds.v2"
    ):
        raise ExactRasterIdentityError("exact_quality_thresholds_invalid")
    ingest = build_raster_fixture_records(manifest_path=manifest_path, input_root=input_root)
    observations = build_tshirt_visual_observations_from_ingested_rasters(
        manifest=manifest,
        input_root=input_root,
        private_record=ingest.private_record,
        normalization_record=ingest.normalization_record,
    )
    evaluator = validate_evaluator_only_ingested_raster(
        manifest=manifest,
        input_root=input_root,
        private_record=ingest.private_record,
    )
    quality = evaluate_exact_raster_quality(
        manifest=manifest,
        ingest=ingest,
        observations=observations,
        thresholds=thresholds,
    )
    lineage: dict[str, Any] = {
        "schemaVersion": 1,
        "lineageVersion": EXACT_RASTER_LINEAGE_VERSION,
        "classification": "project_authored_public_synthetic_d0",
        "selectedIdentity": {
            "garmentId": manifest["garmentId"],
            "avatarContractId": manifest["avatarContractId"],
        },
        "manifest": {
            "manifestId": manifest["manifestId"],
            "manifestHash": _hash_document(manifest),
            "sourceFixtureSetHash": read_json(input_root / "publication_provenance.json")[
                "fixtureSetHash"
            ],
        },
        "sourceJoins": [
            {
                "role": fixture["role"],
                "viewId": fixture["viewId"],
                "sourceByteSha256": fixture["expectedSha256"],
                "decodedContentSha256": fixture["expectedDecodedContentHash"],
                "cameraHash": _hash_document(fixture["camera"]),
                "fitPermission": fixture["fitPermission"],
            }
            for fixture in manifest["fixtures"]
        ],
        "privateRegistry": {
            "sourceRecordId": ingest.private_record["recordId"],
            "sourceRecordHash": ingest.private_record["integrity"]["sourceRecordHash"],
            "normalizationRecordId": ingest.normalization_record["normalizationRecordId"],
            "normalizationRecordHash": ingest.normalization_record["integrity"][
                "normalizationRecordHash"
            ],
            "separateFromPortableOutput": True,
        },
        "portable": {
            "portableSourceSummaryId": ingest.portable_source_summary["portableSourceSummaryId"],
            "portableSourceSummaryHash": _hash_document(ingest.portable_source_summary),
            "privacyReportHash": _hash_document(ingest.privacy_report),
            "rawBytesCopied": False,
            "privatePathsOrFingerprintsIncluded": False,
        },
        "quality": {
            "legacyV1Status": ingest.quality_report["overallStatus"],
            "exactV2Status": quality["overallStatus"],
            "exactV2Hash": quality["integrity"]["qualityReportHash"],
            "thresholdRegistryHash": _hash_document(thresholds),
        },
        "observations": {
            "visualUnderstandingId": observations["visualUnderstandingId"],
            "visualRecordHash": observations["integrity"]["visualRecordHash"],
            "fitRoles": observations["fitInputRoles"],
            "pixelDerivedViewCount": observations["aggregate"]["pixelDerivedViewCount"],
        },
        "evaluatorOnly": evaluator,
        "claims": {
            "frontRearFilesOpenedAndDecoded": True,
            "frontRearJoinedToSelectedIdentity": True,
            "qualityExecuted": True,
            "evaluatorViewWithheldFromFit": True,
            "fixtureRendererCalledDuringIngestionOrObservation": False,
            "privateUserEvidence": False,
            "learnedAiEvidence": False,
            "realPhotoEvidence": False,
            "productEvidence": False,
        },
        "integrity": {"lineageHash": ""},
    }
    lineage["integrity"]["lineageHash"] = _hash_document(lineage, "lineageHash")
    return {
        "manifest": manifest,
        "thresholds": thresholds,
        "ingest": ingest,
        "observations": observations,
        "evaluatorOnly": evaluator,
        "quality": quality,
        "lineage": lineage,
    }


def evaluate_exact_raster_quality(
    *,
    manifest: dict[str, Any],
    ingest: RasterIngestResult,
    observations: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    fixtures = manifest["fixtures"]
    accepted = ingest.private_record["acceptedSources"]
    fit_sources = accepted[:2]
    view_by_id = {str(view["viewId"]): view for view in observations["views"]}
    checks: list[dict[str, Any]] = []

    roles = [str(item["role"]) for item in fixtures]
    checks.append(_check("view_roles", roles == ["front", "rear", "evaluator_only_three_quarter"]))
    decoded_hashes = [str(source["decodedContentSha256"]) for source in accepted]
    checks.append(_check("view_diversity", len(decoded_hashes) == len(set(decoded_hashes))))

    view_metrics: list[dict[str, Any]] = []
    for fixture, source in zip(fixtures[:2], fit_sources, strict=True):
        stats = source["pixelStats"]
        observation = view_by_id[str(fixture["viewId"])]
        occlusion = next(
            (
                float(mask["pixelCountFraction"])
                for mask in observation["masks"]
                if mask["semanticId"] == "component.occlusion_uncertainty"
            ),
            0.0,
        )
        observed_landmarks = {str(item["id"]) for item in observation["landmarks"]}
        landmark_visibility = len(observed_landmarks & set(REQUIRED_TSHIRT_VISUAL_LANDMARKS)) / len(
            REQUIRED_TSHIRT_VISUAL_LANDMARKS
        )
        focus_confidence = min(1.0, float(stats["sharpnessScore"]) / 0.04)
        exposure_balance = 1.0 - float(stats["combinedClipFraction"])
        colour_reliability = min(1.0, exposure_balance * (0.8 + float(stats["luminanceStdDev"])))
        metrics = {
            "role": fixture["role"],
            "foregroundCoverage": float(stats["foregroundCoverage"]),
            "rawSharpnessScore": float(stats["sharpnessScore"]),
            "focusConfidence": round(focus_confidence, 6),
            "exposureBalance": round(exposure_balance, 6),
            "clippedFraction": float(stats["combinedClipFraction"]),
            "occlusionFraction": round(occlusion, 6),
            "landmarkVisibility": round(landmark_visibility, 6),
            "scaleConfidence": 1.0,
            "colourReliability": round(colour_reliability, 6),
        }
        view_metrics.append(metrics)
        checks.extend(
            [
                _range_check(
                    f"{fixture['role']}_foreground_coverage",
                    metrics["foregroundCoverage"],
                    float(thresholds["minimumForegroundCoverage"]),
                    float(thresholds["maximumForegroundCoverage"]),
                ),
                _minimum_check(
                    f"{fixture['role']}_focus",
                    metrics["focusConfidence"],
                    float(thresholds["minimumSharpness"]),
                ),
                _minimum_check(
                    f"{fixture['role']}_exposure",
                    metrics["exposureBalance"],
                    float(thresholds["minimumExposureBalance"]),
                ),
                _maximum_check(
                    f"{fixture['role']}_clipping",
                    metrics["clippedFraction"],
                    float(thresholds["maximumClippedFraction"]),
                ),
                _maximum_check(
                    f"{fixture['role']}_occlusion",
                    metrics["occlusionFraction"],
                    float(thresholds["maximumOcclusionFraction"]),
                ),
                _minimum_check(
                    f"{fixture['role']}_landmarks",
                    metrics["landmarkVisibility"],
                    float(thresholds["minimumLandmarkVisibility"]),
                ),
                _minimum_check(
                    f"{fixture['role']}_scale",
                    metrics["scaleConfidence"],
                    float(thresholds["minimumScaleConfidence"]),
                ),
                _minimum_check(
                    f"{fixture['role']}_colour",
                    metrics["colourReliability"],
                    float(thresholds["minimumColourReliability"]),
                ),
            ]
        )
    coverage = [float(item["foregroundCoverage"]) for item in view_metrics]
    spread = max(coverage) - min(coverage)
    checks.append(
        _maximum_check(
            "cross_view_garment_consistency",
            spread,
            float(thresholds["maximumCrossViewCoverageSpread"]),
        )
    )
    failed = [check["checkId"] for check in checks if check["status"] != "pass"]
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "qualityVersion": EXACT_RASTER_QUALITY_VERSION,
        "thresholdRegistryId": thresholds["registryId"],
        "thresholdRegistryHash": _hash_document(thresholds),
        "sourceRecordHash": ingest.private_record["integrity"]["sourceRecordHash"],
        "visualRecordHash": observations["integrity"]["visualRecordHash"],
        "legacyV1Status": ingest.quality_report["overallStatus"],
        "legacyV1Disposition": "historical_generic_resolution_profile_not_used_for_exact_d0_gate",
        "overallStatus": "pass" if not failed else "fail",
        "viewMetrics": view_metrics,
        "crossViewCoverageSpread": round(spread, 6),
        "checks": checks,
        "failedChecks": failed,
        "inputMode": manifest["inputMode"],
        "cameraAndScaleAssumptionsPersisted": True,
        "integrity": {"qualityReportHash": ""},
    }
    report["integrity"]["qualityReportHash"] = _hash_document(report, "qualityReportHash")
    return report


def build_exact_capture_record(lineage_result: dict[str, Any]) -> dict[str, Any]:
    manifest = lineage_result["manifest"]
    private = lineage_result["ingest"].private_record
    record: dict[str, Any] = {
        "schemaVersion": 1,
        "recordId": "capture.exact_public_tshirt_front_rear_eval_v2",
        "recordType": "exact_project_authored_public_raster_capture",
        "garmentId": manifest["garmentId"],
        "garmentClass": manifest["garmentClass"],
        "avatarContractId": manifest["avatarContractId"],
        "privacy": {
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "allowExternalApis": False,
            "allowTrainingUse": False,
        },
        "views": [
            {
                "viewId": fixture["viewId"],
                "label": fixture["label"],
                "role": fixture["role"],
                "camera": deepcopy(fixture["camera"]),
            }
            for fixture in manifest["fixtures"]
            if fixture["role"] in {"front", "rear"}
        ],
        "immutability": {
            "mutable": False,
            "sourceRecordHash": private["integrity"]["sourceRecordHash"],
        },
    }
    return record


def _check(check_id: str, passed: bool) -> dict[str, Any]:
    return {"checkId": check_id, "status": "pass" if passed else "fail"}


def _minimum_check(check_id: str, value: float, threshold: float) -> dict[str, Any]:
    return {
        **_check(check_id, value >= threshold),
        "value": value,
        "operation": "greater_or_equal",
        "threshold": threshold,
    }


def _maximum_check(check_id: str, value: float, threshold: float) -> dict[str, Any]:
    return {
        **_check(check_id, value <= threshold),
        "value": value,
        "operation": "less_or_equal",
        "threshold": threshold,
    }


def _range_check(check_id: str, value: float, minimum: float, maximum: float) -> dict[str, Any]:
    return {
        **_check(check_id, minimum <= value <= maximum),
        "value": value,
        "operation": "inclusive_range",
        "minimum": minimum,
        "maximum": maximum,
    }


def _hash_document(value: dict[str, Any], blank_key: str | None = None) -> str:
    payload = deepcopy(value)
    if blank_key is not None:
        payload["integrity"][blank_key] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
