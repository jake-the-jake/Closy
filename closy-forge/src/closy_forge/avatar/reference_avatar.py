from __future__ import annotations

from math import cos, pi, sin

from closy_forge.contracts.avatar import REQUIRED_BODY_REGIONS, REQUIRED_LANDMARKS
from closy_forge.contracts.common import COORDINATE_CONVENTION
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.package_io.hashing import geometry_content_hash, topology_hash


def reference_landmarks() -> dict[str, list[float]]:
    return {
        "head": [0.0, 1.70, 0.0],
        "neck": [0.0, 1.50, 0.0],
        "chest": [0.0, 1.29, 0.02],
        "waist": [0.0, 1.02, 0.0],
        "hips": [0.0, 0.88, 0.0],
        "shoulderL": [-0.36, 1.42, 0.0],
        "elbowL": [-0.68, 1.18, 0.0],
        "wristL": [-0.88, 0.94, 0.0],
        "shoulderR": [0.36, 1.42, 0.0],
        "elbowR": [0.68, 1.18, 0.0],
        "wristR": [0.88, 0.94, 0.0],
        "thighL": [-0.16, 0.78, 0.0],
        "kneeL": [-0.16, 0.45, 0.0],
        "ankleL": [-0.15, 0.08, 0.0],
        "footL": [-0.15, 0.02, 0.12],
        "thighR": [0.16, 0.78, 0.0],
        "kneeR": [0.16, 0.45, 0.0],
        "ankleR": [0.15, 0.08, 0.0],
        "footR": [0.15, 0.02, 0.12],
    }


def body_regions() -> dict[str, object]:
    regions = []
    for region_id in REQUIRED_BODY_REGIONS:
        regions.append(
            {
                "id": region_id,
                "schemaVersion": 1,
                "stable": True,
                "provenance": "procedural_fixture",
            }
        )
    return {"schemaVersion": 1, "avatarContractId": "avatar.closy_reference_v1", "regions": regions}


def avatar_contract(avatar_mesh: MeshSet, collision_mesh: MeshSet) -> dict[str, object]:
    landmarks = reference_landmarks()
    return {
        "schemaVersion": 1,
        "avatarContractId": "avatar.closy_reference_v1",
        "version": "1.0.0",
        "displayName": "Closy Reference Mannequin Fixture",
        "coordinateConvention": COORDINATE_CONVENTION,
        "heightMeters": 1.78,
        "pose": "T-pose",
        "root": [0.0, 0.0, 0.0],
        "grounded": True,
        "centeredXZ": True,
        "landmarks": landmarks,
        "requiredLandmarks": REQUIRED_LANDMARKS,
        "measurements": {
            "chestCircumference": 0.92,
            "waistCircumference": 0.78,
            "hipCircumference": 0.92,
            "shoulderWidth": 0.72,
            "neckCircumference": 0.36,
            "upperArmCircumference": 0.28,
        },
        "collisionPrimitives": [
            {
                "id": "collision.torso",
                "type": "ellipsoid",
                "center": [0.0, 1.15, 0.0],
                "radii": [0.25, 0.34, 0.13],
                "bodyRegion": "region.torso",
            },
            {
                "id": "collision.pelvis",
                "type": "ellipsoid",
                "center": [0.0, 0.86, 0.0],
                "radii": [0.25, 0.12, 0.12],
                "bodyRegion": "region.pelvis",
            },
            {
                "id": "collision.upper_arm.left",
                "type": "capsule",
                "a": [-0.36, 1.39, 0.0],
                "b": [-0.68, 1.18, 0.0],
                "radius": 0.055,
                "bodyRegion": "region.upper_arm.left",
            },
            {
                "id": "collision.upper_arm.right",
                "type": "capsule",
                "a": [0.36, 1.39, 0.0],
                "b": [0.68, 1.18, 0.0],
                "radius": 0.055,
                "bodyRegion": "region.upper_arm.right",
            },
            {
                "id": "collision.neck_shoulders",
                "type": "ellipsoid",
                "center": [0.0, 1.43, 0.0],
                "radii": [0.38, 0.08, 0.12],
                "bodyRegion": "region.torso",
            },
            {
                "id": "collision.thigh.left",
                "type": "capsule",
                "a": [-0.16, 0.80, 0.0],
                "b": [-0.16, 0.45, 0.0],
                "radius": 0.09,
                "bodyRegion": "region.thigh.left",
            },
            {
                "id": "collision.thigh.right",
                "type": "capsule",
                "a": [0.16, 0.80, 0.0],
                "b": [0.16, 0.45, 0.0],
                "radius": 0.09,
                "bodyRegion": "region.thigh.right",
            },
            {
                "id": "collision.shin.left",
                "type": "capsule",
                "a": [-0.16, 0.45, 0.0],
                "b": [-0.15, 0.08, 0.0],
                "radius": 0.065,
                "bodyRegion": "region.shin.left",
            },
            {
                "id": "collision.shin.right",
                "type": "capsule",
                "a": [0.16, 0.45, 0.0],
                "b": [0.15, 0.08, 0.0],
                "radius": 0.065,
                "bodyRegion": "region.shin.right",
            },
        ],
        "capabilities": {
            "productionAvatar": False,
            "bodyScan": False,
            "anatomicalModel": False,
            "skeleton": False,
            "animation": False,
            "landmarks": True,
            "collisionPrimitives": True,
        },
        "meshTopologyHash": topology_hash(avatar_mesh),
        "meshContentHash": geometry_content_hash(avatar_mesh),
        "collisionTopologyHash": topology_hash(collision_mesh),
        "collisionContentHash": geometry_content_hash(collision_mesh),
        "provenance": {
            "sourceKind": "procedural_fixture",
            "containsPersonalBodyData": False,
            "containsUserImagery": False,
            "note": (
                "Synthetic non-identifying fixture; not a production avatar, body scan or "
                "anatomical model."
            ),
        },
    }


