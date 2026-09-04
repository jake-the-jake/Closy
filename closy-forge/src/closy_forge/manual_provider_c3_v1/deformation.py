from __future__ import annotations

import math

from closy_forge.geometry.mesh_model import Mesh, MeshSet

from .states import MotionState


def deform_simulation(meshset: MeshSet, state: MotionState) -> MeshSet:
    """Apply the production low-resolution solver-state approximation."""

    all_y = [vertex[1] for mesh in meshset.meshes for vertex in mesh.vertices]
    y_min, y_span = min(all_y), max(max(all_y) - min(all_y), 1e-9)
    meshes: list[Mesh] = []
    for mesh in meshset.meshes:
        vertices = []
        for x, y, z in mesh.vertices:
            t = (y - y_min) / y_span
            side = -1.0 if x < 0.0 else 1.0
            x_new = x + state.lateral * t * t + state.stride * side * (1.0 - t)
            y_new = y + state.vertical * (0.35 + 0.65 * t)
            z_new = z + state.depth * math.sin(math.pi * t)
            z_new += state.twist * x * (0.25 + 0.75 * t)
            vertices.append((x_new, y_new, z_new))
        meshes.append(
            Mesh(
                name=mesh.name,
                panel_id=mesh.panel_id,
                vertices=vertices,
                panel_uvs=mesh.panel_uvs,
                triangles=mesh.triangles,
                material_id=mesh.material_id,
            )
        )
    return MeshSet(meshes)
