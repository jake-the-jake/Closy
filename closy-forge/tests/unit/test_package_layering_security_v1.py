"""Tiny exposed security/regression cases; never execute the final outfit matrix.

Unmet contracts remain ordinary test failures, never xfails. These fixtures do not claim
cloth physics and do not bypass any serialized-output geometry/binding checks.
"""

from __future__ import annotations

import copy
import json
import math
import struct
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from closy_forge.binding.binary_format import BindingFile, read_binding, write_binding
from closy_forge.binding.builder import build_binding
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.geometry.glb_io import read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3, cross, sub
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.manual_provider_c3_v1.states import MOTION_STATES
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, sha256_file
from closy_forge.package_layering_v1.contacts import Witness, contacts
from closy_forge.package_layering_v1.contracts import (
    LayerInputError,
    LayerPackage,
    LayerSpec,
    load_layers,
)
from closy_forge.package_layering_v1.matrix import STATES, cases
from closy_forge.package_layering_v1.solver import (
    LayerSettings,
    combine,
    guard_correction,
    measure_persisted,
    solve,
    validate_output,
)
from closy_forge.simulation.reference_cloth_solver import flatten_mesh, replace_mesh_positions
from closy_forge.simulation.self_collision import build_triangle_refs

ORDER = [("a", "b", 0.0, 2.0, True)]
SMALL = LayerSettings(iterations=2)


def _triangle(points: list[Vec3], panel: str = "panel.front") -> Mesh:
    return Mesh(panel, panel, points, [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)], [(0, 1, 2)])


def _layer(name: str, z: float, *, boundaries: bool = False) -> LayerPackage:
    front = _triangle([(-0.02, 1.0, z), (0.02, 1.0, z), (0.0, 1.04, z)])
    panels = [front]
    constraints: dict[str, Any] = {"constraints": [], "openings": []}
    if boundaries:
        panels.append(_triangle([(0.02, 1.0, z), (-0.02, 1.0, z), (0.0, 0.96, z)], "panel.back"))
        constraints["constraints"] = [
            {
                "seamId": f"seam.join.{i}",
                "enabled": True,
                "spanA": {"meshIndex": 0, "panelId": "panel.front", "vertexIndex": i},
                "spanB": {"meshIndex": 1, "panelId": "panel.back", "vertexIndex": 1 - i},
            }
            for i in (0, 1)
        ]
        constraints["openings"] = [
            {
                "id": "opening.front",
                "boundaryEdges": [{"panelId": "panel.front", "vertexIndices": [0, 1]}],
            }
        ]
    simulation = MeshSet(panels)
    dense, seeds = subdivide_for_render(simulation)
    binding, _ = build_binding(simulation, dense, seeds)
    return LayerPackage(
        LayerSpec(name, Path("unused-authored-tiny-fixture")),
        {
            "avatarId": "avatar.tiny",
            "units": "metres",
            "packageIdentity": sha256_bytes(name.encode()),
        },
        simulation,
        dense,
        binding,
        constraints,
        {"collisionPrimitives": []},
    )


def _output(root: Path, *, contact: bool = False, boundaries: bool = False) -> dict[str, Any]:
    report = solve(
        [
            _layer("a", -0.1, boundaries=boundaries),
            _layer("b", -0.1 if contact else 0.1, boundaries=boundaries),
        ],
        [("a", "b", 0.0, 2.0, not contact)],
        MOTION_STATES[0],
        root,
        settings=SMALL,
    )
    assert (
        report["before"]["contactCount"] > 0 if contact else report["before"]["contactCount"] == 0
    )
    if not contact:
        assert report["ready"], "the clean baseline must pass before the adversarial mutation"
    return report


def _rehash(root: Path, *, omit: str | None = None) -> str:
    """Rehash actual changed bytes, including report, so checks must go beyond SHA."""
    manifest = read_json(root / "manifest.json")
    manifest["inventory"] = [
        {"path": p.name, "sha256": sha256_file(p), "byteSize": p.stat().st_size}
        for p in sorted(root.iterdir())
        if p.is_file() and p.name not in {"manifest.json", omit}
    ]
    manifest.pop("identity", None)
    manifest["identity"] = sha256_bytes(canonical_dumps(manifest).encode())
    write_canonical_json(root / "manifest.json", manifest)
    return sha256_file(root / "manifest.json")


