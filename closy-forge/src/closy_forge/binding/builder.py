from __future__ import annotations

from closy_forge.binding.binary_format import BindingFile, BindingRecord
from closy_forge.binding.reconstruct import reconstruct_vertices, reconstruction_error
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.geometry.subdivision import RenderBindingSeed
from closy_forge.package_io.hashing import topology_hash


def build_binding(
    sim: MeshSet, render: MeshSet, seeds: list[RenderBindingSeed]
) -> tuple[BindingFile, dict[str, object]]:
    panel_table = sorted({mesh.panel_id for mesh in sim.meshes})
    panel_lookup = {panel_id: i for i, panel_id in enumerate(panel_table)}
    sim_tri_offsets = []
    offset = 0
    for mesh in sim.meshes:
        sim_tri_offsets.append(offset)
        offset += len(mesh.triangles)
    records = [
        BindingRecord(
            sim_tri_offsets[seed.sim_mesh_index] + seed.sim_triangle_index,
            seed.barycentric_u,
            seed.barycentric_v,
            0.0,
            panel_lookup[seed.panel_id],
        )
        for seed in seeds
    ]
    binding = BindingFile(
        records, sim.triangle_count, len(panel_table), topology_hash(sim), topology_hash(render)
    )
    reconstructed = reconstruct_vertices(sim, binding)
    max_error, rms_error = reconstruction_error(render, reconstructed)
    manifest = {
        "schemaVersion": 1,
        "format": "CLSYBND1",
        "endianness": "little",
        "headerSize": 96,
        "recordStride": 20,
        "recordLayout": [
            "uint32 simulationTriangleIndex",
            "float32 barycentricU",
            "float32 barycentricV",
            "float32 normalOffset",
            "uint16 panelTableIndex",
            "uint16 flags",
        ],
        "sourceSimulationPath": "simulation/simulation_mesh.glb",
        "targetRenderPath": "render/fallback.glb",
        "simulationTopologyHash": binding.simulation_topology_hash,
        "renderTopologyHash": binding.render_topology_hash,
        "recordCount": len(records),
        "simulationTriangleCount": binding.simulation_triangle_count,
        "panelTable": panel_table,
        "algorithm": "closy.barycentric.subdivision_binding.v1",
        "generationSettings": {"normalOffsetMode": "zero", "preservePanelBoundaries": True},
        "reconstructionTolerance": 1e-6,
        "maximumReconstructionError": max_error,
        "rmsReconstructionError": rms_error,
    }
    return binding, manifest
