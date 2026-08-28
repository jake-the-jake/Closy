from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

C3_BINDING_D0_PROFILE_ID = "C3-Binding-D0"
PHY1_SINGLE_LAYER_D0_PROFILE_ID = "PHY1-SingleLayer-D0"

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_PROFILE_PATHS = {
    C3_BINDING_D0_PROFILE_ID: _REPOSITORY_ROOT
    / "docs"
    / "capability-profiles"
    / "c3-binding-d0-v1.json",
    PHY1_SINGLE_LAYER_D0_PROFILE_ID: _REPOSITORY_ROOT
    / "docs"
    / "capability-profiles"
    / "phy1-single-layer-d0-v1.json",
}


class CapabilityProfileError(ValueError):
    pass


def capability_profile_hash(profile: dict[str, Any]) -> str:
    candidate = deepcopy(profile)
    integrity = candidate.get("integrity")
    if not isinstance(integrity, dict) or "profileHash" not in integrity:
        raise CapabilityProfileError("capability_profile_integrity_missing")
    integrity["profileHash"] = ""
    return sha256_bytes(canonical_dumps(candidate).encode("utf-8"))


def load_capability_profile(profile_id: str) -> dict[str, Any]:
    path = _PROFILE_PATHS.get(profile_id)
    if path is None:
        raise CapabilityProfileError(f"capability_profile_unknown:{profile_id}")
    profile = cast(dict[str, Any], read_json(path))
    validate_capability_profile(profile)
    return profile


def validate_capability_profile(profile: dict[str, Any]) -> None:
    if profile.get("schemaVersion") != 1:
        raise CapabilityProfileError("capability_profile_schema_version_invalid")
    profile_id = profile.get("capabilityId")
    if profile_id not in _PROFILE_PATHS:
        raise CapabilityProfileError("capability_profile_id_invalid")
    axes = profile.get("axes")
    if not isinstance(axes, dict) or set(axes) != {
        "computeProfile",
        "dataProvenance",
        "executionProfile",
        "gateScope",
    }:
        raise CapabilityProfileError("capability_profile_axes_invalid")
    expected_hash = profile.get("integrity", {}).get("profileHash")
    if expected_hash != capability_profile_hash(profile):
        raise CapabilityProfileError("capability_profile_hash_mismatch")
    if profile_id == PHY1_SINGLE_LAYER_D0_PROFILE_ID:
        _validate_phy1_profile(profile)


def validate_profile_package_inputs(profile: dict[str, Any], package_dir: Path) -> list[str]:
    """Fail-closed comparison of frozen inputs; generated trajectories are not goldens."""

    validate_capability_profile(profile)
    issues: list[str] = []
    for asset in profile.get("frozenFiles", []):
        relative = str(asset.get("path", ""))
        path = package_dir / relative
        if not path.is_file():
            issues.append(f"capability_input_missing:{relative}")
            continue
        if sha256_file(path) != asset.get("sha256"):
            issues.append(f"capability_input_hash_mismatch:{relative}")
    simulation = read_json(package_dir / "simulation" / "mesh_manifest.json")
    authority = profile["canonicalAuthority"]
    if simulation.get("topologyHash") != authority["simulationTopologyHash"]:
        issues.append("capability_simulation_topology_drift")
    if int(simulation.get("vertexCount", -1)) != int(authority["simulationVertexCount"]):
        issues.append("capability_simulation_vertex_inventory_drift")
    if int(simulation.get("triangleCount", -1)) != int(authority["simulationTriangleCount"]):
        issues.append("capability_simulation_triangle_inventory_drift")
    if profile["capabilityId"] == C3_BINDING_D0_PROFILE_ID:
        state_index = read_json(package_dir / "simulation" / "motion_states" / "index.json")
        if state_index.get("stateIds") != profile["poseSuite"]["stateIds"]:
            issues.append("capability_pose_suite_inventory_drift")
    return issues


def _validate_phy1_profile(profile: dict[str, Any]) -> None:
    scenarios = profile.get("scenarioDefinitions")
    if not isinstance(scenarios, list) or len(scenarios) != 11:
        raise CapabilityProfileError("phy1_scenario_inventory_invalid")
    scenario_ids = [item.get("scenarioId") for item in scenarios]
    if len(set(scenario_ids)) != 11:
        raise CapabilityProfileError("phy1_scenario_ids_not_unique")
    solver = profile.get("solverProfile", {})
    if int(solver.get("settleStepCount", 0)) > 720:
        raise CapabilityProfileError("phy1_step_budget_exceeded")
    if int(solver.get("maximumSubsteps", 0)) > 8:
        raise CapabilityProfileError("phy1_substep_budget_exceeded")
    if int(solver.get("maximumIterationsPerSubstep", 0)) > 24:
        raise CapabilityProfileError("phy1_iteration_budget_exceeded")
    if profile.get("layerCollision", {}).get("enabled") is not False:
        raise CapabilityProfileError("phy1_must_remain_single_layer")
