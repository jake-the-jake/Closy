from __future__ import annotations

from pathlib import Path

import pytest

from closy_forge.capture.source_records import build_synthetic_capture_record
from closy_forge.capture_engineering_v1.alternate_renderer import render_ray_triangles
from closy_forge.capture_engineering_v1.camera_observation import estimate_camera
from closy_forge.capture_engineering_v1.capture_sources import decode_video_source
from closy_forge.capture_engineering_v1.common import canonical_digest
from closy_forge.capture_engineering_v1.corpus import session_specs
from closy_forge.capture_engineering_v1.development_model import (
    predict_linear_model,
    train_linear_model,
)
from closy_forge.capture_engineering_v1.isolation import (
    assert_contestant_payload,
    future_d0_prerequisite_report,
)
from closy_forge.capture_engineering_v1.ontology import migrate_legacy_mode_c, validate_session
from closy_forge.capture_engineering_v1.privacy import OwnedCaptureSession, secure_write
from closy_forge.capture_engineering_v1.protocol import load_frozen_protocol, validate_protocol
from closy_forge.capture_engineering_v1.quality import observe_pixels
from closy_forge.capture_engineering_v1.uv_projection import (
    ProjectionView,
    project_views_to_panel_uv,
    projection_controls,
    render_atlas_novel_view,
)
from closy_forge.capture_engineering_v1.video_avi import (
    DECODER_LICENSE,
    DECODER_VERSION,
    VideoDecodeError,
    decode_uncompressed_avi,
    encode_uncompressed_avi,
)
from closy_forge.geometry.mesh_model import Mesh, MeshSet


def test_protocol_is_frozen_complete_and_digest_bound() -> None:
    protocol = load_frozen_protocol()
    assert validate_protocol(protocol) == []
    assert protocol["protocolDigest"] == canonical_digest(protocol, "protocolDigest")
    assert protocol["counts"]["uniqueCaptureSessions"] == 80
    assert protocol["denominators"]["heldOutIdentityGroups"] == 20
    assert protocol["unsupportedEvidenceTiers"] == [
        "future_licensed_public",
        "future_private_authorized",
    ]


def test_session_inventory_exactly_matches_every_frozen_facet() -> None:
    specs = session_specs()
    assert len(specs) == 80
    assert len({spec.identity_group_id for spec in specs}) == 80
    assert sum(spec.split == "validation" for spec in specs) == 20
    assert sum(spec.primary_mode == "D" for spec in specs) == 12
    assert all(len(spec.view_roles) == 24 for spec in specs if spec.primary_mode == "D")
    development = [spec for spec in specs if spec.split == "development"]
    validation = [spec for spec in specs if spec.split == "validation"]
    for field in (
        "renderer_camera_family",
        "avatar_shape_family",
        "pose_family",
        "appearance_family",
    ):
        assert not (
            {getattr(spec, field) for spec in development}
            & {getattr(spec, field) for spec in validation}
        )


def test_future_d0_boundary_is_executable_but_does_not_claim_qualification() -> None:
    source_root = (
        Path(__file__).resolve().parents[2] / "src" / "closy_forge" / "capture_engineering_v1"
    )
    report = future_d0_prerequisite_report(
        session_specs(),
        contestant_source_paths=[source_root / "development_model.py", source_root / "fitting.py"],
    )
    assert report["status"] == "pass"
    assert report["qualificationRun"] is False
    assert report["independentRenderers"]["sharedRasterizerCode"] is False
    with pytest.raises(ValueError, match="contestant_payload_leak"):
        assert_contestant_payload({"decodedRgba": b"", "generatorSeed": 7})


def test_legacy_mode_c_migrates_without_duplicate_facet_authority() -> None:
    migrated = migrate_legacy_mode_c(build_synthetic_capture_record())
    assert validate_session(migrated) == []
    assert migrated["primaryMode"] == "C"
    assert migrated["facets"]["acquisitionPattern"] == "guided_multi_image"
    assert migrated["legacyModeC"] is not None
    assert migrated["legacyModeC"]["duplicateFacetFieldsPersisted"] is False


def test_actual_avi_round_trip_timestamps_and_cancellation() -> None:
    frames = [_rgba_fixture(10, 8, offset) for offset in range(24)]
    encoded = encode_uncompressed_avi(10, 8, frames, frames_per_second=12)
    decoded = decode_uncompressed_avi(encoded)
    assert decoded.decoder_version == DECODER_VERSION
    assert decoded.decoder_license == DECODER_LICENSE
    assert [frame.rgba for frame in decoded.frames] == frames
    assert decoded.frames[-1].timestamp_numerator == 23
    assert decoded.frames[-1].timestamp_denominator == 12
    with pytest.raises(VideoDecodeError, match="video_decode_cancelled"):
        decode_uncompressed_avi(encoded, cancelled=lambda: True)


