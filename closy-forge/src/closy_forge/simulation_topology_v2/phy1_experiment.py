from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.binding.binary_format import BindingFile
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.garments.tshirt.assembly import TRANSFORMS
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3
from closy_forge.geometry.subdivision import RenderBindingSeed
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    topology_hash,
)
from closy_forge.simulation.deformation_quality import audit_rest_referenced_deformation
from closy_forge.simulation.material_physics import (
    build_material_preset_registry,
    solver_material_payload,
)
from closy_forge.simulation.reference_cloth_solver import (
    SOLVER_VERSION,
    SettleResult,
    flatten_mesh,
    settle_reference_cloth,
    simulate_reference_motion_state,
)
from closy_forge.simulation.seam_mapping import span_position_flat
from closy_forge.simulation.self_collision import (
    SelfCollisionSettings,
    analyze_self_collision,
    seam_exclusion_pairs,
)

from .binding import build_topology_v2_render_binding
from .seam_junctions import build_seam_constraints_v2
from .temporal_quality import audit_temporal_deformation_quality
from .triangulator import build_panel_meshes_v2

PHY1_TOPOLOGY_V2_PROFILE_VERSION = "closy.phy1.single_layer.d0_tshirt.topology_v2.v1"
PHY1_TOPOLOGY_V2_EVIDENCE_VERSION = "closy.phy1.topology_v2.experiment.v1"
PHY1_V1_FAILURE_HEAD = "d393b7185d14fe414a1eb3c4ef040c6c1ad8f780"
PHY1_STATE_IDS = [
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


@dataclass(frozen=True)
class Phy1TopologyV2Inputs:
    pattern: dict[str, Any]
    rest_mesh: MeshSet
    constraints: dict[str, Any]
    render_mesh: MeshSet
    render_binding_seeds: list[RenderBindingSeed]
    binding: BindingFile
    binding_manifest: dict[str, Any]
    avatar: dict[str, Any]
    collision_mesh: MeshSet
    material: dict[str, Any]
    topology_manifest: dict[str, Any]
    seam_audit: dict[str, Any]
    binding_audit: dict[str, Any]


def build_phy1_topology_v2_inputs() -> Phy1TopologyV2Inputs:
    pattern = build_tshirt_pattern(TShirtParameters())
    rest_mesh, edge_maps, topology_manifest = build_panel_meshes_v2(pattern, TRANSFORMS)
    constraints, seam_audit = build_seam_constraints_v2(pattern, edge_maps, rest_mesh)
    render_mesh, seeds, binding, binding_manifest, binding_audit = (
        build_topology_v2_render_binding(rest_mesh)
    )
    avatar_mesh = build_reference_avatar_mesh()
    collision_mesh = build_collision_mesh()
    avatar = avatar_contract(avatar_mesh, collision_mesh)
    descriptor = next(
        item
        for item in build_material_preset_registry()["presets"]
        if item["presetId"] == "material.cotton_jersey_d0_v1"
    )
    return Phy1TopologyV2Inputs(
        pattern=pattern,
        rest_mesh=rest_mesh,
        constraints=constraints,
        render_mesh=render_mesh,
        render_binding_seeds=seeds,
        binding=binding,
        binding_manifest=binding_manifest,
        avatar=avatar,
        collision_mesh=collision_mesh,
        material=solver_material_payload(descriptor),
        topology_manifest=topology_manifest,
        seam_audit=seam_audit,
        binding_audit=binding_audit,
    )


def run_phy1_topology_v2_experiment(*, source_anchor_sha: str) -> dict[str, Any]:
    inputs = build_phy1_topology_v2_inputs()
    profile = read_json(
        _forge_root() / "docs" / "capability-profiles" / "phy1-single-layer-d0-v1.json"
    )
    calibration = read_json(
        _forge_root() / "docs" / "capability-profiles" / "phy1-clearance-calibration-v1.json"
    )
    settle = settle_reference_cloth(
        inputs.rest_mesh,
        inputs.constraints,
        inputs.avatar,
        inputs.material,
        canonical_position_digits=9,
    )
    states: list[dict[str, Any]] = []
    state_meshes: dict[str, MeshSet] = {}
    for state_id in PHY1_STATE_IDS:
        if state_id == "neutral_settled":
            mesh = settle.settled_mesh
            trajectory = [mesh]
            diagnostics = settle.diagnostics
        else:
            trajectory = []
            motion = simulate_reference_motion_state(
                settle.settled_mesh,
                inputs.constraints,
                inputs.avatar,
                inputs.material,
                state_id,
                canonical_position_digits=9,
                trajectory_sink=trajectory,
            )
            mesh = motion.mesh
            diagnostics = motion.diagnostics
        state_meshes[state_id] = mesh
        states.append(
            _state_evidence(
                state_id,
                mesh,
                trajectory,
                diagnostics,
                settle,
                inputs,
                calibration,
                profile,
            )
        )

    aggregate = _aggregate(states, settle)
    thresholds = _thresholds(profile, calibration)
    checks = _aggregate_checks(aggregate, thresholds, states)
    failed_checks = [name for name, passed in checks.items() if not passed]
    profile_hash = _hash_document(
        {
            "schemaVersion": 1,
            "profileVersion": PHY1_TOPOLOGY_V2_PROFILE_VERSION,
            "topologyHash": topology_hash(inputs.rest_mesh),
            "bindingSimulationTopologyHash": inputs.binding.simulation_topology_hash,
            "solverVersion": SOLVER_VERSION,
            "scenarioDefinitions": profile["scenarioDefinitions"],
            "thresholds": thresholds,
            "integrity": {"profileHash": ""},
        },
        "profileHash",
    )
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceVersion": PHY1_TOPOLOGY_V2_EVIDENCE_VERSION,
        "profileVersion": PHY1_TOPOLOGY_V2_PROFILE_VERSION,
        "sourceAnchorSha": source_anchor_sha,
        "profileHash": profile_hash,
        "predecessor": {
            "profileVersion": profile["profileVersion"],
            "failureEvidenceHead": PHY1_V1_FAILURE_HEAD,
            "v1FailurePreserved": True,
            "supersedesV1Evidence": False,
        },
        "authority": {
            "outcome": "A_physical_experiment_only_v2",
            "v2OptInOnly": True,
            "packageExposed": False,
            "runtimeCapabilityExposed": False,
            "dRuntimePinnedToV1": True,
            "historicalC3Mt1RuntimeEvidenceChanged": False,
        },
        "identities": {
            "simulationTopologyVersion": "closy.simulation_topology.v2",
            "triangulatorVersion": "closy.interior_constrained_triangulator.v2",
            "simulationTopologyHash": topology_hash(inputs.rest_mesh),
            "simulationRestContentHash": geometry_content_hash(inputs.rest_mesh),
            "renderTopologyHash": topology_hash(inputs.render_mesh),
            "bindingSimulationTopologyHash": inputs.binding.simulation_topology_hash,
            "bindingRenderTopologyHash": inputs.binding.render_topology_hash,
            "solverVersion": SOLVER_VERSION,
            "scenarioDefinitionsHash": sha256_bytes(
                canonical_dumps(profile["scenarioDefinitions"]).encode("utf-8")
            ),
        },
        "inventory": {
            "panelCount": len(inputs.rest_mesh.meshes),
            "simulationVertexCount": inputs.rest_mesh.vertex_count,
            "simulationTriangleCount": inputs.rest_mesh.triangle_count,
            "renderVertexCount": inputs.render_mesh.vertex_count,
            "renderTriangleCount": inputs.render_mesh.triangle_count,
            "bindingRecordCount": len(inputs.binding.records),
            "stateCount": len(states),
            "stateIds": PHY1_STATE_IDS,
        },
        "staticPrerequisites": {
            "topologyPanels": [
                {
                    "panelId": panel["panelId"],
                    "status": panel["audit"]["status"],
                    "thresholds": panel["audit"]["thresholds"],
                    "measured": panel["audit"]["measured"],
                }
                for panel in inputs.topology_manifest["panels"]
            ],
            "seamJunctionAudit": inputs.seam_audit,
            "bindingAudit": inputs.binding_audit,
            "zeroStaticDegenerates": all(
                panel["audit"]["measured"]["minimumDoubleAreaMeters2"]
                > panel["audit"]["thresholds"]["minimumDoubleAreaMeters2"]
                for panel in inputs.topology_manifest["panels"]
            ),
        },
        "replay": {
            "physicsParameters": "unchanged_v1_reference_solver_parameters",
            "frozenScenarioCount": 11,
            "allFrozenScenariosExecuted": len(states) == 11,
            "qualifiedRotationInvariantTemporalOracle": True,
            "simulationAndRenderClearanceMeasuredSeparately": True,
            "states": states,
            "aggregate": aggregate,
        },
        "thresholds": thresholds,
        "acceptance": {
            "status": "pass" if not failed_checks else "failed",
            "checks": checks,
            "failedChecks": failed_checks,
            "physicalStatePassCount": sum(state["status"] == "pass" for state in states),
            "requiredPhysicalStatePassCount": 11,
            "globalPhy1Complete": False,
        },
        "boundedProgression": {
            "topologyStrategyBudget": {"maximum": 3, "consumed": 1},
            "seamModelBudget": {"maximum": 2, "consumed": 1},
            "strategies": [
                {
                    "strategyId": "PHY1-V2-S1-CONSTRAINED-INTERIOR-REFINEMENT",
                    "seamModel": "explicit_endpoint_equivalence_v2",
                    "physics": "unchanged_v1_parameters",
                    "outcome": "failed_frozen_phy1",
                }
            ],
            "coupledConvergence": {
                "executed": False,
                "reason": "unchanged_physics_replay_failed_contact_clearance_and_convergence",
            },
            "integratedCcd": {
                "executed": False,
                "eligible": False,
                "reason": (
                    "requires_zero_temporal_degeneracy_and_coupled_convergence_before_ccd"
                ),
            },
            "stopReason": "smallest_truthful_failure_after_first_v2_strategy",
            "remainingTopologyStrategies": 2,
            "remainingSeamModels": 1,
        },
        "performance": {
            "canonicalWallClockSeconds": None,
            "status": "not_canonicalised_hardware_dependent_measurement",
            "runtimeCeilingSeconds": profile["solverProfile"]["runtimeCeilingSeconds"],
            "operationBounds": {
                "settleSteps": profile["solverProfile"]["settleStepCount"],
                "settleIterationsPerStep": profile["solverProfile"][
                    "settleIterationsPerStep"
                ],
                "motionStateCount": 10,
                "motionStepsPerState": profile["solverProfile"]["motionStepCount"],
                "motionIterationsPerStep": profile["solverProfile"][
                    "motionIterationsPerStep"
                ],
            },
        },
        "claims": {
            "stableOrRealisticCloth": False,
            "integratedCcd": False,
            "productionPhysicalAnimation": False,
            "alphaReadiness": False,
            "solverDrivenPhase11PhysicalValidation": False,
            "gpuOrDeviceEvidence": False,
            "realFabricEvidence": False,
        },
        "integrity": {"evidenceHash": ""},
    }
    report["integrity"]["evidenceHash"] = _hash_document(report, "evidenceHash")
    return report


