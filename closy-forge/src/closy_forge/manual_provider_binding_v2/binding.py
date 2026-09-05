"""Geometry-driven, chart-restricted binding, not a canonical topology generator.

The cage retains every second row/column and both endpoints. UV row geometry
identifies the chart; every fine cell must have its two actual oriented faces.
Each dense vertex chooses the geometric closest point on its coarse chart cell,
restricted to the corresponding boundary segment at edges/corners. A metric,
orthonormal triangle-frame residual follows subsequent cage motion.
"""

from __future__ import annotations

import json
import math
import struct
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet, Tri, Vec3, cross, sub
from closy_forge.package_io.hashing import geometry_content_hash, topology_hash

MAGIC = b"CLSYBV2\0"
HEADER = struct.Struct("<8s7I32s32s32s32s")
RECORD = struct.Struct("<II6fI")
MAX_VERTICES = 8192
MAX_TRIANGLES = 16384
MAX_PANELS = 64
MAX_BYTES = 2 * 1024 * 1024
MAX_METADATA_BYTES = 65536
MAX_RESIDUAL_METERS = 0.03
WEIGHT_TOLERANCE = 2e-7
UV_ROW_TOLERANCE = 2e-7
REFINEMENT_VERSION = "broad_metric_cell.v1"
COARSE_EDGE_TRIGGER_METERS = 0.14
COARSE_BIDIRECTIONAL_SPAN_METERS = 0.10


def refinement_policy() -> dict[str, Any]:
    return {
        "version": REFINEMENT_VERSION,
        "maximumPasses": 1,
        "coarseTriangleEdgeTriggerMeters": COARSE_EDGE_TRIGGER_METERS,
        "bothChartDirectionSpanTriggerMeters": COARSE_BIDIRECTIONAL_SPAN_METERS,
        "selection": "least_added_vertices_then_shorter_mean_metric_span_then_columns",
        "operation": "retain_intermediate_samples_in_triggered_intervals_of_one_axis",
        "maximumCageVertexRatioPerPanel": 0.6,
        "edgeTriggerIsNotFinalEdgeCap": True,
    }


@dataclass(frozen=True)
class PanelV2:
    panel_id: str
    material_id: str
    render_vertex_count: int
    cage_vertex_count: int
    cage_triangle_count: int


@dataclass(frozen=True)
class BindingRecordV2:
    simulation_triangle_index: int
    panel_table_index: int
    weights: Vec3
    local_residual: Vec3
    boundary_mask: int = 0


@dataclass(frozen=True)
class BindingV2:
    records: tuple[BindingRecordV2, ...]
    panels: tuple[PanelV2, ...]
    simulation_topology_hash: str
    render_topology_hash: str
    simulation_geometry_hash: str
    render_geometry_hash: str

    @property
    def simulation_triangle_count(self) -> int:
        return sum(panel.cage_triangle_count for panel in self.panels)


@dataclass(frozen=True)
class BoundGarmentV2:
    cage: MeshSet
    binding: BindingV2
    report: dict[str, Any]

    @property
    def simulation(self) -> MeshSet:
        return self.cage


def _f32(value: float) -> float:
    return float(struct.unpack("<f", struct.pack("<f", value))[0])


def _points(mesh: Mesh, triangle: Tri) -> tuple[Vec3, Vec3, Vec3]:
    return mesh.vertices[triangle[0]], mesh.vertices[triangle[1]], mesh.vertices[triangle[2]]


def _dot(a: Vec3, b: Vec3) -> float:
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def _unit(a: Vec3) -> Vec3:
    length = math.sqrt(_dot(a, a))
    if not math.isfinite(length) or length <= 1e-12:
        raise ValueError("binding_v2_degenerate_triangle_frame")
    return (a[0] / length, a[1] / length, a[2] / length)