def _write_deformed(root: Path, mesh: MeshSet, binding: BindingFile | None = None) -> None:
    write_indexed_glb(root / "simulation.glb", mesh, "tiny-sim", (0.2, 0.4, 0.6, 1.0))
    moved = read_glb_meshset(root / "simulation.glb")
    decoded_binding = binding or read_binding(root / "binding.bin")
    dense = read_glb_meshset(root / "render.glb")
    reconstructed = replace_mesh_positions(
        dense, reconstruct_vertices(moved, decoded_binding), flatten_mesh(dense).mesh_offsets
    )
    write_indexed_glb(root / "render.glb", reconstructed, "tiny-render", (0.2, 0.4, 0.6, 1.0))


def _query(
    left: list[Vec3], right: list[Vec3], *, allowed: bool = True
) -> tuple[list[Witness], dict[str, Any]]:
    mesh = MeshSet([_triangle(left, "left"), _triangle(right, "right")])
    refs, _ = build_triangle_refs(mesh)
    return contacts(
        flatten_mesh(mesh).positions,
        refs,
        ["a", "b"],
        {"a": (0.001, 0.001), "b": (0.001, 0.001)},
        [("a", "b", -2.0, 2.0, allowed)],
    )


def test_matrix_inventory_is_ten_by_four_without_executing(tmp_path: Path) -> None:
    matrix = cases(tmp_path)
    assert len(matrix) == 10 and len(STATES) == 4
    assert len({c.case_id for c in matrix}) == 10
    assert {s.state_id for s in STATES} == {"neutral", "reach_left", "twist_right", "step_left"}
    assert {layer.package.parent.name for case in matrix for layer in case.layers} == {
        "tshirt",
        "sleeveless_top",
        "long_sleeved_top",
        "simple_skirt",
        "simple_trousers",
        "simple_dress",
        "button_shirt",
        "jacket_outerwear",
        "layered_asymmetric",
    }
    assert not list(tmp_path.iterdir())


def test_nonmatching_vertex_face_interior_contact() -> None:
    left = [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (0.0, 1.0, 0.0)]
    right = [(0.0, 0.0, 0.001), (0.2, 0.0, 0.001), (0.0, 0.2, 0.001)]
    assert not set(left) & set(right)
    witnesses, summary = _query(left, right)
    interior = [
        w
        for w in witnesses
        if w.kind == "vertex_triangle" and sum(abs(c) > 1e-10 for _, c in w.coefficients) == 4
    ]
    assert interior, "interior VF coverage cannot be replaced by nearest-vertex matching"
    assert min(w.distance for w in interior) == pytest.approx(0.001, abs=1e-10)
    assert summary["crossings"] == 0
    for witness in interior:
        assert math.fsum(c for _, c in witness.coefficients) == pytest.approx(0, abs=1e-8)


def test_nonmatching_edge_edge_interiors_are_detected() -> None:
    left = [(-1.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, -0.4, 0.0)]
    right = [(0.0, -1.0, 0.001), (0.0, 1.0, 0.001), (0.4, 0.0, 1.0)]
    witnesses, _ = _query(left, right)
    interior = [
        w
        for w in witnesses
        if w.kind == "edge_edge" and sum(abs(c) > 1e-10 for _, c in w.coefficients) == 4
    ]
    assert interior, "EE interiors must not depend on matching tessellation or endpoints"
    assert min(w.distance for w in interior) == pytest.approx(0.001, abs=1e-10)