def test_video_qc_retains_blank_frames_but_never_selects_them_when_valid_frames_exist() -> None:
    valid = _rgba_fixture(10, 8, 2)
    blank = bytes((232, 229, 222, 255) * 80)
    encoded = encode_uncompressed_avi(10, 8, [blank, *([valid] * 23)], frames_per_second=12)
    report = decode_video_source(
        encoded,
        source_id="video.qc",
        capture_thresholds={
            "minimumFocusScore": 0.0,
            "minimumExposureBalance": 0.0,
            "minimumForegroundCoverage": 0.0,
            "minimumBackgroundSeparation": 0.0,
        },
    )
    assert report["sourceFrameCount"] == 24
    assert report["frameRows"][0]["qualityStatus"] == "rejected"
    assert 0 not in report["selectedFrameIndices"]


def test_pixels_drive_mask_quality_camera_and_development_model() -> None:
    observations = [observe_pixels(20, 24, _rgba_fixture(20, 24, index)) for index in range(8)]
    camera = estimate_camera(
        observations[0], declared_view_role="front", known_scale_marker_meters=0.5
    )
    assert camera["exactGeneratorCameraConsumed"] is False
    assert camera["scaleSource"] == "known_marker"
    rows = [
        (
            "sleeveless_top",
            observation,
            {
                "body_length_meters": 0.56 + index * 0.01,
                "half_chest_width_meters": 0.25 + index * 0.005,
                "body_ease_meters": 0.03 + index * 0.002,
            },
        )
        for index, observation in enumerate(observations)
    ]
    model = train_linear_model(
        rows,
        target_fields={
            "sleeveless_top": (
                "body_length_meters",
                "half_chest_width_meters",
                "body_ease_meters",
            )
        },
    )
    prediction = predict_linear_model(model, "sleeveless_top", observations[-1])
    assert set(prediction) == {
        "body_length_meters",
        "half_chest_width_meters",
        "body_ease_meters",
    }
    assert model["validationRowsConsumed"] is False


def test_independent_renderer_uv_projection_and_pixel_controls() -> None:
    meshset = _plane_mesh()
    rendered = render_ray_triangles(meshset, width=24, height=24, view_role="front")
    assert rendered.rendered_pixel_count > 0
    observation = observe_pixels(rendered.width, rendered.height, rendered.rgba)
    views = [
        ProjectionView(
            "source.front",
            "front",
            rendered.width,
            rendered.height,
            rendered.rgba,
            observation,
        )
    ]
    atlas = project_views_to_panel_uv(meshset, views, atlas_width=16, atlas_height=16)
    assert atlas.lineage["observedTexelCount"] > 0
    assert all(
        not (observed and generated)
        for observed, generated in zip(atlas.observed_mask, atlas.generated_mask, strict=True)
    )
    controls = projection_controls(meshset, views)
    assert controls["sourcePixelMutationChangesAtlas"] is True
    assert controls["unavailableTargetTruthMutationChangesAtlas"] is False
    assert controls["observedGeneratedMasksDisjoint"] is True
    assert render_atlas_novel_view(meshset, atlas)["decoded"] is True


def test_owned_session_deletion_cannot_escape_root() -> None:
    with OwnedCaptureSession.create() as session:
        secure_write(session.root, "nested/source.bin", b"pixels")
        outside = session.owner / "outside.bin"
        outside.write_bytes(b"keep")
        result = session.delete()
        assert result["status"] == "deleted"
        assert outside.exists()


def _rgba_fixture(width: int, height: int, variant: int) -> bytes:
    pixels = bytearray((232, 229, 222, 255) * (width * height))
    margin = 2 + variant % max(1, min(width, height) // 5)
    for y in range(margin, height - margin):
        for x in range(margin, width - margin):
            offset = (y * width + x) * 4
            pixels[offset : offset + 4] = bytes((45 + (x + variant) % 40, 78 + y % 50, 132, 255))
    return bytes(pixels)


def _plane_mesh() -> MeshSet:
    return MeshSet(
        [
            Mesh(
                name="front",
                panel_id="panel.front",
                vertices=[(-0.4, 0.2, 0.0), (0.4, 0.2, 0.0), (0.4, 1.2, 0.0), (-0.4, 1.2, 0.0)],
                panel_uvs=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
                triangles=[(0, 1, 2), (0, 2, 3)],
            )
        ]
    )
