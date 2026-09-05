from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.binding.binary_format import read_binding, write_binding
from closy_forge.binding.builder import build_binding
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.geometry.glb_io import read_glb_meshset, write_indexed_glb
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)
from closy_forge.package_io.paths import validate_package_relpath
from closy_forge.simulation.reference_cloth_solver import flatten_mesh

from .geometry import FamilyGeometryError, require_glb, require_mesh
from .registry import FamilyInputError, family_spec
from .semantics import boundary_metrics, validate_semantics
from .settling import DEFAULT_SETTINGS, GuardedSettings, settle_family

PROFILE = "closy.all_family_integration.development.v1"
FLOAT32_BINDING_TOLERANCE_M = 2e-6


def compile_family(
    family: str,
    output: Path,
    *,
    changes: dict[str, float | int] | None = None,
    settings: GuardedSettings = DEFAULT_SETTINGS,
) -> dict[str, Any]:
    spec = family_spec(family)
    params = spec.parameters(changes)
    if output.exists():
        raise FamilyInputError("output_must_be_fresh")
    pattern = getattr(spec.module("pattern_generator"), spec.pattern_function)(params)
    semantic = getattr(spec.module("semantic_graph"), spec.semantic_function)(pattern)
    rest, edge_maps = spec.module("assembly").build_simulation_mesh(pattern)
    constraints = spec.module("assembly").build_constraints(pattern, edge_maps)
    validate_semantics(family, params.to_json(), pattern, semantic)
    require_mesh(rest, family=family, stage="rest")
    avatar = avatar_contract(build_reference_avatar_mesh(), build_collision_mesh())
    settled, solve_report = settle_family(rest, constraints, avatar, settings=settings)
    require_mesh(settled, family=family, stage="settled")
    output.mkdir(parents=True)
    for path, mesh in (
        ("simulation/rest.glb", rest),
        ("simulation/simulation_mesh.glb", settled),
        ("avatar/collision.glb", build_collision_mesh()),
    ):
        write_indexed_glb(
            output / path,
            mesh,
            "development_cotton",
            (0.22, 0.38, 0.60, 1.0),
            normalize_signed_zero=True,
        )
    # Bind to the actual float32 cage, not a hidden double-precision authoring copy.
    simulation = read_glb_meshset(output / "simulation/simulation_mesh.glb")
    render, seeds = subdivide_for_render(simulation)
    require_mesh(render, family=family, stage="subdivision")
    binding, binding_manifest = build_binding(simulation, render, seeds)
    write_binding(output / "binding/sim_to_render.bin", binding)
    write_indexed_glb(
        output / "render/fallback.glb",
        render,
        "development_cotton",
        (0.22, 0.38, 0.60, 1.0),
        normalize_signed_zero=True,
    )
    for path, data in {
        "pattern/pattern.json": pattern,
        "semantic/garment_graph.json": semantic,
        "simulation/constraints.json": constraints,
        "simulation/edge_maps.json": edge_maps,
        "simulation/settling.json": solve_report,
        "avatar/avatar_contract.json": avatar,
        "binding/binding_manifest.json": binding_manifest,
        "simulation/material.json": {
            "densityKgM2": 0.16,
            "thicknessM": 0.0016,
            "clearanceM": 0.006,
            "preset": "cotton_reference",
        },
    }.items():
        write_canonical_json(output / path, data)
    inventory = [
        {
            "path": p.relative_to(output).as_posix(),
            "sha256": sha256_file(p),
            "byteSize": p.stat().st_size,
        }
        for p in sorted(output.rglob("*"))
        if p.is_file()
    ]
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "profile": PROFILE,
        "family": family,
        "garmentId": semantic["garmentId"],
        "avatarId": avatar["avatarContractId"],
        "units": "metres",
        "coordinates": "right_handed_y_up",
        "parameters": params.to_json(),
        "parameterSource": "known_structured_manual_input",
        "simulationTopology": topology_hash(simulation),
        "renderTopology": topology_hash(render),
        "restTopology": topology_hash(rest),
        "simulationContent": geometry_content_hash(simulation),
        "inventory": inventory,
        "motionSupport": "analytic_binding_fidelity_only",
        "layerSupport": "separate_semantic_parts_not_collision_qualified",
        "scientificQualification": False,
        "physicalConvergence": False,
    }
    manifest["packageIdentity"] = sha256_bytes(canonical_dumps(manifest).encode())
    write_canonical_json(output / "manifest.json", manifest)
    audit = validate_family(output)
    write_canonical_json(output / "audit.json", audit)
    return audit


