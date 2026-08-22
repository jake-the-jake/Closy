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


def test_non_converged_cloth_settle_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_settle.closygarment")
    diagnostics = read_json(corrupt / "simulation" / "settle_diagnostics.json")
    diagnostics["convergenceState"] = "failed"
    write_json(corrupt / "simulation" / "settle_diagnostics.json", diagnostics)
    assert "cloth_settle_not_converged" in issue_codes(validate_package(corrupt))


def test_settled_state_hash_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_settled_hash.closygarment")
    state = read_json(corrupt / "simulation" / "settled_state.json")
    state["meshContentHash"] = "0" * 64
    write_json(corrupt / "simulation" / "settled_state.json", state)
    assert "settled_state_content_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_cloth_settle_material_contradiction_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_material_settle.closygarment")
    material = read_json(corrupt / "simulation" / "material_physics.json")
    material["clothSettleRun"] = False
    write_json(corrupt / "simulation" / "material_physics.json", material)
    assert "cloth_settle_material_contradiction" in issue_codes(validate_package(corrupt))


def test_capture_provider_policy_violation_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_capture_policy.closygarment")
    record = read_json(corrupt / "source" / "capture_record.json")
    record["privacy"]["allowExternalApis"] = True
    write_json(corrupt / "source" / "capture_record.json", record)
    assert "capture_provider_policy_violation" in issue_codes(validate_package(corrupt))


def test_capture_record_hash_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_capture_hash.closygarment")
    record = read_json(corrupt / "source" / "capture_record.json")
    record["views"][0]["qualityMeasurements"]["garmentCoverage"] = 0.10
    write_json(corrupt / "source" / "capture_record.json", record)
    assert "capture_record_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_capture_quality_source_hash_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(
        build_demo(tmp_path), tmp_path / "bad_capture_quality_hash.closygarment"
    )
    quality = read_json(corrupt / "source" / "capture_quality.json")
    quality["sourceRecordHash"] = "0" * 64
    write_json(corrupt / "source" / "capture_quality.json", quality)
    assert "capture_quality_source_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_capture_quality_failure_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_capture_quality.closygarment")
    quality = read_json(corrupt / "source" / "capture_quality.json")
    quality["overallStatus"] = "fail"
    quality["overallScore"] = 0.01
    write_json(corrupt / "source" / "capture_quality.json", quality)
    codes = issue_codes(validate_package(corrupt))
    assert "capture_quality_not_pass" in codes
    assert "capture_quality_below_threshold" in codes


def test_visual_observation_hash_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_visual_hash.closygarment")
    visual = read_json(corrupt / "source" / "visual_observations.json")
    visual["views"][0]["masks"][0]["confidence"] = 0.01
    write_json(corrupt / "source" / "visual_observations.json", visual)
    assert "visual_observation_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_required_visual_landmark_missing_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "missing_visual_landmark.closygarment")
    visual = read_json(corrupt / "source" / "visual_observations.json")
    for view in visual["views"]:
        view["landmarks"] = [
            landmark for landmark in view["landmarks"] if landmark["id"] != "landmark.neck.center"
        ]
    visual["integrity"]["visualRecordHash"] = "0" * 64
    write_json(corrupt / "source" / "visual_observations.json", visual)
    codes = issue_codes(validate_package(corrupt))
    assert "required_tshirt_visual_landmark_missing" in codes
    assert "visual_observation_hash_mismatch" in codes


def test_correction_policy_violation_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_correction_policy.closygarment")
    correction = read_json(corrupt / "source" / "correction_record.json")
    correction["privacy"]["allowTrainingUse"] = True
    write_json(corrupt / "source" / "correction_record.json", correction)
    assert "correction_policy_violation" in issue_codes(validate_package(corrupt))


def test_tshirt_fit_hash_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_fit_hash.closygarment")
    fit = read_json(corrupt / "fitting" / "tshirt_fit.json")
    fit["fittedParameters"]["garment_body_length"] = 0.74
    write_json(corrupt / "fitting" / "tshirt_fit.json", fit)
    assert "tshirt_fit_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_tshirt_fit_rejection_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_fit_status.closygarment")
    fit = read_json(corrupt / "fitting" / "tshirt_fit.json")
    fit["status"] = "fail"
    fit["accepted"] = False
    write_json(corrupt / "fitting" / "tshirt_fit.json", fit)
    assert "tshirt_fit_not_accepted" in issue_codes(validate_package(corrupt))


