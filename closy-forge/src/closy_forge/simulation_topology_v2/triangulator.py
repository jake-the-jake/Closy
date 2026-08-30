from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet, Tri, Vec2, Vec3
from closy_forge.geometry.triangulation import panel_boundary_samples, triangulate_panel
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

SIMULATION_TOPOLOGY_VERSION = "closy.simulation_topology.v2"
INTERIOR_CONSTRAINED_TRIANGULATOR_VERSION = "closy.interior_constrained_triangulator.v2"
TOPOLOGY_V2_CANONICAL_DIGITS = 12
TOPOLOGY_V2_REFINEMENT_LEVELS = 1
TOPOLOGY_V2_MAX_FLIP_PASSES = 512


@dataclass(frozen=True)
class TopologyV2Result:
    mesh: Mesh
    edge_vertices: dict[str, list[int]]
    provenance: dict[str, Any]
    audit: dict[str, Any]


def build_panel_meshes_v2(
    pattern: dict[str, Any], transforms: Mapping[str, str]
) -> tuple[MeshSet, dict[str, dict[str, list[int]]], dict[str, Any]]:
    """Build an explicitly opt-in physical mesh without changing the v1 garment builders."""

    meshes: list[Mesh] = []
    edge_maps: dict[str, dict[str, list[int]]] = {}
    panels: list[dict[str, Any]] = []
    for panel in pattern["panels"]:
        panel_id = str(panel["id"])
        transform = transforms.get(panel_id)
        if transform is None:
            raise ValueError(f"missing panel transform: {panel_id}")
        result = triangulate_panel_v2(panel, transform)
        meshes.append(result.mesh)
        edge_maps[panel_id] = result.edge_vertices
        panels.append({"panelId": panel_id, "provenance": result.provenance, "audit": result.audit})

    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "simulationTopologyVersion": SIMULATION_TOPOLOGY_VERSION,
        "triangulatorVersion": INTERIOR_CONSTRAINED_TRIANGULATOR_VERSION,
        "selection": "explicit_phy_experiment_only",
        "canonicalDigits": TOPOLOGY_V2_CANONICAL_DIGITS,
        "refinementLevels": TOPOLOGY_V2_REFINEMENT_LEVELS,
        "maxQualityFlipPasses": TOPOLOGY_V2_MAX_FLIP_PASSES,
        "panelCount": len(panels),
        "panels": panels,
        "integrity": {"manifestHash": ""},
    }
    manifest["integrity"]["manifestHash"] = _hash_document(manifest)
    return MeshSet(meshes), edge_maps, manifest


