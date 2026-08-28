from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from math import atan2, isfinite, pi, sqrt
from typing import Any

from closy_forge.geometry.mesh_model import MeshSet, Vec3

SIGNED_DISTANCE_AUDIT_VERSION = "closy.signed_distance_audit.d0.v1"

_POSITION_DIGITS = 9
_DEGENERATE_AREA_SQUARED = 1e-24
_RAY_HIT_EPSILON = 1e-8
_RAY_DIRECTIONS: tuple[Vec3, ...] = (
    (1.0, 0.1732050808, 0.0714285714),
    (0.113, 1.0, 0.271),
    (0.307, 0.149, 1.0),
    (-1.0, 0.219, 0.097),
    (0.181, -1.0, 0.337),
    (0.419, 0.083, -1.0),
    (0.5773502692, 0.7071067812, 0.4082482905),
)

VertexKey = tuple[float, float, float]
EdgeKey = tuple[VertexKey, VertexKey]


def audit_body_signed_clearance(
    points: Sequence[Vec3],
    body: MeshSet,
    *,
    point_ids: Sequence[str] | None = None,
    cloth_half_thickness_meters: float,
    skin_margin_meters: float,
    oracle_uncertainty_meters: float,
    promotion_guard_band_meters: float,
) -> dict[str, Any]:
    """Audit signed clearance using independent parity and winding-number queries.

    The GLB writer de-indexes meshes and the reference ellipsoids intentionally
    contain zero-area pole triangles. The query surface welds exact positions and
    excludes only those zero-area triangles; the original authority is unchanged.
    """

    if not points:
        raise ValueError("signed_distance_points_empty")
    if point_ids is None:
        point_ids = [f"vertex.{index}" for index in range(len(points))]
    if len(point_ids) != len(points):
        raise ValueError("signed_distance_point_id_count_mismatch")
    policy_values = (
        cloth_half_thickness_meters,
        skin_margin_meters,
        oracle_uncertainty_meters,
        promotion_guard_band_meters,
    )
    if any(not isfinite(value) or value < 0.0 for value in policy_values):
        raise ValueError("signed_distance_policy_invalid")

    surface = _canonical_surface(body)
    topology = surface["topology"]
    triangles = surface["triangles"]
    if not triangles:
        raise ValueError("avatar_collision_mesh_has_no_query_triangles")

    witnesses = [
        _query_point(
            point,
            point_id=str(point_id),
            triangles=triangles,
            topology_qualified=bool(topology["querySurfaceQualified"]),
            cloth_half_thickness_meters=cloth_half_thickness_meters,
            skin_margin_meters=skin_margin_meters,
            uncertainty_meters=oracle_uncertainty_meters,
        )
        for point_id, point in zip(point_ids, points, strict=True)
    ]
    worst = min(
        witnesses,
        key=lambda item: (
            float(item["bodySignedClearanceMeters"]),
            str(item["garmentPointId"]),
        ),
    )
    fixtures = _known_fixture_audit(
        body,
        triangles,
        topology_qualified=bool(topology["querySurfaceQualified"]),
        uncertainty_meters=oracle_uncertainty_meters,
    )
    uncertain = [item for item in witnesses if item["oracleUncertain"]]
    return {
        "schemaVersion": 1,
        "auditVersion": SIGNED_DISTANCE_AUDIT_VERSION,
        "signConvention": "positive_outside_negative_inside_authoritative_closed_surface",
        "authorityPreserved": True,
        "queryNormalization": (
            "position_weld_and_zero_area_triangle_exclusion_without_authority_mutation"
        ),
        "policy": {
            "clothHalfThicknessMeters": _round(cloth_half_thickness_meters),
            "skinMarginMeters": _round(skin_margin_meters),
            "numericalOracleUncertaintyMeters": _round(oracle_uncertainty_meters),
            "promotionGuardBandMeters": _round(promotion_guard_band_meters),
        },
        "surfaceTopology": topology,
        "knownFixtureAudit": fixtures,
        "pointCount": len(witnesses),
        "oracleUncertainCount": len(uncertain),
        "minimumSignedSurfaceDistanceMeters": min(
            float(item["signedSurfaceDistanceMeters"]) for item in witnesses
        ),
        "minimumBodySignedClearanceMeters": float(worst["bodySignedClearanceMeters"]),
        "worstWitness": worst,
        "promotionEligible": bool(
            topology["querySurfaceQualified"]
            and fixtures["status"] == "pass"
            and not uncertain
            and float(worst["bodySignedClearanceMeters"]) >= promotion_guard_band_meters
        ),
    }


