from __future__ import annotations

import hashlib
import json
import math
import random
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from closy_forge.binding.binary_format import read_binding as read_legacy_binding
from closy_forge.geometry.glb_io import read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.manual_provider_binding_v2 import binding as producer
from closy_forge.manual_provider_binding_v2 import (
    build_binding_v2,
    check_rest,
    read_binding_v2,
    reconstruct_v2,
    write_binding_v2,
)
from closy_forge.package_io.hashing import geometry_content_hash, topology_hash


def _grid(columns: int = 7, rows: int = 8, *, reverse: bool = False) -> Mesh:
    vertices, uvs, triangles = [], [], []
    for r in range(rows):
        v = r / (rows - 1)
        width = 0.30 + (0.016 if r == 3 else 0.0) + 0.02 * v
        for c in range(columns):
            u = c / (columns - 1)
            x = (u - 0.5) * width
            vertices.append((x, v * 0.25, 0.003 * math.sin(math.pi * u) + 0.001 * v * v))
            # Projected/tapered UVs are deliberately not a Cartesian product.
            uvs.append((x + 0.5, v))
    for r in range(rows - 1):
        for c in range(columns - 1):
            a = r * columns + c
            b, d, e = a + 1, a + columns, a + columns + 1
            cell = [(a, b, d), (b, e, d)] if (r + c) % 2 else [(a, b, e), (a, e, d)]
            triangles.extend(cell if not reverse else [(x, z, y) for x, y, z in cell])
    return Mesh(
        "exposed-grid",
        "opaque.back" if not reverse else "opaque.front",
        vertices,
        uvs,
        triangles,
        "cloth.layer-A",
    )


def _serialize(root: Path, render: MeshSet) -> tuple[Path, Path, Path]:
    bound = build_binding_v2(render, root)
    cp, rp, bp = root / "cage.glb", root / "clean.glb", root / "binding/local_frame_v2.bin"
    write_indexed_glb(cp, bound.cage, "cage", (0.4, 0.4, 0.4, 1.0))
    write_indexed_glb(rp, render, "render", (0.4, 0.4, 0.4, 1.0))
    return cp, rp, bp


def _mutate_record(path: Path, field_offset: int, fmt: str, value: float | int) -> None:
    data = bytearray(path.read_bytes())
    header = producer.HEADER.unpack_from(data)
    start = producer.HEADER.size + header[7]
    struct.pack_into(fmt, data, start + field_offset, value)
    path.write_bytes(data)


@pytest.mark.parametrize(
    ("columns", "rows", "reverse"), [(7, 8, False), (8, 11, True), (13, 6, False)]
)
def test_nonstandard_grid_roundtrip_and_actual_winding(
    tmp_path: Path,
    columns: int,
    rows: int,
    reverse: bool,
) -> None:
    render = MeshSet([_grid(columns, rows, reverse=reverse)])
    before = geometry_content_hash(render)
    bound = build_binding_v2(render)
    assert geometry_content_hash(render) == before
    assert bound.cage.vertex_count < render.vertex_count * 0.4
    assert bound.report["charts"][0]["winding"] == (-1 if reverse else 1)
    assert bound.report["refinementCount"] == 0
    assert bound.report["maximumLocalResidualMeters"] < 0.03
    paths = _serialize(tmp_path, render)
    decoded = read_binding_v2(paths[2])
    assert decoded == bound.binding
    result = check_rest(*paths, declared_metrics=bound.report)
    assert result["status"] == "pass"
    assert result["restMaximumErrorMeters"] < 2e-7
    assert result["float32ComparisonTolerance"] <= 2e-6
    duplicate = tmp_path / "duplicate.bin"
    write_binding_v2(duplicate, decoded)
    assert duplicate.read_bytes() == paths[2].read_bytes()


def test_reordered_vertices_and_faces_keep_correspondence() -> None:
    mesh = _grid()
    order = list(range(len(mesh.vertices)))
    random.Random(149).shuffle(order)
    remap = {old: new for new, old in enumerate(order)}
    shuffled = replace(
        mesh,
        vertices=[mesh.vertices[i] for i in order],
        panel_uvs=[mesh.panel_uvs[i] for i in order],
        triangles=[tuple(remap[i] for i in tri) for tri in reversed(mesh.triangles)],
    )
    original, reordered = build_binding_v2(MeshSet([mesh])), build_binding_v2(MeshSet([shuffled]))
    assert original.cage == reordered.cage
    assert reordered.binding.records == tuple(original.binding.records[i] for i in order)
    assert reordered.report["restMaximumErrorMeters"] < 2e-7


