from __future__ import annotations

from typing import Any

from closy_forge.binding.binary_format import BindingFile
from closy_forge.binding.builder import build_binding
from closy_forge.binding.reconstruct import reconstruct_vertices, reconstruction_error
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.geometry.subdivision import RenderBindingSeed, subdivide_for_render
from closy_forge.package_io.hashing import topology_hash

TOPOLOGY_V2_BINDING_VERSION = "closy.topology_v2.render_binding.v1"


def build_topology_v2_render_binding(
    simulation_mesh: MeshSet,
) -> tuple[MeshSet, list[RenderBindingSeed], BindingFile, dict[str, Any], dict[str, Any]]:
    render_mesh, seeds = subdivide_for_render(simulation_mesh)
    binding, manifest = build_binding(simulation_mesh, render_mesh, seeds)
    manifest = {
        **manifest,
        "algorithm": "closy.barycentric.subdivision_binding.topology_v2.v1",
        "experimentBindingVersion": TOPOLOGY_V2_BINDING_VERSION,
        "simulationTopologyVersion": "closy.simulation_topology.v2",
        "runtimeExposure": False,
    }
    audit = audit_topology_v2_binding(simulation_mesh, render_mesh, binding, manifest)
    if audit["status"] != "pass":
        raise ValueError(f"topology_v2_binding_audit_failed:{','.join(audit['failedChecks'])}")
    return render_mesh, seeds, binding, manifest, audit


def audit_topology_v2_binding(
    simulation_mesh: MeshSet,
    render_mesh: MeshSet,
    binding: BindingFile,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    simulation_hash = topology_hash(simulation_mesh)
    render_hash = topology_hash(render_mesh)
    reconstructed = reconstruct_vertices(simulation_mesh, binding)
    maximum_error, rms_error = reconstruction_error(render_mesh, reconstructed)
    checks = {
        "simulationTopologyCurrent": binding.simulation_topology_hash == simulation_hash,
        "renderTopologyCurrent": binding.render_topology_hash == render_hash,
        "manifestSimulationTopologyCurrent": manifest.get("simulationTopologyHash")
        == simulation_hash,
        "manifestRenderTopologyCurrent": manifest.get("renderTopologyHash") == render_hash,
        "destinationCoverage": len(binding.records) == render_mesh.vertex_count,
        "finiteReconstruction": all(
            component == component and abs(component) < 1e6
            for vertex in reconstructed
            for component in vertex
        ),
        "maximumReconstructionError": maximum_error <= 1e-6,
        "v2AuthorityDeclared": manifest.get("simulationTopologyVersion")
        == "closy.simulation_topology.v2",
    }
    failed = [key for key, passed in checks.items() if not passed]
    return {
        "schemaVersion": 1,
        "auditVersion": "closy.topology_v2.binding_audit.v1",
        "bindingVersion": TOPOLOGY_V2_BINDING_VERSION,
        "simulationTopologyHash": simulation_hash,
        "renderTopologyHash": render_hash,
        "recordCount": len(binding.records),
        "renderVertexCount": render_mesh.vertex_count,
        "maximumReconstructionErrorMeters": maximum_error,
        "rmsReconstructionErrorMeters": rms_error,
        "checks": checks,
        "failedChecks": failed,
        "status": "pass" if not failed else "fail",
    }