def test_edge_through_face_crossing_without_vf_or_ee_proximity() -> None:
    left = [(-0.2, 1.0, 0.0), (0.2, 1.0, 0.0), (0.0, 1.4, 0.0)]
    right = [(0.0, 1.1, -0.2), (0.0, 1.1, 0.2), (0.0, 1.3, 0.2)]
    witnesses, summary = _query(left, right, allowed=False)
    assert {w.kind for w in witnesses} == {"triangle_crossing"}
    assert summary["crossings"] > 0 and summary["policyBlockedContacts"] == len(witnesses)
    assert all(w.depth >= 0.002 and not w.correction_allowed for w in witnesses)


@pytest.mark.parametrize("reverse", [False, True])
def test_coplanar_nonmatching_overlap_and_disjoint_control(reverse: bool) -> None:
    left = [(-0.2, 0.0, 0.0), (0.2, 0.0, 0.0), (0.0, 0.4, 0.0)]
    right = [(-0.1, 0.1, 0.0), (0.3, 0.1, 0.0), (0.1, 0.5, 0.0)]
    if reverse:
        right.reverse()
    found, summary = _query(left, right)
    assert any(w.kind == "coplanar_overlap" for w in found) and summary["crossings"] > 0
    clean, clean_summary = _query(left, [(x + 2.0, y, z) for x, y, z in right])
    assert not clean and clean_summary["contactCount"] == 0


def test_combine_input_permutation_has_canonical_results() -> None:
    layers = [_layer("a", -0.1, boundaries=True), _layer("b", 0.1, boundaries=True)]
    before = copy.deepcopy(layers)
    first, second = combine(layers), combine(list(reversed(layers)))
    assert geometry_content_hash(first[0]) == geometry_content_hash(second[0])
    assert geometry_content_hash(first[1]) == geometry_content_hash(second[1])
    assert first[2:] == second[2:]
    assert layers == before, "combining may not mutate inventoried input objects"


def test_outfit_manifest_id_uses_runtime_garment_namespace(tmp_path: Path) -> None:
    root = tmp_path / "outfit"
    _output(root)
    manifest = read_json(root / "manifest.json")
    sources = {name: sha256_bytes(name.encode()) for name in ("a", "b")}
    assert manifest["sources"] == sources
    suffix = sha256_bytes(canonical_dumps(sources).encode())[:16]
    assert manifest["garmentId"] == f"garment.outfit.{suffix}"
    assert validate_output(root, trusted_manifest_hash=sha256_file(root / "manifest.json"))["ready"]


def test_solve_input_permutation_has_canonical_serialized_geometry(tmp_path: Path) -> None:
    layers = [_layer("a", -0.1), _layer("b", 0.1)]
    first, second = tmp_path / "first", tmp_path / "second"
    a = solve(layers, ORDER, MOTION_STATES[0], first, settings=SMALL)
    b = solve(
        list(reversed(layers)), list(reversed(ORDER)), MOTION_STATES[0], second, settings=SMALL
    )
    assert a["ready"] and b["ready"]
    for filename in (
        "input.glb",
        "simulation.glb",
        "render.glb",
        "binding.bin",
        "constraints.json",
        "context.json",
    ):
        assert sha256_file(first / filename) == sha256_file(second / filename), filename
    # CPU/wall timings and their containing manifest are intentionally not byte-compared.
    assert a["after"] == b["after"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"iterations": 0},
        {"iterations": 25},
        {"iterations": True},
        {"iterations": 1.5},
        {"iterations": "2"},
        {"iterations": None},
        {"max_step_m": True},
        {"max_step_m": "0.001"},
        {"max_step_m": None},
        {"max_step_m": 10**400},
        {"max_step_m": float("nan")},
        {"max_displacement_m": float("inf")},
        {"residual_m": -1.0},
        {"seam_budget_m": 0.009},
        {"binding_tolerance_m": 3e-6},
        {"opening_length_drift": 0.11},
    ],
)
def test_invalid_settings_rejected_at_construction(kwargs: dict[str, Any]) -> None:
    with pytest.raises(LayerInputError):
        LayerSettings(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"thickness_m": float("nan")},
        {"clearance_m": float("inf")},
        {"density_kg_m2": float("nan")},
        {"body_clearance_m": float("-inf")},
        {"translation": (0.0, float("nan"), 0.0)},
        {"clearance_m": 0.04},
        {"density_kg_m2": 0.0},
        {"opening_policy": "drop"},
        {"density_kg_m2": True},
        {"clearance_m": False},
        {"translation": (0.0, 0.0)},
        {"translation": (0.0, "0", 0.0)},
    ],
)
def test_invalid_materials_and_transforms_reject_before_source_reads(
    tmp_path: Path,
    kwargs: dict[str, Any],
) -> None:
    with pytest.raises(LayerInputError):
        load_layers(
            [
                LayerSpec("a", tmp_path / "absent-a", **kwargs),
                LayerSpec("b", tmp_path / "absent-b"),
            ],
            ORDER,
        )