def test_local_residual_follows_rigid_cage_frame() -> None:
    render = MeshSet([_grid()])
    bound = build_binding_v2(render)
    assert max(abs(r.local_residual[0]) for r in bound.binding.records) > 0.001
    assert max(abs(r.local_residual[1]) for r in bound.binding.records) > 0.001
    assert max(abs(r.local_residual[2]) for r in bound.binding.records) > 1e-5
    cm = bound.cage.meshes[0]
    moved = MeshSet(
        [replace(cm, vertices=[(-z + 0.1, y + 0.2, x - 0.3) for x, y, z in cm.vertices])]
    )
    positions = reconstruct_v2(moved, bound.binding)
    expected = [(-z + 0.1, y + 0.2, x - 0.3) for x, y, z in render.meshes[0].vertices]
    assert max(math.dist(a, b) for a, b in zip(positions, expected, strict=True)) < 2e-7


@pytest.mark.parametrize("transformed", [False, True])
def test_metric_refinement_selectively_retains_broad_intervals(
    tmp_path: Path, transformed: bool
) -> None:
    mesh = _grid(9, 9)
    xs = (-0.22, -0.195, -0.17, -0.105, -0.04, 0.025, 0.09, 0.115, 0.14)
    mesh = replace(mesh, vertices=[(x, r * 0.075, 0.0) for r in range(9) for x in xs])
    if transformed:
        order = list(reversed(range(len(mesh.vertices))))
        remap = {old: new for new, old in enumerate(order)}
        mesh = replace(
            mesh,
            name="unrelated-name",
            panel_id="unrelated-semantic-panel",
            vertices=[(-mesh.vertices[i][1], 0.0, mesh.vertices[i][0]) for i in order],
            panel_uvs=[mesh.panel_uvs[i] for i in order],
            triangles=[tuple(remap[i] for i in t) for t in reversed(mesh.triangles)],
        )
    render = MeshSet([mesh])
    before = geometry_content_hash(render)
    bound = build_binding_v2(render)
    chart = bound.report["charts"][0]
    assert chart["retainedRowIndices"] == [0, 2, 4, 6, 8]
    assert chart["retainedColumnIndices"] == [0, 2, 3, 4, 5, 6, 8]
    assert chart["refinedAxis"] == "columns"
    assert bound.report["refinementCount"] == 10
    assert bound.cage.vertex_count == 35 < render.vertex_count * 0.6
    assert geometry_content_hash(render) == before
    assert check_rest(*_serialize(tmp_path, render))["status"] == "pass"


def test_metric_refinement_rejects_over_budget_instead_of_dense_fallback() -> None:
    mesh = _grid(4, 4)
    mesh = replace(mesh, vertices=[(2 * x, 2 * y, z) for x, y, z in mesh.vertices])
    with pytest.raises(ValueError, match="refinement_reduction_budget"):
        build_binding_v2(MeshSet([mesh]))


def test_layers_remain_separate_and_boundary_weights_are_restricted(tmp_path: Path) -> None:
    a = _grid()
    b = replace(
        _grid(reverse=True),
        panel_id="arbitrary.second-layer",
        material_id="cloth.layer-B",
        vertices=[(x, y, z + 0.0001) for x, y, z in a.vertices],
    )
    paths = _serialize(tmp_path, MeshSet([a, b]))
    assert check_rest(*paths)["status"] == "pass"
    binding = read_binding_v2(paths[2])
    for i, record in enumerate(binding.records):
        assert record.panel_table_index == int(i >= len(a.vertices))
    _mutate_record(paths[2], 0, "<I", binding.panels[0].cage_triangle_count)
    with pytest.raises(ValueError, match="cross_panel"):
        check_rest(*paths)


def test_checker_does_not_call_producer_reconstruction_or_decoder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _serialize(tmp_path, MeshSet([_grid()]))

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("producer path used by checker")

    monkeypatch.setattr(producer, "reconstruct_v2", forbidden)
    monkeypatch.setattr(producer, "read_binding_v2", forbidden)
    assert check_rest(*paths)["independentReconstruction"] is True


