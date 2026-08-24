from __future__ import annotations

import binascii
import struct
import zlib
from pathlib import Path

import pytest

from closy_forge.capture import (
    build_synthetic_capture_record,
    decode_raster_fixture_pixels,
)
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.visual_understanding import (
    REQUIRED_TSHIRT_VISUAL_LANDMARKS,
    CorrectionReplayError,
    RasterFixtureView,
    RasterVisualParseError,
    apply_correction_operations,
    build_applied_correction_record,
    build_default_applied_correction_record,
    build_empty_correction_record,
    build_project_authored_tshirt_pixel_views,
    build_tshirt_visual_observations,
    hash_correction_record,
    hash_visual_observations,
    parse_tshirt_raster_pixel_views,
    render_project_authored_tshirt_rgba,
)


def test_tshirt_visual_observations_are_pixel_derived_masks_parts_and_landmarks() -> None:
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)

    assert visual["sourceRecordHash"] == capture["immutability"]["sourceRecordHash"]
    assert visual["integrity"]["visualRecordHash"] == hash_visual_observations(visual)
    assert visual["stageVersion"] == "closy.visual_observations.tshirt.raster_d0_v1"
    assert visual["provider"]["modelIdentity"] == "local_algorithmic_fallback_not_trained_model"
    assert visual["provider"]["externalApis"] is False
    assert visual["provider"]["trainingUse"] is False
    assert visual["aggregate"]["pixelDerivedViewCount"] == 4
    assert visual["aggregate"]["maskCount"] == 16
    assert visual["aggregate"]["targetGarmentMaskCount"] == 4
    assert visual["aggregate"]["personBodyProxyMaskCount"] == 4
    assert visual["aggregate"]["backgroundMaskCount"] == 4
    assert visual["aggregate"]["occlusionUncertaintyMaskCount"] == 4
    assert visual["aggregate"]["semanticPartCount"] == 12
    assert visual["aggregate"]["openingBoundaryCount"] == 16
    assert visual["aggregate"]["meanMaskIoU"] == 1.0
    assert visual["aggregate"]["meanBoundaryFScore"] > 0.9
    assert set(REQUIRED_TSHIRT_VISUAL_LANDMARKS).issubset(
        set(visual["aggregate"]["observedLandmarks"])
    )
    assert visual["privacy"]["rawPixelsExported"] is False

    front = _view(visual, "front")
    assert {mask["semanticId"] for mask in front["masks"]} == {
        "component.tshirt",
        "component.avatar_body_proxy",
        "component.background",
        "component.occlusion_uncertainty",
    }
    assert {part["semanticId"] for part in front["semanticParts"]} == {
        "component.tshirt.torso",
        "component.tshirt.sleeve.left",
        "component.tshirt.sleeve.right",
    }
    assert {opening["openingId"] for opening in front["openings"]} == {
        "opening.neck",
        "opening.hem",
        "opening.cuff.left",
        "opening.cuff.right",
    }


def test_raster_parser_decodes_png_fixture_pixels_independently(tmp_path: Path) -> None:
    capture = build_synthetic_capture_record(seed=101)
    rgba = render_project_authored_tshirt_rgba(64, 80, label="front")
    path = tmp_path / "front.png"
    path.write_bytes(_png_rgba(64, 80, rgba))
    decoded = decode_raster_fixture_pixels(path, declared_mime="image/png")

    visual = parse_tshirt_raster_pixel_views(
        [
            RasterFixtureView(
                view_id="view.front",
                label="front",
                width=decoded.width,
                height=decoded.height,
                rgba=decoded.rgba,
                source_id="source.unit.front",
                normalized_pixel_hash=decoded.pixel_hash,
            )
        ],
        source_record_id=capture["recordId"],
        source_record_hash=capture["immutability"]["sourceRecordHash"],
    )

    assert visual["aggregate"]["pixelDerivedViewCount"] == 1
    assert visual["views"][0]["pixelEvidence"]["normalizedPixelHash"] == decoded.pixel_hash
    assert visual["views"][0]["masks"][0]["pixelCount"] > 0
    assert "front.png" not in canonical_dumps(visual)
    assert str(tmp_path) not in canonical_dumps(visual)