def triangulate_panel_v2(panel: dict[str, Any], transform: str) -> TopologyV2Result:
    """Create a conforming interior mesh while retaining authored boundary indices exactly.

    The v1 ear-clipped polygon is only a constrained seed. Interior edge flips improve its local
    angle quality, then every interior edge is split conformingly. No centre vertex or boundary fan
    is introduced, and no authored boundary point is inserted, removed, or reordered.
    """

    seed_mesh, edge_vertices = triangulate_panel(panel, transform)
    boundary_points, expected_edges = panel_boundary_samples(panel)
    if edge_vertices != expected_edges or seed_mesh.panel_uvs != boundary_points:
        raise ValueError("topology_v2_seed_boundary_identity_mismatch")

    desired_sign = _orientation_sign(seed_mesh.panel_uvs, seed_mesh.triangles[0])
    triangles, flip_count = _improve_interior_edges(
        seed_mesh.panel_uvs,
        seed_mesh.triangles,
        desired_sign,
        max_passes=TOPOLOGY_V2_MAX_FLIP_PASSES,
    )
    vertices = list(seed_mesh.vertices)
    uvs = list(seed_mesh.panel_uvs)
    vertex_records: list[dict[str, Any]] = [
        {
            "newVertexIndex": index,
            "kind": "authored_boundary_sample",
            "sourceBoundaryIndex": index,
            "generation": 0,
        }
        for index in range(len(vertices))
    ]
    triangle_lineage: list[list[int]] = [[index] for index in range(len(triangles))]
    for generation in range(1, TOPOLOGY_V2_REFINEMENT_LEVELS + 1):
        vertices, uvs, triangles, vertex_records, triangle_lineage = _refine_interior_edges(
            vertices,
            uvs,
            triangles,
            vertex_records,
            triangle_lineage,
            desired_sign,
            generation,
        )

    boundary_count = len(boundary_points)
    vertices = list(seed_mesh.vertices) + [
        _vec3_canonical(vertex) for vertex in vertices[boundary_count:]
    ]
    uvs = list(boundary_points) + [_vec2_canonical(uv) for uv in uvs[boundary_count:]]
    mesh = Mesh(
        name=seed_mesh.name,
        panel_id=seed_mesh.panel_id,
        vertices=vertices,
        panel_uvs=uvs,
        triangles=triangles,
        material_id=seed_mesh.material_id,
    )
    audit = audit_panel_topology_v2(
        mesh,
        boundary_points=boundary_points,
        edge_vertices=edge_vertices,
        expected_orientation_sign=desired_sign,
        seed_mesh=seed_mesh,
    )
    if audit["status"] != "pass":
        raise ValueError(f"topology_v2_static_audit_failed:{','.join(audit['failedChecks'])}")

    provenance: dict[str, Any] = {
        "schemaVersion": 1,
        "panelId": str(panel["id"]),
        "simulationTopologyVersion": SIMULATION_TOPOLOGY_VERSION,
        "triangulatorVersion": INTERIOR_CONSTRAINED_TRIANGULATOR_VERSION,
        "seed": {
            "algorithm": "validated_deterministic_ear_clip_constrained_seed",
            "vertexCount": len(seed_mesh.vertices),
            "triangleCount": len(seed_mesh.triangles),
        },
        "qualityImprovement": {
            "interiorEdgeFlipCount": flip_count,
            "refinementLevels": TOPOLOGY_V2_REFINEMENT_LEVELS,
            "method": "conforming_all_interior_edge_midpoint_refinement",
        },
        "boundary": {
            "preservedExactly": True,
            "originalVertexCount": len(boundary_points),
            "newBoundaryVertexCount": 0,
            "edgeVertexIndices": edge_vertices,
        },
        "vertices": vertex_records,
        "triangles": [
            {
                "newTriangleIndex": index,
                "seedTriangleAncestors": ancestors,
                "kind": "interior_refinement_descendant",
            }
            for index, ancestors in enumerate(triangle_lineage)
        ],
        "oldToNew": {
            "vertices": {str(index): index for index in range(len(seed_mesh.vertices))},
            "triangles": {
                str(seed_index): [
                    index
                    for index, ancestors in enumerate(triangle_lineage)
                    if seed_index in ancestors
                ]
                for seed_index in range(len(seed_mesh.triangles))
            },
        },
        "semanticIdentity": {
            "panelId": str(panel["id"]),
            "grainDirection": list(panel.get("grainDirection", [])),
            "materialRegion": panel.get("materialRegion"),
            "edgeIds": [str(edge["id"]) for edge in panel.get("boundary", [])],
            "uvAuthority": "panel_local_authored_boundary_plus_linear_interior_refinement",
        },
        "integrity": {"provenanceHash": ""},
    }
    provenance["integrity"]["provenanceHash"] = _hash_document(provenance)
    return TopologyV2Result(mesh, edge_vertices, provenance, audit)


