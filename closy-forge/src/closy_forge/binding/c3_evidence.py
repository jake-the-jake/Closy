from __future__ import annotations

from copy import deepcopy
from math import isfinite, sqrt
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import BindingFile, read_binding
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.geometry.frame_attributes import meshset_frame_metrics
from closy_forge.geometry.glb_io import audit_glb, read_glb_meshset, write_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Tri, Vec3, mesh_bounds
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)
from closy_forge.simulation.material_motion_suite import MATERIAL_MOTION_CANONICAL_POSITION_DIGITS
from closy_forge.simulation.reference_cloth_solver import (
    SOLVER_VERSION,
    simulate_reference_motion_state,
)
from closy_forge.simulation.seam_mapping import (
    span_dominant_global_index,
    span_position_flat,
)

C3_EVIDENCE_VERSION = "closy.production_binding_c3.d0_tshirt.integrity_v2"
C3_STATE_SUITE_VERSION = "closy.binding_solver_state_suite.d0_tshirt.v1"
REQUIRED_OPENING_IDS = ["opening.hem", "opening.left_cuff", "opening.neck", "opening.right_cuff"]
MOTION_STATE_IDS = [
    "neutral_settled",
    "left_arm_raise",
    "right_arm_raise",
    "forward_bend",
    "side_bend",
    "torso_twist",
    "moderate_gust",
    "lightweight_material_extreme",
    "stiff_material_extreme",
    "opening_stress",
    "seam_stress",
]


def prepare_c3_evidence_assets(
    *,
    package_dir: Path,
    settled_mesh: MeshSet,
    constraints: dict[str, Any],
    avatar_contract: dict[str, Any],
    material: dict[str, Any],
) -> None:
    """Persist solver states and a distinct direct-simulation fallback before evaluation."""

    state_dir = package_dir / "simulation" / "motion_states"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_entries: list[dict[str, Any]] = []
    for state_id in MOTION_STATE_IDS:
        if state_id == "neutral_settled":
            mesh = settled_mesh
            diagnostics = {
                "solverVersion": SOLVER_VERSION,
                "stateGenerator": "persisted_reference_settle",
                "finitePositions": True,
            }
            settings: dict[str, Any] = {"source": "simulation/settled_state.json"}
        else:
            result = simulate_reference_motion_state(
                settled_mesh,
                constraints,
                avatar_contract,
                material,
                state_id,
                canonical_position_digits=MATERIAL_MOTION_CANONICAL_POSITION_DIGITS,
            )
            mesh = result.mesh
            diagnostics = result.diagnostics
            settings = {
                "timeStepSeconds": result.settings.time_step_seconds,
                "stepCount": result.settings.step_count,
                "solverIterations": result.settings.solver_iterations,
                "gravityMS2": result.settings.gravity_m_s2,
                "dampingRatio": result.settings.damping_ratio,
                "stretchStiffness": result.settings.stretch_stiffness,
                "seamStiffness": result.settings.seam_stiffness,
                "bendStiffness": result.settings.bend_stiffness,
            }
        state = _state_document(state_id, mesh, settled_mesh, diagnostics, settings, material)
        rel = f"simulation/motion_states/{state_id}.json"
        write_canonical_json(package_dir / rel, state)
        state_entries.append(
            {
                "stateId": state_id,
                "path": rel,
                "sha256": sha256_file(package_dir / rel),
                "contentHash": state["meshContentHash"],
            }
        )
    index_integrity: dict[str, str] = {"stateSuiteHash": ""}
    index: dict[str, Any] = {
        "schemaVersion": 1,
        "suiteVersion": C3_STATE_SUITE_VERSION,
        "stateCount": len(state_entries),
        "stateIds": MOTION_STATE_IDS,
        "states": state_entries,
        "generatorPolicy": "solver_positions_only_render_mesh_never_motion_transformed",
        "integrity": index_integrity,
    }
    index_integrity["stateSuiteHash"] = _hash_with_blank(index, "stateSuiteHash")
    write_canonical_json(state_dir / "index.json", index)

    fallback_path = package_dir / "render" / "simulation_fallback.glb"
    write_glb(
        fallback_path,
        settled_mesh,
        "closy_direct_simulation_fallback_d0_v1",
        (0.10, 0.30, 0.76, 1.0),
    )
    fallback_integrity: dict[str, str] = {"fallbackManifestHash": ""}
    fallback_manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "assetPath": "render/simulation_fallback.glb",
        "representation": "direct_simulation_mesh_conventional_glb",
        "deformationMethod": "replace_positions_from_persisted_simulation_state",
        "callsDenseReconstruction": False,
        "topologyHash": topology_hash(settled_mesh),
        "contentHash": geometry_content_hash(settled_mesh),
        "vertexCount": settled_mesh.vertex_count,
        "triangleCount": settled_mesh.triangle_count,
        "normalStrategy": "recompute_from_fallback_triangles",
        "tangentStrategy": "recompute_from_fallback_panel_uvs",
        "runtimeTier": "conventional_cpu_or_mobile_fallback_d0",
        "limitations": [
            "lower_resolution_than_dense_render_shell",
            "not_gpu_or_mobile_benchmarked",
        ],
        "integrity": fallback_integrity,
    }
    fallback_integrity["fallbackManifestHash"] = _hash_with_blank(
        fallback_manifest, "fallbackManifestHash"
    )
    write_canonical_json(
        package_dir / "render" / "simulation_fallback_manifest.json", fallback_manifest
    )


