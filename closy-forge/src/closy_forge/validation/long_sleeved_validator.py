from __future__ import annotations

from pathlib import Path
from typing import Any

from closy_forge.garments.long_sleeved_top.fitting import hash_long_sleeved_fit_report
from closy_forge.garments.long_sleeved_top.motion import hash_long_sleeved_motion_report
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

FAMILY_CODE = "long_sleeved"
EXPECTED_FILES = {
    "manifest.json",
    "provenance.json",
    "source/capture_record.json",
    "source/public_fixture/front.png",
    "source/public_fixture/back.png",
    "fitting/long_sleeved_fit.json",
    "textures/long_sleeved_pbr_report.json",
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
    "reports/long_sleeved_quality.json",
    "reports/package_validation.json",
    "reports/summary.json",
    "reports/summary.md",
}
PANEL_IDS = {
    "panel.long_sleeved_top.front",
    "panel.long_sleeved_top.back",
    "panel.long_sleeved_top.sleeve.left",
    "panel.long_sleeved_top.sleeve.right",
}
SEAM_IDS = {
    "seam.long_sleeved_top.shoulder.left",
    "seam.long_sleeved_top.shoulder.right",
    "seam.long_sleeved_top.side.left",
    "seam.long_sleeved_top.side.right",
    "seam.long_sleeved_top.armhole.left.front",
    "seam.long_sleeved_top.armhole.left.back",
    "seam.long_sleeved_top.sleeve_underarm.left",
    "seam.long_sleeved_top.armhole.right.front",
    "seam.long_sleeved_top.armhole.right.back",
    "seam.long_sleeved_top.sleeve_underarm.right",
}
OPENING_IDS = {
    "opening.long_sleeved_top.neck",
    "opening.long_sleeved_top.hem",
    "opening.long_sleeved_top.cuff.left",
    "opening.long_sleeved_top.cuff.right",
}