def _frame(points: tuple[Vec3, Vec3, Vec3]) -> tuple[Vec3, Vec3, Vec3]:
    edge = sub(points[1], points[0])
    normal = _unit(cross(edge, sub(points[2], points[0])))
    tangent = _unit(edge)
    return tangent, cross(normal, tangent), normal


def _blend(points: tuple[Vec3, Vec3, Vec3], weights: Vec3) -> Vec3:
    return (
        _dot((points[0][0], points[1][0], points[2][0]), weights),
        _dot((points[0][1], points[1][1], points[2][1]), weights),
        _dot((points[0][2], points[1][2], points[2][2]), weights),
    )


def _closest_weights(point: Vec3, points: tuple[Vec3, Vec3, Vec3], allowed: list[int]) -> Vec3:
    candidates: list[Vec3] = []
    for i in allowed:
        weights = [0.0, 0.0, 0.0]
        weights[i] = 1.0
        candidates.append((weights[0], weights[1], weights[2]))
    for i, j in ((0, 1), (1, 2), (2, 0)):
        if i not in allowed or j not in allowed:
            continue
        edge = sub(points[j], points[i])
        t = min(1.0, max(0.0, _dot(sub(point, points[i]), edge) / _dot(edge, edge)))
        weights = [0.0, 0.0, 0.0]
        weights[i], weights[j] = 1.0 - t, t
        candidates.append((weights[0], weights[1], weights[2]))
    if len(allowed) == 3:
        tangent, bitangent, _ = _frame(points)
        ac, ap = sub(points[2], points[0]), sub(point, points[0])
        v = _dot(ap, bitangent) / _dot(ac, bitangent)
        u = (_dot(ap, tangent) - v * _dot(ac, tangent)) / math.dist(points[0], points[1])
        if u >= 0.0 and v >= 0.0 and u + v <= 1.0:
            candidates.append((1.0 - u - v, u, v))
    if not candidates:
        raise ValueError("binding_v2_boundary_without_support")
    return min(candidates, key=lambda w: math.dist(point, _blend(points, w)))


def _lattice(mesh: Mesh) -> tuple[list[list[int]], int]:
    """Support row-aligned, tapered UV grids, including arbitrary vertex order."""
    if len(mesh.panel_uvs) != len(mesh.vertices) or not mesh.triangles:
        raise ValueError("binding_v2_unsupported_uv_lattice")
    ordered = sorted(range(len(mesh.vertices)), key=lambda i: (mesh.panel_uvs[i][1], i))
    rows: list[list[int]] = []
    for i in ordered:
        if not rows or abs(mesh.panel_uvs[i][1] - mesh.panel_uvs[rows[-1][0]][1]) > (
            UV_ROW_TOLERANCE
        ):
            rows.append([])
        rows[-1].append(i)
    for row in rows:
        row.sort(key=lambda i: mesh.panel_uvs[i][0])
    columns = len(rows[0])
    if len(rows) < 3 or columns < 3 or any(len(row) != columns for row in rows):
        raise ValueError("binding_v2_unsupported_uv_lattice")
    if any(
        mesh.panel_uvs[b][0] - mesh.panel_uvs[a][0] <= UV_ROW_TOLERANCE
        for row in rows
        for a, b in zip(row, row[1:], strict=False)
    ):
        raise ValueError("binding_v2_ambiguous_uv_lattice")
    coordinates = {i: (r, c) for r, row in enumerate(rows) for c, i in enumerate(row)}
    cells: dict[tuple[int, int], list[frozenset[int]]] = defaultdict(list)
    winding = 0
    for triangle in mesh.triangles:
        if len(set(triangle)) != 3 or any(i not in coordinates for i in triangle):
            raise ValueError("binding_v2_invalid_triangle_indices")
        rc = [coordinates[i] for i in triangle]
        r, c = min(p[0] for p in rc), min(p[1] for p in rc)
        if max(p[0] for p in rc) != r + 1 or max(p[1] for p in rc) != c + 1:
            raise ValueError("binding_v2_unsupported_grid_connectivity")
        cells[r, c].append(frozenset(triangle))
        ua, ub, ud = (mesh.panel_uvs[i] for i in triangle)
        signed_area = (ub[0] - ua[0]) * (ud[1] - ua[1]) - (ub[1] - ua[1]) * (ud[0] - ua[0])
        if abs(signed_area) <= 1e-12:
            raise ValueError("binding_v2_degenerate_uv_triangle")
        sign = 1 if signed_area > 0 else -1
        if winding and winding != sign:
            raise ValueError("binding_v2_inconsistent_winding")
        winding = sign
        _frame(_points(mesh, triangle))
    for r in range(len(rows) - 1):
        for c in range(columns - 1):
            a, b, d, e = rows[r][c], rows[r][c + 1], rows[r + 1][c], rows[r + 1][c + 1]
            actual = cells[r, c]
            choices = (
                {frozenset((a, b, e)), frozenset((a, e, d))},
                {frozenset((a, b, d)), frozenset((b, e, d))},
            )
            if len(actual) != 2 or set(actual) not in choices:
                raise ValueError("binding_v2_unsupported_grid_connectivity")
    return rows, winding