def build_c3_report_from_package(
    *, package_dir: Path, garment_id: str, garment_class: str
) -> dict[str, Any]:
    sim_manifest = read_json(package_dir / "simulation" / "mesh_manifest.json")
    render_manifest = read_json(package_dir / "render" / "mesh_manifest.json")
    constraints = read_json(package_dir / "simulation" / "constraints.json")
    contract = read_json(package_dir / "binding" / "production_binding_contract.json")
    binding_manifest = read_json(package_dir / "binding" / "binding_manifest.json")
    binding = read_binding(package_dir / "binding" / "sim_to_render.bin")
    state_index = read_json(package_dir / "simulation" / "motion_states" / "index.json")
    if state_index.get("integrity", {}).get("stateSuiteHash") != _hash_with_blank(
        state_index, "stateSuiteHash"
    ):
        raise ValueError("motion_state_index_hash_mismatch")
    if state_index.get("stateIds") != MOTION_STATE_IDS:
        raise ValueError("motion_state_suite_ids_mismatch")
    simulation_mesh = _meshset_from_manifest(sim_manifest)
    render_mesh = _meshset_from_manifest(render_manifest)
    fallback_mesh = read_glb_meshset(package_dir / "render" / "simulation_fallback.glb")
    thresholds = _thresholds(simulation_mesh)
    persisted = _persisted_validation(
        package_dir,
        simulation_mesh,
        render_mesh,
        fallback_mesh,
        binding,
        binding_manifest,
        contract,
    )
    states = [
        _evaluate_state(
            package_dir,
            entry,
            simulation_mesh,
            render_mesh,
            simulation_mesh,
            binding,
            contract,
            constraints,
            thresholds,
        )
        for entry in state_index["states"]
    ]
    aggregate = _aggregate(states)
    literal_pass = persisted["status"] == "pass" and aggregate["motionSuiteStatus"] == "pass"
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "production_binding_c3.demo_tshirt_d0_integrity_v2",
        "stageVersion": C3_EVIDENCE_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "profile": {
            "id": "d0_fixed_avatar_tshirt_solver_state_dense_independent_fallback",
            "scope": "fixed_avatar_public_tshirt_fixture_only",
            "globalPhase6Complete": False,
            "cleanGeometryPromoted": False,
            "canonicalGeometryPromoted": False,
        },
        "sourceAssets": _source_assets(package_dir),
        "bindingTrackInventory": _binding_track_inventory(package_dir, contract),
        "persistedValidation": persisted,
        "thresholds": thresholds,
        "motionSuite": {
            "suiteVersion": state_index["suiteVersion"],
            "stateCount": len(states),
            "stateIds": [state["stateId"] for state in states],
            "states": states,
        },
        "aggregate": aggregate,
        "performanceProfile": {
            "executionState": "not_run_in_canonical_build",
            "canonicalTimingIncluded": False,
            "nonCanonicalCommand": "closy-forge benchmark binding-c3 PACKAGE --output REPORT",
            "requiredWarmups": 3,
            "requiredMeasuredRepeats": 20,
            "warmupCount": 0,
            "repeatCount": 0,
            "denseAndFallbackMeasuredSeparately": True,
            "medianMilliseconds": None,
            "p95Milliseconds": None,
            "peakMemoryBytes": None,
            "reason": "hardware_dependent_measurements_are_excluded_from_canonical_digest",
        },
        "execution": {
            "productionBindingContractWritten": True,
            "persistedByteValidationRun": True,
            "glbAccessorAuditRun": True,
            "solverProducedMotionSuiteRun": True,
            "denseBindingRun": True,
            "independentFallbackRun": True,
            "fallbackBindingRun": True,
            "crackSlidingOpeningChecksRun": True,
            "normalTangentChecksRun": True,
            "performanceWorkloadProfileRun": False,
        },
        "capabilities": {
            "productionBindingC3EvidenceAvailable": True,
            "productionBindingC3ProfileAvailable": literal_pass,
            "denseBindingAvailable": True,
            "independentFallbackAvailable": True,
            "globalPhase6Complete": False,
        },
        "readiness": {
            "status": "d0_c3_literal_profile_pass"
            if literal_pass
            else "partial_scoped_reference_profile",
            "gateC3Status": (
                "complete_for_d0_fixed_avatar_tshirt_profile" if literal_pass else "partial"
            ),
            "acceptedForD0RuntimeBindingProfile": literal_pass,
            "acceptedForGlobalPhase6": False,
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "blockingReasons": [
                *([] if literal_pass else aggregate["failureIds"]),
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
            "performance_evidence_noncanonical_only",
            "not_mobile_gpu_runtime_profile",
        ],
        "integrity": {"productionBindingC3ReportHash": ""},
    }
    report["integrity"]["productionBindingC3ReportHash"] = hash_c3_report(report)
    return report


