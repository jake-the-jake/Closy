from __future__ import annotations

from pathlib import Path

import pytest

from closy_forge.binding.builder import build_binding
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.manual_provider_c3_v1.states import MOTION_STATES
from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_layering_v1.contacts import contacts
from closy_forge.package_layering_v1.contracts import (
    LayerInputError,
    LayerPackage,
    LayerSpec,
    load_layers,
)
from closy_forge.package_layering_v1.solver import LayerSettings, solve, validate_output
from closy_forge.simulation.self_collision import build_triangle_refs


def mesh(z: float = 0) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                "test",
                "panel.front",
                [(-0.2, 1, z), (0.2, 1, z), (0, 1.4, z)],
                [(0, 0), (1, 0), (0.5, 1)],
                [(0, 1, 2)],
            )
        ]
    )


def test_crossing_far_from_vertices_and_coplanar() -> None:
    a = mesh().meshes[0]
    b = Mesh(
        "cross",
        "panel.second",
        [(0, 1.1, -0.2), (0, 1.1, 0.2), (0, 1.3, 0.2)],
        [(0, 0), (1, 0), (0, 1)],
        [(0, 1, 2)],
    )
    for other, kind in ((b, "triangle_crossing"), (a, "coplanar_overlap")):
        both = MeshSet([a, other])
        refs, _ = build_triangle_refs(both)
        found, summary = contacts(
            [p for m in both.meshes for p in m.vertices],
            refs,
            ["a", "b"],
            {"a": (0.001, 0.001), "b": (0.001, 0.001)},
            [("a", "b", 0, 2, False)],
        )
        assert any(w.kind == kind for w in found)
        assert summary["policyBlockedContacts"] > 0


@pytest.mark.parametrize(
    "order,reason",
    [
        ([("a", "b", 0, 2, True), ("b", "a", 0, 2, True)], "cyclic"),
        ([("a", "c", 0, 2, True)], "missing"),
    ],
)
def test_order_rejected_before_package_reads(tmp_path: Path, order: list, reason: str) -> None:
    with pytest.raises(LayerInputError, match=reason):
        load_layers([LayerSpec("a", tmp_path), LayerSpec("b", tmp_path)], order)


def fixture_layer(name: str, z: float) -> LayerPackage:
    source = mesh(z)
    dense, seeds = subdivide_for_render(source)
    binding, _ = build_binding(source, dense, seeds)
    return LayerPackage(
        LayerSpec(name, Path("unused")),
        {"avatarId": "test", "packageIdentity": name},
        source,
        dense,
        binding,
        {"constraints": [], "openings": []},
        {"collisionPrimitives": []},
    )


def test_clean_solver_serialization_and_tamper(tmp_path: Path) -> None:
    root = tmp_path / "outfit"
    report = solve(
        [fixture_layer("a", -0.1), fixture_layer("b", 0.1)],
        [("a", "b", 0, 2, True)],
        MOTION_STATES[0],
        root,
        settings=LayerSettings(iterations=2),
    )
    assert report["before"]["contactCount"] == 0
    assert report["after"]["renderBindingErrorM"] < 2e-6
    assert report["ready"]
    trusted = sha256_file(root / "manifest.json")
    document = read_json(root / "report.json")
    document["after"]["contactCount"] = 99
    write_canonical_json(root / "report.json", document)
    with pytest.raises(LayerInputError, match="inventory"):
        validate_output(root, trusted_manifest_hash=trusted)


def test_near_parallel_contact_is_actually_corrected(tmp_path: Path) -> None:
    report = solve(
        [fixture_layer("a", 0), fixture_layer("b", 0.0002)],
        [("a", "b", 0, 2, True)],
        MOTION_STATES[0],
        tmp_path / "contact",
    )
    assert report["before"]["contactCount"] > 0
    assert report["after"]["maximumThicknessDeficitM"] < 0.00016
    assert report["after"]["inversions"] == 0