def audit_panel_topology_v2(
    mesh: Mesh,
    *,
    boundary_points: list[Vec2],
    edge_vertices: dict[str, list[int]],
    expected_orientation_sign: int,
    seed_mesh: Mesh,
) -> dict[str, Any]:
    scale = _panel_scale(boundary_points)
    boundary_indices = set(range(len(boundary_points)))
    edge_counts = Counter(
        _edge_key(left, right)
        for tri in mesh.triangles
        for left, right in _triangle_edges(tri)
    )
    boundary_edges = {
        _edge_key(index, (index + 1) % len(boundary_points))
        for index in range(len(boundary_points))
    }
    double_areas = [
        abs(_orient(mesh.panel_uvs[a], mesh.panel_uvs[b], mesh.panel_uvs[c]))
        for a, b, c in mesh.triangles
    ]
    angles = [_triangle_angles(mesh.panel_uvs, tri) for tri in mesh.triangles]
    aspects = [_triangle_aspect(mesh.panel_uvs, tri) for tri in mesh.triangles]
    edge_lengths = [
        math.dist(mesh.panel_uvs[left], mesh.panel_uvs[right]) for left, right in edge_counts
    ]
    boundary_lengths = [
        math.dist(mesh.panel_uvs[left], mesh.panel_uvs[right]) for left, right in boundary_edges
    ]
    seed_interior_lengths = [
        math.dist(seed_mesh.panel_uvs[left], seed_mesh.panel_uvs[right])
        for left, right in _mesh_edge_counts(seed_mesh.triangles)
        if _edge_key(left, right) not in boundary_edges
    ]
    thresholds = {
        "minimumDoubleAreaMeters2": scale * scale * 1e-10,
        "minimumAngleDegrees": 2.5,
        "maximumAspectRatio": 24.0,
        "maximumEdgeLengthMeters": max(
            max(boundary_lengths, default=0.0) * 1.000000001,
            max(seed_interior_lengths, default=0.0) * 0.500000001,
        ),
    }
    duplicate_faces = len(mesh.triangles) - len({tuple(sorted(tri)) for tri in mesh.triangles})
    inconsistent_winding = sum(
        _orientation_sign(mesh.panel_uvs, tri) != expected_orientation_sign
        for tri in mesh.triangles
    )
    outside = sum(
        not _point_in_polygon(_triangle_centroid(mesh.panel_uvs, tri), boundary_points)
        for tri in mesh.triangles
    )
    t_junctions = _t_junction_count(mesh.panel_uvs, set(edge_counts))
    finite = all(
        math.isfinite(value) for point in (*mesh.vertices, *mesh.panel_uvs) for value in point
    )
    boundary_exact = (
        mesh.panel_uvs[: len(boundary_points)] == boundary_points
        and {index for indices in edge_vertices.values() for index in indices} == boundary_indices
    )
    checks = {
        "boundarySamplesAndOrderPreserved": boundary_exact,
        "boundaryEdgesPreserved": boundary_edges.issubset(edge_counts),
        "manifoldPanel": all(count in {1, 2} for count in edge_counts.values()),
        "duplicateFaces": duplicate_faces == 0,
        "tJunctions": t_junctions == 0,
        "winding": inconsistent_winding == 0,
        "finite": finite,
        "insidePanel": outside == 0,
        "minimumDoubleArea": min(double_areas, default=0.0)
        > thresholds["minimumDoubleAreaMeters2"],
        "minimumAngle": min((value for row in angles for value in row), default=0.0)
        >= thresholds["minimumAngleDegrees"],
        "maximumAspect": max(aspects, default=0.0) <= thresholds["maximumAspectRatio"],
        "maximumEdge": max(edge_lengths, default=0.0) <= thresholds["maximumEdgeLengthMeters"],
        "interiorVerticesAdded": len(mesh.vertices) > len(boundary_points),
    }
    failed = [key for key, passed in checks.items() if not passed]
    return {
        "schemaVersion": 1,
        "auditVersion": "closy.simulation_topology.v2.static_audit.v1",
        "panelId": mesh.panel_id,
        "thresholds": thresholds,
        "measured": {
            "vertexCount": len(mesh.vertices),
            "triangleCount": len(mesh.triangles),
            "authoredBoundaryVertexCount": len(boundary_points),
            "interiorVertexCount": len(mesh.vertices) - len(boundary_points),
            "boundaryEdgeCount": sum(count == 1 for count in edge_counts.values()),
            "nonManifoldEdgeCount": sum(count > 2 for count in edge_counts.values()),
            "duplicateFaceCount": duplicate_faces,
            "tJunctionCount": t_junctions,
            "inconsistentWindingCount": inconsistent_winding,
            "outOfPolygonTriangleCount": outside,
            "minimumDoubleAreaMeters2": min(double_areas, default=0.0),
            "minimumAngleDegrees": min((value for row in angles for value in row), default=0.0),
            "maximumAspectRatio": max(aspects, default=0.0),
            "maximumEdgeLengthMeters": max(edge_lengths, default=0.0),
            "seedMaximumInteriorEdgeLengthMeters": max(seed_interior_lengths, default=0.0),
        },
        "checks": checks,
        "failedChecks": failed,
        "status": "pass" if not failed else "fail",
    }


def _improve_interior_edges(
    points: list[Vec2], triangles: list[Tri], desired_sign: int, *, max_passes: int
) -> tuple[list[Tri], int]:
    current = list(triangles)
    flip_count = 0
    for _ in range(max_passes):
        changed = False
        incidence = _edge_incidence(current)
        for edge in sorted(key for key, records in incidence.items() if len(records) == 2):
            records = incidence[edge]
            first_index, first_opposite = records[0]
            second_index, second_opposite = records[1]
            if first_index >= len(current) or second_index >= len(current):
                continue
            left, right = edge
            if not _strict_convex_flip(points, left, right, first_opposite, second_opposite):
                continue
            before = min(
                _minimum_angle(points, current[first_index]),
                _minimum_angle(points, current[second_index]),
            )
            candidates = (
                _oriented_tri(points, first_opposite, second_opposite, left, desired_sign),
                _oriented_tri(points, second_opposite, first_opposite, right, desired_sign),
            )
            after = min(
                _minimum_angle(points, candidates[0]),
                _minimum_angle(points, candidates[1]),
            )
            if after <= before + 1e-9:
                continue
            current[first_index], current[second_index] = candidates
            flip_count += 1
            changed = True
            break
        if not changed:
            break
    return current, flip_count


