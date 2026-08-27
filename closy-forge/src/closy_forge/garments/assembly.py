from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.geometry.triangulation import panel_boundary_samples, triangulate_panel


def build_panel_meshes(
    pattern: dict[str, Any],
    transforms: Mapping[str, str],
    *,
    canonical_digits: int | None = None,
) -> tuple[MeshSet, dict[str, dict[str, list[int]]]]:
    """Triangulate a garment family without introducing generic-object semantics."""

    meshes = []
    edge_maps: dict[str, dict[str, list[int]]] = {}
    for panel in pattern["panels"]:
        panel_id = str(panel["id"])
        transform = transforms.get(panel_id)
        if transform is None:
            raise ValueError(f"missing panel transform: {panel_id}")
        mesh, edges = triangulate_panel(panel, transform)
        mesh = canonicalize_mesh(mesh, canonical_digits)
        edge_maps[panel_id] = edges
        meshes.append(mesh)
    return MeshSet(meshes), edge_maps


def canonicalize_meshset(
    meshset: MeshSet, digits: int | None, *, normalize_signed_zero: bool = False
) -> MeshSet:
    return MeshSet(
        [
            canonicalize_mesh(mesh, digits, normalize_signed_zero=normalize_signed_zero)
            for mesh in meshset.meshes
        ]
    )


def canonicalize_mesh(
    mesh: Mesh, digits: int | None, *, normalize_signed_zero: bool = False
) -> Mesh:
    if digits is None:
        return mesh
    if not 0 <= digits <= 15:
        raise ValueError("canonical_digits must be between 0 and 15")
    return Mesh(
        name=mesh.name,
        panel_id=mesh.panel_id,
        vertices=[
            (
                _canonical_number(vertex[0], digits, normalize_signed_zero),
                _canonical_number(vertex[1], digits, normalize_signed_zero),
                _canonical_number(vertex[2], digits, normalize_signed_zero),
            )
            for vertex in mesh.vertices
        ],
        panel_uvs=[
            (
                _canonical_number(uv[0], digits, normalize_signed_zero),
                _canonical_number(uv[1], digits, normalize_signed_zero),
            )
            for uv in mesh.panel_uvs
        ],
        triangles=mesh.triangles,
        material_id=mesh.material_id,
    )


def _canonical_number(value: float, digits: int, normalize_signed_zero: bool) -> float:
    canonical = round(float(value), digits)
    return 0.0 if normalize_signed_zero and canonical == 0.0 else canonical


def build_seam_constraints(
    pattern: dict[str, Any], edge_maps: dict[str, dict[str, list[int]]]
) -> dict[str, Any]:
    constraints = []
    mesh_panel_index = {panel["id"]: i for i, panel in enumerate(pattern["panels"])}
    panel_points = {
        str(panel["id"]): panel_boundary_samples(panel)[0] for panel in pattern["panels"]
    }
    for seam in pattern["seams"]:
        if seam.get("simulationEnabled", True) is False:
            continue
        spans = seam["spans"]
        if len(spans) < 2:
            continue
        base = _span_vertices(spans[0], edge_maps)
        for pair_index, other_span in enumerate(spans[1:], start=1):
            other = _span_vertices(other_span, edge_maps)
            if len(base) < 2 or len(other) < 2:
                raise ValueError(f"invalid seam span: {seam['id']}")
            other, correspondence_direction = _orient_span_for_correspondence(
                base,
                other,
                panel_points[str(spans[0]["panelId"])],
                panel_points[str(other_span["panelId"])],
            )
            base_parameters = _normalised_arc_parameters(
                [panel_points[str(spans[0]["panelId"])][index] for index in base]
            )
            other_parameters = _normalised_arc_parameters(
                [panel_points[str(other_span["panelId"])][index] for index in other]
            )
            count = max(len(base), len(other))
            for ordinal in range(count):
                parameter = ordinal / (count - 1)
                base_index, base_next_index, base_weight = _parameterised_span_sample(
                    base_parameters, parameter
                )
                other_index, other_next_index, other_weight = _parameterised_span_sample(
                    other_parameters, parameter
                )
                constraints.append(
                    {
                        "id": (
                            f"constraint.{seam['id']}.{ordinal:03d}"
                            if pair_index == 1
                            else f"constraint.{seam['id']}.pair{pair_index:03d}.{ordinal:03d}"
                        ),
                        "schemaVersion": 1,
                        "seamId": seam["id"],
                        "spanA": _constraint_span_payload(
                            spans[0],
                            base[base_index],
                            mesh_panel_index[spans[0]["panelId"]],
                            next_vertex_index=base[base_next_index],
                            interpolation_weight=base_weight,
                        ),
                        "spanB": _constraint_span_payload(
                            other_span,
                            other[other_index],
                            mesh_panel_index[other_span["panelId"]],
                            next_vertex_index=other[other_next_index],
                            interpolation_weight=other_weight,
                        ),
                        "orientation": [
                            spans[0]["orientation"],
                            other_span["orientation"],
                        ],
                        "restEaseRatio": seam["easeRatio"],
                        "easeDistribution": "normalised_arc_length_uniform_v1",
                        "mapping": {
                            "mappingCount": count,
                            "ordinal": ordinal,
                            "parameter": parameter,
                            "spanAParameter": parameter,
                            "spanAVertexCount": len(base),
                            "spanBParameter": parameter,
                            "spanBVertexCount": len(other),
                            "spanBCorrespondenceDirection": correspondence_direction,
                        },
                        "stitchType": seam["stitchType"],
                        "enabled": True,
                        "provenance": "procedural_fixture",
                        "validationStatus": "unchecked_until_package_validation",
                    }
                )
    return {
        "schemaVersion": 1,
        "constraintModel": "full_span_seam_mapping_v2",
        "constraints": constraints,
        "seams": [
            {
                "id": str(seam["id"]),
                "easeRatio": float(seam["easeRatio"]),
                "mappingVersion": "closy.full_span_seam_mapping.v2",
                "spans": [
                    {
                        "panelId": str(span["panelId"]),
                        "edgeId": str(span["edgeId"]),
                        "orientation": str(span["orientation"]),
                        **(
                            {"sampleRange": list(span["sampleRange"])}
                            if "sampleRange" in span
                            else {}
                        ),
                        **(
                            {"partitionId": str(span["partitionId"])}
                            if "partitionId" in span
                            else {}
                        ),
                    }
                    for span in seam.get("spans", [])
                ],
            }
            for seam in pattern["seams"]
            if seam.get("simulationEnabled", True) is not False
        ],
        "openings": _opening_span_payloads(pattern, edge_maps, mesh_panel_index),
        "derivableFutureConstraints": ["stretch", "shear", "bending"],
    }


