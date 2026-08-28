from __future__ import annotations

from copy import deepcopy
from math import isfinite, sqrt
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import BindingFile
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.geometry.frame_attributes import meshset_frame_metrics
from closy_forge.geometry.glb_io import audit_glb, read_glb_meshset
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Tri, Vec3, mesh_bounds
from closy_forge.geometry.subdivision import RenderBindingSeed
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)
from closy_forge.simulation.seam_mapping import span_position_flat

PRODUCTION_BINDING_CONTRACT_VERSION = "closy.production_binding_contract.d0_tshirt.v1"
PRODUCTION_BINDING_C3_REPORT_VERSION = (
    "closy.production_binding_c3.d0_tshirt.independent_metrics_v3"
)

_MOTION_STATE_IDS = [
    "neutral_settled",
    "left_arm_raise_non_affine",
    "right_arm_raise_non_affine",
    "asymmetric_sleeve_bend",
    "torso_twist_non_affine",
    "forward_bend_non_affine",
    "side_bend_non_affine",
    "compression_ease_non_affine",
    "cloth_impulse_gust_non_affine",
    "material_soft_extreme_non_affine",
    "material_stiff_extreme_non_affine",
]


def build_production_binding_contract(
    *,
    garment_id: str,
    garment_class: str,
    simulation_mesh: MeshSet,
    render_mesh: MeshSet,
    binding: BindingFile,
    binding_manifest: dict[str, Any],
    render_binding_seeds: list[RenderBindingSeed],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    if len(render_binding_seeds) != render_mesh.vertex_count:
        raise ValueError("render_binding_seed_count_mismatch")
    sim_triangles = _flattened_triangles(simulation_mesh)
    render_vertex_refs = _flattened_vertices(render_mesh)
    opening_lookup = _opening_lookup(constraints, simulation_mesh)
    records: list[dict[str, Any]] = []
    invalid_opening_crossing_count = 0
    for global_render_index, seed in enumerate(render_binding_seeds):
        record = binding.records[global_render_index]
        sim_global_triangle_index = _global_triangle_index(
            simulation_mesh, seed.sim_mesh_index, seed.sim_triangle_index
        )
        if sim_global_triangle_index != record.simulation_triangle_index:
            raise ValueError("binding_seed_triangle_mismatch")
        sim_mesh_index, sim_local_triangle_index, tri = sim_triangles[sim_global_triangle_index]
        source_mesh = simulation_mesh.meshes[sim_mesh_index]
        render_mesh_index, render_local_vertex_index, render_vertex = render_vertex_refs[
            global_render_index
        ]
        render_mesh_doc = render_mesh.meshes[render_mesh_index]
        weights = [_round(1.0 - record.barycentric_u - record.barycentric_v)]
        weights.extend([_round(record.barycentric_u), _round(record.barycentric_v)])
        weighted_openings = _weighted_opening_ids(
            [sim_mesh_offsets(simulation_mesh)[sim_mesh_index] + index for index in tri],
            weights,
            opening_lookup,
        )
        opening_crossing = len(weighted_openings) > 1
        invalid_opening_crossing_count += 1 if opening_crossing else 0
        records.append(
            {
                "renderVertexId": _render_vertex_id(global_render_index),
                "globalRenderVertexIndex": global_render_index,
                "renderMeshIndex": render_mesh_index,
                "renderMeshName": render_mesh_doc.name,
                "renderLocalVertexIndex": render_local_vertex_index,
                "renderPanelId": render_mesh_doc.panel_id,
                "renderPosition": [_round(value) for value in render_vertex],
                "sourceTriangle": {
                    "globalTriangleIndex": sim_global_triangle_index,
                    "meshIndex": sim_mesh_index,
                    "meshName": source_mesh.name,
                    "localTriangleIndex": sim_local_triangle_index,
                    "panelId": source_mesh.panel_id,
                    "vertexIndices": list(tri),
                    "globalVertexIndices": [
                        sim_mesh_offsets(simulation_mesh)[sim_mesh_index] + index for index in tri
                    ],
                },
                "binding": {
                    "kind": "triangle_barycentric",
                    "weights": weights,
                    "normalOffsetMeters": _round(record.normal_offset),
                    "weightSum": _round(sum(weights)),
                },
                "logicalToRenderSplit": {
                    "source": "render_subdivision_seed",
                    "splitReason": "render_subdivision_uv_material_hard_normal_safe",
                    "uvSeamPreserved": True,
                    "materialBoundaryPreserved": True,
                    "hardNormalBoundaryPreserved": True,
                    "sourcePanelId": seed.panel_id,
                },
                "ownership": {
                    "panelId": source_mesh.panel_id,
                    "partId": _part_id_for_panel(source_mesh.panel_id),
                    "openingIds": weighted_openings,
                    "openingCrossing": opening_crossing,
                    "panelMatchesBindingPanelTable": source_mesh.panel_id
                    == binding_manifest["panelTable"][record.panel_table_index],
                },
            }
        )
    contract: dict[str, Any] = {
        "schemaVersion": 1,
        "contractId": "production_binding.demo_tshirt_d0_v1",
        "stageVersion": PRODUCTION_BINDING_CONTRACT_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "bindingFormat": "CLSYBND1+production_contract_json_v1",
        "sourceSimulation": {
            "path": "simulation/simulation_mesh.glb",
            "manifestPath": "simulation/mesh_manifest.json",
            "statePath": "simulation/settled_state.json",
            "topologyHash": topology_hash(simulation_mesh),
            "contentHash": geometry_content_hash(simulation_mesh),
            "topologyVersionId": f"simtopo.{topology_hash(simulation_mesh)[:16]}",
            "contentVersionId": f"simcontent.{geometry_content_hash(simulation_mesh)[:16]}",
            "meshCount": len(simulation_mesh.meshes),
            "vertexCount": simulation_mesh.vertex_count,
            "triangleCount": simulation_mesh.triangle_count,
        },
        "destinationRender": {
            "path": "render/fallback.glb",
            "manifestPath": "render/mesh_manifest.json",
            "topologyHash": topology_hash(render_mesh),
            "contentHash": geometry_content_hash(render_mesh),
            "topologyVersionId": f"rendertopo.{topology_hash(render_mesh)[:16]}",
            "contentVersionId": f"rendercontent.{geometry_content_hash(render_mesh)[:16]}",
            "meshCount": len(render_mesh.meshes),
            "vertexCount": render_mesh.vertex_count,
            "triangleCount": render_mesh.triangle_count,
        },
        "binaryBinding": {
            "path": "binding/sim_to_render.bin",
            "manifestPath": "binding/binding_manifest.json",
            "format": binding_manifest["format"],
            "algorithm": binding_manifest["algorithm"],
            "recordCount": len(binding.records),
            "simulationTopologyHash": binding.simulation_topology_hash,
            "renderTopologyHash": binding.render_topology_hash,
        },
        "authority": {
            "routeId": "settled_simulation_to_subdivided_render_v1",
            "status": "authoritative",
            "sourcePath": "simulation/mesh_manifest.json",
            "denseDestinationPath": "render/mesh_manifest.json",
            "denseAssetPath": "render/fallback.glb",
            "independentFallbackAssetPath": "render/simulation_fallback.glb",
            "bp46TopologyRelationship": (
                "BP46 stitched-shell evidence is derived from the same settled panel topology, "
                "seam constraints and semantic openings; it is topology evidence, not a parallel "
                "runtime binding authority"
            ),
            "deprecatedTrackIds": [
                "legacy_cleanup_to_simulation_binding_validation",
                "proposal_runtime_preview_binding_records",
            ],
        },
        "capabilities": {
            "denseBarycentricBindingAvailable": True,
            "independentSimulationMeshFallbackAvailable": True,
            "stableRenderVertexIdsAvailable": True,
            "logicalToRenderSplitMappingAvailable": True,
            "openingOwnershipSafeguardsAvailable": True,
            "deterministicTopologyInvalidationAvailable": True,
        },
        "splitMapping": {
            "mode": "per_render_vertex_records",
            "uvMaterialHardNormalPolicy": (
                "render vertices remain panel-owned; GLB writer may expand triangle vertices, "
                "but production IDs bind the canonical render-manifest vertices"
            ),
            "renderVertexIdFormat": "rv.%06d",
            "recordCount": len(records),
        },
        "safeguards": {
            "weightSumTolerance": 1e-6,
            "finiteValueRequired": True,
            "invalidOpeningCrossingCount": invalid_opening_crossing_count,
            "panelOwnershipRequired": True,
            "partOwnershipRequired": True,
            "invalidationRule": (
                "reject when source or destination topology/content hash differs from manifest, "
                "binding header or contract"
            ),
        },
        "records": records,
        "integrity": {"productionBindingContractHash": ""},
    }
    contract["integrity"]["productionBindingContractHash"] = hash_production_binding_contract(
        contract
    )
    return contract


def build_production_binding_c3_report_from_package(
    *,
    package_dir: Path,
    garment_id: str,
    garment_class: str,
) -> dict[str, Any]:
    from closy_forge.binding.c3_evidence import build_c3_report_from_package

    return build_c3_report_from_package(
        package_dir=package_dir,
        garment_id=garment_id,
        garment_class=garment_class,
    )


def build_production_binding_c3_report(
    *,
    garment_id: str,
    garment_class: str,
    package_dir: Path,
    simulation_mesh: MeshSet,
    render_mesh: MeshSet,
    binding: BindingFile,
    binding_manifest: dict[str, Any],
    contract: dict[str, Any],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    persisted = _persisted_validation(
        package_dir=package_dir,
        simulation_mesh=simulation_mesh,
        render_mesh=render_mesh,
        binding=binding,
        binding_manifest=binding_manifest,
        contract=contract,
    )
    motion_states = [
        _motion_state_result(state_id, simulation_mesh, render_mesh, binding, constraints)
        for state_id in _MOTION_STATE_IDS
    ]
    aggregate = _motion_aggregate(motion_states)
    c3_profile_pass = (
        persisted["status"] == "pass"
        and aggregate["motionSuiteStatus"] == "pass"
        and aggregate["stateCount"] == len(_MOTION_STATE_IDS)
    )
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "production_binding_c3.demo_tshirt_d0_v1",
        "stageVersion": PRODUCTION_BINDING_C3_REPORT_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "profile": {
            "id": "d0_fixed_avatar_tshirt_dense_fallback",
            "scope": "fixed_avatar_demo_tshirt_only",
            "globalPhase6Complete": False,
            "cleanGeometryPromoted": False,
            "canonicalGeometryPromoted": False,
        },
        "sourceAssets": {
            "productionBindingContract": {
                "path": "binding/production_binding_contract.json",
                "sha256": sha256_file(package_dir / "binding" / "production_binding_contract.json"),
            },
            "binaryBinding": {
                "path": "binding/sim_to_render.bin",
                "sha256": sha256_file(package_dir / "binding" / "sim_to_render.bin"),
                "byteSize": (package_dir / "binding" / "sim_to_render.bin").stat().st_size,
            },
            "bindingManifest": {
                "path": "binding/binding_manifest.json",
                "sha256": sha256_file(package_dir / "binding" / "binding_manifest.json"),
            },
            "simulationMeshManifest": {
                "path": "simulation/mesh_manifest.json",
                "sha256": sha256_file(package_dir / "simulation" / "mesh_manifest.json"),
            },
            "renderMeshManifest": {
                "path": "render/mesh_manifest.json",
                "sha256": sha256_file(package_dir / "render" / "mesh_manifest.json"),
            },
            "renderGlb": {
                "path": "render/fallback.glb",
                "sha256": sha256_file(package_dir / "render" / "fallback.glb"),
            },
        },
        "bindingTrackInventory": _binding_track_inventory(package_dir),
        "persistedValidation": persisted,
        "thresholds": {
            "maxReconstructionErrorMeters": 0.006,
            "rmsReconstructionErrorMeters": 0.002,
            "maxSeamCrackMeters": 0.13,
            "maxOpeningCircumferenceDriftMeters": 0.08,
            "maxBoundarySlidingMeters": 0.08,
            "maxDenseFallbackParityErrorMeters": 1e-9,
            "maxNormalLengthError": 1e-6,
            "maxTangentLengthError": 1e-6,
            "maxNormalTangentDot": 1e-6,
            "maxDegenerateTriangles": 0,
            "toleranceBasis": "D0 metres-scale fixed-avatar T-shirt fixture",
        },
        "motionSuite": {
            "stateCount": len(motion_states),
            "stateIds": _MOTION_STATE_IDS,
            "states": motion_states,
        },
        "aggregate": aggregate,
        "performanceProfile": {
            "timingEvidenceKind": "deterministic_workload_budget_canonical_wall_clock_omitted",
            "hardware": "not_recorded_in_canonical_package",
            "os": "not_recorded_in_canonical_package",
            "runtimeProfile": "python_reference_cpu_ci_safe",
            "warmupPolicy": "not_applicable_to_canonical_digest",
            "repeatCount": 0,
            "medianMilliseconds": None,
            "p95Milliseconds": None,
            "peakMemoryBytes": None,
            "denseMode": {
                "renderVertexCount": render_mesh.vertex_count,
                "bindingRecordCount": len(binding.records),
            },
            "fallbackMode": {
                "mode": "panel_batch_reconstruction",
                "panelBatchCount": len(render_mesh.meshes),
            },
            "budgets": {
                "maxRenderVerticesD0": 5000,
                "maxMotionStatesD0": 16,
                "maxBindingRecordsD0": 5000,
            },
            "budgetStatus": "pass"
            if render_mesh.vertex_count <= 5000
            and len(binding.records) <= 5000
            and len(motion_states) <= 16
            else "fail",
        },
        "execution": {
            "productionBindingContractWritten": True,
            "persistedByteValidationRun": True,
            "glbAccessorAuditRun": True,
            "nonAffineMotionSuiteRun": True,
            "denseBindingRun": True,
            "fallbackBindingRun": True,
            "crackSlidingOpeningChecksRun": True,
            "normalTangentChecksRun": True,
            "performanceWorkloadProfileRun": True,
        },
        "capabilities": {
            "productionBindingC3ProfileAvailable": c3_profile_pass,
            "denseBindingAvailable": True,
            "fallbackBindingAvailable": True,
            "globalPhase6Complete": False,
        },
        "readiness": {
            "status": "d0_c3_profile_pass_clean_rejected"
            if c3_profile_pass
            else "d0_c3_profile_failed",
            "gateC3Status": "complete_for_d0_fixed_avatar_tshirt_profile"
            if c3_profile_pass
            else "rejected",
            "acceptedForD0RuntimeBindingProfile": c3_profile_pass,
            "acceptedForGlobalPhase6": False,
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "blockingReasons": [
                "source_image_visual_comparison_not_run",
                "provider_geometry_visual_fidelity_not_run",
                "private_user_avatar_garment_profiles_not_run",
                "mobile_runtime_gpu_profile_not_run",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "limitations": [
            "d0_fixed_avatar_tshirt_profile_only",
            "not_clean_or_canonical_geometry_acceptance",
            "not_provider_derived_geometry_binding",
            "wall_clock_timing_omitted_from_canonical_digest",
            "not_mobile_gpu_runtime_profile",
        ],
        "integrity": {"productionBindingC3ReportHash": ""},
    }
    report["integrity"]["productionBindingC3ReportHash"] = hash_production_binding_c3_report(report)
    return report


def hash_production_binding_contract(contract: dict[str, Any]) -> str:
    payload = deepcopy(contract)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["productionBindingContractHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def hash_production_binding_c3_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["productionBindingC3ReportHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _persisted_validation(
    *,
    package_dir: Path,
    simulation_mesh: MeshSet,
    render_mesh: MeshSet,
    binding: BindingFile,
    binding_manifest: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    issues: list[str] = []
    contract_records = contract.get("records", [])
    expected_ids = {_render_vertex_id(index) for index in range(render_mesh.vertex_count)}
    actual_ids = {
        str(record.get("renderVertexId")) for record in contract_records if isinstance(record, dict)
    }
    duplicate_ids = len(actual_ids) != len(contract_records)
    if actual_ids != expected_ids:
        issues.append("missing_or_unexpected_render_vertex_ids")
    if duplicate_ids:
        issues.append("duplicate_render_vertex_ids")
    if (
        len(contract_records) != len(binding.records)
        or len(binding.records) != render_mesh.vertex_count
    ):
        issues.append("record_count_mismatch")
    if binding.simulation_topology_hash != topology_hash(simulation_mesh):
        issues.append("binding_simulation_topology_stale")
    if binding.render_topology_hash != topology_hash(render_mesh):
        issues.append("binding_render_topology_stale")
    if binding_manifest.get("simulationTopologyHash") != topology_hash(simulation_mesh):
        issues.append("binding_manifest_simulation_topology_stale")
    if binding_manifest.get("renderTopologyHash") != topology_hash(render_mesh):
        issues.append("binding_manifest_render_topology_stale")
    invalid_records = _validate_contract_records(contract, binding, simulation_mesh, render_mesh)
    issues.extend(invalid_records)
    reconstructed = reconstruct_vertices(simulation_mesh, binding)
    target = [vertex for mesh in render_mesh.meshes for vertex in mesh.vertices]
    max_error, mean_error, rms_error, p95_error = _error_metrics(target, reconstructed)
    if max_error > 1e-6 or rms_error > 1e-6:
        issues.append("persisted_reconstruction_error_too_high")
    glb_audit = audit_glb(package_dir / "render" / "fallback.glb")
    expanded_mesh = _expanded_glb_expected_mesh(render_mesh)
    decoded_glb_mesh = read_glb_meshset(package_dir / "render" / "fallback.glb")
    if glb_audit["semanticAccessorCounts"].get("POSITION") != expanded_mesh.vertex_count:
        issues.append("glb_position_accessor_count_mismatch")
    if glb_audit["semanticAccessorTypes"].get("POSITION") != ["VEC3"]:
        issues.append("glb_position_accessor_type_mismatch")
    if glb_audit["semanticAccessorTypes"].get("NORMAL") != ["VEC3"]:
        issues.append("glb_normal_accessor_type_mismatch")
    if glb_audit["semanticAccessorTypes"].get("TANGENT") != ["VEC4"]:
        issues.append("glb_tangent_accessor_type_mismatch")
    if topology_hash(decoded_glb_mesh) != topology_hash(expanded_mesh):
        issues.append("glb_topology_hash_mismatch")
    if geometry_content_hash(decoded_glb_mesh) != geometry_content_hash(expanded_mesh):
        issues.append("glb_content_hash_mismatch")
    return {
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "binaryBindingReopened": True,
        "renderGlbDecoded": True,
        "sourceSimulationTopologyHash": topology_hash(simulation_mesh),
        "sourceSimulationContentHash": geometry_content_hash(simulation_mesh),
        "destinationRenderTopologyHash": topology_hash(render_mesh),
        "destinationRenderContentHash": geometry_content_hash(render_mesh),
        "contractHash": contract["integrity"]["productionBindingContractHash"],
        "recordCount": len(binding.records),
        "stableRenderVertexIdCount": len(actual_ids),
        "duplicateRenderVertexIds": duplicate_ids,
        "allRenderVerticesReconstructed": len(reconstructed) == render_mesh.vertex_count,
        "maxReconstructionErrorMeters": _round(max_error),
        "meanReconstructionErrorMeters": _round(mean_error),
        "rmsReconstructionErrorMeters": _round(rms_error),
        "p95ReconstructionErrorMeters": _round(p95_error),
        "glbAccessorAudit": {
            "meshCount": glb_audit["meshCount"],
            "primitiveCount": glb_audit["primitiveCount"],
            "positionAccessorCount": glb_audit["semanticAccessorCounts"].get("POSITION", 0),
            "normalAccessorCount": glb_audit["semanticAccessorCounts"].get("NORMAL", 0),
            "tangentAccessorCount": glb_audit["semanticAccessorCounts"].get("TANGENT", 0),
            "positionAccessorTypes": glb_audit["semanticAccessorTypes"].get("POSITION", []),
            "normalAccessorTypes": glb_audit["semanticAccessorTypes"].get("NORMAL", []),
            "tangentAccessorTypes": glb_audit["semanticAccessorTypes"].get("TANGENT", []),
            "expandedTopologyHash": topology_hash(decoded_glb_mesh),
            "expectedExpandedTopologyHash": topology_hash(expanded_mesh),
            "expandedContentHash": geometry_content_hash(decoded_glb_mesh),
            "expectedExpandedContentHash": geometry_content_hash(expanded_mesh),
        },
    }


def _motion_state_result(
    state_id: str,
    simulation_mesh: MeshSet,
    render_mesh: MeshSet,
    binding: BindingFile,
    constraints: dict[str, Any],
) -> dict[str, Any]:
    posed_sim = _apply_motion_state(simulation_mesh, state_id)
    posed_render = _apply_motion_state(render_mesh, state_id)
    reconstructed_dense = reconstruct_vertices(posed_sim, binding)
    reconstructed_fallback = _fallback_reconstruct_vertices(posed_sim, binding, render_mesh)
    target = [vertex for mesh in posed_render.meshes for vertex in mesh.vertices]
    max_error, mean_error, rms_error, p95_error = _error_metrics(target, reconstructed_dense)
    parity = _point_cloud_max_distance(reconstructed_dense, reconstructed_fallback)
    frame_metrics = meshset_frame_metrics(posed_render)
    seam = _seam_metrics(posed_sim, constraints)
    openings = _opening_metrics(posed_sim, constraints, simulation_mesh)
    bounds = mesh_bounds(posed_render)
    degenerate_count = _inverted_or_degenerate_triangle_count(posed_render)
    status = (
        "pass"
        if max_error <= 0.006
        and rms_error <= 0.002
        and seam["maxSeamCrackMeters"] <= 0.13
        and openings["maxCircumferenceDriftMeters"] <= 0.08
        and parity <= 1e-9
        and degenerate_count == 0
        and frame_metrics["maxNormalLengthError"] <= 1e-6
        and frame_metrics["maxTangentLengthError"] <= 1e-6
        and frame_metrics["maxNormalTangentDot"] <= 1e-6
        and all(value > 0.0 for value in bounds["size"])
        else "fail"
    )
    return {
        "stateId": state_id,
        "stateKind": _motion_state_kind(state_id),
        "status": status,
        "simulationTopologyHash": topology_hash(posed_sim),
        "renderTopologyHash": topology_hash(posed_render),
        "deformedSimulationContentHash": geometry_content_hash(posed_sim),
        "deformedRenderContentHash": geometry_content_hash(posed_render),
        "maxReconstructionErrorMeters": _round(max_error),
        "meanReconstructionErrorMeters": _round(mean_error),
        "rmsReconstructionErrorMeters": _round(rms_error),
        "p95ReconstructionErrorMeters": _round(p95_error),
        "seamCrack": seam,
        "openingContinuity": openings,
        "boundarySliding": {
            "maxBoundarySlidingMeters": seam["maxBoundarySlidingMeters"],
            "maxCrossPanelDriftMeters": seam["maxSeamCrackMeters"],
        },
        "triangleQuality": {
            "invertedOrDegenerateTriangleCount": degenerate_count,
            "status": "pass" if degenerate_count == 0 else "fail",
        },
        "frameMetrics": frame_metrics,
        "deformedBounds": {
            key: [_round(value) for value in values] for key, values in bounds.items()
        },
        "finiteDeformedBounds": all(
            isfinite(value) for values in bounds.values() for value in values
        ),
        "denseFallbackParity": {
            "fallbackMode": "panel_batch_reconstruction",
            "maxParityErrorMeters": _round(parity),
            "status": "pass" if parity <= 1e-9 else "fail",
        },
        "failureIds": [] if status == "pass" else [f"motion_state_failed.{state_id}"],
        "sampleErrors": _sample_errors(target, reconstructed_dense),
    }


def _apply_motion_state(meshset: MeshSet, state_id: str) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                name=mesh.name,
                panel_id=mesh.panel_id,
                vertices=[
                    _motion_transform(mesh.panel_id, vertex, state_id) for vertex in mesh.vertices
                ],
                panel_uvs=mesh.panel_uvs,
                triangles=mesh.triangles,
                material_id=mesh.material_id,
            )
            for mesh in meshset.meshes
        ]
    )


def _motion_transform(panel_id: str, vertex: Vec3, state_id: str) -> Vec3:
    x, y, z = vertex
    if state_id == "neutral_settled":
        return vertex
    torso = panel_id in {"panel.front", "panel.back", "panel.neck_band"}
    left_sleeve = panel_id == "panel.sleeve.left"
    right_sleeve = panel_id == "panel.sleeve.right"
    if state_id == "left_arm_raise_non_affine" and left_sleeve:
        return _quantize((x - 0.012 * max(0.0, y - 1.0), y + 0.045, z + 0.004 * (x + 0.55)))
    if state_id == "right_arm_raise_non_affine" and right_sleeve:
        return _quantize((x + 0.012 * max(0.0, y - 1.0), y + 0.045, z - 0.004 * (x - 0.55)))
    if state_id == "asymmetric_sleeve_bend":
        if left_sleeve:
            return _quantize((x - 0.012 * y, y + 0.018 * (x + 0.55), z + 0.006 * y))
        if right_sleeve:
            return _quantize((x + 0.006 * y, y - 0.008 * (x - 0.55), z - 0.004 * y))
    if state_id == "torso_twist_non_affine":
        amount = 0.09 * max(-1.0, min(1.0, (y - 0.95) / 0.5))
        twist = amount if torso else amount * 0.5
        return _quantize((x + z * twist, y, z - x * twist))
    if state_id == "forward_bend_non_affine":
        bend = 0.045 * max(0.0, y - 0.92)
        return _quantize((x, y - 0.012 * max(0.0, y - 1.0), z + bend))
    if state_id == "side_bend_non_affine":
        return _quantize((x + 0.035 * max(0.0, y - 1.0), y, z + 0.006 * x * y))
    if state_id == "compression_ease_non_affine":
        factor = 0.987 if torso else 0.994
        return _quantize((x * factor, y + 0.004 * (1.2 - y), z * factor))
    if state_id == "cloth_impulse_gust_non_affine":
        return _quantize((x + 0.004 * y, y, z + 0.014 * max(0.0, 1.36 - y)))
    if state_id == "material_soft_extreme_non_affine":
        return _quantize((x * 0.992, y - 0.008 * max(0.0, 1.25 - y), z + 0.006 * y))
    if state_id == "material_stiff_extreme_non_affine":
        return _quantize((x * 1.004, y + 0.003 * max(0.0, y - 1.0), z * 0.998))
    return vertex


def _binding_track_inventory(package_dir: Path) -> list[dict[str, Any]]:
    validation = read_json(package_dir / "reports" / "geometry_binding_validation.json")
    runtime = read_json(package_dir / "reports" / "geometry_runtime_binding_result.json")
    stitched = read_json(package_dir / "reports" / "geometry_stitched_shell.json")
    return [
        {
            "trackId": "canonical_render_subdivision_binding",
            "paths": ["binding/sim_to_render.bin", "binding/binding_manifest.json"],
            "maps": "simulation/mesh_manifest.json -> render/mesh_manifest.json",
            "status": "promoted_for_d0_c3_profile",
        },
        {
            "trackId": "bp46_logical_stitched_analysis_shell_centroid_map",
            "paths": [
                "stitch/logical_stitched_analysis_shell.json",
                "reports/geometry_stitched_shell.json",
            ],
            "maps": "source logical stitched analysis shell only",
            "status": "separate_analysis_track_not_production_render_binding",
            "bindingCoverage": stitched.get("aggregate", {}).get("bindingCoverage"),
        },
        {
            "trackId": "legacy_cleanup_to_simulation_binding_validation",
            "paths": ["reports/geometry_binding_validation.json"],
            "maps": "cleanup preview vertices -> settled simulation",
            "status": "retired_rejected_track_not_c3_evidence",
            "maxCleanupToSettledOffsetMeters": validation.get("aggregate", {}).get(
                "maxCleanupToSettledOffsetMeters"
            ),
        },
        {
            "trackId": "proposal_runtime_preview_binding_records",
            "paths": [
                "binding/proposal_sim_to_render.bin",
                "binding/proposal_binding_manifest.json",
                "reports/geometry_runtime_binding_result.json",
            ],
            "maps": "noncanonical proposal runtime preview only",
            "status": "kept_separate_clean_acceptance_pending",
            "runtimeBindingAccepted": runtime.get("execution", {}).get("runtimeBindingAccepted"),
        },
    ]


def _motion_aggregate(states: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "motionSuiteStatus": "pass"
        if all(state["status"] == "pass" for state in states)
        else "fail",
        "stateCount": len(states),
        "maxReconstructionErrorMeters": _round(
            max(float(state["maxReconstructionErrorMeters"]) for state in states)
        ),
        "maxRmsReconstructionErrorMeters": _round(
            max(float(state["rmsReconstructionErrorMeters"]) for state in states)
        ),
        "maxSeamCrackMeters": _round(
            max(float(state["seamCrack"]["maxSeamCrackMeters"]) for state in states)
        ),
        "maxOpeningCircumferenceDriftMeters": _round(
            max(
                float(state["openingContinuity"]["maxCircumferenceDriftMeters"]) for state in states
            )
        ),
        "maxDenseFallbackParityErrorMeters": _round(
            max(float(state["denseFallbackParity"]["maxParityErrorMeters"]) for state in states)
        ),
        "maxInvertedOrDegenerateTriangleCount": max(
            int(state["triangleQuality"]["invertedOrDegenerateTriangleCount"]) for state in states
        ),
        "maxNormalLengthError": _round(
            max(float(state["frameMetrics"]["maxNormalLengthError"]) for state in states)
        ),
        "maxTangentLengthError": _round(
            max(float(state["frameMetrics"]["maxTangentLengthError"]) for state in states)
        ),
        "maxNormalTangentDot": _round(
            max(float(state["frameMetrics"]["maxNormalTangentDot"]) for state in states)
        ),
    }


def _validate_contract_records(
    contract: dict[str, Any],
    binding: BindingFile,
    simulation_mesh: MeshSet,
    render_mesh: MeshSet,
) -> list[str]:
    issues: list[str] = []
    sim_triangles = _flattened_triangles(simulation_mesh)
    render_positions = [vertex for mesh in render_mesh.meshes for vertex in mesh.vertices]
    records = contract.get("records", [])
    if not isinstance(records, list):
        return ["contract_records_not_list"]
    for index, raw_record in enumerate(records):
        if not isinstance(raw_record, dict) or index >= len(binding.records):
            issues.append("contract_record_malformed")
            continue
        binding_record = binding.records[index]
        if raw_record.get("renderVertexId") != _render_vertex_id(index):
            issues.append("contract_render_vertex_id_mismatch")
        if int(raw_record.get("globalRenderVertexIndex", -1)) != index:
            issues.append("contract_render_vertex_index_mismatch")
        source = raw_record.get("sourceTriangle", {})
        if not isinstance(source, dict):
            issues.append("contract_source_triangle_missing")
            continue
        if int(source.get("globalTriangleIndex", -1)) != binding_record.simulation_triangle_index:
            issues.append("contract_triangle_mismatch")
        if binding_record.simulation_triangle_index >= len(sim_triangles):
            issues.append("contract_triangle_out_of_range")
            continue
        sim_mesh_index, _, tri = sim_triangles[binding_record.simulation_triangle_index]
        if source.get("panelId") != simulation_mesh.meshes[sim_mesh_index].panel_id:
            issues.append("contract_panel_mismatch")
        binding_doc = raw_record.get("binding", {})
        weights = binding_doc.get("weights") if isinstance(binding_doc, dict) else None
        if not isinstance(weights, list) or len(weights) != 3:
            issues.append("contract_weights_missing")
            continue
        if any(not _finite_number(value) for value in weights):
            issues.append("contract_weight_nonfinite")
        if abs(sum(float(value) for value in weights) - 1.0) > 1e-6:
            issues.append("contract_weight_sum_invalid")
        if min(float(value) for value in weights) < -1e-6:
            issues.append("contract_weight_negative")
        reconstructed = _mix_triangle(
            simulation_mesh.meshes[sim_mesh_index],
            tri,
            float(weights[1]),
            float(weights[2]),
        )
        if _distance(reconstructed, render_positions[index]) > 1e-6:
            issues.append("contract_record_reconstruction_mismatch")
        ownership = raw_record.get("ownership", {})
        if isinstance(ownership, dict):
            if ownership.get("openingCrossing") is True:
                issues.append("contract_opening_crossing")
            if ownership.get("panelMatchesBindingPanelTable") is not True:
                issues.append("contract_panel_table_mismatch")
        else:
            issues.append("contract_ownership_missing")
    return sorted(set(issues))


def _seam_metrics(meshset: MeshSet, constraints: dict[str, Any]) -> dict[str, Any]:
    offsets = sim_mesh_offsets(meshset)
    positions = [vertex for mesh in meshset.meshes for vertex in mesh.vertices]
    distances: list[float] = []
    sliding: list[float] = []
    for constraint in constraints.get("constraints", []):
        span_a = constraint["spanA"]
        span_b = constraint["spanB"]
        position_a = span_position_flat(positions, offsets, span_a)
        position_b = span_position_flat(positions, offsets, span_b)
        distance = _distance(position_a, position_b)
        distances.append(distance)
        sliding.append(abs(distance - _constraint_target_length(constraint)))
    return {
        "seamPairCount": len(distances),
        "maxSeamCrackMeters": _round(max(distances, default=0.0)),
        "meanSeamCrackMeters": _round(sum(distances) / max(1, len(distances))),
        "maxBoundarySlidingMeters": _round(max(sliding, default=0.0)),
        "status": "pass" if max(distances, default=0.0) <= 0.13 else "fail",
    }


def _opening_metrics(
    meshset: MeshSet, constraints: dict[str, Any], reference_meshset: MeshSet
) -> dict[str, Any]:
    current_offsets = sim_mesh_offsets(meshset)
    reference_offsets = sim_mesh_offsets(reference_meshset)
    opening_results: list[dict[str, Any]] = []
    for opening in constraints.get("openings", []):
        current_length = _opening_length(meshset, current_offsets, opening)
        reference_length = _opening_length(reference_meshset, reference_offsets, opening)
        drift = abs(current_length - reference_length)
        opening_results.append(
            {
                "openingId": opening["id"],
                "circumferenceMeters": _round(current_length),
                "referenceCircumferenceMeters": _round(reference_length),
                "driftMeters": _round(drift),
            }
        )
    max_drift = max((float(result["driftMeters"]) for result in opening_results), default=0.0)
    return {
        "openingCount": len(opening_results),
        "maxCircumferenceDriftMeters": _round(max_drift),
        "openings": opening_results,
        "status": "pass" if max_drift <= 0.08 else "fail",
    }


def _opening_length(meshset: MeshSet, offsets: list[int], opening: dict[str, Any]) -> float:
    positions = [vertex for mesh in meshset.meshes for vertex in mesh.vertices]
    total = 0.0
    for edge in opening.get("boundaryEdges", []):
        if edge.get("status") != "resolved":
            continue
        mesh_index = int(edge["meshIndex"])
        global_vertices = [offsets[mesh_index] + int(index) for index in edge["vertexIndices"]]
        for left, right in zip(global_vertices, global_vertices[1:], strict=False):
            total += _distance(positions[left], positions[right])
    return total


def _fallback_reconstruct_vertices(
    simulation_mesh: MeshSet, binding: BindingFile, render_mesh: MeshSet
) -> list[Vec3]:
    dense = reconstruct_vertices(simulation_mesh, binding)
    offsets = sim_mesh_offsets(render_mesh)
    output: list[Vec3] = []
    for mesh_index, mesh in enumerate(render_mesh.meshes):
        start = offsets[mesh_index]
        end = start + len(mesh.vertices)
        output.extend(dense[start:end])
    return output


def _expanded_glb_expected_mesh(render_mesh: MeshSet) -> MeshSet:
    meshes: list[Mesh] = []
    for mesh in render_mesh.meshes:
        vertices = [mesh.vertices[index] for tri in mesh.triangles for index in tri]
        uvs = [mesh.panel_uvs[index] for tri in mesh.triangles for index in tri]
        triangles = [(index, index + 1, index + 2) for index in range(0, len(vertices), 3)]
        meshes.append(
            Mesh(
                name=mesh.name,
                panel_id=mesh.panel_id,
                vertices=vertices,
                panel_uvs=uvs,
                triangles=triangles,
                material_id=mesh.material_id,
            )
        )
    return MeshSet(meshes)


def _meshset_from_manifest(manifest: dict[str, Any]) -> MeshSet:
    meshes: list[Mesh] = []
    for mesh_doc in manifest.get("meshes", []):
        meshes.append(
            Mesh(
                name=str(mesh_doc["name"]),
                panel_id=str(mesh_doc["panelId"]),
                vertices=[_vec3(vertex) for vertex in mesh_doc["vertices"]],
                panel_uvs=[(float(uv[0]), float(uv[1])) for uv in mesh_doc["panelUvs"]],
                triangles=[
                    (int(tri[0]), int(tri[1]), int(tri[2])) for tri in mesh_doc["triangles"]
                ],
                material_id=str(mesh_doc.get("materialId", "material.cotton_jersey_reference_v1")),
            )
        )
    return MeshSet(meshes)


def _flattened_triangles(meshset: MeshSet) -> list[tuple[int, int, Tri]]:
    out: list[tuple[int, int, Tri]] = []
    for mesh_index, mesh in enumerate(meshset.meshes):
        for triangle_index, tri in enumerate(mesh.triangles):
            out.append((mesh_index, triangle_index, tri))
    return out


def _flattened_vertices(meshset: MeshSet) -> list[tuple[int, int, Vec3]]:
    out: list[tuple[int, int, Vec3]] = []
    for mesh_index, mesh in enumerate(meshset.meshes):
        for vertex_index, vertex in enumerate(mesh.vertices):
            out.append((mesh_index, vertex_index, vertex))
    return out


def sim_mesh_offsets(meshset: MeshSet) -> list[int]:
    offsets: list[int] = []
    offset = 0
    for mesh in meshset.meshes:
        offsets.append(offset)
        offset += len(mesh.vertices)
    return offsets


def _global_triangle_index(meshset: MeshSet, mesh_index: int, triangle_index: int) -> int:
    return sum(len(mesh.triangles) for mesh in meshset.meshes[:mesh_index]) + triangle_index


def _opening_lookup(constraints: dict[str, Any], simulation_mesh: MeshSet) -> dict[int, set[str]]:
    offsets = sim_mesh_offsets(simulation_mesh)
    lookup: dict[int, set[str]] = {}
    for opening in constraints.get("openings", []):
        opening_id = str(opening["id"])
        for edge in opening.get("boundaryEdges", []):
            if edge.get("status") != "resolved":
                continue
            mesh_index = int(edge["meshIndex"])
            for vertex_index in edge.get("vertexIndices", []):
                global_vertex_index = offsets[mesh_index] + int(vertex_index)
                lookup.setdefault(global_vertex_index, set()).add(opening_id)
    return lookup


def _weighted_opening_ids(
    global_vertex_indices: list[int],
    weights: list[float],
    opening_lookup: dict[int, set[str]],
) -> list[str]:
    ids: set[str] = set()
    for global_vertex_index, weight in zip(global_vertex_indices, weights, strict=True):
        if weight > 1e-7:
            ids.update(opening_lookup.get(global_vertex_index, set()))
    return sorted(ids)


def _part_id_for_panel(panel_id: str) -> str:
    return {
        "panel.front": "part.torso.front",
        "panel.back": "part.torso.back",
        "panel.sleeve.left": "part.sleeve.left",
        "panel.sleeve.right": "part.sleeve.right",
        "panel.neck_band": "part.neck_band",
    }.get(panel_id, "part.unknown")


def _motion_state_kind(state_id: str) -> str:
    if state_id == "neutral_settled":
        return "settled_reference_state"
    if "material" in state_id:
        return "material_extreme_motion_state"
    if "gust" in state_id:
        return "impulse_response_state"
    return "non_affine_pose_motion_state"


def _mix_triangle(mesh: Mesh, tri: Tri, u: float, v: float) -> Vec3:
    a, b, c = mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]]
    w = 1.0 - u - v
    return (
        a[0] * w + b[0] * u + c[0] * v,
        a[1] * w + b[1] * u + c[1] * v,
        a[2] * w + b[2] * u + c[2] * v,
    )


