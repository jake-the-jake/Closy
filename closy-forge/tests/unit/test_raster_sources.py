from __future__ import annotations

import binascii
import json
import os
import struct
import zlib
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from closy_forge.capture import (
    RasterIngestError,
    build_raster_fixture_records,
    delete_raster_fixture_registry,
    hash_raster_tombstone,
    ingest_raster_fixture_manifest,
    inspect_raster,
)
from closy_forge.cli.main import EXIT_BUILD_FAILURE, EXIT_SUCCESS, main
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_io.managed_output import MARKER_NAME


def test_raster_fixture_ingest_accepts_png_and_jpeg_without_portable_leakage(
    tmp_path: Path,
) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    png_path = root / "private_face_front.png"
    jpg_path = root / "camera_roll_back.jpg"
    png_path.write_bytes(_png_rgba(512, 512))
    jpg_path.write_bytes(_jpeg(640, 800, orientation=6))
    manifest = _manifest(
        tmp_path,
        root,
        [
            ("fixture.front", "view.front", png_path, "image/png"),
            ("fixture.back", "view.back", jpg_path, "image/jpeg"),
        ],
    )

    result = build_raster_fixture_records(manifest_path=manifest, input_root=root)

    assert result.private_record["recordType"] == "raster_fixture_ingest_private"
    assert len(result.private_record["acceptedSources"]) == 2
    assert result.quality_report["overallStatus"] == "pass"
    assert result.quality_report["aggregate"]["pixelDerivedViewCount"] == 2
    assert result.quality_report["aggregate"]["jpegPixelDecodedViewCount"] == 1
    assert result.portable_source_summary["privacy"]["rawSourceBytesCopied"] is False

    private_payload = canonical_dumps(result.private_record)
    portable_payload = canonical_dumps(result.portable_source_summary)
    assert "sourceByteSha256" in private_payload
    assert "decodedContentSha256" in private_payload
    assert "private_face_front.png" not in private_payload
    assert "camera_roll_back.jpg" not in private_payload
    assert str(tmp_path) not in private_payload
    assert "sourceByteSha256" not in portable_payload
    assert "decodedContentSha256" not in portable_payload
    assert "private_face_front.png" not in portable_payload
    assert str(tmp_path) not in portable_payload


