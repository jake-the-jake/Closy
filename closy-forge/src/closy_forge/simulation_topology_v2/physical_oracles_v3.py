from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import sqrt
from typing import Any

from closy_forge.geometry.mesh_model import MeshSet, Tri, Vec3
from closy_forge.simulation.reference_cloth_solver import flatten_mesh

TRIANGLE_BODY_ORACLE_VERSION = "closy.phy1.independent_triangle_body_surface_oracle.v3"
TRIANGLE_TRIANGLE_ORACLE_VERSION = "closy.phy1.independent_triangle_triangle_distance_oracle.v3"


def independent_self_collision_oracle(
    mesh: MeshSet,
    *,
    contact_threshold_meters: float,
    excluded_vertex_pairs: set[tuple[int, int]],
) -> dict[str, Any]:
    positions, triangles = _flatten_triangles(mesh)
    contacts: list[dict[str, Any]] = []
    candidate_count = 0
    for first_index, first in enumerate(triangles):
        first_vertices = set(first)
        first_bounds = _bounds(positions, first)
        for second_index in range(first_index + 1, len(triangles)):
            second = triangles[second_index]
            second_vertices = set(second)
            if first_vertices & second_vertices:
                continue
            if any(
                (min(a, b), max(a, b)) in excluded_vertex_pairs
                for a in first_vertices
                for b in second_vertices
            ):
                continue
            if not _bounds_overlap(
                first_bounds,
                _bounds(positions, second),
                contact_threshold_meters,
            ):
                continue
            candidate_count += 1
            distance = _triangle_triangle_distance(positions, first, second)
            if distance > contact_threshold_meters:
                continue
            contacts.append(
                {
                    "firstTriangleIndex": first_index,
                    "secondTriangleIndex": second_index,
                    "distanceMeters": _round(distance),
                    "penetrationMeters": _round(contact_threshold_meters - distance),
                }
            )
    return {
        "oracleVersion": TRIANGLE_TRIANGLE_ORACLE_VERSION,
        "triangleCount": len(triangles),
        "candidatePairCount": candidate_count,
        "contactCount": len(contacts),
        "unresolvedContactCount": len(contacts),
        "maximumResidualDepthMeters": max(
            (record["penetrationMeters"] for record in contacts), default=0.0
        ),
        "worstWitnesses": sorted(
            contacts,
            key=lambda item: (
                -item["penetrationMeters"],
                item["firstTriangleIndex"],
                item["secondTriangleIndex"],
            ),
        )[:8],
    }


