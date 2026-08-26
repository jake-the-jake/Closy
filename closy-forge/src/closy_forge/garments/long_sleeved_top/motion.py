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
    "panel.long_sleeved_top.back",
    "panel.long_sleeved_top.front",
    "panel.long_sleeved_top.sleeve.left",
    "panel.long_sleeved_top.sleeve.right",
)
CUFF_IDS = frozenset(
    {
        "opening.long_sleeved_top.cuff.left",
        "opening.long_sleeved_top.cuff.right",
    }
)
MOTION_SPEC = MotionSuiteSpec(
    suite_version="closy.long_sleeved_top.motion_suite.d0.v1",
    suite_id="motion.long_sleeved_top.public_d0_v1",
    garment_class="long_sleeved_top",
    state_prefix="long_sleeved",
    stress_state_id="long_sleeved.opening_stress",
    panel_ids=PANEL_IDS,
    tracked_opening_ids=CUFF_IDS,
    preset_opening_key="cuffMetrics",
    stress_report_key="cuffStress",
    opening_count_key="cuffCount",
    collapsed_count_key="collapsedCuffCount",
    opening_records_key="cuffs",
    readiness_execution_key="longSleevedTopD0MotionExecuted",
    readiness_openings_key="cuffsNonCollapsed",
    missing_preset_message="cotton jersey preset missing from long-sleeved motion suite",
    normalize_signed_zero=True,
)


def build_long_sleeved_motion_suite(
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


def hash_long_sleeved_motion_report(report: dict[str, Any]) -> str:
    return hash_motion_report(report)