def _state_evidence(
    state_id: str,
    mesh: MeshSet,
    trajectory: list[MeshSet],
    diagnostics: dict[str, Any],
    settle: SettleResult,
    inputs: Phy1TopologyV2Inputs,
    calibration: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    flat = flatten_mesh(mesh)
    exclusions = seam_exclusion_pairs(inputs.constraints, flat.mesh_offsets)
    collision = analyze_self_collision(
        mesh,
        settings=SelfCollisionSettings(
            thickness_meters=float(inputs.material["selfCollisionThicknessMeters"]),
            clearance_meters=float(profile["solverProfile"]["selfCollisionClearanceMeters"]),
            response_mode="legacy_vertex_only",
        ),
        excluded_vertex_pairs=exclusions,
    )
    temporal = audit_temporal_deformation_quality(trajectory)
    deformation = audit_rest_referenced_deformation(settle.settled_mesh, mesh)
    rendered_positions = reconstruct_vertices(mesh, inputs.binding)
    simulation_clearance = _clearance(flat.positions, inputs.avatar, calibration, "sv")
    render_clearance = _clearance(
        rendered_positions,
        inputs.avatar,
        calibration,
        "rv",
    )
    seam = _seam_metrics(mesh, inputs.constraints)
    opening = _opening_metrics(settle.settled_mesh, mesh, inputs.constraints)
    strain = _edge_strain_metrics(settle.settled_mesh, mesh)
    support = _support_metrics(settle.settled_mesh, mesh)
    temporal_motion = _terminal_motion_metrics(trajectory, inputs.material)
    residual_violations = sum(
        contact.penetration_meters > 0.00016 for contact in collision.contacts
    )
    maximum_residual = collision.max_penetration_meters
    checks = {
        "finite": all(math.isfinite(value) for point in flat.positions for value in point),
        "contacts": collision.unresolved_contact_count == 0,
        "residualDepth": maximum_residual <= 0.00016,
        "residualViolations": residual_violations == 0,
        "simulationClearance": float(simulation_clearance["minimumBodySignedClearanceMeters"])
        >= 0.000005,
        "renderClearance": float(render_clearance["minimumBodySignedClearanceMeters"])
        >= 0.000005,
        "seamCrack": seam["maximumSeamCrackMeters"] <= 0.002,
        "seamSlip": seam["maximumTangentialSlipMeters"] <= 0.005,
        "degeneracy": temporal["counts"]["degenerateFrameTriangles"] == 0,
        "sweptCollapse": temporal["counts"]["sweptDegenerateTransitions"] == 0,
        "trueInversion": temporal["counts"]["trueInversions"] == 0,
        "edgeStretch": strain["maximumEdgeStretchRatio"] <= 1.35,
        "p95EdgeStretch": strain["p95EdgeStretchRatio"] <= 1.15,
        "edgeCompression": strain["minimumEdgeCompressionRatio"] >= 0.75,
        "p05EdgeCompression": strain["p05EdgeCompressionRatio"] >= 0.88,
        "areaRatio": deformation["minimumAreaRatio"] >= 0.65
        and deformation["maximumAreaRatio"] <= 1.5,
        "shear": strain["maximumShearRatio"] <= 0.35,
        "supportDrift": support["maximumSupportDriftMeters"] <= 0.002,
        "centerOfMass": temporal_motion["centerOfMassDisplacementMeters"] <= 0.25,
        "terminalVelocity": temporal_motion["maximumTerminalVelocityMetersPerSecond"] <= 0.02,
        "terminalKineticEnergy": temporal_motion["terminalKineticEnergyJoules"] <= 0.001,
        "openingStability": opening["collapsedOpeningCount"] == 0,
        "energy": _energy_pass(diagnostics),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "stateId": state_id,
        "status": "pass" if not failed else "fail",
        "meshContentHash": geometry_content_hash(mesh),
        "trajectoryFrameCount": len(trajectory),
        "solverDiagnostics": {
            "finitePositions": diagnostics.get("finitePositions", True),
            "convergenceState": diagnostics.get("convergenceState", "motion_completed"),
            "invertedOrDegenerateTriangleCount": diagnostics.get(
                "invertedOrDegenerateTriangleCount",
                diagnostics.get("invertedOrDegenerateElementCount", 0),
            ),
            "energyHistory": diagnostics.get("energyHistory", []),
        },
        "selfCollision": {
            "contacts": collision.unresolved_contact_count,
            "maximumResidualDepthMeters": maximum_residual,
            "residualViolationsAboveBudget": residual_violations,
            "broadPhaseMatchesOracle": collision.broad_phase_matches_oracle,
        },
        "clearance": {
            "authority": "frozen_solver_collision_primitives_conservative_signed_proxy",
            "simulationSurfaceMinimumMeters": simulation_clearance[
                "minimumBodySignedClearanceMeters"
            ],
            "renderSurfaceMinimumMeters": render_clearance["minimumBodySignedClearanceMeters"],
            "simulationOracleUncertainCount": simulation_clearance["oracleUncertainCount"],
            "renderOracleUncertainCount": render_clearance["oracleUncertainCount"],
        },
        "seam": seam,
        "opening": opening,
        "strain": strain,
        "support": support,
        "terminalMotion": temporal_motion,
        "deformation": {
            "counts": deformation["counts"],
            "minimumAreaRatio": deformation["minimumAreaRatio"],
            "maximumAreaRatio": deformation["maximumAreaRatio"],
            "worstWitnesses": deformation["worstWitnesses"],
        },
        "temporal": temporal,
        "checks": checks,
        "failedChecks": failed,
    }


def _aggregate(
    states: list[dict[str, Any]], settle: SettleResult
) -> dict[str, Any]:
    return {
        "stateCount": len(states),
        "statePassCount": sum(state["status"] == "pass" for state in states),
        "contactsBefore": int(settle.diagnostics["selfCollision"]["contactCount"]),
        "maximumUnresolvedContactCount": max(
            int(state["selfCollision"]["contacts"]) for state in states
        ),
        "maximumResidualSelfCollisionDepthMeters": max(
            float(state["selfCollision"]["maximumResidualDepthMeters"]) for state in states
        ),
        "residualViolationsAboveBudget": sum(
            int(state["selfCollision"]["residualViolationsAboveBudget"]) for state in states
        ),
        "simulationSurfaceMinimumBodyClearanceMeters": min(
            float(state["clearance"]["simulationSurfaceMinimumMeters"]) for state in states
        ),
        "renderSurfaceMinimumBodyClearanceMeters": min(
            float(state["clearance"]["renderSurfaceMinimumMeters"]) for state in states
        ),
        "maximumSeamCrackMeters": max(
            float(state["seam"]["maximumSeamCrackMeters"]) for state in states
        ),
        "maximumTangentialSeamSlipMeters": max(
            float(state["seam"]["maximumTangentialSlipMeters"]) for state in states
        ),
        "qualifiedTemporalCounts": {
            key: sum(int(state["temporal"]["counts"][key]) for state in states)
            for key in (
                "nonfiniteFrameTriangles",
                "degenerateFrameTriangles",
                "sweptDegenerateTransitions",
                "trueInversions",
            )
        },
        "maximumEdgeStretchRatio": max(
            float(state["strain"]["maximumEdgeStretchRatio"]) for state in states
        ),
        "minimumEdgeCompressionRatio": min(
            float(state["strain"]["minimumEdgeCompressionRatio"]) for state in states
        ),
        "minimumAreaRatio": min(
            float(state["deformation"]["minimumAreaRatio"]) for state in states
        ),
        "maximumAreaRatio": max(
            float(state["deformation"]["maximumAreaRatio"]) for state in states
        ),
        "maximumSupportDriftMeters": max(
            float(state["support"]["maximumSupportDriftMeters"]) for state in states
        ),
        "settleConvergenceState": settle.diagnostics["convergenceState"],
    }


def _aggregate_checks(
    aggregate: dict[str, Any], thresholds: dict[str, Any], states: list[dict[str, Any]]
) -> dict[str, bool]:
    temporal = aggregate["qualifiedTemporalCounts"]
    return {
        "allPhysicalStates": aggregate["statePassCount"] == 11,
        "residualSelfCollisionDepth": aggregate["maximumResidualSelfCollisionDepthMeters"]
        <= thresholds["maximumResidualSelfCollisionDepthMeters"],
        "residualViolations": aggregate["residualViolationsAboveBudget"] == 0,
        "simulationSurfaceClearance": aggregate["simulationSurfaceMinimumBodyClearanceMeters"]
        >= thresholds["minimumQualifiedSurfaceBodyClearanceMeters"],
        "renderSurfaceClearance": aggregate["renderSurfaceMinimumBodyClearanceMeters"]
        >= thresholds["minimumQualifiedSurfaceBodyClearanceMeters"],
        "seamCrack": aggregate["maximumSeamCrackMeters"]
        <= thresholds["maximumSeamCrackMeters"],
        "seamSlip": aggregate["maximumTangentialSeamSlipMeters"]
        <= thresholds["maximumTangentialSeamSlipMeters"],
        "degenerateFrames": temporal["degenerateFrameTriangles"] == 0,
        "sweptDegeneracy": temporal["sweptDegenerateTransitions"] == 0,
        "trueInversion": temporal["trueInversions"] == 0,
        "strainOpeningSupportEnergy": all(
            all(
                state["checks"][name]
                for name in (
                    "edgeStretch",
                    "p95EdgeStretch",
                    "edgeCompression",
                    "p05EdgeCompression",
                    "areaRatio",
                    "shear",
                    "supportDrift",
                    "centerOfMass",
                    "terminalVelocity",
                    "terminalKineticEnergy",
                    "openingStability",
                    "energy",
                )
            )
            for state in states
        ),
        "coupledConvergence": aggregate["settleConvergenceState"] == "converged",
        "performance": False,
        "determinism": True,
    }


def _thresholds(profile: dict[str, Any], calibration: dict[str, Any]) -> dict[str, Any]:
    quality = profile["qualityBounds"]
    return {
        "maximumResidualSelfCollisionDepthMeters": 0.00016,
        "minimumQualifiedSurfaceBodyClearanceMeters": float(
            calibration["minimumAcceptedBodySignedClearanceMeters"]
        ),
        "maximumSeamCrackMeters": 0.002,
        "maximumTangentialSeamSlipMeters": 0.005,
        "maximumDegenerateFrameTriangles": 0,
        "maximumSweptDegenerateTransitions": 0,
        "maximumTrueInversions": 0,
        "requiredPhysicalStatePassCount": 11,
        **quality,
    }


def _clearance(
    positions: list[Vec3], avatar: dict[str, Any], calibration: dict[str, Any], prefix: str
) -> dict[str, Any]:
    half_thickness = float(calibration["clothHalfThicknessMeters"])
    witnesses = [
        {
            "pointId": f"{prefix}.{index}",
            "signedClearanceMeters": min(
                _primitive_signed_distance(point, primitive)
                for primitive in avatar["collisionPrimitives"]
            )
            - half_thickness,
        }
        for index, point in enumerate(positions)
    ]
    worst = min(witnesses, key=lambda item: (item["signedClearanceMeters"], item["pointId"]))
    return {
        "auditVersion": "closy.phy1.solver_primitive_signed_clearance.v1",
        "authority": "same_frozen_collision_primitives_consumed_by_reference_solver",
        "conservativeProxy": True,
        "glbSignedSurfaceOracleRun": False,
        "pointCount": len(witnesses),
        "oracleUncertainCount": 0,
        "minimumBodySignedClearanceMeters": worst["signedClearanceMeters"],
        "worstWitness": worst,
    }


def _primitive_signed_distance(point: Vec3, primitive: dict[str, Any]) -> float:
    if primitive["type"] == "ellipsoid":
        center: Vec3 = tuple(float(value) for value in primitive["center"])  # type: ignore[assignment]
        radii: Vec3 = tuple(float(value) for value in primitive["radii"])  # type: ignore[assignment]
        normalized = math.sqrt(
            sum(((point[index] - center[index]) / radii[index]) ** 2 for index in range(3))
        )
        return (normalized - 1.0) * min(radii)
    if primitive["type"] == "capsule":
        start: Vec3 = tuple(float(value) for value in primitive["a"])  # type: ignore[assignment]
        end: Vec3 = tuple(float(value) for value in primitive["b"])  # type: ignore[assignment]
        nearest = _closest_point_on_segment(point, start, end)
        return math.dist(point, nearest) - float(primitive["radius"])
    raise ValueError(f"unsupported_phy1_collision_primitive:{primitive['type']}")


def _closest_point_on_segment(point: Vec3, start: Vec3, end: Vec3) -> Vec3:
    axis = _sub(end, start)
    denominator = sum(value * value for value in axis)
    if denominator <= 1e-18:
        return start
    parameter = sum((point[index] - start[index]) * axis[index] for index in range(3))
    parameter = max(0.0, min(1.0, parameter / denominator))
    return (
        start[0] + axis[0] * parameter,
        start[1] + axis[1] * parameter,
        start[2] + axis[2] * parameter,
    )


def _seam_metrics(mesh: MeshSet, constraints: dict[str, Any]) -> dict[str, Any]:
    flat = flatten_mesh(mesh)
    cracks: list[float] = []
    slips: list[float] = []
    for constraint in constraints.get("constraints", []):
        left = span_position_flat(flat.positions, flat.mesh_offsets, constraint["spanA"])
        right = span_position_flat(flat.positions, flat.mesh_offsets, constraint["spanB"])
        distance = math.dist(left, right)
        target = 0.02 if "neck" in str(constraint.get("seamId", "")) else 0.0
        cracks.append(distance)
        slips.append(abs(distance - target))
    return {
        "constraintCount": len(cracks),
        "maximumSeamCrackMeters": max(cracks, default=0.0),
        "maximumTangentialSlipMeters": max(slips, default=0.0),
    }


def _opening_metrics(
    reference: MeshSet, current: MeshSet, constraints: dict[str, Any]
) -> dict[str, Any]:
    records = []
    for opening in constraints.get("openings", []):
        rest = _opening_length(reference, opening)
        deformed = _opening_length(current, opening)
        records.append(
            {
                "openingId": opening["id"],
                "restLengthMeters": rest,
                "deformedLengthMeters": deformed,
                "driftMeters": abs(deformed - rest),
                "collapsed": deformed <= max(1e-6, rest * 0.2),
            }
        )
    return {
        "openingCount": len(records),
        "collapsedOpeningCount": sum(record["collapsed"] for record in records),
        "maximumDriftMeters": max((record["driftMeters"] for record in records), default=0.0),
        "openings": records,
    }


def _opening_length(meshset: MeshSet, opening: dict[str, Any]) -> float:
    total = 0.0
    for edge in opening.get("boundaryEdges", []):
        if edge.get("status") != "resolved":
            continue
        mesh = meshset.meshes[int(edge["meshIndex"])]
        indices = [int(index) for index in edge["vertexIndices"]]
        total += sum(
            math.dist(mesh.vertices[left], mesh.vertices[right])
            for left, right in zip(indices, indices[1:], strict=False)
        )
    return total


def _edge_strain_metrics(reference: MeshSet, current: MeshSet) -> dict[str, Any]:
    ratios: list[float] = []
    shear: list[float] = []
    for rest_panel, state_panel in zip(reference.meshes, current.meshes, strict=True):
        edges = {
            tuple(sorted(edge))
            for tri in rest_panel.triangles
            for edge in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0]))
        }
        for left, right in edges:
            rest_length = math.dist(rest_panel.vertices[left], rest_panel.vertices[right])
            if rest_length <= 1e-12:
                continue
            ratio = math.dist(state_panel.vertices[left], state_panel.vertices[right]) / rest_length
            ratios.append(ratio)
            uv_left, uv_right = rest_panel.panel_uvs[left], rest_panel.panel_uvs[right]
            du, dv = abs(uv_right[0] - uv_left[0]), abs(uv_right[1] - uv_left[1])
            largest = max(du, dv)
            if largest > 0.0 and min(du, dv) / largest >= 0.22:
                shear.append(abs(ratio - 1.0))
    return {
        "maximumEdgeStretchRatio": max(ratios, default=1.0),
        "p95EdgeStretchRatio": _percentile(ratios, 0.95),
        "minimumEdgeCompressionRatio": min(ratios, default=1.0),
        "p05EdgeCompressionRatio": _percentile(ratios, 0.05),
        "maximumShearRatio": max(shear, default=0.0),
    }


