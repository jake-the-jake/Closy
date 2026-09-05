from __future__ import annotations

import copy
import math
import stat
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import (
    BindingFile,
    BindingRecord,
    read_binding,
    write_binding,
)
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.family_integration_v1.geometry import require_glb, require_mesh
from closy_forge.family_integration_v1.semantics import boundary_metrics
from closy_forge.family_integration_v1.settling import _guard_local
from closy_forge.geometry.glb_io import read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import (
    Mesh,
    MeshSet,
    Tri,
    Vec3,
    add,
    cross,
    mesh_bounds,
    scale,
    sub,
)
from closy_forge.manual_provider_c3_v1.deformation import deform_simulation
from closy_forge.manual_provider_c3_v1.states import MotionState
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)
from closy_forge.simulation import reference_cloth_solver as legacy
from closy_forge.simulation.self_collision import build_triangle_refs

from .contacts import contacts
from .contracts import (
    PROFILE,
    LayerInputError,
    LayerPackage,
    LayerSpec,
    finite_number,
    validate_layer_binding,
    validate_order,
    validate_specs,
)


@dataclass(frozen=True)
class LayerSettings:
    iterations: int = 12
    max_displacement_m: float = 0.045
    max_step_m: float = 0.004
    residual_m: float = 0.00016
    seam_budget_m: float = 0.008
    binding_tolerance_m: float = 2e-6
    opening_length_drift: float = 0.1

    def __post_init__(self) -> None:
        if (
            type(self.iterations) is not int
            or not 1 <= self.iterations <= 24
            or not all(
                finite_number(v) and v > 0
                for v in (
                    self.max_displacement_m,
                    self.max_step_m,
                    self.residual_m,
                    self.seam_budget_m,
                    self.binding_tolerance_m,
                    self.opening_length_drift,
                )
            )
            or self.max_displacement_m > 0.045
            or self.max_step_m > 0.004
            or self.residual_m > 0.00016
            or self.seam_budget_m > 0.008
            or self.binding_tolerance_m > 2e-6
            or self.opening_length_drift > 0.1
        ):
            raise LayerInputError("outfit_settings_outside_versioned_budget")


SETTINGS = LayerSettings()


def guard_correction(
    positions: list[Vec3],
    saved: dict[int, Vec3],
    triangles: list[Tri],
    incident: list[list[int]],
    minimum: list[float],
    reference: list[Vec3],
) -> int:
    count = _guard_local(positions, saved, triangles, incident, minimum)
    proposed = {i: positions[i] for i in saved}
    affected = sorted({t for i in saved for t in incident[i]})
    # Contact corrections are small, not pose rotations: also preserve the normal
    # hemisphere of the posed INPUT, not only that of the immediately previous step.
    for attempt in range(25):
        for i, old in saved.items():
            positions[i] = add(old, scale(sub(proposed[i], old), 2.0**-attempt))
        valid = True
        for t in affected:
            a, b, c = triangles[t]
            now = cross(sub(positions[b], positions[a]), sub(positions[c], positions[a]))
            old = cross(sub(reference[b], reference[a]), sub(reference[c], reference[a]))
            if (
                sum(x * y for x, y in zip(now, old, strict=True)) <= 1e-15
                or sum(x * x for x in now) < (2 * minimum[t]) ** 2
            ):
                valid = False
                break
        if valid:
            return count + attempt
    for i, old in saved.items():
        positions[i] = old
    return count + 25


