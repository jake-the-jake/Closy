from __future__ import annotations

import re
from typing import Any

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_THRESHOLD_PROFILES = {
    "closy.surface_equivalence.z1.v1",
    "closy.dynamic_reference.z2.v1",
    "closy.mechanical_reference.mt1.v2",
    "closy.outfit_surface.d0.v1",
    "closy.phase9_e1.selective.v1",
    "closy.phase9_e2.typed_program.v1",
    "closy.phy1.seam_support_neutral.v3",
}
_EXPECTED_BUDGETS = {
    "Z1-SURFACE-REPAIR": ("maximumStrategiesPerFamily", 3),
    "ZEROONE-DYNAMIC-ARCHITECTURE": ("maximumStrategies", 2),
    "PAIRED-DYNAMIC-INTEGRATION": ("maximumStrategies", 2),
    "RUNTIME-OUTFIT-INTEGRATION": ("maximumStrategies", 2),
    "PHASE9-E1": ("maximumModelFamiliesAfterBaselines", 3),
    "PHASE9-E2": ("maximumDecoderFamilies", 1),
    "PHY1": ("maximumStrategies", 3),
    "PHY1-SEAM-SUPPORT-V3": ("maximumSeamModels", 2),
    "CI-INFRASTRUCTURE-RETRY": ("maximumRetries", 1),
}


def validate_threshold_registry(registry: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    profiles = registry.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != _REQUIRED_THRESHOLD_PROFILES:
        return ["threshold_profile_inventory_invalid"]
    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict):
            issues.append(f"threshold_profile_invalid:{profile_id}")
            continue
        for field in (
            "assetProfileHash",
            "datasetSplitHash",
            "oracleVersionHash",
            "metrics",
            "units",
            "rationale",
            "comparisonDirection",
            "aggregationRule",
        ):
            if field not in profile:
                issues.append(f"threshold_field_missing:{profile_id}:{field}")
        for field in ("assetProfileHash", "datasetSplitHash", "oracleVersionHash"):
            if not _SHA256.fullmatch(str(profile.get(field, ""))):
                issues.append(f"threshold_hash_invalid:{profile_id}:{field}")
        metrics = profile.get("metrics")
        if not isinstance(metrics, dict) or not metrics:
            issues.append(f"threshold_metrics_invalid:{profile_id}")
        elif any(not isinstance(value, bool | int | float) for value in metrics.values()):
            issues.append(f"threshold_metric_non_numeric:{profile_id}")
    return sorted(set(issues))


def validate_execution_budget(budget: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    lanes = budget.get("lanes")
    if not isinstance(lanes, list):
        return ["execution_budget_lanes_missing"]
    by_id = {str(lane.get("laneId")): lane for lane in lanes if isinstance(lane, dict)}
    if len(by_id) != len(lanes):
        issues.append("execution_budget_lane_ids_not_unique")
    if set(by_id) != set(_EXPECTED_BUDGETS):
        issues.append("execution_budget_lane_inventory_invalid")
    for lane_id, (field, expected) in _EXPECTED_BUDGETS.items():
        lane = by_id.get(lane_id, {})
        if lane.get(field) != expected:
            issues.append(f"execution_budget_cap_invalid:{lane_id}:{field}")
        for required in (
            "blocker",
            "strategyIds",
            "trialIds",
            "predeclaredThresholdProfile",
            "commands",
            "outcome",
            "evidencePaths",
            "remainingBlocker",
            "stopReason",
        ):
            if required not in lane:
                issues.append(f"execution_budget_field_missing:{lane_id}:{required}")
    return sorted(set(issues))
