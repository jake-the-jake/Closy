from __future__ import annotations

from closy_forge.binding.binary_format import read_binding, write_binding
from closy_forge.binding.builder import build_binding
from closy_forge.binding.reconstruct import (
    perturb_simulation_vertices,
    reconstruct_vertices,
    reconstruction_error,
)
from closy_forge.garments.tshirt.assembly import build_simulation_mesh
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.package_io.paths import validate_package_relpath


def test_binding_round_trip_and_reconstruction(tmp_path) -> None:  # type: ignore[no-untyped-def]
    pattern = build_tshirt_pattern(TShirtParameters())
    simulation_mesh, _ = build_simulation_mesh(pattern)
    render_mesh, seeds = subdivide_for_render(simulation_mesh)
    binding, manifest = build_binding(simulation_mesh, render_mesh, seeds)
    path = tmp_path / "sim_to_render.bin"
    write_binding(path, binding)
    loaded = read_binding(path)
    assert loaded.simulation_topology_hash == manifest["simulationTopologyHash"]
    reconstructed = reconstruct_vertices(simulation_mesh, loaded)
    max_error, rms_error = reconstruction_error(render_mesh, reconstructed)
    assert max_error == 0.0
    assert rms_error == 0.0
    moved = reconstruct_vertices(perturb_simulation_vertices(simulation_mesh), loaded)
    assert moved != reconstructed


def test_package_relative_path_safety() -> None:
    validate_package_relpath("avatar/avatar_contract.json")
    for bad in ["../escape.json", "/absolute.json", "avatar\\windows.json", ""]:
        try:
            validate_package_relpath(bad)
        except ValueError:
            continue
        raise AssertionError(f"unsafe path accepted: {bad}")
