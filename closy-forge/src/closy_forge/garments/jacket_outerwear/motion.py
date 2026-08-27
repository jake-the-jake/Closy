from __future__ import annotations

from typing import Any

from closy_forge.binding.binary_format import BindingFile
from closy_forge.garments.vertical_slice.motion import (
    MotionSuiteSpec,
    build_material_motion_suite,
    hash_motion_report,
)
from closy_forge.geometry.mesh_model import MeshSet

PANEL_IDS = (
    "panel.jacket_outerwear.back",
    "panel.jacket_outerwear.facing.left",
    "panel.jacket_outerwear.facing.right",
    "panel.jacket_outerwear.front.left",
    "panel.jacket_outerwear.front.right",
    "panel.jacket_outerwear.sleeve.left",
    "panel.jacket_outerwear.sleeve.right",
)
CUFF_IDS = frozenset(
    {
        "opening.jacket_outerwear.cuff.left",
        "opening.jacket_outerwear.cuff.right",
    }
)
MOTION_SPEC = MotionSuiteSpec(
    suite_version="closy.jacket_outerwear.motion_suite.d0.v1",
    suite_id="motion.jacket_outerwear.public_d0_v1",
    garment_class="jacket_outerwear",
    state_prefix="jacket_outerwear",
    stress_state_id="jacket_outerwear.opening_stress",
    panel_ids=PANEL_IDS,
    tracked_opening_ids=CUFF_IDS,
    preset_opening_key="cuffMetrics",
    stress_report_key="cuffStress",
    opening_count_key="cuffCount",
    collapsed_count_key="collapsedCuffCount",
    opening_records_key="cuffs",
    readiness_execution_key="jacketOuterwearD0MotionExecuted",
    readiness_openings_key="cuffsNonCollapsed",
    missing_preset_message="heavy jersey preset missing from jacket-outerwear motion suite",
    normalize_signed_zero=True,
    selected_preset_id="material.heavy_jersey_d0_v1",
)


def build_jacket_outerwear_motion_suite(
    *,
    rest_mesh: MeshSet,
    constraints: dict[str, Any],
    avatar_contract: dict[str, Any],
    preset_registry: dict[str, Any],
    binding: BindingFile,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], MeshSet]:
    return build_material_motion_suite(
        spec=MOTION_SPEC,
        rest_mesh=rest_mesh,
        constraints=constraints,
        avatar_contract=avatar_contract,
        preset_registry=preset_registry,
        binding=binding,
    )


def hash_jacket_outerwear_motion_report(report: dict[str, Any]) -> str:
    return hash_motion_report(report)