def _refine_interior_edges(
    vertices: list[Vec3],
    uvs: list[Vec2],
    triangles: list[Tri],
    vertex_records: list[dict[str, Any]],
    triangle_lineage: list[list[int]],
    desired_sign: int,
    generation: int,
) -> tuple[list[Vec3], list[Vec2], list[Tri], list[dict[str, Any]], list[list[int]]]:
    edge_counts = _mesh_edge_counts(triangles)
    split_edges = sorted(edge for edge, count in edge_counts.items() if count == 2)
    midpoint: dict[tuple[int, int], int] = {}
    new_vertices = list(vertices)
    new_uvs = list(uvs)
    new_records = list(vertex_records)
    for left, right in split_edges:
        index = len(new_vertices)
        midpoint[(left, right)] = index
        new_vertices.append(_mid3(vertices[left], vertices[right]))
        new_uvs.append(_mid2(uvs[left], uvs[right]))
        new_records.append(
            {
                "newVertexIndex": index,
                "kind": "interior_edge_midpoint_steiner",
                "parentVertexIndices": [left, right],
                "generation": generation,
            }
        )

    new_triangles: list[Tri] = []
    new_lineage: list[list[int]] = []
    for tri, ancestors in zip(triangles, triangle_lineage, strict=True):
        children = _split_triangle(tri, midpoint, new_uvs, desired_sign)
        new_triangles.extend(children)
        new_lineage.extend([list(ancestors) for _ in children])
    return new_vertices, new_uvs, new_triangles, new_records, new_lineage


def _split_triangle(
    tri: Tri, midpoint: dict[tuple[int, int], int], points: list[Vec2], desired_sign: int
) -> list[Tri]:
    a, b, c = tri
    mab = midpoint.get(_edge_key(a, b))
    mbc = midpoint.get(_edge_key(b, c))
    mca = midpoint.get(_edge_key(c, a))
    split_count = sum(value is not None for value in (mab, mbc, mca))
    if split_count == 0:
        return [tri]
    if split_count == 1:
        if mab is not None:
            raw = [(a, mab, c), (mab, b, c)]
        elif mbc is not None:
            raw = [(b, mbc, a), (mbc, c, a)]
        else:
            assert mca is not None
            raw = [(c, mca, b), (mca, a, b)]
    elif split_count == 2:
        if mab is None:
            assert mbc is not None and mca is not None
            raw = [(c, mca, mbc), (a, b, mbc), (a, mbc, mca)]
        elif mbc is None:
            assert mab is not None and mca is not None
            raw = [(a, mab, mca), (b, c, mca), (b, mca, mab)]
        else:
            assert mab is not None and mbc is not None
            raw = [(b, mbc, mab), (c, a, mab), (c, mab, mbc)]
    else:
        assert mab is not None and mbc is not None and mca is not None
        raw = [(a, mab, mca), (mab, b, mbc), (mca, mbc, c), (mab, mbc, mca)]
    return [_oriented_tri(points, *candidate, desired_sign) for candidate in raw]


def _edge_incidence(triangles: list[Tri]) -> dict[tuple[int, int], list[tuple[int, int]]]:
    result: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for triangle_index, tri in enumerate(triangles):
        oriented_edges = (
            (tri[0], tri[1], tri[2]),
            (tri[1], tri[2], tri[0]),
            (tri[2], tri[0], tri[1]),
        )
        for left, right, opposite in oriented_edges:
            result[_edge_key(left, right)].append((triangle_index, opposite))
    return result


def _mesh_edge_counts(triangles: list[Tri]) -> Counter[tuple[int, int]]:
    return Counter(
        _edge_key(left, right)
        for tri in triangles
        for left, right in _triangle_edges(tri)
    )


def _triangle_edges(tri: Tri) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    return ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0]))


def _edge_key(left: int, right: int) -> tuple[int, int]:
    return (left, right) if left < right else (right, left)