def test_changed_cage_detected_even_after_geometry_identity_rehashed(tmp_path: Path) -> None:
    cp, rp, bp = _serialize(tmp_path, MeshSet([_grid()]))
    cage = read_glb_meshset(cp)
    moved = MeshSet(
        [replace(m, vertices=[(x, y, z + 0.02) for x, y, z in m.vertices]) for m in cage.meshes]
    )
    write_indexed_glb(cp, moved, "moved", (1.0, 0.0, 0.0, 1.0))
    with pytest.raises(ValueError, match="cage_geometry_mismatch"):
        check_rest(cp, rp, bp)
    binding = replace(read_binding_v2(bp), simulation_geometry_hash=geometry_content_hash(moved))
    write_binding_v2(bp, binding)
    report = check_rest(cp, rp, bp)
    assert report["status"] == "fail"
    assert report["restMaximumErrorMeters"] > 0.0199


def test_topology_mismatch(tmp_path: Path) -> None:
    cp, rp, bp = _serialize(tmp_path, MeshSet([_grid()]))
    cage = read_glb_meshset(cp)
    modified = MeshSet([replace(m, triangles=list(reversed(m.triangles))) for m in cage.meshes])
    write_indexed_glb(cp, modified, "changed", (1.0, 0.0, 0.0, 1.0))
    with pytest.raises(ValueError, match="cage_topology_mismatch"):
        check_rest(cp, rp, bp)
    with pytest.raises(ValueError, match="cage_topology_mismatch"):
        reconstruct_v2(modified, read_binding_v2(bp))


@pytest.mark.parametrize(
    ("offset", "value", "reason"),
    [
        (8, -0.1, "invalid_weights"),
        (8, 0.5, "invalid_weights"),
        (8, float("nan"), "invalid_weights"),
        (8, float("inf"), "invalid_weights"),
        (20, 0.031, "residual_budget"),
        (24, -0.031, "residual_budget"),
        (28, 0.031, "residual_budget"),
        (28, float("nan"), "residual_budget"),
    ],
)
def test_corrupt_weights_and_each_offset_axis(
    tmp_path: Path,
    offset: int,
    value: float,
    reason: str,
) -> None:
    paths = _serialize(tmp_path, MeshSet([_grid()]))
    _mutate_record(paths[2], offset, "<f", value)
    with pytest.raises(ValueError, match=reason):
        check_rest(*paths)
    with pytest.raises(ValueError, match=reason):
        read_binding_v2(paths[2])


def test_missing_render_vertex_and_wrong_binding_count(tmp_path: Path) -> None:
    mesh = _grid()
    cp, rp, bp = _serialize(tmp_path, MeshSet([mesh]))
    raw = bytearray(bp.read_bytes())
    struct.pack_into("<I", raw, 20, len(mesh.vertices) - 1)
    bp.write_bytes(raw)
    with pytest.raises(ValueError, match="binding_count_mismatch"):
        check_rest(cp, rp, bp)
    cp, rp, bp = _serialize(tmp_path, MeshSet([mesh]))
    shorter = replace(
        mesh,
        vertices=mesh.vertices[:-1],
        panel_uvs=mesh.panel_uvs[:-1],
        triangles=[t for t in mesh.triangles if len(mesh.vertices) - 1 not in t],
    )
    write_indexed_glb(rp, MeshSet([shorter]), "short", (1.0, 0.0, 0.0, 1.0))
    with pytest.raises(ValueError, match="mesh_count_mismatch"):
        check_rest(cp, rp, bp)


def test_forged_rest_metrics_rejected_despite_rehashed_manifest(tmp_path: Path) -> None:
    paths = _serialize(tmp_path, MeshSet([_grid()]))
    # Make a geometrically failed package, then forge a passing summary and rehash it.
    _mutate_record(paths[2], 28, "<f", 0.012)
    actual = check_rest(*paths)
    assert actual["status"] == "fail"
    fake = {"restMaximumErrorMeters": 0.0, "restP95ErrorMeters": 0.0}
    manifest = {
        "restMetrics": fake,
        "bindingSha256": hashlib.sha256(paths[2].read_bytes()).hexdigest(),
    }
    manifest["digest"] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    assert len(manifest["digest"]) == 64
    with pytest.raises(ValueError, match="declared_rest_metric_mismatch"):
        check_rest(*paths, declared_metrics=fake)
    with pytest.raises(ValueError, match="declared_rest_metrics_missing"):
        check_rest(*paths, declared_metrics={})


def test_float_tolerance_does_not_relax_rest_threshold(tmp_path: Path) -> None:
    paths = _serialize(tmp_path, MeshSet([_grid()]))
    _mutate_record(paths[2], 28, "<f", 0.008001)
    result = check_rest(*paths)
    assert 0.008 < result["restMaximumErrorMeters"] < 0.008002
    assert result["status"] == "fail"


