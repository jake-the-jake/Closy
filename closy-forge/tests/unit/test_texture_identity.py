from __future__ import annotations

import struct
import zlib
from copy import deepcopy

import pytest

from closy_forge.appearance import build_texture_identity_report, hash_texture_identity_report
from closy_forge.appearance.bitmap_atlas import (
    ATLAS_SIZE,
    BITMAP_PATHS,
    audit_bitmap_atlas_bundle,
    build_d0_bitmap_atlas,
    hash_bitmap_pbr_report,
)
from closy_forge.capture import build_synthetic_capture_record
from closy_forge.fitting import fit_tshirt_parameters_from_visual_observations
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.raster import decode_png_rgba, encode_png_rgba
from closy_forge.visual_understanding import (
    build_default_applied_correction_record,
    build_multiview_fusion_record,
    build_tshirt_visual_observations,
)


def test_texture_identity_report_is_deterministic_and_mobile_safe() -> None:
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    correction = build_default_applied_correction_record(visual)
    fusion = build_multiview_fusion_record(capture, visual, correction)
    fit = fit_tshirt_parameters_from_visual_observations(visual, multiview_fusion=fusion)
    materials = {
        "schemaVersion": 1,
        "materials": [
            {
                "id": "material.cotton_jersey_reference_v1",
                "label": "Fixture cotton jersey blue",
                "pbr": {
                    "baseColorFactor": [0.08, 0.26, 0.78, 1.0],
                    "roughnessFactor": 0.86,
                    "metallicFactor": 0.0,
                },
            },
            {
                "id": "material.cotton_rib_reference_v1",
                "label": "Fixture cotton rib collar",
                "pbr": {
                    "baseColorFactor": [0.06, 0.20, 0.62, 1.0],
                    "roughnessFactor": 0.9,
                    "metallicFactor": 0.0,
                },
            },
        ],
    }

    first = build_texture_identity_report(
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        render_materials=materials,
        multiview_fusion=fusion,
    )
    second = build_texture_identity_report(
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        render_materials=materials,
        multiview_fusion=fusion,
    )

    assert first == second
    assert first["status"] == "pass"
    assert first["sourceTextureAvailable"] is True
    assert first["generatedAtlasAvailable"] is True
    assert first["textureProjectionRun"] is True
    assert first["integrity"]["textureIdentityHash"] == hash_texture_identity_report(first)
    assert first["sourceMultiviewFusionId"] == fusion["fusionRecordId"]
    assert first["sourceFusedEvidenceHash"] == fusion["fusedEvidence"]["evidenceHash"]
    assert first["sourceViewProjection"]["visibleProjectionCount"] > 0
    assert first["visibleRegionConfidence"]["meanVisibleConfidence"] >= 0.9
    assert first["logoPrintPreservation"]["visibleSourceOverwriteAllowed"] is False
    assert first["controlledInpainting"]["visibleEvidenceOverwriteAllowed"] is False
    assert first["controlledInpainting"]["overwriteVisibleSourceEvidenceRejectedCount"] > 0
    assert first["policy"]["rawPixelsExported"] is False
    assert {
        "conventionalFallbackMaterials",
        "generatedAtlas",
        "pbrMaterialMaps",
        "sourceProjection",
    } <= set(first["artifactRefs"])
    bitmap = first["decodedBitmapAtlas"]
    assert bitmap["decodedRasterAssetsPersisted"] is True
    assert bitmap["sourceObservedFraction"] > 0.5
    assert bitmap["generatedControlledFillFraction"] > 0.0
    assert len(first["observedMaterialRegions"]) == 2
    assert any(
        region["textureSource"] == "source_projection_summary"
        for region in first["observedMaterialRegions"]
    )
    assert first["pbrMaterialMaps"]["sourceBackedMapCount"] >= 1
    assert first["pbrMaterialMaps"]["placeholderMapCount"] >= 1
    for region in first["observedMaterialRegions"]:
        pbr = region["pbr"]
        assert pbr["normalMapAvailable"] is False
        assert pbr["roughnessMapAvailable"] is True
        assert pbr["metalnessMapAvailable"] is True
        assert pbr["aoMapAvailable"] is False
        assert 0.65 <= pbr["roughnessFactor"] <= 1.0
        assert 0.0 <= pbr["metallicFactor"] <= 0.1


def test_bitmap_atlas_persists_decoded_pbr_maps_and_logo() -> None:
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    bundle = build_d0_bitmap_atlas(capture, visual)

    assert bundle.report["status"] == "pass"
    assert bundle.report["logoPreservation"]["preserved"] is True
    assert bundle.report["coverage"]["generatedPixelsLabelledSourceObserved"] is False
    assert bundle.report["pbr"]["appearancePhysicsSeparated"] is True
    assert audit_bitmap_atlas_bundle(bundle.artifacts, bundle.report, visual)["status"] == "pass"
    for path in BITMAP_PATHS.values():
        assert path in bundle.artifacts
    assert decode_png_rgba(bundle.artifacts[BITMAP_PATHS["baseColor"]]).width == ATLAS_SIZE


