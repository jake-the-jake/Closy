from __future__ import annotations

from math import isfinite, sqrt
from typing import Any

from .mesh_model import (
    Mesh,
    MeshSet,
    Vec2,
    Vec3,
    add,
    cross,
    normalize,
    scale,
    sub,
    triangle_normal,
)

Vec4 = tuple[float, float, float, float]


def vertex_normals(mesh: Mesh) -> list[Vec3]:
    normals: list[Vec3] = [(0.0, 0.0, 0.0) for _ in mesh.vertices]
    for tri in mesh.triangles:
        normal = triangle_normal(mesh.vertices, tri)
        for index in tri:
            normals[index] = add(normals[index], normal)
    return [_quantize_vec3(normalize(normal)) for normal in normals]


def vertex_tangents(mesh: Mesh, normals: list[Vec3] | None = None) -> list[Vec4]:
    vertex_normals_list = normals if normals is not None else vertex_normals(mesh)
    accumulated_tangents: list[Vec3] = [(0.0, 0.0, 0.0) for _ in mesh.vertices]
    accumulated_bitangents: list[Vec3] = [(0.0, 0.0, 0.0) for _ in mesh.vertices]
    for tri in mesh.triangles:
        tangent, bitangent = triangle_tangent_frame(mesh.vertices, mesh.panel_uvs, tri)
        for index in tri:
            accumulated_tangents[index] = add(accumulated_tangents[index], tangent)
            accumulated_bitangents[index] = add(accumulated_bitangents[index], bitangent)
    tangents: list[Vec4] = []
    for normal, tangent, bitangent in zip(
        vertex_normals_list, accumulated_tangents, accumulated_bitangents, strict=True
    ):
        tangents.append(_orthonormal_tangent(normal, tangent, bitangent))
    return tangents


def expanded_triangle_frames(mesh: Mesh) -> tuple[list[Vec3], list[Vec4]]:
    normals: list[Vec3] = []
    tangents: list[Vec4] = []
    for tri in mesh.triangles:
        normal = triangle_normal(mesh.vertices, tri)
        tangent, bitangent = triangle_tangent_frame(mesh.vertices, mesh.panel_uvs, tri)
        tangent4 = _orthonormal_tangent(normal, tangent, bitangent)
        normal = _quantize_vec3(normal)
        tangent4 = _quantize_vec4(tangent4)
        normals.extend([normal, normal, normal])
        tangents.extend([tangent4, tangent4, tangent4])
    return normals, tangents


def triangle_tangent_frame(
    vertices: list[Vec3], uvs: list[Vec2], tri: tuple[int, int, int]
) -> tuple[Vec3, Vec3]:
    i0, i1, i2 = tri
    p0, p1, p2 = vertices[i0], vertices[i1], vertices[i2]
    uv0 = uvs[i0] if i0 < len(uvs) else (0.0, 0.0)
    uv1 = uvs[i1] if i1 < len(uvs) else (1.0, 0.0)
    uv2 = uvs[i2] if i2 < len(uvs) else (0.0, 1.0)
    edge1 = sub(p1, p0)
    edge2 = sub(p2, p0)
    duv1 = (uv1[0] - uv0[0], uv1[1] - uv0[1])
    duv2 = (uv2[0] - uv0[0], uv2[1] - uv0[1])
    denom = (duv1[0] * duv2[1]) - (duv2[0] * duv1[1])
    if abs(denom) <= 1e-12:
        normal = triangle_normal(vertices, tri)
        tangent = _fallback_tangent(normal)
        return tangent, _quantize_vec3(normalize(cross(normal, tangent)))
    inv = 1.0 / denom
    tangent = normalize(
        (
            ((edge1[0] * duv2[1]) - (edge2[0] * duv1[1])) * inv,
            ((edge1[1] * duv2[1]) - (edge2[1] * duv1[1])) * inv,
            ((edge1[2] * duv2[1]) - (edge2[2] * duv1[1])) * inv,
        )
    )
    bitangent = normalize(
        (
            ((edge2[0] * duv1[0]) - (edge1[0] * duv2[0])) * inv,
            ((edge2[1] * duv1[0]) - (edge1[1] * duv2[0])) * inv,
            ((edge2[2] * duv1[0]) - (edge1[2] * duv2[0])) * inv,
        )
    )
    return _quantize_vec3(tangent), _quantize_vec3(bitangent)