def _canonical_surface(body: MeshSet) -> dict[str, Any]:
    triangles: list[dict[str, Any]] = []
    mesh_reports: list[dict[str, Any]] = []
    total_source_degenerate = 0
    total_source_duplicate = 0
    total_boundary = 0
    total_nonmanifold = 0
    total_winding_mismatch = 0
    for mesh_index, mesh in enumerate(body.meshes):
        edge_counts: Counter[EdgeKey] = Counter()
        directed_edges: Counter[tuple[VertexKey, VertexKey]] = Counter()
        seen_triangles: set[tuple[VertexKey, VertexKey, VertexKey]] = set()
        source_degenerate = 0
        source_duplicate = 0
        mesh_triangles: list[dict[str, Any]] = []
        for triangle_index, triangle in enumerate(mesh.triangles):
            points = tuple(mesh.vertices[index] for index in triangle)
            keys = tuple(_vertex_key(point) for point in points)
            normal = _cross(_sub(points[1], points[0]), _sub(points[2], points[0]))
            if len(set(keys)) != 3 or _dot(normal, normal) <= _DEGENERATE_AREA_SQUARED:
                source_degenerate += 1
                continue
            canonical_triangle = tuple(sorted(keys))
            if canonical_triangle in seen_triangles:
                source_duplicate += 1
                continue
            seen_triangles.add(canonical_triangle)
            record = {
                "meshIndex": mesh_index,
                "meshName": mesh.name,
                "sourceTriangleIndex": triangle_index,
                "triangleId": f"{mesh.name}:triangle.{triangle_index}",
                "points": points,
            }
            mesh_triangles.append(record)
            triangles.append(record)
            for start, end in (
                (keys[0], keys[1]),
                (keys[1], keys[2]),
                (keys[2], keys[0]),
            ):
                edge_counts[tuple(sorted((start, end)))] += 1
                directed_edges[(start, end)] += 1
        boundary = sum(count == 1 for count in edge_counts.values())
        nonmanifold = sum(count > 2 for count in edge_counts.values())
        winding_mismatch = sum(
            count == 2
            and not (
                directed_edges[(edge[0], edge[1])] == 1 and directed_edges[(edge[1], edge[0])] == 1
            )
            for edge, count in edge_counts.items()
        )
        qualified = bool(
            mesh_triangles and boundary == 0 and nonmanifold == 0 and winding_mismatch == 0
        )
        mesh_reports.append(
            {
                "meshIndex": mesh_index,
                "meshName": mesh.name,
                "sourceVertexCount": len(mesh.vertices),
                "sourceTriangleCount": len(mesh.triangles),
                "queryTriangleCount": len(mesh_triangles),
                "sourceDegenerateTriangleCount": source_degenerate,
                "sourceDuplicateTriangleCount": source_duplicate,
                "boundaryEdgeCount": boundary,
                "nonManifoldEdgeCount": nonmanifold,
                "windingMismatchEdgeCount": winding_mismatch,
                "watertightAfterCanonicalWeld": boundary == 0 and nonmanifold == 0,
                "windingConsistentAfterCanonicalWeld": winding_mismatch == 0,
                "querySurfaceQualified": qualified,
            }
        )
        total_source_degenerate += source_degenerate
        total_source_duplicate += source_duplicate
        total_boundary += boundary
        total_nonmanifold += nonmanifold
        total_winding_mismatch += winding_mismatch
    return {
        "triangles": triangles,
        "topology": {
            "sourceMeshCount": len(body.meshes),
            "sourceVertexCount": body.vertex_count,
            "sourceTriangleCount": body.triangle_count,
            "queryTriangleCount": len(triangles),
            "sourceDegenerateTriangleCount": total_source_degenerate,
            "sourceDuplicateTriangleCount": total_source_duplicate,
            "boundaryEdgeCount": total_boundary,
            "nonManifoldEdgeCount": total_nonmanifold,
            "windingMismatchEdgeCount": total_winding_mismatch,
            "watertightAfterCanonicalWeld": total_boundary == 0 and total_nonmanifold == 0,
            "windingConsistentAfterCanonicalWeld": total_winding_mismatch == 0,
            "querySurfaceQualified": bool(mesh_reports)
            and all(item["querySurfaceQualified"] for item in mesh_reports),
            "meshes": mesh_reports,
        },
    }


