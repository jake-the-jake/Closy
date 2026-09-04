from __future__ import annotations

import io
import struct
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image

from .common import sha256_bytes

DECODER_VERSION = "closy.project_owned_avi_mjpeg.decoder.v2"
MAX_VIDEO_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 512
MAX_FRAMES = 96


class VideoDecodeError(ValueError):
    pass


@dataclass(frozen=True)
class DecodedFrame:
    index: int
    timestampNumerator: int
    timestampDenominator: int
    width: int
    height: int
    rgba: bytes
    pixelSha256: str


@dataclass(frozen=True)
class DecodedVideo:
    width: int
    height: int
    framesPerSecond: int
    frames: tuple[DecodedFrame, ...]
    sourceSha256: str


def encode_mjpeg_avi(
    width: int,
    height: int,
    rgba_frames: Sequence[bytes],
    *,
    frames_per_second: int = 12,
    jpeg_quality: int = 58,
) -> bytes:
    _validate_dimensions(width, height)
    if not 1 <= len(rgba_frames) <= MAX_FRAMES or frames_per_second <= 0:
        raise ValueError("avi_frame_count_or_rate_invalid")
    encoded_frames: list[bytes] = []
    expected = width * height * 4
    for rgba in rgba_frames:
        if len(rgba) != expected:
            raise ValueError("avi_rgba_length_invalid")
        output = io.BytesIO()
        Image.frombytes("RGBA", (width, height), rgba).convert("RGB").save(
            output,
            format="JPEG",
            quality=jpeg_quality,
            optimize=False,
            progressive=False,
            subsampling=2,
        )
        encoded_frames.append(output.getvalue())
    maximum_frame = max(len(frame) for frame in encoded_frames)
    avih = struct.pack(
        "<IIIIIIIIII4I",
        round(1_000_000 / frames_per_second),
        maximum_frame * frames_per_second,
        0,
        0x10,
        len(encoded_frames),
        0,
        1,
        maximum_frame,
        width,
        height,
        0,
        0,
        0,
        0,
    )
    strh = struct.pack(
        "<4s4sIHHIIIIIIIIhhhh",
        b"vids",
        b"MJPG",
        0,
        0,
        0,
        0,
        1,
        frames_per_second,
        0,
        len(encoded_frames),
        maximum_frame,
        0xFFFFFFFF,
        0,
        0,
        0,
        width,
        height,
    )
    strf = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,
        1,
        24,
        struct.unpack("<I", b"MJPG")[0],
        maximum_frame,
        0,
        0,
        0,
        0,
    )
    hdrl = _list_chunk(
        b"hdrl",
        _chunk(b"avih", avih) + _list_chunk(b"strl", _chunk(b"strh", strh) + _chunk(b"strf", strf)),
    )
    movi = _list_chunk(b"movi", b"".join(_chunk(b"00dc", frame) for frame in encoded_frames))
    payload = b"AVI " + hdrl + movi
    encoded = b"RIFF" + struct.pack("<I", len(payload)) + payload
    if len(encoded) > MAX_VIDEO_BYTES:
        raise ValueError("avi_byte_budget_exceeded")
    return encoded


def decode_mjpeg_avi(data: bytes) -> DecodedVideo:
    if len(data) > MAX_VIDEO_BYTES:
        raise VideoDecodeError("video_byte_limit_exceeded")
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"AVI ":
        raise VideoDecodeError("video_container_invalid")
    if _u32(data, 4) + 8 != len(data):
        raise VideoDecodeError("video_riff_length_invalid")
    chunks = _walk_chunks(data, 12, len(data), parent=b"AVI ")
    strh = _first(chunks, b"strh")
    strf = _first(chunks, b"strf")
    frames = [payload for kind, parent, payload in chunks if kind == b"00dc" and parent == b"movi"]
    if strh is None or strf is None or not frames or len(strh) < 48 or len(strf) < 40:
        raise VideoDecodeError("video_required_chunks_missing")
    if strh[:8] != b"vidsMJPG" or _u32(strf, 16) != struct.unpack("<I", b"MJPG")[0]:
        raise VideoDecodeError("video_codec_unsupported")
    scale, rate, declared = _u32(strh, 20), _u32(strh, 24), _u32(strh, 32)
    width, height = _i32(strf, 4), _i32(strf, 8)
    _validate_dimensions(width, height)
    if scale != 1 or rate <= 0 or declared != len(frames) or len(frames) > MAX_FRAMES:
        raise VideoDecodeError("video_header_denominator_invalid")
    decoded: list[DecodedFrame] = []
    for index, payload in enumerate(frames):
        try:
            with Image.open(io.BytesIO(payload)) as image:
                image.load()
                if image.size != (width, height):
                    raise VideoDecodeError("video_frame_dimensions_invalid")
                rgba = image.convert("RGBA").tobytes()
        except OSError as error:
            raise VideoDecodeError("video_frame_decode_failed") from error
        decoded.append(
            DecodedFrame(
                index=index,
                timestampNumerator=index,
                timestampDenominator=rate,
                width=width,
                height=height,
                rgba=rgba,
                pixelSha256=sha256_bytes(rgba),
            )
        )
    return DecodedVideo(width, height, rate, tuple(decoded), sha256_bytes(data))


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return kind + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) % 2 else b"")


def _list_chunk(kind: bytes, payload: bytes) -> bytes:
    return _chunk(b"LIST", kind + payload)


def _walk_chunks(
    data: bytes, start: int, end: int, *, parent: bytes
) -> list[tuple[bytes, bytes, bytes]]:
    rows: list[tuple[bytes, bytes, bytes]] = []
    offset = start
    while offset < end:
        if offset + 8 > end:
            raise VideoDecodeError("video_chunk_header_truncated")
        kind, size = data[offset : offset + 4], _u32(data, offset + 4)
        payload_start, payload_end = offset + 8, offset + 8 + size
        if payload_end > end:
            raise VideoDecodeError("video_chunk_payload_truncated")
        payload = data[payload_start:payload_end]
        if kind == b"LIST":
            if len(payload) < 4:
                raise VideoDecodeError("video_list_truncated")
            rows.extend(_walk_chunks(payload, 4, len(payload), parent=payload[:4]))
        else:
            rows.append((kind, parent, payload))
        offset = payload_end + size % 2
    if offset != end:
        raise VideoDecodeError("video_chunk_alignment_invalid")
    return rows


def _first(chunks: Sequence[tuple[bytes, bytes, bytes]], kind: bytes) -> bytes | None:
    return next((payload for chunk, _parent, payload in chunks if chunk == kind), None)


def _validate_dimensions(width: int, height: int) -> None:
    if width < 256 or height < 256 or width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise VideoDecodeError("video_dimensions_invalid")


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise VideoDecodeError("video_integer_out_of_bounds")
    return int(struct.unpack_from("<I", data, offset)[0])


def _i32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise VideoDecodeError("video_integer_out_of_bounds")
    return int(struct.unpack_from("<i", data, offset)[0])
