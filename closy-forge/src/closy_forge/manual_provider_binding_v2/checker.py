"""Independent rest check: shared GLB/hash helpers, no producer binding imports.

The wire layout and frame equations are implemented here separately on purpose.
Declared metrics are comparisons only, never inputs to the derived result.
"""

from __future__ import annotations

import json
import math
import struct
from collections import Counter
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import audit_glb_geometry, read_glb_meshset
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.package_io.hashing import geometry_content_hash, sha256_file, topology_hash

REST_LIMIT_METERS = 0.008
FLOAT32_COMPARISON_TOLERANCE = 2e-6
_MAX_BYTES = 2097152
_MAX_VERTICES = 8192
_MAX_TRIANGLES = 16384


def _decode_glb(path: Path) -> MeshSet:
    # Bound allocation before the immutable shared accessor decoder is invoked.
    with path.open("rb") as handle:
        raw = handle.read(_MAX_BYTES + 1)
    if not 20 <= len(raw) <= _MAX_BYTES:
        raise ValueError("checker_v2_glb_byte_budget")
    magic, version, size = struct.unpack_from("<III", raw)
    if (magic, version, size) != (0x46546C67, 2, len(raw)):
        raise ValueError("checker_v2_glb_header")
    offset, chunks = 12, []
    while offset + 8 <= len(raw):
        length, kind = struct.unpack_from("<II", raw, offset)
        if length % 4 or offset + 8 + length > len(raw):
            raise ValueError("checker_v2_glb_chunk")
        chunks.append((kind, raw[offset + 8 : offset + 8 + length]))
        offset += 8 + length
    if offset != len(raw) or [c[0] for c in chunks] != [0x4E4F534A, 0x004E4942]:
        raise ValueError("checker_v2_glb_chunk_layout")
    doc = json.loads(chunks[0][1])
    if any(k in doc for k in ("skins", "animations", "extensionsRequired")) or any(
        any(k in node for k in ("matrix", "translation", "rotation", "scale", "skin"))
        for node in doc.get("nodes", [])
    ):
        raise ValueError("checker_v2_unsupported_glb_transform")
    accessors = doc.get("accessors", [])
    if not 1 <= len(accessors) <= 320 or any(
        type(a.get("count")) is not int
        or not 1 <= a["count"] <= _MAX_TRIANGLES * 3
        or "sparse" in a
        for a in accessors
    ):
        raise ValueError("checker_v2_glb_accessor_budget")
    primitives = [p for m in doc.get("meshes", []) for p in m.get("primitives", [])]
    if not 1 <= len(primitives) <= 64:
        raise ValueError("checker_v2_glb_panel_budget")
    total_vertices = total_triangles = 0
    for primitive in primitives:
        attrs = primitive.get("attributes", {})
        if primitive.get("mode", 4) != 4 or "indices" not in primitive:
            raise ValueError("checker_v2_indexed_triangles_required")
        if not {"POSITION", "NORMAL", "TANGENT", "TEXCOORD_0"} <= attrs.keys():
            raise ValueError("checker_v2_frame_attributes_missing")
        count = accessors[attrs["POSITION"]]["count"]
        for name, kind in (
            ("POSITION", "VEC3"),
            ("NORMAL", "VEC3"),
            ("TANGENT", "VEC4"),
            ("TEXCOORD_0", "VEC2"),
        ):
            accessor = accessors[attrs[name]]
            if (accessor.get("type"), accessor.get("componentType"), accessor["count"]) != (
                kind,
                5126,
                count,
            ):
                raise ValueError("checker_v2_frame_attribute_layout")
        index_accessor = accessors[primitive["indices"]]
        if index_accessor.get("type") != "SCALAR" or index_accessor["count"] % 3:
            raise ValueError("checker_v2_index_layout")
        total_vertices += count
        total_triangles += index_accessor["count"] // 3
    if total_vertices > _MAX_VERTICES or total_triangles > _MAX_TRIANGLES:
        raise ValueError("checker_v2_glb_mesh_budget")
    result = read_glb_meshset(path)
    if audit_glb_geometry(path)["status"] != "pass":
        raise ValueError("checker_v2_glb_geometry_invalid")
    return result