@pytest.mark.parametrize(
    "corruption",
    [
        "swapped_front_rear",
        "wrong_color_profile",
        "shifted_logo",
        "seam_discontinuity",
        "corrupted_png_bytes",
        "wrong_atlas_dimensions",
        "forged_confidence",
        "generated_provenance_mismatch",
    ],
)
def test_bitmap_atlas_corruption_controls_fail_closed(corruption: str) -> None:
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    bundle = build_d0_bitmap_atlas(capture, visual)
    artifacts = deepcopy(bundle.artifacts)
    report = deepcopy(bundle.report)

    if corruption == "swapped_front_rear":
        front = "source/public_fixture/front.png"
        rear = "source/public_fixture/back.png"
        artifacts[front], artifacts[rear] = artifacts[rear], artifacts[front]
    elif corruption == "wrong_color_profile":
        front = "source/public_fixture/front.png"
        payload = artifacts[front]
        assert isinstance(payload, bytes)
        artifacts[front] = _insert_png_chunk(payload, b"iCCP", b"forged\x00\x00x")
    elif corruption == "shifted_logo":
        _mutate_map(artifacts, report, "baseColor", _erase_logo)
    elif corruption == "seam_discontinuity":
        _mutate_map(artifacts, report, "baseColor", _break_seam)
    elif corruption == "corrupted_png_bytes":
        path = BITMAP_PATHS["normal"]
        payload = artifacts[path]
        assert isinstance(payload, bytes)
        artifacts[path] = payload[:-7]
    elif corruption == "wrong_atlas_dimensions":
        path = BITMAP_PATHS["roughness"]
        artifacts[path] = encode_png_rgba(
            128, ATLAS_SIZE, bytes((220, 220, 220, 255)) * 128 * ATLAS_SIZE
        )
        _rehash_map(report, "roughness", artifacts[path])
    elif corruption == "forged_confidence":
        _mutate_map(artifacts, report, "viewConfidence", _forge_confidence)
    elif corruption == "generated_provenance_mismatch":
        _mutate_map(artifacts, report, "sourceContribution", _forge_provenance)
    report["integrity"]["bitmapPbrReportHash"] = hash_bitmap_pbr_report(report)

    with pytest.raises(ValueError):
        audit_bitmap_atlas_bundle(artifacts, report, visual)


def test_tshirt_visual_parts_include_privacy_safe_color_evidence() -> None:
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)

    parts = [
        part
        for view in visual["views"]
        for part in view["semanticParts"]
        if part["semanticId"] == "component.tshirt.torso"
    ]

    assert parts
    for part in parts:
        color = part["colorEvidence"]
        assert color["source"] == "decoded_pixel_mean_rgba_summary"
        assert color["sourcePixelsPortable"] is False
        assert color["pixelSampleCount"] > 0
        assert len(color["meanBaseColorFactor"]) == 4


def _mutate_map(
    artifacts: dict[str, bytes | dict[str, object]],
    report: dict[str, object],
    map_id: str,
    mutate: object,
) -> None:
    path = BITMAP_PATHS[map_id]
    payload = artifacts[path]
    assert isinstance(payload, bytes)
    decoded = decode_png_rgba(payload)
    pixels = bytearray(decoded.rgba)
    assert callable(mutate)
    mutate(pixels)
    artifacts[path] = encode_png_rgba(decoded.width, decoded.height, bytes(pixels))
    _rehash_map(report, map_id, artifacts[path])


def _rehash_map(report: dict[str, object], map_id: str, payload: object) -> None:
    assert isinstance(payload, bytes)
    maps = report["maps"]
    assert isinstance(maps, list)
    record = next(item for item in maps if isinstance(item, dict) and item["mapId"] == map_id)
    record["sha256"] = sha256_bytes(payload)


def _erase_logo(pixels: bytearray) -> None:
    for offset in range(0, len(pixels), 4):
        if tuple(pixels[offset : offset + 4]) == (244, 184, 44, 255):
            pixels[offset : offset + 4] = bytes((42, 96, 210, 255))


def _break_seam(pixels: bytearray) -> None:
    for y in range(ATLAS_SIZE):
        for x in range(128, 130):
            offset = (y * ATLAS_SIZE + x) * 4
            pixels[offset : offset + 4] = bytes((240, 32, 32, 255))


def _forge_confidence(pixels: bytearray) -> None:
    pixels[0:4] = bytes((255, 255, 255, 255))


def _forge_provenance(pixels: bytearray) -> None:
    pixels[0:4] = bytes((255, 0, 0, 255))


def _insert_png_chunk(data: bytes, kind: bytes, payload: bytes) -> bytes:
    chunk = (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )
    return data[:33] + chunk + data[33:]
