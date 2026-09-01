from __future__ import annotations

from collections.abc import Mapping
from math import cos, isfinite, radians, sin
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

ORACLE_VERSION = "closy.c3.independent_material_coordinate_oracle.v5"


def generate_oracle_target(
    simulation_source: MeshSet,
    dense_source: MeshSet,
    pose: Mapping[str, object],
) -> dict[str, Any]:
    """Generate targets directly from material coordinates; no binding path is imported."""
    simulation = _deform_directly(simulation_source, pose)
    dense = _deform_directly(dense_source, pose)
    target: dict[str, Any] = {
        "schemaVersion": 1,
        "oracleVersion": ORACLE_VERSION,
        "pose": dict(pose),
        "simulationVertices": _serialise_vertices(simulation),
        "denseVertices": _serialise_vertices(dense),
        "readsCandidateBindingWeights": False,
        "callsCandidateReconstruction": False,
        "targetDigest": "",
    }
    target["targetDigest"] = _target_digest(target)
    return target


def validate_oracle_target(target: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if target.get("oracleVersion") != ORACLE_VERSION:
        issues.append("oracle_version_mismatch")
    if target.get("readsCandidateBindingWeights") is not False:
        issues.append("oracle_reads_candidate_binding")
    if target.get("callsCandidateReconstruction") is not False:
        issues.append("oracle_calls_candidate_reconstruction")
    if target.get("targetDigest") != _target_digest(dict(target)):
        issues.append("oracle_target_digest_mismatch")
    return issues


def _deform_directly(meshset: MeshSet, pose: Mapping[str, object]) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                mesh.name,
                mesh.panel_id,
                [_oracle_point(point, mesh.panel_id, pose) for point in mesh.vertices],
                list(mesh.panel_uvs),
                list(mesh.triangles),
                mesh.material_id,
            )
            for mesh in meshset.meshes
        ]
    )


def _oracle_point(point: Vec3, panel_id: str, pose: Mapping[str, object]) -> Vec3:
    # This implementation is deliberately independent from candidate.py. It shares only the
    # frozen synthetic pose semantics; it is not physical or real-world ground truth.
    x, y, z = point
    x = x * _number(pose, "materialStretchU", 1.0)
    bend = radians(_number(pose, "torsoBendDegrees", 0.0))
    relative_y = y - 1.08
    y, z = (
        1.08 + cos(bend) * relative_y - sin(bend) * z,
        sin(bend) * relative_y + cos(bend) * z,
    )
    twist = radians(_number(pose, "torsoTwistDegrees", 0.0))
    x, z = cos(twist) * x - sin(twist) * z, sin(twist) * x + cos(twist) * z
    angle = 0.0
    pivot_x = 0.0
    if panel_id == "panel.sleeve.left":
        angle = radians(_number(pose, "leftArmLiftDegrees", 0.0))
        pivot_x = -0.48
    elif panel_id == "panel.sleeve.right":
        angle = -radians(_number(pose, "rightArmLiftDegrees", 0.0))
        pivot_x = 0.48
    if angle:
        px, py = x - pivot_x, y - 1.31
        x, y = (
            pivot_x + cos(angle) * px - sin(angle) * py,
            1.31 + sin(angle) * px + cos(angle) * py,
        )
    return (x, y, z)


def _serialise_vertices(meshset: MeshSet) -> list[list[list[float]]]:
    return [
        [[float(x), float(y), float(z)] for x, y, z in mesh.vertices] for mesh in meshset.meshes
    ]


def _number(pose: Mapping[str, object], key: str, default: float) -> float:
    value = pose.get(key, default)
    if not isinstance(value, int | float) or isinstance(value, bool) or not isfinite(value):
        raise ValueError(f"c3_v5_oracle_pose_value_invalid:{key}")
    return float(value)


def _target_digest(target: dict[str, Any]) -> str:
    payload = dict(target)
    payload["targetDigest"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