def _boundary_masks(mesh: Mesh) -> list[int]:
    # Derive boundary membership from both UV geometry and actual edge incidence.
    ordered = sorted(range(len(mesh.vertices)), key=lambda i: mesh.panel_uvs[i][1])
    rows: list[list[int]] = []
    for i in ordered:
        if not rows or mesh.panel_uvs[i][1] - mesh.panel_uvs[rows[-1][0]][1] > 2e-7:
            rows.append([])
        rows[-1].append(i)
    if len(rows) < 2 or min(map(len, rows)) < 2 or len({len(r) for r in rows}) != 1:
        raise ValueError("checker_v2_unsupported_uv_rows")
    masks = [0] * len(mesh.vertices)
    for r, row in enumerate(rows):
        row.sort(key=lambda i: mesh.panel_uvs[i][0])
        for c, i in enumerate(row):
            masks[i] = (
                (1 if c == 0 else 0)
                | (2 if c == len(row) - 1 else 0)
                | (4 if r == 0 else 0)
                | (8 if r == len(rows) - 1 else 0)
            )
    edges: Counter[tuple[int, int]] = Counter()
    directions: Counter[tuple[int, int]] = Counter()
    for a, b, c in mesh.triangles:
        for u, v in ((a, b), (b, c), (c, a)):
            edges[min(u, v), max(u, v)] += 1
            directions[u, v] += 1
    boundary = {i for edge, count in edges.items() if count == 1 for i in edge}
    if boundary != {i for i, mask in enumerate(masks) if mask} or any(
        count > 2 or (count == 2 and directions[a, b] != directions[b, a])
        for (a, b), count in edges.items()
    ):
        raise ValueError("checker_v2_boundary_or_winding_mismatch")
    return masks


