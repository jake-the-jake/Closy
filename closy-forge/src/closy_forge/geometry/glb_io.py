from __future__ import annotations

import json
import math
import struct
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .frame_attributes import expanded_triangle_frames, vertex_normals, vertex_tangents
from .mesh_model import Mesh, MeshSet


def _pad4(data: bytes, pad: bytes) -> bytes:
    return data + pad * ((4 - len(data) % 4) % 4)


def _write_floats(
    values: Sequence[Sequence[float]], *, normalize_signed_zero: bool = False
) -> bytes:
    return b"".join(
        struct.pack(
            "<" + "f" * len(value),
            *(
                0.0 if normalize_signed_zero and component == 0.0 else component
                for component in value
            ),
        )
        for value in values
    )


def _write_indices(values: list[tuple[int, int, int]]) -> bytes:
    return b"".join(struct.pack("<III", *value) for value in values)


def write_glb(
    path: Path, meshset: MeshSet, material_name: str, color: tuple[float, float, float, float]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = bytearray()
    buffer_views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    meshes_json: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []

    def append_blob(blob: bytes, target: int | None = None) -> int:
        nonlocal buffer
        buffer.extend(b"\x00" * ((4 - len(buffer) % 4) % 4))
        offset = len(buffer)
        buffer.extend(blob)
        view: dict[str, Any] = {"buffer": 0, "byteOffset": offset, "byteLength": len(blob)}
        if target is not None:
            view["target"] = target
        buffer_views.append(view)
        return len(buffer_views) - 1

    for mesh_i, mesh in enumerate(meshset.meshes):
        expanded_vertices = [mesh.vertices[index] for tri in mesh.triangles for index in tri]
        expanded_uvs = [mesh.panel_uvs[index] for tri in mesh.triangles for index in tri]
        expanded_indices = [(i, i + 1, i + 2) for i in range(0, len(expanded_vertices), 3)]
        normals, tangents = expanded_triangle_frames(mesh)

        pos_view = append_blob(_write_floats(expanded_vertices), 34962)
        norm_view = append_blob(_write_floats(normals), 34962)
        tangent_view = append_blob(_write_floats(tangents), 34962)
        uv_view = append_blob(_write_floats(expanded_uvs), 34962)
        idx_view = append_blob(_write_indices(expanded_indices), 34963)
        mins = [min(v[i] for v in expanded_vertices) for i in range(3)]
        maxs = [max(v[i] for v in expanded_vertices) for i in range(3)]
        pos_acc = len(accessors)
        accessors.append(
            {
                "bufferView": pos_view,
                "componentType": 5126,
                "count": len(expanded_vertices),
                "type": "VEC3",
                "min": mins,
                "max": maxs,
            }
        )
        norm_acc = len(accessors)
        accessors.append(
            {"bufferView": norm_view, "componentType": 5126, "count": len(normals), "type": "VEC3"}
        )
        tangent_acc = len(accessors)
        accessors.append(
            {
                "bufferView": tangent_view,
                "componentType": 5126,
                "count": len(tangents),
                "type": "VEC4",
            }
        )
        uv_acc = len(accessors)
        accessors.append(
            {
                "bufferView": uv_view,
                "componentType": 5126,
                "count": len(expanded_uvs),
                "type": "VEC2",
            }
        )
        idx_acc = len(accessors)
        accessors.append(
            {
                "bufferView": idx_view,
                "componentType": 5125,
                "count": len(expanded_indices) * 3,
                "type": "SCALAR",
            }
        )
        meshes_json.append(
            {
                "name": mesh.name,
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": pos_acc,
                            "NORMAL": norm_acc,
                            "TANGENT": tangent_acc,
                            "TEXCOORD_0": uv_acc,
                        },
                        "indices": idx_acc,
                        "material": 0,
                        "mode": 4,
                        "extras": {"panelId": mesh.panel_id, "primitiveOrder": mesh_i},
                    }
                ],
                "extras": {"panelId": mesh.panel_id},
            }
        )
        nodes.append({"mesh": mesh_i, "name": mesh.name, "extras": {"panelId": mesh.panel_id}})

    gltf: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "closy-forge-0.1.0"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes_json,
        "materials": [
            {
                "name": material_name,
                "pbrMetallicRoughness": {
                    "baseColorFactor": list(color),
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.86,
                },
                "doubleSided": True,
            }
        ],
        "buffers": [{"byteLength": len(buffer)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
    }
    json_bytes = _pad4(
        json.dumps(gltf, sort_keys=True, separators=(",", ":")).encode("utf-8"), b" "
    )
    bin_bytes = _pad4(bytes(buffer), b"\x00")
    total_len = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    with path.open("wb") as handle:
        handle.write(struct.pack("<III", 0x46546C67, 2, total_len))
        handle.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))
        handle.write(json_bytes)
        handle.write(struct.pack("<II", len(bin_bytes), 0x004E4942))
        handle.write(bin_bytes)


