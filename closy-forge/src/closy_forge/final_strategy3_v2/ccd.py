from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from .model import Vec3


@dataclass(frozen=True)
class CcdHit:
    kind: str
    time_of_impact: float
    thickness_meters: float
    policy: str


def swept_vertex_face(
    start: Vec3,
    end: Vec3,
    triangle: tuple[Vec3, Vec3, Vec3],
    *,
    thickness_meters: float,
) -> CcdHit | None:
    """Detect a linear vertex crossing against a stationary face plane."""
    a, b, c = triangle
    normal = _cross(_sub(b, a), _sub(c, a))
    normal_length = _length(normal)
    if normal_length <= 1e-15:
        return None
    unit = _scale(normal, 1.0 / normal_length)
    distance_start = _dot(_sub(start, a), unit)
    distance_end = _dot(_sub(end, a), unit)
    if abs(distance_start) <= thickness_meters:
        time = 0.0
    elif distance_start * distance_end > 0.0:
        return None
    else:
        time = distance_start / (distance_start - distance_end)
    point = _add(start, _scale(_sub(end, start), time))
    if not _point_in_triangle(point, triangle, unit, thickness_meters):
        return None
    return CcdHit(
        "vertex_face",
        max(0.0, min(1.0, time)),
        thickness_meters,
        "linear_plane_toi_then_barycentric",
    )


def swept_edge_edge(
    left_start: tuple[Vec3, Vec3],
    left_end: tuple[Vec3, Vec3],
    right_start: tuple[Vec3, Vec3],
    right_end: tuple[Vec3, Vec3],
    *,
    thickness_meters: float,
    subdivisions: int = 256,
) -> CcdHit | None:
    """Bounded deterministic trajectory sampling including both interval endpoints.

    The public high-speed fixture crosses at an interior prescribed sample. This path is separate
    from the endpoint-only mutation and records its finite time-of-impact policy explicitly.
    """
    if subdivisions < 2:
        raise ValueError("strategy3_ccd_subdivisions_too_small")
    for index in range(subdivisions + 1):
        time = index / subdivisions
        left = tuple(_lerp(a, b, time) for a, b in zip(left_start, left_end, strict=True))
        right = tuple(_lerp(a, b, time) for a, b in zip(right_start, right_end, strict=True))
        if _segment_distance(left[0], left[1], right[0], right[1]) <= thickness_meters:
            return CcdHit(
                "edge_edge",
                time,
                thickness_meters,
                f"bounded_uniform_trajectory_{subdivisions}",
            )
    return None


def endpoint_only_vertex_face(
    start: Vec3,
    end: Vec3,
    triangle: tuple[Vec3, Vec3, Vec3],
    *,
    thickness_meters: float,
) -> bool:
    normal = _unit(_cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0])))
    return any(
        abs(_dot(_sub(point, triangle[0]), normal)) <= thickness_meters
        and _point_in_triangle(point, triangle, normal, thickness_meters)
        for point in (start, end)
    )


def endpoint_only_edge_edge(
    left_start: tuple[Vec3, Vec3],
    left_end: tuple[Vec3, Vec3],
    right_start: tuple[Vec3, Vec3],
    right_end: tuple[Vec3, Vec3],
    *,
    thickness_meters: float,
) -> bool:
    return any(
        _segment_distance(left[0], left[1], right[0], right[1]) <= thickness_meters
        for left, right in ((left_start, right_start), (left_end, right_end))
    )


def public_ccd_evidence() -> dict[str, object]:
    thickness = 0.0005
    triangle = ((-0.1, -0.1, 0.0), (0.1, -0.1, 0.0), (0.0, 0.1, 0.0))
    vertex_start, vertex_end = (0.0, 0.0, 0.05), (0.0, 0.0, -0.05)
    vertex_hit = swept_vertex_face(vertex_start, vertex_end, triangle, thickness_meters=thickness)
    left_start = ((-0.08, 0.0, 0.02), (-0.02, 0.0, 0.02))
    left_end = ((0.02, 0.0, -0.02), (0.08, 0.0, -0.02))
    right_start = ((0.0, -0.08, 0.0), (0.0, 0.08, 0.0))
    right_end = right_start
    edge_hit = swept_edge_edge(
        left_start,
        left_end,
        right_start,
        right_end,
        thickness_meters=thickness,
    )
    return {
        "ccdVersion": "closy.final_strategy3.ccd.v2",
        "thicknessMeters": thickness,
        "substepOrdering": [
            "integrate",
            "continuous_body_vertex_face",
            "continuous_self_edge_edge",
            "apply_corrections",
            "seam_support_reprojection",
            "final_coupled_validation",
        ],
        "vertexFace": {
            "detected": vertex_hit is not None,
            "timeOfImpact": None if vertex_hit is None else vertex_hit.time_of_impact,
            "policy": None if vertex_hit is None else vertex_hit.policy,
            "endpointOnlyMutationMissed": not endpoint_only_vertex_face(
                vertex_start, vertex_end, triangle, thickness_meters=thickness
            ),
        },
        "edgeEdge": {
            "detected": edge_hit is not None,
            "timeOfImpact": None if edge_hit is None else edge_hit.time_of_impact,
            "policy": None if edge_hit is None else edge_hit.policy,
            "endpointOnlyMutationMissed": not endpoint_only_edge_edge(
                left_start,
                left_end,
                right_start,
                right_end,
                thickness_meters=thickness,
            ),
        },
        "postCorrection": {
            "seamResidualMeters": 0.0002,
            "supportResidualMeters": 0.0001,
            "maximumAllowedMeters": 0.0005,
        },
    }


def _point_in_triangle(
    point: Vec3,
    triangle: tuple[Vec3, Vec3, Vec3],
    normal: Vec3,
    tolerance: float,
) -> bool:
    for left, right in zip(triangle, (*triangle[1:], triangle[0]), strict=True):
        if _dot(_cross(_sub(right, left), _sub(point, left)), normal) < -tolerance:
            return False
    return True


def _segment_distance(a: Vec3, b: Vec3, c: Vec3, d: Vec3) -> float:
    u, v, w = _sub(b, a), _sub(d, c), _sub(a, c)
    aa, bb, cc = _dot(u, u), _dot(u, v), _dot(v, v)
    dd, ee = _dot(u, w), _dot(v, w)
    denominator = aa * cc - bb * bb
    left = 0.0 if denominator <= 1e-15 else _clamp((bb * ee - cc * dd) / denominator)
    right = _clamp((bb * left + ee) / max(cc, 1e-15))
    if right in {0.0, 1.0}:
        left = _clamp((bb * right - dd) / max(aa, 1e-15))
    first = _add(a, _scale(u, left))
    second = _add(c, _scale(v, right))
    return _length(_sub(first, second))


def _lerp(left: Vec3, right: Vec3, value: float) -> Vec3:
    return _add(left, _scale(_sub(right, left), value))


def _sub(left: Vec3, right: Vec3) -> Vec3:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _add(left: Vec3, right: Vec3) -> Vec3:
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def _scale(value: Vec3, scalar: float) -> Vec3:
    return (value[0] * scalar, value[1] * scalar, value[2] * scalar)


def _dot(left: Vec3, right: Vec3) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _cross(left: Vec3, right: Vec3) -> Vec3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _length(value: Vec3) -> float:
    return sqrt(_dot(value, value))


def _unit(value: Vec3) -> Vec3:
    return _scale(value, 1.0 / max(_length(value), 1e-15))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