def hash_c3_report(report: dict[str, Any]) -> str:
    return _hash_with_blank(report, "productionBindingC3ReportHash")


def hash_motion_state(state: dict[str, Any]) -> str:
    return _hash_with_blank(state, "stateHash")


def metric_within_threshold(value: Any, threshold: Any) -> bool:
    try:
        measured = float(value)
        limit = float(threshold)
    except (TypeError, ValueError):
        return False
    return isfinite(measured) and isfinite(limit) and limit >= 0.0 and measured <= limit


def _state_document(
    state_id: str,
    mesh: MeshSet,
    reference: MeshSet,
    diagnostics: dict[str, Any],
    settings: dict[str, Any],
    material: dict[str, Any],
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "schemaVersion": 1,
        "stateId": state_id,
        "stateSuiteVersion": C3_STATE_SUITE_VERSION,
        "solverVersion": SOLVER_VERSION,
        "sourceTopologyHash": topology_hash(reference),
        "meshTopologyHash": topology_hash(mesh),
        "meshContentHash": geometry_content_hash(mesh),
        "avatarContractVersion": "closy.reference_avatar.v1",
        "materialParameters": material,
        "solverSettings": settings,
        "stateProvenance": "deterministic_public_fixture_reference_solver",
        "diagnostics": diagnostics,
        "meshes": [
            {
                "name": item.name,
                "panelId": item.panel_id,
                "positions": [list(point) for point in item.vertices],
            }
            for item in mesh.meshes
        ],
        "integrity": {"stateHash": ""},
    }
    state["integrity"]["stateHash"] = _hash_with_blank(state, "stateHash")
    return state


