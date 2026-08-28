from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from closy_forge.zeroone.derivative_inspection import (
    DerivativeDecodeError,
    decode_v3_page_packs,
    probe_page_pack_failures,
)


def _vector(fmt: str, width: int, records: list[tuple[float, ...] | int]) -> bytes:
    flattened = [
        value
        for record in records
        for value in (record if isinstance(record, tuple) else (record,))
    ]
    return struct.pack("<Q", len(records)) + struct.pack(f"<{len(flattened)}{fmt}", *flattened)


def _payload() -> bytes:
    return b"".join(
        (
            _vector("f", 3, [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]),
            _vector("f", 3, [(0.0, 0.0, 1.0)] * 3),
            _vector("f", 2, [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]),
            _vector("f", 4, [(1.0, 0.0, 0.0, 1.0)] * 3),
            _vector("f", 4, [(1.0, 1.0, 1.0, 1.0)] * 3),
            _vector("I", 1, [0, 1, 2]),
            _vector("I", 1, [0]),
        )
    )


def _fnv(payload: bytes) -> int:
    value = 1469598103934665603
    for byte in payload:
        value ^= byte
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def _write_fixture(root: Path) -> Path:
    root.mkdir()
    payload = _payload()
    (root / "packs.bin").write_bytes(payload)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": 3,
                "assetGuid": "fixture",
                "cookKey": "fixture",
                "packs": [
                    {
                        "packId": 0,
                        "parentPackId": -1,
                        "hierarchyNodeIndex": 0,
                        "offset": 0,
                        "size": len(payload),
                        "checksum": _fnv(payload),
                        "triangleCount": 1,
                        "materialSectionIds": [0],
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return root


def test_independent_decoder_consumes_leaf_page_bytes(tmp_path: Path) -> None:
    decoded = decode_v3_page_packs(_write_fixture(tmp_path / "pages"))

    assert decoded.meshset.vertex_count == 3
    assert decoded.meshset.triangle_count == 1
    assert decoded.audit["usesConventionalFallbackGeometry"] is False
    assert decoded.audit["usesSourceVerticesOutsideDerivative"] is False
    assert decoded.audit["consumedPagePackCount"] == 1


def test_corrupt_page_checksum_fails_closed(tmp_path: Path) -> None:
    pages = _write_fixture(tmp_path / "pages")
    payload = bytearray((pages / "packs.bin").read_bytes())
    payload[-1] ^= 0x01
    (pages / "packs.bin").write_bytes(payload)

    with pytest.raises(DerivativeDecodeError, match="page_pack_checksum_mismatch"):
        decode_v3_page_packs(pages)


def test_all_declared_page_faults_are_rejected(tmp_path: Path) -> None:
    pages = _write_fixture(tmp_path / "pages")

    result = probe_page_pack_failures(pages, tmp_path / "faults")

    assert result["status"] == "pass"
    assert result["missingPage"]["failureReason"] == "page_pack_inventory_empty"
    assert result["corruptPage"]["failureReason"] == "page_pack_checksum_mismatch"
    assert result["reorderedPage"]["status"] == "pass"
    assert result["reorderedPage"]["failureReason"] == ("page_pack_id_inventory_or_order_invalid")
