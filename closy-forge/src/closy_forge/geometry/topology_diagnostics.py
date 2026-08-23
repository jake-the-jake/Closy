from __future__ import annotations

from collections import Counter
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3, cross, mesh_bounds, sub

TOPOLOGY_DIAGNOSTICS_VERSION = "closy.geometry.topology_diagnostics.v1"

_POSITION_TOLERANCE = 1e-6
_AREA_TOLERANCE = 1e-12

VertexKey = tuple[int, int, int]
EdgeKey = tuple[VertexKey, VertexKey]


def meshset_topology_diagnostics(meshset: MeshSet) -> dict[str, Any]:
    mesh_reports = [_mesh_topology_report(mesh) for mesh in meshset.meshes]
    aggregate = _topology_counts(
        [
            vertex
            for mesh in meshset.meshes
            for tri in mesh.triangles
            for vertex in [mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]]]
        ]
    )
    return {
        "schemaVersion": 1,
        "analyzerVersion": TOPOLOGY_DIAGNOSTICS_VERSION,
        "meshCount": len(meshset.meshes),
        "vertexCount": meshset.vertex_count,
        "triangleCount": meshset.triangle_count,
        "bounds": mesh_bounds(meshset),
        "componentCount": aggregate["componentCount"],
        "largestComponentTriangleCount": aggregate["largestComponentTriangleCount"],
        "boundaryEdgeCount": aggregate["boundaryEdgeCount"],
        "nonManifoldEdgeCount": aggregate["nonManifoldEdgeCount"],
        "degenerateTriangleCount": aggregate["degenerateTriangleCount"],
        "duplicatePositionCount": _duplicate_position_count(
            [vertex for mesh in meshset.meshes for vertex in mesh.vertices]
        ),
        "manifoldStatus": _manifold_status(
            aggregate["triangleCount"],
            aggregate["boundaryEdgeCount"],
            aggregate["nonManifoldEdgeCount"],
        ),
        "meshes": mesh_reports,
    }


def _mesh_topology_report(mesh: Mesh) -> dict[str, Any]:
    counts = _topology_counts(
        [
            vertex
            for tri in mesh.triangles
            for vertex in [mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]]]
        ]
    )
    meshset = MeshSet([mesh])
    return {
        "meshName": mesh.name,
        "panelId": mesh.panel_id,
        "vertexCount": len(mesh.vertices),
        "triangleCount": len(mesh.triangles),
        "bounds": mesh_bounds(meshset),
        "componentCount": counts["componentCount"],
        "largestComponentTriangleCount": counts["largestComponentTriangleCount"],
        "boundaryEdgeCount": counts["boundaryEdgeCount"],
        "nonManifoldEdgeCount": counts["nonManifoldEdgeCount"],
        "degenerateTriangleCount": counts["degenerateTriangleCount"],
        "duplicatePositionCount": _duplicate_position_count(mesh.vertices),
        "manifoldStatus": _manifold_status(
            counts["triangleCount"],
            counts["boundaryEdgeCount"],
            counts["nonManifoldEdgeCount"],
        ),
    }


def _topology_counts(triangle_vertices: list[Vec3]) -> dict[str, int]:
    triangle_count = len(triangle_vertices) // 3
    parent = list(range(triangle_count))
    rank = [0 for _ in range(triangle_count)]
    edge_counts: Counter[EdgeKey] = Counter()
    first_triangle_for_vertex: dict[VertexKey, int] = {}
    degenerate_count = 0

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if rank[left_root] < rank[right_root]:
            parent[left_root] = right_root
        elif rank[left_root] > rank[right_root]:
            parent[right_root] = left_root
        else:
            parent[right_root] = left_root
            rank[left_root] += 1

    for tri_index in range(triangle_count):
        tri_vertices = [
            triangle_vertices[tri_index * 3],
            triangle_vertices[tri_index * 3 + 1],
            triangle_vertices[tri_index * 3 + 2],
        ]
        keys = [_vertex_key(vertex) for vertex in tri_vertices]
        if len(set(keys)) != 3 or _triangle_area2(tri_vertices) <= _AREA_TOLERANCE:
            degenerate_count += 1
        for key in keys:
            previous = first_triangle_for_vertex.get(key)
            if previous is None:
                first_triangle_for_vertex[key] = tri_index
            else:
                union(previous, tri_index)
        for left, right in [(keys[0], keys[1]), (keys[1], keys[2]), (keys[2], keys[0])]:
            edge_counts[_edge_key(left, right)] += 1

    component_sizes: Counter[int] = Counter(find(index) for index in range(triangle_count))
    return {
        "triangleCount": triangle_count,
        "componentCount": len(component_sizes),
        "largestComponentTriangleCount": max(component_sizes.values(), default=0),
        "boundaryEdgeCount": sum(1 for count in edge_counts.values() if count == 1),
        "nonManifoldEdgeCount": sum(1 for count in edge_counts.values() if count > 2),
        "degenerateTriangleCount": degenerate_count,
    }


def _duplicate_position_count(vertices: list[Vec3]) -> int:
    keys = [_vertex_key(vertex) for vertex in vertices]
    return len(keys) - len(set(keys))


def _vertex_key(vertex: Vec3) -> VertexKey:
    return (
        round(vertex[0] / _POSITION_TOLERANCE),
        round(vertex[1] / _POSITION_TOLERANCE),
        round(vertex[2] / _POSITION_TOLERANCE),
    )


def _edge_key(left: VertexKey, right: VertexKey) -> EdgeKey:
    return (left, right) if left <= right else (right, left)


def _triangle_area2(vertices: list[Vec3]) -> float:
    normal = cross(sub(vertices[1], vertices[0]), sub(vertices[2], vertices[0]))
    return sum(value * value for value in normal)


def _manifold_status(triangle_count: int, boundary_edges: int, non_manifold_edges: int) -> str:
    if triangle_count == 0:
        return "no_triangles"
    if non_manifold_edges > 0:
        return "non_manifold"
    if boundary_edges > 0:
        return "open_surface_with_boundaries"
    return "closed_manifold"
