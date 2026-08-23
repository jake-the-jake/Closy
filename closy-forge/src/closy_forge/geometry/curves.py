from __future__ import annotations

from math import cos, sin
from typing import Any

Vec2 = tuple[float, float]


def vec2(value: Any) -> Vec2:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise ValueError("expected 2D point")
    return (float(value[0]), float(value[1]))


def lerp(a: Vec2, b: Vec2, t: float) -> Vec2:
    return (a[0] * (1 - t) + b[0] * t, a[1] * (1 - t) + b[1] * t)


def eval_curve(curve: dict[str, Any], t: float) -> Vec2:
    kind = curve["type"]
    if kind == "line":
        return lerp(vec2(curve["points"][0]), vec2(curve["points"][1]), t)
    if kind == "quadratic_bezier":
        p0, p1, p2 = [vec2(p) for p in curve["points"]]
        a = lerp(p0, p1, t)
        b = lerp(p1, p2, t)
        return lerp(a, b, t)
    if kind == "cubic_bezier":
        p0, p1, p2, p3 = [vec2(p) for p in curve["points"]]
        a = lerp(p0, p1, t)
        b = lerp(p1, p2, t)
        c = lerp(p2, p3, t)
        return lerp(lerp(a, b, t), lerp(b, c, t), t)
    if kind == "arc":
        center = vec2(curve["center"])
        radius = float(curve["radius"])
        start = float(curve["startAngle"])
        end = float(curve["endAngle"])
        theta = start * (1 - t) + end * t
        return (center[0] + radius * cos(theta), center[1] + radius * sin(theta))
    if kind == "polyline":
        points = [vec2(p) for p in curve["points"]]
        if len(points) < 2:
            raise ValueError("polyline requires at least two points")
        scaled = t * (len(points) - 1)
        index = min(int(scaled), len(points) - 2)
        return lerp(points[index], points[index + 1], scaled - index)
    raise ValueError(f"unsupported curve type {kind!r}")


def sample_curve(curve: dict[str, Any], sample_count: int) -> list[Vec2]:
    if sample_count < 2:
        raise ValueError("sample_count must be >= 2")
    return [eval_curve(curve, i / (sample_count - 1)) for i in range(sample_count)]


def signed_area(points: list[Vec2]) -> float:
    area = 0.0
    for i, point in enumerate(points):
        nxt = points[(i + 1) % len(points)]
        area += point[0] * nxt[1] - nxt[0] * point[1]
    return area * 0.5


def segments_intersect(a: Vec2, b: Vec2, c: Vec2, d: Vec2) -> bool:
    def orient(p: Vec2, q: Vec2, r: Vec2) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    return o1 * o2 < -1e-12 and o3 * o4 < -1e-12


def polygon_self_intersects(points: list[Vec2]) -> bool:
    n = len(points)
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        for j in range(i + 1, n):
            if abs(i - j) <= 1 or {i, j} == {0, n - 1}:
                continue
            c, d = points[j], points[(j + 1) % n]
            if segments_intersect(a, b, c, d):
                return True
    return False
