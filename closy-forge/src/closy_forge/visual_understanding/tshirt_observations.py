from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.capture.raster_sources import decode_raster_fixture_pixels
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.visual_understanding.raster_parser import (
    RASTER_PIXEL_PARSER_VERSION,
    RasterFixtureView,
    RasterVisualParseError,
    build_project_authored_tshirt_pixel_views,
    normalized_raster_pixel_hash,
    parse_tshirt_raster_pixel_views,
)

TSHIRT_VISUAL_OBSERVATION_VERSION = "closy.visual_observations.tshirt.raster_d0_v1"
TSHIRT_VISUAL_OBSERVATION_ID = "visual.raster_d0_tshirt_reference_v1"
TSHIRT_INGESTED_VISUAL_OBSERVATION_VERSION = (
    "closy.visual_observations.tshirt.exact_ingested_raster_d0_v2"
)
TSHIRT_INGESTED_VISUAL_OBSERVATION_ID = "visual.exact_ingested_raster_d0_tshirt_v2"

REQUIRED_TSHIRT_VISUAL_LANDMARKS = (
    "landmark.neck.center",
    "landmark.shoulder.left",
    "landmark.shoulder.right",
    "landmark.armhole.left",
    "landmark.armhole.right",
    "landmark.cuff.left",
    "landmark.cuff.right",
    "landmark.hem.left",
    "landmark.hem.right",
    "landmark.hem.center",
)


def build_tshirt_visual_observations(capture_record: dict[str, Any]) -> dict[str, Any]:
    """Build BP50 D0 visual evidence from decoded project-authored raster pixels.

    This is still a synthetic fixture profile. It is materially stronger than
    the earlier analytic-polygon scaffold because masks, parts, openings and
    landmarks are derived from a deterministic pixel fixture instead of from the
    T-shirt parameter object used by fitting.
    """

    pixel_views = build_project_authored_tshirt_pixel_views(capture_record)
    record = parse_tshirt_raster_pixel_views(
        pixel_views,
        source_record_id=str(capture_record["recordId"]),
        source_record_hash=str(capture_record["immutability"]["sourceRecordHash"]),
    )
    record["visualUnderstandingId"] = TSHIRT_VISUAL_OBSERVATION_ID
    record["stageVersion"] = TSHIRT_VISUAL_OBSERVATION_VERSION
    record["aggregate"]["requiredLandmarks"] = list(REQUIRED_TSHIRT_VISUAL_LANDMARKS)
    record["provider"]["algorithmVersion"] = RASTER_PIXEL_PARSER_VERSION
    cameras = {
        str(view.get("viewId", "")): deepcopy(view.get("camera", {}))
        for view in capture_record.get("views", [])
        if isinstance(view, Mapping)
    }
    for view in record["views"]:
        view["camera"] = {
            **cameras.get(str(view.get("viewId", "")), {}),
            "source": "synthetic_capture_record_camera_metadata",
        }
    record["integrity"]["visualRecordHash"] = hash_visual_observations(record)
    return record