def _strict_convex_flip(points: list[Vec2], left: int, right: int, a: int, b: int) -> bool:
    return (
        _orient(points[left], points[right], points[a])
        * _orient(points[left], points[right], points[b])
        < -1e-15
        and _orient(points[a], points[b], points[left])
        * _orient(points[a], points[b], points[right])
        < -1e-15
    )


def _oriented_tri(points: list[Vec2], a: int, b: int, c: int, desired_sign: int) -> Tri:
    tri = (a, b, c)
    return tri if _orientation_sign(points, tri) == desired_sign else (a, c, b)


def _orientation_sign(points: list[Vec2], tri: Tri) -> int:
    value = _orient(points[tri[0]], points[tri[1]], points[tri[2]])
    if abs(value) <= 1e-18:
        raise ValueError("topology_v2_degenerate_triangle")
    return 1 if value > 0.0 else -1


def _minimum_angle(points: list[Vec2], tri: Tri) -> float:
    return min(_triangle_angles(points, tri))


def _triangle_angles(points: list[Vec2], tri: Tri) -> tuple[float, float, float]:
    a, b, c = (points[index] for index in tri)
    lengths = (math.dist(b, c), math.dist(a, c), math.dist(a, b))
    angles: list[float] = []
    for opposite, left, right in (
        (lengths[0], lengths[1], lengths[2]),
        (lengths[1], lengths[0], lengths[2]),
        (lengths[2], lengths[0], lengths[1]),
    ):
        denominator = 2.0 * left * right
        cosine = (left * left + right * right - opposite * opposite) / denominator
        angles.append(math.degrees(math.acos(max(-1.0, min(1.0, cosine)))))
    return angles[0], angles[1], angles[2]


def _triangle_aspect(points: list[Vec2], tri: Tri) -> float:
    lengths = [math.dist(points[left], points[right]) for left, right in _triangle_edges(tri)]
    double_area = abs(_orient(points[tri[0]], points[tri[1]], points[tri[2]]))
    return max(lengths) ** 2 / double_area


def _triangle_centroid(points: list[Vec2], tri: Tri) -> Vec2:
    return (
        sum(points[index][0] for index in tri) / 3.0,
        sum(points[index][1] for index in tri) / 3.0,
    )


def _point_in_polygon(point: Vec2, polygon: list[Vec2]) -> bool:
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if (current[1] > point[1]) != (previous[1] > point[1]):
            crossing = (previous[0] - current[0]) * (point[1] - current[1]) / (
                previous[1] - current[1]
            ) + current[0]
            if point[0] < crossing:
                inside = not inside
        previous = current
    return inside


def _t_junction_count(points: list[Vec2], edges: set[tuple[int, int]]) -> int:
    count = 0
    for left, right in edges:
        a, b = points[left], points[right]
        tolerance = max(math.dist(a, b), 1.0) * 1e-10
        for index, point in enumerate(points):
            if index in {left, right}:
                continue
            if abs(_orient(a, b, point)) <= tolerance and _strictly_between(point, a, b, tolerance):
                count += 1
    return count


def _strictly_between(point: Vec2, a: Vec2, b: Vec2, tolerance: float) -> bool:
    return (
        min(a[0], b[0]) + tolerance < point[0] < max(a[0], b[0]) - tolerance
        or min(a[1], b[1]) + tolerance < point[1] < max(a[1], b[1]) - tolerance
    )


def _panel_scale(points: list[Vec2]) -> float:
    width = max(point[0] for point in points) - min(point[0] for point in points)
    height = max(point[1] for point in points) - min(point[1] for point in points)
    return max(math.hypot(width, height), 1e-9)


def _orient(a: Vec2, b: Vec2, c: Vec2) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _mid2(a: Vec2, b: Vec2) -> Vec2:
    return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)


def _mid3(a: Vec3, b: Vec3) -> Vec3:
    return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5)


def _vec2_canonical(value: Vec2) -> Vec2:
    return (
        round(value[0], TOPOLOGY_V2_CANONICAL_DIGITS),
        round(value[1], TOPOLOGY_V2_CANONICAL_DIGITS),
    )


def _vec3_canonical(value: Vec3) -> Vec3:
    return (
        round(value[0], TOPOLOGY_V2_CANONICAL_DIGITS),
        round(value[1], TOPOLOGY_V2_CANONICAL_DIGITS),
        round(value[2], TOPOLOGY_V2_CANONICAL_DIGITS),
    )


def _hash_document(document: dict[str, Any]) -> str:
    payload = {**document, "integrity": {key: "" for key in document["integrity"]}}
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
