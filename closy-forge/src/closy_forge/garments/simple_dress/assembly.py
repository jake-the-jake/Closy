from __future__ import annotations

from typing import Any

from closy_forge.garments.assembly import (
    build_panel_meshes,
    build_seam_constraints,
    canonicalize_meshset,
)
from closy_forge.geometry.mesh_model import MeshSet

TRANSFORMS = {
    f"panel.simple_dress.{face}.bodice": f"dress.bodice.{face}" for face in ("front", "back")
} | {f"panel.simple_dress.{face}.skirt": f"dress.skirt.{face}" for face in ("front", "back")}
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