def build_reference_avatar_mesh() -> MeshSet:
    meshes = [
        _ellipsoid("avatar.torso", "region.torso", (0.0, 1.18, 0.0), (0.24, 0.34, 0.12)),
        _ellipsoid("avatar.pelvis", "region.pelvis", (0.0, 0.86, 0.0), (0.25, 0.12, 0.11)),
        _ellipsoid("avatar.head", "region.head", (0.0, 1.63, 0.0), (0.10, 0.13, 0.095)),
        _ellipsoid("avatar.neck", "region.torso", (0.0, 1.48, 0.0), (0.055, 0.08, 0.05)),
        _ellipsoid(
            "avatar.arm.left", "region.upper_arm.left", (-0.53, 1.28, 0.0), (0.18, 0.05, 0.05)
        ),
        _ellipsoid(
            "avatar.arm.right", "region.upper_arm.right", (0.53, 1.28, 0.0), (0.18, 0.05, 0.05)
        ),
        _ellipsoid("avatar.leg.left", "region.thigh.left", (-0.14, 0.42, 0.0), (0.07, 0.42, 0.065)),
        _ellipsoid(
            "avatar.leg.right", "region.thigh.right", (0.14, 0.42, 0.0), (0.07, 0.42, 0.065)
        ),
    ]
    return MeshSet(meshes)


def build_collision_mesh() -> MeshSet:
    return MeshSet(
        [
            _ellipsoid(
                "collision.torso",
                "collision.torso",
                (0.0, 1.15, 0.0),
                (0.27, 0.36, 0.15),
                rings=6,
                segments=10,
            ),
            _ellipsoid(
                "collision.pelvis",
                "collision.pelvis",
                (0.0, 0.86, 0.0),
                (0.27, 0.14, 0.14),
                rings=6,
                segments=10,
            ),
            _ellipsoid(
                "collision.shoulders",
                "collision.neck_shoulders",
                (0.0, 1.43, 0.0),
                (0.39, 0.08, 0.13),
                rings=5,
                segments=10,
            ),
        ]
    )


def _ellipsoid(
    name: str,
    panel_id: str,
    center: tuple[float, float, float],
    radii: tuple[float, float, float],
    rings: int = 8,
    segments: int = 12,
) -> Mesh:
    vertices = []
    uvs = []
    for r in range(rings + 1):
        theta = pi * r / rings
        for s in range(segments):
            phi = 2.0 * pi * s / segments
            vertices.append(
                (
                    center[0] + radii[0] * sin(theta) * cos(phi),
                    center[1] + radii[1] * cos(theta),
                    center[2] + radii[2] * sin(theta) * sin(phi),
                )
            )
            uvs.append((s / segments, r / rings))
    triangles = []
    for r in range(rings):
        for s in range(segments):
            a = r * segments + s
            b = r * segments + (s + 1) % segments
            c = (r + 1) * segments + s
            d = (r + 1) * segments + (s + 1) % segments
            triangles.append((a, c, b))
            triangles.append((b, c, d))
    return Mesh(name=name, panel_id=panel_id, vertices=vertices, panel_uvs=uvs, triangles=triangles)
