from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]
Tri = tuple[int, int, int]


@dataclass(frozen=True)
class Mesh:
    name: str
    panel_id: str
    vertices: list[Vec3]
    panel_uvs: list[Vec2]
    triangles: list[Tri]
    material_id: str = "material.cotton_jersey_reference_v1"


@dataclass(frozen=True)
class MeshSet:
    meshes: list[Mesh]

    @property
    def vertex_count(self) -> int:
        return sum(len(mesh.vertices) for mesh in self.meshes)

    @property
    def triangle_count(self) -> int:
        return sum(len(mesh.triangles) for mesh in self.meshes)


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def scale(a: Vec3, k: float) -> Vec3:
    return (a[0] * k, a[1] * k, a[2] * k)


def normalize(v: Vec3) -> Vec3:
    length = sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length <= 1e-12:
        return (0.0, 1.0, 0.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def triangle_normal(vertices: list[Vec3], tri: Tri) -> Vec3:
    a, b, c = vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]
    return normalize(cross(sub(b, a), sub(c, a)))


def mesh_bounds(meshset: MeshSet) -> dict[str, list[float]]:
    verts = [v for mesh in meshset.meshes for v in mesh.vertices]
    if not verts:
        return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0], "size": [0.0, 0.0, 0.0]}
    mins = [min(v[i] for v in verts) for i in range(3)]
    maxs = [max(v[i] for v in verts) for i in range(3)]
    return {
        "min": mins,
        "max": maxs,
        "size": [maxs[i] - mins[i] for i in range(3)],
    }


def finite_mesh(meshset: MeshSet) -> bool:
    for mesh in meshset.meshes:
        for vertex in mesh.vertices:
            if not all(abs(n) < 1e6 and n == n for n in vertex):
                return False
        for uv in mesh.panel_uvs:
            if not all(abs(n) < 1e6 and n == n for n in uv):
                return False
        for tri in mesh.triangles:
            if len(set(tri)) != 3 or any(i < 0 or i >= len(mesh.vertices) for i in tri):
                return False
    return True
