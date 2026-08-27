from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import read_binding
from closy_forge.binding.reconstruct import reconstruct_vertices, reconstruction_error
from closy_forge.garments.layered_asymmetric.fitting import hash_layered_asymmetric_fit_report
from closy_forge.garments.layered_asymmetric.motion import hash_layered_asymmetric_motion_report
from closy_forge.geometry.glb_io import audit_glb, read_glb_meshset
from closy_forge.geometry.triangulation import validate_panel_boundary
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file, topology_hash
from closy_forge.package_io.writer import (
    EXCLUDED_FROM_CANONICAL_INVENTORY,
    canonical_package_digest,
    collect_inventory,
)
from closy_forge.raster import decode_png_rgba
from closy_forge.simulation.material_physics import (
    FabricDescriptorError,
    validate_fabric_descriptor,
)
from closy_forge.validation.issues import Severity, ValidationIssue

EXPECTED_FILES = {
    "manifest.json",
    "provenance.json",
    "source/capture_record.json",
    "source/public_fixture/front.png",
    "source/public_fixture/back.png",
    "fitting/layered_asymmetric_fit.json",
    "textures/layered_asymmetric_pbr_report.json",
    "textures/atlas/base_color.png",
    "textures/atlas/normal.png",
    "textures/atlas/roughness.png",
    "textures/atlas/occlusion.png",
    "avatar/avatar_contract.json",
    "avatar/reference_avatar.glb",
    "avatar/collision.glb",
    "semantic/garment_graph.json",
    "pattern/pattern.json",
    "simulation/rest_state.json",
    "simulation/settled_state.json",
    "simulation/constraints.json",
    "simulation/material_presets.json",
    "simulation/material_selection.json",
    "simulation/material_physics.json",
    "simulation/simulation_mesh.glb",
    "simulation/motion_states/lightweight_knit.json",
    "simulation/motion_states/cotton_jersey.json",
    "simulation/motion_states/heavy_jersey.json",
    "simulation/motion_states/lightweight_woven.json",
    "simulation/motion_states/opening_stress.json",
    "render/fallback.glb",
    "render/simulation_fallback.glb",
    "render/materials.json",
    "binding/sim_to_render.bin",
    "binding/binding_manifest.json",
    "reports/material_motion_suite.json",
    "reports/fidelity/source_render_fidelity.json",
    "reports/fidelity/rendered_front.png",
    "reports/fidelity/rendered_back.png",
    "reports/layered_asymmetric_quality.json",
    "reports/package_validation.json",
    "reports/summary.json",
    "reports/summary.md",
}

PANEL_IDS = {
    "panel.layered_asymmetric.inner.front",
    "panel.layered_asymmetric.inner.back",
    "panel.layered_asymmetric.outer.front",
    "panel.layered_asymmetric.outer.back",
}
SEAM_IDS = {
    f"seam.layered_asymmetric.{layer}.{role}.{side}"
    for layer in ("inner", "outer")
    for role, side in (
        ("shoulder", "left"),
        ("shoulder", "right"),
        ("side", "left"),
        ("side", "right"),
    )
}
OPENING_IDS = {
    f"opening.layered_asymmetric.{layer}.{role}"
    for layer in ("inner", "outer")
    for role in ("neck", "hem", "armhole.left", "armhole.right")
}
COMPONENT_IDS = {
    "component.layered_asymmetric.base_layer",
    "component.layered_asymmetric.outer_asymmetric_layer",
}
PRESET_IDS = {
    "material.lightweight_knit_d0_v1",
    "material.cotton_jersey_d0_v1",
    "material.heavy_jersey_d0_v1",
    "material.lightweight_woven_d0_v1",
}


