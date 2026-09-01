from __future__ import annotations

from math import cos, radians, sin

from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3

ORACLE_VERSION = "closy.c3.independent_material_shell_oracle.v4"


def deform_dense_shell_directly(meshset: MeshSet, state: dict[str, object]) -> MeshSet:
    """Deform dense material/panel coordinates without reading binding records."""
    meshes = []
    for mesh in meshset.meshes:
        vertices = [_oracle_point(vertex, mesh.panel_id, state) for vertex in mesh.vertices]
        meshes.append(
            Mesh(
                mesh.name,
                mesh.panel_id,
                vertices,
                list(mesh.panel_uvs),
                list(mesh.triangles),
                mesh.material_id,
            )
        )
    return MeshSet(meshes)


def _oracle_point(point: Vec3, panel_id: str, state: dict[str, object]) -> Vec3:
    x, y, z = point
    x *= _number(state, "materialStretchU", 1.0)
    bend = radians(_number(state, "torsoBendDegrees", 0.0))
    y0 = y - 1.08
    y, z = 1.08 + cos(bend) * y0 - sin(bend) * z, sin(bend) * y0 + cos(bend) * z
    twist = radians(_number(state, "torsoTwistDegrees", 0.0))
    x, z = cos(twist) * x - sin(twist) * z, sin(twist) * x + cos(twist) * z
    arm = 0.0
    pivot_x = 0.0
    if panel_id == "panel.sleeve.left":
        arm = radians(_number(state, "leftArmLiftDegrees", 0.0))
        pivot_x = -0.48
    elif panel_id == "panel.sleeve.right":
        arm = -radians(_number(state, "rightArmLiftDegrees", 0.0))
        pivot_x = 0.48
    if arm:
        px, py = x - pivot_x, y - 1.31
        x, y = pivot_x + cos(arm) * px - sin(arm) * py, 1.31 + sin(arm) * px + cos(arm) * py
    return (x, y, z)


def _number(state: dict[str, object], key: str, default: float) -> float:
    value = state.get(key, default)
    if not isinstance(value, int | float):
        raise ValueError(f"h4_oracle_state_value_invalid:{key}")
    return float(value)