def _normalised_arc_parameters(points: list[tuple[float, float]]) -> list[float]:
    if len(points) < 2:
        raise ValueError("seam_span_requires_two_vertices")
    cumulative = [0.0]
    for left, right in zip(points, points[1:], strict=False):
        cumulative.append(cumulative[-1] + math.dist(left, right))
    if cumulative[-1] <= 1e-12:
        raise ValueError("seam_span_zero_arc_length")
    return [distance / cumulative[-1] for distance in cumulative]


def _parameterised_span_sample(parameters: list[float], parameter: float) -> tuple[int, int, float]:
    if parameter <= 0.0:
        return 0, 0, 0.0
    if parameter >= 1.0:
        final = len(parameters) - 1
        return final, final, 0.0
    for right in range(1, len(parameters)):
        if parameters[right] >= parameter:
            if abs(parameters[right] - parameter) <= 1e-12:
                return right, right, 0.0
            left = right - 1
            extent = parameters[right] - parameters[left]
            if extent <= 1e-12:
                raise ValueError("seam_span_parameter_interval_zero")
            return left, right, (parameter - parameters[left]) / extent
    raise ValueError("seam_span_parameter_out_of_range")


def _constraint_span_payload(
    span: dict[str, Any],
    vertex_index: int,
    mesh_index: int,
    *,
    next_vertex_index: int,
    interpolation_weight: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "panelId": span["panelId"],
        "boundaryId": span["edgeId"],
        "vertexIndex": vertex_index,
        "nextVertexIndex": next_vertex_index,
        "interpolationWeight": interpolation_weight,
        "meshIndex": mesh_index,
    }
    if "sampleRange" in span:
        payload["sampleRange"] = list(span["sampleRange"])
    if "partitionId" in span:
        payload["partitionId"] = span["partitionId"]
    return payload


def _span_vertices(span: dict[str, Any], edge_maps: dict[str, dict[str, list[int]]]) -> list[int]:
    ids = list(edge_maps[span["panelId"]][span["edgeId"]])
    if "sampleRange" in span:
        start, end = span["sampleRange"]
        ids = ids[int(start) : int(end)]
    return ids


def _orient_span_for_correspondence(
    base: list[int],
    other: list[int],
    base_points: list[tuple[float, float]],
    other_points: list[tuple[float, float]],
) -> tuple[list[int], str]:
    direct = math.dist(base_points[base[0]], other_points[other[0]]) + math.dist(
        base_points[base[-1]], other_points[other[-1]]
    )
    reverse = math.dist(base_points[base[0]], other_points[other[-1]]) + math.dist(
        base_points[base[-1]], other_points[other[0]]
    )
    if reverse + 1e-12 < direct:
        return list(reversed(other)), "reversed_by_endpoint_correspondence"
    return other, "forward_by_endpoint_correspondence"


def _opening_span_payloads(
    pattern: dict[str, Any],
    edge_maps: dict[str, dict[str, list[int]]],
    mesh_panel_index: dict[str, int],
) -> list[dict[str, Any]]:
    edge_to_panel: dict[str, str] = {}
    for panel in pattern["panels"]:
        panel_id = str(panel["id"])
        for edge in panel.get("boundary", []):
            edge_to_panel[str(edge["id"])] = panel_id

    payloads: list[dict[str, Any]] = []
    for opening in pattern["openings"]:
        boundary_edges: list[dict[str, Any]] = []
        for edge_id in opening.get("boundaryEdges", []):
            edge_key = str(edge_id)
            resolved_panel_id = edge_to_panel.get(edge_key)
            if resolved_panel_id is None:
                boundary_edges.append({"edgeId": edge_key, "status": "missing_panel_edge"})
                continue
            vertex_indices = [int(index) for index in edge_maps[resolved_panel_id][edge_key]]
            boundary_edges.append(
                {
                    "edgeId": edge_key,
                    "panelId": resolved_panel_id,
                    "meshIndex": int(mesh_panel_index[resolved_panel_id]),
                    "vertexIndices": vertex_indices,
                    "vertexCount": len(vertex_indices),
                    "status": "resolved",
                }
            )
        payloads.append(
            {
                "id": str(opening["id"]),
                "status": str(opening.get("status", "unknown")),
                "boundaryEdges": boundary_edges,
            }
        )
    return payloads