def _persisted_validation(
    package_dir: Path,
    simulation_mesh: MeshSet,
    render_mesh: MeshSet,
    fallback_mesh: MeshSet,
    binding: BindingFile,
    binding_manifest: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    issues: list[str] = []
    records = contract.get("records", [])
    ids = [str(record.get("renderVertexId")) for record in records if isinstance(record, dict)]
    expected_ids = [f"rv.{index:06d}" for index in range(render_mesh.vertex_count)]
    if ids != expected_ids:
        issues.append("stable_render_vertex_ids_invalid")
    if binding.simulation_topology_hash != topology_hash(simulation_mesh):
        issues.append("binding_simulation_topology_stale")
    if binding.render_topology_hash != topology_hash(render_mesh):
        issues.append("binding_render_topology_stale")
    if binding_manifest.get("simulationTopologyHash") != topology_hash(simulation_mesh):
        issues.append("binding_manifest_simulation_topology_stale")
    if binding_manifest.get("renderTopologyHash") != topology_hash(render_mesh):
        issues.append("binding_manifest_render_topology_stale")
    authority = contract.get("authority", {})
    if authority.get("status") != "authoritative" or authority.get("routeId") != (
        "settled_simulation_to_subdivided_render_v1"
    ):
        issues.append("binding_authority_conflict")
    dense = reconstruct_vertices(simulation_mesh, binding)
    target = [point for mesh in render_mesh.meshes for point in mesh.vertices]
    max_error = _max_pair_distance(dense, target)
    if max_error > 1e-6:
        issues.append("persisted_rest_reconstruction_error")
    fallback_manifest = read_json(package_dir / "render" / "simulation_fallback_manifest.json")
    if fallback_manifest.get("callsDenseReconstruction") is not False:
        issues.append("fallback_not_independent")
    if topology_hash(fallback_mesh) != topology_hash(_expanded_glb_expected_mesh(simulation_mesh)):
        issues.append("fallback_glb_topology_mismatch")
    dense_audit = audit_glb(package_dir / "render" / "fallback.glb")
    fallback_audit = audit_glb(package_dir / "render" / "simulation_fallback.glb")
    return {
        "status": "pass" if not issues else "fail",
        "issues": sorted(set(issues)),
        "binaryBindingReopened": True,
        "motionStatesReopened": True,
        "denseRenderGlbDecoded": True,
        "fallbackRenderGlbDecoded": True,
        "sourceSimulationTopologyHash": topology_hash(simulation_mesh),
        "destinationRenderTopologyHash": topology_hash(render_mesh),
        "fallbackTopologyHash": topology_hash(fallback_mesh),
        "recordCount": len(binding.records),
        "stableRenderVertexIdCount": len(set(ids)),
        "duplicateRenderVertexIds": len(set(ids)) != len(ids),
        "restStateMaxReconstructionErrorMeters": _round(max_error),
        "denseGlbPositionAccessorCount": dense_audit["semanticAccessorCounts"].get("POSITION", 0),
        "fallbackGlbPositionAccessorCount": fallback_audit["semanticAccessorCounts"].get(
            "POSITION", 0
        ),
    }


def _evaluate_state(
    package_dir: Path,
    entry: dict[str, Any],
    reference_sim: MeshSet,
    render_mesh: MeshSet,
    fallback_reference: MeshSet,
    binding: BindingFile,
    contract: dict[str, Any],
    constraints: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    path = package_dir / str(entry["path"])
    if sha256_file(path) != entry.get("sha256"):
        raise ValueError("motion_state_index_content_hash_mismatch")
    state = read_json(path)
    state_mesh = _meshset_from_state(state, reference_sim)
    dense_positions = reconstruct_vertices(state_mesh, binding)
    dense_positions_repeat = reconstruct_vertices(
        state_mesh, read_binding(package_dir / "binding" / "sim_to_render.bin")
    )
    dense_mesh = _replace_positions(render_mesh, dense_positions)
    fallback_mesh = _replace_positions(
        fallback_reference, [p for m in state_mesh.meshes for p in m.vertices]
    )
    seam = _seam_metrics(
        state_mesh, reference_sim, dense_positions, render_mesh, contract, constraints
    )
    openings = _opening_metrics(state_mesh, reference_sim, constraints)
    agreement = _dense_fallback_agreement(dense_mesh, fallback_mesh)
    dense_frames = meshset_frame_metrics(dense_mesh)
    fallback_frames = meshset_frame_metrics(fallback_mesh)
    triangle_count = _degenerate_count(dense_mesh) + _degenerate_count(fallback_mesh)
    deterministic_error = _max_pair_distance(dense_positions, dense_positions_repeat)
    rest_target_error: float | None = None
    if state["stateId"] == "neutral_settled":
        rest_target_error = _max_pair_distance(
            dense_positions, [point for mesh in render_mesh.meshes for point in mesh.vertices]
        )
    checks = {
        "deterministicRecompute": deterministic_error <= 1e-12,
        "seamCrackResidual": metric_within_threshold(
            seam["maxCrackResidualMeters"], thresholds["maxSeamCrackResidualMeters"]
        ),
        "tangentialSliding": metric_within_threshold(
            seam["maxTangentialSlidingMeters"], thresholds["maxTangentialSlidingMeters"]
        ),
        "openingDrift": metric_within_threshold(
            openings["maxCircumferenceDriftMeters"],
            thresholds["maxOpeningCircumferenceDriftMeters"],
        ),
        "openingNonCollapse": openings["collapsedOpeningCount"] == 0,
        "denseFallbackLandmarks": agreement["maxPanelCentroidDeltaMeters"]
        <= thresholds["maxDenseFallbackPanelCentroidDeltaMeters"],
        "denseFallbackSilhouette": agreement["silhouetteBoundsDeltaNormalised"]
        <= thresholds["maxDenseFallbackSilhouetteBoundsDeltaNormalised"],
        "frames": _frames_valid(dense_frames) and _frames_valid(fallback_frames),
        "triangleQuality": triangle_count == 0,
        "finite": all(isfinite(value) for point in dense_positions for value in point),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "stateId": state["stateId"],
        "statePath": str(entry["path"]),
        "stateSha256": sha256_file(path),
        "stateHash": state["integrity"]["stateHash"],
        "stateProvenance": state["stateProvenance"],
        "solverVersion": state["solverVersion"],
        "status": "pass" if not failures else "fail",
        "simulationTopologyHash": topology_hash(state_mesh),
        "deformedSimulationContentHash": geometry_content_hash(state_mesh),
        "renderTopologyHash": topology_hash(dense_mesh),
        "deformedRenderContentHash": geometry_content_hash(dense_mesh),
        "motionTargetComparison": {
            "status": "executed_rest_target_only"
            if rest_target_error is not None
            else "not_run_no_independent_motion_oracle",
            "restTargetErrorMeters": _round(rest_target_error)
            if rest_target_error is not None
            else None,
            "renderMotionTransformUsedAsOracle": False,
        },
        "deterministicRecomputeErrorMeters": _round(deterministic_error),
        "seamCrack": seam,
        "boundarySliding": {
            "maxTangentialSlidingMeters": seam["maxTangentialSlidingMeters"],
            "metricFrame": "persisted_reference_seam_tangent",
        },
        "openingContinuity": openings,
        "triangleQuality": {
            "invertedOrDegenerateTriangleCount": triangle_count,
            "status": "pass" if triangle_count == 0 else "fail",
        },
        "frameMetrics": {"dense": dense_frames, "fallback": fallback_frames},
        "denseFallbackAgreement": agreement,
        "deformedBounds": mesh_bounds(dense_mesh),
        "checks": checks,
        "failureIds": [f"motion_state.{state['stateId']}.{failure}" for failure in failures],
    }


def _thresholds(mesh: MeshSet) -> dict[str, Any]:
    bounds = mesh_bounds(mesh)
    garment_scale = max(float(value) for value in bounds["size"])
    edge_lengths = [
        _distance(item.vertices[a], item.vertices[b])
        for item in mesh.meshes
        for tri in item.triangles
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0]))
    ]
    local_edge = sum(edge_lengths) / max(1, len(edge_lengths))
    return {
        "units": "metres",
        "garmentScaleMeters": _round(garment_scale),
        "meanLocalEdgeLengthMeters": _round(local_edge),
        "maxSeamCrackResidualMeters": _round(min(0.060, max(0.012, local_edge * 0.55))),
        "maxTangentialSlidingMeters": _round(min(0.045, max(0.010, local_edge * 0.40))),
        "maxOpeningCircumferenceDriftMeters": _round(min(0.080, garment_scale * 0.08)),
        "maxDenseFallbackPanelCentroidDeltaMeters": _round(min(0.030, local_edge * 0.30)),
        "maxDenseFallbackSilhouetteBoundsDeltaNormalised": 0.025,
        "hardUpperBounds": {"crackMeters": 0.060, "slidingMeters": 0.045},
        "basis": "fixture_scale_and_mean_local_edge_with_documented_hard_cap",
    }


