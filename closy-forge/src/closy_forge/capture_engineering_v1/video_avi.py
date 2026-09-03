from __future__ import annotations

import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .common import sha256_bytes

DECODER_VERSION = "closy.project_owned_avi_dib.decoder.v1"
DECODER_LICENSE = "MIT; project-owned implementation"
SUPPORTED_CONTAINER = "video/x-msvideo"
SUPPORTED_CODEC = "DIB "

MAX_VIDEO_BYTES = 4_000_000
MAX_WIDTH = 256
MAX_HEIGHT = 256
MAX_FRAMES = 192
MAX_DURATION_SECONDS = 8.0
MAX_DECODED_FRAME_BYTES = 1_048_576


class VideoDecodeError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DecodedVideoFrame:
    index: int
    timestamp_numerator: int
    timestamp_denominator: int
    width: int
    height: int
    rgba: bytes
    pixel_sha256: str


@dataclass(frozen=True)
class DecodedVideo:
    container: str
    codec: str
    decoder_version: str
    decoder_license: str
    width: int
    height: int
    frames_per_second: int
    frames: tuple[DecodedVideoFrame, ...]
    source_byte_sha256: str


def encode_uncompressed_avi(
    width: int,
    height: int,
    rgba_frames: Sequence[bytes],
    *,
    frames_per_second: int = 12,
) -> bytes:
    _validate_dimensions(width, height)
    if not rgba_frames or len(rgba_frames) > MAX_FRAMES:
        raise ValueError("avi_frame_count_invalid")
    if frames_per_second <= 0 or len(rgba_frames) / frames_per_second > MAX_DURATION_SECONDS:
        raise ValueError("avi_duration_invalid")
    expected_rgba = width * height * 4
    row_stride = ((width * 3 + 3) // 4) * 4
    frame_size = row_stride * height
    encoded_frames: list[bytes] = []
    for rgba in rgba_frames:
        if len(rgba) != expected_rgba:
            raise ValueError("avi_rgba_length_invalid")
        encoded_frames.append(_rgba_to_bottom_up_bgr(rgba, width, height, row_stride))

    microseconds = round(1_000_000 / frames_per_second)
    avih = struct.pack(
        "<IIIIIIIIII4I",
        microseconds,
        frame_size * frames_per_second,
        0,
        0x10,
        len(encoded_frames),
        0,
        1,
        frame_size,
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
        b"DIB ",
        0,
        0,
        0,
        0,
        1,
        frames_per_second,
        0,
        len(encoded_frames),
        frame_size,
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
        0,
        frame_size,
        0,
        0,
        0,
        0,
    )
    hdrl = _list_chunk(
        b"hdrl",
        _chunk(b"avih", avih) + _list_chunk(b"strl", _chunk(b"strh", strh) + _chunk(b"strf", strf)),
    )
    movi_payload = b"".join(_chunk(b"00db", frame) for frame in encoded_frames)
    movi = _list_chunk(b"movi", movi_payload)
    riff_payload = b"AVI " + hdrl + movi
    encoded = b"RIFF" + struct.pack("<I", len(riff_payload)) + riff_payload
    if len(encoded) > MAX_VIDEO_BYTES:
        raise ValueError("avi_byte_limit_exceeded")
    return encoded


def decode_uncompressed_avi(
    data: bytes,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> DecodedVideo:
    if len(data) > MAX_VIDEO_BYTES:
        raise VideoDecodeError("video_byte_limit_exceeded")
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"AVI ":
        raise VideoDecodeError("video_container_invalid")
    declared_size = _u32(data, 4)
    if declared_size + 8 != len(data):
        raise VideoDecodeError("video_riff_length_invalid")

    chunks = list(_walk_chunks(data, 12, len(data), parent=b"AVI "))
    avih = _first_payload(chunks, b"avih")
    strh = _first_payload(chunks, b"strh")
    strf = _first_payload(chunks, b"strf")
    frame_payloads = [
        payload for chunk_id, parent, payload in chunks if chunk_id == b"00db" and parent == b"movi"
    ]
    if avih is None or strh is None or strf is None or not frame_payloads:
        raise VideoDecodeError("video_required_chunks_missing")
    if len(avih) < 40 or len(strh) < 48 or len(strf) < 40:
        raise VideoDecodeError("video_header_truncated")
    codec = strh[4:8]
    if strh[:4] != b"vids" or codec != b"DIB ":
        raise VideoDecodeError("video_codec_unsupported")
    scale = _u32(strh, 20)
    rate = _u32(strh, 24)
    declared_frames = _u32(strh, 32)
    width = _i32(strf, 4)
    height = _i32(strf, 8)
    planes, bits = struct.unpack_from("<HH", strf, 12)
    compression = _u32(strf, 16)
    if scale != 1 or rate <= 0 or planes != 1 or bits != 24 or compression != 0:
        raise VideoDecodeError("video_format_unsupported")
    _validate_dimensions(width, height, error_type=VideoDecodeError)
    if declared_frames != len(frame_payloads) or declared_frames > MAX_FRAMES:
        raise VideoDecodeError("video_frame_count_invalid")
    if declared_frames / rate > MAX_DURATION_SECONDS:
        raise VideoDecodeError("video_duration_limit_exceeded")
    row_stride = ((width * 3 + 3) // 4) * 4
    expected_frame_bytes = row_stride * height
    if expected_frame_bytes > MAX_DECODED_FRAME_BYTES:
        raise VideoDecodeError("decoded_frame_limit_exceeded")

    frames: list[DecodedVideoFrame] = []
    for index, payload in enumerate(frame_payloads):
        if cancelled is not None and cancelled():
            raise VideoDecodeError("video_decode_cancelled")
        if len(payload) != expected_frame_bytes:
            raise VideoDecodeError("video_frame_length_invalid")
        rgba = _bottom_up_bgr_to_rgba(payload, width, height, row_stride)
        frames.append(
            DecodedVideoFrame(
                index=index,
                timestamp_numerator=index,
                timestamp_denominator=rate,
                width=width,
                height=height,
                rgba=rgba,
                pixel_sha256=sha256_bytes(rgba),
            )
        )
    return DecodedVideo(
        container=SUPPORTED_CONTAINER,
        codec=SUPPORTED_CODEC,
        decoder_version=DECODER_VERSION,
        decoder_license=DECODER_LICENSE,
        width=width,
        height=height,
        frames_per_second=rate,
        frames=tuple(frames),
        source_byte_sha256=sha256_bytes(data),
    )


def _chunk(kind: bytes, payload: bytes) -> bytes:
    padding = b"\x00" if len(payload) % 2 else b""
    return kind + struct.pack("<I", len(payload)) + payload + padding


def _list_chunk(kind: bytes, payload: bytes) -> bytes:
    return _chunk(b"LIST", kind + payload)


def _walk_chunks(
    data: bytes, start: int, end: int, *, parent: bytes
) -> Sequence[tuple[bytes, bytes, bytes]]:
    result: list[tuple[bytes, bytes, bytes]] = []
    offset = start
    while offset < end:
        if offset + 8 > end:
            raise VideoDecodeError("video_chunk_header_truncated")
        chunk_id = data[offset : offset + 4]
        size = _u32(data, offset + 4)
        payload_start = offset + 8
        payload_end = payload_start + size
        if payload_end > end:
            raise VideoDecodeError("video_chunk_payload_truncated")
        payload = data[payload_start:payload_end]
        if chunk_id == b"LIST":
            if len(payload) < 4:
                raise VideoDecodeError("video_list_truncated")
            result.extend(_walk_chunks(payload, 4, len(payload), parent=payload[:4]))
        else:
            result.append((chunk_id, parent, payload))
        offset = payload_end + (size % 2)
    if offset != end:
        raise VideoDecodeError("video_chunk_alignment_invalid")
    return result


def _first_payload(chunks: Sequence[tuple[bytes, bytes, bytes]], kind: bytes) -> bytes | None:
    return next((payload for chunk_id, _parent, payload in chunks if chunk_id == kind), None)


def _rgba_to_bottom_up_bgr(rgba: bytes, width: int, height: int, stride: int) -> bytes:
    result = bytearray(stride * height)
    for output_row, source_y in enumerate(range(height - 1, -1, -1)):
        for x in range(width):
            source = (source_y * width + x) * 4
            target = output_row * stride + x * 3
            result[target : target + 3] = bytes((rgba[source + 2], rgba[source + 1], rgba[source]))
    return bytes(result)


def _bottom_up_bgr_to_rgba(data: bytes, width: int, height: int, stride: int) -> bytes:
    result = bytearray(width * height * 4)
    for source_row, target_y in enumerate(range(height - 1, -1, -1)):
        for x in range(width):
            source = source_row * stride + x * 3
            target = (target_y * width + x) * 4
            result[target : target + 4] = bytes(
                (data[source + 2], data[source + 1], data[source], 255)
            )
    return bytes(result)


def _validate_dimensions(
    width: int, height: int, *, error_type: type[Exception] = ValueError
) -> None:
    if width <= 0 or height <= 0 or width > MAX_WIDTH or height > MAX_HEIGHT:
        raise error_type("video_dimensions_invalid")


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise VideoDecodeError("video_integer_out_of_bounds")
    return int(struct.unpack_from("<I", data, offset)[0])


def _i32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise VideoDecodeError("video_integer_out_of_bounds")
    return int(struct.unpack_from("<i", data, offset)[0])