def _axis(size: int) -> list[int]:
    return sorted(set(range(0, size, 2)) | {size - 1})


def _mask(row: int, column: int, rows: int, columns: int) -> int:
    return (
        int(column == 0)
        | (int(column == columns - 1) << 1)
        | (int(row == 0) << 2)
        | (int(row == rows - 1) << 3)
    )


def _refined_axes(mesh: Mesh, rows: list[list[int]]) -> tuple[list[int], list[int], dict[str, Any]]:
    rs, cs = _axis(len(rows)), _axis(len(rows[0]))
    add_rows: set[int] = set()
    add_columns: set[int] = set()
    spans: list[tuple[float, float]] = []
    maximum_edge = 0.0
    for r0, r1 in zip(rs, rs[1:], strict=False):
        for c0, c1 in zip(cs, cs[1:], strict=False):
            a, b, d, e = (
                mesh.vertices[rows[r][c]] for r, c in ((r0, c0), (r0, c1), (r1, c0), (r1, c1))
            )
            u = max(math.dist(a, b), math.dist(d, e))
            v = max(math.dist(a, d), math.dist(b, e))
            edge = max(u, v, math.dist(a, e))
            maximum_edge = max(maximum_edge, edge)
            if edge > COARSE_EDGE_TRIGGER_METERS and min(u, v) > COARSE_BIDIRECTIONAL_SPAN_METERS:
                spans.append((u, v))
                add_rows.update(range(r0 + 1, r1))
                add_columns.update(range(c0 + 1, c1))
    before = len(rs) * len(cs)
    # One panel-wide axis preserves a conforming lattice. Compare storage cost,
    # then actual metric span; neither identity nor world-axis orientation enters.
    choices = []
    if add_columns:
        choices.append((len(add_columns) * len(rs), math.fsum(s[0] for s in spans), "columns"))
    if add_rows:
        choices.append((len(add_rows) * len(cs), math.fsum(s[1] for s in spans), "rows"))
    axis = min(choices)[2] if choices else "none"
    if axis == "columns":
        cs = sorted(set(cs) | add_columns)
    elif axis == "rows":
        rs = sorted(set(rs) | add_rows)
    return (
        rs,
        cs,
        {
            "refinementVersion": REFINEMENT_VERSION,
            "triggeredCellCount": len(spans),
            "initialMaximumCoarseTriangleEdgeMeters": maximum_edge,
            "refinedAxis": axis,
            "addedCageVertexCount": len(rs) * len(cs) - before,
            "retainedRowIndices": rs,
            "retainedColumnIndices": cs,
        },
    )


