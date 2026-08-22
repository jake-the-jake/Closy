from __future__ import annotations

from closy_forge.binding.binary_format import HEADER_SIZE, RECORD_STRUCT
from closy_forge.cli.main import EXIT_VALIDATION_FAILURE, main
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.validation.validator import validate_package
from tests.helpers import build_demo, clone_package, issue_codes, read_json, write_json


def test_unsupported_schema_version_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = build_demo(tmp_path)
    corrupt = clone_package(package, tmp_path / "bad_schema.closygarment")
    manifest = read_json(corrupt / "manifest.json")
    manifest["schemaVersion"] = 99
    write_json(corrupt / "manifest.json", manifest)
    report = validate_package(corrupt)
    assert "unsupported_schema_version" in issue_codes(report)
    assert main(["validate", str(corrupt), "--json"]) == EXIT_VALIDATION_FAILURE


def test_missing_required_file_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "missing_glb.closygarment")
    (corrupt / "render" / "fallback.glb").unlink()
    report = validate_package(corrupt)
    assert {"required_file_missing", "missing_declared_file"} & issue_codes(report)


def test_file_hash_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "hash_mismatch.closygarment")
    pattern = read_json(corrupt / "pattern" / "pattern.json")
    pattern["parameters"]["body_ease"] = 0.111
    write_json(corrupt / "pattern" / "pattern.json", pattern)
    assert "file_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_unsafe_inventory_path_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "unsafe_path.closygarment")
    manifest = read_json(corrupt / "manifest.json")
    manifest["inventory"].append({"path": "../evil.json", "sha256": "0" * 64})
    write_json(corrupt / "manifest.json", manifest)
    assert "unsafe_package_path" in issue_codes(validate_package(corrupt))


def test_escaping_symlink_is_rejected_when_supported(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "symlink.closygarment")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = corrupt / "avatar" / "escape.txt"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError):
        return
    assert "escaping_symlink" in issue_codes(validate_package(corrupt))


def test_duplicate_panel_id_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "duplicate_panel.closygarment")
    pattern = read_json(corrupt / "pattern" / "pattern.json")
    pattern["panels"].append(pattern["panels"][0])
    write_json(corrupt / "pattern" / "pattern.json", pattern)
    assert "duplicate_panel_id" in issue_codes(validate_package(corrupt))


def test_duplicate_seam_id_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "duplicate_seam.closygarment")
    pattern = read_json(corrupt / "pattern" / "pattern.json")
    pattern["seams"].append(pattern["seams"][0])
    write_json(corrupt / "pattern" / "pattern.json", pattern)
    assert "duplicate_seam_id" in issue_codes(validate_package(corrupt))


def test_dangling_component_panel_reference_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "dangling_component.closygarment")
    semantic = read_json(corrupt / "semantic" / "garment_graph.json")
    semantic["components"][0]["panels"][0] = "panel.missing"
    write_json(corrupt / "semantic" / "garment_graph.json", semantic)
    assert "dangling_component_panel_reference" in issue_codes(validate_package(corrupt))


def test_dangling_seam_reference_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "dangling_seam.closygarment")
    pattern = read_json(corrupt / "pattern" / "pattern.json")
    pattern["seams"][0]["spans"][0]["edgeId"] = "edge.missing"
    write_json(corrupt / "pattern" / "pattern.json", pattern)
    assert "dangling_seam_reference" in issue_codes(validate_package(corrupt))


def test_self_intersecting_panel_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "self_intersection.closygarment")
    pattern = read_json(corrupt / "pattern" / "pattern.json")
    pattern["panels"][0]["boundary"] = [
        {"id": "edge.a", "curve": {"type": "line", "points": [[0, 0], [1, 1]]}, "sampleCount": 2},
        {"id": "edge.b", "curve": {"type": "line", "points": [[1, 1], [0, 1]]}, "sampleCount": 2},
        {"id": "edge.c", "curve": {"type": "line", "points": [[0, 1], [1, 0]]}, "sampleCount": 2},
        {"id": "edge.d", "curve": {"type": "line", "points": [[1, 0], [0, 0]]}, "sampleCount": 2},
    ]
    write_json(corrupt / "pattern" / "pattern.json", pattern)
    assert "panel_boundary_self_intersects" in issue_codes(validate_package(corrupt))


def test_invalid_curve_is_rejected_without_traceback(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "invalid_curve.closygarment")
    pattern = read_json(corrupt / "pattern" / "pattern.json")
    pattern["panels"][0]["boundary"][0]["curve"]["type"] = "spline_magic"
    write_json(corrupt / "pattern" / "pattern.json", pattern)
    assert "invalid_curve" in issue_codes(validate_package(corrupt))


def test_incompatible_seam_ease_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_ease.closygarment")
    pattern = read_json(corrupt / "pattern" / "pattern.json")
    pattern["seams"][0]["easeRatio"] = 0.01
    write_json(corrupt / "pattern" / "pattern.json", pattern)
    assert "seam_ease_incompatible" in issue_codes(validate_package(corrupt))


