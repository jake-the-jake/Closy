from __future__ import annotations

from typing import Any

from .curves import polygon_self_intersects, sample_curve, signed_area
from .mesh_model import Mesh, Vec2, Vec3


def panel_boundary_samples(panel: dict[str, Any]) -> tuple[list[Vec2], dict[str, list[int]]]:
    points: list[Vec2] = []
    edge_vertices: dict[str, list[int]] = {}
    for edge in panel["boundary"]:
        samples = sample_curve(edge["curve"], int(edge["sampleCount"]))
        if points and samples[0] == points[-1]:
            samples = samples[1:]
        start = len(points)
        points.extend(samples)
        edge_vertices[edge["id"]] = list(range(start, len(points)))
    if len(points) >= 2 and points[0] == points[-1]:
        points.pop()
        for ids in edge_vertices.values():
            if ids and ids[-1] == len(points):
                ids.pop()
    return points, edge_vertices


def validate_panel_boundary(panel: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    points, _ = panel_boundary_samples(panel)
    if len(points) < 4:
        issues.append("panel_boundary_too_short")
    if signed_area(points) <= 1e-6:
        issues.append("panel_boundary_not_ccw_or_zero_area")
    if polygon_self_intersects(points):
        issues.append("panel_boundary_self_intersects")
    return issues


def triangulate_panel(
    panel: dict[str, Any],
    transform: str,
) -> tuple[Mesh, dict[str, list[int]]]:
    points, edge_vertices = panel_boundary_samples(panel)
    issues = validate_panel_boundary(panel)
    if issues:
        raise ValueError(f"invalid panel {panel['id']}: {','.join(issues)}")
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    vertices: list[Vec3] = [_map_point(point, transform) for point in points]
    vertices.append(_map_point((cx, cy), transform))
    uvs: list[Vec2] = [point for point in points] + [(cx, cy)]
    center_i = len(vertices) - 1
    triangles = [(center_i, i, (i + 1) % (len(vertices) - 1)) for i in range(len(vertices) - 1)]
    if transform == "back":
        triangles = [(a, c, b) for a, b, c in triangles]
    return (
        Mesh(
            name=panel["id"],
            panel_id=panel["id"],
            vertices=vertices,
            panel_uvs=uvs,
            triangles=triangles,
        ),
        edge_vertices,
    )


def _map_point(point: Vec2, transform: str) -> Vec3:
    x, y = point
    garment_bottom = 0.74
    if transform == "front":
        return (x, garment_bottom + y, 0.115)
    if transform == "jacket.facing.left":
        return (x, garment_bottom + y, 0.119)
    if transform == "jacket.facing.right":
        return (x, garment_bottom + y, 0.119)
    if transform == "layered.inner.front":
        return (x, garment_bottom + y, 0.112)
    if transform == "layered.inner.back":
        return (-x, garment_bottom + y, -0.112)
    if transform == "layered.outer.front":
        return (x, garment_bottom + y, 0.132)
    if transform == "layered.outer.back":
        return (-x, garment_bottom + y, -0.132)
    if transform == "back":
        return (-x, garment_bottom + y, -0.115)
    if transform == "lower.front":
        return (x, 0.06 + y, 0.115)
    if transform == "lower.back":
        return (-x, 0.06 + y, -0.115)
    if transform == "dress.skirt.front":
        return (x, 0.40 + y, 0.115)
    if transform == "dress.skirt.back":
        return (-x, 0.40 + y, -0.115)
    if transform == "dress.bodice.front":
        return (x, 1.02 + y, 0.115)
    if transform == "dress.bodice.back":
        return (-x, 1.02 + y, -0.115)
    if transform == "sleeve.left":
        return (-0.36 - y, 1.34 - 0.10 * y, x * 0.75)
    if transform == "sleeve.right":
        return (0.36 + y, 1.34 - 0.10 * y, -x * 0.75)
    if transform == "neck_band":
        return (x, 1.42 + 0.02 * y, 0.04 + y)
    raise ValueError(f"unknown transform {transform}")