def test_empty_correction_record_is_still_editable_and_hash_stable() -> None:
    visual = build_tshirt_visual_observations(build_synthetic_capture_record(seed=101))
    correction = build_empty_correction_record(visual)

    assert correction["editable"] is True
    assert correction["operations"] == []
    assert correction["application"]["status"] == "not_applied_empty"
    assert correction["visualRecordHash"] == visual["integrity"]["visualRecordHash"]
    assert correction["integrity"]["correctionRecordHash"] == hash_correction_record(correction)
    assert "mask_exclude_polygon" in correction["allowedOperations"]


def test_non_empty_corrections_apply_and_change_structured_artifact_hashes() -> None:
    visual = build_tshirt_visual_observations(build_synthetic_capture_record(seed=101))
    correction = build_default_applied_correction_record(visual)
    corrected = apply_correction_operations(visual, correction["operations"])

    assert correction["state"] == "edited"
    assert correction["application"]["status"] == "applied"
    assert correction["application"]["operationCount"] == 4
    assert (
        correction["application"]["beforeVisualRecordHash"]
        == visual["integrity"]["visualRecordHash"]
    )
    assert (
        correction["application"]["afterVisualRecordHash"]
        == corrected["integrity"]["visualRecordHash"]
    )
    assert (
        correction["application"]["afterArtifactHash"]
        != correction["application"]["beforeArtifactHash"]
    )
    assert correction["application"]["confidenceDelta"] < 0
    assert correction["integrity"]["correctionRecordHash"] == hash_correction_record(correction)
    front = _view(corrected, "front")
    assert front["protectedPrintRegions"][0]["regionId"] == "print.region.front_center_demo"


def test_correction_order_is_deterministic_and_semantically_observable() -> None:
    visual = build_tshirt_visual_observations(build_synthetic_capture_record(seed=101))
    before_hash = visual["integrity"]["visualRecordHash"]
    include = {
        "operationId": "op.include",
        "operation": "mask_include_polygon",
        "order": 1,
        "viewId": "view.front",
        "targetMaskId": "mask.front.target_garment",
        "polygon": [[0.10, 0.10], [0.20, 0.10], [0.20, 0.20], [0.10, 0.20]],
        "expectedVisualRecordHash": before_hash,
    }
    exclude = {
        "operationId": "op.exclude",
        "operation": "mask_exclude_polygon",
        "order": 2,
        "viewId": "view.front",
        "targetMaskId": "mask.front.target_garment",
        "polygon": [[0.10, 0.10], [0.20, 0.10], [0.20, 0.20], [0.10, 0.20]],
        "expectedVisualRecordHash": before_hash,
    }

    first = build_applied_correction_record(visual, [include, exclude])
    second = build_applied_correction_record(
        visual, [exclude | {"order": 1}, include | {"order": 2}]
    )

    assert first["integrity"]["correctionRecordHash"] != second["integrity"]["correctionRecordHash"]
    assert first["application"]["afterArtifactHash"] != second["application"]["afterArtifactHash"]


def test_stale_visual_hash_is_rejected_without_path_or_pixel_leakage() -> None:
    visual = build_tshirt_visual_observations(build_synthetic_capture_record(seed=101))

    with pytest.raises(CorrectionReplayError) as exc:
        build_applied_correction_record(
            visual,
            [
                {
                    "operationId": "op.stale",
                    "operation": "landmark_move",
                    "viewId": "view.front",
                    "landmarkId": "landmark.hem.center",
                    "position2d": [0.5, 0.8],
                    "expectedVisualRecordHash": "0" * 64,
                }
            ],
        )

    assert exc.value.code == "stale_visual_record_hash"
    assert "view.front" not in str(exc.value)


