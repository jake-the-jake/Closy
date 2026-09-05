from __future__ import annotations

import copy
from pathlib import Path

import pytest

from closy_forge.family_integration_v1.compiler import compile_family, validate_family
from closy_forge.family_integration_v1.geometry import FamilyGeometryError, require_glb
from closy_forge.family_integration_v1.registry import FAMILIES, FamilyInputError, family_spec
from closy_forge.family_integration_v1.semantics import validate_semantics
from closy_forge.family_integration_v1.settling import GuardedSettings, guarded_update
from closy_forge.geometry.glb_io import write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet


@pytest.mark.parametrize("spec", FAMILIES, ids=lambda s: s.name)
def test_declared_ranges_and_semantics(spec: object) -> None:
    s = family_spec(spec.name)
    for changes in ({}, *s.variations):
        params = s.parameters(changes)
        pattern = getattr(s.module("pattern_generator"), s.pattern_function)(params)
        semantic = getattr(s.module("semantic_graph"), s.semantic_function)(pattern)
        validate_semantics(s.name, params.to_json(), pattern, semantic)
        broken = copy.deepcopy(pattern)
        broken["panels"][0]["id"] = "panel.forged"
        with pytest.raises(FamilyInputError, match="semantic"):
            validate_semantics(s.name, params.to_json(), broken, semantic)


def test_guard_stops_collapse_and_inversion() -> None:
    old = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    for candidate in (
        [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0)],
    ):
        result, backtracks = guarded_update(old, candidate, [(0, 1, 2)], [0.01])
        assert backtracks > 0
        assert result[1][0] * result[2][1] > 0


def test_decoded_glb_rejects_valid_container_with_zero_area(tmp_path: Path) -> None:
    path = tmp_path / "bad.glb"
    mesh = Mesh(
        "bad",
        "panel.bad",
        [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
        [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
        [(0, 1, 2)],
    )
    write_indexed_glb(path, MeshSet([mesh]), "fabric", (0.2, 0.3, 0.5, 1.0))
    with pytest.raises(FamilyGeometryError):
        require_glb(path)


def test_serialized_package_not_declared_audit_is_authority(tmp_path: Path) -> None:
    output = tmp_path / "skirt"
    audit = compile_family("simple_skirt", output, settings=GuardedSettings(steps=1, iterations=1))
    assert audit["validConventionalGeometry"]
    (output / "audit.json").write_text('{"validConventionalGeometry": false}')
    assert validate_family(output)["validConventionalGeometry"]
    (output / "binding/sim_to_render.bin").write_bytes(b"forged")
    with pytest.raises(FamilyInputError, match="inventory"):
        validate_family(output)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -100.0, True])
def test_invalid_parameters_rejected(value: float) -> None:
    with pytest.raises(FamilyInputError):
        family_spec("tshirt").parameters({"garment_body_length": value})