def _cage(
    mesh: Mesh, rows: list[list[int]], winding: int
) -> tuple[Mesh, list[int], list[int], dict[str, Any]]:
    rs, cs, refinement = _refined_axes(mesh, rows)
    selected = [rows[r][c] for r in rs for c in cs]
    triangles = []
    for r in range(len(rs) - 1):
        for c in range(len(cs) - 1):
            a = r * len(cs) + c
            b, d, e = a + 1, a + len(cs), a + len(cs) + 1
            cell = [(a, b, e), (a, e, d)]
            triangles.extend(cell if winding > 0 else [(x, z, y) for x, y, z in cell])
    result = Mesh(
        f"cage-v2:{mesh.name}",
        mesh.panel_id,
        [mesh.vertices[i] for i in selected],
        [mesh.panel_uvs[i] for i in selected],
        triangles,
        mesh.material_id,
    )
    # Every coarse face must point along all of the fine faces in its chart region.
    # Reject a folded/coarsening-incompatible chart instead of crossing cloth sides.
    fine_normals: dict[tuple[int, int], list[Vec3]] = defaultdict(list)
    coords = {i: (r, c) for r, row in enumerate(rows) for c, i in enumerate(row)}
    for tri in mesh.triangles:
        r = min(coords[i][0] for i in tri)
        c = min(coords[i][1] for i in tri)
        fine_normals[r, c].append(_frame(_points(mesh, tri))[2])
    for r in range(len(rs) - 1):
        for c in range(len(cs) - 1):
            start = 2 * (r * (len(cs) - 1) + c)
            for tri in triangles[start : start + 2]:
                normal = _frame(_points(result, tri))[2]
                if any(
                    _dot(normal, n) <= 0.0
                    for fr in range(rs[r], rs[r + 1])
                    for fc in range(cs[c], cs[c + 1])
                    for n in fine_normals[fr, fc]
                ):
                    raise ValueError("binding_v2_unsupported_folded_chart")
    if len(result.vertices) > len(mesh.vertices) * 0.6:
        raise ValueError("binding_v2_refinement_reduction_budget")
    return result, rs, cs, refinement


def _validate(binding: BindingV2) -> None:
    if not 1 <= len(binding.records) <= MAX_VERTICES or not 1 <= len(binding.panels) <= MAX_PANELS:
        raise ValueError("binding_v2_count_budget")
    if len({p.panel_id for p in binding.panels}) != len(binding.panels):
        raise ValueError("binding_v2_duplicate_panel")
    if sum(p.render_vertex_count for p in binding.panels) != len(binding.records):
        raise ValueError("binding_v2_record_count_mismatch")
    if not 1 <= binding.simulation_triangle_count <= MAX_TRIANGLES:
        raise ValueError("binding_v2_triangle_count_budget")
    record_start = triangle_start = 0
    for pi, panel in enumerate(binding.panels):
        if (
            not panel.panel_id
            or not panel.material_id
            or not 0 < panel.cage_vertex_count <= panel.render_vertex_count * 0.6
            or panel.cage_triangle_count <= 0
        ):
            raise ValueError("binding_v2_panel_or_reduction_invalid")
        for record in binding.records[record_start : record_start + panel.render_vertex_count]:
            if record.panel_table_index != pi or not (
                triangle_start
                <= record.simulation_triangle_index
                < triangle_start + panel.cage_triangle_count
            ):
                raise ValueError("binding_v2_cross_panel_influence")
            if any(not math.isfinite(w) or w < 0 or w > 1 for w in record.weights) or (
                abs(math.fsum(record.weights) - 1.0) > WEIGHT_TOLERANCE
            ):
                raise ValueError("binding_v2_invalid_weights")
            if any(
                not math.isfinite(x) or abs(x) > MAX_RESIDUAL_METERS
                for x in (record.local_residual)
            ) or math.sqrt(_dot(record.local_residual, record.local_residual)) > (
                MAX_RESIDUAL_METERS + 2e-9
            ):
                raise ValueError("binding_v2_residual_budget")
            if record.boundary_mask not in (0, 1, 2, 4, 8, 5, 6, 9, 10):
                raise ValueError("binding_v2_invalid_boundary_mask")
        record_start += panel.render_vertex_count
        triangle_start += panel.cage_triangle_count
    for value in (
        binding.simulation_topology_hash,
        binding.render_topology_hash,
        binding.simulation_geometry_hash,
        binding.render_geometry_hash,
    ):
        if len(value) != 64 or len(bytes.fromhex(value)) != 32:
            raise ValueError("binding_v2_invalid_hash")