def test_filled_required_opening_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "filled_opening.closygarment")
    pattern = read_json(corrupt / "pattern" / "pattern.json")
    pattern["openings"][0]["status"] = "filled"
    write_json(corrupt / "pattern" / "pattern.json", pattern)
    assert "required_opening_filled" in issue_codes(validate_package(corrupt))


def test_nonfinite_pattern_value_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "nan.closygarment")
    pattern = read_json(corrupt / "pattern" / "pattern.json")
    pattern["panels"][0]["boundary"][0]["curve"]["points"][0][0] = float("nan")
    (corrupt / "pattern" / "pattern.json").write_text(canonical_dumps(pattern), encoding="utf-8")
    assert "nonfinite_numeric_value" in issue_codes(validate_package(corrupt))


def test_invalid_constraint_vertex_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "constraint.closygarment")
    constraints = read_json(corrupt / "simulation" / "constraints.json")
    constraints["constraints"][0]["spanA"]["vertexIndex"] = 999999
    write_json(corrupt / "simulation" / "constraints.json", constraints)
    assert "invalid_constraint_vertex" in issue_codes(validate_package(corrupt))


def test_missing_pattern_coordinates_are_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "missing_uvs.closygarment")
    mesh_manifest = read_json(corrupt / "simulation" / "mesh_manifest.json")
    del mesh_manifest["meshes"][0]["panelUvs"]
    write_json(corrupt / "simulation" / "mesh_manifest.json", mesh_manifest)
    assert "mesh_manifest_invalid" in issue_codes(validate_package(corrupt))


def test_degenerate_triangle_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "degenerate_tri.closygarment")
    mesh_manifest = read_json(corrupt / "simulation" / "mesh_manifest.json")
    mesh_manifest["meshes"][0]["triangles"][0] = [0, 0, 1]
    write_json(corrupt / "simulation" / "mesh_manifest.json", mesh_manifest)
    assert {"mesh_nonfinite_or_invalid", "degenerate_triangle"} & issue_codes(
        validate_package(corrupt)
    )


def test_bad_binding_magic_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_magic.closygarment")
    binding_path = corrupt / "binding" / "sim_to_render.bin"
    data = bytearray(binding_path.read_bytes())
    data[0:8] = b"NOTBIND!"
    binding_path.write_bytes(bytes(data))
    assert "binding_invalid" in issue_codes(validate_package(corrupt))


def test_bad_binding_version_or_stride_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_stride.closygarment")
    binding_path = corrupt / "binding" / "sim_to_render.bin"
    data = bytearray(binding_path.read_bytes())
    data[16:20] = (99).to_bytes(4, byteorder="little")
    binding_path.write_bytes(bytes(data))
    assert "binding_invalid" in issue_codes(validate_package(corrupt))


def test_invalid_binding_triangle_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_tri.closygarment")
    binding_path = corrupt / "binding" / "sim_to_render.bin"
    data = bytearray(binding_path.read_bytes())
    record = RECORD_STRUCT.pack(999999, 0.0, 0.0, 0.0, 0, 0)
    data[HEADER_SIZE : HEADER_SIZE + RECORD_STRUCT.size] = record
    binding_path.write_bytes(bytes(data))
    assert "binding_triangle_out_of_range" in issue_codes(validate_package(corrupt))


def test_invalid_binding_barycentric_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_bary.closygarment")
    binding_path = corrupt / "binding" / "sim_to_render.bin"
    data = bytearray(binding_path.read_bytes())
    record = RECORD_STRUCT.pack(0, 0.8, 0.8, 0.0, 0, 0)
    data[HEADER_SIZE : HEADER_SIZE + RECORD_STRUCT.size] = record
    binding_path.write_bytes(bytes(data))
    assert "binding_barycentric_invalid" in issue_codes(validate_package(corrupt))


def test_binding_topology_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "binding_topology.closygarment")
    manifest = read_json(corrupt / "binding" / "binding_manifest.json")
    manifest["simulationTopologyHash"] = "0" * 64
    write_json(corrupt / "binding" / "binding_manifest.json", manifest)
    assert "binding_sim_topology_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_render_topology_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "render_topology.closygarment")
    manifest = read_json(corrupt / "binding" / "binding_manifest.json")
    manifest["renderTopologyHash"] = "0" * 64
    write_json(corrupt / "binding" / "binding_manifest.json", manifest)
    assert "binding_render_topology_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_false_capability_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "false_capability.closygarment")
    manifest = read_json(corrupt / "manifest.json")
    manifest["capabilities"]["zeroOneStaticAvailable"] = True
    write_json(corrupt / "manifest.json", manifest)
    assert "false_zeroone_capability" in issue_codes(validate_package(corrupt))