def test_tshirt_fit_loss_threshold_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_fit_loss.closygarment")
    fit = read_json(corrupt / "fitting" / "tshirt_fit.json")
    fit["losses"]["landmarkRmsNormalised"] = 0.5
    write_json(corrupt / "fitting" / "tshirt_fit.json", fit)
    assert "tshirt_fit_landmark_loss_too_high" in issue_codes(validate_package(corrupt))


def test_texture_identity_hash_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_texture_hash.closygarment")
    texture = read_json(corrupt / "textures" / "texture_identity.json")
    texture["observedMaterialRegions"][0]["pbr"]["roughnessFactor"] = 0.2
    write_json(corrupt / "textures" / "texture_identity.json", texture)
    assert "texture_identity_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_texture_identity_source_hash_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_texture_source_hash.closygarment")
    texture = read_json(corrupt / "textures" / "texture_identity.json")
    texture["sourceVisualRecordHash"] = "0" * 64
    write_json(corrupt / "textures" / "texture_identity.json", texture)
    assert "texture_identity_visual_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_texture_identity_unknown_material_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_texture_material.closygarment")
    texture = read_json(corrupt / "textures" / "texture_identity.json")
    texture["observedMaterialRegions"][0]["materialId"] = "material.unknown"
    write_json(corrupt / "textures" / "texture_identity.json", texture)
    assert "texture_identity_unknown_material" in issue_codes(validate_package(corrupt))


def test_texture_source_capability_contradiction_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_texture_capability.closygarment")
    manifest = read_json(corrupt / "manifest.json")
    manifest["capabilities"]["sourceImageTextureAvailable"] = True
    write_json(corrupt / "manifest.json", manifest)
    assert "texture_source_capability_contradiction" in issue_codes(validate_package(corrupt))


def test_geometry_proposal_hash_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_proposal_hash.closygarment")
    proposal = read_json(corrupt / "proposals" / "raw_geometry_proposal.json")
    proposal["geometryAudit"]["triangleEstimate"] = 42
    write_json(corrupt / "proposals" / "raw_geometry_proposal.json", proposal)
    assert "geometry_proposal_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_geometry_proposal_provider_policy_violation_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_proposal_policy.closygarment")
    proposal = read_json(corrupt / "proposals" / "raw_geometry_proposal.json")
    proposal["provider"]["runtimeExternalApis"] = True
    write_json(corrupt / "proposals" / "raw_geometry_proposal.json", proposal)
    assert "geometry_proposal_provider_policy_violation" in issue_codes(validate_package(corrupt))


def test_geometry_proposal_domain_violation_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_proposal_domain.closygarment")
    proposal = read_json(corrupt / "proposals" / "raw_geometry_proposal.json")
    proposal["request"]["supportedDomain"] = "generic_object"
    write_json(corrupt / "proposals" / "raw_geometry_proposal.json", proposal)
    assert "geometry_proposal_domain_invalid" in issue_codes(validate_package(corrupt))


def test_geometry_proposal_canonical_acceptance_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_proposal_canonical.closygarment")
    proposal = read_json(corrupt / "proposals" / "raw_geometry_proposal.json")
    proposal["quality"]["acceptedForCanonical"] = True
    write_json(corrupt / "proposals" / "raw_geometry_proposal.json", proposal)
    assert "geometry_proposal_canonical_acceptance_invalid" in issue_codes(
        validate_package(corrupt)
    )


def test_provider_registry_hash_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_registry_hash.closygarment")
    registry = read_json(corrupt / "proposals" / "provider_registry.json")
    registry["selectionReason"] = "tampered"
    write_json(corrupt / "proposals" / "provider_registry.json", registry)
    assert "provider_registry_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_provider_registry_policy_violation_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_registry_policy.closygarment")
    registry = read_json(corrupt / "proposals" / "provider_registry.json")
    registry["providers"][0]["policy"]["runtimeExternalApis"] = True
    write_json(corrupt / "proposals" / "provider_registry.json", registry)
    assert "provider_registry_provider_policy_violation" in issue_codes(validate_package(corrupt))