def _seam_metrics(
    current: MeshSet,
    reference: MeshSet,
    dense_positions: list[Vec3],
    render_mesh: MeshSet,
    contract: dict[str, Any],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    current_positions = [p for mesh in current.meshes for p in mesh.vertices]
    reference_positions = [p for mesh in reference.meshes for p in mesh.vertices]
    offsets = _offsets(current)
    render_source_map = _render_vertex_source_weights(contract)
    records: list[dict[str, Any]] = []
    by_seam: dict[str, list[dict[str, Any]]] = {}
    for item in constraints.get("constraints", []):
        left = span_dominant_global_index(item["spanA"], offsets)
        right = span_dominant_global_index(item["spanB"], offsets)
        intended = (
            0.02
            if "panel.neck_band" in {str(item["spanA"]["panelId"]), str(item["spanB"]["panelId"])}
            else 0.0
        )
        current_left = span_position_flat(current_positions, offsets, item["spanA"])
        current_right = span_position_flat(current_positions, offsets, item["spanB"])
        reference_left = span_position_flat(reference_positions, offsets, item["spanA"])
        reference_right = span_position_flat(reference_positions, offsets, item["spanB"])
        separation = _distance(current_left, current_right)
        reference_mid = _mid(reference_left, reference_right)
        current_mid = _mid(current_left, current_right)
        tangent = _normalise(_sub(reference_right, reference_left))
        sliding = abs(_dot(_sub(current_mid, reference_mid), tangent))
        dense_left = _best_render_vertex_for_source(render_source_map, left)
        dense_right = _best_render_vertex_for_source(render_source_map, right)
        dense_separation = (
            _distance(dense_positions[dense_left], dense_positions[dense_right])
            if dense_left is not None and dense_right is not None
            else separation
        )
        seam_id = str(item["seamId"])
        record: dict[str, Any] = {
            "seamId": seam_id,
            "intendedSeparationMeters": intended,
            "sourceSeparationMeters": _round(separation),
            "denseDuplicatedSeamSeparationMeters": _round(dense_separation),
            "crackResidualMeters": _round(max(0.0, dense_separation - intended)),
            "tangentialSlidingMeters": _round(sliding),
        }
        records.append(record)
        by_seam.setdefault(seam_id, []).append(record)
    seam_summaries = [
        {
            "seamId": seam_id,
            "pairCount": len(items),
            "maxCrackResidualMeters": max(float(item["crackResidualMeters"]) for item in items),
            "maxTangentialSlidingMeters": max(
                float(item["tangentialSlidingMeters"]) for item in items
            ),
        }
        for seam_id, items in sorted(by_seam.items())
    ]
    return {
        "metricVersion": "closy.seam_crack_sliding.dense_split_v2",
        "units": "metres",
        "pairCount": len(records),
        "maxCrackResidualMeters": max(
            (float(item["crackResidualMeters"]) for item in records), default=0.0
        ),
        "maxTangentialSlidingMeters": max(
            (float(item["tangentialSlidingMeters"]) for item in records), default=0.0
        ),
        "seams": seam_summaries,
        "samples": records[:12],
    }


def _opening_metrics(
    current: MeshSet, reference: MeshSet, constraints: dict[str, Any]
) -> dict[str, Any]:
    current_offsets = _offsets(current)
    reference_offsets = _offsets(reference)
    results: list[dict[str, Any]] = []
    for opening in constraints.get("openings", []):
        current_length = _opening_length(current, current_offsets, opening)
        reference_length = _opening_length(reference, reference_offsets, opening)
        results.append(
            {
                "openingId": str(opening["id"]),
                "circumferenceMeters": _round(current_length),
                "referenceCircumferenceMeters": _round(reference_length),
                "driftMeters": _round(abs(current_length - reference_length)),
                "scaleNormalisedDrift": _round(
                    abs(current_length - reference_length) / max(reference_length, 1e-9)
                ),
                "collapsed": current_length < max(0.01, reference_length * 0.25),
            }
        )
    ids = sorted(str(item["openingId"]) for item in results)
    return {
        "openingIds": ids,
        "requiredOpeningIds": REQUIRED_OPENING_IDS,
        "allRequiredOpeningsEvaluated": ids == REQUIRED_OPENING_IDS,
        "maxCircumferenceDriftMeters": max(
            (float(item["driftMeters"]) for item in results), default=0.0
        ),
        "collapsedOpeningCount": sum(bool(item["collapsed"]) for item in results),
        "openings": results,
    }


def _dense_fallback_agreement(dense: MeshSet, fallback: MeshSet) -> dict[str, Any]:
    dense_centroids = {mesh.panel_id: _centroid(mesh.vertices) for mesh in dense.meshes}
    fallback_centroids = {mesh.panel_id: _centroid(mesh.vertices) for mesh in fallback.meshes}
    shared = sorted(set(dense_centroids) & set(fallback_centroids))
    centroid_deltas = {
        panel_id: _round(_distance(dense_centroids[panel_id], fallback_centroids[panel_id]))
        for panel_id in shared
    }
    dense_bounds = mesh_bounds(dense)
    fallback_bounds = mesh_bounds(fallback)
    scale = max(max(dense_bounds["size"]), 1e-9)
    silhouette_delta = max(
        abs(float(a) - float(b)) / scale
        for key in ("min", "max")
        for a, b in zip(dense_bounds[key][:2], fallback_bounds[key][:2], strict=True)
    )
    return {
        "comparisonKind": "independent_topology_shared_panel_landmarks_and_xy_bounds",
        "fallbackCallsDensePath": False,
        "denseVertexCount": dense.vertex_count,
        "fallbackVertexCount": fallback.vertex_count,
        "sharedPanelIds": shared,
        "panelCentroidDeltasMeters": centroid_deltas,
        "maxPanelCentroidDeltaMeters": max(centroid_deltas.values(), default=0.0),
        "silhouetteBoundsDeltaNormalised": _round(silhouette_delta),
    }


def _aggregate(states: list[dict[str, Any]]) -> dict[str, Any]:
    failures = sorted({failure for state in states for failure in state["failureIds"]})
    rest_errors = [
        state["motionTargetComparison"]["restTargetErrorMeters"]
        for state in states
        if state["motionTargetComparison"]["restTargetErrorMeters"] is not None
    ]
    return {
        "motionSuiteStatus": "pass" if not failures else "fail",
        "stateCount": len(states),
        "failureIds": failures,
        "restStateMaxReconstructionErrorMeters": max(rest_errors, default=0.0),
        "maxReconstructionErrorMeters": max(rest_errors, default=0.0),
        "maxRmsReconstructionErrorMeters": max(rest_errors, default=0.0),
        "maxSeamCrackMeters": max(
            float(state["seamCrack"]["maxCrackResidualMeters"]) for state in states
        ),
        "maxSeamCrackResidualMeters": max(
            float(state["seamCrack"]["maxCrackResidualMeters"]) for state in states
        ),
        "maxTangentialSlidingMeters": max(
            float(state["seamCrack"]["maxTangentialSlidingMeters"]) for state in states
        ),
        "maxOpeningCircumferenceDriftMeters": max(
            float(state["openingContinuity"]["maxCircumferenceDriftMeters"]) for state in states
        ),
        "maxDenseFallbackParityErrorMeters": max(
            float(state["denseFallbackAgreement"]["maxPanelCentroidDeltaMeters"])
            for state in states
        ),
        "maxDenseFallbackPanelCentroidDeltaMeters": max(
            float(state["denseFallbackAgreement"]["maxPanelCentroidDeltaMeters"])
            for state in states
        ),
        "maxInvertedOrDegenerateTriangleCount": max(
            int(state["triangleQuality"]["invertedOrDegenerateTriangleCount"]) for state in states
        ),
    }


def _source_assets(package_dir: Path) -> dict[str, Any]:
    paths = {
        "productionBindingContract": "binding/production_binding_contract.json",
        "binaryBinding": "binding/sim_to_render.bin",
        "bindingManifest": "binding/binding_manifest.json",
        "simulationMeshManifest": "simulation/mesh_manifest.json",
        "renderMeshManifest": "render/mesh_manifest.json",
        "denseRenderGlb": "render/fallback.glb",
        "independentFallbackGlb": "render/simulation_fallback.glb",
        "independentFallbackManifest": "render/simulation_fallback_manifest.json",
        "motionStateIndex": "simulation/motion_states/index.json",
    }
    return {
        key: {"path": rel, "sha256": sha256_file(package_dir / rel)} for key, rel in paths.items()
    }


def _binding_track_inventory(package_dir: Path, contract: dict[str, Any]) -> dict[str, Any]:
    legacy = read_json(package_dir / "reports" / "geometry_binding_validation.json")
    return {
        "authoritativeRouteId": contract.get("authority", {}).get("routeId"),
        "authoritativeTrackCount": 1,
        "tracks": [
            {
                "trackId": "settled_simulation_to_subdivided_render_v1",
                "status": "authoritative",
                "sourcePath": "simulation/mesh_manifest.json",
                "densePath": "render/mesh_manifest.json",
                "fallbackPath": "render/simulation_fallback.glb",
            },
            {
                "trackId": "legacy_cleanup_binding_candidate",
                "status": "deprecated_historical_evidence_not_runtime_authority",
                "maximumOffsetMeters": legacy.get("aggregate", {}).get(
                    "maxCleanupToSettledOffsetMeters"
                ),
            },
            {
                "trackId": "proposal_runtime_preview",
                "status": "noncanonical_preview_only_not_runtime_authority",
            },
            {
                "trackId": "bp46_stitched_topology",
                "status": "topology_equivalence_evidence_for_authoritative_source",
            },
        ],
    }


def _meshset_from_manifest(manifest: dict[str, Any]) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                name=str(item["name"]),
                panel_id=str(item["panelId"]),
                vertices=[_vec3(point) for point in item["vertices"]],
                panel_uvs=[(float(uv[0]), float(uv[1])) for uv in item["panelUvs"]],
                triangles=[_tri(tri) for tri in item["triangles"]],
                material_id=str(item.get("materialId", "material.cotton_jersey_reference_v1")),
            )
            for item in manifest["meshes"]
        ]
    )


