from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from closy_forge.geometry.mesh_model import MeshSet, Vec2, Vec3, cross, normalize, sub

from .common import sha256_bytes

RENDERER_VERSION = "closy.independent_orthographic_ray_triangle.v1"
RGBA = tuple[int, int, int, int]
TextureSampler = Callable[[str, Vec2], RGBA]


@dataclass(frozen=True)
class RayHit:
    mesh_index: int
    triangle_index: int
    barycentric: tuple[float, float, float]
    world_position: Vec3
    panel_uv: Vec2
    normal: Vec3


@dataclass(frozen=True)
class RayRenderResult:
    width: int
    height: int
    rgba: bytes
    hits: tuple[RayHit | None, ...]
    rendered_pixel_count: int
    renderer_version: str
    camera: dict[str, object]
    image_sha256: str


def render_ray_triangles(
    meshset: MeshSet,
    *,
    width: int,
    height: int,
    view_role: str,
    background: RGBA = (232, 229, 222, 255),
    principal_offset: tuple[float, float] = (0.0, 0.0),
    texture_sampler: TextureSampler | None = None,
) -> RayRenderResult:
    """Render with per-pixel ray intersections, not the project's z-buffer rasterizer."""

    if width <= 0 or height <= 0:
        raise ValueError("ray_renderer_dimensions_invalid")
    vertices = [vertex for mesh in meshset.meshes for vertex in mesh.vertices]
    if not vertices:
        raise ValueError("ray_renderer_mesh_empty")
    center: Vec3 = (
        (min(v[0] for v in vertices) + max(v[0] for v in vertices)) / 2,
        (min(v[1] for v in vertices) + max(v[1] for v in vertices)) / 2,
        (min(v[2] for v in vertices) + max(v[2] for v in vertices)) / 2,
    )
    size = tuple(
        max(v[axis] for v in vertices) - min(v[axis] for v in vertices) for axis in range(3)
    )
    forward, horizontal = _view_basis(view_role)
    vertical: Vec3 = (0.0, 1.0, 0.0)
    depth_radius = max(size) + 1.0
    camera_origin = _add(center, _scale(forward, -depth_radius))
    horizontal_extent = max(0.1, _projected_extent(vertices, center, horizontal) * 1.15)
    vertical_extent = max(0.1, _projected_extent(vertices, center, vertical) * 1.15)
    triangles = [
        (mesh_index, triangle_index, mesh, triangle)
        for mesh_index, mesh in enumerate(meshset.meshes)
        for triangle_index, triangle in enumerate(mesh.triangles)
    ]
    pixels = bytearray(background * (width * height))
    hits: list[RayHit | None] = [None] * (width * height)
    light = normalize((-0.35, 0.7, -0.55))
    for y in range(height):
        normalized_y = (0.5 - (y + 0.5) / height) * 2.0 + principal_offset[1]
        for x in range(width):
            normalized_x = ((x + 0.5) / width - 0.5) * 2.0 + principal_offset[0]
            origin = _add(
                camera_origin,
                _add(
                    _scale(horizontal, normalized_x * horizontal_extent),
                    _scale(vertical, normalized_y * vertical_extent),
                ),
            )
            nearest_t = math.inf
            nearest: RayHit | None = None
            panel_id = ""
            for mesh_index, triangle_index, mesh, triangle in triangles:
                a, b, c = (mesh.vertices[index] for index in triangle)
                intersection = _intersect(origin, forward, a, b, c)
                if intersection is None or intersection[0] >= nearest_t:
                    continue
                t, u, v = intersection
                w = 1.0 - u - v
                uv_a, uv_b, uv_c = (mesh.panel_uvs[index] for index in triangle)
                nearest_t = t
                normal = normalize(cross(sub(b, a), sub(c, a)))
                nearest = RayHit(
                    mesh_index=mesh_index,
                    triangle_index=triangle_index,
                    barycentric=(w, u, v),
                    world_position=_add(origin, _scale(forward, t)),
                    panel_uv=(
                        w * uv_a[0] + u * uv_b[0] + v * uv_c[0],
                        w * uv_a[1] + u * uv_b[1] + v * uv_c[1],
                    ),
                    normal=normal,
                )
                panel_id = mesh.panel_id
            if nearest is not None:
                index = y * width + x
                hits[index] = nearest
                color = _shade(
                    panel_id,
                    nearest.panel_uv,
                    nearest.normal,
                    light,
                    texture_sampler=texture_sampler,
                )
                pixels[index * 4 : index * 4 + 4] = bytes(color)
    rgba = bytes(pixels)
    return RayRenderResult(
        width=width,
        height=height,
        rgba=rgba,
        hits=tuple(hits),
        rendered_pixel_count=sum(hit is not None for hit in hits),
        renderer_version=RENDERER_VERSION,
        camera={
            "implementation": "independent_orthographic_ray_origin_basis_v1",
            "viewRole": view_role,
            "forward": list(forward),
            "horizontal": list(horizontal),
            "vertical": list(vertical),
            "center": list(center),
            "horizontalExtent": horizontal_extent,
            "verticalExtent": vertical_extent,
            "principalOffset": list(principal_offset),
            "sharedRasterizerCodeWithCpuZbuffer": False,
        },
        image_sha256=sha256_bytes(rgba),
    )


