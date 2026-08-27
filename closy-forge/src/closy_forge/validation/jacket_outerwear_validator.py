from __future__ import annotations

from pathlib import Path
from typing import Any

from closy_forge.garments.jacket_outerwear.fitting import hash_jacket_outerwear_fit_report
from closy_forge.garments.jacket_outerwear.motion import hash_jacket_outerwear_motion_report
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

FAMILY_CODE = "jacket_outerwear"
EXPECTED_FILES = {
    "manifest.json",
    "provenance.json",
    "source/capture_record.json",
    "source/public_fixture/front.png",
    "source/public_fixture/back.png",
    "fitting/jacket_outerwear_fit.json",
    "textures/jacket_outerwear_pbr_report.json",
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
    "reports/jacket_outerwear_quality.json",
    "reports/package_validation.json",
    "reports/summary.json",
    "reports/summary.md",
}
PANEL_IDS = {
    "panel.jacket_outerwear.front.left",
    "panel.jacket_outerwear.front.right",
    "panel.jacket_outerwear.back",
    "panel.jacket_outerwear.sleeve.left",
    "panel.jacket_outerwear.sleeve.right",
    "panel.jacket_outerwear.facing.left",
    "panel.jacket_outerwear.facing.right",
}
SEAM_IDS = {
    "seam.jacket_outerwear.shoulder.left",
    "seam.jacket_outerwear.shoulder.right",
    "seam.jacket_outerwear.side.left",
    "seam.jacket_outerwear.side.right",
    "seam.jacket_outerwear.armhole.left.front",
    "seam.jacket_outerwear.armhole.left.back",
    "seam.jacket_outerwear.sleeve_underarm.left",
    "seam.jacket_outerwear.armhole.right.front",
    "seam.jacket_outerwear.armhole.right.back",
    "seam.jacket_outerwear.sleeve_underarm.right",
    "seam.jacket_outerwear.facing_attachment.left",
    "seam.jacket_outerwear.facing_attachment.right",
}
OPENING_IDS = {
    "opening.jacket_outerwear.neck",
    "opening.jacket_outerwear.hem",
    "opening.jacket_outerwear.front",
    "opening.jacket_outerwear.cuff.left",
    "opening.jacket_outerwear.cuff.right",
}