def combine(
    layers: list[LayerPackage],
) -> tuple[MeshSet, MeshSet, BindingFile, dict[str, Any], list[str], list[str]]:
    """Copy/renumber existing binding records; never independently rebind a pose."""
    validate_specs([p.spec for p in layers])
    if (
        len({p.manifest.get("avatarId") for p in layers}) != 1
        or len({p.manifest.get("units") for p in layers}) != 1
        or any(p.avatar != layers[0].avatar for p in layers)
    ):
        raise LayerInputError("avatar_or_units_mismatch")
    simulation: list[Mesh] = []
    render: list[Mesh] = []
    pending: list[tuple[BindingRecord, int, str]] = []
    constraints: dict[str, Any] = {"constraints": [], "openings": []}
    vertex_layers, triangle_layers = [], []
    for layer in sorted(layers, key=lambda p: p.spec.layer_id):
        validate_layer_binding(layer.simulation, layer.render, layer.binding)
        if any(
            math.dist(a, b) > SETTINGS.binding_tolerance_m
            for a, b in zip(
                reconstruct_vertices(layer.simulation, layer.binding),
                legacy.flatten_mesh(layer.render).positions,
                strict=True,
            )
        ):
            raise LayerInputError("outfit_source_binding_reconstruction")
        spec = layer.spec
        selected = {
            i: len(simulation) + j
            for j, i in enumerate(
                i
                for i, m in enumerate(layer.simulation.meshes)
                if m.panel_id.startswith(spec.panel_prefix)
            )
        }
        if not selected:
            raise LayerInputError("missing_semantic_part")
        old_triangle = 0
        triangle_map = {}
        for i, mesh in enumerate(layer.simulation.meshes):
            if i in selected:
                start = sum(len(m.triangles) for m in simulation)
                triangle_map.update(
                    {old_triangle + j: start + j for j in range(len(mesh.triangles))}
                )
                simulation.append(
                    replace(
                        mesh,
                        panel_id=f"{spec.layer_id}:{mesh.panel_id}",
                        name=f"{spec.layer_id}:{mesh.name}",
                        vertices=[add(p, spec.translation) for p in mesh.vertices],
                    )
                )
                vertex_layers.extend([spec.layer_id] * len(mesh.vertices))
                triangle_layers.extend([spec.layer_id] * len(mesh.triangles))
            old_triangle += len(mesh.triangles)
        cursor = 0
        for mesh in layer.render.meshes:
            if mesh.panel_id.startswith(spec.panel_prefix):
                panel = f"{spec.layer_id}:{mesh.panel_id}"
                render.append(
                    replace(
                        mesh,
                        panel_id=panel,
                        name=f"{spec.layer_id}:{mesh.name}",
                        vertices=[add(p, spec.translation) for p in mesh.vertices],
                    )
                )
                for record in layer.binding.records[cursor : cursor + len(mesh.vertices)]:
                    if record.simulation_triangle_index not in triangle_map:
                        raise LayerInputError("cross_part_binding_unsupported")
                    pending.append((record, triangle_map[record.simulation_triangle_index], panel))
            cursor += len(mesh.vertices)
        for original in layer.constraints["constraints"]:
            included = [int(original[s]["meshIndex"]) in selected for s in ("spanA", "spanB")]
            if any(included) and not all(included):
                raise LayerInputError("cross_layer_seam_requires_explicit_attachment")
            if not all(included):
                continue
            row = copy.deepcopy(original)
            row["seamId"] = f"{spec.layer_id}:{row['seamId']}"
            for key in ("spanA", "spanB"):
                row[key]["meshIndex"] = selected[int(row[key]["meshIndex"])]
                row[key]["panelId"] = f"{spec.layer_id}:{row[key]['panelId']}"
            constraints["constraints"].append(row)
        for original in layer.constraints.get("openings", []):
            row = copy.deepcopy(original)
            row["id"] = f"{spec.layer_id}:{row['id']}"
            row["boundaryEdges"] = [
                e for e in row["boundaryEdges"] if str(e["panelId"]).startswith(spec.panel_prefix)
            ]
            for edge in row["boundaryEdges"]:
                edge["panelId"] = f"{spec.layer_id}:{edge['panelId']}"
            if row["boundaryEdges"]:
                constraints["openings"].append(row)
    sim, dense = MeshSet(simulation), MeshSet(render)
    panels = sorted(m.panel_id for m in simulation)
    records = [
        BindingRecord(
            tri, r.barycentric_u, r.barycentric_v, r.normal_offset, panels.index(panel), r.flags
        )
        for r, tri, panel in pending
    ]
    binding = BindingFile(
        records, sim.triangle_count, len(panels), topology_hash(sim), topology_hash(dense)
    )
    validate_layer_binding(sim, dense, binding)
    return sim, dense, binding, constraints, vertex_layers, triangle_layers


