from __future__ import annotations

import math

from closy_forge.geometry.mesh_model import Mesh, MeshSet

CANDIDATE_DEFORMATION_VERSION = "closy.c3.candidate_sim_deformation.v4"


def deform_simulation_representation(meshset: MeshSet, state: dict[str, object]) -> MeshSet:
    output: list[Mesh] = []
    for source in meshset.meshes:
        transformed = []
        for source_point in source.vertices:
            px = source_point[0] * _number(state, "materialStretchU", 1.0)
            py = source_point[1]
            pz = source_point[2]
            angle = math.radians(_number(state, "torsoBendDegrees", 0.0))
            relative_y = py - 1.08
            py = 1.08 + relative_y * math.cos(angle) - pz * math.sin(angle)
            pz = relative_y * math.sin(angle) + pz * math.cos(angle)
            yaw = math.radians(_number(state, "torsoTwistDegrees", 0.0))
            rotated_x = px * math.cos(yaw) - pz * math.sin(yaw)
            pz = px * math.sin(yaw) + pz * math.cos(yaw)
            px = rotated_x
            lift = 0.0
            shoulder_x = 0.0
            if source.panel_id.endswith("sleeve.left"):
                lift = math.radians(_number(state, "leftArmLiftDegrees", 0.0))
                shoulder_x = -0.48
            if source.panel_id.endswith("sleeve.right"):
                lift = -math.radians(_number(state, "rightArmLiftDegrees", 0.0))
                shoulder_x = 0.48
            if lift != 0.0:
                local_x = px - shoulder_x
                local_y = py - 1.31
                px = shoulder_x + local_x * math.cos(lift) - local_y * math.sin(lift)
                py = 1.31 + local_x * math.sin(lift) + local_y * math.cos(lift)
            transformed.append((px, py, pz))
        output.append(
            Mesh(
                source.name,
                source.panel_id,
                transformed,
                list(source.panel_uvs),
                list(source.triangles),
                source.material_id,
            )
        )
    return MeshSet(output)


def _number(state: dict[str, object], key: str, default: float) -> float:
    value = state.get(key, default)
    if not isinstance(value, int | float):
        raise ValueError(f"h4_candidate_state_value_invalid:{key}")
    return float(value)
