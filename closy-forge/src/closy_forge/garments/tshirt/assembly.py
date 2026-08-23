from __future__ import annotations

from typing import Any

from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.geometry.triangulation import triangulate_panel

TRANSFORMS = {
    "panel.front": "front",
    "panel.back": "back",
    "panel.sleeve.left": "sleeve.left",
    "panel.sleeve.right": "sleeve.right",
    "panel.neck_band": "neck_band",
}


def build_simulation_mesh(
    pattern: dict[str, Any],
) -> tuple[MeshSet, dict[str, dict[str, list[int]]]]:
    meshes = []
    edge_maps: dict[str, dict[str, list[int]]] = {}
    for panel in pattern["panels"]:
        mesh, edges = triangulate_panel(panel, TRANSFORMS[panel["id"]])
        edge_maps[panel["id"]] = edges
        meshes.append(mesh)
    return MeshSet(meshes), edge_maps


def build_constraints(
    pattern: dict[str, Any], edge_maps: dict[str, dict[str, list[int]]]
) -> dict[str, Any]:
    constraints = []
    mesh_panel_index = {panel["id"]: i for i, panel in enumerate(pattern["panels"])}
    for seam in pattern["seams"]:
        spans = seam["spans"]
        if len(spans) < 2:
            continue
        base = _span_vertices(spans[0], edge_maps)
        for other_span in spans[1:]:
            other = _span_vertices(other_span, edge_maps)
            count = min(len(base), len(other))
            for ordinal in range(count):
                a = base[ordinal]
                b = other[ordinal]
                constraints.append(
                    {
                        "id": f"constraint.{seam['id']}.{ordinal:03d}",
                        "schemaVersion": 1,
                        "seamId": seam["id"],
                        "spanA": {
                            "panelId": spans[0]["panelId"],
                            "boundaryId": spans[0]["edgeId"],
                            "vertexIndex": a,
                            "meshIndex": mesh_panel_index[spans[0]["panelId"]],
                        },
                        "spanB": {
                            "panelId": other_span["panelId"],
                            "boundaryId": other_span["edgeId"],
                            "vertexIndex": b,
                            "meshIndex": mesh_panel_index[other_span["panelId"]],
                        },
                        "orientation": [spans[0]["orientation"], other_span["orientation"]],
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
        "derivableFutureConstraints": ["stretch", "shear", "bending"],
    }


def _span_vertices(span: dict[str, str], edge_maps: dict[str, dict[str, list[int]]]) -> list[int]:
    ids = list(edge_maps[span["panelId"]][span["edgeId"]])
    if span["orientation"] == "reverse":
        ids.reverse()
    return ids