def solve(
    layers: list[LayerPackage],
    order: list[tuple[str, str, float, float, bool]],
    state: MotionState,
    target: Path,
    *,
    settings: LayerSettings = SETTINGS,
) -> dict[str, Any]:
    if target.exists():
        raise LayerInputError("outfit_output_must_be_fresh")
    validate_order([p.spec.layer_id for p in layers], order)
    layers = sorted(layers, key=lambda p: p.spec.layer_id)
    order = sorted(order)
    start, cpu = time.perf_counter(), time.process_time()
    rest, render, binding, constraints_doc, vertex_layers, triangle_layers = combine(layers)
    posed = deform_simulation(rest, state)
    require_mesh(posed, family="outfit", stage="analytic_input")
    target.mkdir(parents=True)
    write_indexed_glb(target / "input.glb", posed, "outfit_input", (0.45, 0.5, 0.58, 1))
    posed = read_glb_meshset(target / "input.glb")
    flat = legacy.flatten_mesh(posed)
    positions = list(flat.positions)
    refs, offsets = build_triangle_refs(posed)
    triangles = [t.vertex_indices for t in refs]
    materials = {p.spec.layer_id: (p.spec.thickness_m, p.spec.clearance_m) for p in layers}
    specs = {p.spec.layer_id: p.spec for p in layers}
    before_witnesses, before = contacts(positions, refs, triangle_layers, materials, order)
    boundaries_before = boundary_metrics(posed, constraints_doc)
    incident: list[list[int]] = [[] for _ in positions]
    minimum = []
    for i, (a, b, c) in enumerate(triangles):
        for index in (a, b, c):
            incident[index].append(i)
        normal = cross(sub(positions[b], positions[a]), sub(positions[c], positions[a]))
        minimum.append(max(1e-10, math.sqrt(sum(v * v for v in normal)) * 0.01))
    constraints = legacy._build_distance_constraints(
        posed, constraints_doc, offsets, legacy.SettleSettings()
    )
    masses = []
    for mesh in posed.meshes:
        layer_id = mesh.panel_id.split(":", 1)[0]
        masses.extend(
            legacy._particle_inverse_masses(MeshSet([mesh]), specs[layer_id].density_kg_m2)
        )
    backtracks = 0
    history = []
    for _iteration in range(settings.iterations):
        witnesses, observed = contacts(positions, refs, triangle_layers, materials, order)
        history.append(observed)
        deltas: list[Vec3] = [(0, 0, 0) for _ in positions]
        counts = [0 for _ in positions]
        # All interacting layers are updated in the same Jacobi step. Density and
        # lumped triangle area determine inverse mass; thickness determines contact.
        for witness in witnesses:
            if not witness.correction_allowed:
                continue
            denom = sum(masses[i] * w * w for i, w in witness.coefficients)
            if denom <= 1e-12:
                continue
            for i, w in witness.coefficients:
                delta = scale(witness.normal, 0.7 * witness.depth * masses[i] * w / denom)
                deltas[i] = add(deltas[i], delta)
                counts[i] += 1
        for i in range(len(positions)):
            proposed = add(positions[i], scale(deltas[i], 1 / max(1, counts[i])))
            step = sub(proposed, positions[i])
            length = math.dist(proposed, positions[i])
            proposed = add(
                positions[i], scale(step, min(1, settings.max_step_m / max(length, 1e-12)))
            )
            spec = specs[vertex_layers[i]]
            for primitive in layers[0].avatar["collisionPrimitives"]:
                proposed, _ = legacy._project_primitive(proposed, primitive, spec.body_clearance_m)
            displacement = math.dist(proposed, flat.positions[i])
            proposed = add(
                flat.positions[i],
                scale(
                    sub(proposed, flat.positions[i]),
                    min(1, settings.max_displacement_m / max(displacement, 1e-12)),
                ),
            )
            saved = {i: positions[i]}
            positions[i] = proposed
            backtracks += guard_correction(
                positions, saved, triangles, incident, minimum, flat.positions
            )
        for constraint in constraints:
            saved = {
                i: positions[i]
                for i in (constraint.a, constraint.b, constraint.a_next, constraint.b_next)
                if i is not None
            }
            constraint.lagrange_multiplier = 0
            legacy._solve_distance(positions, masses, constraint, 1 / 60)
            for i in saved:
                distance = math.dist(positions[i], flat.positions[i])
                if distance > settings.max_displacement_m:
                    positions[i] = add(
                        flat.positions[i],
                        scale(
                            sub(positions[i], flat.positions[i]),
                            settings.max_displacement_m / distance,
                        ),
                    )
            backtracks += guard_correction(
                positions, saved, triangles, incident, minimum, flat.positions
            )
    moved = legacy.replace_mesh_positions(posed, positions, offsets)
    require_mesh(moved, family="outfit", stage="corrected")
    # Recompute dense derivatives from unchanged weights, then audit the persisted float32 bytes.
    write_indexed_glb(target / "simulation.glb", moved, "outfit_simulation", (0.2, 0.5, 0.65, 1))
    moved = read_glb_meshset(target / "simulation.glb")
    dense = legacy.replace_mesh_positions(
        render, reconstruct_vertices(moved, binding), legacy.flatten_mesh(render).mesh_offsets
    )
    write_indexed_glb(target / "render.glb", dense, "outfit_render", (0.22, 0.4, 0.65, 1))
    write_binding(target / "binding.bin", binding)
    write_canonical_json(target / "constraints.json", constraints_doc)
    context = {
        "triangleLayers": triangle_layers,
        "vertexLayers": vertex_layers,
        "order": order,
        "materials": materials,
        "avatar": layers[0].avatar,
        "bodyClearance": {p.spec.layer_id: p.spec.body_clearance_m for p in layers},
        "sourcePackages": {p.spec.layer_id: p.manifest["packageIdentity"] for p in layers},
        "pose": state.state_id,
        "settings": settings.__dict__,
        "profile": PROFILE,
    }
    write_canonical_json(target / "context.json", context)
    metrics = measure_persisted(target)
    report = {
        "profile": PROFILE,
        "before": before,
        "after": metrics,
        "beforeWitnesses": [w.__dict__ for w in before_witnesses],
        "boundariesBefore": boundaries_before,
        "iterations": settings.iterations,
        "history": history,
        "backtracks": backtracks,
        "cpuSeconds": time.process_time() - cpu,
        "wallSeconds": time.perf_counter() - start,
        "physicalCloth": False,
        "ccd": False,
        "articulatedAvatar": False,
        "materialScope": "thickness_clearance_density_weighted_geometric_projection",
        "ready": metrics["ready"],
        "fallback": "verified_input_only_not_collision_ready" if not metrics["ready"] else None,
    }
    write_canonical_json(target / "report.json", report)
    inventory = [
        {"path": p.name, "sha256": sha256_file(p), "byteSize": p.stat().st_size}
        for p in sorted(target.iterdir())
        if p.is_file()
    ]
    manifest = {
        "profile": PROFILE,
        "sources": context["sourcePackages"],
        "inventory": inventory,
        "garmentId": "garment.outfit."
        + sha256_bytes(canonical_dumps(context["sourcePackages"]).encode())[:16],
        "avatarId": layers[0].manifest["avatarId"],
        "restBindingPreserved": True,
    }
    manifest["identity"] = sha256_bytes(canonical_dumps(manifest).encode())
    write_canonical_json(target / "manifest.json", manifest)
    validate_output(target, trusted_manifest_hash=sha256_file(target / "manifest.json"))
    return report


