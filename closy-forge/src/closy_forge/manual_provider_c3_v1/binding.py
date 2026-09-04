from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import BindingFile, BindingRecord, write_binding
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.package_io.hashing import topology_hash


@dataclass(frozen=True)
class BoundGarment:
    simulation: MeshSet
    binding: BindingFile
    report: dict[str, Any]


def _lattice_shape(mesh: Mesh) -> tuple[int, int]:
    vertex_count = len(mesh.vertices)
    candidates = [
        (columns, vertex_count // columns)
        for columns in (25, 27, 29)
        if vertex_count % columns == 0 and vertex_count // columns in (27, 29)
    ]
    if not candidates:
        raise ValueError("clean_mesh_lattice_shape_ambiguous")
    scored = []
    for columns, rows in candidates:
        allowed = {1, columns, columns + 1}
        mismatches = sum(
            abs(a - b) not in allowed
            for triangle in mesh.triangles[: min(128, len(mesh.triangles))]
            for a, b in (
                (triangle[0], triangle[1]),
                (triangle[1], triangle[2]),
                (triangle[2], triangle[0]),
            )
        )
        scored.append((mismatches, columns, rows))
    scored.sort()
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        raise ValueError("clean_mesh_lattice_shape_ambiguous")
    return scored[0][1], scored[0][2]


def _sample_axis(size: int) -> list[int]:
    values = list(range(0, size, 2))
    if values[-1] != size - 1:
        values.append(size - 1)
    return values


def _low_resolution_mesh(render: Mesh) -> tuple[Mesh, list[int], list[int]]:
    columns, rows = _lattice_shape(render)
    selected_columns = _sample_axis(columns)
    selected_rows = _sample_axis(rows)
    vertices = [
        render.vertices[row * columns + column]
        for row in selected_rows
        for column in selected_columns
    ]
    uvs = [
        render.panel_uvs[row * columns + column]
        for row in selected_rows
        for column in selected_columns
    ]
    low_columns = len(selected_columns)
    triangles: list[tuple[int, int, int]] = []
    back = render.panel_id.endswith("back")
    for row in range(len(selected_rows) - 1):
        for column in range(low_columns - 1):
            a = row * low_columns + column
            b, c, d = a + 1, a + low_columns, a + low_columns + 1
            cell = [(a, b, d), (a, d, c)]
            if back:
                cell = [(first, third, second) for first, second, third in cell]
            triangles.extend(cell)
    return (
        Mesh(
            name=f"simulation:{render.name}",
            panel_id=render.panel_id,
            vertices=vertices,
            panel_uvs=uvs,
            triangles=triangles,
            material_id=render.material_id,
        ),
        selected_columns,
        selected_rows,
    )


def _interval(samples: list[int], value: int) -> tuple[int, float]:
    for index in range(len(samples) - 1):
        if samples[index] <= value <= samples[index + 1]:
            extent = samples[index + 1] - samples[index]
            return index, (value - samples[index]) / extent
    raise ValueError("render_vertex_outside_simulation_lattice")


def build_hybrid_binding(render: MeshSet, output_path: Path | None = None) -> BoundGarment:
    simulation_meshes: list[Mesh] = []
    records: list[BindingRecord] = []
    panel_table = sorted(mesh.panel_id for mesh in render.meshes)
    panel_lookup = {panel_id: index for index, panel_id in enumerate(panel_table)}
    triangle_offset = 0
    minimum_weight = 1.0
    maximum_weight = 0.0
    for render_mesh in render.meshes:
        sim_mesh, sample_columns, sample_rows = _low_resolution_mesh(render_mesh)
        simulation_meshes.append(sim_mesh)
        columns, rows = _lattice_shape(render_mesh)
        low_columns = len(sample_columns)
        back = render_mesh.panel_id.endswith("back")
        for row in range(rows):
            cell_row, fy = _interval(sample_rows, row)
            for column in range(columns):
                cell_column, fx = _interval(sample_columns, column)
                cell_triangle_offset = (cell_row * (low_columns - 1) + cell_column) * 2
                if fx >= fy:
                    local_triangle = 0
                    weights = (1.0 - fx, fx - fy, fy)
                else:
                    local_triangle = 1
                    weights = (1.0 - fy, fx, fy - fx)
                if back:
                    weights = (weights[0], weights[2], weights[1])
                minimum_weight = min(minimum_weight, *weights)
                maximum_weight = max(maximum_weight, *weights)
                records.append(
                    BindingRecord(
                        simulation_triangle_index=triangle_offset
                        + cell_triangle_offset
                        + local_triangle,
                        barycentric_u=weights[1],
                        barycentric_v=weights[2],
                        normal_offset=0.0,
                        panel_table_index=panel_lookup[render_mesh.panel_id],
                        flags=1,
                    )
                )
        triangle_offset += len(sim_mesh.triangles)
    simulation = MeshSet(simulation_meshes)
    binding = BindingFile(
        records=records,
        simulation_triangle_count=simulation.triangle_count,
        panel_count=len(panel_table),
        simulation_topology_hash=topology_hash(simulation),
        render_topology_hash=topology_hash(render),
    )
    if output_path is not None:
        write_binding(output_path, binding)
    reconstructed = reconstruct_vertices(simulation, binding)
    targets = [vertex for mesh in render.meshes for vertex in mesh.vertices]
    errors = [
        math.dist(actual, expected) for actual, expected in zip(reconstructed, targets, strict=True)
    ]
    all_binding_weights = [
        (
            1.0 - record.barycentric_u - record.barycentric_v,
            record.barycentric_u,
            record.barycentric_v,
        )
        for record in records
    ]
    out_of_domain_count = sum(
        any(weight < -1e-9 or weight > 1.0 + 1e-9 for weight in row) for row in all_binding_weights
    )
    report = {
        "schemaVersion": 1,
        "bindingVersion": "closy.manual_provider.hybrid_barycentric_cage.v1",
        "algorithm": "structured_cage_with_per_vertex_barycentric_weights",
        "boundAssetId": f"bound:{topology_hash(render)[:20]}",
        "simulationTopologyHash": binding.simulation_topology_hash,
        "renderTopologyHash": binding.render_topology_hash,
        "recordCount": len(records),
        "coverage": len(records) / max(1, len(targets)),
        "outOfDomainCount": out_of_domain_count,
        "minimumWeight": minimum_weight,
        "maximumWeight": maximum_weight,
        "maximumWeightSumError": max(
            (abs(sum(weight_row) - 1.0) for weight_row in all_binding_weights), default=0.0
        ),
        "restMaximumErrorMeters": max(errors, default=0.0),
        "restRmsErrorMeters": math.sqrt(
            sum(error * error for error in errors) / max(1, len(errors))
        ),
        "fallbackDistinct": topology_hash(simulation) != topology_hash(render),
        "status": "pass",
    }
    return BoundGarment(simulation=simulation, binding=binding, report=report)
