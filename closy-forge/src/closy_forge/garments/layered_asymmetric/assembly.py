from __future__ import annotations

from typing import Any

from closy_forge.garments.assembly import build_panel_meshes, build_seam_constraints
from closy_forge.geometry.mesh_model import MeshSet

TRANSFORMS = {
    "panel.layered_asymmetric.inner.front": "layered.inner.front",
    "panel.layered_asymmetric.inner.back": "layered.inner.back",
    "panel.layered_asymmetric.outer.front": "layered.outer.front",
    "panel.layered_asymmetric.outer.back": "layered.outer.back",
}
CANONICAL_GEOMETRY_DIGITS = 12


def build_simulation_mesh(
    pattern: dict[str, Any],
) -> tuple[MeshSet, dict[str, dict[str, list[int]]]]:
    return build_panel_meshes(
        pattern,
        TRANSFORMS,
        canonical_digits=CANONICAL_GEOMETRY_DIGITS,
    )


def build_constraints(
    pattern: dict[str, Any], edge_maps: dict[str, dict[str, list[int]]]
) -> dict[str, Any]:
    return build_seam_constraints(pattern, edge_maps)
