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
    f"panel.simple_trousers.{face}.{side}"
    for face in ("back", "front")
    for side in ("left", "right")
)
CUFF_IDS = frozenset({"opening.simple_trousers.cuff.left", "opening.simple_trousers.cuff.right"})
MOTION_SPEC = MotionSuiteSpec(
    suite_version="closy.simple_trousers.motion_suite.d0.v1",
    suite_id="motion.simple_trousers.public_d0_v1",
    garment_class="simple_trousers",
    state_prefix="simple_trousers",
    stress_state_id="simple_trousers.cuff_stress",
    panel_ids=PANEL_IDS,
    tracked_opening_ids=CUFF_IDS,
    preset_opening_key="cuffMetrics",
    stress_report_key="cuffStress",
    opening_count_key="cuffOpeningCount",
    collapsed_count_key="collapsedCuffCount",
    opening_records_key="cuffOpenings",
    readiness_execution_key="simpleTrousersD0MotionExecuted",
    readiness_openings_key="cuffsNonCollapsed",
    missing_preset_message="cotton jersey preset missing from simple-trousers motion suite",
    normalize_signed_zero=True,
)


def build_simple_trousers_motion_suite(
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


def hash_simple_trousers_motion_report(report: dict[str, Any]) -> str:
    return hash_motion_report(report)