def _intersect(
    origin: Vec3, direction: Vec3, a: Vec3, b: Vec3, c: Vec3
) -> tuple[float, float, float] | None:
    edge1 = sub(b, a)
    edge2 = sub(c, a)
    h = cross(direction, edge2)
    determinant = _dot(edge1, h)
    if abs(determinant) < 1e-10:
        return None
    inverse = 1.0 / determinant
    s = sub(origin, a)
    u = inverse * _dot(s, h)
    if u < 0.0 or u > 1.0:
        return None
    q = cross(s, edge1)
    v = inverse * _dot(direction, q)
    if v < 0.0 or u + v > 1.0:
        return None
    t = inverse * _dot(edge2, q)
    return (t, u, v) if t > 1e-8 else None


def _view_basis(view_role: str) -> tuple[Vec3, Vec3]:
    if view_role == "front":
        return ((0.0, 0.0, -1.0), (1.0, 0.0, 0.0))
    if view_role == "rear":
        return ((0.0, 0.0, 1.0), (-1.0, 0.0, 0.0))
    if view_role == "side":
        return ((-1.0, 0.0, 0.0), (0.0, 0.0, -1.0))
    if view_role == "three-quarter":
        return (normalize((-0.7, 0.0, -0.7)), normalize((0.7, 0.0, -0.7)))
    if view_role == "detail":
        return (normalize((-0.2, -0.05, -1.0)), normalize((1.0, 0.0, -0.2)))
    raise ValueError("ray_renderer_view_role_invalid")


def _shade(
    panel_id: str,
    uv: Vec2,
    normal: Vec3,
    light: Vec3,
    *,
    texture_sampler: TextureSampler | None,
) -> RGBA:
    palette = ((48, 82, 131), (137, 70, 69), (55, 114, 87), (177, 125, 58))
    sampled = texture_sampler(panel_id, uv) if texture_sampler is not None else None
    base = (
        sampled[:3]
        if sampled is not None
        else palette[int(sha256_bytes(panel_id.encode("utf-8"))[:2], 16) % len(palette)]
    )
    logo = 0.36 < uv[0] < 0.64 and 0.32 < uv[1] < 0.54
    pattern = 18 if (int(uv[0] * 12) + int(uv[1] * 12)) % 2 == 0 else 0
    lambert = 0.62 + 0.38 * abs(_dot(normal, light))
    if logo and sampled is None:
        base = (218, 208, 180)
    return (
        min(255, round((base[0] + pattern) * lambert)),
        min(255, round((base[1] + pattern) * lambert)),
        min(255, round((base[2] + pattern) * lambert)),
        sampled[3] if sampled is not None else 255,
    )


def _projected_extent(vertices: list[Vec3], center: Vec3, axis: Vec3) -> float:
    return max(abs(_dot(sub(vertex, center), axis)) for vertex in vertices)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Vec3, factor: float) -> Vec3:
    return (a[0] * factor, a[1] * factor, a[2] * factor)
