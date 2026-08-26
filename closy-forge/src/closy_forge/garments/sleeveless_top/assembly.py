from __future__ import annotations

from typing import Any

from closy_forge.garments.assembly import build_panel_meshes, build_seam_constraints
from closy_forge.geometry.mesh_model import MeshSet

TRANSFORMS = {
    "panel.sleeveless_top.front": "front",
    "panel.sleeveless_top.back": "back",
}


def build_simulation_mesh(
    pattern: dict[str, Any],
) -> tuple[MeshSet, dict[str, dict[str, list[int]]]]:
    return build_panel_meshes(pattern, TRANSFORMS)


def build_constraints(
    pattern: dict[str, Any], edge_maps: dict[str, dict[str, list[int]]]
) -> dict[str, Any]:
    return build_seam_constraints(pattern, edge_maps)
