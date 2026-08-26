from __future__ import annotations

from pathlib import Path
from typing import Any

from closy_forge.garments.button_shirt.fitting import hash_button_shirt_fit_report
from closy_forge.garments.button_shirt.motion import hash_button_shirt_motion_report
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

FAMILY_CODE = "button_shirt"
EXPECTED_FILES = {
    "manifest.json",
    "provenance.json",
    "source/capture_record.json",
    "source/public_fixture/front.png",
    "source/public_fixture/back.png",
    "fitting/button_shirt_fit.json",
    "textures/button_shirt_pbr_report.json",
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
    "reports/button_shirt_quality.json",
    "reports/package_validation.json",
    "reports/summary.json",
    "reports/summary.md",
}
PANEL_IDS = {
    "panel.button_shirt.front.left",
    "panel.button_shirt.front.right",
    "panel.button_shirt.back",
    "panel.button_shirt.sleeve.left",
    "panel.button_shirt.sleeve.right",
}
SEAM_IDS = {
    f"seam.button_shirt.{region}.{side}"
    for region in ("shoulder", "side", "sleeve_underarm")
    for side in ("left", "right")
} | {
    f"seam.button_shirt.armhole.{side}.{face}"
    for side in ("left", "right")
    for face in ("front", "back")
}
OPENING_IDS = {
    "opening.button_shirt.neck",
    "opening.button_shirt.hem",
    "opening.button_shirt.front_placket",
    "opening.button_shirt.cuff.left",
    "opening.button_shirt.cuff.right",
}
CLOSURE_IDS = {f"closure.button_shirt.button.{index:02d}" for index in range(1, 7)}
PANEL_ROLES = {
    "front_left_torso",
    "front_right_torso",
    "back_torso",
    "left_long_sleeve",
    "right_long_sleeve",
}


