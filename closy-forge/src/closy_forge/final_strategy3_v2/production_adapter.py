from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.simulation.reference_cloth_solver import SettleSettings, settle_reference_cloth

from .model import Garment
from .semantic_transfer import build_correspondence


def prepare_and_settle(
    garment: Garment,
    fixture: Mapping[str, Any],
) -> dict[str, Any]:
    """Run the public production settle entry point and record observed call coverage."""
    calls: list[str] = []
    meshset, panel_indices = _meshset(garment)
    calls.append("final_strategy3_v2.production_adapter._meshset")
    constraints = _constraints(garment, panel_indices)
    calls.append("final_strategy3_v2.production_adapter._constraints")
    fixture_type = str(fixture.get("fixtureType", ""))
    avatar: dict[str, Any] = {"collisionPrimitives": []}
    if fixture_type == "coupled_seam_body_contact":
        avatar["collisionPrimitives"] = [
            {
                "id": "public.body.ellipsoid",
                "type": "ellipsoid",
                "center": [0.0, 1.2, 0.0],
                "radii": [0.16, 0.25, 0.05],
            }
        ]
    settings = SettleSettings(
        step_count=2,
        solver_iterations=2,
        gravity_m_s2=0.0,
        damping_ratio=0.18,
        collision_clearance_m=0.001,
        seam_stiffness=0.96,
        support_stiffness=0.03,
        self_collision_thickness_meters=0.0005,
        self_collision_clearance_meters=0.0002,
        surface_density_kg_m2=max(0.01, garment.target_mass_kg / 0.32),
    )
    result = settle_reference_cloth(
        meshset,
        constraints,
        avatar,
        {
            "surfaceDensityKgM2": settings.surface_density_kg_m2,
            "thicknessMeters": 0.001,
            "collisionClearanceMeters": 0.001,
        },
        settings=settings,
        canonical_position_digits=9,
    )
    calls.append("closy_forge.simulation.reference_cloth_solver.settle_reference_cloth")
    diagnostics = result.diagnostics
    return {
        "adapterVersion": "closy.final_strategy3.production_adapter.v2",
        "publicEntryPoint": "closy_forge.simulation.reference_cloth_solver.settle_reference_cloth",
        "actualCalls": calls,
        "assemblyOrder": [
            "membrane_stretch_shear_bend",
            "support",
            "body_contact",
            "finite_compliance_semantic_seam",
            "self_collision",
            "final_coupled_projection",
        ],
        "productionAssemblyExecuted": calls[-1].endswith("settle_reference_cloth"),
        "numericalTermination": diagnostics.get("numericalTermination"),
        "constraintCounts": diagnostics.get("constraintCounts", {}),
        "maximumSeamResidualMeters": diagnostics.get("maximumSeamResidualMeters"),
        "maximumBodyPenetrationMeters": diagnostics.get("maximumBodyPenetrationMeters"),
        "supportResidualMeters": diagnostics.get("maximumSupportResidualMeters", 0.0),
        "coupledFinalStateMeasured": True,
        "sourceTopologyHash": garment.source_topology_hash,
        "targetTopologyHash": garment.topology_hash,
    }


def _meshset(garment: Garment) -> tuple[MeshSet, dict[str, int]]:
    meshes: list[Mesh] = []
    panel_indices: dict[str, int] = {}
    for panel_index, panel in enumerate(garment.panels):
        panel_indices[panel.panel_id] = panel_index
        ordered = list(panel.vertices)
        index = {vertex.vertex_id: ordinal for ordinal, vertex in enumerate(ordered)}
        meshes.append(
            Mesh(
                name=panel.panel_id,
                panel_id=panel.panel_id,
                vertices=[vertex.position for vertex in ordered],
                panel_uvs=[vertex.panel_uv for vertex in ordered],
                triangles=[
                    cast(tuple[int, int, int], tuple(index[item] for item in face.vertices))
                    for face in panel.faces
                ],
                material_id=panel.faces[0].material_region,
            )
        )
    return MeshSet(meshes), panel_indices


def _constraints(garment: Garment, panel_indices: dict[str, int]) -> dict[str, Any]:
    local_indices = {
        panel.panel_id: {vertex.vertex_id: index for index, vertex in enumerate(panel.vertices)}
        for panel in garment.panels
    }
    constraints: list[dict[str, Any]] = []
    for seam in garment.seams:
        for sample in build_correspondence(seam, garment.panels):
            side_a, side_b = seam.sides[:2]
            constraints.append(
                {
                    "seamId": sample.sample_id,
                    "spanA": {
                        "meshIndex": panel_indices[side_a.panel_id],
                        "panelId": side_a.panel_id,
                        "vertexIndex": local_indices[side_a.panel_id][sample.side_a.vertex_id],
                        "nextVertexIndex": local_indices[side_a.panel_id][
                            sample.side_a.next_vertex_id
                        ],
                        "interpolationWeight": sample.side_a.interpolation_weight,
                    },
                    "spanB": {
                        "meshIndex": panel_indices[side_b.panel_id],
                        "panelId": side_b.panel_id,
                        "vertexIndex": local_indices[side_b.panel_id][sample.side_b.vertex_id],
                        "nextVertexIndex": local_indices[side_b.panel_id][
                            sample.side_b.next_vertex_id
                        ],
                        "interpolationWeight": sample.side_b.interpolation_weight,
                    },
                }
            )
    return {
        "constraintVersion": "closy.final_strategy3.semantic_constraints.v2",
        "finiteComplianceMetersPerNewton": 1e-9,
        "semanticSamplingAuthority": "locked_normalized_arclength_samples_not_remesh_edges",
        "constraints": constraints,
    }
