from __future__ import annotations

from pathlib import Path

from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.hashing import topology_hash
from closy_forge.simulation_topology_v2.phy1_experiment import (
    PHY1_STATE_IDS,
    PHY1_TOPOLOGY_V2_PROFILE_VERSION,
    build_phy1_topology_v2_inputs,
)


def test_phy1_v2_inputs_are_rebuilt_and_remain_experiment_only() -> None:
    inputs = build_phy1_topology_v2_inputs()
    v1 = read_json(Path("docs/capability-profiles/phy1-single-layer-d0-v1.json"))

    assert PHY1_TOPOLOGY_V2_PROFILE_VERSION.endswith("topology_v2.v1")
    assert len(PHY1_STATE_IDS) == 11
    assert topology_hash(inputs.rest_mesh) != v1["canonicalAuthority"]["simulationTopologyHash"]
    assert inputs.binding_manifest["runtimeExposure"] is False
    assert inputs.binding_manifest["simulationTopologyVersion"] == ("closy.simulation_topology.v2")
    assert inputs.binding.simulation_topology_hash == topology_hash(inputs.rest_mesh)
    assert inputs.seam_audit["status"] == "pass"
    assert inputs.binding_audit["status"] == "pass"
