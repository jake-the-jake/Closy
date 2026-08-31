from __future__ import annotations

from pathlib import Path
from typing import Any

from closy_forge.capture.raster_sources import inspect_raster
from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.raster import encode_png_rgba
from closy_forge.visual_understanding.raster_parser import render_project_authored_tshirt_rgba

D0_RASTER_PUBLICATION_VERSION = "closy.d0_exact_raster_publication.v2"
D0_RASTER_MANIFEST_ID = "exact_public_tshirt_front_rear_eval_v2"
GARMENT_ID = "garment.demo_tshirt.reference_v1"
AVATAR_CONTRACT_ID = "avatar.closy_reference_v1"
WIDTH = 128
HEIGHT = 160

_VIEW_SPECS: tuple[dict[str, Any], ...] = (
    {
        "fixtureId": "d0_tshirt_exact_front_v2",
        "viewId": "view.front",
        "label": "front",
        "role": "front",
        "fitPermission": "front_rear_fit_allowed",
        "azimuthDegrees": 0.0,
        "elevationDegrees": 4.0,
    },
    {
        "fixtureId": "d0_tshirt_exact_rear_v2",
        "viewId": "view.rear",
        "label": "back",
        "role": "rear",
        "fitPermission": "front_rear_fit_allowed",
        "azimuthDegrees": 180.0,
        "elevationDegrees": 4.0,
    },
    {
        "fixtureId": "d0_tshirt_exact_evaluator_three_quarter_v2",
        "viewId": "view.evaluator_left_three_quarter",
        "label": "left_three_quarter",
        "role": "evaluator_only_three_quarter",
        "fitPermission": "evaluator_only_after_prediction_freeze",
        "azimuthDegrees": 62.0,
        "elevationDegrees": 5.0,
    },
)


def publish_exact_d0_raster_fixture(output_dir: Path) -> dict[str, Any]:
    """Publish immutable D0 source bytes; this function is never used by contenders."""

    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    fixtures: list[dict[str, Any]] = []
    for spec in _VIEW_SPECS:
        relative_path = f"images/{spec['role']}.png"
        path = output_dir / relative_path
        rgba = render_project_authored_tshirt_rgba(WIDTH, HEIGHT, label=str(spec["label"]))
        path.write_bytes(encode_png_rgba(WIDTH, HEIGHT, rgba))
        audit = inspect_raster(path, declared_mime="image/png")
        fixtures.append(
            {
                **spec,
                "relativePath": relative_path,
                "declaredMime": "image/png",
                "expectedSha256": audit["sourceByteSha256"],
                "expectedDecodedContentHash": audit["decodedContentSha256"],
                "decodedPixelHash": audit["pixelHash"],
                "decodedDimensions": audit["decodedDimensions"],
                "colourSpace": "srgb_rgba8_unpremultiplied",
                "rightsClassification": "not_required_project_fixture",
                "publicRightsClass": "project_authored_public_synthetic_d0",
                "camera": {
                    "projection": "orthographic",
                    "azimuthDegrees": spec["azimuthDegrees"],
                    "elevationDegrees": spec["elevationDegrees"],
                    "distanceMeters": 2.6,
                    "focalLengthMm": 70.0,
                    "sensorWidthMm": 32.0,
                    "principalPointNormalized": [0.5, 0.5],
                    "scaleAssumption": "fixed_avatar_height_1_72_m",
                },
            }
        )

    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "manifestId": D0_RASTER_MANIFEST_ID,
        "publicationVersion": D0_RASTER_PUBLICATION_VERSION,
        "profile": "synthetic_fixture_raster_v1",
        "approvedFixtureRootId": "committed_project_authored_d0_exact_raster_v2",
        "garmentId": GARMENT_ID,
        "garmentClass": "tshirt",
        "avatarContractId": AVATAR_CONTRACT_ID,
        "inputMode": "exact_decoded_public_png",
        "policy": {
            "reconstructionConsent": "not_required_project_fixture",
            "rightsClassification": "not_required_project_fixture",
            "publicFixtureException": True,
            "allowTrainingUse": False,
            "allowExternalApis": False,
            "allowNetwork": False,
            "containsUserImagery": False,
            "containsRealPerson": False,
            "containsBiometricIdentity": False,
            "retentionPolicy": "generated_fixture_ephemeral",
            "genericFailureUploadRawBytes": False,
        },
        "informationBoundary": {
            "fitRoles": ["front", "rear"],
            "evaluatorOnlyRoles": ["evaluator_only_three_quarter"],
            "targetParametersInMetadata": False,
            "targetParametersInIds": False,
            "targetParametersInFilenames": False,
            "fixtureGeneratorMountedIntoContenders": False,
            "evaluatorPixelsMountedBeforePredictionFreeze": False,
        },
        "fixtures": fixtures,
    }
    write_canonical_json(output_dir / "fixture_manifest.json", manifest)

    thresholds = {
        "schemaVersion": 1,
        "registryId": "closy.d0_exact_raster_quality_thresholds.v2",
        "publicationVersion": D0_RASTER_PUBLICATION_VERSION,
        "minimumForegroundCoverage": 0.10,
        "maximumForegroundCoverage": 0.70,
        "minimumSharpness": 0.05,
        "minimumExposureBalance": 0.70,
        "maximumClippedFraction": 0.20,
        "maximumOcclusionFraction": 0.18,
        "maximumCrossViewCoverageSpread": 0.20,
        "minimumLandmarkVisibility": 0.70,
        "minimumScaleConfidence": 0.80,
        "minimumColourReliability": 0.70,
        "requiredFitRoles": ["front", "rear"],
        "requiredEvaluatorRoles": ["evaluator_only_three_quarter"],
        "calibrationSource": "pre_fit_analytic_and_bp52_bp53_d0_thresholds",
    }
    write_canonical_json(output_dir / "quality_thresholds.json", thresholds)

    publication = {
        "schemaVersion": 1,
        "publicationVersion": D0_RASTER_PUBLICATION_VERSION,
        "manifestId": D0_RASTER_MANIFEST_ID,
        "fixtureCount": len(fixtures),
        "sourceByteHashes": {str(item["role"]): str(item["expectedSha256"]) for item in fixtures},
        "decodedContentHashes": {
            str(item["role"]): str(item["expectedDecodedContentHash"]) for item in fixtures
        },
        "roles": [str(item["role"]) for item in fixtures],
        "rightsClass": "project_authored_public_synthetic_d0",
        "sourceExternalToFit": True,
        "evaluatorOnlyViewFrozenWithSources": True,
        "fitOrEvaluationRunAtPublication": False,
        "learnedAiEvidence": False,
        "realPhotoEvidence": False,
        "generalisationEvidence": False,
        "productEvidence": False,
        "fixtureSetHash": "",
    }
    publication["fixtureSetHash"] = sha256_bytes(
        "\n".join(
            [
                D0_RASTER_PUBLICATION_VERSION,
                *(str(item["expectedSha256"]) for item in fixtures),
                *(str(item["expectedDecodedContentHash"]) for item in fixtures),
            ]
        ).encode("utf-8")
    )
    write_canonical_json(output_dir / "publication_provenance.json", publication)
    return publication