def validate_button_shirt_package(
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
        "garment.demo_button_shirt.reference_v1"
    ):
        issues.append(
            issue(
                "button_shirt_family_mismatch",
                "fatal",
                "manifest.json",
                "Button-shirt package identity must use canonical family and garment IDs.",
                FAMILY_CODE,
            )
        )
    if manifest.get("packageKind") != "closy.garment" or manifest.get("schemaVersion") != 1:
        issues.append(
            issue(
                "button_shirt_manifest_contract_invalid",
                "fatal",
                "manifest.json",
                "Button-shirt manifest kind/schema is unsupported.",
                FAMILY_CODE,
            )
        )
    if any(item.severity == "fatal" and item.code.endswith("_file_missing") for item in issues):
        return report(issues)
    try:
        pattern = read_json(package_dir / "pattern/pattern.json")
        semantic = read_json(package_dir / "semantic/garment_graph.json")
        constraints = read_json(package_dir / "simulation/constraints.json")
        fit = read_json(package_dir / "fitting/button_shirt_fit.json")
        presets = read_json(package_dir / "simulation/material_presets.json")
        selection = read_json(package_dir / "simulation/material_selection.json")
        motion = read_json(package_dir / "reports/material_motion_suite.json")
        fidelity = read_json(package_dir / "reports/fidelity/source_render_fidelity.json")
        texture = read_json(package_dir / "textures/button_shirt_pbr_report.json")
        quality = read_json(package_dir / "reports/button_shirt_quality.json")
        binding_manifest = read_json(package_dir / "binding/binding_manifest.json")
    except Exception as exc:
        issues.append(
            issue("button_shirt_contract_unreadable", "fatal", ".", str(exc), FAMILY_CODE)
        )
        return report(issues)

    _validate_pattern_semantics(pattern, semantic, constraints, issues)
    _validate_fit_and_motion(package_dir, fit, motion, issues)
    validate_material_selection(
        presets,
        selection,
        issues,
        family_code=FAMILY_CODE,
        expected_preset_id="material.lightweight_woven_d0_v1",
    )
    if selection.get("selection", {}).get("selectedPresetId") != "material.lightweight_woven_d0_v1":
        issues.append(
            issue(
                "button_shirt_material_selection_invalid",
                "fatal",
                "simulation/material_selection.json",
                "Button-shirt public fixture must select the bounded lightweight woven preset.",
                FAMILY_CODE,
            )
        )
    validate_geometry_binding(package_dir, binding_manifest, issues, family_code=FAMILY_CODE)
    validate_appearance(
        package_dir,
        fidelity,
        texture,
        issues,
        acceptance_key="acceptedForD0ButtonShirtFixture",
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
    closure_ids = {str(item.get("id")) for item in pattern.get("closures", [])}
    required = semantic.get("requiredIds", {})
    panel_roles = {str(item.get("semanticRole")) for item in pattern.get("panels", [])}
    if (
        pattern.get("garmentClass") != FAMILY_CODE
        or semantic.get("garmentClass") != FAMILY_CODE
        or panel_ids != PANEL_IDS
        or seam_ids != SEAM_IDS
        or opening_ids != OPENING_IDS
        or closure_ids != CLOSURE_IDS
        or set(required.get("panels", [])) != PANEL_IDS
        or set(required.get("seams", [])) != SEAM_IDS
        or set(required.get("openings", [])) != OPENING_IDS
        or set(required.get("closures", [])) != CLOSURE_IDS
        or panel_roles != PANEL_ROLES
    ):
        issues.append(
            issue(
                "button_shirt_semantic_ids_invalid",
                "fatal",
                "semantic/garment_graph.json",
                "Split fronts, sleeves, seams, openings and closure IDs must match ontology.",
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
    resolved = {str(item.get("id")): item for item in constraints.get("openings", [])}
    expected_edges = {
        "opening.button_shirt.neck": 3,
        "opening.button_shirt.hem": 3,
        "opening.button_shirt.front_placket": 2,
        "opening.button_shirt.cuff.left": 1,
        "opening.button_shirt.cuff.right": 1,
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
                "button_shirt_opening_loop_invalid",
                "fatal",
                "simulation/constraints.json",
                "Neck, hem, open placket and both cuff boundaries must resolve literally.",
                FAMILY_CODE,
            )
        )
    if {str(item.get("id")) for item in constraints.get("seams", [])} != SEAM_IDS:
        issues.append(
            issue(
                "button_shirt_constraint_pairing_invalid",
                "fatal",
                "simulation/constraints.json",
                "Persisted constraints must preserve shoulders, sides, armholes and underarms.",
                FAMILY_CODE,
            )
        )
    _validate_closures(pattern, semantic, constraints, issues)


def _validate_closures(
    pattern: dict[str, Any],
    semantic: dict[str, Any],
    constraints: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    pattern_records = pattern.get("closures", [])
    semantic_records = semantic.get("closures", [])
    constraint_records = constraints.get("closures", [])
    distances = [item.get("distanceFromHemMeters") for item in pattern_records]
    ordered = all(
        isinstance(value, int | float) and not isinstance(value, bool) for value in distances
    ) and all(
        float(first) < float(second)
        for first, second in zip(distances, distances[1:], strict=False)
    )
    pattern_valid = len(pattern_records) == 6 and ordered
    for index, closure in enumerate(pattern_records):
        button = closure.get("button", {})
        buttonhole = closure.get("buttonhole", {})
        pattern_valid = pattern_valid and (
            closure.get("id") == f"closure.button_shirt.button.{index + 1:02d}"
            and closure.get("type") == "button_buttonhole"
            and closure.get("stationIndex") == index
            and closure.get("stationCount") == 6
            and closure.get("paired") is True
            and closure.get("simulationEnabled") is False
            and button.get("panelId") == "panel.button_shirt.front.right"
            and button.get("edgeId") == "edge.button_shirt.placket.right"
            and buttonhole.get("panelId") == "panel.button_shirt.front.left"
            and buttonhole.get("edgeId") == "edge.button_shirt.placket.left"
            and button.get("distanceFromHemMeters") == closure.get("distanceFromHemMeters")
            and buttonhole.get("distanceFromHemMeters") == closure.get("distanceFromHemMeters")
        )
    placket_sewn = any(
        "placket" in str(span.get("edgeId"))
        for seam in pattern.get("seams", [])
        for span in seam.get("spans", [])
    )
    if (
        not pattern_valid
        or semantic_records != pattern_records
        or {str(item.get("id")) for item in constraint_records} != CLOSURE_IDS
        or any(item.get("paired") is not True for item in constraint_records)
        or any(item.get("simulationEnabled") is not False for item in constraint_records)
        or placket_sewn
    ):
        issues.append(
            issue(
                "button_shirt_closure_pairing_invalid",
                "fatal",
                "pattern/pattern.json",
                "Six ordered button/buttonhole pairs must reference opposite open placket edges.",
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
        fit.get("integrity", {}).get("fitReportHash") != hash_button_shirt_fit_report(fit)
        or fit.get("candidateCount") != 25
        or fit.get("accepted") is not True
        or fit.get("learnedFitRun") is not False
    ):
        issues.append(
            issue(
                "button_shirt_fit_integrity_invalid",
                "fatal",
                "fitting/button_shirt_fit.json",
                "Bounded 25-candidate button-shirt fitting evidence is invalid.",
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
        == "reports/material_motion_suite.json#/cuffStress/diagnostics"
        and stress_state.get("sourceContentHash") is not None
    )
    if (
        motion.get("integrity", {}).get("suiteHash") != hash_button_shirt_motion_report(motion)
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
                "button_shirt_motion_suite_invalid",
                "fatal",
                "reports/material_motion_suite.json",
                "Four-preset solver evidence and accepted non-collapsed cuff stress are required.",
                FAMILY_CODE,
            )
        )


def _validate_quality(quality: dict[str, Any], issues: list[ValidationIssue]) -> None:
    readiness = quality.get("readiness", {})
    topology = quality.get("topology", {})
    material = quality.get("material", {})
    if (
        readiness.get("buttonShirtD0Complete") is not True
        or readiness.get("phase8GloballyComplete") is not False
        or readiness.get("nextGarmentFamily") != "jacket_outerwear"
        or topology.get("hasLiteralSplitFront") is not True
        or topology.get("frontPlacketIsOpen") is not True
        or topology.get("closurePairsValid") is not True
        or material.get("selectedPresetId") != "material.lightweight_woven_d0_v1"
    ):
        issues.append(
            issue(
                "button_shirt_quality_claim_invalid",
                "fatal",
                "reports/button_shirt_quality.json",
                "Button-shirt completion and global Phase 8 partial status must remain truthful.",
                FAMILY_CODE,
            )
        )