def _meshset_from_state(state: dict[str, Any], reference: MeshSet) -> MeshSet:
    if state.get("meshTopologyHash") != topology_hash(reference):
        raise ValueError("motion_state_topology_hash_mismatch")
    meshes = []
    for source, state_mesh in zip(reference.meshes, state["meshes"], strict=True):
        if state_mesh["panelId"] != source.panel_id or state_mesh["name"] != source.name:
            raise ValueError("motion_state_mesh_identity_mismatch")
        meshes.append(
            Mesh(
                source.name,
                source.panel_id,
                [_vec3(point) for point in state_mesh["positions"]],
                source.panel_uvs,
                source.triangles,
                source.material_id,
            )
        )
    meshset = MeshSet(meshes)
    if geometry_content_hash(meshset) != state.get("meshContentHash"):
        raise ValueError("motion_state_content_hash_mismatch")
    if _hash_with_blank(state, "stateHash") != state.get("integrity", {}).get("stateHash"):
        raise ValueError("motion_state_integrity_hash_mismatch")
    return meshset


def _replace_positions(meshset: MeshSet, positions: list[Vec3]) -> MeshSet:
    meshes: list[Mesh] = []
    offset = 0
    for mesh in meshset.meshes:
        count = len(mesh.vertices)
        meshes.append(
            Mesh(
                mesh.name,
                mesh.panel_id,
                positions[offset : offset + count],
                mesh.panel_uvs,
                mesh.triangles,
                mesh.material_id,
            )
        )
        offset += count
    if offset != len(positions):
        raise ValueError("replacement_position_count_mismatch")
    return MeshSet(meshes)