def _query_point(
    point: Vec3,
    *,
    point_id: str,
    triangles: Sequence[dict[str, Any]],
    topology_qualified: bool,
    cloth_half_thickness_meters: float,
    skin_margin_meters: float,
    uncertainty_meters: float,
) -> dict[str, Any]:
    if not all(isfinite(value) for value in point):
        raise ValueError("signed_distance_point_nonfinite")
    nearest: tuple[float, str, Vec3, dict[str, Any]] | None = None
    for triangle in triangles:
        closest = _closest_point_on_triangle(point, *triangle["points"])
        distance = _distance(point, closest)
        candidate = (distance, str(triangle["triangleId"]), closest, triangle)
        if nearest is None or candidate[:2] < nearest[:2]:
            nearest = candidate
    if nearest is None:
        raise ValueError("signed_distance_surface_empty")
    unsigned, _, closest, nearest_triangle = nearest
    ray_votes = [_ray_parity(point, direction, triangles) for direction in _RAY_DIRECTIONS]
    inside_votes = sum(ray_votes)
    outside_votes = len(ray_votes) - inside_votes
    parity_inside = inside_votes > outside_votes
    parity_unanimous = inside_votes in {0, len(ray_votes)}
    winding_number = _generalized_winding_number(point, triangles)
    winding_inside = abs(winding_number) > 0.5
    near_surface = unsigned <= uncertainty_meters
    oracle_agreement = parity_inside == winding_inside
    oracle_uncertain = bool(
        not topology_qualified or near_surface or not parity_unanimous or not oracle_agreement
    )
    signed_surface = -unsigned if parity_inside else unsigned
    clearance = signed_surface - cloth_half_thickness_meters - skin_margin_meters
    return {
        "garmentPointId": point_id,
        "garmentPosition": [_round(value) for value in point],
        "closestBodyMeshIndex": int(nearest_triangle["meshIndex"]),
        "closestBodyMeshName": str(nearest_triangle["meshName"]),
        "closestBodyTriangleIndex": int(nearest_triangle["sourceTriangleIndex"]),
        "closestBodyTriangleId": str(nearest_triangle["triangleId"]),
        "closestPoint": [_round(value) for value in closest],
        "unsignedDistanceMeters": _round(unsigned),
        "signDecision": "inside" if parity_inside else "outside",
        "signedSurfaceDistanceMeters": _round(signed_surface),
        "bodySignedClearanceMeters": _round(clearance),
        "rayParityVotes": {
            "inside": inside_votes,
            "outside": outside_votes,
            "unanimous": parity_unanimous,
            "votes": ["inside" if vote else "outside" for vote in ray_votes],
        },
        "independentGeneralizedWinding": {
            "windingNumber": _round(winding_number),
            "signDecision": "inside" if winding_inside else "outside",
            "agreesWithRayParity": oracle_agreement,
        },
        "nearSurfaceWithinUncertainty": near_surface,
        "oracleUncertain": oracle_uncertain,
    }


