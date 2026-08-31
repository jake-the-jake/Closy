from __future__ import annotations

import binascii
import math
import re
import struct
import warnings
import zlib
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from closy_forge.contracts.common import COORDINATE_CONVENTION, FIXED_TIMESTAMP
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.package_io.managed_output import (
    cleanup_managed_staging,
    create_managed_staging,
    publish_managed_staging,
)

RASTER_FIXTURE_PROFILE = "synthetic_fixture_raster_v1"
RASTER_INGEST_RECORD_VERSION = "closy.raster_fixture_ingest_record.v1"
RASTER_NORMALIZATION_VERSION = "closy.raster_normalization.v1"
RASTER_QUALITY_SCORER_VERSION = "closy.raster_capture_quality.v1"
RASTER_LIFECYCLE_VERSION = "closy.raster_lifecycle_journal.v1"
RASTER_DELETION_VERSION = "closy.raster_deletion_tombstone.v1"

MAX_FILE_BYTES = 2_000_000
MAX_DIMENSION_PX = 4096
MAX_PIXEL_COUNT = 4_000_000
MAX_DECOMPRESSED_BYTES = 24_000_000
SUPPORTED_MIMES = {"image/png", "image/jpeg"}

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class RasterIngestError(RuntimeError):
    """Fail-closed raster ingest error with no path or filename leakage."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True)
class RasterIngestResult:
    private_record: dict[str, Any]
    lifecycle_journal: dict[str, Any]
    normalization_record: dict[str, Any]
    quality_report: dict[str, Any]
    portable_source_summary: dict[str, Any]
    privacy_report: dict[str, Any]


@dataclass(frozen=True)
class DecodedRasterPixels:
    width: int
    height: int
    mime: str
    rgba: bytes
    pixel_hash: str
    decoded_content_sha256: str


def ingest_raster_fixture_manifest(
    *,
    manifest_path: Path,
    input_root: Path,
    private_registry_dir: Path,
    portable_output_dir: Path,
    allowed_output_root: Path,
    force: bool = False,
) -> dict[str, Any]:
    """Ingest allowlisted project-authored PNG/JPEG fixtures into private records.

    This is a D0 synthetic-fixture raster profile only. It intentionally rejects
    arbitrary user paths and does not copy raw images into portable artifacts.
    """

    if private_registry_dir.absolute() == portable_output_dir.absolute():
        raise RasterIngestError("registry_and_portable_output_must_be_separate")
    result = build_raster_fixture_records(manifest_path=manifest_path, input_root=input_root)
    private_files = {
        "private_ingest_record.json": result.private_record,
        "lifecycle_journal.json": result.lifecycle_journal,
        "normalization_record.json": result.normalization_record,
        "raster_quality.json": result.quality_report,
    }
    portable_files = {
        "source_summary.json": result.portable_source_summary,
        "privacy_report.json": result.privacy_report,
    }
    private_staging = create_managed_staging(
        private_registry_dir,
        allowed_root=allowed_output_root,
        purpose="raster-private",
    )
    portable_staging = create_managed_staging(
        portable_output_dir,
        allowed_root=allowed_output_root,
        purpose="raster-portable",
    )
    try:
        for name, payload in private_files.items():
            write_canonical_json(private_staging / name, payload)
        for name, payload in portable_files.items():
            write_canonical_json(portable_staging / name, payload)
        publish_managed_staging(
            private_staging,
            private_registry_dir,
            allowed_root=allowed_output_root,
            purpose="raster-private",
            force=force,
        )
        publish_managed_staging(
            portable_staging,
            portable_output_dir,
            allowed_root=allowed_output_root,
            purpose="raster-portable",
            force=force,
        )
    finally:
        cleanup_managed_staging(
            private_staging,
            allowed_root=allowed_output_root,
            purpose="raster-private",
        )
        cleanup_managed_staging(
            portable_staging,
            allowed_root=allowed_output_root,
            purpose="raster-portable",
        )

    return {
        "status": "ingested",
        "profile": RASTER_FIXTURE_PROFILE,
        "recordId": result.private_record["recordId"],
        "sourceCount": len(result.private_record["acceptedSources"]),
        "qualityStatus": result.quality_report["overallStatus"],
        "pixelDerivedViewCount": result.quality_report["aggregate"]["pixelDerivedViewCount"],
        "portableRawBytesCopied": False,
        "privateRegistryFiles": sorted(private_files),
        "portableFiles": sorted(portable_files),
    }


def build_raster_fixture_records(*, manifest_path: Path, input_root: Path) -> RasterIngestResult:
    manifest = _load_fixture_manifest(manifest_path)
    root = _approved_root(input_root)
    sources = [_accepted_source(entry, root) for entry in _fixture_entries(manifest)]
    _reject_duplicate_sources(sources)

    manifest_id = _safe_id(str(manifest["manifestId"]))
    record_id = f"capture.raster_fixture.{manifest_id}"
    lifecycle_id = f"lifecycle.{manifest_id}"
    normalization_id = f"normalization.{manifest_id}"
    quality_id = f"capture_quality.raster_fixture.{manifest_id}"
    portable_id = f"portable_source_summary.{manifest_id}"

    private_record: dict[str, Any] = {
        "schemaVersion": 1,
        "recordId": record_id,
        "recordVersion": RASTER_INGEST_RECORD_VERSION,
        "recordType": "raster_fixture_ingest_private",
        "profile": RASTER_FIXTURE_PROFILE,
        "garmentId": _string(manifest.get("garmentId"), "garment.demo_tshirt.reference_v1"),
        "garmentClass": _string(manifest.get("garmentClass"), "tshirt"),
        "avatarContractId": _string(manifest.get("avatarContractId"), "avatar.closy_reference_v1"),
        "coordinateConvention": COORDINATE_CONVENTION,
        "policy": _policy_record(manifest),
        "sourceBoundary": {
            "allowlistedFixtureRootId": _string(manifest.get("approvedFixtureRootId"), ""),
            "arbitraryPathsAccepted": False,
            "pathTraversalRejected": True,
            "symlinkRejected": True,
            "hardlinkRejected": True,
            "networkAccessAllowed": False,
        },
        "acceptedSources": sources,
        "privateRegistryOnlyFields": [
            "sourceByteSha256",
            "decodedContentSha256",
            "sourceByteLength",
        ],
        "portablePackageExclusions": [
            "rawImageBytes",
            "sourceFilenames",
            "absolutePaths",
            "exifMetadata",
            "sourceByteSha256",
            "decodedContentSha256",
            "durablePublicSourceFingerprint",
        ],
        "derivationEdges": [
            {
                "from": source["sourceId"],
                "to": f"normalized.{source['sourceId']}",
                "kind": "metadata_stripped_normalized_fixture",
            }
            for source in sources
        ],
        "immutability": {
            "mutable": False,
            "canonicalization": "closy_canonical_json_v1_sort_keys_compact",
            "contentAddressable": True,
        },
        "integrity": {"sourceRecordHash": ""},
    }
    private_record["integrity"]["sourceRecordHash"] = hash_raster_ingest_record(private_record)
    lifecycle_journal = _lifecycle_journal(lifecycle_id, private_record)
    normalization_record = _normalization_record(normalization_id, private_record)
    quality_report = _quality_report(quality_id, private_record, normalization_record)
    portable_source_summary = _portable_source_summary(portable_id, private_record)
    privacy_report = _privacy_report(private_record, normalization_record, quality_report)
    return RasterIngestResult(
        private_record=private_record,
        lifecycle_journal=lifecycle_journal,
        normalization_record=normalization_record,
        quality_report=quality_report,
        portable_source_summary=portable_source_summary,
        privacy_report=privacy_report,
    )


def delete_raster_fixture_registry(
    *,
    private_registry_dir: Path,
    tombstone_path: Path,
    force: bool = False,
) -> dict[str, Any]:
    registry = private_registry_dir.resolve()
    if not registry.exists():
        raise RasterIngestError("private_registry_missing")
    if registry.is_symlink() or not registry.is_dir():
        raise RasterIngestError("private_registry_not_real_directory")
    if tombstone_path.exists() and not force:
        raise RasterIngestError("tombstone_exists")
    tombstone_path.parent.mkdir(parents=True, exist_ok=True)

    managed_names = (
        "private_ingest_record.json",
        "lifecycle_journal.json",
        "normalization_record.json",
        "raster_quality.json",
    )
    deleted: list[str] = []
    already_absent: list[str] = []
    failures: list[dict[str, str]] = []
    record_id = "capture.raster_fixture.unknown"
    record_path = registry / "private_ingest_record.json"
    if record_path.is_file():
        record = read_json(record_path)
        if isinstance(record, dict):
            record_id = _string(record.get("recordId"), record_id)
    for name in managed_names:
        path = registry / name
        try:
            if not _is_relative_to(path.resolve(strict=False), registry):
                failures.append({"artifactId": name, "code": "path_escape_rejected"})
                continue
            if path.exists():
                if path.is_symlink() or path.is_dir():
                    failures.append({"artifactId": name, "code": "unexpected_artifact_kind"})
                    continue
                path.unlink()
                deleted.append(name)
            else:
                already_absent.append(name)
        except OSError:
            failures.append({"artifactId": name, "code": "delete_failed"})

    status = "deleted" if not failures else "partial_failure"
    tombstone: dict[str, Any] = {
        "schemaVersion": 1,
        "tombstoneId": f"tombstone.{_safe_id(record_id)}",
        "recordVersion": RASTER_DELETION_VERSION,
        "recordId": record_id,
        "profile": RASTER_FIXTURE_PROFILE,
        "fixedTimestamp": FIXED_TIMESTAMP,
        "status": status,
        "deletedArtifactCount": len(deleted),
        "alreadyAbsentCount": len(already_absent),
        "failureCount": len(failures),
        "deletedArtifactIds": deleted,
        "alreadyAbsentArtifactIds": already_absent,
        "failures": failures,
        "policy": {
            "rawSourceBytesCopiedByForge": False,
            "userOwnedOriginalDeleted": False,
            "userOwnedOriginalAction": "not_applicable_project_fixture",
            "retainsRecoverableSourceIdentifiers": False,
        },
        "integrity": {"tombstoneHash": ""},
    }
    tombstone["integrity"]["tombstoneHash"] = hash_raster_tombstone(tombstone)
    write_canonical_json(tombstone_path, tombstone)
    return {
        "status": status,
        "recordId": record_id,
        "deletedArtifactCount": len(deleted),
        "alreadyAbsentCount": len(already_absent),
        "failureCount": len(failures),
    }


def hash_raster_ingest_record(record: dict[str, Any]) -> str:
    payload = deepcopy(record)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["sourceRecordHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def hash_raster_tombstone(tombstone: dict[str, Any]) -> str:
    payload = deepcopy(tombstone)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["tombstoneHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _load_fixture_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RasterIngestError("fixture_manifest_missing")
    manifest = read_json(path)
    if not isinstance(manifest, dict):
        raise RasterIngestError("fixture_manifest_invalid")
    if manifest.get("profile") != RASTER_FIXTURE_PROFILE:
        raise RasterIngestError("unsupported_capture_profile")
    if manifest.get("schemaVersion") != 1:
        raise RasterIngestError("unsupported_fixture_manifest_schema")
    if not _string(manifest.get("manifestId"), ""):
        raise RasterIngestError("fixture_manifest_id_missing")
    _validate_policy(manifest)
    return manifest


def _validate_policy(manifest: dict[str, Any]) -> None:
    policy = _mapping(manifest.get("policy"))
    if policy.get("reconstructionConsent") != "not_required_project_fixture":
        raise RasterIngestError("missing_reconstruction_consent")
    if policy.get("rightsClassification") != "not_required_project_fixture":
        raise RasterIngestError("missing_fixture_rights_review")
    if policy.get("allowTrainingUse", False) is not False:
        raise RasterIngestError("training_use_forbidden")
    if policy.get("allowExternalApis", False) is not False:
        raise RasterIngestError("external_provider_use_forbidden")
    if policy.get("allowNetwork", False) is not False:
        raise RasterIngestError("network_use_forbidden")
    if policy.get("containsUserImagery", True) is not False:
        raise RasterIngestError("user_capture_profile_disabled")
    if policy.get("retentionPolicy") != "generated_fixture_ephemeral":
        raise RasterIngestError("unsupported_retention_policy")


def _policy_record(manifest: dict[str, Any]) -> dict[str, Any]:
    policy = _mapping(manifest.get("policy"))
    return {
        "profile": RASTER_FIXTURE_PROFILE,
        "containsUserImagery": False,
        "containsPersonalBodyData": False,
        "reconstructionConsent": "not_required_project_fixture",
        "rightsClassification": "not_required_project_fixture",
        "allowTrainingUse": False,
        "allowExternalApis": False,
        "allowNetwork": False,
        "retentionPolicy": _string(policy.get("retentionPolicy"), "generated_fixture_ephemeral"),
        "sourceCopiesPolicy": "do_not_copy_raw_images_to_portable_package",
        "sensitiveDataClassification": "project_authored_non_person_fixture",
        "realUserProcessingGate": "Gate P1 not complete; disabled",
    }


def _fixture_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise RasterIngestError("fixture_manifest_has_no_fixtures")
    entries: list[dict[str, Any]] = []
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            raise RasterIngestError("fixture_entry_invalid")
        if fixture.get("rightsClassification") != "not_required_project_fixture":
            raise RasterIngestError("fixture_rights_review_missing")
        entries.append(fixture)
    return entries


def _accepted_source(entry: dict[str, Any], root: Path) -> dict[str, Any]:
    fixture_id = _required_safe_text(entry, "fixtureId")
    view_id = _required_safe_text(entry, "viewId")
    declared_mime = _required_safe_text(entry, "declaredMime")
    expected_hash = _required_safe_text(entry, "expectedSha256")
    path = _fixture_path(root, _required_safe_text(entry, "relativePath"))
    audit = inspect_raster(path, declared_mime=declared_mime)
    if audit["sourceByteSha256"] != expected_hash:
        raise RasterIngestError("fixture_hash_mismatch")
    expected_decoded = entry.get("expectedDecodedContentHash")
    if (
        isinstance(expected_decoded, str)
        and expected_decoded
        and audit["decodedContentSha256"] != expected_decoded
    ):
        raise RasterIngestError("fixture_decoded_hash_mismatch")
    source_id = f"source.{_safe_id(fixture_id)}"
    return {
        "sourceId": source_id,
        "fixtureId": fixture_id,
        "viewId": view_id,
        "redactedDisplayName": f"fixture:{fixture_id}",
        "sourceFilenameStored": False,
        "absolutePathStored": False,
        "sourceByteLength": audit["sourceByteLength"],
        "verifiedMime": audit["verifiedMime"],
        "declaredMime": declared_mime,
        "extension": audit["extension"],
        "decodedDimensions": audit["decodedDimensions"],
        "normalizedDimensions": audit["normalizedDimensions"],
        "exifOrientation": audit["exifOrientation"],
        "sourceByteSha256": audit["sourceByteSha256"],
        "decodedContentSha256": audit["decodedContentSha256"],
        "decodedContentHashPolicy": audit["decodedContentHashPolicy"],
        "decoder": audit["decoder"],
        "colorPolicy": audit["colorPolicy"],
        "alphaPolicy": audit["alphaPolicy"],
        "pixelStats": audit["pixelStats"],
        "warnings": audit["warnings"],
    }


def inspect_raster(path: Path, *, declared_mime: str) -> dict[str, Any]:
    if declared_mime not in SUPPORTED_MIMES:
        raise RasterIngestError("unsupported_declared_mime")
    _ensure_regular_fixture_file(path)
    suffix = path.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise RasterIngestError("unsupported_extension")
    if declared_mime == "image/png" and suffix != ".png":
        raise RasterIngestError("extension_mime_mismatch")
    if declared_mime == "image/jpeg" and suffix not in {".jpg", ".jpeg"}:
        raise RasterIngestError("extension_mime_mismatch")
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise RasterIngestError("file_too_large")
    data = path.read_bytes()
    detected_mime = _detect_mime(data)
    if detected_mime != declared_mime:
        raise RasterIngestError("magic_mime_mismatch")
    if detected_mime == "image/png":
        parsed = _parse_png(data)
    elif detected_mime == "image/jpeg":
        parsed = _parse_jpeg(data)
    else:
        raise RasterIngestError("unsupported_magic")
    _check_dimensions(
        int(parsed["decodedDimensions"]["width"]),
        int(parsed["decodedDimensions"]["height"]),
    )
    source_hash = sha256_file(path)
    decoded_payload = {
        "decodedDimensions": parsed["decodedDimensions"],
        "mime": detected_mime,
        "normalizedDimensions": parsed["normalizedDimensions"],
        "pixelHash": parsed["pixelHash"],
        "policy": parsed["decodedContentHashPolicy"],
    }
    return {
        "sourceByteLength": size,
        "sourceByteSha256": source_hash,
        "verifiedMime": detected_mime,
        "extension": suffix,
        "decodedContentSha256": sha256_bytes(
            b"CLOSY_RASTER_DECODED_CONTENT_V1" + canonical_dumps(decoded_payload).encode("utf-8")
        ),
        **parsed,
    }


def decode_raster_fixture_pixels(path: Path, *, declared_mime: str) -> DecodedRasterPixels:
    """Decode approved fixture PNG/JPEG pixels under the shared byte/pixel limits."""

    audit = inspect_raster(path, declared_mime=declared_mime)
    data = path.read_bytes()
    if audit["verifiedMime"] == "image/png":
        chunks = _png_chunks(data)
        width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
            ">IIBBBBB", chunks[0][1]
        )
        if bit_depth != 8 or color_type not in {0, 2, 4, 6}:
            raise RasterIngestError("unsupported_png_color_type_or_bit_depth")
        if compression != 0 or filter_method != 0 or interlace != 0:
            raise RasterIngestError("unsupported_png_compression_or_filter")
        rgba = _decode_png_rgba(chunks, width, height, color_type)
        pixel_hash = sha256_bytes(b"CLOSY_PNG_RGBA_V1" + rgba)
    elif audit["verifiedMime"] == "image/jpeg":
        decoded = _decode_jpeg_rgba(data)
        width = decoded["width"]
        height = decoded["height"]
        rgba = decoded["rgba"]
        pixel_hash = sha256_bytes(b"CLOSY_JPEG_RGBA_V1" + rgba)
    else:
        raise RasterIngestError("decoded_pixels_unavailable_for_mime")
    if pixel_hash != audit["pixelHash"]:
        raise RasterIngestError("decoded_pixel_hash_mismatch")
    return DecodedRasterPixels(
        width=width,
        height=height,
        mime=str(audit["verifiedMime"]),
        rgba=rgba,
        pixel_hash=pixel_hash,
        decoded_content_sha256=str(audit["decodedContentSha256"]),
    )


def _parse_png(data: bytes) -> dict[str, Any]:
    if not data.startswith(_PNG_SIGNATURE):
        raise RasterIngestError("bad_png_magic")
    chunks = _png_chunks(data)
    if not chunks or chunks[0][0] != b"IHDR":
        raise RasterIngestError("png_missing_ihdr")
    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1]
    )
    _check_dimensions(width, height)
    if compression != 0 or filter_method != 0:
        raise RasterIngestError("unsupported_png_compression_or_filter")
    if interlace != 0:
        raise RasterIngestError("animated_or_multipage_rejected")
    chunk_names = {name for name, _payload in chunks}
    if b"acTL" in chunk_names:
        raise RasterIngestError("animated_or_multipage_rejected")
    if b"iCCP" in chunk_names:
        raise RasterIngestError("unsupported_color_profile")
    pixel_hash = ""
    pixel_stats: dict[str, Any]
    if bit_depth == 8 and color_type in {0, 2, 4, 6}:
        rgba = _decode_png_rgba(chunks, width, height, color_type)
        pixel_hash = sha256_bytes(b"CLOSY_PNG_RGBA_V1" + rgba)
        pixel_stats = _pixel_stats_from_rgba(rgba, width, height)
    else:
        raise RasterIngestError("unsupported_png_color_type_or_bit_depth")
    return {
        "decodedDimensions": {"width": width, "height": height},
        "normalizedDimensions": {"width": width, "height": height},
        "exifOrientation": 1,
        "pixelHash": pixel_hash,
        "decodedContentHashPolicy": "decoded_rgba_pixels_metadata_stripped",
        "decoder": {
            "name": "closy_stdlib_png_decoder",
            "version": "v1",
            "dependency": "python-stdlib-zlib",
            "colorSpacePolicy": "reject_icc_profiles_accept_8bit_srgb_or_unspecified",
        },
        "colorPolicy": {
            "profile": "srgb_or_unspecified",
            "metadataStripped": True,
            "unsupportedProfilesRejected": True,
        },
        "alphaPolicy": {
            "mode": "retain_alpha_for_evidence_hash_and_quality",
            "compositeBackground": None,
        },
        "pixelStats": pixel_stats,
        "warnings": [],
    }


def _parse_jpeg(data: bytes) -> dict[str, Any]:
    decoded = _decode_jpeg_rgba(data)
    rgba = decoded["rgba"]
    width = decoded["width"]
    height = decoded["height"]
    return {
        "decodedDimensions": {
            "width": decoded["sourceWidth"],
            "height": decoded["sourceHeight"],
        },
        "normalizedDimensions": {"width": width, "height": height},
        "exifOrientation": decoded["orientation"],
        "pixelHash": sha256_bytes(b"CLOSY_JPEG_RGBA_V1" + rgba),
        "decodedContentHashPolicy": "normalized_exif_transposed_rgba8_sha256",
        "decoder": {
            "name": "Pillow",
            "version": "v1",
            "dependency": "Pillow==11.1.0",
            "colorSpacePolicy": "reject_icc_profiles_no_os_color_management",
        },
        "colorPolicy": {
            "profile": "srgb_or_unspecified",
            "metadataStripped": True,
            "unsupportedProfilesRejected": True,
        },
        "alphaPolicy": {"mode": "opaque_jpeg", "compositeBackground": None},
        "pixelStats": _pixel_stats_from_rgba(rgba, width, height),
        "warnings": [],
    }


def _decode_jpeg_rgba(data: bytes) -> dict[str, Any]:
    if not data.startswith(_JPEG_SIGNATURE):
        raise RasterIngestError("bad_jpeg_magic")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != "JPEG":
                    raise RasterIngestError("bad_jpeg_magic")
                if int(getattr(image, "n_frames", 1)) != 1:
                    raise RasterIngestError("animated_or_multipage_rejected")
                source_width, source_height = image.size
                _check_dimensions(source_width, source_height)
                if image.info.get("icc_profile"):
                    raise RasterIngestError("unsupported_color_profile")
                orientation = int(image.getexif().get(0x0112, 1))
                if orientation not in range(1, 9):
                    raise RasterIngestError("invalid_exif_orientation")
                normalized = ImageOps.exif_transpose(image)
                if normalized is None:
                    raise RasterIngestError("jpeg_pixel_decode_failed")
                width, height = normalized.size
                _check_dimensions(width, height)
                if width * height * 4 > MAX_DECOMPRESSED_BYTES:
                    raise RasterIngestError("decompression_limit_exceeded")
                rgba = normalized.convert("RGBA").tobytes()
    except RasterIngestError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise RasterIngestError("decompression_limit_exceeded") from error
    except (OSError, ValueError) as error:
        raise RasterIngestError("jpeg_pixel_decode_failed") from error
    if len(rgba) != width * height * 4:
        raise RasterIngestError("jpeg_pixel_decode_failed")
    return {
        "height": height,
        "orientation": orientation,
        "rgba": rgba,
        "sourceHeight": source_height,
        "sourceWidth": source_width,
        "width": width,
    }


def _png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    chunks: list[tuple[bytes, bytes]] = []
    index = len(_PNG_SIGNATURE)
    saw_iend = False
    while index < len(data):
        if index + 12 > len(data):
            raise RasterIngestError("truncated_png")
        length = int.from_bytes(data[index : index + 4], "big")
        name = data[index + 4 : index + 8]
        payload_start = index + 8
        payload_end = payload_start + length
        crc_end = payload_end + 4
        if crc_end > len(data):
            raise RasterIngestError("truncated_png")
        payload = data[payload_start:payload_end]
        expected_crc = int.from_bytes(data[payload_end:crc_end], "big")
        actual_crc = binascii.crc32(name + payload) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise RasterIngestError("corrupt_png_crc")
        chunks.append((name, payload))
        index = crc_end
        if name == b"IEND":
            saw_iend = True
            break
    if not saw_iend or index != len(data):
        raise RasterIngestError("truncated_png")
    return chunks


def _decode_png_rgba(
    chunks: list[tuple[bytes, bytes]], width: int, height: int, color_type: int
) -> bytes:
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    row_length = width * channels
    expected_length = (row_length + 1) * height
    if expected_length > MAX_DECOMPRESSED_BYTES:
        raise RasterIngestError("decompression_limit_exceeded")
    compressed = b"".join(payload for name, payload in chunks if name == b"IDAT")
    if not compressed:
        raise RasterIngestError("png_missing_idat")
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(compressed, expected_length + 1)
    if len(raw) != expected_length or not decompressor.eof:
        raise RasterIngestError("decompression_limit_exceeded")
    if decompressor.unused_data or decompressor.unconsumed_tail:
        raise RasterIngestError("decompression_trailing_data")
    output = bytearray(width * height * 4)
    previous = bytearray(row_length)
    offset = 0
    out_offset = 0
    for _row in range(height):
        filter_type = raw[offset]
        offset += 1
        encoded = bytearray(raw[offset : offset + row_length])
        offset += row_length
        decoded = _apply_png_filter(encoded, previous, channels, filter_type)
        previous = decoded
        for column in range(width):
            source = column * channels
            r, g, b, a = _rgba_from_png_sample(decoded[source : source + channels], color_type)
            output[out_offset : out_offset + 4] = bytes((r, g, b, a))
            out_offset += 4
    return bytes(output)


def _apply_png_filter(
    encoded: bytearray, previous: bytearray, bytes_per_pixel: int, filter_type: int
) -> bytearray:
    decoded = bytearray(len(encoded))
    for index, value in enumerate(encoded):
        left = decoded[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        up = previous[index] if index < len(previous) else 0
        up_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        if filter_type == 0:
            predictor = 0
        elif filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = up
        elif filter_type == 3:
            predictor = (left + up) // 2
        elif filter_type == 4:
            predictor = _paeth(left, up, up_left)
        else:
            raise RasterIngestError("unsupported_png_filter")
        decoded[index] = (value + predictor) & 0xFF
    return decoded


def _rgba_from_png_sample(sample: bytearray, color_type: int) -> tuple[int, int, int, int]:
    if color_type == 0:
        gray = sample[0]
        return gray, gray, gray, 255
    if color_type == 2:
        return sample[0], sample[1], sample[2], 255
    if color_type == 4:
        gray = sample[0]
        return gray, gray, gray, sample[1]
    return sample[0], sample[1], sample[2], sample[3]


def _pixel_stats_from_rgba(rgba: bytes, width: int, height: int) -> dict[str, Any]:
    pixel_count = width * height
    luminance_values: list[float] = []
    transparent = 0
    highlight = 0
    shadow = 0
    for index in range(0, len(rgba), 4):
        red = rgba[index]
        green = rgba[index + 1]
        blue = rgba[index + 2]
        alpha = rgba[index + 3]
        luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255.0
        luminance_values.append(luminance)
        if alpha < 250:
            transparent += 1
        if luminance >= 0.985:
            highlight += 1
        if luminance <= 0.015:
            shadow += 1
    mean = sum(luminance_values) / pixel_count
    variance = sum((value - mean) ** 2 for value in luminance_values) / pixel_count
    sharpness = _sharpness_score(luminance_values, width, height)
    transparent_fraction = transparent / pixel_count
    foreground_fraction = (
        1.0 - transparent_fraction if transparent else _foreground_fraction(luminance_values)
    )
    clipping_fraction = (highlight + shadow) / pixel_count
    exposure_score = _clamp(1.0 - abs(mean - 0.52) * 1.4 - clipping_fraction * 1.8)
    return {
        "available": True,
        "luminanceMean": _round(mean),
        "luminanceStdDev": _round(math.sqrt(variance)),
        "shadowClipFraction": _round(shadow / pixel_count),
        "highlightClipFraction": _round(highlight / pixel_count),
        "combinedClipFraction": _round(clipping_fraction),
        "exposureScore": _round(exposure_score),
        "sharpnessScore": _round(sharpness),
        "alphaTransparentFraction": _round(transparent_fraction),
        "foregroundCoverage": _round(foreground_fraction),
        "effectiveResolutionScore": _round(_effective_resolution_score(width, height)),
    }


def _sharpness_score(values: list[float], width: int, height: int) -> float:
    if width < 2 or height < 2:
        return 0.0
    total = 0.0
    count = 0
    for y in range(height):
        row = y * width
        for x in range(width):
            value = values[row + x]
            if x + 1 < width:
                total += abs(value - values[row + x + 1])
                count += 1
            if y + 1 < height:
                total += abs(value - values[row + width + x])
                count += 1
    return _clamp((total / max(1, count)) * 7.5)


def _foreground_fraction(values: list[float]) -> float:
    if not values:
        return 0.0
    background = values[0]
    different = sum(1 for value in values if abs(value - background) > 0.035)
    return different / len(values)


def _quality_report(
    quality_id: str, private_record: dict[str, Any], normalization_record: dict[str, Any]
) -> dict[str, Any]:
    source_hash = str(private_record["integrity"]["sourceRecordHash"])
    view_scores = [_raster_view_quality(source) for source in private_record["acceptedSources"]]
    score = sum(view["score"] for view in view_scores) / max(1, len(view_scores))
    duplicate_groups = _decoded_duplicate_groups(private_record["acceptedSources"])
    duplicate_penalty = 0.08 if duplicate_groups else 0.0
    overall_score = _round(_clamp(score - duplicate_penalty))
    report = {
        "schemaVersion": 1,
        "qualityReportId": quality_id,
        "scorerVersion": RASTER_QUALITY_SCORER_VERSION,
        "sourceRecordId": private_record["recordId"],
        "sourceRecordHash": source_hash,
        "normalizationRecordId": normalization_record["normalizationRecordId"],
        "normalizationRecordHash": normalization_record["integrity"]["normalizationRecordHash"],
        "overallStatus": "pass" if overall_score >= 0.7 else "fail",
        "overallScore": overall_score,
        "qualityThreshold": 0.7,
        "viewCount": len(view_scores),
        "viewScores": view_scores,
        "aggregate": {
            "pixelDerivedViewCount": sum(
                1
                for source in private_record["acceptedSources"]
                if source["pixelStats"]["available"]
            ),
            "jpegPixelDecodedViewCount": sum(
                1
                for source in private_record["acceptedSources"]
                if source["verifiedMime"] == "image/jpeg" and source["pixelStats"]["available"]
            ),
            "duplicateDecodedHashGroups": duplicate_groups,
        },
        "policy": {
            "requiresUserConsent": False,
            "profile": RASTER_FIXTURE_PROFILE,
            "externalApiUseAllowed": False,
            "trainingUseAllowed": False,
            "rasterImagesAvailable": True,
            "realUserProcessingEnabled": False,
        },
        "warnings": _quality_warnings(private_record["acceptedSources"]),
        "integrity": {"qualityReportHash": ""},
    }
    report["integrity"]["qualityReportHash"] = _hash_with_blank(report, "qualityReportHash")
    return report


def _raster_view_quality(source: dict[str, Any]) -> dict[str, Any]:
    stats = _mapping(source.get("pixelStats"))
    dimensions = _mapping(source.get("normalizedDimensions"))
    width = _integer(dimensions.get("width"), 0)
    height = _integer(dimensions.get("height"), 0)
    resolution = _effective_resolution_score(width, height)
    metrics: dict[str, float | None]
    if stats.get("available") is True:
        exposure = _number(stats.get("exposureScore"), 0.0)
        sharpness = _number(stats.get("sharpnessScore"), 0.0)
        alpha_anomaly = _clamp(_number(stats.get("alphaTransparentFraction"), 0.0) * 2.5)
        foreground = _number(stats.get("foregroundCoverage"), 0.0)
        framing = _clamp(1.0 - abs(foreground - 0.55) * 1.5)
        score = (
            exposure * 0.25
            + sharpness * 0.20
            + resolution * 0.20
            + (1.0 - alpha_anomaly) * 0.15
            + framing * 0.20
        )
        metrics = {
            "exposure": _round(exposure),
            "sharpness": _round(sharpness),
            "effectiveResolution": _round(resolution),
            "alphaBackgroundSafety": _round(1.0 - alpha_anomaly),
            "cropFraming": _round(framing),
        }
    else:
        score = resolution * 0.82
        metrics = {
            "exposure": None,
            "sharpness": None,
            "effectiveResolution": _round(resolution),
            "alphaBackgroundSafety": None,
            "cropFraming": None,
        }
    return {
        "sourceId": source["sourceId"],
        "viewId": source["viewId"],
        "score": _round(_clamp(score)),
        "status": "pass" if score >= 0.7 else "warn" if score >= 0.55 else "fail",
        "pixelDerived": stats.get("available") is True,
        "metrics": metrics,
        "warnings": source.get("warnings", []),
    }


def _normalization_record(normalization_id: str, private_record: dict[str, Any]) -> dict[str, Any]:
    source_hash = str(private_record["integrity"]["sourceRecordHash"])
    outputs = [
        {
            "sourceId": source["sourceId"],
            "viewId": source["viewId"],
            "evidenceRepresentation": {
                "retainsShapeAndLightingCues": True,
                "metadataStripped": True,
                "dimensions": source["decodedDimensions"],
                "privateDecodedContentHash": source["decodedContentSha256"],
            },
            "normalizedRepresentation": {
                "exifOrientationApplied": source["exifOrientation"] != 1,
                "dimensions": source["normalizedDimensions"],
                "privateNormalizedContentHash": source["decodedContentSha256"],
                "cropPaddingPolicy": "no_crop_no_padding_in_d0_fixture_profile",
                "colorPolicy": source["colorPolicy"],
                "alphaPolicy": source["alphaPolicy"],
            },
            "transforms": _normalization_transforms(source),
        }
        for source in private_record["acceptedSources"]
    ]
    record = {
        "schemaVersion": 1,
        "normalizationRecordId": normalization_id,
        "recordVersion": RASTER_NORMALIZATION_VERSION,
        "sourceRecordId": private_record["recordId"],
        "sourceRecordHash": source_hash,
        "profile": RASTER_FIXTURE_PROFILE,
        "outputs": outputs,
        "policy": {
            "evidenceRepresentationPreserved": True,
            "visualNormalizationAggressiveCleanup": False,
            "metadataStripped": True,
            "volatilePathsExcluded": True,
        },
        "integrity": {"normalizationRecordHash": ""},
    }
    record["integrity"]["normalizationRecordHash"] = _hash_with_blank(
        record, "normalizationRecordHash"
    )
    return record


def _normalization_transforms(source: dict[str, Any]) -> list[dict[str, Any]]:
    transforms = [
        {
            "operation": "verify_magic_mime_extension",
            "inputDimensions": source["decodedDimensions"],
            "outputDimensions": source["decodedDimensions"],
        },
        {
            "operation": "strip_metadata_for_portable_outputs",
            "inputDimensions": source["decodedDimensions"],
            "outputDimensions": source["decodedDimensions"],
        },
    ]
    if source["exifOrientation"] != 1:
        transforms.append(
            {
                "operation": "apply_exif_orientation_dimensions",
                "exifOrientation": source["exifOrientation"],
                "inputDimensions": source["decodedDimensions"],
                "outputDimensions": source["normalizedDimensions"],
            }
        )
    return transforms


def _lifecycle_journal(journal_id: str, private_record: dict[str, Any]) -> dict[str, Any]:
    journal = {
        "schemaVersion": 1,
        "journalId": journal_id,
        "recordVersion": RASTER_LIFECYCLE_VERSION,
        "sourceRecordId": private_record["recordId"],
        "sourceRecordHash": private_record["integrity"]["sourceRecordHash"],
        "profile": RASTER_FIXTURE_PROFILE,
        "events": [
            {
                "eventId": "event.0001.ingested",
                "eventKind": "ingested",
                "fixedTimestamp": FIXED_TIMESTAMP,
                "actorClass": "forge_cli",
                "policySnapshot": private_record["policy"],
                "mutableStateChangedByAppendOnlyEvent": True,
            }
        ],
        "integrity": {"journalHash": ""},
    }
    journal["integrity"]["journalHash"] = _hash_with_blank(journal, "journalHash")
    return journal


def _portable_source_summary(portable_id: str, private_record: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "schemaVersion": 1,
        "portableSourceSummaryId": portable_id,
        "recordVersion": "closy.raster_portable_source_summary.v1",
        "sourceRecordId": private_record["recordId"],
        "profile": RASTER_FIXTURE_PROFILE,
        "sources": [
            {
                "opaqueSourceRef": f"source_ref.{index:04d}",
                "viewId": source["viewId"],
                "verifiedMime": source["verifiedMime"],
                "normalizedDimensions": source["normalizedDimensions"],
                "sourceFilenameExposed": False,
                "absolutePathExposed": False,
                "rawBytesExposed": False,
                "sourceByteHashExposed": False,
                "decodedContentHashExposed": False,
                "exifExposed": False,
            }
            for index, source in enumerate(private_record["acceptedSources"], start=1)
        ],
        "privacy": {
            "containsUserImagery": False,
            "portablePackageSafe": True,
            "revocableOpaqueReferencesOnly": True,
            "rawSourceBytesCopied": False,
            "externalApiUseAllowed": False,
            "trainingUseAllowed": False,
        },
        "integrity": {"portableSourceSummaryHash": ""},
    }
    summary["integrity"]["portableSourceSummaryHash"] = _hash_with_blank(
        summary, "portableSourceSummaryHash"
    )
    return summary


def _privacy_report(
    private_record: dict[str, Any],
    normalization_record: dict[str, Any],
    quality_report: dict[str, Any],
) -> dict[str, Any]:
    report = {
        "schemaVersion": 1,
        "privacyReportId": f"privacy_report.{_safe_id(str(private_record['recordId']))}",
        "recordVersion": "closy.raster_privacy_report.v1",
        "profile": RASTER_FIXTURE_PROFILE,
        "sourceRecordId": private_record["recordId"],
        "normalizationRecordId": normalization_record["normalizationRecordId"],
        "qualityReportId": quality_report["qualityReportId"],
        "gateP1": {
            "status": "not_complete",
            "realUserRasterProcessingEnabled": False,
        },
        "threatModel": {
            "identityFaceBodyHomeInteriorLeakage": "fail_closed_by_fixture_profile_only",
            "exifLocationDeviceTimeLeakage": "metadata_stripped_not_portable",
            "absolutePathOrFilenameLeakage": "not_recorded",
            "rawByteFingerprintsInPortablePackages": "excluded",
            "logsExceptionsSnapshotsCiArtifacts": "redacted_errors_and_ci_rejections",
            "decompressionBombsMalformedInputs": "bounded_decoder_rejections",
            "symlinkHardlinkTraversal": "rejected",
            "networkProviderUpload": "disabled",
            "defaultTrainingUse": "false",
            "deletionPropagation": "private_registry_tombstone_flow",
            "contentAddressedCacheRetention": "no_raw_cache_in_d0_profile",
            "duplicateSourceCorrelation": "private_registry_only_duplicate_detection",
        },
        "portableExclusions": private_record["portablePackageExclusions"],
        "capabilities": {
            "localRasterFixtureIngestion": True,
            "pixelDerivedCaptureQuality": True,
            "privateSourceRegistry": True,
            "sourceDeletionTombstoneFlow": True,
            "realUserCaptureReady": False,
            "externalProviderUploadReady": False,
        },
        "integrity": {"privacyReportHash": ""},
    }
    report["integrity"]["privacyReportHash"] = _hash_with_blank(report, "privacyReportHash")
    return report


def _decoded_duplicate_groups(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter(str(source["decodedContentSha256"]) for source in sources)
    groups = []
    for digest, count in sorted(counts.items()):
        if count > 1:
            groups.append(
                {
                    "privateDecodedContentHash": digest,
                    "count": count,
                    "sourceIds": [
                        source["sourceId"]
                        for source in sources
                        if source["decodedContentSha256"] == digest
                    ],
                }
            )
    return groups


def _quality_warnings(sources: list[dict[str, Any]]) -> list[str]:
    warnings = sorted({warning for source in sources for warning in source.get("warnings", [])})
    if not any(source["pixelStats"]["available"] for source in sources):
        warnings.append("no_pixel_derived_views_available")
    return warnings


def _detect_mime(data: bytes) -> str:
    if data.startswith(_PNG_SIGNATURE):
        return "image/png"
    if data.startswith(_JPEG_SIGNATURE):
        return "image/jpeg"
    raise RasterIngestError("bad_magic")


def _approved_root(input_root: Path) -> Path:
    root = input_root.resolve()
    if root.is_symlink() or not root.is_dir():
        raise RasterIngestError("input_root_invalid")
    return root


def _fixture_path(root: Path, relative_text: str) -> Path:
    if "\\" in relative_text or ":" in relative_text or relative_text.startswith("/"):
        raise RasterIngestError("path_traversal_rejected")
    relative = Path(relative_text)
    if relative.is_absolute() or any(part in {"..", ""} for part in relative.parts):
        raise RasterIngestError("path_traversal_rejected")
    candidate = root / relative
    resolved = candidate.resolve(strict=False)
    if not _is_relative_to(resolved, root):
        raise RasterIngestError("path_traversal_rejected")
    return candidate


def _ensure_regular_fixture_file(path: Path) -> None:
    if path.is_symlink():
        raise RasterIngestError("symlink_rejected")
    if not path.exists():
        raise RasterIngestError("source_file_missing")
    if not path.is_file():
        raise RasterIngestError("source_file_not_regular")
    if path.stat().st_nlink > 1:
        raise RasterIngestError("hardlink_rejected")


def _reject_duplicate_sources(sources: list[dict[str, Any]]) -> None:
    counts = Counter(str(source["sourceByteSha256"]) for source in sources)
    if any(count > 1 for count in counts.values()):
        raise RasterIngestError("duplicate_source_hash")


def _check_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise RasterIngestError("invalid_dimensions")
    if width > MAX_DIMENSION_PX or height > MAX_DIMENSION_PX:
        raise RasterIngestError("dimension_limit_exceeded")
    if width * height > MAX_PIXEL_COUNT:
        raise RasterIngestError("pixel_count_limit_exceeded")


def _paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    left_delta = abs(estimate - left)
    up_delta = abs(estimate - up)
    up_left_delta = abs(estimate - up_left)
    if left_delta <= up_delta and left_delta <= up_left_delta:
        return left
    if up_delta <= up_left_delta:
        return up
    return up_left


def _required_safe_text(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise RasterIngestError(f"{key}_missing")
    return value


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _string(value: object, fallback: str) -> str:
    return value if isinstance(value, str) else fallback


def _integer(value: object, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback


def _number(value: object, fallback: float) -> float:
    return (
        float(value) if isinstance(value, int | float) and not isinstance(value, bool) else fallback
    )


def _safe_id(value: str) -> str:
    cleaned = _SAFE_ID_RE.sub("_", value.strip()).strip("._-")
    return cleaned or "unknown"


def _hash_with_blank(payload: dict[str, Any], hash_key: str) -> str:
    clone = deepcopy(payload)
    integrity = clone.get("integrity")
    if isinstance(integrity, dict):
        integrity[hash_key] = ""
    return sha256_bytes(canonical_dumps(clone).encode("utf-8"))


def _effective_resolution_score(width: int, height: int) -> float:
    return _clamp((width * height) / (512 * 512))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _round(value: float) -> float:
    return round(value, 6)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
