from __future__ import annotations

from math import pi, sin

from closy_forge.geometry.mesh_model import Mesh, MeshSet

from .states import MotionState


def independently_deform_dense_reference(meshset: MeshSet, state: MotionState) -> MeshSet:
    """Dense reference implementation kept separate from low-resolution solver deformation."""

    ordinates = [point[1] for part in meshset.meshes for point in part.vertices]
    floor = min(ordinates)
    extent = max(max(ordinates) - floor, 1e-9)
    output: list[Mesh] = []
    for part in meshset.meshes:
        moved = []
        for point in part.vertices:
            horizontal, vertical, depth = point
            normalized_height = (vertical - floor) / extent
            side_factor = -1.0 if horizontal < 0.0 else 1.0
            moved_horizontal = horizontal + state.lateral * normalized_height**2
            moved_horizontal += state.stride * side_factor * (1.0 - normalized_height)
            moved_vertical = vertical + state.vertical * (0.35 + normalized_height * 0.65)
            moved_depth = depth + state.depth * sin(pi * normalized_height)
            moved_depth += state.twist * horizontal * (0.25 + normalized_height * 0.75)
            moved.append((moved_horizontal, moved_vertical, moved_depth))
        output.append(
            Mesh(
                name=part.name,
                panel_id=part.panel_id,
                vertices=moved,
                panel_uvs=part.panel_uvs,
                triangles=part.triangles,
                material_id=part.material_id,
            )
        )
    return MeshSet(output)
