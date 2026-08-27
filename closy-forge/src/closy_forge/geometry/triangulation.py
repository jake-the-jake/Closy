from __future__ import annotations

import math
from typing import Any

from .curves import sample_curve, signed_area
from .mesh_model import Mesh, Tri, Vec2, Vec3

RELATIVE_LENGTH_TOLERANCE = 1e-10
RELATIVE_AREA_TOLERANCE = 1e-12


def panel_boundary_samples(panel: dict[str, Any]) -> tuple[list[Vec2], dict[str, list[int]]]:
    points: list[Vec2] = []
    edge_vertices: dict[str, list[int]] = {}
    for edge in panel["boundary"]:
        samples = sample_curve(edge["curve"], int(edge["sampleCount"]))
        ids: list[int] = []
        if points and samples[0] == points[-1]:
            ids.append(len(points) - 1)
            samples = samples[1:]
        start = len(points)
        points.extend(samples)
        ids.extend(range(start, len(points)))
        edge_vertices[str(edge["id"])] = ids
    if len(points) >= 2 and points[0] == points[-1]:
        closing_index = len(points) - 1
        points.pop()
        for ids in edge_vertices.values():
            ids[:] = [0 if index == closing_index else index for index in ids]
    return points, edge_vertices


def validate_panel_boundary(panel: dict[str, Any]) -> list[str]:
    points, _ = panel_boundary_samples(panel)
    issues: list[str] = []
    if len(points) < 3:
        return ["panel_boundary_too_short"]
    length_tolerance, area_tolerance = _tolerances(points)
    for left in range(len(points)):
        for right in range(left + 1, len(points)):
            if math.dist(points[left], points[right]) <= length_tolerance:
                issues.append("panel_boundary_repeated_or_near_repeated_point")
                break
        if issues:
            break
    if abs(signed_area(points)) <= area_tolerance:
        issues.append("panel_boundary_zero_area")
    if _polygon_self_intersects(points, area_tolerance):
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

    triangles = triangulate_simple_polygon(points)
    if transform == "back" or transform.endswith(".back"):
        triangles = [(a, c, b) for a, b, c in triangles]
    mesh = Mesh(
        name=panel["id"],
        panel_id=panel["id"],
        vertices=[_map_point(point, transform) for point in points],
        panel_uvs=list(points),
        triangles=triangles,
    )
    _validate_triangulation(points, triangles)
    return mesh, edge_vertices


def triangulate_simple_polygon(points: list[Vec2]) -> list[Tri]:
    """Deterministic, dependency-free ear clipping for a validated simple polygon."""

    if len(points) < 3:
        raise ValueError("polygon_too_short")
    length_tolerance, area_tolerance = _tolerances(points)
    if any(
        math.dist(points[left], points[right]) <= length_tolerance
        for left in range(len(points))
        for right in range(left + 1, len(points))
    ):
        raise ValueError("polygon_repeated_or_near_repeated_point")
    if _polygon_self_intersects(points, area_tolerance):
        raise ValueError("polygon_self_intersects")
    area = signed_area(points)
    if abs(area) <= area_tolerance:
        raise ValueError("polygon_zero_area")

    remaining = list(range(len(points)))
    if area < 0.0:
        remaining.reverse()
    triangles: list[Tri] = []
    while len(remaining) > 3:
        clipped = False
        for cursor, current in enumerate(remaining):
            previous = remaining[cursor - 1]
            following = remaining[(cursor + 1) % len(remaining)]
            if _orient(points[previous], points[current], points[following]) <= area_tolerance:
                continue
            if any(
                _point_in_or_on_triangle(
                    points[candidate],
                    points[previous],
                    points[current],
                    points[following],
                    area_tolerance,
                )
                for candidate in remaining
                if candidate not in {previous, current, following}
            ):
                continue
            triangles.append((previous, current, following))
            del remaining[cursor]
            clipped = True
            break
        if not clipped:
            raise ValueError("polygon_ear_clipping_failed")
    final = (remaining[0], remaining[1], remaining[2])
    if _orient(points[final[0]], points[final[1]], points[final[2]]) <= area_tolerance:
        raise ValueError("polygon_degenerate_final_triangle")
    triangles.append(final)
    _validate_triangulation(points, triangles)
    return triangles