def build_tshirt_visual_observations_from_ingested_rasters(
    *,
    manifest: dict[str, Any],
    input_root: Path,
    private_record: dict[str, Any],
    normalization_record: dict[str, Any],
) -> dict[str, Any]:
    """Reopen the frozen front/rear files and derive observations from decoded pixels."""

    _validate_ingested_identity(manifest, private_record, normalization_record)
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list):
        raise RasterVisualParseError("ingested_fixture_inventory_invalid")
    roles = [str(item.get("role", "")) for item in fixtures if isinstance(item, Mapping)]
    if roles != ["front", "rear", "evaluator_only_three_quarter"]:
        raise RasterVisualParseError("ingested_fixture_roles_reordered_or_missing")
    accepted_by_fixture = {
        str(source.get("fixtureId")): source
        for source in private_record.get("acceptedSources", [])
        if isinstance(source, Mapping)
    }
    normalized_by_source = {
        str(item.get("sourceId")): item
        for item in normalization_record.get("outputs", [])
        if isinstance(item, Mapping)
    }
    root = input_root.resolve()
    pixel_views: list[RasterFixtureView] = []
    lineage_by_view: dict[str, dict[str, Any]] = {}
    for fixture in fixtures[:2]:
        if not isinstance(fixture, Mapping):
            raise RasterVisualParseError("ingested_fixture_entry_invalid")
        fixture_id = str(fixture.get("fixtureId", ""))
        source = accepted_by_fixture.get(fixture_id)
        if not isinstance(source, Mapping):
            raise RasterVisualParseError("ingested_source_join_missing")
        relative = fixture.get("relativePath")
        if not isinstance(relative, str) or not relative:
            raise RasterVisualParseError("ingested_source_path_invalid")
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise RasterVisualParseError("ingested_source_path_not_allowlisted") from error
        if path.is_symlink() or not path.is_file():
            raise RasterVisualParseError("ingested_source_file_missing")
        if sha256_file(path) != fixture.get("expectedSha256"):
            raise RasterVisualParseError("ingested_source_byte_hash_stale")
        decoded = decode_raster_fixture_pixels(path, declared_mime="image/png")
        expected_dimensions = fixture.get("decodedDimensions")
        if expected_dimensions != {"width": decoded.width, "height": decoded.height}:
            raise RasterVisualParseError("ingested_source_dimensions_mismatch")
        if source.get("decodedDimensions") != expected_dimensions:
            raise RasterVisualParseError("ingested_private_dimensions_stale")
        if source.get("viewId") != fixture.get("viewId"):
            raise RasterVisualParseError("ingested_private_view_join_stale")
        if decoded.pixel_hash != fixture.get("decodedPixelHash"):
            raise RasterVisualParseError("ingested_source_pixel_hash_stale")
        if decoded.decoded_content_sha256 != fixture.get("expectedDecodedContentHash"):
            raise RasterVisualParseError("ingested_source_decoded_hash_stale")
        if decoded.decoded_content_sha256 != source.get("decodedContentSha256"):
            raise RasterVisualParseError("ingested_private_record_join_stale")
        normalized = normalized_by_source.get(str(source.get("sourceId", "")))
        normalized_hash = (
            normalized.get("normalizedRepresentation", {}).get("privateNormalizedContentHash")
            if isinstance(normalized, Mapping)
            else None
        )
        if normalized_hash != decoded.decoded_content_sha256:
            raise RasterVisualParseError("ingested_normalization_join_stale")
        view_id = str(fixture.get("viewId", ""))
        label = str(fixture.get("label", ""))
        pixel_views.append(
            RasterFixtureView(
                view_id=view_id,
                label=label,
                width=decoded.width,
                height=decoded.height,
                rgba=decoded.rgba,
                source_id=str(source.get("sourceId", "")),
                normalized_pixel_hash=normalized_raster_pixel_hash(
                    decoded.width, decoded.height, decoded.rgba
                ),
            )
        )
        lineage_by_view[view_id] = {
            "classification": "public_fixture",
            "role": fixture.get("role"),
            "sourceId": source.get("sourceId"),
            "sourceByteSha256": fixture.get("expectedSha256"),
            "decodedContentSha256": decoded.decoded_content_sha256,
            "normalizationRecordHash": normalization_record["integrity"]["normalizationRecordHash"],
            "camera": deepcopy(fixture.get("camera")),
        }

    record = parse_tshirt_raster_pixel_views(
        pixel_views,
        source_record_id=str(private_record["recordId"]),
        source_record_hash=str(private_record["integrity"]["sourceRecordHash"]),
    )
    record["visualUnderstandingId"] = TSHIRT_INGESTED_VISUAL_OBSERVATION_ID
    record["stageVersion"] = TSHIRT_INGESTED_VISUAL_OBSERVATION_VERSION
    record["garmentId"] = manifest["garmentId"]
    record["avatarContractId"] = manifest["avatarContractId"]
    record["inputMode"] = manifest["inputMode"]
    record["sourceClassification"] = "project_authored_public_synthetic_d0"
    record["fitInputRoles"] = ["front", "rear"]
    record["evaluatorOnlyBoundary"] = {
        "role": "evaluator_only_three_quarter",
        "mounted": False,
        "pixelsAvailableToFit": False,
        "derivedEvidenceAvailableToFit": False,
        "reason": "withheld_until_prediction_and_atlas_content_addressed",
    }
    for view in record["views"]:
        view_id = str(view.get("viewId", ""))
        view["sourceLineage"] = lineage_by_view[view_id]
        view["camera"] = deepcopy(lineage_by_view[view_id]["camera"])
    record["provider"]["settings"]["fixtureRendererCalledDuringObservationBuild"] = False
    record["provider"]["settings"]["sourceFilesReopened"] = True
    record["integrity"]["visualRecordHash"] = hash_visual_observations(record)
    return record