@pytest.mark.parametrize("kind", ["nan", "infinity", "repeated_index", "out_of_range"])
def test_invalid_geometry_never_publishes_ready_output(tmp_path: Path, kind: str) -> None:
    layer = _layer("a", -0.1)
    panel = layer.simulation.meshes[0]
    if kind in {"nan", "infinity"}:
        points = list(panel.vertices)
        points[0] = (float("nan") if kind == "nan" else float("inf"), 1.0, -0.1)
        panel = replace(panel, vertices=points)
    else:
        panel = replace(panel, triangles=[(0, 0, 2) if kind == "repeated_index" else (0, 1, 999)])
    invalid = replace(layer, simulation=MeshSet([panel]))
    with pytest.raises(ValueError):
        solve(
            [invalid, _layer("b", 0.1)],
            ORDER,
            MOTION_STATES[0],
            tmp_path / "invalid",
            settings=SMALL,
        )
    assert not (tmp_path / "invalid/manifest.json").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "simulation_hash",
        "render_hash",
        "negative_weight",
        "weight_sum",
        "offset",
        "missing_record",
        "panel_index",
        "flags",
        "triangle_count",
        "panel_count",
        "nan_weight",
        "infinite_weight",
        "triangle_index",
    ],
)
def test_combine_cannot_launder_invalid_source_binding(mutation: str) -> None:
    layer = _layer("a", -0.1)
    binding = _mutate_binding(layer.binding, mutation)
    with pytest.raises(ValueError):
        combine([replace(layer, binding=binding), _layer("b", 0.1)])


def _mutate_binding(binding: BindingFile, mutation: str) -> BindingFile:
    if mutation in {"simulation_hash", "render_hash"}:
        if mutation == "simulation_hash":
            return replace(binding, simulation_topology_hash="0" * 64)
        return replace(binding, render_topology_hash="0" * 64)
    if mutation == "missing_record":
        return replace(binding, records=binding.records[:-1])
    if mutation == "triangle_count":
        return replace(binding, simulation_triangle_count=binding.simulation_triangle_count + 1)
    if mutation == "panel_count":
        return replace(binding, panel_count=binding.panel_count + 1)
    mutations: dict[str, dict[str, Any]] = {
        "negative_weight": {"barycentric_u": -0.1},
        "weight_sum": {"barycentric_u": 0.7, "barycentric_v": 0.7},
        "offset": {"normal_offset": 0.002},
        "panel_index": {"panel_table_index": 65535},
        "flags": {"flags": 1},
        "nan_weight": {"barycentric_u": float("nan")},
        "infinite_weight": {"barycentric_v": float("inf")},
        "triangle_index": {"simulation_triangle_index": binding.simulation_triangle_count},
    }
    return replace(
        binding, records=[replace(binding.records[0], **mutations[mutation]), *binding.records[1:]]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "simulation_hash",
        "render_hash",
        "negative_weight",
        "weight_sum",
        "offset",
        "panel_index",
        "flags",
        "triangle_count",
        "panel_count",
        "missing_record",
        "nan_weight",
        "infinite_weight",
        "triangle_index",
    ],
)
def test_rehashed_persisted_binding_must_be_valid_even_with_matching_render(
    tmp_path: Path,
    mutation: str,
) -> None:
    root = tmp_path / "outfit"
    _output(root)
    binding = _mutate_binding(read_binding(root / "binding.bin"), mutation)
    write_binding(root / "binding.bin", binding)
    if mutation in {"negative_weight", "weight_sum", "offset", "panel_index", "flags"}:
        _write_deformed(root, read_glb_meshset(root / "simulation.glb"), binding)
    trusted = _rehash(root)
    # A new trust anchor does not excuse structurally invalid weights/counts/semantics.
    with pytest.raises(ValueError):
        actual = measure_persisted(root)
        report = read_json(root / "report.json")
        report["after"], report["ready"] = actual, actual["ready"]
        write_canonical_json(root / "report.json", report)
        trusted = _rehash(root)
        validate_output(root, trusted_manifest_hash=trusted)