def _expanded_glb_expected_mesh(meshset: MeshSet) -> MeshSet:
    meshes: list[Mesh] = []
    for mesh in meshset.meshes:
        vertices: list[Vec3] = []
        uvs: list[tuple[float, float]] = []
        triangles: list[Tri] = []
        for tri in mesh.triangles:
            base = len(vertices)
            vertices.extend(mesh.vertices[index] for index in tri)
            uvs.extend(mesh.panel_uvs[index] for index in tri)
            triangles.append((base, base + 1, base + 2))
        meshes.append(Mesh(mesh.name, mesh.panel_id, vertices, uvs, triangles, mesh.material_id))
    return MeshSet(meshes)


def _render_vertex_source_weights(contract: dict[str, Any]) -> dict[int, list[tuple[int, float]]]:
    result: dict[int, list[tuple[int, float]]] = {}
    for record in contract.get("records", []):
        render_index = int(record["globalRenderVertexIndex"])
        source_indices = record["sourceTriangle"]["globalVertexIndices"]
        weights = record["binding"]["weights"]
        for source_index, weight in zip(source_indices, weights, strict=True):
            result.setdefault(int(source_index), []).append((render_index, float(weight)))
    return result


def _best_render_vertex_for_source(
    lookup: dict[int, list[tuple[int, float]]], source_index: int
) -> int | None:
    candidates = lookup.get(source_index, [])
    return max(candidates, key=lambda item: (item[1], -item[0]))[0] if candidates else None