def _validate_context(context: dict[str, Any], meshset: MeshSet) -> LayerSettings:
    raw_settings = context.get("settings")
    if not isinstance(raw_settings, dict) or set(raw_settings) != set(SETTINGS.__dict__):
        raise LayerInputError("outfit_invalid_settings_contract")
    settings = LayerSettings(**raw_settings)
    sources = context.get("sourcePackages")
    materials = context.get("materials")
    clearance = context.get("bodyClearance")
    if (
        context.get("profile") != PROFILE
        or not isinstance(sources, dict)
        or any(not isinstance(v, str) or not v for v in sources.values())
        or not isinstance(materials, dict)
        or not isinstance(clearance, dict)
        or set(materials) != set(sources)
        or set(clearance) != set(sources)
    ):
        raise LayerInputError("outfit_invalid_layer_inventory")
    validate_order(list(sources), context.get("order"))
    specs = []
    for layer_id in sources:
        material = materials[layer_id]
        if not isinstance(material, list | tuple) or len(material) != 2:
            raise LayerInputError("outfit_invalid_material_contract")
        specs.append(
            LayerSpec(
                layer_id,
                Path("."),
                thickness_m=material[0],
                clearance_m=material[1],
                body_clearance_m=clearance[layer_id],
            )
        )
    validate_specs(specs)
    vertex_layers, triangle_layers, mesh_layers = [], [], []
    for mesh in meshset.meshes:
        owner, separator, panel = mesh.panel_id.partition(":")
        if not separator or not panel or owner not in sources:
            raise LayerInputError("outfit_invalid_panel_ownership")
        mesh_layers.append(owner)
        vertex_layers.extend([owner] * len(mesh.vertices))
        triangle_layers.extend([owner] * len(mesh.triangles))
    # Ownership comes from decoded panels, never from contact candidate coverage.
    if (
        set(mesh_layers) != set(sources)
        or mesh_layers != sorted(mesh_layers)
        or context.get("vertexLayers") != vertex_layers
        or context.get("triangleLayers") != triangle_layers
    ):
        raise LayerInputError("outfit_noncanonical_geometry_ownership")
    return settings