@pytest.mark.parametrize(
    "mutation",
    [
        "after_count",
        "before_count",
        "empty_witnesses",
        "same_count_fake_witnesses",
        "before_depth",
        "before_boundaries",
    ],
)
def test_rehashed_report_tampering_is_independently_rejected(tmp_path: Path, mutation: str) -> None:
    root = tmp_path / "outfit"
    report = _output(root, contact=True, boundaries=True)
    assert report["beforeWitnesses"] and report["before"]["maximumThicknessDeficitM"] > 0
    if mutation == "after_count":
        report["after"]["contactCount"] += 999
    elif mutation == "before_count":
        report["before"]["contactCount"] += 999
    elif mutation == "empty_witnesses":
        report["beforeWitnesses"] = []
        report["executed"] = True
    elif mutation == "same_count_fake_witnesses":
        report["beforeWitnesses"] = [{"executed": True} for _ in report["beforeWitnesses"]]
    elif mutation == "before_depth":
        report["before"]["maximumThicknessDeficitM"] = 0.0
    else:
        report["boundariesBefore"]["maximumPairedSeamGapM"] = 99.0
    write_canonical_json(root / "report.json", report)
    trusted = _rehash(root)
    with pytest.raises(LayerInputError):
        validate_output(root, trusted_manifest_hash=trusted)


def test_manifest_cannot_omit_file_that_validator_consumes(tmp_path: Path) -> None:
    root = tmp_path / "outfit"
    _output(root)
    trusted = _rehash(root, omit="render.glb")
    with pytest.raises(LayerInputError):
        validate_output(root, trusted_manifest_hash=trusted)


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "wrong_size", "bool_size", "string_size", "alias", "extra_file", "directory"],
)
def test_exact_inventory_rejected_after_manifest_rehash(tmp_path: Path, mutation: str) -> None:
    root = tmp_path / "outfit"
    _output(root)
    manifest = read_json(root / "manifest.json")
    row = manifest["inventory"][0]
    if mutation == "duplicate":
        manifest["inventory"][-1] = copy.deepcopy(row)
    elif mutation == "wrong_size":
        row["byteSize"] += 1
    elif mutation == "bool_size":
        row["byteSize"] = True
    elif mutation == "string_size":
        row["byteSize"] = str(row["byteSize"])
    elif mutation == "alias":
        row["path"] = "./" + row["path"]
    elif mutation == "extra_file":
        (root / "unlisted.bin").write_bytes(b"not in the output contract")
    else:
        (root / "unlisted-directory").mkdir()
    manifest.pop("identity")
    manifest["identity"] = sha256_bytes(canonical_dumps(manifest).encode())
    write_canonical_json(root / "manifest.json", manifest)
    with pytest.raises(LayerInputError, match="inventory"):
        validate_output(root, trusted_manifest_hash=sha256_file(root / "manifest.json"))


@pytest.mark.parametrize("field", ["panel_table_index", "simulation_triangle_index"])
def test_in_range_binding_indices_must_reference_the_render_panel(field: str) -> None:
    layer = _layer("a", -0.1, boundaries=True)
    # Both new indices are in range, but refer to panel.back, not this front vertex.
    changed = replace(layer.binding.records[0], **{field: 0 if field == "panel_table_index" else 1})
    binding = replace(layer.binding, records=[changed, *layer.binding.records[1:]])
    with pytest.raises(LayerInputError, match="binding_membership"):
        combine([replace(layer, binding=binding), _layer("b", 0.1)])