def _opening_length(meshset: MeshSet, offsets: list[int], opening: dict[str, Any]) -> float:
    positions = [point for mesh in meshset.meshes for point in mesh.vertices]
    total = 0.0
    for edge in opening.get("boundaryEdges", []):
        if edge.get("status") != "resolved":
            continue
        mesh_offset = offsets[int(edge["meshIndex"])]
        indices = [mesh_offset + int(index) for index in edge["vertexIndices"]]
        if len(indices) >= 2:
            total += _distance(positions[indices[0]], positions[indices[1]])
    return total


def _offsets(meshset: MeshSet) -> list[int]:
    out: list[int] = []
    offset = 0
    for mesh in meshset.meshes:
        out.append(offset)
        offset += len(mesh.vertices)
    return out


def _frames_valid(metrics: dict[str, Any]) -> bool:
    return bool(
        int(metrics["normalVectorCount"]) == int(metrics["finiteNormalCount"])
        and int(metrics["tangentVectorCount"]) == int(metrics["finiteTangentCount"])
        and float(metrics["maxNormalLengthError"]) <= 1e-6
        and float(metrics["maxTangentLengthError"]) <= 1e-6
        and float(metrics["maxNormalTangentDot"]) <= 1e-6
    )


def _degenerate_count(meshset: MeshSet) -> int:
    return sum(
        _triangle_area2(mesh.vertices, tri) <= 1e-10
        for mesh in meshset.meshes
        for tri in mesh.triangles
    )


def _triangle_area2(vertices: list[Vec3], tri: Tri) -> float:
    a, b, c = (vertices[index] for index in tri)
    ab, ac = _sub(b, a), _sub(c, a)
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return _length(cross)


def _centroid(points: list[Vec3]) -> Vec3:
    count = max(1, len(points))
    return tuple(sum(point[index] for point in points) / count for index in range(3))  # type: ignore[return-value]


def _max_pair_distance(left: list[Vec3], right: list[Vec3]) -> float:
    if len(left) != len(right):
        raise ValueError("point_count_mismatch")
    return max((_distance(a, b) for a, b in zip(left, right, strict=True)), default=0.0)


def _mid(a: Vec3, b: Vec3) -> Vec3:
    return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5)


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(value: Vec3) -> float:
    return sqrt(_dot(value, value))


def _normalise(value: Vec3) -> Vec3:
    length = _length(value)
    return (0.0, 0.0, 0.0) if length <= 1e-12 else tuple(v / length for v in value)  # type: ignore[return-value]


def _distance(a: Vec3, b: Vec3) -> float:
    return _length(_sub(a, b))


def _vec3(value: Any) -> Vec3:
    return (float(value[0]), float(value[1]), float(value[2]))


def _tri(value: Any) -> Tri:
    return (int(value[0]), int(value[1]), int(value[2]))


def _round(value: float) -> float:
    return round(float(value), 9)


def _hash_with_blank(document: dict[str, Any], key: str) -> str:
    payload = deepcopy(document)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity[key] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
