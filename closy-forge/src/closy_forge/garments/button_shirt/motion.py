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
    "panel.button_shirt.back",
    "panel.button_shirt.front.left",
    "panel.button_shirt.front.right",
    "panel.button_shirt.sleeve.left",
    "panel.button_shirt.sleeve.right",
)
CUFF_IDS = frozenset(
    {
        "opening.button_shirt.cuff.left",
        "opening.button_shirt.cuff.right",
    }
)
MOTION_SPEC = MotionSuiteSpec(
    suite_version="closy.button_shirt.motion_suite.d0.v1",
    suite_id="motion.button_shirt.public_d0_v1",
    garment_class="button_shirt",
    state_prefix="button_shirt",
    stress_state_id="button_shirt.opening_stress",
    panel_ids=PANEL_IDS,
    tracked_opening_ids=CUFF_IDS,
    preset_opening_key="cuffMetrics",
    stress_report_key="cuffStress",
    opening_count_key="cuffCount",
    collapsed_count_key="collapsedCuffCount",
    opening_records_key="cuffs",
    readiness_execution_key="buttonShirtD0MotionExecuted",
    readiness_openings_key="cuffsNonCollapsed",
    missing_preset_message="lightweight woven preset missing from button-shirt motion suite",
    normalize_signed_zero=True,
    selected_preset_id="material.lightweight_woven_d0_v1",
)


def build_button_shirt_motion_suite(
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


def hash_button_shirt_motion_report(report: dict[str, Any]) -> str:
    return hash_motion_report(report)
