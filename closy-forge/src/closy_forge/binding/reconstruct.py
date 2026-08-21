from __future__ import annotations

from math import sqrt

from closy_forge.binding.binary_format import BindingFile
from closy_forge.geometry.mesh_model import MeshSet, Vec3


def flattened_triangles(meshset: MeshSet) -> list[tuple[int, tuple[int, int, int]]]:
    out = []
    for mesh_i, mesh in enumerate(meshset.meshes):
        for tri in mesh.triangles:
            out.append((mesh_i, tri))
    return out


def reconstruct_vertices(sim: MeshSet, binding: BindingFile) -> list[Vec3]:
    tris = flattened_triangles(sim)
    result: list[Vec3] = []
    for record in binding.records:
        if record.simulation_triangle_index >= len(tris):
            raise ValueError("binding_triangle_out_of_range")
        mesh_i, tri = tris[record.simulation_triangle_index]
        mesh = sim.meshes[mesh_i]
        a, b, c = mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]]
        u, v = record.barycentric_u, record.barycentric_v
        w = 1.0 - u - v
        result.append(
            (
                a[0] * w + b[0] * u + c[0] * v,
                a[1] * w + b[1] * u + c[1] * v,
                a[2] * w + b[2] * u + c[2] * v,
            )
        )
    return result


def reconstruction_error(render: MeshSet, reconstructed: list[Vec3]) -> tuple[float, float]:
    target = [vertex for mesh in render.meshes for vertex in mesh.vertices]
    if len(target) != len(reconstructed):
        raise ValueError("binding_record_count_mismatch")
    squared_sum = 0.0
    max_err = 0.0
    for a, b in zip(target, reconstructed, strict=True):
        dist = sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))
        max_err = max(max_err, dist)
        squared_sum += dist * dist
    return max_err, sqrt(squared_sum / max(1, len(target)))


def perturb_simulation_vertices(sim: MeshSet) -> MeshSet:
    meshes = []
    for mesh in sim.meshes:
        verts = [
            (x, y + (0.006 if i % 7 == 0 else 0.0), z) for i, (x, y, z) in enumerate(mesh.vertices)
        ]
        meshes.append(
            type(mesh)(
                mesh.name, mesh.panel_id, verts, mesh.panel_uvs, mesh.triangles, mesh.material_id
            )
        )
    return MeshSet(meshes)
