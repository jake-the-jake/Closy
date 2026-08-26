from __future__ import annotations

from pathlib import Path
from typing import Any

from closy_forge.garments.simple_dress.fitting import hash_simple_dress_fit_report
from closy_forge.garments.simple_dress.motion import hash_simple_dress_motion_report
from closy_forge.geometry.triangulation import validate_panel_boundary
from closy_forge.package_io.canonical_json import read_json
from closy_forge.validation.issues import ValidationIssue
from closy_forge.validation.vertical_slice_validator import (
    PRESET_IDS,
    issue,
    report,
    require_files,
    validate_appearance,
    validate_geometry_binding,
    validate_inventory,
    validate_material_selection,
)

FAMILY_CODE = "simple_dress"
EXPECTED_FILES = {
    "manifest.json",
    "provenance.json",
    "source/capture_record.json",
    "source/public_fixture/front.png",
    "source/public_fixture/back.png",
    "fitting/simple_dress_fit.json",
    "textures/simple_dress_pbr_report.json",
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
    "reports/simple_dress_quality.json",
    "reports/package_validation.json",
    "reports/summary.json",
    "reports/summary.md",
}
PANEL_IDS = {
    f"panel.simple_dress.{face}.{section}"
    for face in ("front", "back")
    for section in ("bodice", "skirt")
}
SEAM_IDS = {
    f"seam.simple_dress.bodice.{region}.{side}"
    for region in ("shoulder", "side")
    for side in ("left", "right")
} | {
    "seam.simple_dress.waist.front",
    "seam.simple_dress.waist.back",
    "seam.simple_dress.skirt.side.left",
    "seam.simple_dress.skirt.side.right",
}
OPENING_IDS = {
    "opening.simple_dress.neck",
    "opening.simple_dress.hem",
    "opening.simple_dress.armhole.left",
    "opening.simple_dress.armhole.right",
}
PANEL_ROLES = {"front_bodice", "back_bodice", "front_skirt", "back_skirt"}


def validate_simple_dress_package(
    package_dir: Path, *, manifest: dict[str, Any] | None = None
) -> dict[str, Any]:
    issues: list[ValidationIssue] = []
    if package_dir.suffix != ".closygarment":
        issues.append(
            issue("package_suffix_invalid", "fatal", ".", "Invalid package suffix.", FAMILY_CODE)
        )
        return report(issues)
    try:
        manifest = manifest or read_json(package_dir / "manifest.json")
    except Exception as exc:
        issues.append(issue("manifest_unreadable", "fatal", "manifest.json", str(exc), FAMILY_CODE))
        return report(issues)
    require_files(package_dir, EXPECTED_FILES, issues, family_code=FAMILY_CODE)
    if manifest.get("garmentClass") != FAMILY_CODE or manifest.get("garmentId") != (
        "garment.demo_simple_dress.reference_v1"
    ):
        issues.append(
            issue(
                "simple_dress_family_mismatch",
                "fatal",
                "manifest.json",
                "Simple-dress package identity must use canonical family and garment IDs.",
                FAMILY_CODE,
            )
        )
    if manifest.get("packageKind") != "closy.garment" or manifest.get("schemaVersion") != 1:
        issues.append(
            issue(
                "simple_dress_manifest_contract_invalid",
                "fatal",
                "manifest.json",
                "Simple-dress manifest kind/schema is unsupported.",
                FAMILY_CODE,
            )
        )
    if any(item.severity == "fatal" and item.code.endswith("_file_missing") for item in issues):
        return report(issues)
    try:
        pattern = read_json(package_dir / "pattern/pattern.json")
        semantic = read_json(package_dir / "semantic/garment_graph.json")
        constraints = read_json(package_dir / "simulation/constraints.json")
        fit = read_json(package_dir / "fitting/simple_dress_fit.json")
        presets = read_json(package_dir / "simulation/material_presets.json")
        selection = read_json(package_dir / "simulation/material_selection.json")
        motion = read_json(package_dir / "reports/material_motion_suite.json")
        fidelity = read_json(package_dir / "reports/fidelity/source_render_fidelity.json")
        texture = read_json(package_dir / "textures/simple_dress_pbr_report.json")
        quality = read_json(package_dir / "reports/simple_dress_quality.json")
        binding_manifest = read_json(package_dir / "binding/binding_manifest.json")
    except Exception as exc:
        issues.append(
            issue("simple_dress_contract_unreadable", "fatal", ".", str(exc), FAMILY_CODE)
        )
        return report(issues)

    _validate_pattern_semantics(pattern, semantic, constraints, issues)
    _validate_fit_and_motion(package_dir, fit, motion, issues)
    validate_material_selection(presets, selection, issues, family_code=FAMILY_CODE)
    validate_geometry_binding(package_dir, binding_manifest, issues, family_code=FAMILY_CODE)
    validate_appearance(
        package_dir,
        fidelity,
        texture,
        issues,
        acceptance_key="acceptedForD0SimpleDressFixture",
        family_code=FAMILY_CODE,
    )
    _validate_quality(quality, issues)
    validate_inventory(package_dir, manifest, issues, family_code=FAMILY_CODE)
    return report(issues)