def write_indexed_glb(
    path: Path,
    meshset: MeshSet,
    material_name: str,
    color: tuple[float, float, float, float],
    *,
    normalize_signed_zero: bool = False,
) -> None:
    """Write an indexed GLB without expanding vertices per triangle.

    The default writer preserves the original D0 render fixture behaviour. This
    indexed variant is used by mesh-cleanup previews so duplicate-position welds
    remain visible to topology diagnostics.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = bytearray()
    buffer_views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    meshes_json: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []

    def append_blob(blob: bytes, target: int | None = None) -> int:
        nonlocal buffer
        buffer.extend(b"\x00" * ((4 - len(buffer) % 4) % 4))
        offset = len(buffer)
        buffer.extend(blob)
        view: dict[str, Any] = {"buffer": 0, "byteOffset": offset, "byteLength": len(blob)}
        if target is not None:
            view["target"] = target
        buffer_views.append(view)
        return len(buffer_views) - 1

    for mesh_i, mesh in enumerate(meshset.meshes):
        if not mesh.vertices or not mesh.triangles:
            continue
        uvs = mesh.panel_uvs
        if len(uvs) != len(mesh.vertices):
            uvs = [(0.0, 0.0) for _ in mesh.vertices]
        normals = vertex_normals(mesh)
        tangents = vertex_tangents(mesh, normals)

        pos_view = append_blob(
            _write_floats(mesh.vertices, normalize_signed_zero=normalize_signed_zero), 34962
        )
        norm_view = append_blob(
            _write_floats(normals, normalize_signed_zero=normalize_signed_zero), 34962
        )
        tangent_view = append_blob(
            _write_floats(tangents, normalize_signed_zero=normalize_signed_zero), 34962
        )
        uv_view = append_blob(
            _write_floats(uvs, normalize_signed_zero=normalize_signed_zero), 34962
        )
        idx_view = append_blob(_write_indices(mesh.triangles), 34963)
        mins = [min(v[i] for v in mesh.vertices) for i in range(3)]
        maxs = [max(v[i] for v in mesh.vertices) for i in range(3)]
        pos_acc = len(accessors)
        accessors.append(
            {
                "bufferView": pos_view,
                "componentType": 5126,
                "count": len(mesh.vertices),
                "type": "VEC3",
                "min": mins,
                "max": maxs,
            }
        )
        norm_acc = len(accessors)
        accessors.append(
            {"bufferView": norm_view, "componentType": 5126, "count": len(normals), "type": "VEC3"}
        )
        tangent_acc = len(accessors)
        accessors.append(
            {
                "bufferView": tangent_view,
                "componentType": 5126,
                "count": len(tangents),
                "type": "VEC4",
            }
        )
        uv_acc = len(accessors)
        accessors.append(
            {
                "bufferView": uv_view,
                "componentType": 5126,
                "count": len(uvs),
                "type": "VEC2",
            }
        )
        idx_acc = len(accessors)
        accessors.append(
            {
                "bufferView": idx_view,
                "componentType": 5125,
                "count": len(mesh.triangles) * 3,
                "type": "SCALAR",
            }
        )
        meshes_json.append(
            {
                "name": mesh.name,
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": pos_acc,
                            "NORMAL": norm_acc,
                            "TANGENT": tangent_acc,
                            "TEXCOORD_0": uv_acc,
                        },
                        "indices": idx_acc,
                        "material": 0,
                        "mode": 4,
                        "extras": {
                            "panelId": mesh.panel_id,
                            "materialId": mesh.material_id,
                            "primitiveOrder": mesh_i,
                        },
                    }
                ],
                "extras": {"panelId": mesh.panel_id, "materialId": mesh.material_id},
            }
        )
        nodes.append(
            {
                "mesh": len(meshes_json) - 1,
                "name": mesh.name,
                "extras": {"panelId": mesh.panel_id, "materialId": mesh.material_id},
            }
        )

    gltf: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "closy-forge-0.1.0-indexed"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes_json,
        "materials": [
            {
                "name": material_name,
                "pbrMetallicRoughness": {
                    "baseColorFactor": list(color),
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.86,
                },
                "doubleSided": True,
            }
        ],
        "buffers": [{"byteLength": len(buffer)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
    }
    json_bytes = _pad4(
        json.dumps(gltf, sort_keys=True, separators=(",", ":")).encode("utf-8"), b" "
    )
    bin_bytes = _pad4(bytes(buffer), b"\x00")
    total_len = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    with path.open("wb") as handle:
        handle.write(struct.pack("<III", 0x46546C67, 2, total_len))
        handle.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))
        handle.write(json_bytes)
        handle.write(struct.pack("<II", len(bin_bytes), 0x004E4942))
        handle.write(bin_bytes)


def audit_glb(path: Path) -> dict[str, Any]:
    gltf, _ = _read_glb(path)
    mesh_count = len(gltf.get("meshes", []))
    primitive_count = sum(len(mesh.get("primitives", [])) for mesh in gltf.get("meshes", []))
    triangle_estimate = 0
    semantic_attribute_counts: dict[str, int] = {}
    semantic_accessor_counts: dict[str, int] = {}
    semantic_accessor_types: dict[str, list[str]] = {}
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            attributes = primitive.get("attributes", {})
            if isinstance(attributes, dict):
                for semantic, accessor_index in attributes.items():
                    semantic_attribute_counts[semantic] = (
                        semantic_attribute_counts.get(semantic, 0) + 1
                    )
                    accessor = gltf["accessors"][int(accessor_index)]
                    semantic_accessor_counts[semantic] = semantic_accessor_counts.get(
                        semantic, 0
                    ) + int(accessor.get("count", 0))
                    semantic_accessor_types.setdefault(semantic, []).append(
                        str(accessor.get("type", ""))
                    )
            accessor_index = primitive.get("indices")
            if accessor_index is None:
                accessor_index = primitive.get("attributes", {}).get("POSITION")
            if accessor_index is None:
                continue
            acc = gltf["accessors"][accessor_index]
            triangle_estimate += int(acc["count"]) // 3
    return {
        "validGlb20": True,
        "meshCount": mesh_count,
        "primitiveCount": primitive_count,
        "triangleEstimate": triangle_estimate,
        "materialCount": len(gltf.get("materials", [])),
        "nodeCount": len(gltf.get("nodes", [])),
        "semanticAttributeCounts": semantic_attribute_counts,
        "semanticAccessorCounts": semantic_accessor_counts,
        "semanticAccessorTypes": {
            semantic: sorted(set(types)) for semantic, types in semantic_accessor_types.items()
        },
        "hasVec4Tangents": semantic_attribute_counts.get("TANGENT", 0) == primitive_count
        and semantic_accessor_counts.get("TANGENT", 0) > 0
        and set(semantic_accessor_types.get("TANGENT", [])) == {"VEC4"},
    }


def audit_glb_geometry(path: Path, *, minimum_triangle_area: float = 1e-12) -> dict[str, Any]:
    """Independently decode render attributes and audit processor-critical geometry."""

    gltf, binary = _read_glb(path)
    totals = {
        "vertexCount": 0,
        "triangleCount": 0,
        "nonfinitePositionCount": 0,
        "nonfiniteNormalCount": 0,
        "nonfiniteTangentCount": 0,
        "nonfiniteUvCount": 0,
        "repeatedIndexTriangleCount": 0,
        "duplicateOrientedTriangleCount": 0,
        "duplicateUnorientedTriangleCount": 0,
        "zeroAreaTriangleCount": 0,
        "indexOutOfRangeCount": 0,
    }
    witnesses: list[dict[str, Any]] = []
    global_triangle = 0
    for mesh_index, mesh_doc in enumerate(gltf.get("meshes", [])):
        mesh_extras = mesh_doc.get("extras", {})
        for primitive_index, primitive in enumerate(mesh_doc.get("primitives", [])):
            attributes = primitive.get("attributes", {})
            required = ("POSITION", "NORMAL", "TANGENT", "TEXCOORD_0")
            if any(name not in attributes for name in required):
                raise ValueError("missing_required_render_attribute")
            positions = [_vec3(row) for row in _read_accessor(gltf, binary, attributes["POSITION"])]
            normals = [_vec3(row) for row in _read_accessor(gltf, binary, attributes["NORMAL"])]
            tangents = _read_accessor(gltf, binary, attributes["TANGENT"])
            uvs = [_vec2(row) for row in _read_accessor(gltf, binary, attributes["TEXCOORD_0"])]
            if not (len(positions) == len(normals) == len(tangents) == len(uvs)):
                raise ValueError("render_attribute_count_mismatch")
            if "indices" in primitive:
                flat_indices = [
                    _scalar_int(row)
                    for row in _read_accessor(gltf, binary, int(primitive["indices"]))
                ]
            else:
                flat_indices = list(range(len(positions)))
            if len(flat_indices) % 3:
                raise ValueError("triangle_index_count_not_divisible_by_three")
            totals["vertexCount"] += len(positions)
            totals["triangleCount"] += len(flat_indices) // 3
            totals["nonfinitePositionCount"] += sum(
                not all(math.isfinite(value) for value in row) for row in positions
            )
            totals["nonfiniteNormalCount"] += sum(
                not all(math.isfinite(value) for value in row) for row in normals
            )
            totals["nonfiniteTangentCount"] += sum(
                len(row) != 4 or not all(math.isfinite(float(value)) for value in row)
                for row in tangents
            )
            totals["nonfiniteUvCount"] += sum(
                not all(math.isfinite(value) for value in row) for row in uvs
            )
            primitive_extras = primitive.get("extras", {})
            panel_id = str(
                primitive_extras.get("panelId")
                or (mesh_extras.get("panelId") if isinstance(mesh_extras, dict) else None)
                or mesh_doc.get("name", f"mesh_{mesh_index}")
            )
            material_index = int(primitive.get("material", 0))
            primitive_triangles = [
                tuple(flat_indices[index : index + 3]) for index in range(0, len(flat_indices), 3)
            ]
            oriented_counts = Counter(primitive_triangles)
            unoriented_counts = Counter(tuple(sorted(tri)) for tri in primitive_triangles)
            totals["duplicateOrientedTriangleCount"] += sum(
                count - 1 for count in oriented_counts.values()
            )
            totals["duplicateUnorientedTriangleCount"] += sum(
                count - 1 for count in unoriented_counts.values()
            )
            for local_triangle in range(len(flat_indices) // 3):
                tri = tuple(flat_indices[local_triangle * 3 : local_triangle * 3 + 3])
                out_of_range = any(index < 0 or index >= len(positions) for index in tri)
                repeated = len(set(tri)) != 3
                if out_of_range:
                    totals["indexOutOfRangeCount"] += 1
                    area = 0.0
                else:
                    area = _triangle_area(positions[tri[0]], positions[tri[1]], positions[tri[2]])
                if repeated:
                    totals["repeatedIndexTriangleCount"] += 1
                if not math.isfinite(area) or area <= minimum_triangle_area:
                    totals["zeroAreaTriangleCount"] += 1
                    if len(witnesses) < 64:
                        witnesses.append(
                            {
                                "globalTriangleIndex": global_triangle,
                                "meshIndex": mesh_index,
                                "primitiveIndex": primitive_index,
                                "localTriangleIndex": local_triangle,
                                "panelId": panel_id,
                                "materialIndex": material_index,
                                "indices": list(tri),
                                "positions": [
                                    list(positions[index])
                                    for index in tri
                                    if 0 <= index < len(positions)
                                ],
                                "areaMeters2": area,
                                "repeatedIndex": repeated,
                                "indexOutOfRange": out_of_range,
                            }
                        )
                global_triangle += 1
    failure_count = sum(
        int(totals[key])
        for key in (
            "nonfinitePositionCount",
            "nonfiniteNormalCount",
            "nonfiniteTangentCount",
            "nonfiniteUvCount",
            "repeatedIndexTriangleCount",
            "duplicateOrientedTriangleCount",
            "duplicateUnorientedTriangleCount",
            "zeroAreaTriangleCount",
            "indexOutOfRangeCount",
        )
    )
    return {
        "schemaVersion": 1,
        "auditVersion": "closy.glb.processor_geometry_audit.v1",
        "minimumTriangleAreaMeters2": minimum_triangle_area,
        **totals,
        "status": "pass" if failure_count == 0 else "fail",
        "witnesses": witnesses,
    }


def _triangle_area(
    a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]
) -> float:
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cross_value = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return 0.5 * math.sqrt(sum(value * value for value in cross_value))


def read_glb_meshset(path: Path) -> MeshSet:
    """Read triangle POSITION/index data from a GLB for diagnostics.

    This intentionally supports the conservative GLB subset Closy writes and
    common non-interleaved triangle primitives. Unsupported provider features
    should fail audit rather than silently producing misleading topology data.
    """

    gltf, binary = _read_glb(path)
    meshes: list[Mesh] = []
    for mesh_index, mesh_doc in enumerate(gltf.get("meshes", [])):
        mesh_name = str(mesh_doc.get("name", f"mesh_{mesh_index}"))
        mesh_extras = mesh_doc.get("extras", {})
        for primitive_index, primitive in enumerate(mesh_doc.get("primitives", [])):
            if int(primitive.get("mode", 4)) != 4:
                raise ValueError("unsupported_glb_primitive_mode")
            attributes = primitive.get("attributes", {})
            if "POSITION" not in attributes:
                raise ValueError("missing_position_accessor")
            positions = _read_accessor(gltf, binary, int(attributes["POSITION"]))
            vertices = [_vec3(value) for value in positions]
            indices: list[int]
            if "indices" in primitive:
                indices = [
                    _scalar_int(value)
                    for value in _read_accessor(gltf, binary, int(primitive["indices"]))
                ]
            else:
                indices = list(range(len(vertices)))
            if len(indices) % 3 != 0:
                raise ValueError("triangle_index_count_not_divisible_by_three")
            triangles = [
                (indices[i], indices[i + 1], indices[i + 2]) for i in range(0, len(indices), 3)
            ]
            uv_accessor_index = attributes.get("TEXCOORD_0")
            if uv_accessor_index is None:
                panel_uvs = [(0.0, 0.0) for _ in vertices]
            else:
                panel_uvs = [
                    _vec2(value) for value in _read_accessor(gltf, binary, int(uv_accessor_index))
                ]
                if len(panel_uvs) != len(vertices):
                    raise ValueError("texcoord_count_mismatch")
            primitive_extras = primitive.get("extras", {})
            panel_id = str(
                primitive_extras.get("panelId")
                or (mesh_extras.get("panelId") if isinstance(mesh_extras, dict) else None)
                or mesh_name
            )
            material_id = str(
                primitive_extras.get("materialId")
                or (mesh_extras.get("materialId") if isinstance(mesh_extras, dict) else None)
                or "material.cotton_jersey_reference_v1"
            )
            suffix = (
                "" if len(mesh_doc.get("primitives", [])) == 1 else f".primitive_{primitive_index}"
            )
            meshes.append(
                Mesh(
                    name=f"{mesh_name}{suffix}",
                    panel_id=panel_id,
                    vertices=vertices,
                    panel_uvs=panel_uvs,
                    triangles=triangles,
                    material_id=material_id,
                )
            )
    return MeshSet(meshes)


def _read_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    data = path.read_bytes()
    if len(data) < 20:
        raise ValueError("malformed_glb_too_small")
    magic, version, total = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2 or total != len(data):
        raise ValueError("malformed_glb_header")
    offset = 12
    gltf: dict[str, Any] | None = None
    binary = b""
    while offset + 8 <= len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        payload = data[offset + 8 : offset + 8 + length]
        if kind == 0x4E4F534A:
            gltf = json.loads(payload.decode("utf-8").rstrip(" \0"))
        elif kind == 0x004E4942:
            binary = payload
        offset += 8 + length
    if gltf is None:
        raise ValueError("missing_json_chunk")
    return gltf, binary


def _read_accessor(
    gltf: dict[str, Any], binary: bytes, accessor_index: int
) -> list[tuple[Any, ...]]:
    accessor = gltf["accessors"][accessor_index]
    if "sparse" in accessor:
        raise ValueError("unsupported_sparse_accessor")
    view = gltf["bufferViews"][accessor["bufferView"]]
    component_type = int(accessor["componentType"])
    component_count = _accessor_component_count(str(accessor["type"]))
    component_format = _accessor_component_format(component_type)
    component_size = struct.calcsize("<" + component_format)
    stride = int(view.get("byteStride", component_size * component_count))
    base_offset = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    count = int(accessor["count"])
    values: list[tuple[Any, ...]] = []
    for index in range(count):
        offset = base_offset + index * stride
        row = struct.unpack_from("<" + component_format * component_count, binary, offset)
        values.append(row)
    return values


def _accessor_component_count(accessor_type: str) -> int:
    counts = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
    try:
        return counts[accessor_type]
    except KeyError as exc:
        raise ValueError("unsupported_accessor_type") from exc


def _accessor_component_format(component_type: int) -> str:
    formats = {
        5120: "b",
        5121: "B",
        5122: "h",
        5123: "H",
        5125: "I",
        5126: "f",
    }
    try:
        return formats[component_type]
    except KeyError as exc:
        raise ValueError("unsupported_accessor_component_type") from exc


def _vec3(value: tuple[Any, ...]) -> tuple[float, float, float]:
    if len(value) != 3:
        raise ValueError("expected_vec3_accessor")
    return (float(value[0]), float(value[1]), float(value[2]))


def _vec2(value: tuple[Any, ...]) -> tuple[float, float]:
    if len(value) != 2:
        raise ValueError("expected_vec2_accessor")
    return (float(value[0]), float(value[1]))


def _scalar_int(value: tuple[Any, ...]) -> int:
    if len(value) != 1:
        raise ValueError("expected_scalar_accessor")
    return int(value[0])