def validate_layered_asymmetric_package(
    package_dir: Path, *, manifest: dict[str, Any] | None = None
) -> dict[str, Any]:
    issues: list[ValidationIssue] = []
    if package_dir.suffix != ".closygarment":
        issues.append(_issue("package_suffix_invalid", "fatal", ".", "Invalid package suffix."))
        return _report(issues)
    try:
        manifest = manifest or read_json(package_dir / "manifest.json")
    except Exception as exc:
        issues.append(_issue("manifest_unreadable", "fatal", "manifest.json", str(exc)))
        return _report(issues)
    _required_files(package_dir, issues)
    if manifest.get("garmentClass") != "layered_asymmetric" or manifest.get("garmentId") != (
        "garment.demo_layered_asymmetric.reference_v1"
    ):
        issues.append(
            _issue(
                "layered_asymmetric_family_mismatch",
                "fatal",
                "manifest.json",
                "LayeredAsymmetric package identity must use the canonical family and garment IDs.",
            )
        )
    if manifest.get("packageKind") != "closy.garment" or manifest.get("schemaVersion") != 1:
        issues.append(
            _issue(
                "layered_asymmetric_manifest_contract_invalid",
                "fatal",
                "manifest.json",
                "LayeredAsymmetric manifest kind/schema is unsupported.",
            )
        )
    if any(
        issue.severity == "fatal" and issue.code == "layered_asymmetric_file_missing"
        for issue in issues
    ):
        return _report(issues)

    try:
        pattern = read_json(package_dir / "pattern/pattern.json")
        semantic = read_json(package_dir / "semantic/garment_graph.json")
        constraints = read_json(package_dir / "simulation/constraints.json")
        fit = read_json(package_dir / "fitting/layered_asymmetric_fit.json")
        presets = read_json(package_dir / "simulation/material_presets.json")
        selection = read_json(package_dir / "simulation/material_selection.json")
        motion = read_json(package_dir / "reports/material_motion_suite.json")
        fidelity = read_json(package_dir / "reports/fidelity/source_render_fidelity.json")
        texture = read_json(package_dir / "textures/layered_asymmetric_pbr_report.json")
        quality = read_json(package_dir / "reports/layered_asymmetric_quality.json")
        binding_manifest = read_json(package_dir / "binding/binding_manifest.json")
    except Exception as exc:
        issues.append(_issue("layered_asymmetric_contract_unreadable", "fatal", ".", str(exc)))
        return _report(issues)

    _validate_pattern_semantics(pattern, semantic, constraints, issues)
    _validate_fit_material_motion(package_dir, fit, presets, selection, motion, issues)
    _validate_geometry_binding(package_dir, binding_manifest, issues)
    _validate_appearance(package_dir, fidelity, texture, issues)
    _validate_quality(quality, pattern, semantic, issues)
    _validate_inventory(package_dir, manifest, issues)
    return _report(issues)


def _required_files(package_dir: Path, issues: list[ValidationIssue]) -> None:
    for relpath in sorted(EXPECTED_FILES):
        if not (package_dir / relpath).is_file():
            issues.append(
                _issue(
                    "layered_asymmetric_file_missing",
                    "fatal",
                    relpath,
                    "Required layered_asymmetric package artifact is missing.",
                )
            )