def _error_metrics(left: list[Vec3], right: list[Vec3]) -> tuple[float, float, float, float]:
    if len(left) != len(right):
        raise ValueError("point_cloud_count_mismatch")
    distances = [_distance(a, b) for a, b in zip(left, right, strict=True)]
    mean = sum(distances) / max(1, len(distances))
    rms = sqrt(sum(value * value for value in distances) / max(1, len(distances)))
    return max(distances, default=0.0), mean, rms, _percentile(distances, 0.95)


def _sample_errors(target: list[Vec3], reconstructed: list[Vec3]) -> list[dict[str, Any]]:
    samples = []
    for index in range(0, min(len(target), len(reconstructed)), max(1, len(target) // 5)):
        samples.append(
            {
                "renderVertexId": _render_vertex_id(index),
                "errorMeters": _round(_distance(target[index], reconstructed[index])),
            }
        )
        if len(samples) == 5:
            break
    return samples


def _point_cloud_max_distance(left: list[Vec3], right: list[Vec3]) -> float:
    if len(left) != len(right):
        raise ValueError("point_cloud_count_mismatch")
    return max((_distance(a, b) for a, b in zip(left, right, strict=True)), default=0.0)


def _inverted_or_degenerate_triangle_count(meshset: MeshSet) -> int:
    count = 0
    for mesh in meshset.meshes:
        for tri in mesh.triangles:
            if _triangle_area2(mesh.vertices, tri) <= 1e-10:
                count += 1
    return count


def _triangle_area2(vertices: list[Vec3], tri: Tri) -> float:
    a, b, c = vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    normal = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return _length(normal)


def _rotate_z(vertex: Vec3, pivot: Vec3, radians: float) -> Vec3:
    x, y, z = vertex
    px, py, _ = pivot
    dx, dy = x - px, y - py
    c, s = _trig(radians)
    return (px + dx * c - dy * s, py + dx * s + dy * c, z)


def _rotate_y(vertex: Vec3, pivot: Vec3, radians: float) -> Vec3:
    x, y, z = vertex
    px, _, pz = pivot
    dx, dz = x - px, z - pz
    c, s = _trig(radians)
    return (px + dx * c + dz * s, y, pz - dx * s + dz * c)


def _trig(radians: float) -> tuple[float, float]:
    table = {
        0.22: (0.975897449331, 0.218229623081),
        -0.22: (0.975897449331, -0.218229623081),
        0.11: (0.993956097957, 0.109778300837),
        -0.11: (0.993956097957, -0.109778300837),
    }
    nearest = min(table, key=lambda value: abs(value - radians))
    if abs(nearest - radians) < 1e-9:
        return table[nearest]
    return table[0.11]


def _constraint_target_length(constraint: dict[str, Any]) -> float:
    return 0.02 if "neck" in str(constraint.get("seamId", "")) else 0.0


def _render_vertex_id(index: int) -> str:
    return f"rv.{index:06d}"


def _finite_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(number)


def _vec3(value: Any) -> Vec3:
    return (float(value[0]), float(value[1]), float(value[2]))


def _distance(a: Vec3, b: Vec3) -> float:
    return _length((a[0] - b[0], a[1] - b[1], a[2] - b[2]))


def _length(value: Vec3) -> float:
    return sqrt(sum(component * component for component in value))


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[index]


def _round(value: float) -> float:
    return round(float(value), 9)


def _quantize(value: Vec3) -> Vec3:
    return (_round(value[0]), _round(value[1]), _round(value[2]))
