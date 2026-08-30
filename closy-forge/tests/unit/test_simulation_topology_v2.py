from __future__ import annotations

from copy import deepcopy

import pytest

from closy_forge.garments.tshirt.assembly import TRANSFORMS
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.geometry.triangulation import panel_boundary_samples
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import topology_hash
from closy_forge.simulation_topology_v2 import build_panel_meshes_v2


def test_topology_v2_preserves_boundary_and_is_deterministic() -> None:
    pattern = build_tshirt_pattern(TShirtParameters())
    first, first_edges, first_manifest = build_panel_meshes_v2(pattern, TRANSFORMS)
    second, second_edges, second_manifest = build_panel_meshes_v2(deepcopy(pattern), TRANSFORMS)

    assert topology_hash(first) == topology_hash(second)
    assert first == second
    assert first_edges == second_edges
    assert canonical_dumps(first_manifest) == canonical_dumps(second_manifest)
    assert first.vertex_count > 218
    assert first.triangle_count > 208
    for panel, mesh in zip(pattern["panels"], first.meshes, strict=True):
        boundary, expected_edges = panel_boundary_samples(panel)
        assert mesh.panel_uvs[: len(boundary)] == boundary
        assert first_edges[panel["id"]] == expected_edges
    assert all(panel["audit"]["status"] == "pass" for panel in first_manifest["panels"])


def test_topology_v2_does_not_mutate_v1_or_accept_invalid_boundary() -> None:
    pattern = build_tshirt_pattern(TShirtParameters())
    snapshot = deepcopy(pattern)
    build_panel_meshes_v2(pattern, TRANSFORMS)
    assert pattern == snapshot

    broken = deepcopy(pattern)
    broken["panels"][0]["boundary"][1]["curve"]["points"][1] = broken["panels"][0][
        "boundary"
    ][0]["curve"]["points"][0]
    with pytest.raises(ValueError, match="invalid panel"):
        build_panel_meshes_v2(broken, TRANSFORMS)