def validate_long_sleeved_package(
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
    if manifest.get("garmentClass") != "long_sleeved_top" or manifest.get("garmentId") != (
        "garment.demo_long_sleeved_top.reference_v1"
    ):
        issues.append(
            issue(
                "long_sleeved_family_mismatch",
                "fatal",
                "manifest.json",
                "Long-sleeved package identity must use canonical family and garment IDs.",
                FAMILY_CODE,
            )
        )
    if manifest.get("packageKind") != "closy.garment" or manifest.get("schemaVersion") != 1:
        issues.append(
            issue(
                "long_sleeved_manifest_contract_invalid",
                "fatal",
                "manifest.json",
                "Long-sleeved manifest kind/schema is unsupported.",
                FAMILY_CODE,
            )
        )
    if any(item.severity == "fatal" and item.code.endswith("_file_missing") for item in issues):
        return report(issues)

    try:
        pattern = read_json(package_dir / "pattern/pattern.json")
        semantic = read_json(package_dir / "semantic/garment_graph.json")
        constraints = read_json(package_dir / "simulation/constraints.json")
        fit = read_json(package_dir / "fitting/long_sleeved_fit.json")
        presets = read_json(package_dir / "simulation/material_presets.json")
        selection = read_json(package_dir / "simulation/material_selection.json")
        motion = read_json(package_dir / "reports/material_motion_suite.json")
        fidelity = read_json(package_dir / "reports/fidelity/source_render_fidelity.json")
        texture = read_json(package_dir / "textures/long_sleeved_pbr_report.json")
        quality = read_json(package_dir / "reports/long_sleeved_quality.json")
        binding_manifest = read_json(package_dir / "binding/binding_manifest.json")
    except Exception as exc:
        issues.append(
            issue("long_sleeved_contract_unreadable", "fatal", ".", str(exc), FAMILY_CODE)
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
        acceptance_key="acceptedForD0LongSleevedFixture",
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
        pattern.get("garmentClass") != "long_sleeved_top"
        or semantic.get("garmentClass") != "long_sleeved_top"
        or panel_ids != PANEL_IDS
        or seam_ids != SEAM_IDS
        or opening_ids != OPENING_IDS
        or set(required.get("panels", [])) != PANEL_IDS
        or set(required.get("seams", [])) != SEAM_IDS
        or set(required.get("openings", [])) != OPENING_IDS
        or {"left_long_sleeve", "right_long_sleeve"} - panel_roles
    ):
        issues.append(
            issue(
                "long_sleeved_semantic_ids_invalid",
                "fatal",
                "semantic/garment_graph.json",
                "Panels, sleeve parts, seams and cuff openings must match the family ontology.",
                FAMILY_CODE,
            )
        )
    for panel in pattern.get("panels", []):
        for code in validate_panel_boundary(panel):
            issues.append(
                issue(
                    code, "fatal", "pattern/pattern.json", "Panel boundary is invalid.", FAMILY_CODE
                )
            )
    resolved_openings = {
        str(opening.get("id")): opening for opening in constraints.get("openings", [])
    }
    opening_edge_counts = {
        "opening.long_sleeved_top.neck": 2,
        "opening.long_sleeved_top.hem": 2,
        "opening.long_sleeved_top.cuff.left": 1,
        "opening.long_sleeved_top.cuff.right": 1,
    }
    if set(resolved_openings) != OPENING_IDS or any(
        len(resolved_openings[opening_id].get("boundaryEdges", [])) != count
        or any(
            edge.get("status") != "resolved"
            for edge in resolved_openings[opening_id].get("boundaryEdges", [])
        )
        for opening_id, count in opening_edge_counts.items()
    ):
        issues.append(
            issue(
                "long_sleeved_opening_loop_invalid",
                "fatal",
                "simulation/constraints.json",
                "Neck, hem and both cuff boundary loops must resolve.",
                FAMILY_CODE,
            )
        )
    if {str(item.get("id")) for item in constraints.get("seams", [])} != SEAM_IDS:
        issues.append(
            issue(
                "long_sleeved_constraint_pairing_invalid",
                "fatal",
                "simulation/constraints.json",
                "Persisted constraints must preserve every torso, armhole and underarm seam.",
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
        fit.get("integrity", {}).get("fitReportHash") != hash_long_sleeved_fit_report(fit)
        or fit.get("candidateCount") != 25
        or fit.get("accepted") is not True
        or fit.get("learnedFitRun") is not False
    ):
        issues.append(
            issue(
                "long_sleeved_fit_integrity_invalid",
                "fatal",
                "fitting/long_sleeved_fit.json",
                "Bounded 25-candidate long-sleeved fitting evidence is invalid.",
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
        preset_id = str(record.get("presetId"))
        state_name = state_names.get(preset_id)
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
        == "reports/material_motion_suite.json#/cuffStress/diagnostics"
        and stress_state.get("sourceContentHash") is not None
    )
    if (
        motion.get("integrity", {}).get("suiteHash") != hash_long_sleeved_motion_report(motion)
        or {str(item.get("presetId")) for item in records} != PRESET_IDS
        or not all(item.get("actualSolverRun") is True for item in records)
        or not all(item.get("cuffMetrics", {}).get("cuffCount") == 2 for item in records)
        or not all(item.get("cuffMetrics", {}).get("collapsedCuffCount") == 0 for item in records)
        or motion.get("crossPreset", {}).get("allFourPresetsExecuted") is not True
        or motion.get("cuffStress", {}).get("actualSolverRun") is not True
        or motion.get("cuffStress", {}).get("accepted") is not True
        or not refs_valid
    ):
        issues.append(
            issue(
                "long_sleeved_motion_suite_invalid",
                "fatal",
                "reports/material_motion_suite.json",
                "Four-preset solver evidence and accepted non-collapsed cuff stress are required.",
                FAMILY_CODE,
            )
        )


def _validate_quality(quality: dict[str, Any], issues: list[ValidationIssue]) -> None:
    readiness = quality.get("readiness", {})
    topology = quality.get("topology", {})
    if (
        readiness.get("longSleevedTopD0Complete") is not True
        or readiness.get("phase8GloballyComplete") is not False
        or readiness.get("nextGarmentFamily") != "simple_skirt"
        or topology.get("hasLiteralLongSleeves") is not True
        or topology.get("hasLiteralCuffs") is not True
    ):
        issues.append(
            issue(
                "long_sleeved_quality_claim_invalid",
                "fatal",
                "reports/long_sleeved_quality.json",
                "Family completion and global Phase 8 partial status must remain truthful.",
                FAMILY_CODE,
            )
        )