def _known_fixture_audit(
    body: MeshSet,
    triangles: Sequence[dict[str, Any]],
    *,
    topology_qualified: bool,
    uncertainty_meters: float,
) -> dict[str, Any]:
    all_points = [point for mesh in body.meshes for point in mesh.vertices]
    minimum = tuple(min(point[axis] for point in all_points) for axis in range(3))
    maximum = tuple(max(point[axis] for point in all_points) for axis in range(3))
    center = tuple((minimum[axis] + maximum[axis]) * 0.5 for axis in range(3))
    extent = max(maximum[axis] - minimum[axis] for axis in range(3))
    outside = (maximum[0] + extent, maximum[1] + extent, maximum[2] + extent)
    first_triangle = triangles[0]["points"]
    near_surface = tuple(sum(point[axis] for point in first_triangle) / 3.0 for axis in range(3))
    records = [
        _query_point(
            center,
            point_id="fixture.known_inside.bounds_center",
            triangles=triangles,
            topology_qualified=topology_qualified,
            cloth_half_thickness_meters=0.0,
            skin_margin_meters=0.0,
            uncertainty_meters=uncertainty_meters,
        ),
        _query_point(
            outside,
            point_id="fixture.known_outside.bounds_offset",
            triangles=triangles,
            topology_qualified=topology_qualified,
            cloth_half_thickness_meters=0.0,
            skin_margin_meters=0.0,
            uncertainty_meters=uncertainty_meters,
        ),
        _query_point(
            near_surface,
            point_id="fixture.known_near_surface.triangle_centroid",
            triangles=triangles,
            topology_qualified=topology_qualified,
            cloth_half_thickness_meters=0.0,
            skin_margin_meters=0.0,
            uncertainty_meters=uncertainty_meters,
        ),
    ]
    checks = {
        "knownInside": records[0]["signDecision"] == "inside"
        and records[0]["oracleUncertain"] is False,
        "knownOutside": records[1]["signDecision"] == "outside"
        and records[1]["oracleUncertain"] is False,
        "knownNearSurfaceFailsClosed": records[2]["oracleUncertain"] is True,
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "records": records,
    }


def _ray_parity(point: Vec3, direction: Vec3, triangles: Sequence[dict[str, Any]]) -> bool:
    distances = sorted(
        distance
        for triangle in triangles
        if (distance := _ray_triangle_distance(point, direction, *triangle["points"])) is not None
    )
    unique: list[float] = []
    for distance in distances:
        if not unique or abs(distance - unique[-1]) > _RAY_HIT_EPSILON:
            unique.append(distance)
    return len(unique) % 2 == 1


def _generalized_winding_number(point: Vec3, triangles: Sequence[dict[str, Any]]) -> float:
    solid_angle = 0.0
    for triangle in triangles:
        a, b, c = (_sub(vertex, point) for vertex in triangle["points"])
        la, lb, lc = _length(a), _length(b), _length(c)
        numerator = _dot(a, _cross(b, c))
        denominator = la * lb * lc + _dot(a, b) * lc + _dot(b, c) * la + _dot(c, a) * lb
        solid_angle += 2.0 * atan2(numerator, denominator)
    return solid_angle / (4.0 * pi)


def _ray_triangle_distance(
    origin: Vec3, direction: Vec3, a: Vec3, b: Vec3, c: Vec3
) -> float | None:
    edge1 = _sub(b, a)
    edge2 = _sub(c, a)
    h = _cross(direction, edge2)
    determinant = _dot(edge1, h)
    if abs(determinant) <= 1e-12:
        return None
    inverse = 1.0 / determinant
    s = _sub(origin, a)
    u = inverse * _dot(s, h)
    if u < 0.0 or u > 1.0:
        return None
    q = _cross(s, edge1)
    v = inverse * _dot(direction, q)
    if v < 0.0 or u + v > 1.0:
        return None
    distance = inverse * _dot(edge2, q)
    return distance if distance > 1e-9 else None


def _closest_point_on_triangle(point: Vec3, a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(point, a)
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a
    bp = _sub(point, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        return _add(a, _scale(ab, d1 / (d1 - d3)))
    cp = _sub(point, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        return _add(a, _scale(ac, d2 / (d2 - d6)))
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        return _add(b, _scale(_sub(c, b), (d4 - d3) / ((d4 - d3) + (d5 - d6))))
    denominator = 1.0 / max(1e-15, va + vb + vc)
    v, w = vb * denominator, vc * denominator
    return _add(a, _add(_scale(ab, v), _scale(ac, w)))


def _vertex_key(point: Vec3) -> VertexKey:
    return tuple(round(float(value), _POSITION_DIGITS) for value in point)  # type: ignore[return-value]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(value: Vec3, factor: float) -> Vec3:
    return (value[0] * factor, value[1] * factor, value[2] * factor)


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(value: Vec3) -> float:
    return sqrt(_dot(value, value))


def _distance(a: Vec3, b: Vec3) -> float:
    return _length(_sub(a, b))


def _round(value: float) -> float:
    return round(float(value), 9)