def measure_persisted(root: Path) -> dict[str, Any]:
    for filename in ("input.glb", "simulation.glb", "render.glb"):
        require_glb(root / filename)
    original, moved, dense = [
        read_glb_meshset(root / f) for f in ("input.glb", "simulation.glb", "render.glb")
    ]
    context = read_json(root / "context.json")
    settings = _validate_context(context, moved)
    binding = read_binding(root / "binding.bin")
    validate_layer_binding(moved, dense, binding)
    if topology_hash(moved) != topology_hash(original):
        raise LayerInputError("outfit_stale_binding_or_topology")
    flat = legacy.flatten_mesh(moved)
    reference = legacy.flatten_mesh(original)
    refs, _ = build_triangle_refs(moved)
    witnesses, observed = contacts(
        flat.positions, refs, context["triangleLayers"], context["materials"], context["order"]
    )
    body_depth = max(
        legacy._penetration_depth(
            p, context["avatar"]["collisionPrimitives"], context["bodyClearance"][layer]
        )
        for p, layer in zip(flat.positions, context["vertexLayers"], strict=True)
    )
    error = max(
        math.dist(a, b)
        for a, b in zip(
            reconstruct_vertices(moved, binding), legacy.flatten_mesh(dense).positions, strict=True
        )
    )
    constraints = read_json(root / "constraints.json")
    boundaries = boundary_metrics(moved, constraints)
    before = boundary_metrics(original, constraints)
    opening_drift = max(
        (
            abs(a["boundaryLengthM"] / b["boundaryLengthM"] - 1)
            for a, b in zip(boundaries["openings"], before["openings"], strict=True)
        ),
        default=0,
    )
    inverted = 0
    for ref in refs:
        a, b, c = ref.vertex_indices
        old = cross(
            sub(reference.positions[b], reference.positions[a]),
            sub(reference.positions[c], reference.positions[a]),
        )
        new = cross(
            sub(flat.positions[b], flat.positions[a]), sub(flat.positions[c], flat.positions[a])
        )
        inverted += int(sum(x * y for x, y in zip(old, new, strict=True)) <= 0)
    displacement = max(
        math.dist(a, b) for a, b in zip(flat.positions, reference.positions, strict=True)
    )
    ready = (
        observed["crossings"] == 0
        and observed["maximumThicknessDeficitM"] <= settings.residual_m
        and body_depth <= settings.residual_m
        and boundaries["maximumPairedSeamGapM"] <= settings.seam_budget_m
        and opening_drift <= settings.opening_length_drift
        and inverted == 0
        and error <= settings.binding_tolerance_m
        and displacement <= settings.max_displacement_m + 2e-6
        and observed["layerOrderViolations"] == 0
    )
    return {
        **observed,
        "bodyPenetrationM": body_depth,
        "bodyClearanceScope": "reference_primitive_conservative_projection_deficit",
        "boundaries": boundaries,
        "openingLengthRelativeDrift": opening_drift,
        "inversions": inverted,
        "maximumDisplacementM": displacement,
        "renderBindingErrorM": error,
        "bounds": mesh_bounds(moved),
        "deformedContentHash": geometry_content_hash(moved),
        "ready": ready,
        "witnesses": [w.__dict__ for w in witnesses],
    }


