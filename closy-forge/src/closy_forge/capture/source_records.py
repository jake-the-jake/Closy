from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from closy_forge.contracts.common import COORDINATE_CONVENTION, FIXED_TIMESTAMP
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

SYNTHETIC_CAPTURE_RECORD_VERSION = "closy.synthetic_capture_record.v1"
SYNTHETIC_CAPTURE_RECORD_ID = "capture.synthetic_tshirt_reference_v1"


@dataclass(frozen=True)
class SyntheticCaptureView:
    view_id: str
    label: str
    azimuth_degrees: float
    elevation_degrees: float
    garment_coverage: float
    body_coverage: float
    blur_score: float
    exposure_balance: float
    background_separation: float
    occlusion_fraction: float
    landmark_visibility: float
    scale_confidence: float
    visible_regions: tuple[str, ...]
    occluded_regions: tuple[str, ...]


def build_synthetic_capture_record(
    *,
    garment_id: str = "garment.demo_tshirt.reference_v1",
    garment_class: str = "tshirt",
    avatar_contract_id: str = "avatar.closy_reference_v1",
    seed: int = 101,
) -> dict[str, Any]:
    """Build an immutable no-user-data capture fixture for Phase 2 gates."""

    views = [_view_json(view) for view in synthetic_capture_views()]
    record: dict[str, Any] = {
        "schemaVersion": 1,
        "recordId": SYNTHETIC_CAPTURE_RECORD_ID,
        "recordVersion": SYNTHETIC_CAPTURE_RECORD_VERSION,
        "recordType": "synthetic_fixture_capture",
        "sourceKind": "synthetic_metadata_only",
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "avatarContractId": avatar_contract_id,
        "coordinateConvention": COORDINATE_CONVENTION,
        "privacy": {
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "consentRequired": False,
            "deletionPolicy": "regenerable_fixture_no_user_data",
        },
        "captureSession": {
            "sessionId": "capture_session.synthetic_tshirt_reference_v1",
            "seed": seed,
            "fixedTimestamp": FIXED_TIMESTAMP,
            "sourceDescription": (
                "Deterministic synthetic camera and quality metadata only; no raster "
                "photographs or user imagery are included in Phase 2."
            ),
            "viewCount": len(views),
            "runtimeExternalApis": False,
        },
        "views": views,
        "immutability": {
            "mutable": False,
            "canonicalization": "closy_canonical_json_v1_sort_keys_compact",
            "contentAddressable": True,
            "sourceRecordHash": "",
        },
        "futureEditableArtifacts": {
            "maskRecords": "not_started_phase_02",
            "landmarkCorrections": "not_started_phase_02",
            "userCorrections": "not_started_phase_02",
        },
    }
    record["immutability"]["sourceRecordHash"] = hash_capture_record(record)
    return record


def synthetic_capture_views() -> tuple[SyntheticCaptureView, ...]:
    return (
        SyntheticCaptureView(
            view_id="view.front",
            label="front",
            azimuth_degrees=0.0,
            elevation_degrees=4.0,
            garment_coverage=0.96,
            body_coverage=0.92,
            blur_score=0.97,
            exposure_balance=0.96,
            background_separation=0.94,
            occlusion_fraction=0.04,
            landmark_visibility=0.95,
            scale_confidence=0.96,
            visible_regions=(
                "region.torso.front",
                "region.neck",
                "region.left_sleeve",
                "region.right_sleeve",
                "region.hem.front",
            ),
            occluded_regions=("region.torso.back",),
        ),
        SyntheticCaptureView(
            view_id="view.back",
            label="back",
            azimuth_degrees=180.0,
            elevation_degrees=4.0,
            garment_coverage=0.94,
            body_coverage=0.90,
            blur_score=0.96,
            exposure_balance=0.95,
            background_separation=0.93,
            occlusion_fraction=0.05,
            landmark_visibility=0.93,
            scale_confidence=0.95,
            visible_regions=(
                "region.torso.back",
                "region.neck",
                "region.left_sleeve",
                "region.right_sleeve",
                "region.hem.back",
            ),
            occluded_regions=("region.torso.front",),
        ),
        SyntheticCaptureView(
            view_id="view.left_three_quarter",
            label="left_three_quarter",
            azimuth_degrees=62.0,
            elevation_degrees=5.0,
            garment_coverage=0.90,
            body_coverage=0.88,
            blur_score=0.95,
            exposure_balance=0.95,
            background_separation=0.92,
            occlusion_fraction=0.08,
            landmark_visibility=0.91,
            scale_confidence=0.93,
            visible_regions=(
                "region.torso.front",
                "region.torso.back",
                "region.left_sleeve",
                "region.left_armhole",
                "region.hem.side",
            ),
            occluded_regions=("region.right_sleeve",),
        ),
        SyntheticCaptureView(
            view_id="view.right_three_quarter",
            label="right_three_quarter",
            azimuth_degrees=-62.0,
            elevation_degrees=5.0,
            garment_coverage=0.90,
            body_coverage=0.88,
            blur_score=0.95,
            exposure_balance=0.95,
            background_separation=0.92,
            occlusion_fraction=0.08,
            landmark_visibility=0.91,
            scale_confidence=0.93,
            visible_regions=(
                "region.torso.front",
                "region.torso.back",
                "region.right_sleeve",
                "region.right_armhole",
                "region.hem.side",
            ),
            occluded_regions=("region.left_sleeve",),
        ),
    )


def hash_capture_record(record: dict[str, Any]) -> str:
    payload = capture_record_payload_for_hash(record)
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def capture_record_payload_for_hash(record: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(record)
    immutability = payload.get("immutability")
    if isinstance(immutability, dict):
        immutability["sourceRecordHash"] = ""
    return payload


def _view_json(view: SyntheticCaptureView) -> dict[str, Any]:
    return {
        "viewId": view.view_id,
        "label": view.label,
        "kind": "synthetic_metadata_only",
        "rasterImage": {
            "available": False,
            "path": None,
            "sha256": None,
            "reason": "no_raster_image_in_phase_02",
        },
        "segmentationMask": {
            "available": False,
            "path": None,
            "sha256": None,
            "editableFutureMaskId": f"mask.{view.label}.placeholder",
            "reason": "mask_schema_not_started_phase_02",
        },
        "camera": {
            "projection": "orthographic",
            "azimuthDegrees": view.azimuth_degrees,
            "elevationDegrees": view.elevation_degrees,
            "distanceMeters": 2.6,
            "focalLengthMm": 70.0,
            "sensorWidthMm": 32.0,
            "principalPointNormalized": [0.5, 0.5],
        },
        "qualityMeasurements": {
            "resolutionWidthPx": 1600,
            "resolutionHeightPx": 2200,
            "garmentCoverage": view.garment_coverage,
            "bodyCoverage": view.body_coverage,
            "blurScore": view.blur_score,
            "exposureBalance": view.exposure_balance,
            "backgroundSeparation": view.background_separation,
            "occlusionFraction": view.occlusion_fraction,
            "landmarkVisibility": view.landmark_visibility,
            "scaleConfidence": view.scale_confidence,
        },
        "visibleSemanticRegions": list(view.visible_regions),
        "occludedSemanticRegions": list(view.occluded_regions),
    }
