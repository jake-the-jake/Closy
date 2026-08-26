from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from closy_forge.geometry.mesh_model import MeshSet, Vec2, Vec3

RGBA = tuple[int, int, int, int]
TextureSampler = Callable[[str, Vec2], RGBA]


@dataclass(frozen=True)
class CpuRasterResult:
    width: int
    height: int
    rgba: bytes
    foreground: frozenset[int]
    rendered_triangle_count: int
    projected_vertex_count: int
    camera: dict[str, object]


def rasterize_settled_garment(
    meshset: MeshSet,
    *,
    label: str,
    width: int,
    height: int,
    camera: Mapping[str, object] | None = None,
    texture_sampler: TextureSampler | None = None,
    background: RGBA = (246, 244, 239, 0),
) -> CpuRasterResult:
    """Rasterize a settled garment with a deterministic, dependency-free CPU path.

    The fixed projection is calibrated only for the public D0 avatar fixture. It
    is deliberately independent from the source-fixture polygon generator and
    from the fidelity metric implementation.
    """

    if width <= 0 or height <= 0:
        raise ValueError("raster dimensions must be positive")
    active_camera = dict(camera or {})
    _validate_camera(active_camera, label)
    pixels = bytearray(background * (width * height))
    depth = [math.inf] * (width * height)
    foreground: set[int] = set()
    rendered_triangles = 0
    projected_vertices = 0
    sampler = texture_sampler or _default_sampler
    allowed = _visible_panels(label)
    visible_meshes = [
        mesh
        for mesh in sorted(meshset.meshes, key=lambda item: (item.panel_id, item.name))
        if mesh.panel_id in allowed
    ]
    unframed = [
        _project(vertex, label, width, height)
        for mesh in visible_meshes
        for vertex in mesh.vertices
    ]
    frame_offset = _frame_offset(unframed, width, height, active_camera)

    for mesh in visible_meshes:
        projected = [
            _apply_frame(_project(vertex, label, width, height), frame_offset)
            for vertex in mesh.vertices
        ]
        projected_vertices += len(projected)
        for tri in mesh.triangles:
            points = [projected[index] for index in tri]
            uvs = [mesh.panel_uvs[index] for index in tri]
            if _raster_triangle(
                pixels,
                depth,
                foreground,
                width,
                height,
                points,
                uvs,
                mesh.panel_id,
                sampler,
            ):
                rendered_triangles += 1
    return CpuRasterResult(
        width=width,
        height=height,
        rgba=bytes(pixels),
        foreground=frozenset(foreground),
        rendered_triangle_count=rendered_triangles,
        projected_vertex_count=projected_vertices,
        camera={
            "projection": str(active_camera.get("projection", "orthographic")),
            "azimuthDegrees": _number(active_camera.get("azimuthDegrees"), _label_azimuth(label)),
            "elevationDegrees": _number(active_camera.get("elevationDegrees"), 4.0),
            "fixtureProjection": "fixed_avatar_d0_orthographic_xy_v1",
            "runtimeBoundsFramed": True,
            "frameOffsetPixels": [round(frame_offset[0], 6), round(frame_offset[1], 6)],
        },
    )


def _raster_triangle(
    pixels: bytearray,
    depth_buffer: list[float],
    foreground: set[int],
    width: int,
    height: int,
    points: list[tuple[float, float, float]],
    uvs: list[Vec2],
    panel_id: str,
    sampler: TextureSampler,
) -> bool:
    area = _edge(points[0], points[1], points[2][0], points[2][1])
    if abs(area) <= 1e-9:
        return False
    min_x = max(0, int(math.floor(min(point[0] for point in points))))
    max_x = min(width - 1, int(math.ceil(max(point[0] for point in points))))
    min_y = max(0, int(math.floor(min(point[1] for point in points))))
    max_y = min(height - 1, int(math.ceil(max(point[1] for point in points))))
    wrote = False
    for y in range(min_y, max_y + 1):
        py = y + 0.5
        for x in range(min_x, max_x + 1):
            px = x + 0.5
            w0 = _edge(points[1], points[2], px, py) / area
            w1 = _edge(points[2], points[0], px, py) / area
            w2 = 1.0 - w0 - w1
            if min(w0, w1, w2) < -1e-8:
                continue
            z = w0 * points[0][2] + w1 * points[1][2] + w2 * points[2][2]
            index = y * width + x
            if z >= depth_buffer[index]:
                continue
            uv = (
                w0 * uvs[0][0] + w1 * uvs[1][0] + w2 * uvs[2][0],
                w0 * uvs[0][1] + w1 * uvs[1][1] + w2 * uvs[2][1],
            )
            color = sampler(panel_id, uv)
            offset = index * 4
            pixels[offset : offset + 4] = bytes(color)
            depth_buffer[index] = z
            if color[3] > 0:
                foreground.add(index)
            wrote = True
    return wrote