OUTPUT_FILES = frozenset(
    {
        "input.glb",
        "simulation.glb",
        "render.glb",
        "binding.bin",
        "constraints.json",
        "context.json",
        "report.json",
    }
)


def _validate_inventory(root: Path, inventory: Any) -> None:
    if not isinstance(inventory, list) or len(inventory) != len(OUTPUT_FILES):
        raise LayerInputError("outfit_inventory_mismatch")
    seen = set()
    for row in inventory:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "byteSize"}:
            raise LayerInputError("outfit_inventory_mismatch")
        name, digest, size = row["path"], row["sha256"], row["byteSize"]
        if (
            not isinstance(name, str)
            or name not in OUTPUT_FILES
            or name in seen
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
            or type(size) is not int
            or size < 0
            or (root / name).stat().st_size != size
            or sha256_file(root / name) != digest
        ):
            raise LayerInputError("outfit_inventory_mismatch")
        seen.add(name)
    if seen != OUTPUT_FILES:
        raise LayerInputError("outfit_inventory_mismatch")


def validate_output(root: Path, *, trusted_manifest_hash: str) -> dict[str, Any]:
    try:
        paths = list(root.iterdir())
        if root.is_symlink() or set(p.name for p in paths) != OUTPUT_FILES | {"manifest.json"}:
            raise LayerInputError("outfit_inventory_mismatch")
        for path in [root, *paths]:
            info = path.lstat()
            if (
                path.is_symlink()
                or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                or (path != root and not stat.S_ISREG(info.st_mode))
            ):
                raise LayerInputError("outfit_inventory_mismatch")
    except OSError as error:
        raise LayerInputError("outfit_inventory_mismatch") from error
    if sha256_file(root / "manifest.json") != trusted_manifest_hash:
        raise LayerInputError("outfit_untrusted_manifest")
    manifest = read_json(root / "manifest.json")
    claimed = manifest.pop("identity")
    if sha256_bytes(canonical_dumps(manifest).encode()) != claimed:
        raise LayerInputError("outfit_manifest_mismatch")
    _validate_inventory(root, manifest.get("inventory"))
    actual = measure_persisted(root)
    report = read_json(root / "report.json")
    if (
        canonical_dumps(report["after"]) != canonical_dumps(actual)
        or report["ready"] != actual["ready"]
    ):
        raise LayerInputError("outfit_forged_measurements")
    context = read_json(root / "context.json")
    if (
        manifest.get("profile") != PROFILE
        or report.get("profile") != PROFILE
        or manifest.get("sources") != context["sourcePackages"]
        or manifest.get("restBindingPreserved") is not True
    ):
        raise LayerInputError("outfit_metadata_mismatch")
    original = read_glb_meshset(root / "input.glb")
    refs, _ = build_triangle_refs(original)
    witnesses, before = contacts(
        legacy.flatten_mesh(original).positions,
        refs,
        context["triangleLayers"],
        context["materials"],
        context["order"],
    )
    # Recomputed from input bytes: an empty list or executed=true is not evidence.
    if canonical_dumps(before) != canonical_dumps(report["before"]) or canonical_dumps(
        [w.__dict__ for w in witnesses]
    ) != canonical_dumps(report["beforeWitnesses"]):
        raise LayerInputError("outfit_forged_input_contacts")
    boundaries_before = boundary_metrics(original, read_json(root / "constraints.json"))
    if canonical_dumps(boundaries_before) != canonical_dumps(report.get("boundariesBefore")):
        raise LayerInputError("outfit_forged_input_boundaries")
    return actual