def build_binding_v2(render: MeshSet, output_root: Path | None = None) -> BoundGarmentV2:
    """Bind clean indexed geometry; optional output_root writes binding/local_frame_v2.bin.

    No source authoring parameters are used. A single bounded metric refinement
    pass may retain intermediate lattice samples. Cage and render
    positions are rounded to the shared GLB float32 representation before fitting.
    The original render MeshSet (including its vertex/face order) is not mutated.
    """
    if (
        not 1 <= render.vertex_count <= MAX_VERTICES
        or not 1 <= render.triangle_count <= (MAX_TRIANGLES)
        or not 1 <= len(render.meshes) <= MAX_PANELS
    ):
        raise ValueError("binding_v2_mesh_budget")
    cages, panels, records = [], [], []
    triangle_start = 0
    chart_reports = []
    targets = []
    for pi, source in enumerate(render.meshes):
        if any(
            not math.isfinite(x) or abs(x) > 1e4
            for row in (*source.vertices, *source.panel_uvs)
            for x in row
        ):
            raise ValueError("binding_v2_nonfinite_or_unbounded_geometry")
        mesh = Mesh(
            source.name,
            source.panel_id,
            [(_f32(x), _f32(y), _f32(z)) for x, y, z in source.vertices],
            [(_f32(u), _f32(v)) for u, v in source.panel_uvs],
            list(source.triangles),
            source.material_id,
        )
        rows, winding = _lattice(mesh)
        cage, rs, cs, refinement = _cage(mesh, rows, winding)
        coordinates = {i: (r, c) for r, row in enumerate(rows) for c, i in enumerate(row)}
        cage_masks = [_mask(r, c, len(rs), len(cs)) for r in range(len(rs)) for c in range(len(cs))]
        for i, point in enumerate(mesh.vertices):
            row, column = coordinates[i]
            mask = _mask(row, column, len(rows), len(rows[0]))
            candidates = []
            for cr in range(len(rs) - 1):
                if not rs[cr] <= row <= rs[cr + 1]:
                    continue
                for cc in range(len(cs) - 1):
                    if not cs[cc] <= column <= cs[cc + 1]:
                        continue
                    start = 2 * (cr * (len(cs) - 1) + cc)
                    for ti in (start, start + 1):
                        tri = cage.triangles[ti]
                        allowed = [j for j, vi in enumerate(tri) if cage_masks[vi] & mask == mask]
                        if not allowed:
                            continue
                        points = _points(cage, tri)
                        weights = _closest_weights(point, points, allowed)
                        candidates.append((math.dist(point, _blend(points, weights)), ti, weights))
            _, ti, weights = min(candidates)
            points = _points(cage, cage.triangles[ti])
            residual = sub(point, _blend(points, weights))
            basis = _frame(points)
            local = (
                _f32(_dot(residual, basis[0])),
                _f32(_dot(residual, basis[1])),
                _f32(_dot(residual, basis[2])),
            )
            records.append(
                BindingRecordV2(
                    triangle_start + ti,
                    pi,
                    (_f32(weights[0]), _f32(weights[1]), _f32(weights[2])),
                    local,
                    mask,
                )
            )
        cages.append(cage)
        panels.append(
            PanelV2(
                mesh.panel_id,
                mesh.material_id,
                len(mesh.vertices),
                len(cage.vertices),
                len(cage.triangles),
            )
        )
        targets.extend(mesh.vertices)
        triangle_start += len(cage.triangles)
        chart_reports.append(
            {
                "panelId": mesh.panel_id,
                "rows": len(rows),
                "columns": len(rows[0]),
                "winding": winding,
                **refinement,
            }
        )
    simulation = MeshSet(cages)
    binding = BindingV2(
        tuple(records),
        tuple(panels),
        topology_hash(simulation),
        topology_hash(render),
        geometry_content_hash(simulation),
        geometry_content_hash(render),
    )
    _validate(binding)
    positions = reconstruct_v2(simulation, binding)
    errors = sorted(math.dist(p, q) for p, q in zip(positions, targets, strict=True))
    report = {
        "schemaVersion": 2,
        "bindingVersion": "closy.manual_provider.local_frame.v2",
        "scope": "manual_provider_binding_v2_development",
        "boundAssetId": f"bound-v2:{binding.render_geometry_hash[:20]}",
        "simulationTopologyHash": binding.simulation_topology_hash,
        "renderTopologyHash": binding.render_topology_hash,
        "recordCount": len(records),
        "coverage": 1.0,
        "outOfDomainCount": 0,
        "cageVertexCount": simulation.vertex_count,
        "renderVertexCount": render.vertex_count,
        "cageVertexRatio": simulation.vertex_count / render.vertex_count,
        "influencesPerVertex": 3,
        "samplingStride": 2,
        "refinementCount": sum(chart["addedCageVertexCount"] for chart in chart_reports),
        "refinementPolicy": refinement_policy(),
        "maximumLocalResidualMeters": max(
            math.sqrt(_dot(r.local_residual, r.local_residual)) for r in records
        ),
        "maximumResidualCoordinateMeters": max(abs(x) for r in records for x in r.local_residual),
        "minimumWeight": min(w for r in records for w in r.weights),
        "maximumWeight": max(w for r in records for w in r.weights),
        "maximumWeightSumError": max(abs(math.fsum(r.weights) - 1) for r in records),
        "restMaximumErrorMeters": errors[-1],
        "restP95ErrorMeters": errors[math.ceil(0.95 * len(errors)) - 1],
        "restRmsErrorMeters": math.sqrt(math.fsum(e * e for e in errors) / len(errors)),
        "fallbackDistinct": True,
        "charts": chart_reports,
        "status": "pass" if errors[-1] <= 0.008 else "fail",
    }
    if output_root is not None:
        write_binding_v2(output_root / "binding" / "local_frame_v2.bin", binding)
    return BoundGarmentV2(simulation, binding, report)