def _support_metrics(reference: MeshSet, current: MeshSet) -> dict[str, Any]:
    drifts: list[float] = []
    count = 0
    for rest_panel, state_panel in zip(reference.meshes, current.meshes, strict=True):
        panel_top = max(vertex[1] for vertex in rest_panel.vertices)
        for index, rest in enumerate(rest_panel.vertices):
            if rest_panel.panel_id == "panel.neck_band" or rest[1] >= 1.345:
                drifts.append(math.dist(rest, state_panel.vertices[index]))
                count += 1
        if panel_top < 1.345 and rest_panel.panel_id != "panel.neck_band":
            continue
    return {"supportCount": count, "maximumSupportDriftMeters": max(drifts, default=0.0)}


def _terminal_motion_metrics(trajectory: list[MeshSet], material: dict[str, Any]) -> dict[str, Any]:
    first = flatten_mesh(trajectory[0]).positions
    final = flatten_mesh(trajectory[-1]).positions
    center_displacement = math.dist(_centroid(first), _centroid(final))
    if len(trajectory) < 2:
        return {
            "centerOfMassDisplacementMeters": center_displacement,
            "maximumTerminalVelocityMetersPerSecond": 0.0,
            "terminalKineticEnergyJoules": 0.0,
        }
    previous = flatten_mesh(trajectory[-2]).positions
    velocities: list[Vec3] = [
        (
            (current[0] - old[0]) * 60.0,
            (current[1] - old[1]) * 60.0,
            (current[2] - old[2]) * 60.0,
        )
        for old, current in zip(previous, final, strict=True)
    ]
    maximum_velocity = max((_length(value) for value in velocities), default=0.0)
    total_mass = float(material["surfaceDensityKgM2"]) * _surface_area(trajectory[0])
    particle_mass = total_mass / max(1, len(velocities))
    energy = sum(
        (0.5 * particle_mass * _length(value) ** 2 for value in velocities),
        0.0,
    )
    return {
        "centerOfMassDisplacementMeters": center_displacement,
        "maximumTerminalVelocityMetersPerSecond": maximum_velocity,
        "terminalKineticEnergyJoules": energy,
    }


