from __future__ import annotations

from typing import Any

from closy_forge.binding.binary_format import BindingFile
from closy_forge.garments.vertical_slice.motion import (
    MotionSuiteSpec,
    build_material_motion_suite,
    hash_motion_report,
)
from closy_forge.geometry.mesh_model import MeshSet

PANEL_IDS = tuple(
    f"panel.simple_dress.{face}.{section}"
    for face in ("back", "front")
    for section in ("bodice", "skirt")
)
ARMHOLE_IDS = frozenset({"opening.simple_dress.armhole.left", "opening.simple_dress.armhole.right"})
MOTION_SPEC = MotionSuiteSpec(
    suite_version="closy.simple_dress.motion_suite.d0.v1",
    suite_id="motion.simple_dress.public_d0_v1",
    garment_class="simple_dress",
    state_prefix="simple_dress",
    stress_state_id="simple_dress.armhole_stress",
    panel_ids=PANEL_IDS,
    tracked_opening_ids=ARMHOLE_IDS,
    preset_opening_key="armholeMetrics",
    stress_report_key="armholeStress",
    opening_count_key="armholeOpeningCount",
    collapsed_count_key="collapsedArmholeCount",
    opening_records_key="armholeOpenings",
    readiness_execution_key="simpleDressD0MotionExecuted",
    readiness_openings_key="armholesNonCollapsed",
    missing_preset_message="cotton jersey preset missing from simple-dress motion suite",
    normalize_signed_zero=True,
)


def build_simple_dress_motion_suite(
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


def hash_simple_dress_motion_report(report: dict[str, Any]) -> str:
    return hash_motion_report(report)