def validate_family(output: Path) -> dict[str, Any]:
    manifest = read_json(output / "manifest.json")
    if manifest.get("profile") != PROFILE or manifest.get("units") != "metres":
        raise FamilyInputError("family_profile_or_units_invalid")
    identity = dict(manifest)
    claimed = identity.pop("packageIdentity", None)
    if sha256_bytes(canonical_dumps(identity).encode()) != claimed:
        raise FamilyInputError("family_manifest_identity_mismatch")
    paths: set[str] = set()
    for row in manifest["inventory"]:
        validate_package_relpath(row["path"])
        path = output / row["path"]
        if (
            row["path"] in paths
            or path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != row["byteSize"]
            or sha256_file(path) != row["sha256"]
        ):
            raise FamilyInputError("family_inventory_mismatch")
        paths.add(row["path"])
    family = str(manifest["family"])
    pattern = read_json(output / "pattern/pattern.json")
    validate_semantics(
        family, manifest["parameters"], pattern, read_json(output / "semantic/garment_graph.json")
    )
    geometry = {
        name: require_glb(output / path, family=family)
        for name, path in (
            ("rest", "simulation/rest.glb"),
            ("simulation", "simulation/simulation_mesh.glb"),
            ("render", "render/fallback.glb"),
        )
    }
    simulation = read_glb_meshset(output / "simulation/simulation_mesh.glb")
    render = read_glb_meshset(output / "render/fallback.glb")
    binding = read_binding(output / "binding/sim_to_render.bin")
    if (
        binding.simulation_topology_hash != topology_hash(simulation)
        or binding.render_topology_hash != topology_hash(render)
        or binding.simulation_topology_hash != manifest["simulationTopology"]
        or binding.render_topology_hash != manifest["renderTopology"]
        or manifest["restTopology"] != manifest["simulationTopology"]
        or len(binding.records) != render.vertex_count
    ):
        raise FamilyGeometryError("stale_binding_or_changed_canonical_topology")
    tri_panels = [m.panel_id for m in simulation.meshes for _ in m.triangles]
    panels = sorted({m.panel_id for m in simulation.meshes})
    render_panels = [m.panel_id for m in render.meshes for _ in m.vertices]
    for record, panel in zip(binding.records, render_panels, strict=True):
        if (
            not 0 <= record.simulation_triangle_index < len(tri_panels)
            or not 0 <= record.panel_table_index < len(panels)
            or tri_panels[record.simulation_triangle_index] != panel
            or panels[record.panel_table_index] != panel
            or record.normal_offset != 0
            or not all(
                math.isfinite(x) and 0 <= x <= 1
                for x in (record.barycentric_u, record.barycentric_v)
            )
            or record.barycentric_u + record.barycentric_v > 1.000001
        ):
            raise FamilyGeometryError("invalid_binding_influence")
    positions = reconstruct_vertices(simulation, binding)
    error = max(
        math.dist(a, b) for a, b in zip(positions, flatten_mesh(render).positions, strict=True)
    )
    if error > FLOAT32_BINDING_TOLERANCE_M:
        raise FamilyGeometryError("serialized_binding_reconstruction_failed")
    boundaries = boundary_metrics(simulation, read_json(output / "simulation/constraints.json"))
    if not boundaries["allOpeningsNoncollapsed"]:
        raise FamilyGeometryError("collapsed_opening")
    return {
        "profile": PROFILE,
        "family": family,
        "packageIdentity": claimed,
        "geometry": geometry,
        "semanticsValid": True,
        "canonicalTopologyPreserved": True,
        "bindingCoverage": len(binding.records),
        "renderVertexCount": render.vertex_count,
        "maximumBindingErrorM": error,
        "float32ToleranceM": FLOAT32_BINDING_TOLERANCE_M,
        "boundaries": boundaries,
        "validConventionalGeometry": True,
        "physicalQualityPassed": False,
        "physicalQualityScope": "not_qualified",
        "motionSupport": manifest["motionSupport"],
        "layerSupport": manifest["layerSupport"],
    }
