from __future__ import annotations

import math
from collections.abc import Mapping

from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3

CANDIDATE_VERSION = "closy.c3.unit_f_candidate_pose_field.v5"


def deform_candidate_simulation(meshset: MeshSet, pose: Mapping[str, object]) -> MeshSet:
    """Apply the frozen candidate pose field without changing binding or topology."""
    return MeshSet(
        [
            Mesh(
                mesh.name,
                mesh.panel_id,
                [_candidate_point(point, mesh.panel_id, pose) for point in mesh.vertices],
                list(mesh.panel_uvs),
                list(mesh.triangles),
                mesh.material_id,
            )
            for mesh in meshset.meshes
        ]
    )


def _candidate_point(point: Vec3, panel_id: str, pose: Mapping[str, object]) -> Vec3:
    x, y, z = point
    x *= _number(pose, "materialStretchU", 1.0)

    bend = math.radians(_number(pose, "torsoBendDegrees", 0.0))
    local_y = y - 1.08
    y = 1.08 + local_y * math.cos(bend) - z * math.sin(bend)
    z = local_y * math.sin(bend) + z * math.cos(bend)

    twist = math.radians(_number(pose, "torsoTwistDegrees", 0.0))
    x, z = x * math.cos(twist) - z * math.sin(twist), x * math.sin(twist) + z * math.cos(twist)

    lift = 0.0
    shoulder_x = 0.0
    if panel_id.endswith("sleeve.left"):
        lift = math.radians(_number(pose, "leftArmLiftDegrees", 0.0))
        shoulder_x = -0.48
    elif panel_id.endswith("sleeve.right"):
        lift = -math.radians(_number(pose, "rightArmLiftDegrees", 0.0))
        shoulder_x = 0.48
    if lift:
        local_x = x - shoulder_x
        local_y = y - 1.31
        x = shoulder_x + local_x * math.cos(lift) - local_y * math.sin(lift)
        y = 1.31 + local_x * math.sin(lift) + local_y * math.cos(lift)
    return (x, y, z)


def _number(pose: Mapping[str, object], key: str, default: float) -> float:
    value = pose.get(key, default)
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"c3_v5_candidate_pose_value_invalid:{key}")
    return float(value)