@pytest.mark.parametrize(
    "mutation",
    [
        "vertex_owner",
        "extra_triangle",
        "missing_material",
        "missing_clearance",
        "extra_source",
        "missing_setting",
        "extra_setting",
        "bool_setting",
        "bool_order",
    ],
)
def test_persisted_ownership_and_settings_contracts_reject(tmp_path: Path, mutation: str) -> None:
    root = tmp_path / "outfit"
    _output(root)
    context = read_json(root / "context.json")
    if mutation == "vertex_owner":
        context["vertexLayers"][-1] = "a"
    elif mutation == "extra_triangle":
        context["triangleLayers"].append("a")
    elif mutation == "missing_material":
        context["materials"].pop("b")
    elif mutation == "missing_clearance":
        context["bodyClearance"].pop("b")
    elif mutation == "extra_source":
        context["sourcePackages"]["unused"] = "unrepresented"
    elif mutation == "missing_setting":
        context["settings"].pop("residual_m")
    elif mutation == "extra_setting":
        context["settings"]["ignore_contact"] = True
    elif mutation == "bool_setting":
        context["settings"]["iterations"] = True
    else:
        context["order"][0][2] = False
    write_canonical_json(root / "context.json", context)
    with pytest.raises(LayerInputError):
        validate_output(root, trusted_manifest_hash=_rehash(root))


@pytest.mark.parametrize("mapping", ["vertexLayers", "triangleLayers"])
def test_missing_serialized_geometry_membership_rejected(tmp_path: Path, mapping: str) -> None:
    root = tmp_path / "outfit"
    _output(root)
    context = read_json(root / "context.json")
    context[mapping] = context[mapping][:-1]
    write_canonical_json(root / "context.json", context)
    trusted = _rehash(root)
    with pytest.raises(ValueError):
        validate_output(root, trusted_manifest_hash=trusted)


@pytest.mark.parametrize("kind", ["seam", "opening"])
def test_measured_boundary_drift_blocks_readiness_with_valid_geometry(
    tmp_path: Path,
    kind: str,
) -> None:
    root = tmp_path / "outfit"
    _output(root, boundaries=True)
    moved = read_glb_meshset(root / "simulation.glb")
    panels = list(moved.meshes)
    first = panels[0]
    changed = (
        [(x + 0.012, y, z) for x, y, z in first.vertices]
        if kind == "seam"
        else [(x * 1.25, y, z) for x, y, z in first.vertices]
    )
    panels[0] = replace(first, vertices=changed)
    _write_deformed(root, MeshSet(panels))
    actual = measure_persisted(root)
    assert actual["renderBindingErrorM"] < 2e-6 and actual["inversions"] == 0
    assert actual["maximumDisplacementM"] < SMALL.max_displacement_m
    if kind == "seam":
        assert actual["boundaries"]["maximumPairedSeamGapM"] > SMALL.seam_budget_m
        assert actual["openingLengthRelativeDrift"] < 1e-5
    else:
        assert actual["openingLengthRelativeDrift"] > SMALL.opening_length_drift
        assert actual["boundaries"]["maximumPairedSeamGapM"] < SMALL.seam_budget_m
    assert actual["ready"] is False


@pytest.mark.parametrize("field", ["constraints", "openings"])
def test_dropping_boundary_declarations_cannot_erase_prior_evidence(
    tmp_path: Path,
    field: str,
) -> None:
    root = tmp_path / "outfit"
    _output(root, boundaries=True)
    constraints = read_json(root / "constraints.json")
    assert constraints[field]
    constraints[field] = []
    write_canonical_json(root / "constraints.json", constraints)
    report = read_json(root / "report.json")
    actual = measure_persisted(root)
    report["after"], report["ready"] = actual, actual["ready"]
    write_canonical_json(root / "report.json", report)
    trusted = _rehash(root)
    with pytest.raises(LayerInputError):
        validate_output(root, trusted_manifest_hash=trusted)