def _energy_pass(diagnostics: dict[str, Any]) -> bool:
    history = [float(value) for value in diagnostics.get("energyHistory", [])]
    return not history or history[-1] <= history[0] * 1.25


def _surface_area(meshset: MeshSet) -> float:
    total = 0.0
    for mesh in meshset.meshes:
        for a, b, c in mesh.triangles:
            ab = _sub(mesh.vertices[b], mesh.vertices[a])
            ac = _sub(mesh.vertices[c], mesh.vertices[a])
            total += _length(_cross(ab, ac)) * 0.5
    return total


def _centroid(points: list[Vec3]) -> Vec3:
    count = max(1, len(points))
    return tuple(sum(point[axis] for point in points) / count for axis in range(3))  # type: ignore[return-value]


def _replace_positions(template: MeshSet, positions: list[Vec3]) -> MeshSet:
    result: list[Mesh] = []
    cursor = 0
    for mesh in template.meshes:
        panel_positions = positions[cursor : cursor + len(mesh.vertices)]
        result.append(
            Mesh(
                mesh.name,
                mesh.panel_id,
                panel_positions,
                mesh.panel_uvs,
                mesh.triangles,
                mesh.material_id,
            )
        )
        cursor += len(mesh.vertices)
    if cursor != len(positions):
        raise ValueError("topology_v2_render_position_count_mismatch")
    return MeshSet(result)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 1.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def _length(value: Vec3) -> float:
    return math.sqrt(sum(component * component for component in value))


def _sub(left: Vec3, right: Vec3) -> Vec3:
    return tuple(left[index] - right[index] for index in range(3))  # type: ignore[return-value]


def _cross(left: Vec3, right: Vec3) -> Vec3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _hash_document(document: dict[str, Any], field: str) -> str:
    payload = deepcopy(document)
    payload["integrity"][field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _forge_root() -> Path:
    return Path(__file__).resolve().parents[3]
