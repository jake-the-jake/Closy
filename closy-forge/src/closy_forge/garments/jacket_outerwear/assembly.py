from __future__ import annotations

from typing import Any

from closy_forge.garments.assembly import (
    build_panel_meshes,
    build_seam_constraints,
    canonicalize_meshset,
)
from closy_forge.geometry.mesh_model import MeshSet

TRANSFORMS = {
    "panel.jacket_outerwear.front.left": "front",
    "panel.jacket_outerwear.front.right": "front",
    "panel.jacket_outerwear.back": "back",
    "panel.jacket_outerwear.sleeve.left": "sleeve.left",
    "panel.jacket_outerwear.sleeve.right": "sleeve.right",
    "panel.jacket_outerwear.facing.left": "jacket.facing.left",
    "panel.jacket_outerwear.facing.right": "jacket.facing.right",
}
CANONICAL_GEOMETRY_DIGITS = 12


def build_simulation_mesh(
    pattern: dict[str, Any],
) -> tuple[MeshSet, dict[str, dict[str, list[int]]]]:
    meshset, edge_maps = build_panel_meshes(
        pattern,
        TRANSFORMS,
        canonical_digits=CANONICAL_GEOMETRY_DIGITS,
    )
    return (
        canonicalize_meshset(
            meshset,
            CANONICAL_GEOMETRY_DIGITS,
            normalize_signed_zero=True,
        ),
        edge_maps,
    )


def build_constraints(
    pattern: dict[str, Any], edge_maps: dict[str, dict[str, list[int]]]
) -> dict[str, Any]:
    return build_seam_constraints(pattern, edge_maps)