def write_binding_v2(path: Path, binding: BindingV2) -> None:
    _validate(binding)
    metadata = json.dumps(
        [
            {
                "panelId": p.panel_id,
                "materialId": p.material_id,
                "renderVertexCount": p.render_vertex_count,
                "cageVertexCount": p.cage_vertex_count,
                "cageTriangleCount": p.cage_triangle_count,
            }
            for p in binding.panels
        ],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    size = HEADER.size + len(metadata) + len(binding.records) * RECORD.size
    if len(metadata) > MAX_METADATA_BYTES or size > MAX_BYTES:
        raise ValueError("binding_v2_byte_budget")
    header = HEADER.pack(
        MAGIC,
        2,
        HEADER.size,
        RECORD.size,
        len(binding.records),
        binding.simulation_triangle_count,
        len(binding.panels),
        len(metadata),
        *(
            bytes.fromhex(h)
            for h in (
                binding.simulation_topology_hash,
                binding.render_topology_hash,
                binding.simulation_geometry_hash,
                binding.render_geometry_hash,
            )
        ),
    )
    data = b"".join(
        RECORD.pack(
            r.simulation_triangle_index,
            r.panel_table_index,
            *r.weights,
            *r.local_residual,
            r.boundary_mask,
        )
        for r in binding.records
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + metadata + data)


def read_binding_v2(path: Path) -> BindingV2:
    with path.open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    if not HEADER.size <= len(data) <= MAX_BYTES:
        raise ValueError("binding_v2_byte_budget_or_truncated_header")
    magic, version, header, stride, count, triangles, panels, meta, *hashes = HEADER.unpack_from(
        data
    )
    if (magic, version, header, stride) != (MAGIC, 2, HEADER.size, RECORD.size):
        raise ValueError("binding_v2_bad_layout")
    if (
        not 0 < count <= MAX_VERTICES
        or not 0 < panels <= MAX_PANELS
        or not (0 < triangles <= MAX_TRIANGLES and 0 < meta <= MAX_METADATA_BYTES)
    ):
        raise ValueError("binding_v2_count_budget")
    if len(data) != header + meta + count * stride:
        raise ValueError("binding_v2_record_count_mismatch")
    try:
        table = json.loads(data[header : header + meta])
        if not isinstance(table, list) or len(table) != panels:
            raise ValueError("binding_v2_panel_count_mismatch")
        panel_rows = []
        for p in table:
            if (
                not isinstance(p, dict)
                or set(p)
                != {
                    "panelId",
                    "materialId",
                    "renderVertexCount",
                    "cageVertexCount",
                    "cageTriangleCount",
                }
                or not all(
                    type(p[k]) is int
                    for k in ("renderVertexCount", "cageVertexCount", "cageTriangleCount")
                )
                or not all(isinstance(p[k], str) for k in ("panelId", "materialId"))
            ):
                raise ValueError("binding_v2_invalid_panel_metadata")
            panel_rows.append(
                PanelV2(
                    p["panelId"],
                    p["materialId"],
                    p["renderVertexCount"],
                    p["cageVertexCount"],
                    p["cageTriangleCount"],
                )
            )
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("binding_v2_invalid_panel_metadata") from exc
    records = tuple(
        BindingRecordV2(ti, pi, (a, b, c), (x, y, z), mask)
        for ti, pi, a, b, c, x, y, z, mask in RECORD.iter_unpack(data[header + meta :])
    )
    result = BindingV2(records, tuple(panel_rows), *(h.hex() for h in hashes))
    _validate(result)
    if result.simulation_triangle_count != triangles:
        raise ValueError("binding_v2_triangle_count_mismatch")
    return result


def reconstruct_v2(cage: MeshSet, binding: BindingV2) -> list[Vec3]:
    """Reconstruct using only the passed (possibly moved) cage and decoded binding.

    Rest geometry hashes are checked by check_rest, not here: motion intentionally
    changes positions. Topology, ordered semantic membership and weights stay fixed.
    """
    _validate(binding)
    if cage.vertex_count > MAX_VERTICES or cage.triangle_count > MAX_TRIANGLES:
        raise ValueError("binding_v2_mesh_budget")
    if topology_hash(cage) != binding.simulation_topology_hash:
        raise ValueError("binding_v2_cage_topology_mismatch")
    if len(cage.meshes) != len(binding.panels):
        raise ValueError("binding_v2_panel_count_mismatch")
    triangles: list[tuple[Vec3, Vec3, Vec3]] = []
    for mesh, panel in zip(cage.meshes, binding.panels, strict=True):
        if (mesh.panel_id, mesh.material_id, len(mesh.vertices), len(mesh.triangles)) != (
            panel.panel_id,
            panel.material_id,
            panel.cage_vertex_count,
            panel.cage_triangle_count,
        ):
            raise ValueError("binding_v2_cage_semantics_mismatch")
        triangles.extend(_points(mesh, tri) for tri in mesh.triangles)
    output = []
    for record in binding.records:
        points = triangles[record.simulation_triangle_index]
        base = _blend(points, record.weights)
        basis = _frame(points)
        delta = _blend(basis, record.local_residual)
        output.append((base[0] + delta[0], base[1] + delta[1], base[2] + delta[2]))
    return output