def test_missing_sleeve_occlusion_and_background_confusion_are_reported() -> None:
    capture = build_synthetic_capture_record(seed=101)
    missing = parse_tshirt_raster_pixel_views(
        build_project_authored_tshirt_pixel_views(capture, perturbation="missing_left_sleeve"),
        source_record_id=capture["recordId"],
        source_record_hash=capture["immutability"]["sourceRecordHash"],
    )
    confused = parse_tshirt_raster_pixel_views(
        build_project_authored_tshirt_pixel_views(capture, perturbation="background_confusion"),
        source_record_id=capture["recordId"],
        source_record_hash=capture["immutability"]["sourceRecordHash"],
    )

    assert missing["aggregate"]["missingEvidence"]
    assert missing["aggregate"]["meanSemanticPartIoU"] < 1.0
    assert any(
        "component.tshirt.sleeve.left" in view["missing"]
        for view in missing["aggregate"]["missingEvidence"]
    )
    assert confused["aggregate"]["meanMaskIoU"] == 1.0
    assert any(
        mask["semanticId"] == "component.occlusion_uncertainty" and mask["pixelCount"] > 0
        for view in confused["views"]
        for mask in view["masks"]
    )


def test_pixel_perturbation_changes_hashes_and_pixel_derived_evidence() -> None:
    capture = build_synthetic_capture_record(seed=101)
    normal = build_project_authored_tshirt_pixel_views(capture)
    shifted = build_project_authored_tshirt_pixel_views(capture, perturbation="crop")
    assert normal[0].normalized_pixel_hash != shifted[0].normalized_pixel_hash

    normal_visual = parse_tshirt_raster_pixel_views(
        normal,
        source_record_id=capture["recordId"],
        source_record_hash=capture["immutability"]["sourceRecordHash"],
    )
    shifted_visual = parse_tshirt_raster_pixel_views(
        shifted,
        source_record_id=capture["recordId"],
        source_record_hash=capture["immutability"]["sourceRecordHash"],
    )
    assert (
        normal_visual["views"][0]["masks"][0]["maskHash"]
        != shifted_visual["views"][0]["masks"][0]["maskHash"]
    )


def test_non_garment_and_non_avatar_domains_are_rejected() -> None:
    capture = build_synthetic_capture_record(seed=101)
    blank = bytes([246, 244, 239, 255]) * (64 * 80)
    body_only = bytearray(blank)
    for index in range(64 * 80):
        if 20 <= index % 64 <= 44 and 20 <= index // 64 <= 64:
            offset = index * 4
            body_only[offset : offset + 4] = bytes([218, 178, 142, 255])

    with pytest.raises(RasterVisualParseError) as no_garment:
        parse_tshirt_raster_pixel_views(
            [
                RasterFixtureView(
                    view_id="view.front",
                    label="front",
                    width=64,
                    height=80,
                    rgba=bytes(body_only),
                    source_id="source.blank",
                    normalized_pixel_hash="0" * 64,
                )
            ],
            source_record_id=capture["recordId"],
            source_record_hash=capture["immutability"]["sourceRecordHash"],
        )
    assert no_garment.value.code == "non_garment_domain_rejected"

    garment_only = render_project_authored_tshirt_rgba(64, 80, label="front").replace(
        bytes([218, 178, 142, 255]),
        bytes([246, 244, 239, 255]),
    )
    with pytest.raises(RasterVisualParseError) as no_avatar:
        parse_tshirt_raster_pixel_views(
            [
                RasterFixtureView(
                    view_id="view.front",
                    label="front",
                    width=64,
                    height=80,
                    rgba=garment_only,
                    source_id="source.garment_only",
                    normalized_pixel_hash="1" * 64,
                )
            ],
            source_record_id=capture["recordId"],
            source_record_hash=capture["immutability"]["sourceRecordHash"],
        )
    assert no_avatar.value.code == "non_avatar_domain_rejected"


def _view(visual: dict, label: str) -> dict:
    for view in visual["views"]:
        if view["label"] == label:
            return view
    raise AssertionError(f"missing view {label}")


def _png_rgba(width: int, height: int, rgba: bytes) -> bytes:
    assert len(rgba) == width * height * 4
    chunks: list[tuple[bytes, bytes]] = []
    chunks.append((b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        row = y * width * 4
        rows.extend(rgba[row : row + width * 4])
    chunks.append((b"IDAT", zlib.compress(bytes(rows))))
    chunks.append((b"IEND", b""))
    payload = bytearray(b"\x89PNG\r\n\x1a\n")
    for name, chunk in chunks:
        payload.extend(len(chunk).to_bytes(4, "big"))
        payload.extend(name)
        payload.extend(chunk)
        payload.extend((binascii.crc32(name + chunk) & 0xFFFFFFFF).to_bytes(4, "big"))
    return bytes(payload)