def independent_body_surface_oracle(
    garment: MeshSet,
    body_surface: MeshSet,
    collision_primitives: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    garment_positions, garment_triangles = _flatten_triangles(garment)
    body_positions, body_triangles = _flatten_triangles(body_surface)
    minimum_surface_distance = float("inf")
    closest_pair: tuple[int, int] | None = None
    for garment_index, garment_triangle in enumerate(garment_triangles):
        garment_bounds = _bounds(garment_positions, garment_triangle)
        for body_index, body_triangle in enumerate(body_triangles):
            body_bounds = _bounds(body_positions, body_triangle)
            lower_bound = _bounds_distance(garment_bounds, body_bounds)
            if lower_bound >= minimum_surface_distance:
                continue
            distance = _triangle_triangle_distance_between_sets(
                garment_positions,
                garment_triangle,
                body_positions,
                body_triangle,
            )
            if distance < minimum_surface_distance:
                minimum_surface_distance = distance
                closest_pair = (garment_index, body_index)
    signed = [
        _signed_primitive_clearance(point, collision_primitives) for point in garment_positions
    ]
    maximum_penetration = max((-value for value in signed if value < 0.0), default=0.0)
    signed_clearance = (
        -maximum_penetration if maximum_penetration > 0.0 else minimum_surface_distance
    )
    return {
        "oracleVersion": TRIANGLE_BODY_ORACLE_VERSION,
        "garmentTriangleCount": len(garment_triangles),
        "bodyTriangleCount": len(body_triangles),
        "minimumSurfaceDistanceMeters": _round(minimum_surface_distance),
        "minimumSignedClearanceMeters": _round(signed_clearance),
        "maximumPenetrationMeters": _round(maximum_penetration),
        "penetratingVertexCount": sum(value < 0.0 for value in signed),
        "closestTrianglePair": None if closest_pair is None else list(closest_pair),
        "solverContactListConsumed": False,
        "solverCollisionPrimitiveConsumedForSurfaceDistance": False,
        "primitiveContractUsedOnlyForIndependentInsideOutsideSign": True,
    }


def independent_dense_render_clearance_oracle(
    render_positions: Sequence[Vec3],
    body_surface: MeshSet,
    collision_primitives: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    body_positions, body_triangles = _flatten_triangles(body_surface)
    minimum_distance = float("inf")
    closest: tuple[int, int] | None = None
    for point_index, point in enumerate(render_positions):
        for triangle_index, triangle in enumerate(body_triangles):
            distance = _point_triangle_distance(
                point,
                body_positions[triangle[0]],
                body_positions[triangle[1]],
                body_positions[triangle[2]],
            )
            if distance < minimum_distance:
                minimum_distance = distance
                closest = (point_index, triangle_index)
    signed = [
        _signed_primitive_clearance(point, collision_primitives) for point in render_positions
    ]
    maximum_penetration = max((-value for value in signed if value < 0.0), default=0.0)
    signed_clearance = -maximum_penetration if maximum_penetration else minimum_distance
    return {
        "oracleVersion": f"{TRIANGLE_BODY_ORACLE_VERSION}.dense_binding",
        "renderVertexCount": len(render_positions),
        "minimumSurfaceDistanceMeters": _round(minimum_distance),
        "minimumSignedClearanceMeters": _round(signed_clearance),
        "maximumPenetrationMeters": _round(maximum_penetration),
        "penetratingVertexCount": sum(value < 0.0 for value in signed),
        "closestRenderVertexBodyTriangle": None if closest is None else list(closest),
        "solverContactListConsumed": False,
    }


def collision_microfixture() -> dict[str, Any]:
    positions: list[Vec3] = [
        (-1.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.25, -1.0),
        (0.0, 0.25, 1.0),
        (0.0, 1.25, 0.0),
        (-1.0, 0.0, 2.0),
        (1.0, 0.0, 2.0),
        (0.0, 1.0, 2.0),
    ]
    intersecting = _triangle_triangle_distance(positions, (0, 1, 2), (3, 4, 5))
    separated = _triangle_triangle_distance(positions, (0, 1, 2), (6, 7, 8))
    return {
        "oracleVersion": TRIANGLE_TRIANGLE_ORACLE_VERSION,
        "intersectingDistanceMeters": _round(intersecting),
        "intersectingContactCount": int(intersecting <= 1e-12),
        "separatedDistanceMeters": _round(separated),
        "separatedContactCount": int(separated <= 1e-12),
        "status": "pass" if intersecting <= 1e-12 and separated > 0.0 else "fail",
    }


def _flatten_triangles(mesh: MeshSet) -> tuple[list[Vec3], list[Tri]]:
    flat = flatten_mesh(mesh)
    triangles = [
        (
            flat.mesh_offsets[mesh_index] + triangle[0],
            flat.mesh_offsets[mesh_index] + triangle[1],
            flat.mesh_offsets[mesh_index] + triangle[2],
        )
        for mesh_index, panel in enumerate(mesh.meshes)
        for triangle in panel.triangles
    ]
    return flat.positions, triangles


def _triangle_triangle_distance(positions: Sequence[Vec3], first: Tri, second: Tri) -> float:
    return _triangle_triangle_distance_between_sets(positions, first, positions, second)


def _triangle_triangle_distance_between_sets(
    first_positions: Sequence[Vec3],
    first: Tri,
    second_positions: Sequence[Vec3],
    second: Tri,
) -> float:
    a = tuple(first_positions[index] for index in first)
    b = tuple(second_positions[index] for index in second)
    if any(_segment_intersects_triangle(a[index], a[(index + 1) % 3], *b) for index in range(3)):
        return 0.0
    if any(_segment_intersects_triangle(b[index], b[(index + 1) % 3], *a) for index in range(3)):
        return 0.0
    distances = [_point_triangle_distance(point, *b) for point in a]
    distances.extend(_point_triangle_distance(point, *a) for point in b)
    for first_edge in range(3):
        for second_edge in range(3):
            distances.append(
                _segment_segment_distance(
                    a[first_edge],
                    a[(first_edge + 1) % 3],
                    b[second_edge],
                    b[(second_edge + 1) % 3],
                )
            )
    return min(distances)


def _segment_intersects_triangle(start: Vec3, end: Vec3, a: Vec3, b: Vec3, c: Vec3) -> bool:
    epsilon = 1e-12
    direction = _subtract(end, start)
    edge1 = _subtract(b, a)
    edge2 = _subtract(c, a)
    h = _cross(direction, edge2)
    determinant = _dot(edge1, h)
    if abs(determinant) <= epsilon:
        return False
    inverse = 1.0 / determinant
    s = _subtract(start, a)
    u = inverse * _dot(s, h)
    if u < -epsilon or u > 1.0 + epsilon:
        return False
    q = _cross(s, edge1)
    v = inverse * _dot(direction, q)
    if v < -epsilon or u + v > 1.0 + epsilon:
        return False
    t = inverse * _dot(edge2, q)
    return -epsilon <= t <= 1.0 + epsilon


def _point_triangle_distance(point: Vec3, a: Vec3, b: Vec3, c: Vec3) -> float:
    ab = _subtract(b, a)
    ac = _subtract(c, a)
    ap = _subtract(point, a)
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return _length(ap)
    bp = _subtract(point, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return _length(bp)
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        return _length(_subtract(point, _add(a, _scale(ab, d1 / (d1 - d3)))))
    cp = _subtract(point, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return _length(cp)
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        return _length(_subtract(point, _add(a, _scale(ac, d2 / (d2 - d6)))))
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and d4 - d3 >= 0.0 and d5 - d6 >= 0.0:
        edge = _subtract(c, b)
        weight = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return _length(_subtract(point, _add(b, _scale(edge, weight))))
    normal = _cross(ab, ac)
    normal_length = _length(normal)
    return 0.0 if normal_length <= 1e-15 else abs(_dot(ap, normal)) / normal_length


def _segment_segment_distance(p1: Vec3, q1: Vec3, p2: Vec3, q2: Vec3) -> float:
    epsilon = 1e-15
    d1 = _subtract(q1, p1)
    d2 = _subtract(q2, p2)
    r = _subtract(p1, p2)
    a, e, f = _dot(d1, d1), _dot(d2, d2), _dot(d2, r)
    if a <= epsilon and e <= epsilon:
        return _length(r)
    if a <= epsilon:
        s, t = 0.0, _clamp(f / e)
    else:
        c = _dot(d1, r)
        if e <= epsilon:
            t, s = 0.0, _clamp(-c / a)
        else:
            b = _dot(d1, d2)
            denominator = a * e - b * b
            s = _clamp((b * f - c * e) / denominator) if denominator else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, _clamp(-c / a)
            elif t > 1.0:
                t, s = 1.0, _clamp((b - c) / a)
    first = _add(p1, _scale(d1, s))
    second = _add(p2, _scale(d2, t))
    return _length(_subtract(first, second))


def _signed_primitive_clearance(point: Vec3, primitives: Sequence[Mapping[str, Any]]) -> float:
    values: list[float] = []
    for primitive in primitives:
        if primitive.get("type") == "capsule":
            a = _vec3(primitive["a"])
            b = _vec3(primitive["b"])
            nearest = _closest_segment_point(point, a, b)
            values.append(_length(_subtract(point, nearest)) - float(primitive["radius"]))
        elif primitive.get("type") == "ellipsoid":
            centre = _vec3(primitive["center"])
            radii = _vec3(primitive["radii"])
            local: Vec3 = (
                (point[0] - centre[0]) / radii[0],
                (point[1] - centre[1]) / radii[1],
                (point[2] - centre[2]) / radii[2],
            )
            values.append((_length(local) - 1.0) * min(radii))
    return min(values, default=float("inf"))


def _closest_segment_point(point: Vec3, start: Vec3, end: Vec3) -> Vec3:
    direction = _subtract(end, start)
    denominator = _dot(direction, direction)
    parameter = (
        0.0
        if denominator <= 1e-15
        else _clamp(_dot(_subtract(point, start), direction) / denominator)
    )
    return _add(start, _scale(direction, parameter))


def _bounds(positions: Sequence[Vec3], triangle: Tri) -> tuple[Vec3, Vec3]:
    points = [positions[index] for index in triangle]
    return (
        tuple(min(point[axis] for point in points) for axis in range(3)),
        tuple(max(point[axis] for point in points) for axis in range(3)),
    )  # type: ignore[return-value]


def _bounds_overlap(first: tuple[Vec3, Vec3], second: tuple[Vec3, Vec3], pad: float) -> bool:
    return all(
        first[0][axis] - pad <= second[1][axis] and second[0][axis] - pad <= first[1][axis]
        for axis in range(3)
    )


def _bounds_distance(first: tuple[Vec3, Vec3], second: tuple[Vec3, Vec3]) -> float:
    delta = [
        max(0.0, first[0][axis] - second[1][axis], second[0][axis] - first[1][axis])
        for axis in range(3)
    ]
    return sqrt(sum(value * value for value in delta))


def _vec3(value: object) -> Vec3:
    values = list(value) if isinstance(value, Sequence) else []
    if len(values) != 3:
        raise ValueError("phy1_v3_oracle_vec3_invalid")
    return (float(values[0]), float(values[1]), float(values[2]))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _add(first: Vec3, second: Vec3) -> Vec3:
    return (first[0] + second[0], first[1] + second[1], first[2] + second[2])


def _subtract(first: Vec3, second: Vec3) -> Vec3:
    return (first[0] - second[0], first[1] - second[1], first[2] - second[2])


def _scale(value: Vec3, factor: float) -> Vec3:
    return (value[0] * factor, value[1] * factor, value[2] * factor)


def _dot(first: Vec3, second: Vec3) -> float:
    return first[0] * second[0] + first[1] * second[1] + first[2] * second[2]


def _cross(first: Vec3, second: Vec3) -> Vec3:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _length(value: Vec3) -> float:
    return sqrt(_dot(value, value))


def _round(value: float) -> float:
    return round(float(value), 12)