def _project(vertex: Vec3, label: str, width: int, height: int) -> tuple[float, float, float]:
    x, y, z = vertex
    if label == "back":
        horizontal = -x
        camera_depth = z
    elif label == "left_three_quarter":
        horizontal = x * 0.82 + z * 0.32
        camera_depth = -(z * 0.82 - x * 0.32)
    elif label == "right_three_quarter":
        horizontal = x * 0.82 - z * 0.32
        camera_depth = -(z * 0.82 + x * 0.32)
    else:
        horizontal = x
        camera_depth = -z
    nx = 0.5 + horizontal * 0.46
    ny = 0.78 - (y - 1.04) * 1.21
    return (nx * width, ny * height, camera_depth)


def _visible_panels(label: str) -> set[str]:
    back = label == "back"
    torso = "panel.back" if back else "panel.front"
    sleeveless_torso = "panel.sleeveless_top.back" if back else "panel.sleeveless_top.front"
    long_sleeved_torso = "panel.long_sleeved_top.back" if back else "panel.long_sleeved_top.front"
    simple_skirt = "panel.simple_skirt.back" if back else "panel.simple_skirt.front"
    trouser_face = "back" if back else "front"
    return {
        torso,
        sleeveless_torso,
        long_sleeved_torso,
        simple_skirt,
        f"panel.simple_trousers.{trouser_face}.left",
        f"panel.simple_trousers.{trouser_face}.right",
        f"panel.simple_dress.{trouser_face}.bodice",
        f"panel.simple_dress.{trouser_face}.skirt",
        "panel.sleeve.left",
        "panel.sleeve.right",
        "panel.long_sleeved_top.sleeve.left",
        "panel.long_sleeved_top.sleeve.right",
        "panel.neck_band",
    }


def _frame_offset(
    projected: list[tuple[float, float, float]],
    width: int,
    height: int,
    camera: Mapping[str, object],
) -> tuple[float, float]:
    if not projected:
        return (0.0, 0.0)
    principal = camera.get("principalPointNormalized", [0.5, 0.5])
    if not isinstance(principal, list | tuple) or len(principal) != 2:
        principal = [0.5, 0.5]
    target_x = _number(principal[0], 0.5) * width
    target_y = _number(principal[1], 0.5) * height
    center_x = (min(point[0] for point in projected) + max(point[0] for point in projected)) / 2
    center_y = (min(point[1] for point in projected) + max(point[1] for point in projected)) / 2
    return (target_x - center_x, target_y - center_y)


def _apply_frame(
    point: tuple[float, float, float], offset: tuple[float, float]
) -> tuple[float, float, float]:
    return (point[0] + offset[0], point[1] + offset[1], point[2])


def _validate_camera(camera: Mapping[str, object], label: str) -> None:
    if str(camera.get("projection", "orthographic")) != "orthographic":
        raise ValueError("unsupported_d0_camera_projection")
    values = [
        _number(camera.get("azimuthDegrees"), _label_azimuth(label)),
        _number(camera.get("elevationDegrees"), 4.0),
    ]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("nonfinite_d0_camera")


def _label_azimuth(label: str) -> float:
    return {
        "front": 0.0,
        "back": 180.0,
        "left_three_quarter": 62.0,
        "right_three_quarter": -62.0,
    }.get(label, 0.0)


def _edge(
    a: tuple[float, float, float], b: tuple[float, float, float], x: float, y: float
) -> float:
    return (x - a[0]) * (b[1] - a[1]) - (y - a[1]) * (b[0] - a[0])


def _default_sampler(panel_id: str, uv: Vec2) -> RGBA:
    del panel_id, uv
    return (42, 96, 210, 255)


def _number(value: object, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return fallback
    return fallback