@pytest.mark.parametrize(
    "kind", ["hole", "reversed_face", "duplicate_face", "nonlocal_face", "no_uv"]
)
def test_unsupported_topology_rejected_clearly(kind: str) -> None:
    m = _grid()
    triangles = list(m.triangles)
    if kind == "hole":
        triangles.pop()
    elif kind == "reversed_face":
        a, b, c = triangles[0]
        triangles[0] = (a, c, b)
    elif kind == "duplicate_face":
        triangles[-1] = triangles[0]
    elif kind == "nonlocal_face":
        triangles[0] = (0, 1, len(m.vertices) - 1)
    else:
        m = replace(m, panel_uvs=[(0.0, 0.0)] * len(m.vertices))
    with pytest.raises(ValueError, match="binding_v2_(unsupported|inconsistent|ambiguous)"):
        build_binding_v2(MeshSet([replace(m, triangles=triangles)]))


def test_offset_and_input_memory_budgets_are_enforced() -> None:
    m = _grid()
    spike = replace(
        m,
        vertices=[(x * (4 if i // 7 == 3 else 1), y, z) for i, (x, y, z) in enumerate(m.vertices)],
    )
    with pytest.raises(ValueError, match="residual_budget"):
        build_binding_v2(MeshSet([spike]))
    with pytest.raises(ValueError, match="mesh_budget"):
        build_binding_v2(MeshSet([m] * 200))


def test_boundary_mask_corruption_and_duplicate_panel_rejected(tmp_path: Path) -> None:
    paths = _serialize(tmp_path, MeshSet([_grid()]))
    _mutate_record(paths[2], 32, "<I", 0)
    with pytest.raises(ValueError, match="boundary_influence_mismatch"):
        check_rest(*paths)
    with pytest.raises(ValueError, match="duplicate_panel"):
        build_binding_v2(MeshSet([_grid(), _grid()]))


def test_binding_topology_identity_is_shared_helper() -> None:
    render = MeshSet([_grid()])
    bound = build_binding_v2(render)
    assert bound.binding.render_topology_hash == topology_hash(render)
    assert bound.binding.simulation_topology_hash == topology_hash(bound.cage)


def test_closest_point_is_geometric_not_index_interpolation() -> None:
    mesh = _grid()
    mesh = replace(mesh, vertices=[(x, y, 0.0) for x, y, _ in mesh.vertices])
    bound = build_binding_v2(MeshSet([mesh]))
    # The width kink changes physical spacing without changing row/column indices.
    # Interior vertices still project exactly onto the plane, unlike index weights.
    record = bound.binding.records[3 * 7 + 1]
    assert record.boundary_mask == 0
    assert math.sqrt(sum(x * x for x in record.local_residual)) < 1e-12
    assert any(abs(w - 0.5) > 1e-3 and w > 1e-3 for w in record.weights)


def test_binding_header_budget_is_checked_before_record_allocation(tmp_path: Path) -> None:
    paths = _serialize(tmp_path, MeshSet([_grid()]))
    data = bytearray(paths[2].read_bytes())
    struct.pack_into("<I", data, 20, 0xFFFFFFFF)
    paths[2].write_bytes(data)
    with pytest.raises(ValueError, match="count_budget"):
        read_binding_v2(paths[2])
    with pytest.raises(ValueError, match="count_budget"):
        check_rest(*paths)


def test_changed_render_geometry_is_not_accepted_as_same_rest(tmp_path: Path) -> None:
    cp, rp, bp = _serialize(tmp_path, MeshSet([_grid()]))
    render = read_glb_meshset(rp)
    changed = MeshSet(
        [replace(m, vertices=[(x + 0.0001, y, z) for x, y, z in m.vertices]) for m in render.meshes]
    )
    write_indexed_glb(rp, changed, "changed", (1.0, 0.0, 0.0, 1.0))
    with pytest.raises(ValueError, match="render_geometry_mismatch"):
        check_rest(cp, rp, bp)


def test_unsupported_folded_coarse_chart_is_rejected() -> None:
    mesh = _grid()
    folded = replace(
        mesh,
        vertices=[(x, -y if i // 7 % 2 else y, z) for i, (x, y, z) in enumerate(mesh.vertices)],
    )
    with pytest.raises(ValueError, match="unsupported_folded_chart"):
        build_binding_v2(MeshSet([folded]))


def test_checker_rejects_malformed_glb_with_typed_error(tmp_path: Path) -> None:
    paths = _serialize(tmp_path, MeshSet([_grid()]))
    raw = paths[0].read_bytes()
    json_size = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20 : 20 + json_size])
    doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"] = 999999
    encoded = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary_chunk = raw[20 + json_size :]
    paths[0].write_bytes(
        struct.pack("<III", 0x46546C67, 2, 20 + len(encoded) + len(binary_chunk))
        + struct.pack("<II", len(encoded), 0x4E4F534A)
        + encoded
        + binary_chunk
    )
    with pytest.raises(ValueError, match="malformed_payload"):
        check_rest(*paths)


@pytest.mark.parametrize(
    "source_id",
    [
        "manual-skirt-01",
        "manual-skirt-02",
        "manual-skirt-03",
        "manual-sleeveless-01",
        "manual-sleeveless-02",
        "manual-sleeveless-03",
        "manual-tshirt-01",
        "manual-tshirt-02",
        "manual-tshirt-03",
    ],
)
def test_published_shell_serialized_rest_only(tmp_path: Path, source_id: str) -> None:
    """Saved inputs only: no authoring, package assembly, motion states, or evaluator."""
    root = Path(__file__).resolve().parents[2] / "docs/evidence/manual_provider_c3_v1/packages"
    source = root / source_id
    render_path = source / "render/clean.glb"
    render = read_glb_meshset(render_path)
    old_cage = read_glb_meshset(source / "render/fallback.glb")
    old_binding = read_legacy_binding(source / "binding/hybrid_binding.bin")
    old_triangles = [
        tuple(m.vertices[i] for i in tri) for m in old_cage.meshes for tri in m.triangles
    ]
    old_errors = []
    offset = 0
    for mesh in render.meshes:
        for index, target in enumerate(mesh.vertices):
            record = old_binding.records[offset + index]
            points = old_triangles[record.simulation_triangle_index]
            weights = (
                1 - record.barycentric_u - record.barycentric_v,
                record.barycentric_u,
                record.barycentric_v,
            )
            position = tuple(sum(weights[j] * points[j][k] for j in range(3)) for k in range(3))
            old_errors.append(
                (
                    math.dist(position, target),
                    mesh.panel_id,
                    index,
                    mesh.panel_uvs[index],
                    tuple(target[k] - position[k] for k in range(3)),
                )
            )
        offset += len(mesh.vertices)
    old_worst = max(old_errors)
    bound = build_binding_v2(render)
    cage_path, binding_path = tmp_path / "cage.glb", tmp_path / "local_frame_v2.bin"
    assert bound.report["refinementCount"] == 0
    assert bound.cage.vertex_count == old_cage.vertex_count
    for chart in bound.report["charts"]:
        assert chart["retainedRowIndices"] == producer._axis(chart["rows"])
        assert chart["retainedColumnIndices"] == producer._axis(chart["columns"])
    write_indexed_glb(
        cage_path, bound.cage, "rest-v2-cage", (0.5, 0.5, 0.5, 1.0), normalize_signed_zero=True
    )
    write_binding_v2(binding_path, bound.binding)
    receipt = check_rest(cage_path, render_path, binding_path, bound.report)
    runtime = reconstruct_v2(read_glb_meshset(cage_path), read_binding_v2(binding_path))
    targets = [v for m in render.meshes for v in m.vertices]
    runtime_errors = sorted(math.dist(a, b) for a, b in zip(runtime, targets, strict=True))
    assert receipt["status"] == "pass"
    assert receipt["restMaximumErrorMeters"] < 2e-7
    assert abs(receipt["restMaximumErrorMeters"] - runtime_errors[-1]) < 1e-12
    assert (
        abs(
            receipt["restP95ErrorMeters"]
            - runtime_errors[math.ceil(0.95 * len(runtime_errors)) - 1]
        )
        < 1e-12
    )
    assert receipt["cageVertexRatio"] < 0.28
    print(
        json.dumps(
            {
                "sourceId": source_id,
                "scope": "saved_shell_serialized_rest_only",
                "oldMaximumErrorMeters": old_worst[0],
                "oldP95ErrorMeters": sorted(e[0] for e in old_errors)[
                    math.ceil(0.95 * len(old_errors)) - 1
                ],
                "oldWorstPanel": old_worst[1],
                "oldWorstLocalVertex": old_worst[2],
                "oldWorstUv": old_worst[3],
                "oldWorstResidual": old_worst[4],
                "maximumStoredResidualMeters": bound.report["maximumLocalResidualMeters"],
                "bindingBytes": binding_path.stat().st_size,
                "cageBytes": cage_path.stat().st_size,
                **receipt,
            },
            sort_keys=True,
        )
    )