def test_provider_registry_generic_domain_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_registry_domain.closygarment")
    registry = read_json(corrupt / "proposals" / "provider_registry.json")
    registry["scope"]["allowsGenericObjects"] = True
    write_json(corrupt / "proposals" / "provider_registry.json", registry)
    assert "provider_registry_domain_invalid" in issue_codes(validate_package(corrupt))


def test_provider_registry_manual_rights_violation_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(
        build_demo(tmp_path), tmp_path / "bad_registry_manual_rights.closygarment"
    )
    registry = read_json(corrupt / "proposals" / "provider_registry.json")
    registry["providers"][1]["licence"]["termsReviewed"] = False
    write_json(corrupt / "proposals" / "provider_registry.json", registry)
    assert "provider_registry_manual_rights_unreviewed" in issue_codes(validate_package(corrupt))


def test_geometry_proposal_asset_hash_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_proposal_asset.closygarment")
    proposal = read_json(corrupt / "proposals" / "raw_geometry_proposal.json")
    proposal["rawProposal"]["sourceAssetHash"] = "0" * 64
    write_json(corrupt / "proposals" / "raw_geometry_proposal.json", proposal)
    assert "geometry_proposal_asset_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_raw_geometry_topology_hash_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_raw_topology_hash.closygarment")
    topology = read_json(corrupt / "reports" / "raw_geometry_topology.json")
    topology["topology"]["componentCount"] = 99
    write_json(corrupt / "reports" / "raw_geometry_topology.json", topology)
    assert "raw_geometry_topology_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_raw_geometry_topology_clean_acceptance_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(
        build_demo(tmp_path), tmp_path / "bad_raw_topology_clean_ready.closygarment"
    )
    topology = read_json(corrupt / "reports" / "raw_geometry_topology.json")
    topology["cleanReadiness"]["acceptedForCleanProposal"] = True
    write_json(corrupt / "reports" / "raw_geometry_topology.json", topology)
    codes = issue_codes(validate_package(corrupt))
    assert "raw_geometry_topology_hash_mismatch" in codes
    assert "raw_geometry_topology_clean_acceptance_invalid" in codes


def test_clean_geometry_proposal_hash_mismatch_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_clean_hash.closygarment")
    clean = read_json(corrupt / "proposals" / "clean_geometry_proposal.json")
    clean["cleanGeometryAudit"]["triangleEstimate"] = 12
    write_json(corrupt / "proposals" / "clean_geometry_proposal.json", clean)
    assert "clean_geometry_proposal_hash_mismatch" in issue_codes(validate_package(corrupt))


def test_clean_geometry_proposal_availability_claim_is_rejected(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_clean_available.closygarment")
    clean = read_json(corrupt / "proposals" / "clean_geometry_proposal.json")
    clean["cleanProposal"]["available"] = True
    clean["quality"]["acceptedForCanonical"] = True
    write_json(corrupt / "proposals" / "clean_geometry_proposal.json", clean)
    codes = issue_codes(validate_package(corrupt))
    assert "clean_geometry_proposal_hash_mismatch" in codes
    assert "clean_geometry_proposal_availability_invalid" in codes
    assert "clean_geometry_proposal_canonical_acceptance_invalid" in codes


def test_clean_geometry_proposal_topology_state_claim_is_rejected(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    corrupt = clone_package(build_demo(tmp_path), tmp_path / "bad_clean_topology.closygarment")
    clean = read_json(corrupt / "proposals" / "clean_geometry_proposal.json")
    clean["cleanupPipeline"]["topologyDiagnosticsRun"] = False
    write_json(corrupt / "proposals" / "clean_geometry_proposal.json", clean)
    codes = issue_codes(validate_package(corrupt))
    assert "clean_geometry_proposal_hash_mismatch" in codes
    assert "clean_geometry_proposal_topology_state_invalid" in codes