def check_rest(
    cage_path: Path,
    render_path: Path,
    binding_path: Path,
    declared_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Decode bytes and independently derive rest max/P95/RMS.

    Invalid structure, stale identities, cross-panel/boundary influences, and
    forged declared metrics raise ValueError. Valid bytes over the geometric
    limit return status='fail'; the 2e-6 comparison tolerance NEVER relaxes 8 mm.
    If supplied, declared_metrics must contain restMaximumErrorMeters and
    restP95ErrorMeters; restRmsErrorMeters is compared when present.
    """
    try:
        return _check_rest(cage_path, render_path, binding_path, declared_metrics)
    except (IndexError, KeyError, TypeError, UnicodeError, struct.error, OverflowError) as exc:
        raise ValueError("checker_v2_malformed_payload") from exc


def _check_rest(
    cage_path: Path,
    render_path: Path,
    binding_path: Path,
    declared_metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    with binding_path.open("rb") as handle:
        data = handle.read(_MAX_BYTES + 1)
    layout = struct.Struct("<8s7I32s32s32s32s")
    if not layout.size <= len(data) <= _MAX_BYTES:
        raise ValueError("checker_v2_binding_size")
    magic, version, header, stride, count, tri_count, panel_count, meta, *identities = (
        layout.unpack_from(data)
    )
    if (magic, version, header, stride) != (b"CLSYBV2\0", 2, layout.size, 36):
        raise ValueError("checker_v2_binding_layout")
    if (
        not 1 <= count <= _MAX_VERTICES
        or not 1 <= tri_count <= _MAX_TRIANGLES
        or not (1 <= panel_count <= 64 and 1 <= meta <= 65536)
    ):
        raise ValueError("checker_v2_binding_count_budget")
    if len(data) != header + meta + count * stride:
        raise ValueError("checker_v2_binding_count_mismatch")
    table = json.loads(data[header : header + meta])
    if not isinstance(table, list) or len(table) != panel_count:
        raise ValueError("checker_v2_panel_count_mismatch")
    cage, render = _decode_glb(cage_path), _decode_glb(render_path)
    if cage.triangle_count != tri_count or render.vertex_count != count:
        raise ValueError("checker_v2_mesh_count_mismatch")
    if len(cage.meshes) != panel_count or len(render.meshes) != panel_count:
        raise ValueError("checker_v2_panel_count_mismatch")
    expected_hashes = (
        topology_hash(cage),
        topology_hash(render),
        geometry_content_hash(cage),
        geometry_content_hash(render),
    )
    for label, actual_hash, expected in zip(
        ("cage_topology", "render_topology", "cage_geometry", "render_geometry"),
        expected_hashes,
        identities,
        strict=True,
    ):
        if actual_hash != expected.hex():
            raise ValueError(f"checker_v2_{label}_mismatch")
    if len({m.panel_id for m in render.meshes}) != panel_count:
        raise ValueError("checker_v2_duplicate_panel")
    errors: list[float] = []
    vertex_offset = triangle_offset = 0
    worst: dict[str, Any] = {}
    for panel_index, (cm, rm, declared_panel) in enumerate(
        zip(
            cage.meshes,
            render.meshes,
            table,
            strict=True,
        )
    ):
        derived_panel = {
            "panelId": rm.panel_id,
            "materialId": rm.material_id,
            "renderVertexCount": len(rm.vertices),
            "cageVertexCount": len(cm.vertices),
            "cageTriangleCount": len(cm.triangles),
        }
        if declared_panel != derived_panel or (cm.panel_id, cm.material_id) != (
            rm.panel_id,
            rm.material_id,
        ):
            raise ValueError("checker_v2_panel_semantics_mismatch")
        if len(cm.vertices) > len(rm.vertices) * 0.6 or len(cm.triangles) >= len(rm.triangles):
            raise ValueError("checker_v2_cage_not_lower_resolution")
        cage_masks, render_masks = _boundary_masks(cm), _boundary_masks(rm)
        for local_index, target in enumerate(rm.vertices):
            index = vertex_offset + local_index
            ti, pi, w0, w1, w2, dx, dy, dz, mask = struct.unpack_from(
                "<II6fI", data, header + meta + index * stride
            )
            if pi != panel_index or not triangle_offset <= ti < triangle_offset + len(cm.triangles):
                raise ValueError("checker_v2_cross_panel_influence")
            weights, residual = (w0, w1, w2), (dx, dy, dz)
            if (
                any(not math.isfinite(w) or not 0 <= w <= 1 for w in weights)
                or abs(sum(weights) - 1) > 2e-7
            ):
                raise ValueError("checker_v2_invalid_weights")
            if any(not math.isfinite(x) or abs(x) > 0.03 for x in residual) or (
                math.sqrt(sum(x * x for x in residual)) > 0.03 + 2e-9
            ):
                raise ValueError("checker_v2_residual_budget")
            tri = cm.triangles[ti - triangle_offset]
            if mask != render_masks[local_index] or any(
                w != 0.0 and cage_masks[vi] & mask != mask
                for vi, w in zip(tri, weights, strict=True)
            ):
                raise ValueError("checker_v2_boundary_influence_mismatch")
            a, b, c = (cm.vertices[vi] for vi in tri)
            ab = [b[k] - a[k] for k in range(3)]
            ac = [c[k] - a[k] for k in range(3)]
            normal = [
                ab[1] * ac[2] - ab[2] * ac[1],
                ab[2] * ac[0] - ab[0] * ac[2],
                ab[0] * ac[1] - ab[1] * ac[0],
            ]
            length = math.sqrt(sum(x * x for x in ab))
            area2 = math.sqrt(sum(x * x for x in normal))
            if min(length, area2) <= 1e-12 or not math.isfinite(length + area2):
                raise ValueError("checker_v2_degenerate_frame")
            tangent = [x / length for x in ab]
            normal = [x / area2 for x in normal]
            second = [
                normal[1] * tangent[2] - normal[2] * tangent[1],
                normal[2] * tangent[0] - normal[0] * tangent[2],
                normal[0] * tangent[1] - normal[1] * tangent[0],
            ]
            actual = [
                w0 * a[k]
                + w1 * b[k]
                + w2 * c[k]
                + dx * tangent[k]
                + dy * second[k]
                + dz * normal[k]
                for k in range(3)
            ]
            error = math.sqrt(sum((actual[k] - target[k]) ** 2 for k in range(3)))
            if not math.isfinite(error):
                raise ValueError("checker_v2_nonfinite_reconstruction")
            if not errors or error > worst["errorMeters"]:
                worst = {
                    "panelId": rm.panel_id,
                    "renderVertexIndex": index,
                    "localVertexIndex": local_index,
                    "cageTriangleIndex": ti,
                    "uv": list(rm.panel_uvs[local_index]),
                    "errorMeters": error,
                }
            errors.append(error)
        vertex_offset += len(rm.vertices)
        triangle_offset += len(cm.triangles)
    ordered = sorted(errors)
    metrics = {
        "restMaximumErrorMeters": ordered[-1],
        "restP95ErrorMeters": ordered[math.ceil(0.95 * count) - 1],
        "restRmsErrorMeters": math.sqrt(math.fsum(e * e for e in errors) / count),
    }
    if declared_metrics is not None:
        if not {"restMaximumErrorMeters", "restP95ErrorMeters"} <= declared_metrics.keys():
            raise ValueError("checker_v2_declared_rest_metrics_missing")
        for key, value in metrics.items():
            if key not in declared_metrics:
                continue
            declared = declared_metrics[key]
            if (
                type(declared) not in (int, float)
                or not math.isfinite(declared)
                or abs(declared - value) > FLOAT32_COMPARISON_TOLERANCE
            ):
                raise ValueError(f"checker_v2_declared_rest_metric_mismatch:{key}")
    return {
        "schemaVersion": 2,
        "checkerVersion": "closy.manual_provider.rest_checker.v2",
        "status": "pass" if metrics["restMaximumErrorMeters"] <= REST_LIMIT_METERS else "fail",
        **metrics,
        "recomputedMetrics": metrics,
        "restLimitMeters": REST_LIMIT_METERS,
        "float32ComparisonTolerance": FLOAT32_COMPARISON_TOLERANCE,
        "recordCount": count,
        "cageVertexCount": cage.vertex_count,
        "renderVertexCount": render.vertex_count,
        "panelCount": panel_count,
        "cageVertexRatio": cage.vertex_count / render.vertex_count,
        "worstRestWitness": worst,
        "independentReconstruction": True,
        "cageSha256": sha256_file(cage_path),
        "renderSha256": sha256_file(render_path),
        "bindingSha256": sha256_file(binding_path),
    }
