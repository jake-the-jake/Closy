from __future__ import annotations

from math import sqrt
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3, mesh_bounds


def evaluate_independent_surface_agreement(
    dense: MeshSet,
    fallback: MeshSet,
    *,
    constraints: dict[str, Any],
    binding_contract: dict[str, Any],
) -> dict[str, Any]:
    """Compare two independently reconstructed surfaces without vertex-order assumptions."""

    dense_by_panel = _unique_panel_meshes(dense)
    fallback_by_panel = _unique_panel_meshes(fallback)
    shared = sorted(set(dense_by_panel) & set(fallback_by_panel))
    if not shared:
        raise ValueError("dense_fallback_no_shared_panels")

    area_centroid_deltas: dict[str, float] = {}
    sampled_surface_distances: dict[str, float] = {}
    landmark_deltas: dict[str, float] = {}
    for panel_id in shared:
        dense_panel = dense_by_panel[panel_id]
        fallback_panel = fallback_by_panel[panel_id]
        area_centroid_deltas[panel_id] = _round(
            _distance(
                _area_weighted_surface_centroid(dense_panel),
                _area_weighted_surface_centroid(fallback_panel),
            )
        )
        sampled_surface_distances[panel_id] = _round(
            _symmetric_sampled_surface_distance(dense_panel, fallback_panel)
        )
        landmark_deltas[panel_id] = _round(_semantic_landmark_delta(dense_panel, fallback_panel))

    dense_bounds = mesh_bounds(dense)
    fallback_bounds = mesh_bounds(fallback)
    scale = max(max(float(value) for value in dense_bounds["size"]), 1e-9)
    bounds_delta = max(
        abs(float(left) - float(right)) / scale
        for key in ("min", "max")
        for left, right in zip(dense_bounds[key], fallback_bounds[key], strict=True)
    )
    source_to_dense = _source_to_dense_vertex_map(dense, binding_contract)
    fallback_positions = [point for mesh in fallback.meshes for point in mesh.vertices]
    offsets = _offsets(fallback)
    opening_landmarks = _constraint_landmark_delta(
        constraints.get("openings", []),
        source_to_dense,
        fallback_positions,
        offsets,
        "boundaryEdges",
    )
    seam_landmarks = _constraint_landmark_delta(
        constraints.get("constraints", []), source_to_dense, fallback_positions, offsets, "spans"
    )

    return {
        "metricVersion": "closy.c3_independent_surface_agreement.v1",
        "comparisonKind": (
            "independent_area_weighted_surface_centroid_bounds_sampled_surface_"
            "and_semantic_landmarks"
        ),
        "fallbackCallsDensePath": False,
        "vertexOrderCompared": False,
        "denseVertexCount": dense.vertex_count,
        "fallbackVertexCount": fallback.vertex_count,
        "sharedPanelIds": shared,
        "panelAreaWeightedCentroidDeltasMeters": area_centroid_deltas,
        "maxAreaWeightedCentroidDeltaMeters": max(area_centroid_deltas.values(), default=0.0),
        "panelSampledSurfaceDistancesMeters": sampled_surface_distances,
        "maxSampledSurfaceDistanceMeters": max(sampled_surface_distances.values(), default=0.0),
        "panelSemanticLandmarkDeltasMeters": landmark_deltas,
        "maxSemanticLandmarkDeltaMeters": max(landmark_deltas.values(), default=0.0),
        "openingLandmarkDeltaMeters": _round(opening_landmarks),
        "seamPathLandmarkDeltaMeters": _round(seam_landmarks),
        "silhouetteBoundsDeltaNormalised": _round(bounds_delta),
    }


def unweighted_vertex_centroid(mesh: Mesh) -> Vec3:
    """Legacy metric retained only for adversarial regression tests."""

    count = max(1, len(mesh.vertices))
    return tuple(sum(point[axis] for point in mesh.vertices) / count for axis in range(3))  # type: ignore[return-value]


def _unique_panel_meshes(meshset: MeshSet) -> dict[str, Mesh]:
    result: dict[str, Mesh] = {}
    for mesh in meshset.meshes:
        if mesh.panel_id in result:
            raise ValueError(f"duplicate_panel_mesh:{mesh.panel_id}")
        result[mesh.panel_id] = mesh
    return result


def _area_weighted_surface_centroid(mesh: Mesh) -> Vec3:
    weighted = [0.0, 0.0, 0.0]
    total_area = 0.0
    for triangle in mesh.triangles:
        a, b, c = (mesh.vertices[index] for index in triangle)
        area = _triangle_area(a, b, c)
        if area <= 1e-15:
            continue
        center = (
            (a[0] + b[0] + c[0]) / 3.0,
            (a[1] + b[1] + c[1]) / 3.0,
            (a[2] + b[2] + c[2]) / 3.0,
        )
        total_area += area
        for axis in range(3):
            weighted[axis] += center[axis] * area
    if total_area <= 1e-15:
        raise ValueError(f"zero_area_panel:{mesh.panel_id}")
    return (weighted[0] / total_area, weighted[1] / total_area, weighted[2] / total_area)