def test_raster_fixture_cli_writes_private_and_portable_outputs(tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    png_path = root / "front.png"
    png_path.write_bytes(_png_rgba(8, 8))
    manifest = _manifest(tmp_path, root, [("fixture.front", "view.front", png_path, "image/png")])
    private_registry = tmp_path / "private-registry"
    portable_output = tmp_path / "portable-output"

    exit_code = main(
        [
            "capture",
            "ingest-raster-fixture",
            "--manifest",
            str(manifest),
            "--input-root",
            str(root),
            "--private-registry",
            str(private_registry),
            "--portable-output",
            str(portable_output),
            "--output-root",
            str(tmp_path),
            "--json",
        ]
    )

    assert exit_code == EXIT_SUCCESS
    assert sorted(path.name for path in private_registry.iterdir()) == [
        MARKER_NAME,
        "lifecycle_journal.json",
        "normalization_record.json",
        "private_ingest_record.json",
        "raster_quality.json",
    ]
    assert sorted(path.name for path in portable_output.iterdir()) == [
        MARKER_NAME,
        "privacy_report.json",
        "source_summary.json",
    ]
    assert "sourceByteSha256" not in (portable_output / "source_summary.json").read_text(
        encoding="utf-8"
    )


def test_jpeg_exif_orientation_is_normalized_deterministically(tmp_path: Path) -> None:
    path = tmp_path / "fixture.jpg"
    path.write_bytes(_jpeg(11, 29, orientation=6))

    audit = inspect_raster(path, declared_mime="image/jpeg")

    assert audit["decodedDimensions"] == {"width": 11, "height": 29}
    assert audit["normalizedDimensions"] == {"width": 29, "height": 11}
    assert audit["exifOrientation"] == 6
    assert audit["pixelStats"]["available"] is True
    assert audit["decoder"]["dependency"] == "Pillow==11.1.0"


def test_structural_only_jpeg_header_is_rejected_without_pixel_decode(tmp_path: Path) -> None:
    path = tmp_path / "header-only.jpg"
    path.write_bytes(b"\xff\xd8\xff\xc0\x00\x08\x08\x00\x08\x00\x08\x03\xff\xd9")

    with pytest.raises(RasterIngestError) as error:
        inspect_raster(path, declared_mime="image/jpeg")

    assert error.value.code == "jpeg_pixel_decode_failed"


@pytest.mark.parametrize(
    ("filename", "declared_mime", "payload_kind", "code"),
    [
        ("wrong.jpg", "image/jpeg", "png", "magic_mime_mismatch"),
        ("bad.png", "image/png", "bad", "bad_magic"),
        ("truncated.png", "image/png", "truncated_png", "truncated_png"),
        ("truncated.jpg", "image/jpeg", "truncated_jpeg", "jpeg_pixel_decode_failed"),
    ],
)
def test_raster_ingest_rejects_bad_magic_and_truncated_inputs(
    tmp_path: Path, filename: str, declared_mime: str, payload_kind: str, code: str
) -> None:
    path = tmp_path / filename
    payloads = {
        "png": _png_rgba(4, 4),
        "bad": b"not image bytes",
        "truncated_png": b"\x89PNG\r\n\x1a\n",
        "truncated_jpeg": b"\xff\xd8\xff\xe0\x00",
    }
    path.write_bytes(payloads[payload_kind])

    with pytest.raises(RasterIngestError) as exc:
        inspect_raster(path, declared_mime=declared_mime)

    assert exc.value.code == code


@pytest.mark.parametrize(
    ("payload_kind", "code"),
    [
        ("large_dimension", "dimension_limit_exceeded"),
        ("large_pixels", "pixel_count_limit_exceeded"),
        ("decompression_extra", "decompression_limit_exceeded"),
        ("animated", "animated_or_multipage_rejected"),
        ("icc", "unsupported_color_profile"),
    ],
)
def test_raster_ingest_rejects_limits_animation_and_profiles(
    tmp_path: Path, payload_kind: str, code: str
) -> None:
    path = tmp_path / "fixture.png"
    payloads = {
        "large_dimension": _png_rgba(5000, 1),
        "large_pixels": _png_header_only(2048, 2048),
        "decompression_extra": _png_rgba(16, 16, raw_extra=b"\x00"),
        "animated": _png_rgba(8, 8, extra_chunks=[(b"acTL", b"\x00" * 8)]),
        "icc": _png_rgba(8, 8, extra_chunks=[(b"iCCP", b"profile\x00\x00x")]),
    }
    path.write_bytes(payloads[payload_kind])

    with pytest.raises(RasterIngestError) as exc:
        inspect_raster(path, declared_mime="image/png")

    assert exc.value.code == code


@pytest.mark.parametrize(
    ("policy_patch", "code"),
    [
        ({"reconstructionConsent": "missing"}, "missing_reconstruction_consent"),
        ({"allowTrainingUse": True}, "training_use_forbidden"),
        ({"allowExternalApis": True}, "external_provider_use_forbidden"),
        ({"allowNetwork": True}, "network_use_forbidden"),
        ({"containsUserImagery": True}, "user_capture_profile_disabled"),
    ],
)
def test_raster_manifest_policy_fails_closed(
    tmp_path: Path, policy_patch: dict[str, Any], code: str
) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    path = root / "front.png"
    path.write_bytes(_png_rgba(6, 6))
    manifest = _manifest(
        tmp_path,
        root,
        [("fixture.front", "view.front", path, "image/png")],
        policy_patch=policy_patch,
    )

    with pytest.raises(RasterIngestError) as exc:
        build_raster_fixture_records(manifest_path=manifest, input_root=root)

    assert exc.value.code == code


def test_raster_manifest_rejects_duplicate_source_hash(tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    path = root / "front.png"
    path.write_bytes(_png_rgba(6, 6))
    manifest = _manifest(
        tmp_path,
        root,
        [
            ("fixture.front", "view.front", path, "image/png"),
            ("fixture.copy", "view.back", path, "image/png"),
        ],
    )

    with pytest.raises(RasterIngestError) as exc:
        build_raster_fixture_records(manifest_path=manifest, input_root=root)

    assert exc.value.code == "duplicate_source_hash"


def test_raster_manifest_rejects_paths_symlinks_hardlinks_and_hash_spoofing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png_rgba(6, 6))
    private_looking = root / "renamed_private_capture.png"
    private_looking.write_bytes(_png_rgba(7, 7))
    traversal_manifest = _manifest(
        tmp_path,
        root,
        [("fixture.escape", "view.front", outside, "image/png")],
        relative_override="../outside.png",
    )

    with pytest.raises(RasterIngestError) as traversal:
        build_raster_fixture_records(manifest_path=traversal_manifest, input_root=root)
    assert traversal.value.code == "path_traversal_rejected"

    spoof_manifest = _manifest(
        tmp_path,
        root,
        [("fixture.spoof", "view.front", private_looking, "image/png")],
        expected_hash_override="0" * 64,
    )
    with pytest.raises(RasterIngestError) as spoof:
        build_raster_fixture_records(manifest_path=spoof_manifest, input_root=root)
    assert spoof.value.code == "fixture_hash_mismatch"

    symlink = root / "symlink.png"
    try:
        symlink.symlink_to(private_looking)
    except OSError:
        symlink = None
    if symlink is not None:
        symlink_manifest = _manifest(
            tmp_path,
            root,
            [("fixture.symlink", "view.front", symlink, "image/png")],
        )
        with pytest.raises(RasterIngestError) as symlink_error:
            build_raster_fixture_records(manifest_path=symlink_manifest, input_root=root)
        assert symlink_error.value.code == "symlink_rejected"

    hardlink = root / "hardlink.png"
    try:
        os.link(private_looking, hardlink)
    except OSError:
        hardlink = None
    if hardlink is not None:
        hardlink_manifest = _manifest(
            tmp_path,
            root,
            [("fixture.hardlink", "view.front", hardlink, "image/png")],
        )
        with pytest.raises(RasterIngestError) as hardlink_error:
            build_raster_fixture_records(manifest_path=hardlink_manifest, input_root=root)
        assert hardlink_error.value.code == "hardlink_rejected"


def test_raster_deletion_tombstone_is_idempotent_and_non_recoverable(tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    original = root / "front.png"
    original.write_bytes(_png_rgba(8, 8))
    manifest = _manifest(tmp_path, root, [("fixture.front", "view.front", original, "image/png")])
    private_registry = tmp_path / "private-registry"
    portable_output = tmp_path / "portable-output"
    tombstone = tmp_path / "tombstone.json"
    ingest_raster_fixture_manifest(
        manifest_path=manifest,
        input_root=root,
        private_registry_dir=private_registry,
        portable_output_dir=portable_output,
        allowed_output_root=tmp_path,
        force=True,
    )

    first = delete_raster_fixture_registry(
        private_registry_dir=private_registry,
        tombstone_path=tombstone,
    )
    second = delete_raster_fixture_registry(
        private_registry_dir=private_registry,
        tombstone_path=tombstone,
        force=True,
    )

    assert first["status"] == "deleted"
    assert first["deletedArtifactCount"] == 4
    assert second["status"] == "deleted"
    assert second["alreadyAbsentCount"] == 4
    assert original.exists()
    payload = json.loads(tombstone.read_text(encoding="utf-8"))
    assert payload["integrity"]["tombstoneHash"] == hash_raster_tombstone(payload)
    combined = canonical_dumps(payload)
    assert "sourceByteSha256" not in combined
    assert "front.png" not in combined
    assert str(tmp_path) not in combined


def test_raster_cli_errors_are_redacted(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    path = root / "private-face-front.png"
    path.write_bytes(_png_rgba(6, 6))
    manifest = _manifest(
        tmp_path,
        root,
        [("fixture.front", "view.front", path, "image/png")],
        expected_hash_override="0" * 64,
    )

    exit_code = main(
        [
            "capture",
            "ingest-raster-fixture",
            "--manifest",
            str(manifest),
            "--input-root",
            str(root),
            "--private-registry",
            str(tmp_path / "private-registry"),
            "--portable-output",
            str(tmp_path / "portable-output"),
            "--output-root",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_BUILD_FAILURE
    assert "fixture_hash_mismatch" in captured.err
    assert "private-face-front.png" not in captured.err
    assert str(tmp_path) not in captured.err


def _manifest(
    tmp_path: Path,
    root: Path,
    fixtures: list[tuple[str, str, Path, str]],
    *,
    policy_patch: dict[str, Any] | None = None,
    relative_override: str | None = None,
    expected_hash_override: str | None = None,
) -> Path:
    policy = {
        "reconstructionConsent": "not_required_project_fixture",
        "rightsClassification": "not_required_project_fixture",
        "allowTrainingUse": False,
        "allowExternalApis": False,
        "allowNetwork": False,
        "containsUserImagery": False,
        "retentionPolicy": "generated_fixture_ephemeral",
    }
    if policy_patch:
        policy.update(policy_patch)
    entries: list[dict[str, Any]] = []
    for fixture_id, view_id, path, mime in fixtures:
        relative_path = relative_override or path.relative_to(root).as_posix()
        try:
            audit = (
                inspect_raster(path, declared_mime=mime)
                if path.exists() and not path.is_symlink()
                else {}
            )
        except RasterIngestError:
            audit = {}
        entries.append(
            {
                "fixtureId": fixture_id,
                "viewId": view_id,
                "relativePath": relative_path,
                "declaredMime": mime,
                "expectedSha256": expected_hash_override or sha256_file(path),
                "expectedDecodedContentHash": audit.get("decodedContentSha256"),
                "rightsClassification": "not_required_project_fixture",
            }
        )
    manifest_path = tmp_path / "fixture_manifest.json"
    write_canonical_json(
        manifest_path,
        {
            "schemaVersion": 1,
            "manifestId": "synthetic_tshirt_raster_fixture_v1",
            "profile": "synthetic_fixture_raster_v1",
            "approvedFixtureRootId": "unit-test-generated-fixtures",
            "garmentId": "garment.demo_tshirt.reference_v1",
            "garmentClass": "tshirt",
            "avatarContractId": "avatar.closy_reference_v1",
            "policy": policy,
            "fixtures": entries,
        },
    )
    return manifest_path


def _png_rgba(
    width: int,
    height: int,
    *,
    raw_extra: bytes = b"",
    extra_chunks: list[tuple[bytes, bytes]] | None = None,
) -> bytes:
    chunks: list[tuple[bytes, bytes]] = []
    chunks.append((b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
    chunks.extend(extra_chunks or [])
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            red = 48 + (x * 9) % 140
            green = 80 + (y * 7) % 120
            blue = 128 + ((x + y) * 5) % 80
            alpha = 255 if 1 <= x < width - 1 and 1 <= y < height - 1 else 0
            rows.extend((red, green, blue, alpha))
    chunks.append((b"IDAT", zlib.compress(bytes(rows) + raw_extra)))
    chunks.append((b"IEND", b""))
    payload = bytearray(b"\x89PNG\r\n\x1a\n")
    for name, chunk in chunks:
        payload.extend(len(chunk).to_bytes(4, "big"))
        payload.extend(name)
        payload.extend(chunk)
        payload.extend((binascii.crc32(name + chunk) & 0xFFFFFFFF).to_bytes(4, "big"))
    return bytes(payload)


def _png_header_only(width: int, height: int) -> bytes:
    chunks = [(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)), (b"IEND", b"")]
    payload = bytearray(b"\x89PNG\r\n\x1a\n")
    for name, chunk in chunks:
        payload.extend(len(chunk).to_bytes(4, "big"))
        payload.extend(name)
        payload.extend(chunk)
        payload.extend((binascii.crc32(name + chunk) & 0xFFFFFFFF).to_bytes(4, "big"))
    return bytes(payload)


def _jpeg(width: int, height: int, *, orientation: int = 1) -> bytes:
    image = Image.new("RGB", (width, height))
    image.putdata(
        [
            (184, 154, 122) if ((x // 4) + (y // 4)) % 2 == 0 else (72, 96, 132)
            for y in range(height)
            for x in range(width)
        ]
    )
    exif = Image.Exif()
    exif[0x0112] = orientation
    output = BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=False, progressive=False, exif=exif)
    return output.getvalue()
