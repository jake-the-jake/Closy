from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.geometry.triangulation import triangulate_panel


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


def canonicalize_meshset(meshset: MeshSet, digits: int | None) -> MeshSet:
    return MeshSet([canonicalize_mesh(mesh, digits) for mesh in meshset.meshes])


def canonicalize_mesh(mesh: Mesh, digits: int | None) -> Mesh:
    if digits is None:
        return mesh
    if not 0 <= digits <= 15:
        raise ValueError("canonical_digits must be between 0 and 15")
    return Mesh(
        name=mesh.name,
        panel_id=mesh.panel_id,
        vertices=[
            (
                round(float(vertex[0]), digits),
                round(float(vertex[1]), digits),
                round(float(vertex[2]), digits),
            )
            for vertex in mesh.vertices
        ],
        panel_uvs=[
            (round(float(uv[0]), digits), round(float(uv[1]), digits)) for uv in mesh.panel_uvs
        ],
        triangles=mesh.triangles,
        material_id=mesh.material_id,
    )


def build_seam_constraints(
    pattern: dict[str, Any], edge_maps: dict[str, dict[str, list[int]]]
) -> dict[str, Any]:
    constraints = []
    mesh_panel_index = {panel["id"]: i for i, panel in enumerate(pattern["panels"])}
    for seam in pattern["seams"]:
        if seam.get("simulationEnabled", True) is False:
            continue
        spans = seam["spans"]
        if len(spans) < 2:
            continue
        base = _span_vertices(spans[0], edge_maps)
        for other_span in spans[1:]:
            other = _span_vertices(other_span, edge_maps)
            count = min(len(base), len(other))
            for ordinal in range(count):
                constraints.append(
                    {
                        "id": f"constraint.{seam['id']}.{ordinal:03d}",
                        "schemaVersion": 1,
                        "seamId": seam["id"],
                        "spanA": _constraint_span_payload(
                            spans[0], base[ordinal], mesh_panel_index[spans[0]["panelId"]]
                        ),
                        "spanB": _constraint_span_payload(
                            other_span,
                            other[ordinal],
                            mesh_panel_index[other_span["panelId"]],
                        ),
                        "orientation": [
                            spans[0]["orientation"],
                            other_span["orientation"],
                        ],
                        "restEaseRatio": seam["easeRatio"],
                        "stitchType": seam["stitchType"],
                        "enabled": True,
                        "provenance": "procedural_fixture",
                        "validationStatus": "unchecked_until_package_validation",
                    }
                )
    return {
        "schemaVersion": 1,
        "constraintModel": "seam_pairs_v1",
        "constraints": constraints,
        "seams": [
            {
                "id": str(seam["id"]),
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


def _constraint_span_payload(
    span: dict[str, Any], vertex_index: int, mesh_index: int
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "panelId": span["panelId"],
        "boundaryId": span["edgeId"],
        "vertexIndex": vertex_index,
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
    if span["orientation"] == "reverse":
        ids.reverse()
    return ids


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
