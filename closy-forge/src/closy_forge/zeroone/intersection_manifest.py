from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.zeroone.dynamic_oracle import triangles_intersect

Vec3 = tuple[float, float, float]
Tri = tuple[int, int, int]

INTERSECTION_CLASSIFIER_VERSION = "closy.intersection-classifier.exact-aabb.v2"
GEOMETRIC_EPSILON_METERS = 1.0e-9


@dataclass(frozen=True)
class SurfaceRepresentation:
    representation_id: str
    positions: list[Vec3]
    triangles: list[Tri]
    logical_vertex_ids: list[int]
    triangle_lineage: list[dict[str, Any]]


def audit_surface(
    surface: SurfaceRepresentation, *, topology_override: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Audit one indexed surface without hiding crossings at shared single vertices."""

    _validate_surface(surface)
    bounds = _bounds(surface.positions)
    diagonal = math.dist(tuple(bounds["minimum"]), tuple(bounds["maximum"]))
    epsilon = max(GEOMETRIC_EPSILON_METERS, diagonal * 1.0e-10)
    topology = (
        topology_override if topology_override is not None else _topology_audit(surface, epsilon)
    )
    candidates = _broad_phase(surface, epsilon)
    pairs: list[dict[str, Any]] = []
    adjacent_intersections = 0
    for left, right in candidates:
        left_triangle = surface.triangles[left]
        right_triangle = surface.triangles[right]
        left_ids = {surface.logical_vertex_ids[index] for index in left_triangle}
        right_ids = {surface.logical_vertex_ids[index] for index in right_triangle}
        shared = sorted(left_ids & right_ids)
        expected_adjacency = len(shared) >= 2
        a = (
            surface.positions[left_triangle[0]],
            surface.positions[left_triangle[1]],
            surface.positions[left_triangle[2]],
        )
        b = (
            surface.positions[right_triangle[0]],
            surface.positions[right_triangle[1]],
            surface.positions[right_triangle[2]],
        )
        if shared:
            intersects = _crosses_beyond_shared_simplex(a, b, shared, surface, epsilon)
        else:
            intersects = triangles_intersect(a, b)
        if not intersects:
            continue
        adjacent_intersections += int(expected_adjacency)
        witness = _intersection_witness(a, b)
        pair_id = f"tri.{left:06d}:tri.{right:06d}"
        pairs.append(
            {
                "pairId": pair_id,
                "leftTriangle": left,
                "rightTriangle": right,
                "expectedTopologicalAdjacency": expected_adjacency,
                "sharedLogicalVertexIds": shared,
                "classification": (
                    "crossing_beyond_expected_shared_simplex"
                    if expected_adjacency
                    else "nonadjacent_surface_intersection"
                ),
                "witness": witness,
                "leftLineage": surface.triangle_lineage[left],
                "rightLineage": surface.triangle_lineage[right],
            }
        )
    witness_hash = hashlib.sha256(canonical_dumps(pairs).encode("utf-8")).hexdigest()
    return {
        "schemaVersion": 2,
        "classifierVersion": INTERSECTION_CLASSIFIER_VERSION,
        "representationId": surface.representation_id,
        "vertexCount": len(surface.positions),
        "triangleCount": len(surface.triangles),
        "topology": topology,
        "bounds": bounds,
        "spatialIndex": {
            "kind": "deterministic_x_axis_sweep_aabb",
            "epsilonMeters": epsilon,
            "candidatePairCount": len(candidates),
        },
        "adjacentIntersectionCount": adjacent_intersections,
        "nonadjacentIntersectionCount": len(pairs) - adjacent_intersections,
        "intersectingPairCount": len(pairs),
        "intersectingPairs": pairs,
        "deterministicWitnessHash": witness_hash,
    }


def _validate_surface(surface: SurfaceRepresentation) -> None:
    if len(surface.logical_vertex_ids) != len(surface.positions):
        raise ValueError("intersection_logical_vertex_inventory_mismatch")
    if len(surface.triangle_lineage) != len(surface.triangles):
        raise ValueError("intersection_triangle_lineage_inventory_mismatch")
    if not surface.positions or not surface.triangles:
        raise ValueError("intersection_surface_empty")
    for position in surface.positions:
        if not all(math.isfinite(value) for value in position):
            raise ValueError("intersection_surface_nonfinite")
    for triangle in surface.triangles:
        if len(set(triangle)) != 3 or any(
            index < 0 or index >= len(surface.positions) for index in triangle
        ):
            raise ValueError("intersection_triangle_invalid")


def _bounds(positions: Iterable[Vec3]) -> dict[str, list[float]]:
    values = list(positions)
    minimum = [min(position[axis] for position in values) for axis in range(3)]
    maximum = [max(position[axis] for position in values) for axis in range(3)]
    return {
        "minimum": minimum,
        "maximum": maximum,
        "size": [maximum[axis] - minimum[axis] for axis in range(3)],
    }


def _topology_audit(surface: SurfaceRepresentation, epsilon: float) -> dict[str, Any]:
    face_keys: dict[tuple[int, int, int], list[int]] = {}
    edge_faces: dict[tuple[int, int], list[int]] = {}
    degenerate: list[int] = []
    for triangle_index, triangle in enumerate(surface.triangles):
        ids = (
            surface.logical_vertex_ids[triangle[0]],
            surface.logical_vertex_ids[triangle[1]],
            surface.logical_vertex_ids[triangle[2]],
        )
        sorted_ids = sorted(ids)
        face_key = (sorted_ids[0], sorted_ids[1], sorted_ids[2])
        face_keys.setdefault(face_key, []).append(triangle_index)
        for left, right in ((ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0])):
            edge_faces.setdefault((min(left, right), max(left, right)), []).append(triangle_index)
        a, b, c = (surface.positions[index] for index in triangle)
        if _double_area(a, b, c) <= epsilon * epsilon:
            degenerate.append(triangle_index)
    duplicate_groups = [rows for rows in face_keys.values() if len(rows) > 1]
    nonmanifold = [edge for edge, rows in edge_faces.items() if len(rows) > 2]
    boundary_edges = [edge for edge, rows in edge_faces.items() if len(rows) == 1]
    boundary_components = _boundary_components(boundary_edges)
    return {
        "duplicateFaceCount": sum(len(rows) - 1 for rows in duplicate_groups),
        "duplicateFaceGroups": duplicate_groups,
        "nonManifoldEdgeCount": len(nonmanifold),
        "nonManifoldEdges": [list(edge) for edge in nonmanifold],
        "tJunctionCount": _t_junction_count(surface, edge_faces, epsilon),
        "degenerateTriangleCount": len(degenerate),
        "degenerateTriangles": degenerate,
        "boundaryEdgeCount": len(boundary_edges),
        "boundaryComponentCount": len(boundary_components),
        "boundaryComponents": boundary_components,
    }


def _boundary_components(edges: list[tuple[int, int]]) -> list[list[int]]:
    neighbours: dict[int, set[int]] = {}
    for left, right in edges:
        neighbours.setdefault(left, set()).add(right)
        neighbours.setdefault(right, set()).add(left)
    components: list[list[int]] = []
    unseen = set(neighbours)
    while unseen:
        seed = min(unseen)
        stack = [seed]
        component: list[int] = []
        unseen.remove(seed)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbour in sorted(neighbours[current], reverse=True):
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    stack.append(neighbour)
        components.append(sorted(component))
    return sorted(components, key=lambda row: (row[0], len(row)))


def _t_junction_count(
    surface: SurfaceRepresentation,
    edge_faces: dict[tuple[int, int], list[int]],
    epsilon: float,
) -> int:
    first_position: dict[int, Vec3] = {}
    for index, logical_id in enumerate(surface.logical_vertex_ids):
        first_position.setdefault(logical_id, surface.positions[index])
    count = 0
    for edge in edge_faces:
        start = first_position[edge[0]]
        end = first_position[edge[1]]
        edge_length = math.dist(start, end)
        if edge_length <= epsilon:
            continue
        for logical_id, point in first_position.items():
            if logical_id in edge:
                continue
            if _point_segment_distance(point, start, end) <= epsilon:
                projection = _projection_parameter(point, start, end)
                if epsilon / edge_length < projection < 1.0 - epsilon / edge_length:
                    count += 1
    return count


def _broad_phase(surface: SurfaceRepresentation, epsilon: float) -> list[tuple[int, int]]:
    boxes = []
    for index, triangle in enumerate(surface.triangles):
        points = [surface.positions[value] for value in triangle]
        minimum: Vec3 = (
            min(point[0] for point in points) - epsilon,
            min(point[1] for point in points) - epsilon,
            min(point[2] for point in points) - epsilon,
        )
        maximum: Vec3 = (
            max(point[0] for point in points) + epsilon,
            max(point[1] for point in points) + epsilon,
            max(point[2] for point in points) + epsilon,
        )
        boxes.append((minimum, maximum, index))
    boxes.sort(key=lambda row: (row[0][0], row[2]))
    active: list[tuple[Vec3, Vec3, int]] = []
    result: list[tuple[int, int]] = []
    for minimum, maximum, index in boxes:
        active = [row for row in active if row[1][0] >= minimum[0]]
        for other_minimum, other_maximum, other_index in active:
            if all(
                minimum[axis] <= other_maximum[axis] and maximum[axis] >= other_minimum[axis]
                for axis in (1, 2)
            ):
                result.append((min(other_index, index), max(other_index, index)))
        active.append((minimum, maximum, index))
    return sorted(set(result))


def _crosses_beyond_shared_simplex(
    left: tuple[Vec3, Vec3, Vec3],
    right: tuple[Vec3, Vec3, Vec3],
    shared_ids: list[int],
    surface: SurfaceRepresentation,
    epsilon: float,
) -> bool:
    if not triangles_intersect(left, right):
        return False
    shared_points = [
        surface.positions[surface.logical_vertex_ids.index(logical_id)] for logical_id in shared_ids
    ]
    for point in (*left, *right):
        if any(math.dist(point, shared) <= epsilon for shared in shared_points):
            continue
        if _point_in_triangle_strict(point, right if point in left else left, epsilon):
            return True
    for a, b in _triangle_edges(left):
        for c, d in _triangle_edges(right):
            contact = _closest_segment_contact(a, b, c, d, epsilon)
            if contact is not None and not _on_expected_simplex(contact, shared_points, epsilon):
                return True
    return False


def _triangle_edges(triangle: tuple[Vec3, Vec3, Vec3]) -> tuple[tuple[Vec3, Vec3], ...]:
    return (
        (triangle[0], triangle[1]),
        (triangle[1], triangle[2]),
        (triangle[2], triangle[0]),
    )


def _on_expected_simplex(point: Vec3, shared: list[Vec3], epsilon: float) -> bool:
    if len(shared) == 1:
        return math.dist(point, shared[0]) <= epsilon
    if len(shared) >= 2:
        return _point_segment_distance(point, shared[0], shared[1]) <= epsilon
    return False


def _closest_segment_contact(a: Vec3, b: Vec3, c: Vec3, d: Vec3, epsilon: float) -> Vec3 | None:
    # Distinguish a shared endpoint/edge from a crossing using deterministic closest points.
    u = _sub(b, a)
    v = _sub(d, c)
    w = _sub(a, c)
    aa = _dot(u, u)
    bb = _dot(u, v)
    cc = _dot(v, v)
    dd = _dot(u, w)
    ee = _dot(v, w)
    denominator = aa * cc - bb * bb
    if aa <= epsilon * epsilon or cc <= epsilon * epsilon:
        return None
    if abs(denominator) <= epsilon * epsilon:
        s = 0.0
        t = max(0.0, min(1.0, ee / cc))
    else:
        s = max(0.0, min(1.0, (bb * ee - cc * dd) / denominator))
        t = max(0.0, min(1.0, (aa * ee - bb * dd) / denominator))
    left = _add(a, _scale(u, s))
    right = _add(c, _scale(v, t))
    if math.dist(left, right) > epsilon:
        return None
    return _scale(_add(left, right), 0.5)


def _point_in_triangle_strict(
    point: Vec3, triangle: tuple[Vec3, Vec3, Vec3], epsilon: float
) -> bool:
    a, b, c = triangle
    v0 = _sub(c, a)
    v1 = _sub(b, a)
    v2 = _sub(point, a)
    dot00 = _dot(v0, v0)
    dot01 = _dot(v0, v1)
    dot02 = _dot(v0, v2)
    dot11 = _dot(v1, v1)
    dot12 = _dot(v1, v2)
    denominator = dot00 * dot11 - dot01 * dot01
    if abs(denominator) <= epsilon * epsilon:
        return False
    u = (dot11 * dot02 - dot01 * dot12) / denominator
    v = (dot00 * dot12 - dot01 * dot02) / denominator
    plane_distance = abs(_dot(_sub(point, a), _cross(v1, v0)))
    return plane_distance <= epsilon * math.sqrt(max(denominator, epsilon)) and (
        u > epsilon and v > epsilon and u + v < 1.0 - epsilon
    )


def _intersection_witness(
    left: tuple[Vec3, Vec3, Vec3], right: tuple[Vec3, Vec3, Vec3]
) -> dict[str, Any]:
    minimum = [
        max(min(point[axis] for point in left), min(point[axis] for point in right))
        for axis in range(3)
    ]
    maximum = [
        min(max(point[axis] for point in left), max(point[axis] for point in right))
        for axis in range(3)
    ]
    point = (
        (minimum[0] + maximum[0]) * 0.5,
        (minimum[1] + maximum[1]) * 0.5,
        (minimum[2] + maximum[2]) * 0.5,
    )
    return {
        "kind": "narrow_phase_overlap_aabb_midpoint",
        "point": list(point),
        "leftBarycentric": list(_barycentric(point, left)),
        "rightBarycentric": list(_barycentric(point, right)),
    }


def _barycentric(point: Vec3, triangle: tuple[Vec3, Vec3, Vec3]) -> tuple[float, float, float]:
    a, b, c = triangle
    v0, v1, v2 = _sub(b, a), _sub(c, a), _sub(point, a)
    d00, d01, d11 = _dot(v0, v0), _dot(v0, v1), _dot(v1, v1)
    d20, d21 = _dot(v2, v0), _dot(v2, v1)
    denominator = d00 * d11 - d01 * d01
    if abs(denominator) <= 1.0e-30:
        return (0.0, 0.0, 0.0)
    v = (d11 * d20 - d01 * d21) / denominator
    w = (d00 * d21 - d01 * d20) / denominator
    return (1.0 - v - w, v, w)


def _double_area(a: Vec3, b: Vec3, c: Vec3) -> float:
    value = _cross(_sub(b, a), _sub(c, a))
    return math.sqrt(_dot(value, value))


def _projection_parameter(point: Vec3, start: Vec3, end: Vec3) -> float:
    direction = _sub(end, start)
    denominator = _dot(direction, direction)
    return 0.0 if denominator == 0.0 else _dot(_sub(point, start), direction) / denominator


def _point_segment_distance(point: Vec3, start: Vec3, end: Vec3) -> float:
    t = max(0.0, min(1.0, _projection_parameter(point, start, end)))
    return math.dist(point, _add(start, _scale(_sub(end, start), t)))


def _sub(left: Vec3, right: Vec3) -> Vec3:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _add(left: Vec3, right: Vec3) -> Vec3:
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def _scale(value: Vec3, amount: float) -> Vec3:
    return (value[0] * amount, value[1] * amount, value[2] * amount)


def _dot(left: Vec3, right: Vec3) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _cross(left: Vec3, right: Vec3) -> Vec3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )
