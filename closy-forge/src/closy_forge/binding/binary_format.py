from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from closy_forge.contracts.binding import BINDING_MAGIC, BINDING_RECORD_STRIDE, BINDING_VERSION

HEADER_STRUCT = struct.Struct("<8sIIIIII32s32s")
RECORD_STRUCT = struct.Struct("<IfffHH")
HEADER_SIZE = HEADER_STRUCT.size


@dataclass(frozen=True)
class BindingRecord:
    simulation_triangle_index: int
    barycentric_u: float
    barycentric_v: float
    normal_offset: float
    panel_table_index: int
    flags: int = 0


@dataclass(frozen=True)
class BindingFile:
    records: list[BindingRecord]
    simulation_triangle_count: int
    panel_count: int
    simulation_topology_hash: str
    render_topology_hash: str


def write_binding(path: Path, binding: BindingFile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = HEADER_STRUCT.pack(
        BINDING_MAGIC,
        BINDING_VERSION,
        HEADER_SIZE,
        BINDING_RECORD_STRIDE,
        len(binding.records),
        binding.simulation_triangle_count,
        binding.panel_count,
        bytes.fromhex(binding.simulation_topology_hash),
        bytes.fromhex(binding.render_topology_hash),
    )
    records = b"".join(
        RECORD_STRUCT.pack(
            record.simulation_triangle_index,
            record.barycentric_u,
            record.barycentric_v,
            record.normal_offset,
            record.panel_table_index,
            record.flags,
        )
        for record in binding.records
    )
    path.write_bytes(header + records)


def read_binding(path: Path) -> BindingFile:
    data = path.read_bytes()
    if len(data) < HEADER_SIZE:
        raise ValueError("binding_truncated_header")
    (
        magic,
        version,
        header_size,
        stride,
        record_count,
        sim_tri_count,
        panel_count,
        sim_hash,
        render_hash,
    ) = HEADER_STRUCT.unpack_from(data, 0)
    if magic != BINDING_MAGIC:
        raise ValueError("binding_bad_magic")
    if version != BINDING_VERSION:
        raise ValueError("binding_unsupported_version")
    if header_size != HEADER_SIZE or stride != BINDING_RECORD_STRIDE:
        raise ValueError("binding_bad_layout")
    expected = header_size + record_count * stride
    if len(data) != expected:
        raise ValueError("binding_size_mismatch")
    records = []
    offset = header_size
    for _ in range(record_count):
        tri_i, u, v, normal_offset, panel_i, flags = RECORD_STRUCT.unpack_from(data, offset)
        offset += stride
        records.append(BindingRecord(tri_i, u, v, normal_offset, panel_i, flags))
    return BindingFile(records, sim_tri_count, panel_count, sim_hash.hex(), render_hash.hex())
