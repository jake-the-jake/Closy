"""Independent Python codec and numerical oracle for ZeroOne dynamic v1.

This module intentionally does not import or call the production C++ codec or
deformation kernel. It owns a second field-wise implementation of the frozen
wire format and reconstructs expected output directly from request influences.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, overload

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]
Vec4 = tuple[float, float, float, float]
Vec6 = tuple[float, float, float, float, float, float]

REQUEST_MAGIC = b"Z1DYREQ\0"
OUTPUT_MAGIC = b"Z1DYOUT\0"
FORMAT_VERSION = 1
HEADER_BYTES = 96
ENTRY_BYTES = 80
ALIGNMENT = 16
MAXIMUM_BYTES = 512 * 1024 * 1024
CONTRACT_IDENTITY = (
    b"zeroone.dynamic.container.v1;header=96;directory=80;alignment=16;"
    b"byte-order=little;scalar=ieee754-binary32;checksum=sha256"
)
CONTRACT_DIGEST = hashlib.sha256(CONTRACT_IDENTITY).digest()

METADATA = 1
SIMULATION_IDS = 2
RENDER_IDS = 3
SIMULATION_REST = 4
BINDINGS = 5
TIMESTAMPS = 6
FRAME_SIMULATION_POSITIONS = 7
OUTPUT_INDICES = 101
OUTPUT_TEXCOORDS = 102
OUTPUT_FRAME_POSITIONS = 103
OUTPUT_FRAME_NORMALS = 104
OUTPUT_FRAME_TANGENTS = 105
OUTPUT_CLUSTER_BOUNDS = 106
OUTPUT_HIERARCHY_BOUNDS = 107
OUTPUT_LINEAGE = 108
KNOWN_SECTIONS = {
    METADATA,
    SIMULATION_IDS,
    RENDER_IDS,
    SIMULATION_REST,
    BINDINGS,
    TIMESTAMPS,
    FRAME_SIMULATION_POSITIONS,
    OUTPUT_INDICES,
    OUTPUT_TEXCOORDS,
    OUTPUT_FRAME_POSITIONS,
    OUTPUT_FRAME_NORMALS,
    OUTPUT_FRAME_TANGENTS,
    OUTPUT_CLUSTER_BOUNDS,
    OUTPUT_HIERARCHY_BOUNDS,
    OUTPUT_LINEAGE,
}


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def align(value: int) -> int:
    return (value + ALIGNMENT - 1) // ALIGNMENT * ALIGNMENT


@dataclass(frozen=True)
class Section:
    kind: int
    count: int
    encoding: int
    payload: bytes
    flags: int = 0


@dataclass(frozen=True)
class DecodedDocument:
    request: bool
    sections: dict[int, Section]
    sha256: str
    raw: bytes


def encode_document(sections: Iterable[Section], *, request: bool) -> bytes:
    ordered = list(sections)
    if not ordered or len(ordered) > 32:
        raise ValueError("section count")
    kinds = [section.kind for section in ordered]
    if len(set(kinds)) != len(kinds) or any(kind not in KNOWN_SECTIONS for kind in kinds):
        raise ValueError("duplicate or unknown section")
    payload_offset = align(HEADER_BYTES + len(ordered) * ENTRY_BYTES)
    placements: list[tuple[int, bytes]] = []
    cursor = payload_offset
    for section in ordered:
        cursor = align(cursor)
        placements.append((cursor, hashlib.sha256(section.payload).digest()))
        cursor += len(section.payload)
    if cursor > MAXIMUM_BYTES:
        raise ValueError("oversized")
    result = bytearray(
        struct.pack(
            "<8sHBBIIIQQQQ32sQ",
            REQUEST_MAGIC if request else OUTPUT_MAGIC,
            FORMAT_VERSION,
            1,
            1,
            HEADER_BYTES,
            len(ordered),
            ENTRY_BYTES,
            HEADER_BYTES,
            cursor,
            payload_offset,
            MAXIMUM_BYTES,
            CONTRACT_DIGEST,
            0,
        )
    )
    assert len(result) == HEADER_BYTES
    for section, (offset, checksum) in zip(ordered, placements, strict=True):
        result.extend(
            struct.pack(
                "<IIQQQII32sQ",
                section.kind,
                section.flags,
                offset,
                len(section.payload),
                section.count,
                ALIGNMENT,
                section.encoding,
                checksum,
                0,
            )
        )
    result.extend(b"\0" * (payload_offset - len(result)))
    for section, (offset, _) in zip(ordered, placements, strict=True):
        result.extend(b"\0" * (offset - len(result)))
        result.extend(section.payload)
    assert len(result) == cursor
    return bytes(result)


def decode_document(value: bytes, *, request: bool) -> DecodedDocument:
    if len(value) < HEADER_BYTES or len(value) > MAXIMUM_BYTES:
        raise ValueError("truncated_or_oversized")
    (
        magic,
        version,
        byte_order,
        scalar,
        header_bytes,
        section_count,
        entry_bytes,
        directory_offset,
        total_bytes,
        payload_offset,
        maximum_bytes,
        contract_digest,
        reserved,
    ) = struct.unpack_from("<8sHBBIIIQQQQ32sQ", value)
    if magic != (REQUEST_MAGIC if request else OUTPUT_MAGIC):
        raise ValueError("magic")
    if (
        version != FORMAT_VERSION
        or byte_order != 1
        or scalar != 1
        or header_bytes != HEADER_BYTES
        or not 0 < section_count <= 32
        or entry_bytes != ENTRY_BYTES
        or directory_offset != HEADER_BYTES
        or total_bytes != len(value)
        or maximum_bytes != MAXIMUM_BYTES
        or contract_digest != CONTRACT_DIGEST
        or reserved
    ):
        raise ValueError("header_contract")
    directory_end = directory_offset + section_count * entry_bytes
    if payload_offset % ALIGNMENT or directory_end > payload_offset or payload_offset > len(value):
        raise ValueError("directory_range")
    if any(value[directory_end:payload_offset]):
        raise ValueError("forbidden_padding")
    sections: dict[int, Section] = {}
    ranges: list[tuple[int, int]] = []
    for index in range(section_count):
        base = directory_offset + index * entry_bytes
        kind, flags, offset, length, count, alignment, encoding, checksum, entry_reserved = (
            struct.unpack_from("<IIQQQII32sQ", value, base)
        )
        if kind not in KNOWN_SECTIONS or kind in sections:
            raise ValueError("duplicate_or_unknown_section")
        if (
            alignment != ALIGNMENT
            or offset % alignment
            or offset < payload_offset
            or length > len(value) - offset
            or entry_reserved
        ):
            raise ValueError("section_range_or_alignment")
        candidate = (offset, offset + length)
        if any(candidate[0] < end and start < candidate[1] for start, end in ranges):
            raise ValueError("section_overlap")
        payload = value[offset : offset + length]
        if hashlib.sha256(payload).digest() != checksum:
            raise ValueError("section_checksum")
        ranges.append(candidate)
        sections[kind] = Section(kind, count, encoding, payload, flags)
    cursor = payload_offset
    for start, end in sorted(ranges):
        if any(value[cursor:start]):
            raise ValueError("forbidden_padding")
        cursor = end
    if cursor != len(value):
        raise ValueError("forbidden_trailing_bytes")
    return DecodedDocument(request, sections, digest_bytes(value), value)


def json_section(value: dict[str, Any]) -> Section:
    return Section(METADATA, 1, 1, canonical_json(value))


def u64_section(kind: int, values: Iterable[int]) -> Section:
    packed = tuple(values)
    return Section(kind, len(packed), 2, b"".join(struct.pack("<Q", item) for item in packed))


def vec3_section(kind: int, values: Iterable[tuple[float, float, float]]) -> Section:
    packed = tuple(values)
    return Section(kind, len(packed), 3, b"".join(struct.pack("<3f", *item) for item in packed))


def decode_u64(section: Section) -> list[int]:
    if section.encoding != 2 or len(section.payload) != section.count * 8:
        raise ValueError("u64 section")
    return list(struct.unpack(f"<{section.count}Q", section.payload))


def decode_u32(section: Section) -> list[int]:
    if section.encoding != 5 or len(section.payload) != section.count * 4:
        raise ValueError("u32 section")
    return list(struct.unpack(f"<{section.count}I", section.payload))


@overload
def decode_vectors(section: Section, lanes: Literal[2], encoding: int) -> list[Vec2]: ...


@overload
def decode_vectors(section: Section, lanes: Literal[3], encoding: int) -> list[Vec3]: ...


@overload
def decode_vectors(section: Section, lanes: Literal[4], encoding: int) -> list[Vec4]: ...


@overload
def decode_vectors(section: Section, lanes: Literal[6], encoding: int) -> list[Vec6]: ...


def decode_vectors(section: Section, lanes: int, encoding: int) -> Any:
    if section.encoding != encoding or len(section.payload) != section.count * lanes * 4:
        raise ValueError("vector section")
    values = struct.unpack(f"<{section.count * lanes}f", section.payload)
    return [tuple(values[index : index + lanes]) for index in range(0, len(values), lanes)]


def binding_payload(
    render_ids: list[int],
    simulation_ids: list[int],
) -> bytes:
    if len(render_ids) != len(simulation_ids):
        raise ValueError("direct fixture binding requires matching counts")
    records = bytearray()
    for render_id, simulation_id in zip(render_ids, simulation_ids, strict=True):
        records.extend(
            struct.pack(
                "<QII3Q3fQI",
                render_id,
                1,
                1,
                simulation_id,
                0,
                0,
                1.0,
                0.0,
                0.0,
                simulation_id,
                0,
            )
        )
    assert len(records) == len(render_ids) * 64
    return bytes(records)


def decode_bindings(section: Section) -> list[dict[str, Any]]:
    if section.encoding != 4 or len(section.payload) != section.count * 64:
        raise ValueError("binding section")
    result = []
    for index in range(section.count):
        values = struct.unpack_from("<QII3Q3fQI", section.payload, index * 64)
        result.append(
            {
                "destination": values[0],
                "authority": values[1],
                "count": values[2],
                "sources": values[3:6],
                "weights": values[6:9],
                "triangle": values[9],
                "reserved": values[10],
            }
        )
    return result


def decode_lineage(section: Section) -> list[dict[str, Any]]:
    if section.encoding != 9 or len(section.payload) != section.count * 72:
        raise ValueError("lineage section")
    result = []
    for index in range(section.count):
        values = struct.unpack_from("<IIIIQII3Q3fI", section.payload, index * 72)
        result.append(
            {
                "cluster": values[0],
                "page": values[1],
                "local": values[2],
                "source_index": values[3],
                "render_id": values[4],
                "authority": values[5],
                "count": values[6],
                "sources": values[7:10],
                "weights": values[10:13],
                "reserved": values[13],
            }
        )
    return result


def render_topology_hash(render_ids: list[int], indices: list[int]) -> str:
    payload = bytearray(b"Z1RENTOP\x01")
    payload.extend(struct.pack("<Q", len(render_ids)))
    payload.extend(b"".join(struct.pack("<Q", value) for value in render_ids))
    payload.extend(struct.pack("<Q", len(indices)))
    payload.extend(b"".join(struct.pack("<I", value) for value in indices))
    return digest_bytes(bytes(payload))


def simulation_topology_hash(simulation_ids: list[int]) -> str:
    payload = bytearray(b"Z1SIMTOP\x01")
    payload.extend(struct.pack("<Q", len(simulation_ids)))
    payload.extend(b"".join(struct.pack("<Q", value) for value in simulation_ids))
    return digest_bytes(bytes(payload))


def source_to_cluster_hash(render_ids: list[int], indices: list[int]) -> str:
    payload = bytearray(b"Z1CMAP\x01")
    cluster_count = (len(indices) // 3 + 127) // 128
    payload.extend(struct.pack("<Q", cluster_count))
    for cluster in range(cluster_count):
        first_triangle = cluster * 128
        last_triangle = min(first_triangle + 128, len(indices) // 3)
        source_to_local: dict[int, int] = {}
        local_to_source: list[int] = []
        for source in indices[first_triangle * 3 : last_triangle * 3]:
            if source not in source_to_local:
                source_to_local[source] = len(source_to_local)
                local_to_source.append(source)
        for local, source in enumerate(local_to_source):
            payload.extend(
                struct.pack("<IIIIQ", cluster, cluster, local, source, render_ids[source])
            )
    return digest_bytes(bytes(payload))


def static_inventory_hash(nanite: dict[str, Any]) -> str:
    payload = bytearray(b"Z1CINV\x01")
    for key in (
        "clusterCount",
        "geometryHash",
        "hierarchyNodeCount",
        "materialHash",
        "pageCount",
        "pagePackCount",
        "topologyHash",
    ):
        payload.extend(struct.pack("<Q", nanite[key]))
    return digest_bytes(bytes(payload))


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def scale(a: tuple[float, float, float], value: float) -> tuple[float, float, float]:
    return a[0] * value, a[1] * value, a[2] * value


def dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(value: tuple[float, float, float]) -> float:
    return math.sqrt(dot(value, value))


def normalize(value: tuple[float, float, float]) -> tuple[float, float, float]:
    magnitude = length(value)
    if magnitude <= 1.0e-20:
        raise ValueError("zero vector")
    return scale(value, 1.0 / magnitude)


def decode_metadata(document: DecodedDocument) -> dict[str, Any]:
    section = document.sections[METADATA]
    if section.encoding != 1 or section.count != 1:
        raise ValueError("metadata")
    metadata = json.loads(section.payload)
    if not isinstance(metadata, dict):
        raise ValueError("metadata object")
    if canonical_json(metadata) != section.payload:
        raise ValueError("noncanonical metadata")
    return metadata


def recompute_frames(
    request: DecodedDocument,
) -> tuple[
    list[int],
    list[int],
    list[int],
    list[list[tuple[float, float, float]]],
]:
    simulation_ids = decode_u64(request.sections[SIMULATION_IDS])
    render_ids = decode_u64(request.sections[RENDER_IDS])
    timestamps = decode_u64(request.sections[TIMESTAMPS])
    simulation_positions_flat = decode_vectors(request.sections[FRAME_SIMULATION_POSITIONS], 3, 3)
    if len(simulation_positions_flat) != len(timestamps) * len(simulation_ids):
        raise ValueError("frame count")
    simulation_index = {value: index for index, value in enumerate(simulation_ids)}
    bindings = {
        record["destination"]: record for record in decode_bindings(request.sections[BINDINGS])
    }
    expected: list[list[tuple[float, float, float]]] = []
    for frame in range(len(timestamps)):
        positions: list[tuple[float, float, float]] = []
        for render_id in render_ids:
            binding = bindings[render_id]
            value = (0.0, 0.0, 0.0)
            for lane in range(binding["count"]):
                source = simulation_index[binding["sources"][lane]]
                point = simulation_positions_flat[frame * len(simulation_ids) + source]
                value = add(value, scale(point, binding["weights"][lane]))
            positions.append(value)
        expected.append(positions)
    return simulation_ids, render_ids, timestamps, expected


def expected_normal_tangent(
    positions: list[tuple[float, float, float]],
    indices: list[int],
    texcoords: list[tuple[float, float]],
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float, float]]]:
    normals = [(0.0, 0.0, 0.0) for _ in positions]
    tangent_a = [(0.0, 0.0, 0.0) for _ in positions]
    tangent_b = [(0.0, 0.0, 0.0) for _ in positions]
    for offset in range(0, len(indices), 3):
        i0, i1, i2 = indices[offset : offset + 3]
        edge1 = sub(positions[i1], positions[i0])
        edge2 = sub(positions[i2], positions[i0])
        face = cross(edge1, edge2)
        if length(face) <= 1.0e-8:
            raise ValueError("degenerate triangle")
        for index in (i0, i1, i2):
            normals[index] = add(normals[index], face)
        duv1 = (texcoords[i1][0] - texcoords[i0][0], texcoords[i1][1] - texcoords[i0][1])
        duv2 = (texcoords[i2][0] - texcoords[i0][0], texcoords[i2][1] - texcoords[i0][1])
        denominator = duv1[0] * duv2[1] - duv1[1] * duv2[0]
        if abs(denominator) > 1.0e-12:
            inverse = 1.0 / denominator
            sdir = scale(sub(scale(edge1, duv2[1]), scale(edge2, duv1[1])), inverse)
            tdir = scale(sub(scale(edge2, duv1[0]), scale(edge1, duv2[0])), inverse)
        else:
            sdir = normalize(edge1)
            tdir = normalize(cross(normalize(face), sdir))
        for index in (i0, i1, i2):
            tangent_a[index] = add(tangent_a[index], sdir)
            tangent_b[index] = add(tangent_b[index], tdir)
    normal_output: list[tuple[float, float, float]] = []
    tangent_output: list[tuple[float, float, float, float]] = []
    for normal_value, first, second in zip(normals, tangent_a, tangent_b, strict=True):
        normal = normalize(normal_value)
        tangent = sub(first, scale(normal, dot(normal, first)))
        if length(tangent) <= 1.0e-8:
            axis = (0.0, 1.0, 0.0) if abs(normal[1]) < 0.9 else (1.0, 0.0, 0.0)
            tangent = cross(axis, normal)
        tangent = normalize(tangent)
        handedness = -1.0 if dot(cross(normal, tangent), second) < 0.0 else 1.0
        normal_output.append(normal)
        tangent_output.append((*tangent, handedness))
    return normal_output, tangent_output


def clip_polygon_axis(
    polygon: list[tuple[float, float, float]],
    axis: int,
    boundary: float,
    keep_greater: bool,
) -> list[tuple[float, float, float]]:
    output: list[tuple[float, float, float]] = []
    if not polygon:
        return output
    for index, current in enumerate(polygon):
        prior = polygon[index - 1]
        current_inside = current[axis] >= boundary if keep_greater else current[axis] <= boundary
        prior_inside = prior[axis] >= boundary if keep_greater else prior[axis] <= boundary
        if current_inside != prior_inside:
            denominator = current[axis] - prior[axis]
            if abs(denominator) > 1.0e-20:
                amount = (boundary - prior[axis]) / denominator
                output.append(add(prior, scale(sub(current, prior), amount)))
        if current_inside:
            output.append(current)
    return output


def view_point(point: tuple[float, float, float], yaw: float) -> tuple[float, float, float]:
    cosine = math.cos(yaw)
    sine = math.sin(yaw)
    return cosine * point[0] + sine * point[2], point[1], -sine * point[0] + cosine * point[2]


def triangle_frustum(
    triangle: tuple[tuple[float, float, float], ...],
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float],
    yaw: float,
) -> bool:
    polygon = [view_point(point, yaw) for point in triangle]
    for axis in range(3):
        polygon = clip_polygon_axis(polygon, axis, minimum[axis], True)
        polygon = clip_polygon_axis(polygon, axis, maximum[axis], False)
        if not polygon:
            return False
    return True


def bounds_frustum(
    bounds: tuple[float, ...],
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float],
    yaw: float,
) -> bool:
    points = [
        view_point(
            (
                bounds[3] if corner & 1 else bounds[0],
                bounds[4] if corner & 2 else bounds[1],
                bounds[5] if corner & 4 else bounds[2],
            ),
            yaw,
        )
        for corner in range(8)
    ]
    transformed_min = tuple(min(point[axis] for point in points) for axis in range(3))
    transformed_max = tuple(max(point[axis] for point in points) for axis in range(3))
    return all(
        transformed_max[axis] >= minimum[axis] and transformed_min[axis] <= maximum[axis]
        for axis in range(3)
    )


def culling_oracle(
    positions: Sequence[Sequence[Vec3]],
    indices: Sequence[int],
    cluster_bounds: Sequence[Vec6],
    cluster_count: int,
    root_bounds: Sequence[Vec6],
) -> dict[str, int | float | bool]:
    false_negatives = 0
    false_positives = 0
    oracle_visible = 0
    bound_visible = 0
    scenarios_total = 0
    for frame, frame_positions in enumerate(positions):
        root = root_bounds[frame]
        root_min: Vec3 = (root[0], root[1], root[2])
        root_max: Vec3 = (root[3], root[4], root[5])
        center: Vec3 = tuple((root_min[axis] + root_max[axis]) * 0.5 for axis in range(3))  # type: ignore[assignment]
        extent: Vec3 = tuple(
            max((root_max[axis] - root_min[axis]) * 0.5, 0.01) for axis in range(3)
        )  # type: ignore[assignment]
        scenarios = [
            (
                0.0,
                _offset_scaled(center, extent, -1.1),
                _offset_scaled(center, extent, 1.1),
            ),
            (
                0.0,
                (root_min[0] - 0.01, root_min[1] - 0.01, root_min[2] - 0.01),
                (center[0], root_max[1] + 0.01, root_max[2] + 0.01),
            ),
            (
                0.0,
                (center[0], root_min[1] - 0.01, root_min[2] - 0.01),
                _offset3(root_max, 0.01),
            ),
            (
                0.0,
                (root_min[0] - 0.01, center[1], root_min[2] - 0.01),
                _offset3(root_max, 0.01),
            ),
            (
                math.pi / 4.0,
                (-extent[0], root_min[1] - 0.02, -extent[2]),
                (extent[0], root_max[1] + 0.02, extent[2]),
            ),
            (
                math.pi / 2.0,
                (-extent[2] * 0.4, root_min[1], -extent[0]),
                (extent[2] * 0.4, root_max[1], extent[0]),
            ),
            (
                0.0,
                _offset3(root_max, 0.2),
                _offset3(root_max, 0.4),
            ),
        ]
        for yaw, minimum, maximum in scenarios:
            scenarios_total += 1
            for cluster in range(cluster_count):
                first_triangle = cluster * 128
                last_triangle = min(first_triangle + 128, len(indices) // 3)
                triangle_visible = any(
                    triangle_frustum(
                        (
                            frame_positions[indices[triangle * 3]],
                            frame_positions[indices[triangle * 3 + 1]],
                            frame_positions[indices[triangle * 3 + 2]],
                        ),
                        minimum,
                        maximum,
                        yaw,
                    )
                    for triangle in range(first_triangle, last_triangle)
                )
                bounds_visible = bounds_frustum(
                    cluster_bounds[frame * cluster_count + cluster], minimum, maximum, yaw
                )
                oracle_visible += int(triangle_visible)
                bound_visible += int(bounds_visible)
                false_negatives += int(triangle_visible and not bounds_visible)
                false_positives += int(bounds_visible and not triangle_visible)
    return {
        "scenarioCount": scenarios_total,
        "oracleVisibleClusterSamples": oracle_visible,
        "boundVisibleClusterSamples": bound_visible,
        "falseNegativeCount": false_negatives,
        "falsePositiveCount": false_positives,
        "falsePositiveRate": false_positives / bound_visible if bound_visible else 0.0,
        "passed": false_negatives == 0,
    }


def _offset3(value: Vec3, amount: float) -> Vec3:
    return (value[0] + amount, value[1] + amount, value[2] + amount)


def _offset_scaled(center: Vec3, extent: Vec3, amount: float) -> Vec3:
    return (
        center[0] + extent[0] * amount,
        center[1] + extent[1] * amount,
        center[2] + extent[2] * amount,
    )


def interpolation_minimum_double_area(
    prior: tuple[tuple[float, float, float], ...],
    current: tuple[tuple[float, float, float], ...],
) -> float:
    # Linear-in-time vertices produce a quadratic cross product. Sampling the
    # endpoints plus a dense deterministic interval is an independent bounded
    # continuity oracle for this reference clip, not a physical solver claim.
    minimum = math.inf
    for step in range(65):
        amount = step / 64.0
        triangle = tuple(
            add(prior[lane], scale(sub(current[lane], prior[lane]), amount)) for lane in range(3)
        )
        minimum = min(
            minimum, length(cross(sub(triangle[1], triangle[0]), sub(triangle[2], triangle[0])))
        )
    return minimum


def segment_triangle_intersection(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    triangle: tuple[tuple[float, float, float], ...],
) -> bool:
    direction = sub(end, start)
    edge1 = sub(triangle[1], triangle[0])
    edge2 = sub(triangle[2], triangle[0])
    p = cross(direction, edge2)
    determinant = dot(edge1, p)
    if abs(determinant) <= 1.0e-10:
        return False
    inverse = 1.0 / determinant
    offset = sub(start, triangle[0])
    u = dot(offset, p) * inverse
    if u < -1.0e-8 or u > 1.0 + 1.0e-8:
        return False
    q = cross(offset, edge1)
    v = dot(direction, q) * inverse
    if v < -1.0e-8 or u + v > 1.0 + 1.0e-8:
        return False
    amount = dot(edge2, q) * inverse
    return 1.0e-8 < amount < 1.0 - 1.0e-8


def orient2d(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def coplanar_triangles_overlap(
    first: tuple[tuple[float, float, float], ...],
    second: tuple[tuple[float, float, float], ...],
    normal: tuple[float, float, float],
) -> bool:
    drop = max(range(3), key=lambda axis: abs(normal[axis]))
    keep = [axis for axis in range(3) if axis != drop]
    a = [(point[keep[0]], point[keep[1]]) for point in first]
    b = [(point[keep[0]], point[keep[1]]) for point in second]
    for left in (a, b):
        right = b if left is a else a
        for index in range(3):
            p0, p1 = left[index], left[(index + 1) % 3]
            for other in range(3):
                q0, q1 = right[other], right[(other + 1) % 3]
                o1 = orient2d(p0, p1, q0)
                o2 = orient2d(p0, p1, q1)
                o3 = orient2d(q0, q1, p0)
                o4 = orient2d(q0, q1, p1)
                if o1 * o2 < -1.0e-14 and o3 * o4 < -1.0e-14:
                    return True

    def inside(point: tuple[float, float], triangle: list[tuple[float, float]]) -> bool:
        values = [orient2d(triangle[index], triangle[(index + 1) % 3], point) for index in range(3)]
        return all(value > 1.0e-8 for value in values) or all(value < -1.0e-8 for value in values)

    return inside(a[0], b) or inside(b[0], a)


def triangles_intersect(
    first: tuple[tuple[float, float, float], ...],
    second: tuple[tuple[float, float, float], ...],
) -> bool:
    first_min = tuple(min(point[axis] for point in first) for axis in range(3))
    first_max = tuple(max(point[axis] for point in first) for axis in range(3))
    second_min = tuple(min(point[axis] for point in second) for axis in range(3))
    second_max = tuple(max(point[axis] for point in second) for axis in range(3))
    if any(
        first_max[axis] < second_min[axis] - 1.0e-8 or second_max[axis] < first_min[axis] - 1.0e-8
        for axis in range(3)
    ):
        return False
    normal_first = cross(sub(first[1], first[0]), sub(first[2], first[0]))
    normal_second = cross(sub(second[1], second[0]), sub(second[2], second[0]))
    if length(cross(normal_first, normal_second)) <= 1.0e-8 * length(normal_first) * length(
        normal_second
    ):
        distance = abs(dot(normalize(normal_first), sub(second[0], first[0])))
        if distance <= 1.0e-7:
            return coplanar_triangles_overlap(first, second, normal_first)
    for triangle, other in ((first, second), (second, first)):
        for edge in range(3):
            if segment_triangle_intersection(triangle[edge], triangle[(edge + 1) % 3], other):
                return True
    return False


def self_intersection_count(positions: list[tuple[float, float, float]], indices: list[int]) -> int:
    triangles = [tuple(indices[offset : offset + 3]) for offset in range(0, len(indices), 3)]
    count = 0
    for first_index, first_ids in enumerate(triangles):
        first = tuple(positions[index] for index in first_ids)
        for second_ids in triangles[first_index + 1 :]:
            if set(first_ids) & set(second_ids):
                continue
            second = tuple(positions[index] for index in second_ids)
            count += int(triangles_intersect(first, second))
    return count


def audit_output(request: DecodedDocument, output: DecodedDocument) -> dict[str, Any]:
    request_metadata = decode_metadata(request)
    output_metadata = decode_metadata(output)
    simulation_ids, render_ids, timestamps, expected_positions = recompute_frames(request)
    output_render_ids = decode_u64(output.sections[RENDER_IDS])
    output_timestamps = decode_u64(output.sections[TIMESTAMPS])
    indices = decode_u32(output.sections[OUTPUT_INDICES])
    texcoords = decode_vectors(output.sections[OUTPUT_TEXCOORDS], 2, 6)
    positions_flat = decode_vectors(output.sections[OUTPUT_FRAME_POSITIONS], 3, 3)
    normals_flat = decode_vectors(output.sections[OUTPUT_FRAME_NORMALS], 3, 3)
    tangents_flat = decode_vectors(output.sections[OUTPUT_FRAME_TANGENTS], 4, 7)
    frame_count = len(timestamps)
    vertex_count = len(render_ids)
    if output_render_ids != render_ids or output_timestamps != timestamps:
        raise AssertionError("stable ids/timestamps changed")
    if not all(
        len(values) == frame_count * vertex_count
        for values in (positions_flat, normals_flat, tangents_flat)
    ):
        raise AssertionError("frame stream count")
    actual_positions = [
        positions_flat[index * vertex_count : (index + 1) * vertex_count]
        for index in range(frame_count)
    ]
    actual_normals = [
        normals_flat[index * vertex_count : (index + 1) * vertex_count]
        for index in range(frame_count)
    ]
    actual_tangents = [
        tangents_flat[index * vertex_count : (index + 1) * vertex_count]
        for index in range(frame_count)
    ]
    position_errors = [
        length(sub(actual_positions[frame][vertex], expected_positions[frame][vertex]))
        for frame in range(frame_count)
        for vertex in range(vertex_count)
    ]
    normal_errors: list[float] = []
    tangent_errors: list[float] = []
    handedness_mismatches = 0
    minimum_swept_area = math.inf
    for frame in range(frame_count):
        expected_normals, expected_tangents = expected_normal_tangent(
            actual_positions[frame], indices, texcoords
        )
        for vertex in range(vertex_count):
            normal = actual_normals[frame][vertex]
            tangent = actual_tangents[frame][vertex]
            if not all(math.isfinite(value) for value in (*normal, *tangent)):
                raise AssertionError("nonfinite normal/tangent")
            if abs(length(normal) - 1.0) > 2.0e-5 or abs(dot(normal, tangent[:3])) > 2.0e-5:
                raise AssertionError("normal/tangent basis")
            normal_errors.append(length(sub(normal, expected_normals[vertex])))
            tangent_errors.append(length(sub(tangent[:3], expected_tangents[vertex][:3])))
            handedness_mismatches += int(tangent[3] != expected_tangents[vertex][3])
        if frame:
            for offset in range(0, len(indices), 3):
                prior = (
                    actual_positions[frame - 1][indices[offset]],
                    actual_positions[frame - 1][indices[offset + 1]],
                    actual_positions[frame - 1][indices[offset + 2]],
                )
                current = (
                    actual_positions[frame][indices[offset]],
                    actual_positions[frame][indices[offset + 1]],
                    actual_positions[frame][indices[offset + 2]],
                )
                minimum_swept_area = min(
                    minimum_swept_area, interpolation_minimum_double_area(prior, current)
                )
    # Rest identity is evaluated after the independently decoded influence map;
    # production packages do not have a one-to-one simulation/render vertex map.
    rest_error = max(
        length(sub(actual_positions[0][index], expected_positions[0][index]))
        for index in range(vertex_count)
    )
    input_sensitivity = any(
        length(sub(actual_positions[frame][vertex], actual_positions[0][vertex])) > 1.0e-5
        for frame in range(1, frame_count - 1)
        for vertex in range(vertex_count)
    )
    lineage = decode_lineage(output.sections[OUTPUT_LINEAGE])
    cluster_count = output_metadata["clusterCount"]
    hierarchy_count = output_metadata["hierarchyNodeCount"]
    cluster_bounds = decode_vectors(output.sections[OUTPUT_CLUSTER_BOUNDS], 6, 8)
    hierarchy_bounds = decode_vectors(output.sections[OUTPUT_HIERARCHY_BOUNDS], 6, 8)
    if (
        len(cluster_bounds) != frame_count * cluster_count
        or len(hierarchy_bounds) != frame_count * hierarchy_count
    ):
        raise AssertionError("bounds count")
    sources_by_cluster: dict[int, set[int]] = {index: set() for index in range(cluster_count)}
    for record in lineage:
        if record["reserved"] or record["authority"] not in (1, 2):
            raise AssertionError("lineage authority")
        sources_by_cluster[record["cluster"]].add(record["source_index"])
    bound_failures = 0
    for frame in range(frame_count):
        for cluster, sources in sources_by_cluster.items():
            bounds = cluster_bounds[frame * cluster_count + cluster]
            for source in sources:
                point = actual_positions[frame][source]
                bound_failures += int(
                    any(
                        point[axis] < bounds[axis] - 1.0e-7
                        or point[axis] > bounds[axis + 3] + 1.0e-7
                        for axis in range(3)
                    )
                )
    # The static hierarchy builds leaves first, then pairwise parents in order.
    hierarchy_children: dict[int, tuple[int, int]] = {}
    level = list(range(cluster_count))
    next_node = cluster_count
    while len(level) > 1:
        following = []
        for index in range(0, len(level), 2):
            if index + 1 == len(level):
                following.append(level[index])
            else:
                hierarchy_children[next_node] = (level[index], level[index + 1])
                following.append(next_node)
                next_node += 1
        level = following
    if next_node != hierarchy_count:
        raise AssertionError("hierarchy shape")
    parent_failures = 0
    for frame in range(frame_count):
        for parent, children in hierarchy_children.items():
            parent_bounds = hierarchy_bounds[frame * hierarchy_count + parent]
            for child in children:
                child_bounds = hierarchy_bounds[frame * hierarchy_count + child]
                parent_failures += int(
                    any(
                        child_bounds[axis] < parent_bounds[axis] - 1.0e-7
                        or child_bounds[axis + 3] > parent_bounds[axis + 3] + 1.0e-7
                        for axis in range(3)
                    )
                )
    root = level[0]
    root_bounds = [hierarchy_bounds[frame * hierarchy_count + root] for frame in range(frame_count)]
    culling = culling_oracle(actual_positions, indices, cluster_bounds, cluster_count, root_bounds)
    body_spheres = request_metadata["provenance"].get("bodyProxySpheres", [])
    minimum_body_clearance = math.inf
    for frame_positions in actual_positions:
        for point in frame_positions:
            for sphere in body_spheres:
                center_value = sphere["center"]
                sphere_center: Vec3 = (
                    float(center_value[0]),
                    float(center_value[1]),
                    float(center_value[2]),
                )
                minimum_body_clearance = min(
                    minimum_body_clearance,
                    length(sub(point, sphere_center)) - sphere["radius"],
                )
    semantic_preserved = output_metadata["semanticIds"] == request_metadata["semanticIds"]
    dense_self_intersections = [
        self_intersection_count(frame_positions, indices) for frame_positions in actual_positions
    ]
    # The output-topology reconstruction is independently derived from request
    # simulation frames and influences rather than inferred from the report.
    simulation_self_intersections = [
        self_intersection_count(frame_positions, indices) for frame_positions in expected_positions
    ]
    passed = (
        max(position_errors) <= 1.0e-6
        and percentile(position_errors, 0.95) <= 1.0e-6
        and max(normal_errors) <= 2.0e-5
        and max(tangent_errors) <= 2.0e-5
        and handedness_mismatches == 0
        and rest_error <= 1.0e-6
        and input_sensitivity
        and minimum_swept_area > 1.0e-8
        and bound_failures == 0
        and parent_failures == 0
        and culling["passed"]
        and semantic_preserved
        and max(dense_self_intersections) == 0
        and max(simulation_self_intersections) == 0
    )
    return {
        "oracleVersion": "zeroone.dynamic.independent-python-oracle.v1",
        "requestSha256": request.sha256,
        "outputSha256": output.sha256,
        "frameCount": frame_count,
        "renderVertexCount": vertex_count,
        "triangleCount": len(indices) // 3,
        "clusterCount": cluster_count,
        "hierarchyNodeCount": hierarchy_count,
        "maximumPositionErrorMetres": max(position_errors),
        "p95PositionErrorMetres": percentile(position_errors, 0.95),
        "maximumNormalError": max(normal_errors),
        "maximumTangentError": max(tangent_errors),
        "tangentHandednessMismatchCount": handedness_mismatches,
        "restIdentityMaximumErrorMetres": rest_error,
        "inputSensitive": input_sensitivity,
        "minimumSweptTriangleDoubleArea": minimum_swept_area,
        "trueTemporalInversionCount": 0 if minimum_swept_area > 1.0e-8 else 1,
        "clusterBoundContainmentFailures": bound_failures,
        "parentBoundContainmentFailures": parent_failures,
        "culling": culling,
        "semanticOpeningOrderPreserved": semantic_preserved,
        "denseSelfIntersectionCountByFrame": dense_self_intersections,
        "simulationSelfIntersectionCountByFrame": simulation_self_intersections,
        "minimumBodyProxyClearanceMetres": None
        if math.isinf(minimum_body_clearance)
        else minimum_body_clearance,
        "physicalTruthClaimed": False,
        "passed": passed,
    }


def audit_files(request_path: Path, output_path: Path) -> dict[str, Any]:
    request = decode_document(request_path.read_bytes(), request=True)
    output = decode_document(output_path.read_bytes(), request=False)
    return audit_output(request, output)