def _validate_pattern_semantics(
    pattern: dict[str, Any],
    semantic: dict[str, Any],
    constraints: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    panel_ids = {str(item.get("id")) for item in pattern.get("panels", [])}
    seam_ids = {str(item.get("id")) for item in pattern.get("seams", [])}
    opening_ids = {str(item.get("id")) for item in pattern.get("openings", [])}
    required = semantic.get("requiredIds", {})
    panel_roles = {str(item.get("semanticRole")) for item in pattern.get("panels", [])}
    if (
        pattern.get("garmentClass") != FAMILY_CODE
        or semantic.get("garmentClass") != FAMILY_CODE
        or panel_ids != PANEL_IDS
        or seam_ids != SEAM_IDS
        or opening_ids != OPENING_IDS
        or set(required.get("panels", [])) != PANEL_IDS
        or set(required.get("seams", [])) != SEAM_IDS
        or set(required.get("openings", [])) != OPENING_IDS
        or panel_roles != PANEL_ROLES
        or "opening.simple_dress.waist" in opening_ids
    ):
        issues.append(
            issue(
                "simple_dress_semantic_ids_invalid",
                "fatal",
                "semantic/garment_graph.json",
                "Literal bodice/skirt panels, sewn waist, seams and neck/hem/armholes "
                "must match ontology.",
                FAMILY_CODE,
            )
        )
    for panel in pattern.get("panels", []):
        for code in validate_panel_boundary(panel):
            issues.append(
                issue(
                    code,
                    "fatal",
                    "pattern/pattern.json",
                    "Panel boundary is invalid.",
                    FAMILY_CODE,
                )
            )
    resolved = {str(item.get("id")): item for item in constraints.get("openings", [])}
    expected_edges = {
        "opening.simple_dress.neck": 2,
        "opening.simple_dress.hem": 2,
        "opening.simple_dress.armhole.left": 2,
        "opening.simple_dress.armhole.right": 2,
    }
    if set(resolved) != OPENING_IDS or any(
        len(resolved[opening_id].get("boundaryEdges", [])) != edge_count
        or any(
            edge.get("status") != "resolved"
            for edge in resolved[opening_id].get("boundaryEdges", [])
        )
        for opening_id, edge_count in expected_edges.items()
    ):
        issues.append(
            issue(
                "simple_dress_opening_loop_invalid",
                "fatal",
                "simulation/constraints.json",
                "Neck, hem and both armhole loops must resolve across literal panels.",
                FAMILY_CODE,
            )
        )
    if {str(item.get("id")) for item in constraints.get("seams", [])} != SEAM_IDS:
        issues.append(
            issue(
                "simple_dress_constraint_pairing_invalid",
                "fatal",
                "simulation/constraints.json",
                "Persisted constraints must preserve shoulder, side and waist joins.",
                FAMILY_CODE,
            )
        )


def _validate_fit_and_motion(
    package_dir: Path,
    fit: dict[str, Any],
    motion: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    if (
        fit.get("integrity", {}).get("fitReportHash") != hash_simple_dress_fit_report(fit)
        or fit.get("candidateCount") != 25
        or fit.get("accepted") is not True
        or fit.get("learnedFitRun") is not False
    ):
        issues.append(
            issue(
                "simple_dress_fit_integrity_invalid",
                "fatal",
                "fitting/simple_dress_fit.json",
                "Bounded 25-candidate simple-dress fitting evidence is invalid.",
                FAMILY_CODE,
            )
        )
    records = motion.get("presetRecords", [])
    state_names = {
        "material.lightweight_knit_d0_v1": "lightweight_knit.json",
        "material.cotton_jersey_d0_v1": "cotton_jersey.json",
        "material.heavy_jersey_d0_v1": "heavy_jersey.json",
        "material.lightweight_woven_d0_v1": "lightweight_woven.json",
    }
    refs_valid = True
    for index, record in enumerate(records):
        state_name = state_names.get(str(record.get("presetId")))
        if state_name is None:
            refs_valid = False
            continue
        state = read_json(package_dir / "simulation/motion_states" / state_name)
        refs_valid = refs_valid and (
            state.get("diagnosticsRef")
            == f"reports/material_motion_suite.json#/presetRecords/{index}/diagnostics"
            and state.get("sourceContentHash") is not None
        )
    stress_state = read_json(package_dir / "simulation/motion_states/opening_stress.json")
    refs_valid = refs_valid and (
        stress_state.get("diagnosticsRef")
        == "reports/material_motion_suite.json#/armholeStress/diagnostics"
        and stress_state.get("sourceContentHash") is not None
    )
    if (
        motion.get("integrity", {}).get("suiteHash") != hash_simple_dress_motion_report(motion)
        or {str(item.get("presetId")) for item in records} != PRESET_IDS
        or not all(item.get("actualSolverRun") is True for item in records)
        or not all(
            item.get("armholeMetrics", {}).get("armholeOpeningCount") == 2 for item in records
        )
        or not all(
            item.get("armholeMetrics", {}).get("collapsedArmholeCount") == 0 for item in records
        )
        or motion.get("crossPreset", {}).get("allFourPresetsExecuted") is not True
        or motion.get("armholeStress", {}).get("actualSolverRun") is not True
        or motion.get("armholeStress", {}).get("accepted") is not True
        or not refs_valid
    ):
        issues.append(
            issue(
                "simple_dress_motion_suite_invalid",
                "fatal",
                "reports/material_motion_suite.json",
                "Four-preset solver evidence and accepted non-collapsed armhole stress "
                "are required.",
                FAMILY_CODE,
            )
        )


def _validate_quality(quality: dict[str, Any], issues: list[ValidationIssue]) -> None:
    readiness = quality.get("readiness", {})
    topology = quality.get("topology", {})
    if (
        readiness.get("simpleDressD0Complete") is not True
        or readiness.get("phase8GloballyComplete") is not False
        or readiness.get("nextGarmentFamily") != "shirt_with_openings"
        or topology.get("hasLiteralBodiceAndSkirtPanels") is not True
        or topology.get("waistIsSewnNotOpen") is not True
    ):
        issues.append(
            issue(
                "simple_dress_quality_claim_invalid",
                "fatal",
                "reports/simple_dress_quality.json",
                "Dress completion and global Phase 8 partial status must remain truthful.",
                FAMILY_CODE,
            )
        )
