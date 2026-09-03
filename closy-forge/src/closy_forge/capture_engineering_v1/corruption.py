from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from closy_forge.capture.raster_sources import RasterIngestError, decode_raster_fixture_pixels
from closy_forge.raster.png_codec import encode_png_rgba

from .capture_sources import select_video_frames
from .privacy import (
    PrivacyBoundaryError,
    assert_portable_record,
    sanitize_diagnostic,
    secure_write,
)
from .video_avi import VideoDecodeError, decode_uncompressed_avi, encode_uncompressed_avi


def run_corruption_suite() -> dict[str, Any]:
    rgba = _fixture_rgba(12, 12)
    png = encode_png_rgba(12, 12, rgba)
    avi = encode_uncompressed_avi(12, 12, [rgba, rgba], frames_per_second=2)
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="closy-capture-corruption-") as temporary:
        root = Path(temporary)
        rows.extend(
            (
                _raster_case(root, "raster_bad_signature", b"not-an-image", "image/png"),
                _raster_case(root, "raster_truncated_png", png[:20], "image/png"),
                _raster_case(root, "raster_mime_mismatch", png, "image/jpeg"),
                _raster_case(root, "raster_trailing_bytes", png + b"tail", "image/png"),
                _privacy_case(
                    "portable_absolute_path",
                    {"sourceId": "safe", "absolutePath": "C:\\private\\capture.png"},
                ),
                _privacy_case(
                    "portable_private_hash",
                    {"sourceId": "safe", "sourceByteSha256": "1" * 64},
                ),
                _diagnostic_case(),
                _owned_write_case(root),
                _video_case("video_truncated", avi[:-5]),
                _video_case("video_codec", avi.replace(b"DIB ", b"XVID", 1)),
                _video_case("video_trailing", avi + b"tail"),
                _video_case("video_bad_riff_size", avi[:4] + b"\x01\x00\x00\x00" + avi[8:]),
                _video_case("video_bad_width", _replace_strf_width(avi, 300)),
                _cancel_case(avi),
                _duplicate_frame_case(),
                _raster_case(root, "raster_empty", b"", "image/jpeg"),
            )
        )
    if len(rows) != 16:
        raise ValueError("corruption_denominator_invalid")
    return {
        "schemaVersion": 1,
        "suiteVersion": "closy.capture_engineering.corruption.v1",
        "attemptCount": len(rows),
        "passCount": sum(row["passed"] is True for row in rows),
        "rows": rows,
        "allExpectedOutcomesObserved": all(row["passed"] is True for row in rows),
    }


def _raster_case(root: Path, case_id: str, data: bytes, mime: str) -> dict[str, Any]:
    path = root / f"{case_id}.bin"
    path.write_bytes(data)
    try:
        decode_raster_fixture_pixels(path, declared_mime=mime)
    except RasterIngestError as error:
        return {"caseId": case_id, "passed": True, "outcome": error.code}
    return {"caseId": case_id, "passed": False, "outcome": "unexpected_accept"}


def _privacy_case(case_id: str, record: dict[str, Any]) -> dict[str, Any]:
    try:
        assert_portable_record(record)
    except PrivacyBoundaryError as error:
        return {"caseId": case_id, "passed": True, "outcome": str(error)}
    return {"caseId": case_id, "passed": False, "outcome": "unexpected_accept"}


def _diagnostic_case() -> dict[str, Any]:
    sanitized = sanitize_diagnostic(
        {"errorCode": "decode_failed", "sourceId": "opaque", "absolutePath": "secret"}
    )
    return {
        "caseId": "diagnostic_allowlist",
        "passed": "absolutePath" not in sanitized and sanitized["sourceId"] == "opaque",
        "outcome": "allowlist_applied",
    }


def _owned_write_case(root: Path) -> dict[str, Any]:
    try:
        secure_write(root, "../escape.bin", b"secret")
    except PrivacyBoundaryError as error:
        return {"caseId": "owned_write_escape", "passed": True, "outcome": str(error)}
    return {"caseId": "owned_write_escape", "passed": False, "outcome": "unexpected_accept"}


def _video_case(case_id: str, data: bytes) -> dict[str, Any]:
    try:
        decode_uncompressed_avi(data)
    except VideoDecodeError as error:
        return {"caseId": case_id, "passed": True, "outcome": error.code}
    return {"caseId": case_id, "passed": False, "outcome": "unexpected_accept"}


def _cancel_case(data: bytes) -> dict[str, Any]:
    try:
        decode_uncompressed_avi(data, cancelled=lambda: True)
    except VideoDecodeError as error:
        return {
            "caseId": "video_cancellation",
            "passed": error.code == "video_decode_cancelled",
            "outcome": error.code,
        }
    return {"caseId": "video_cancellation", "passed": False, "outcome": "unexpected_accept"}


def _duplicate_frame_case() -> dict[str, Any]:
    rows = [
        {
            "frameIndex": index,
            "pixelSha256": "same",
            "focusScore": 0.8,
            "foregroundCentroidNormalized": [0.5, 0.5],
        }
        for index in range(3)
    ]
    selected = select_video_frames(rows, maximum_selected=3)
    return {
        "caseId": "video_duplicate_rejection",
        "passed": len(selected) == 1,
        "outcome": "duplicate_rejected" if len(selected) == 1 else "duplicate_accepted",
    }


def _replace_strf_width(data: bytes, width: int) -> bytes:
    result = bytearray(data)
    index = data.find(b"strf")
    if index < 0:
        raise ValueError("test_avi_strf_missing")
    result[index + 12 : index + 16] = int(width).to_bytes(4, "little", signed=True)
    return bytes(result)


def _fixture_rgba(width: int, height: int) -> bytes:
    pixels = bytearray((230, 228, 222, 255) * (width * height))
    for y in range(2, height - 2):
        for x in range(3, width - 3):
            offset = (y * width + x) * 4
            pixels[offset : offset + 4] = bytes((45 + x * 3, 80 + y * 2, 130, 255))
    return bytes(pixels)