def _symmetric_sampled_surface_distance(left: Mesh, right: Mesh) -> float:
    return max(
        _one_way_sampled_surface_distance(left, right),
        _one_way_sampled_surface_distance(right, left),
    )


def _one_way_sampled_surface_distance(source: Mesh, target: Mesh) -> float:
    target_triangles = [tuple(target.vertices[index] for index in tri) for tri in target.triangles]
    if not target_triangles:
        raise ValueError(f"target_panel_has_no_triangles:{target.panel_id}")
    samples = list(source.vertices)
    samples.extend(
        (
            sum(source.vertices[index][0] for index in tri) / 3.0,
            sum(source.vertices[index][1] for index in tri) / 3.0,
            sum(source.vertices[index][2] for index in tri) / 3.0,
        )
        for tri in source.triangles
    )
    stride = max(1, len(samples) // 256)
    selected = samples[::stride]
    if selected[-1] != samples[-1]:
        selected.append(samples[-1])
    return max(
        min(
            _distance(point, _closest_point_on_triangle(point, *triangle))
            for triangle in target_triangles
        )
        for point in selected
    )


def _semantic_landmark_delta(left: Mesh, right: Mesh) -> float:
    left_landmarks = _axis_landmarks(left.vertices)
    right_landmarks = _axis_landmarks(right.vertices)
    return max(
        _distance(left_landmarks[key], right_landmarks[key]) for key in sorted(left_landmarks)
    )


def _axis_landmarks(points: list[Vec3]) -> dict[str, Vec3]:
    result: dict[str, Vec3] = {}
    for axis, name in enumerate(("x", "y", "z")):
        result[f"{name}Min"] = min(points, key=lambda point: (point[axis], point))
        result[f"{name}Max"] = max(points, key=lambda point: (point[axis], point))
    return result


def _source_to_dense_vertex_map(dense: MeshSet, contract: dict[str, Any]) -> dict[int, Vec3]:
    dense_positions = [point for mesh in dense.meshes for point in mesh.vertices]
    candidates: dict[int, list[tuple[float, int]]] = {}
    for record in contract.get("records", []):
        render_index = int(record["globalRenderVertexIndex"])
        source_indices = record["sourceTriangle"]["globalVertexIndices"]
        weights = record["binding"]["weights"]
        for source_index, weight in zip(source_indices, weights, strict=True):
            candidates.setdefault(int(source_index), []).append((float(weight), render_index))
    result: dict[int, Vec3] = {}
    for source_index, weighted in candidates.items():
        _, render_index = max(weighted, key=lambda item: (item[0], -item[1]))
        result[source_index] = dense_positions[render_index]
    return result


def _constraint_landmark_delta(
    records: list[dict[str, Any]],
    source_to_dense: dict[int, Vec3],
    fallback_positions: list[Vec3],
    offsets: list[int],
    kind: str,
) -> float:
    source_indices: set[int] = set()
    if kind == "boundaryEdges":
        for record in records:
            for edge in record.get("boundaryEdges", []):
                if edge.get("status") != "resolved":
                    continue
                offset = offsets[int(edge["meshIndex"])]
                source_indices.update(offset + int(index) for index in edge["vertexIndices"])
    else:
        for record in records:
            for key in ("spanA", "spanB"):
                span = record.get(key, {})
                offset = offsets[int(span["meshIndex"])]
                source_indices.add(offset + int(span["vertexIndex"]))
                source_indices.add(offset + int(span.get("nextVertexIndex", span["vertexIndex"])))
    distances = [
        _distance(source_to_dense[index], fallback_positions[index])
        for index in sorted(source_indices)
        if index in source_to_dense
    ]
    return max(distances, default=0.0)


def _offsets(meshset: MeshSet) -> list[int]:
    offsets: list[int] = []
    current = 0
    for mesh in meshset.meshes:
        offsets.append(current)
        current += len(mesh.vertices)
    return offsets


def _triangle_area(a: Vec3, b: Vec3, c: Vec3) -> float:
    ab = _sub(b, a)
    ac = _sub(c, a)
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return 0.5 * sqrt(_dot(cross, cross))


def _closest_point_on_triangle(point: Vec3, a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    ab = _sub(b, a)
    ac = _sub(c, a)
    ap = _sub(point, a)
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


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(value: Vec3, factor: float) -> Vec3:
    return (value[0] * factor, value[1] * factor, value[2] * factor)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _distance(a: Vec3, b: Vec3) -> float:
    delta = _sub(a, b)
    return sqrt(_dot(delta, delta))


def _round(value: float) -> float:
    return round(float(value), 9)