def test_small_contact_guard_keeps_posed_input_normal_hemisphere() -> None:
    reference: list[Vec3] = [(0.0, 0.0, 0.0), (0.01, 0.0, 0.0), (0.0, 0.001, 0.0)]
    old_angle, new_angle = math.radians(89), math.radians(91)
    old = (0.0, 0.001 * math.cos(old_angle), 0.001 * math.sin(old_angle))
    proposed = (0.0, 0.001 * math.cos(new_angle), 0.001 * math.sin(new_angle))
    positions = [reference[0], reference[1], proposed]
    assert math.dist(old, proposed) < SMALL.max_step_m
    backtracks = guard_correction(
        positions, {2: old}, [(0, 1, 2)], [[0], [0], [0]], [1e-10], reference
    )
    normal = cross(sub(positions[1], positions[0]), sub(positions[2], positions[0]))
    posed_normal = cross(sub(reference[1], reference[0]), sub(reference[2], reference[0]))
    assert math.fsum(a * b for a, b in zip(normal, posed_normal, strict=True)) > 0
    assert backtracks > 0


def test_unresolved_blocked_contact_remains_failed_not_physics(tmp_path: Path) -> None:
    report = _output(tmp_path / "outfit", contact=True)
    assert report["after"]["crossings"] > 0
    assert report["after"]["policyBlockedContacts"] > 0
    assert report["ready"] is False and report["after"]["ready"] is False
    assert report["fallback"] == "verified_input_only_not_collision_ready"
    assert report["physicalCloth"] is False and report["ccd"] is False


@pytest.mark.parametrize("filename", ["input.glb", "simulation.glb", "render.glb"])
def test_actual_serialized_missing_vertex_rejected(tmp_path: Path, filename: str) -> None:
    root = tmp_path / "outfit"
    _output(root)
    path = root / filename
    payload = path.read_bytes()
    size = struct.unpack_from("<I", payload, 12)[0]
    doc = json.loads(payload[20 : 20 + size])
    attributes = doc["meshes"][0]["primitives"][0]["attributes"]
    for index in set(attributes.values()):
        doc["accessors"][index]["count"] -= 1
    metadata = json.dumps(doc, separators=(",", ":"), sort_keys=True).encode()
    metadata += b" " * (-len(metadata) % 4)
    remainder = payload[20 + size :]
    path.write_bytes(
        struct.pack("<4sII", b"glTF", 2, 20 + len(metadata) + len(remainder))
        + struct.pack("<II", len(metadata), 0x4E4F534A)
        + metadata
        + remainder
    )
    trusted = _rehash(root)
    with pytest.raises(ValueError):
        validate_output(root, trusted_manifest_hash=trusted)


def test_triangle_ownership_cannot_hide_known_interlayer_contacts(tmp_path: Path) -> None:
    root = tmp_path / "outfit"
    original_report = _output(root, contact=True)
    assert original_report["before"]["contactCount"] > 0
    context = read_json(root / "context.json")
    context["triangleLayers"] = ["a"] * len(context["triangleLayers"])
    write_canonical_json(root / "context.json", context)
    # Keep every reported measurement consistent with the forged ownership mapping.
    # The independent check must compare labels to serialized panel/vertex ownership.
    with pytest.raises(LayerInputError):
        actual = measure_persisted(root)
        original = read_glb_meshset(root / "input.glb")
        refs, _ = build_triangle_refs(original)
        witnesses, before = contacts(
            flatten_mesh(original).positions,
            refs,
            context["triangleLayers"],
            context["materials"],
            context["order"],
        )
        report = read_json(root / "report.json")
        report.update(
            after=actual,
            ready=actual["ready"],
            before=before,
            beforeWitnesses=[w.__dict__ for w in witnesses],
        )
        write_canonical_json(root / "report.json", report)
        trusted = _rehash(root)
        validate_output(root, trusted_manifest_hash=trusted)
