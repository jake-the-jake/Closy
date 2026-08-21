from __future__ import annotations

import json
import struct
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .mesh_model import MeshSet, triangle_normal


def _pad4(data: bytes, pad: bytes) -> bytes:
    return data + pad * ((4 - len(data) % 4) % 4)


def _write_floats(values: Sequence[Sequence[float]]) -> bytes:
    return b"".join(struct.pack("<" + "f" * len(value), *value) for value in values)


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
        normals = [triangle_normal(mesh.vertices, tri) for tri in mesh.triangles for _ in range(3)]
        expanded_vertices = [mesh.vertices[index] for tri in mesh.triangles for index in tri]
        expanded_uvs = [mesh.panel_uvs[index] for tri in mesh.triangles for index in tri]
        expanded_indices = [(i, i + 1, i + 2) for i in range(0, len(expanded_vertices), 3)]

        pos_view = append_blob(_write_floats(expanded_vertices), 34962)
        norm_view = append_blob(_write_floats(normals), 34962)
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


def audit_glb(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) < 20:
        raise ValueError("malformed_glb_too_small")
    magic, version, total = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2 or total != len(data):
        raise ValueError("malformed_glb_header")
    offset = 12
    gltf: dict[str, Any] | None = None
    while offset + 8 <= len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        payload = data[offset + 8 : offset + 8 + length]
        if kind == 0x4E4F534A:
            gltf = json.loads(payload.decode("utf-8").rstrip(" \0"))
        offset += 8 + length
    if gltf is None:
        raise ValueError("missing_json_chunk")
    mesh_count = len(gltf.get("meshes", []))
    primitive_count = sum(len(mesh.get("primitives", [])) for mesh in gltf.get("meshes", []))
    triangle_estimate = 0
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            acc = gltf["accessors"][primitive["indices"]]
            triangle_estimate += int(acc["count"]) // 3
    return {
        "validGlb20": True,
        "meshCount": mesh_count,
        "primitiveCount": primitive_count,
        "triangleEstimate": triangle_estimate,
        "materialCount": len(gltf.get("materials", [])),
        "nodeCount": len(gltf.get("nodes", [])),
    }
