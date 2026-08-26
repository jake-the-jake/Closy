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
    "panel.simple_skirt.back",
    "panel.simple_skirt.front",
)
WAIST_IDS = frozenset({"opening.simple_skirt.waist"})
MOTION_SPEC = MotionSuiteSpec(
    suite_version="closy.simple_skirt.motion_suite.d0.v1",
    suite_id="motion.simple_skirt.public_d0_v1",
    garment_class="simple_skirt",
    state_prefix="simple_skirt",
    stress_state_id="simple_skirt.waist_stress",
    panel_ids=PANEL_IDS,
    tracked_opening_ids=WAIST_IDS,
    preset_opening_key="waistMetrics",
    stress_report_key="waistStress",
    opening_count_key="waistOpeningCount",
    collapsed_count_key="collapsedWaistCount",
    opening_records_key="waistOpenings",
    readiness_execution_key="simpleSkirtD0MotionExecuted",
    readiness_openings_key="waistNonCollapsed",
    missing_preset_message="cotton jersey preset missing from simple-skirt motion suite",
    normalize_signed_zero=True,
)


def build_simple_skirt_motion_suite(
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


def hash_simple_skirt_motion_report(report: dict[str, Any]) -> str:
    return hash_motion_report(report)
