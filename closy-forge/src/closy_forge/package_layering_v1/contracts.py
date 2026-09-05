from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import BindingFile, read_binding
from closy_forge.family_integration_v1.compiler import validate_family
from closy_forge.family_integration_v1.geometry import require_mesh
from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import MeshSet, Vec3
from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.hashing import topology_hash

PROFILE = "package_mesh_layering_development_v1"


class LayerInputError(ValueError):
    pass


@dataclass(frozen=True)
class LayerSpec:
    layer_id: str
    package: Path
    panel_prefix: str = ""
    thickness_m: float = 0.0016
    clearance_m: float = 0.001
    density_kg_m2: float = 0.16
    translation: Vec3 = (0, 0, 0)
    body_clearance_m: float = 0.002
    opening_policy: str = "preserve"


@dataclass(frozen=True)
class LayerPackage:
    spec: LayerSpec
    manifest: dict[str, Any]
    simulation: MeshSet
    render: MeshSet
    binding: BindingFile
    constraints: dict[str, Any]
    avatar: dict[str, Any]


def finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_order(ids: list[str], order: object) -> None:
    if not 2 <= len(ids) <= 6 or any(
        not isinstance(i, str) or not i or any(c in i for c in "/\\:") for i in ids
    ):
        raise LayerInputError("invalid_layer_inventory")
    if len(set(ids)) != len(ids):
        raise LayerInputError("duplicate_layer_id")
    if not isinstance(order, list):
        raise LayerInputError("invalid_order_region")
    edges: dict[str, set[str]] = {i: set() for i in ids}
    for row in order:
        if not isinstance(row, tuple | list) or len(row) != 5:
            raise LayerInputError("invalid_order_region")
        a, b, low, high, allowed = row
        if not isinstance(a, str) or not isinstance(b, str):
            raise LayerInputError("invalid_order_region")
        if a not in edges or b not in edges:
            raise LayerInputError("missing_layer_id")
        if (
            a == b
            or not all(finite_number(v) for v in (low, high))
            or low >= high
            or not isinstance(allowed, bool)
        ):
            raise LayerInputError("invalid_order_region")
        edges[a].add(b)
    # Conservative cycle rejection even if disjoint regional intervals could be valid.
    visited: set[str] = set()
    active: set[str] = set()

    def visit(node: str) -> None:
        if node in active:
            raise LayerInputError("cyclic_layer_order")
        if node in visited:
            return
        active.add(node)
        for child in sorted(edges[node]):
            visit(child)
        active.remove(node)
        visited.add(node)

    for node in sorted(ids):
        visit(node)


def validate_specs(specs: list[LayerSpec]) -> None:
    validate_order([s.layer_id for s in specs], [])
    for spec in specs:
        if (
            not isinstance(spec.translation, tuple | list)
            or len(spec.translation) != 3
            or not isinstance(spec.panel_prefix, str)
        ):
            raise LayerInputError("invalid_layer_transform_or_part")
        numbers = (
            spec.thickness_m,
            spec.clearance_m,
            spec.density_kg_m2,
            spec.body_clearance_m,
            *spec.translation,
        )
        if not all(finite_number(n) for n in numbers):
            raise LayerInputError("nonfinite_material_or_transform")
        if not (
            0.0001 <= spec.thickness_m <= 0.015
            and 0 <= spec.clearance_m <= 0.03
            and 0.03 <= spec.density_kg_m2 <= 2
            and 0 <= spec.body_clearance_m <= 0.03
        ):
            raise LayerInputError("impossible_clearance_or_material")
        if spec.opening_policy != "preserve":
            raise LayerInputError("incompatible_opening_policy")


def validate_layer_binding(simulation: MeshSet, render: MeshSet, binding: BindingFile) -> None:
    """Validate the supported zero-offset CLSYBND1 contract before any remapping."""
    for name, meshset in (("simulation", simulation), ("render", render)):
        require_mesh(meshset, family="outfit", stage=f"binding_{name}")
        ids = [m.panel_id for m in meshset.meshes]
        if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise LayerInputError("outfit_invalid_binding_panels")
    panels = sorted(m.panel_id for m in simulation.meshes)
    if set(panels) != {m.panel_id for m in render.meshes}:
        raise LayerInputError("outfit_binding_panel_coverage")
    if (
        type(binding.simulation_triangle_count) is not int
        or type(binding.panel_count) is not int
        or binding.simulation_triangle_count != simulation.triangle_count
        or binding.panel_count != len(panels)
        or len(binding.records) != render.vertex_count
        or binding.simulation_topology_hash != topology_hash(simulation)
        or binding.render_topology_hash != topology_hash(render)
    ):
        raise LayerInputError("outfit_stale_binding_or_topology")
    triangle_panels = [m.panel_id for m in simulation.meshes for _ in m.triangles]
    vertex_panels = [m.panel_id for m in render.meshes for _ in m.vertices]
    for record, panel in zip(binding.records, vertex_panels, strict=True):
        u, v = record.barycentric_u, record.barycentric_v
        if (
            not all(finite_number(n) for n in (u, v, record.normal_offset))
            or not 0 <= u <= 1
            or not 0 <= v <= 1
            or u + v > 1 + 1e-6
            or record.normal_offset != 0
            or type(record.flags) is not int
            or record.flags != 0
        ):
            raise LayerInputError("outfit_invalid_binding_weights_or_mode")
        if (
            type(record.simulation_triangle_index) is not int
            or not 0 <= record.simulation_triangle_index < len(triangle_panels)
            or type(record.panel_table_index) is not int
            or not 0 <= record.panel_table_index < len(panels)
            or panels[record.panel_table_index] != panel
            or triangle_panels[record.simulation_triangle_index] != panel
        ):
            raise LayerInputError("outfit_invalid_binding_membership")


def load_layers(
    specs: list[LayerSpec], order: list[tuple[str, str, float, float, bool]]
) -> list[LayerPackage]:
    validate_order([s.layer_id for s in specs], order)
    validate_specs(specs)
    result = []
    for spec in sorted(specs, key=lambda s: s.layer_id):
        validate_family(spec.package)
        manifest = read_json(spec.package / "manifest.json")
        simulation = read_glb_meshset(spec.package / "simulation/simulation_mesh.glb")
        if not any(m.panel_id.startswith(spec.panel_prefix) for m in simulation.meshes):
            raise LayerInputError("missing_semantic_part")
        result.append(
            LayerPackage(
                spec,
                manifest,
                simulation,
                read_glb_meshset(spec.package / "render/fallback.glb"),
                read_binding(spec.package / "binding/sim_to_render.bin"),
                read_json(spec.package / "simulation/constraints.json"),
                read_json(spec.package / "avatar/avatar_contract.json"),
            )
        )
        validate_layer_binding(result[-1].simulation, result[-1].render, result[-1].binding)
    if (
        len({p.manifest["avatarId"] for p in result}) != 1
        or len({p.manifest["units"] for p in result}) != 1
    ):
        raise LayerInputError("avatar_or_units_mismatch")
    return result