def _validate_pattern_semantics(
    pattern: dict[str, Any],
    semantic: dict[str, Any],
    constraints: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    panel_ids = {str(item.get("id")) for item in pattern.get("panels", [])}
    seam_ids = {str(item.get("id")) for item in pattern.get("seams", [])}
    opening_ids = {str(item.get("id")) for item in pattern.get("openings", [])}
    semantic_required = semantic.get("requiredIds", {})
    if (
        pattern.get("garmentClass") != "layered_asymmetric"
        or semantic.get("garmentClass") != "layered_asymmetric"
        or panel_ids != PANEL_IDS
        or seam_ids != SEAM_IDS
        or opening_ids != OPENING_IDS
        or set(semantic_required.get("panels", [])) != PANEL_IDS
        or set(semantic_required.get("seams", [])) != SEAM_IDS
        or set(semantic_required.get("openings", [])) != OPENING_IDS
        or set(semantic_required.get("components", [])) != COMPONENT_IDS
    ):
        issues.append(
            _issue(
                "layered_asymmetric_semantic_ids_invalid",
                "fatal",
                "semantic/garment_graph.json",
                "Panel, seam and opening IDs must exactly match the layered_asymmetric ontology.",
            )
        )
    components = semantic.get("components", [])
    layering = semantic.get("layering", {})
    component_by_id = {str(item.get("id")): item for item in components}
    outer_drop = float(pattern.get("parameters", {}).get("outer_asymmetry_drop_meters", 0.0))
    outer_hem_drops = []
    for panel in pattern.get("panels", []):
        if ".outer." not in str(panel.get("id")):
            continue
        hem = next(
            (edge for edge in panel.get("boundary", []) if ".outer.hem." in str(edge.get("id"))),
            None,
        )
        points = [] if hem is None else hem.get("curve", {}).get("points", [])
        if len(points) == 2:
            outer_hem_drops.append(abs(float(points[0][1]) - float(points[1][1])))
    if (
        pattern.get("layerCount") != 2
        or pattern.get("asymmetric") is not True
        or layering.get("layerCount") != 2
        or layering.get("orderedLayerIds")
        != ["layer.layered_asymmetric.inner", "layer.layered_asymmetric.outer"]
        or layering.get("interLayerCollisionEnabled") is not True
        or float(layering.get("minimumClearanceMeters", 0.0)) < 0.008
        or set(component_by_id) != COMPONENT_IDS
        or component_by_id.get("component.layered_asymmetric.base_layer", {}).get("collisionOrder")
        != 10
        or component_by_id.get("component.layered_asymmetric.outer_asymmetric_layer", {}).get(
            "collisionOrder"
        )
        != 20
        or len(outer_hem_drops) != 2
        or outer_drop < 0.04
        or any(abs(drop - outer_drop) > 1e-9 for drop in outer_hem_drops)
    ):
        issues.append(
            _issue(
                "layered_asymmetric_layer_contract_invalid",
                "fatal",
                "semantic/garment_graph.json",
                "Two ordered non-empty layers, collision clearance and literal outer "
                "asymmetry are required.",
            )
        )
    all_ids = (
        panel_ids
        | seam_ids
        | opening_ids
        | set(semantic_required.get("components", []))
        | set(semantic_required.get("panels", []))
        | set(semantic_required.get("seams", []))
        | set(semantic_required.get("openings", []))
    )
    if any(_has_exact_token(identifier, {"sleeve", "cuff"}) for identifier in all_ids):
        issues.append(
            _issue(
                "layered_asymmetric_false_sleeve_semantics",
                "fatal",
                "semantic/garment_graph.json",
                "LayeredAsymmetric family must not retain sleeve or cuff semantic tokens.",
            )
        )
    for panel in pattern.get("panels", []):
        for code in validate_panel_boundary(panel):
            issues.append(
                _issue(code, "fatal", "pattern/pattern.json", "Panel boundary is invalid.")
            )
    for seam in pattern.get("seams", []):
        spans = seam.get("spans", [])
        if len(spans) != 2 or [span.get("orientation") for span in spans] != [
            "forward",
            "reverse",
        ]:
            issues.append(
                _issue(
                    "layered_asymmetric_seam_orientation_invalid",
                    "fatal",
                    "pattern/pattern.json",
                    "Every side/shoulder seam needs forward/reverse pairing.",
                )
            )
    resolved_openings = {
        str(opening.get("id")): opening for opening in constraints.get("openings", [])
    }
    if set(resolved_openings) != OPENING_IDS or any(
        len(opening.get("boundaryEdges", [])) != 2
        or any(edge.get("status") != "resolved" for edge in opening.get("boundaryEdges", []))
        for opening in resolved_openings.values()
    ):
        issues.append(
            _issue(
                "layered_asymmetric_opening_loop_invalid",
                "fatal",
                "simulation/constraints.json",
                "Neck, hem and both armholes must resolve to two-panel boundary loops.",
            )
        )
    if {str(item.get("id")) for item in constraints.get("seams", [])} != SEAM_IDS or any(
        item.get("orientation") != ["forward", "reverse"]
        for item in constraints.get("constraints", [])
    ):
        issues.append(
            _issue(
                "layered_asymmetric_constraint_pairing_invalid",
                "fatal",
                "simulation/constraints.json",
                "Persisted constraints must preserve all seam pairings and orientation.",
            )
        )


def _validate_fit_material_motion(
    package_dir: Path,
    fit: dict[str, Any],
    presets: dict[str, Any],
    selection: dict[str, Any],
    motion: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    if (
        fit.get("integrity", {}).get("fitReportHash") != hash_layered_asymmetric_fit_report(fit)
        or fit.get("candidateCount") != 25
        or fit.get("accepted") is not True
        or fit.get("learnedFitRun") is not False
    ):
        issues.append(
            _issue(
                "layered_asymmetric_fit_integrity_invalid",
                "fatal",
                "fitting/layered_asymmetric_fit.json",
                "Bounded 25-candidate public fitting evidence is invalid.",
            )
        )
    descriptors = presets.get("presets", [])
    try:
        for descriptor in descriptors:
            validate_fabric_descriptor(descriptor)
    except FabricDescriptorError as exc:
        issues.append(
            _issue(
                "layered_asymmetric_material_descriptor_invalid",
                "fatal",
                "simulation/material_presets.json",
                str(exc),
            )
        )
    preset_ids = {str(item.get("presetId")) for item in descriptors}
    if (
        preset_ids != PRESET_IDS
        or presets.get("integrity", {}).get("registryHash")
        != _hash_blank_integrity(presets, "registryHash")
        or selection.get("integrity", {}).get("selectionHash")
        != _hash_blank_integrity(selection, "selectionHash")
        or selection.get("selection", {}).get("selectedPresetId") != "material.cotton_jersey_d0_v1"
    ):
        issues.append(
            _issue(
                "layered_asymmetric_material_selection_invalid",
                "fatal",
                "simulation/material_selection.json",
                "Preset registry/selection must be intact and select cotton jersey from cues.",
            )
        )
    records = motion.get("presetRecords", [])
    state_names = {
        "material.lightweight_knit_d0_v1": "lightweight_knit.json",
        "material.cotton_jersey_d0_v1": "cotton_jersey.json",
        "material.heavy_jersey_d0_v1": "heavy_jersey.json",
        "material.lightweight_woven_d0_v1": "lightweight_woven.json",
    }
    state_references_are_valid = True
    for index, record in enumerate(records):
        preset_id = str(record.get("presetId"))
        state_name = state_names.get(preset_id)
        if state_name is None:
            state_references_are_valid = False
            continue
        state = read_json(package_dir / "simulation/motion_states" / state_name)
        expected_ref = f"reports/material_motion_suite.json#/presetRecords/{index}/diagnostics"
        state_references_are_valid = state_references_are_valid and (
            state.get("diagnosticsRef") == expected_ref
            and state.get("sourceContentHash") is not None
            and isinstance(record.get("diagnostics"), dict)
            and bool(record["diagnostics"])
        )
    stress_state = read_json(package_dir / "simulation/motion_states/opening_stress.json")
    state_references_are_valid = state_references_are_valid and (
        stress_state.get("diagnosticsRef")
        == "reports/material_motion_suite.json#/underarmStress/diagnostics"
        and stress_state.get("sourceContentHash") is not None
        and isinstance(motion.get("underarmStress", {}).get("diagnostics"), dict)
        and bool(motion["underarmStress"]["diagnostics"])
    )
    if (
        motion.get("integrity", {}).get("suiteHash")
        != hash_layered_asymmetric_motion_report(motion)
        or {str(item.get("presetId")) for item in records} != PRESET_IDS
        or not all(item.get("actualSolverRun") is True for item in records)
        or not all(item.get("armholeMetrics", {}).get("armholeCount") == 4 for item in records)
        or not all(
            item.get("armholeMetrics", {}).get("collapsedArmholeCount") == 0 for item in records
        )
        or motion.get("crossPreset", {}).get("allFourPresetsExecuted") is not True
        or motion.get("underarmStress", {}).get("actualSolverRun") is not True
        or motion.get("underarmStress", {}).get("accepted") is not True
        or not state_references_are_valid
    ):
        issues.append(
            _issue(
                "layered_asymmetric_motion_suite_invalid",
                "fatal",
                "reports/material_motion_suite.json",
                "Four-preset motion and accepted underarm/armhole stress evidence is required.",
            )
        )


def _validate_geometry_binding(
    package_dir: Path,
    binding_manifest: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    try:
        sim_path = package_dir / "simulation/simulation_mesh.glb"
        render_path = package_dir / "render/fallback.glb"
        fallback_path = package_dir / "render/simulation_fallback.glb"
        for path in (sim_path, render_path, fallback_path):
            audit = audit_glb(path)
            if audit.get("validGlb20") is not True or audit.get("hasVec4Tangents") is not True:
                raise ValueError("conventional_glb_audit_failed")
        simulation = read_glb_meshset(sim_path)
        render = read_glb_meshset(render_path)
        fallback = read_glb_meshset(fallback_path)
        binding = read_binding(package_dir / "binding/sim_to_render.bin")
        if any(
            record.barycentric_u < -1e-7
            or record.barycentric_v < -1e-7
            or record.barycentric_u + record.barycentric_v > 1.0000001
            or record.panel_table_index >= binding.panel_count
            for record in binding.records
        ):
            raise ValueError("binding_record_outside_triangle_or_panel_table")
        reconstructed = reconstruct_vertices(simulation, binding)
        maximum, rms = reconstruction_error(render, reconstructed)
        if (
            topology_hash(simulation) != binding.simulation_topology_hash
            or topology_hash(render) != binding.render_topology_hash
            or binding_manifest.get("authority") != "binding/sim_to_render.bin"
            or binding_manifest.get("fallbackUsesDenseBinding") is not False
            or maximum > 1e-6
            or rms > 1e-6
            or topology_hash(fallback) != topology_hash(simulation)
            or fallback.vertex_count != simulation.vertex_count
            or render.vertex_count <= simulation.vertex_count
        ):
            raise ValueError("persisted_binding_or_fallback_mismatch")
    except Exception as exc:
        issues.append(
            _issue(
                "layered_asymmetric_binding_validation_failed",
                "fatal",
                "binding/sim_to_render.bin",
                str(exc),
            )
        )


def _validate_appearance(
    package_dir: Path,
    fidelity: dict[str, Any],
    texture: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    paths = [
        "source/public_fixture/front.png",
        "source/public_fixture/back.png",
        "reports/fidelity/rendered_front.png",
        "reports/fidelity/rendered_back.png",
        "textures/atlas/base_color.png",
        "textures/atlas/normal.png",
        "textures/atlas/roughness.png",
        "textures/atlas/occlusion.png",
    ]
    try:
        decoded = [decode_png_rgba((package_dir / path).read_bytes()) for path in paths]
        if any(item.width <= 0 or item.height <= 0 or not any(item.rgba[3::4]) for item in decoded):
            raise ValueError("blank_or_invalid_decoded_png")
        if (
            fidelity.get("decodedPixelComparisonRun") is not True
            or fidelity.get("acceptedForD0LayeredAsymmetricFixture") is not True
            or len(fidelity.get("viewComparisons", [])) != 2
            or not all(
                view.get("accepted") is True
                and int(view.get("metrics", {}).get("sourceForegroundPixels", 0)) > 0
                and int(view.get("metrics", {}).get("renderForegroundPixels", 0)) > 0
                for view in fidelity.get("viewComparisons", [])
            )
            or texture.get("decodedPbrMapsPersisted") is not True
            or len(texture.get("maps", [])) != 4
        ):
            raise ValueError("decoded_appearance_evidence_not_accepted")
    except Exception as exc:
        issues.append(
            _issue(
                "layered_asymmetric_appearance_validation_failed",
                "fatal",
                "reports/fidelity/source_render_fidelity.json",
                str(exc),
            )
        )


def _validate_quality(
    quality: dict[str, Any],
    pattern: dict[str, Any],
    semantic: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    readiness = quality.get("readiness", {})
    layering = quality.get("layering", {})
    if (
        readiness.get("layeredAsymmetricD0Complete") is not True
        or readiness.get("phase8FamilyLadderComplete") is not True
        or readiness.get("phase8GloballyComplete") is not False
        or readiness.get("nextBlueprintPhase") != "phase9_editor_export_regression"
        or quality.get("topology", {}).get("hasSleeveOrCuffSemantics") is not False
        or quality.get("topology", {}).get("panelCount") != 4
        or quality.get("topology", {}).get("seamCount") != 8
        or quality.get("topology", {}).get("openingCount") != 8
        or layering.get("layerCount") != 2
        or layering.get("innerPanelCount") != 2
        or layering.get("outerPanelCount") != 2
        or layering.get("interLayerCollisionEnabled") is not True
        or layering.get("orderedCollisionLayers") != [10, 20]
        or float(layering.get("restFrontClearanceMeters", 0.0))
        < float(pattern.get("parameters", {}).get("layer_clearance_meters", 1.0))
        or layering.get("outerAsymmetricHemDropMeters")
        != pattern.get("parameters", {}).get("outer_asymmetry_drop_meters")
        or semantic.get("layering", {}).get("interLayerCollisionEnabled") is not True
    ):
        issues.append(
            _issue(
                "layered_asymmetric_quality_claim_invalid",
                "fatal",
                "reports/layered_asymmetric_quality.json",
                "D0 family completion and global Phase 8 partial status must be truthful.",
            )
        )


def _validate_inventory(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    actual = collect_inventory(package_dir, exclude=EXCLUDED_FROM_CANONICAL_INVENTORY)
    declared = manifest.get("inventory", [])
    actual_map = {str(item["path"]): item for item in actual}
    declared_map = {str(item.get("path")): item for item in declared if isinstance(item, dict)}
    if set(actual_map) != set(declared_map):
        issues.append(
            _issue(
                "layered_asymmetric_inventory_file_set_mismatch",
                "fatal",
                "manifest.json",
                "Manifest inventory does not exactly match persisted canonical files.",
            )
        )
        return
    for relpath, actual_entry in actual_map.items():
        declared_entry = declared_map[relpath]
        if (
            declared_entry.get("sha256") != actual_entry["sha256"]
            or declared_entry.get("byteSize") != actual_entry["byteSize"]
            or sha256_file(package_dir / relpath) != actual_entry["sha256"]
        ):
            issues.append(
                _issue(
                    "layered_asymmetric_inventory_hash_mismatch",
                    "fatal",
                    relpath,
                    "Persisted bytes do not match manifest inventory hash/size.",
                )
            )
    if manifest.get("packageDigest") != canonical_package_digest(actual):
        issues.append(
            _issue(
                "layered_asymmetric_package_digest_mismatch",
                "fatal",
                "manifest.json",
                "Canonical package digest does not match inventoried bytes.",
            )
        )


def _hash_blank_integrity(report: dict[str, Any], field: str) -> str:
    payload = deepcopy(report)
    payload["integrity"][field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _has_exact_token(identifier: str, forbidden: set[str]) -> bool:
    tokens = identifier.replace("_", ".").replace("-", ".").split(".")
    return any(token in forbidden for token in tokens)


def _issue(code: str, severity: Severity, path: str, message: str) -> ValidationIssue:
    return ValidationIssue(
        code,
        severity,
        path,
        message,
        "Regenerate the layered_asymmetric fixture from canonical Forge inputs.",
    )


def _report(issues: list[ValidationIssue]) -> dict[str, Any]:
    counts = {
        severity: sum(issue.severity == severity for issue in issues)
        for severity in ("info", "warning", "error", "fatal")
    }
    return {
        "schemaVersion": 1,
        "status": "failed" if counts["error"] or counts["fatal"] else "passed",
        "counts": counts,
        "issues": [issue.to_json() for issue in issues],
    }
