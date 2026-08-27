from __future__ import annotations

from math import isfinite
from typing import Any

from closy_forge.geometry.mesh_model import MeshSet, Vec3, add, scale


def span_local_influences(span: dict[str, Any]) -> list[tuple[int, float]]:
    current = int(span["vertexIndex"])
    following = int(span.get("nextVertexIndex", current))
    weight = float(span.get("interpolationWeight", 0.0))
    if not isfinite(weight) or not 0.0 <= weight <= 1.0:
        raise ValueError("seam_interpolation_weight_invalid")
    combined: dict[int, float] = {}
    combined[current] = combined.get(current, 0.0) + 1.0 - weight
    combined[following] = combined.get(following, 0.0) + weight
    return [(index, value) for index, value in sorted(combined.items()) if value > 0.0]


def span_global_influences(
    span: dict[str, Any], mesh_offsets: list[int]
) -> list[tuple[int, float]]:
    offset = mesh_offsets[int(span["meshIndex"])]
    return [(offset + index, weight) for index, weight in span_local_influences(span)]


def span_dominant_local_index(span: dict[str, Any]) -> int:
    influences = span_local_influences(span)
    return min(influences, key=lambda item: (-item[1], item[0]))[0]


def span_dominant_global_index(span: dict[str, Any], mesh_offsets: list[int]) -> int:
    return mesh_offsets[int(span["meshIndex"])] + span_dominant_local_index(span)


def span_position(meshset: MeshSet, span: dict[str, Any]) -> Vec3:
    mesh = meshset.meshes[int(span["meshIndex"])]
    return weighted_position(mesh.vertices, span_local_influences(span))


def span_position_flat(
    positions: list[Vec3], mesh_offsets: list[int], span: dict[str, Any]
) -> Vec3:
    return weighted_position(positions, span_global_influences(span, mesh_offsets))


def weighted_position(positions: list[Vec3], influences: list[tuple[int, float]]) -> Vec3:
    point = (0.0, 0.0, 0.0)
    for index, weight in influences:
        point = add(point, scale(positions[index], weight))
    return point