def _validate_triangulation(points: list[Vec2], triangles: list[Tri]) -> None:
    _, area_tolerance = _tolerances(points)
    if len(triangles) != len(points) - 2:
        raise ValueError("triangulation_triangle_count_mismatch")
    triangle_area = sum(
        abs(_orient(points[a], points[b], points[c])) * 0.5 for a, b, c in triangles
    )
    if abs(triangle_area - abs(signed_area(points))) > area_tolerance * max(1, len(points)):
        raise ValueError("triangulation_area_mismatch")
    triangle_edges = {
        tuple(sorted(edge))
        for triangle in triangles
        for edge in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        )
    }
    boundary_edges = {
        tuple(sorted((index, (index + 1) % len(points)))) for index in range(len(points))
    }
    if not boundary_edges.issubset(triangle_edges):
        raise ValueError("triangulation_boundary_not_preserved")


def _tolerances(points: list[Vec2]) -> tuple[float, float]:
    width = max(point[0] for point in points) - min(point[0] for point in points)
    height = max(point[1] for point in points) - min(point[1] for point in points)
    scale = max(width, height, 1e-9)
    return scale * RELATIVE_LENGTH_TOLERANCE, scale * scale * RELATIVE_AREA_TOLERANCE


def _orient(a: Vec2, b: Vec2, c: Vec2) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_in_or_on_triangle(point: Vec2, a: Vec2, b: Vec2, c: Vec2, tolerance: float) -> bool:
    return (
        _orient(a, b, point) >= -tolerance
        and _orient(b, c, point) >= -tolerance
        and _orient(c, a, point) >= -tolerance
    )


def _polygon_self_intersects(points: list[Vec2], tolerance: float) -> bool:
    count = len(points)
    for left in range(count):
        a = points[left]
        b = points[(left + 1) % count]
        for right in range(left + 1, count):
            if abs(left - right) <= 1 or {left, right} == {0, count - 1}:
                continue
            c = points[right]
            d = points[(right + 1) % count]
            if _segments_intersect(a, b, c, d, tolerance):
                return True
    return False


def _segments_intersect(a: Vec2, b: Vec2, c: Vec2, d: Vec2, tolerance: float) -> bool:
    orientations = (
        _orient(a, b, c),
        _orient(a, b, d),
        _orient(c, d, a),
        _orient(c, d, b),
    )
    if (
        orientations[0] * orientations[1] < -tolerance
        and orientations[2] * orientations[3] < -tolerance
    ):
        return True
    return any(
        abs(value) <= tolerance and _point_on_segment(point, first, second, tolerance)
        for value, point, first, second in (
            (orientations[0], c, a, b),
            (orientations[1], d, a, b),
            (orientations[2], a, c, d),
            (orientations[3], b, c, d),
        )
    )


def _point_on_segment(point: Vec2, a: Vec2, b: Vec2, tolerance: float) -> bool:
    return (
        min(a[0], b[0]) - tolerance <= point[0] <= max(a[0], b[0]) + tolerance
        and min(a[1], b[1]) - tolerance <= point[1] <= max(a[1], b[1]) + tolerance
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
        return (x, garment_bottom + y, -0.112)
    if transform == "layered.outer.front":
        return (x, garment_bottom + y, 0.132)
    if transform == "layered.outer.back":
        return (x, garment_bottom + y, -0.132)
    if transform == "back":
        return (x, garment_bottom + y, -0.115)
    if transform == "lower.front":
        return (x, 0.06 + y, 0.115)
    if transform == "lower.back":
        return (x, 0.06 + y, -0.115)
    if transform == "dress.skirt.front":
        return (x, 0.40 + y, 0.115)
    if transform == "dress.skirt.back":
        return (x, 0.40 + y, -0.115)
    if transform == "dress.bodice.front":
        return (x, 1.02 + y, 0.115)
    if transform == "dress.bodice.back":
        return (x, 1.02 + y, -0.115)
    if transform == "sleeve.left":
        return (-0.64 + y, 1.28 + 0.10 * y, x * 0.75)
    if transform == "sleeve.right":
        return (0.64 - y, 1.28 + 0.10 * y, -x * 0.75)
    if transform == "neck_band":
        return (x, 1.42 + 0.02 * y, 0.04 + y)
    raise ValueError(f"unknown transform {transform}")
