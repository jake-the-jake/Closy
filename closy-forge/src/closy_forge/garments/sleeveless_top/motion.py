from __future__ import annotations

from typing import Any

from closy_forge.binding.binary_format import BindingFile
from closy_forge.garments.vertical_slice.motion import (
    CANONICAL_POSITION_DIGITS as SHARED_CANONICAL_POSITION_DIGITS,
)
from closy_forge.garments.vertical_slice.motion import (
    MotionSuiteSpec,
    build_material_motion_suite,
    hash_motion_report,
)
from closy_forge.garments.vertical_slice.motion import (
    binding_panel_ids as shared_binding_panel_ids,
)
from closy_forge.geometry.mesh_model import MeshSet

CANONICAL_POSITION_DIGITS = SHARED_CANONICAL_POSITION_DIGITS
SLEEVELESS_MOTION_VERSION = "closy.sleeveless_top.motion_suite.d0.v1"
ARMHOLE_IDS = frozenset(
    {
        "opening.sleeveless_top.armhole.left",
        "opening.sleeveless_top.armhole.right",
    }
)
PANEL_IDS = (
    "panel.sleeveless_top.back",
    "panel.sleeveless_top.front",
)
MOTION_SPEC = MotionSuiteSpec(
    suite_version=SLEEVELESS_MOTION_VERSION,
    suite_id="motion.sleeveless_top.public_d0_v1",
    garment_class="sleeveless_top",
    state_prefix="sleeveless",
    stress_state_id="sleeveless.opening_stress",
    panel_ids=PANEL_IDS,
    tracked_opening_ids=ARMHOLE_IDS,
    preset_opening_key="armholeMetrics",
    stress_report_key="underarmStress",
    opening_count_key="armholeCount",
    collapsed_count_key="collapsedArmholeCount",
    opening_records_key="armholes",
    readiness_execution_key="sleevelessTopD0MotionExecuted",
    readiness_openings_key="armholesNonCollapsed",
    missing_preset_message="cotton jersey preset missing from sleeveless motion suite",
)


def build_sleeveless_motion_suite(
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


def hash_sleeveless_motion_report(report: dict[str, Any]) -> str:
    return hash_motion_report(report)


def binding_panel_ids(binding: BindingFile) -> list[str]:
    return list(shared_binding_panel_ids(binding, PANEL_IDS))
