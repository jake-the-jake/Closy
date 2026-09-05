from __future__ import annotations

import math

from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.package_layering_v1.contacts import contacts
from closy_forge.simulation.reference_cloth_solver import flatten_mesh
from closy_forge.simulation.self_collision import build_triangle_refs


def test_empty_mixed_material_query_never_overstates_separation() -> None:
    panels = [
        Mesh(
            name,
            name,
            [(0.0, 0.0, z), (0.1, 0.0, z), (0.0, 0.1, z)],
            [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
            [(0, 1, 2)],
        )
        for name, z in (("a", 0.0), ("b", 0.0035))
    ]
    mesh = MeshSet(panels)
    refs, _ = build_triangle_refs(mesh)
    witnesses, report = contacts(
        flatten_mesh(mesh).positions,
        refs,
        ["a", "b"],
        {"a": (0.001, 0.0), "b": (0.003, 0.001)},
        [],
    )
    assert not witnesses
    assert report["noContactSeparationIsLowerBound"]
    assert report["minimumQueriedSeparationM"] <= 0.0035
    assert math.isclose(report["minimumQueriedSeparationM"], 0.003, abs_tol=1e-12)
