from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class PngCodecError(ValueError):
    """Fail-closed PNG error without source paths or private pixel content."""


@dataclass(frozen=True)
class DecodedPng:
    width: int
    height: int
    rgba: bytes
    color_space: str = "srgb"
    channel_meaning: str = "red_green_blue_alpha_8bit_straight"


def encode_png_rgba(width: int, height: int, rgba: bytes) -> bytes:
    """Encode deterministic non-interlaced RGBA8 PNG bytes using only stdlib."""

    if width <= 0 or height <= 0 or len(rgba) != width * height * 4:
        raise PngCodecError("invalid_rgba_dimensions")
    rows = bytearray()
    stride = width * 4
    for y in range(height):
        rows.append(0)
        start = y * stride
        rows.extend(rgba[start : start + stride])
    return b"".join(
        [
            PNG_MAGIC,
            _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            _chunk(b"sRGB", b"\x00"),
            _chunk(b"IDAT", zlib.compress(bytes(rows), level=9)),
            _chunk(b"IEND", b""),
        ]
    )


def decode_png_rgba(data: bytes) -> DecodedPng:
    """Decode the constrained PNG profile emitted by :func:`encode_png_rgba`."""

    if not data.startswith(PNG_MAGIC):
        raise PngCodecError("bad_png_magic")
    chunks = _chunks(data)
    if any(kind == b"iCCP" for kind, _payload in chunks):
        raise PngCodecError("unsupported_or_unexpected_color_profile")
    srgb = [payload for kind, payload in chunks if kind == b"sRGB"]
    if srgb != [b"\x00"]:
        raise PngCodecError("missing_or_invalid_srgb_profile")
    ihdr = next((payload for kind, payload in chunks if kind == b"IHDR"), None)
    if ihdr is None or len(ihdr) != 13:
        raise PngCodecError("png_missing_ihdr")
    width, height, depth, color_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    if width <= 0 or height <= 0:
        raise PngCodecError("invalid_png_dimensions")
    if (depth, color_type, compression, filter_method, interlace) != (8, 6, 0, 0, 0):
        raise PngCodecError("unsupported_png_profile")
    compressed = b"".join(payload for kind, payload in chunks if kind == b"IDAT")
    if not compressed:
        raise PngCodecError("png_missing_idat")
    try:
        raw = zlib.decompress(compressed)
    except zlib.error as exc:
        raise PngCodecError("corrupt_png_deflate") from exc
    stride = width * 4
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise PngCodecError("png_decoded_length_mismatch")
    output = bytearray()
    previous = bytearray(stride)
    offset = 0
    for _y in range(height):
        filter_type = raw[offset]
        offset += 1
        encoded = bytearray(raw[offset : offset + stride])
        offset += stride
        decoded = _unfilter(encoded, previous, 4, filter_type)
        output.extend(decoded)
        previous = decoded
    return DecodedPng(width=width, height=height, rgba=bytes(output))


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    chunks: list[tuple[bytes, bytes]] = []
    offset = len(PNG_MAGIC)
    saw_end = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise PngCodecError("truncated_png")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(data):
            raise PngCodecError("truncated_png")
        payload = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length : end])[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != expected_crc:
            raise PngCodecError("corrupt_png_crc")
        chunks.append((kind, payload))
        offset = end
        if kind == b"IEND":
            saw_end = True
            break
    if not saw_end or offset != len(data):
        raise PngCodecError("invalid_png_termination")
    return chunks


def _unfilter(
    encoded: bytearray, previous: bytearray, channels: int, filter_type: int
) -> bytearray:
    decoded = bytearray(len(encoded))
    for index, value in enumerate(encoded):
        left = decoded[index - channels] if index >= channels else 0
        up = previous[index]
        up_left = previous[index - channels] if index >= channels else 0
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
            raise PngCodecError("unsupported_png_filter")
        decoded[index] = (value + predictor) & 0xFF
    return decoded


def _paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    up_left_distance = abs(estimate - up_left)
    if left_distance <= up_distance and left_distance <= up_left_distance:
        return left
    if up_distance <= up_left_distance:
        return up
    return up_left
