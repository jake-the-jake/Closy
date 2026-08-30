from __future__ import annotations

from copy import deepcopy

from closy_forge.binding.builder import build_binding
from closy_forge.garments.tshirt.assembly import TRANSFORMS, build_simulation_mesh
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.simulation_topology_v2 import (
    build_panel_meshes_v2,
    build_seam_constraints_v2,
    build_topology_v2_render_binding,
)
from closy_forge.simulation_topology_v2.binding import audit_topology_v2_binding
from closy_forge.simulation_topology_v2.seam_junctions import audit_seam_constraints_v2


def _experiment() -> tuple[dict[str, object], object, object]:
    pattern = build_tshirt_pattern(TShirtParameters())
    simulation, edges, _manifest = build_panel_meshes_v2(pattern, TRANSFORMS)
    constraints, seam_audit = build_seam_constraints_v2(pattern, edges, simulation)
    return constraints, seam_audit, simulation


def test_topology_v2_seams_and_binding_are_rebuilt_and_valid() -> None:
    constraints, seam_audit, simulation = _experiment()
    render, _seeds, binding, manifest, binding_audit = build_topology_v2_render_binding(simulation)

    assert seam_audit["status"] == "pass"
    assert constraints["junctionModelVersion"] == "closy.seam_junction_equivalence.v2"
    assert constraints["provenance"]["historicalToleranceInflated"] is False
    assert binding_audit["status"] == "pass"
    assert binding.simulation_topology_hash == binding_audit["simulationTopologyHash"]
    assert manifest["runtimeExposure"] is False
    assert render.vertex_count == len(binding.records)


def test_v1_binding_is_rejected_for_v2_topology() -> None:
    pattern = build_tshirt_pattern(TShirtParameters())
    v1_simulation, _v1_edges = build_simulation_mesh(pattern)
    v1_render, v1_seeds = subdivide_for_render(v1_simulation)
    v1_binding, v1_manifest = build_binding(v1_simulation, v1_render, v1_seeds)
    v2_simulation, _v2_edges, _topology = build_panel_meshes_v2(pattern, TRANSFORMS)

    audit = audit_topology_v2_binding(v2_simulation, v1_render, v1_binding, v1_manifest)
    assert audit["status"] == "fail"
    assert "simulationTopologyCurrent" in audit["failedChecks"]
    assert "v2AuthorityDeclared" in audit["failedChecks"]


def test_seam_audit_rejects_duplicate_and_opening_capture() -> None:
    constraints, _audit, simulation = _experiment()
    pattern = build_tshirt_pattern(TShirtParameters())
    corrupt = deepcopy(constraints)
    corrupt["constraints"].append(deepcopy(corrupt["constraints"][0]))
    pattern["seams"][0]["spans"][0]["edgeId"] = "edge.hem.front"

    audit = audit_seam_constraints_v2(pattern, corrupt, simulation)
    assert audit["status"] == "fail"
    assert "duplicatePairConstraints" in audit["failedChecks"]
    assert "openingEndpointsRemainOpen" in audit["failedChecks"]