def validate_evaluator_only_ingested_raster(
    *,
    manifest: dict[str, Any],
    input_root: Path,
    private_record: dict[str, Any],
) -> dict[str, Any]:
    """Decode the frozen third view in qualification scope without returning its pixels."""

    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) != 3:
        raise RasterVisualParseError("evaluator_fixture_inventory_invalid")
    fixture = fixtures[2]
    if not isinstance(fixture, Mapping) or fixture.get("role") != ("evaluator_only_three_quarter"):
        raise RasterVisualParseError("evaluator_fixture_role_invalid")
    root = input_root.resolve()
    path = (root / str(fixture.get("relativePath", ""))).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise RasterVisualParseError("evaluator_source_path_not_allowlisted") from error
    if path.is_symlink() or not path.is_file():
        raise RasterVisualParseError("evaluator_source_file_missing")
    if sha256_file(path) != fixture.get("expectedSha256"):
        raise RasterVisualParseError("evaluator_source_byte_hash_stale")
    decoded = decode_raster_fixture_pixels(path, declared_mime="image/png")
    if fixture.get("decodedDimensions") != {
        "width": decoded.width,
        "height": decoded.height,
    }:
        raise RasterVisualParseError("evaluator_source_dimensions_mismatch")
    if decoded.pixel_hash != fixture.get("decodedPixelHash"):
        raise RasterVisualParseError("evaluator_source_pixel_hash_stale")
    if decoded.decoded_content_sha256 != fixture.get("expectedDecodedContentHash"):
        raise RasterVisualParseError("evaluator_source_decoded_hash_stale")
    accepted = [
        source
        for source in private_record.get("acceptedSources", [])
        if isinstance(source, Mapping) and source.get("fixtureId") == fixture.get("fixtureId")
    ]
    if (
        len(accepted) != 1
        or accepted[0].get("viewId") != fixture.get("viewId")
        or accepted[0].get("decodedDimensions") != fixture.get("decodedDimensions")
        or decoded.decoded_content_sha256 != accepted[0].get("decodedContentSha256")
    ):
        raise RasterVisualParseError("evaluator_private_record_join_stale")
    return {
        "schemaVersion": 1,
        "validationVersion": "closy.evaluator_only_raster_validation.v1",
        "classification": "public_fixture_restricted_evaluator_mount",
        "role": fixture["role"],
        "sourceId": accepted[0]["sourceId"],
        "sourceByteSha256": fixture["expectedSha256"],
        "decodedContentSha256": decoded.decoded_content_sha256,
        "decodedDimensions": {"width": decoded.width, "height": decoded.height},
        "decodedAndValidated": True,
        "rgbaBytesPersisted": False,
        "masksOrLandmarksDerived": False,
        "mountedIntoContender": False,
        "mountedBeforePredictionFreeze": False,
    }


def _validate_ingested_identity(
    manifest: dict[str, Any],
    private_record: dict[str, Any],
    normalization_record: dict[str, Any],
) -> None:
    if manifest.get("manifestId") != "exact_public_tshirt_front_rear_eval_v2":
        raise RasterVisualParseError("ingested_manifest_identity_invalid")
    if private_record.get("garmentId") != manifest.get("garmentId") or private_record.get(
        "avatarContractId"
    ) != manifest.get("avatarContractId"):
        raise RasterVisualParseError("ingested_selected_identity_mismatch")
    if normalization_record.get("sourceRecordHash") != private_record.get("integrity", {}).get(
        "sourceRecordHash"
    ):
        raise RasterVisualParseError("ingested_normalization_source_mismatch")


def hash_visual_observations(record: dict[str, Any]) -> str:
    payload = deepcopy(record)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["visualRecordHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