def meshset_frame_metrics(meshset: MeshSet) -> dict[str, Any]:
    normal_count = 0
    tangent_count = 0
    finite_normal_count = 0
    finite_tangent_count = 0
    unit_normal_count = 0
    unit_tangent_count = 0
    orthogonal_count = 0
    max_normal_length_error = 0.0
    max_tangent_length_error = 0.0
    max_normal_tangent_dot = 0.0
    handedness_values: set[float] = set()
    for mesh in meshset.meshes:
        normals = vertex_normals(mesh)
        tangents = vertex_tangents(mesh, normals)
        for normal, tangent in zip(normals, tangents, strict=True):
            normal_count += 1
            tangent_count += 1
            normal_length = _length3(normal)
            tangent_length = _length3((tangent[0], tangent[1], tangent[2]))
            normal_error = abs(normal_length - 1.0)
            tangent_error = abs(tangent_length - 1.0)
            normal_tangent_dot = abs(_dot3(normal, (tangent[0], tangent[1], tangent[2])))
            max_normal_length_error = max(max_normal_length_error, normal_error)
            max_tangent_length_error = max(max_tangent_length_error, tangent_error)
            max_normal_tangent_dot = max(max_normal_tangent_dot, normal_tangent_dot)
            if all(isfinite(component) for component in normal):
                finite_normal_count += 1
            if all(isfinite(component) for component in tangent):
                finite_tangent_count += 1
            if normal_error <= 1e-6:
                unit_normal_count += 1
            if tangent_error <= 1e-6:
                unit_tangent_count += 1
            if normal_tangent_dot <= 1e-6:
                orthogonal_count += 1
            handedness_values.add(round(float(tangent[3]), 6))
    return {
        "normalVectorCount": normal_count,
        "tangentVectorCount": tangent_count,
        "finiteNormalCount": finite_normal_count,
        "finiteTangentCount": finite_tangent_count,
        "unitNormalCount": unit_normal_count,
        "unitTangentCount": unit_tangent_count,
        "orthogonalNormalTangentCount": orthogonal_count,
        "maxNormalLengthError": round(max_normal_length_error, 9),
        "maxTangentLengthError": round(max_tangent_length_error, 9),
        "maxNormalTangentDot": round(max_normal_tangent_dot, 9),
        "tangentHandednessValues": sorted(handedness_values),
    }


def _orthonormal_tangent(normal: Vec3, tangent: Vec3, bitangent: Vec3) -> Vec4:
    projected = sub(tangent, scale(normal, _dot3(normal, tangent)))
    tangent3 = normalize(projected if _length3(projected) > 1e-12 else _fallback_tangent(normal))
    handedness = -1.0 if _dot3(cross(normal, tangent3), bitangent) < 0.0 else 1.0
    return _quantize_vec4((tangent3[0], tangent3[1], tangent3[2], handedness))


def _fallback_tangent(normal: Vec3) -> Vec3:
    reference = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 0.0, 1.0)
    return _quantize_vec3(normalize(cross(reference, normal)))


def _dot3(left: Vec3, right: Vec3) -> float:
    return sum(left[index] * right[index] for index in range(3))


def _length3(value: Vec3) -> float:
    return sqrt(_dot3(value, value))


def _quantize_vec3(value: Vec3) -> Vec3:
    return (round(float(value[0]), 9), round(float(value[1]), 9), round(float(value[2]), 9))


def _quantize_vec4(value: Vec4) -> Vec4:
    return (
        round(float(value[0]), 9),
        round(float(value[1]), 9),
        round(float(value[2]), 9),
        1.0 if value[3] >= 0.0 else -1.0,
    )