def validate_jacket_outerwear_package(
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
    if manifest.get("garmentClass") != "jacket_outerwear" or manifest.get("garmentId") != (
        "garment.demo_jacket_outerwear.reference_v1"
    ):
        issues.append(
            issue(
                "jacket_outerwear_family_mismatch",
                "fatal",
                "manifest.json",
                "Jacket/outerwear package identity must use canonical family and garment IDs.",
                FAMILY_CODE,
            )
        )
    if manifest.get("packageKind") != "closy.garment" or manifest.get("schemaVersion") != 1:
        issues.append(
            issue(
                "jacket_outerwear_manifest_contract_invalid",
                "fatal",
                "manifest.json",
                "Jacket/outerwear manifest kind/schema is unsupported.",
                FAMILY_CODE,
            )
        )
    if any(item.severity == "fatal" and item.code.endswith("_file_missing") for item in issues):
        return report(issues)

    try:
        pattern = read_json(package_dir / "pattern/pattern.json")
        semantic = read_json(package_dir / "semantic/garment_graph.json")
        constraints = read_json(package_dir / "simulation/constraints.json")
        fit = read_json(package_dir / "fitting/jacket_outerwear_fit.json")
        presets = read_json(package_dir / "simulation/material_presets.json")
        selection = read_json(package_dir / "simulation/material_selection.json")
        motion = read_json(package_dir / "reports/material_motion_suite.json")
        fidelity = read_json(package_dir / "reports/fidelity/source_render_fidelity.json")
        texture = read_json(package_dir / "textures/jacket_outerwear_pbr_report.json")
        quality = read_json(package_dir / "reports/jacket_outerwear_quality.json")
        binding_manifest = read_json(package_dir / "binding/binding_manifest.json")
    except Exception as exc:
        issues.append(
            issue("jacket_outerwear_contract_unreadable", "fatal", ".", str(exc), FAMILY_CODE)
        )
        return report(issues)

    _validate_pattern_semantics(pattern, semantic, constraints, issues)
    _validate_fit_and_motion(package_dir, fit, motion, issues)
    validate_material_selection(
        presets,
        selection,
        issues,
        family_code=FAMILY_CODE,
        expected_preset_id="material.heavy_jersey_d0_v1",
    )
    validate_geometry_binding(package_dir, binding_manifest, issues, family_code=FAMILY_CODE)
    validate_appearance(
        package_dir,
        fidelity,
        texture,
        issues,
        acceptance_key="acceptedForD0JacketOuterwearFixture",
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
        pattern.get("garmentClass") != "jacket_outerwear"
        or semantic.get("garmentClass") != "jacket_outerwear"
        or panel_ids != PANEL_IDS
        or seam_ids != SEAM_IDS
        or opening_ids != OPENING_IDS
        or set(required.get("panels", [])) != PANEL_IDS
        or set(required.get("seams", [])) != SEAM_IDS
        or set(required.get("openings", [])) != OPENING_IDS
        or {
            "front_left_torso",
            "front_right_torso",
            "back_torso",
            "left_long_sleeve",
            "right_long_sleeve",
            "front_left_facing",
            "front_right_facing",
        }
        != panel_roles
    ):
        issues.append(
            issue(
                "jacket_outerwear_semantic_ids_invalid",
                "fatal",
                "semantic/garment_graph.json",
                "Split fronts, separate facings, sleeves, seams and openings must match ontology.",
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
        "opening.jacket_outerwear.neck": 5,
        "opening.jacket_outerwear.hem": 5,
        "opening.jacket_outerwear.front": 2,
        "opening.jacket_outerwear.cuff.left": 1,
        "opening.jacket_outerwear.cuff.right": 1,
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
                "jacket_outerwear_opening_loop_invalid",
                "fatal",
                "simulation/constraints.json",
                "Neck, hem, facing-backed front and both cuff boundaries must resolve.",
                FAMILY_CODE,
            )
        )
    front_opening: dict[str, Any] = next(
        (
            item
            for item in pattern.get("openings", [])
            if item.get("id") == "opening.jacket_outerwear.front"
        ),
        {},
    )
    facing_seams = {
        str(seam.get("id")): {str(span.get("edgeId")) for span in seam.get("spans", [])}
        for seam in pattern.get("seams", [])
        if "facing_attachment" in str(seam.get("id"))
    }
    expected_facing_seams = {
        f"seam.jacket_outerwear.facing_attachment.{side}": {
            f"edge.jacket_outerwear.facing_attachment.{side}",
            f"edge.jacket_outerwear.facing.outer.{side}",
        }
        for side in ("left", "right")
    }
    if (
        set(front_opening.get("boundaryEdges", []))
        != {
            "edge.jacket_outerwear.facing.inner.left",
            "edge.jacket_outerwear.facing.inner.right",
        }
        or facing_seams != expected_facing_seams
    ):
        issues.append(
            issue(
                "jacket_outerwear_facing_contract_invalid",
                "fatal",
                "pattern/pattern.json",
                "Facing outer edges must attach while facing inner edges remain the front opening.",
                FAMILY_CODE,
            )
        )
    components = {str(item.get("id")): item for item in semantic.get("components", [])}
    outer_orders = [
        components.get(f"component.jacket_outerwear.{component}", {}).get("collisionOrder")
        for component in ("torso", "sleeve.left", "sleeve.right")
    ]
    layer_contract_valid = (
        all(
            components.get(f"component.jacket_outerwear.{component}", {}).get("layerClass")
            == "outer_shell"
            for component in ("torso", "sleeve.left", "sleeve.right")
        )
        and all(
            isinstance(order, int) and not isinstance(order, bool) and order >= 30
            for order in outer_orders
        )
        and all(
            components.get(f"component.jacket_outerwear.facing.{side}", {}).get("layerClass")
            == "outer_shell_internal_facing"
            and components.get(f"component.jacket_outerwear.facing.{side}", {}).get(
                "collisionOrder"
            )
            == 29
            for side in ("left", "right")
        )
    )
    if not layer_contract_valid:
        issues.append(
            issue(
                "jacket_outerwear_collision_layer_invalid",
                "fatal",
                "semantic/garment_graph.json",
                "Outer shell and internal facing collision orders must remain literal.",
                FAMILY_CODE,
            )
        )
    if {str(item.get("id")) for item in constraints.get("seams", [])} != SEAM_IDS:
        issues.append(
            issue(
                "jacket_outerwear_constraint_pairing_invalid",
                "fatal",
                "simulation/constraints.json",
                "Persisted constraints must preserve torso, armhole, underarm and facing seams.",
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
        fit.get("integrity", {}).get("fitReportHash") != hash_jacket_outerwear_fit_report(fit)
        or fit.get("candidateCount") != 25
        or fit.get("accepted") is not True
        or fit.get("learnedFitRun") is not False
    ):
        issues.append(
            issue(
                "jacket_outerwear_fit_integrity_invalid",
                "fatal",
                "fitting/jacket_outerwear_fit.json",
                "Bounded 25-candidate jacket-outerwear fitting evidence is invalid.",
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
        motion.get("integrity", {}).get("suiteHash") != hash_jacket_outerwear_motion_report(motion)
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
                "jacket_outerwear_motion_suite_invalid",
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
        readiness.get("jacketOuterwearD0Complete") is not True
        or readiness.get("phase8GloballyComplete") is not False
        or readiness.get("nextGarmentFamily") != "layered_unusual"
        or topology.get("hasLiteralSplitFront") is not True
        or topology.get("hasSeparateFacings") is not True
        or topology.get("frontOpeningUsesFacingInnerEdges") is not True
        or topology.get("outerLayerCollisionOrderValid") is not True
        or topology.get("facingCollisionOrderValid") is not True
        or material.get("selectedPresetId") != "material.heavy_jersey_d0_v1"
    ):
        issues.append(
            issue(
                "jacket_outerwear_quality_claim_invalid",
                "fatal",
                "reports/jacket_outerwear_quality.json",
                "Outerwear completion and global Phase 8 partial status must remain truthful.",
                FAMILY_CODE,
            )
        )
