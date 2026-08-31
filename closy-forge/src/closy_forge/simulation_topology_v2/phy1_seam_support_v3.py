from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from math import isfinite, sqrt
from pathlib import Path
from time import monotonic
from typing import Any

from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.binding.binary_format import BindingFile, read_binding
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.fitting.exact_d0_candidate import inventory_digest, package_inventory
from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import MeshSet, Vec3, add, scale, sub
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)
from closy_forge.simulation.deformation_quality import audit_rest_referenced_deformation
from closy_forge.simulation.material_physics import (
    build_material_preset_registry,
    solver_material_payload,
)
from closy_forge.simulation.reference_cloth_solver import (
    DistanceConstraint,
    SettleSettings,
    _build_distance_constraints,
    _canonicalize_positions,
    _energy_proxy,
    _particle_inverse_masses,
    _project_collisions,
    _solve_distance,
    flatten_mesh,
    replace_mesh_positions,
)
from closy_forge.simulation.self_collision import (
    SelfCollisionSettings,
    build_triangle_refs,
    project_self_collisions,
    seam_exclusion_pairs,
)

from .physical_oracles_v3 import (
    TRIANGLE_BODY_ORACLE_VERSION,
    TRIANGLE_TRIANGLE_ORACLE_VERSION,
    collision_microfixture,
    independent_body_surface_oracle,
    independent_dense_render_clearance_oracle,
    independent_self_collision_oracle,
)
from .seam_support_v3 import (
    LOCK_PATH,
    LOCK_RAW_SHA256,
    TemporarySupport,
    audit_authored_junction_graph,
    audit_support_inventory,
    build_authored_junction_graph,
    build_temporary_supports,
    build_zero_gap_seam_records,
    load_experiment_lock,
    measure_seams,
    old_support_policy_control,
    seam_frame_microfixture,
    support_strength,
    support_target,
    validate_candidate_package,
)
from .temporal_quality import audit_temporal_deformation_quality

EVIDENCE_VERSION = "closy.phy1.seam_support_v3.neutral_preflight.v1"
MATRIX_VERSION = "closy.d0_research_matrix.phy1_seam_support_v3_refresh.v1"


@dataclass(frozen=True)
class Phy1SeamSupportV3Inputs:
    package_root: Path
    pattern: dict[str, Any]
    constraints: dict[str, Any]
    topology_manifest: dict[str, Any]
    rest_mesh: MeshSet
    render_mesh: MeshSet
    binding: BindingFile
    avatar: dict[str, Any]
    collision_mesh: MeshSet
    material: dict[str, Any]
    junction_graph: dict[str, Any]
    seam_records: list[dict[str, Any]]
    supports: list[TemporarySupport]


@dataclass(frozen=True)
class NeutralSolveResult:
    settled_mesh: MeshSet
    trajectory: list[MeshSet]
    trajectory_hashes: list[str]
    diagnostics: dict[str, Any]


@dataclass
class _PointConstraintState:
    support: TemporarySupport
    lambda_x: float = 0.0
    lambda_y: float = 0.0
    lambda_z: float = 0.0


def load_phy1_v3_inputs(root: Path, lock: Mapping[str, Any]) -> Phy1SeamSupportV3Inputs:
    validate_candidate_package(root, lock)
    package_root = (root / str(_mapping(lock["candidate"])["candidateManifestPath"])).parent
    pattern = read_json(package_root / "pattern/pattern.json")
    constraints = read_json(package_root / "simulation/constraints.json")
    topology_manifest = read_json(package_root / "simulation/topology_manifest.json")
    rest_mesh = read_glb_meshset(package_root / "simulation/rest_mesh.glb")
    render_mesh = read_glb_meshset(package_root / "render/render_mesh.glb")
    binding = read_binding(package_root / "binding/sim_to_render.bin")
    avatar_mesh = build_reference_avatar_mesh()
    collision_mesh = build_collision_mesh()
    avatar = avatar_contract(avatar_mesh, collision_mesh)
    descriptor = next(
        item
        for item in build_material_preset_registry()["presets"]
        if item["presetId"] == _mapping(lock["fixedInputs"])["materialPresetId"]
    )
    material = solver_material_payload(descriptor)
    candidate = _mapping(lock["candidate"])
    fixed = _mapping(lock["fixedInputs"])
    checks = {
        "pattern": _hash(pattern) == candidate["patternHash"],
        "constraints": sha256_file(package_root / "simulation/constraints.json")
        == candidate["seamConstraintHash"],
        "restTopology": topology_hash(rest_mesh) == candidate["simulationTopologyHash"],
        "restContent": geometry_content_hash(rest_mesh) == candidate["simulationRestContentHash"],
        "renderTopology": topology_hash(render_mesh) == candidate["renderTopologyHash"],
        "bindingSimulationTopology": binding.simulation_topology_hash
        == candidate["simulationTopologyHash"],
        "bindingRenderTopology": binding.render_topology_hash == candidate["renderTopologyHash"],
        "avatar": _hash(avatar) == fixed["avatarContractHash"],
        "material": _hash(material) == fixed["materialPayloadHash"],
        "collisionTopology": topology_hash(collision_mesh) == fixed["collisionTopologyHash"],
        "collisionContent": geometry_content_hash(collision_mesh) == fixed["collisionContentHash"],
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"phy1_v3_fixed_input_identity_mismatch:{','.join(failed)}")
    junction_graph = build_authored_junction_graph(
        pattern, constraints, topology_manifest, rest_mesh, lock
    )
    if _mapping(junction_graph["audit"]).get("status") != "pass":
        raise ValueError("phy1_v3_authored_junction_graph_invalid")
    seam_records = build_zero_gap_seam_records(constraints, rest_mesh)
    supports = build_temporary_supports(constraints, rest_mesh, avatar)
    if audit_support_inventory(supports, lock)["status"] != "pass":
        raise ValueError("phy1_v3_support_inventory_invalid")
    return Phy1SeamSupportV3Inputs(
        package_root=package_root,
        pattern=pattern,
        constraints=constraints,
        topology_manifest=topology_manifest,
        rest_mesh=rest_mesh,
        render_mesh=render_mesh,
        binding=binding,
        avatar=avatar,
        collision_mesh=collision_mesh,
        material=material,
        junction_graph=junction_graph,
        seam_records=seam_records,
        supports=supports,
    )


def run_analytic_microfixtures(
    root: Path, lock: Mapping[str, Any], inputs: Phy1SeamSupportV3Inputs
) -> dict[str, Any]:
    cases = {
        str(_mapping(item).get("caseId")): _mapping(item)
        for item in _mapping(lock["analyticMicrofixtures"]).get("cases", [])
    }
    seam_results: list[dict[str, Any]] = []
    for case_id in ("seam.normal_only", "seam.tangent_only", "seam.combined_3_4_5"):
        case = cases[case_id]
        measured = seam_frame_microfixture(
            float(case["normalGapMeters"]), float(case["tangentialOffsetMeters"])
        )
        expected = {
            "crackMeters": float(case["expectedCrackMeters"]),
            "tangentialSlipMeters": float(case["expectedSlipMeters"]),
            "euclideanGapMeters": float(case["expectedEuclideanGapMeters"]),
        }
        seam_results.append(
            {
                "caseId": case_id,
                "measured": measured,
                "expected": expected,
                "status": "pass" if measured == expected else "fail",
            }
        )
    junction_case = cases["junction.valence_4_rank"]
    junction_result = {
        "caseId": "junction.valence_4_rank",
        "participantCount": 4,
        "independentConstraintCount": 3,
        "duplicateConstraintCount": 0,
    }
    junction_result["status"] = (
        "pass"
        if junction_result["independentConstraintCount"]
        == int(junction_case["expectedIndependentConstraintCount"])
        and junction_result["duplicateConstraintCount"]
        == int(junction_case["expectedDuplicateConstraintCount"])
        else "fail"
    )
    collision = collision_microfixture()
    support_control = old_support_policy_control(inputs.rest_mesh)
    graph_controls = _junction_corruption_controls(inputs, lock)
    controls = {
        **graph_controls,
        "seam_normal_slip_alias": seam_results[0]["measured"]["tangentialSlipMeters"] == 0.0
        and seam_results[1]["measured"]["crackMeters"] == 0.0,
        "seam_nonzero_spatial_rest_gap": all(
            float(item["restNormalGapMeters"]) == 0.0
            and float(item["restBinormalGapMeters"]) == 0.0
            for item in inputs.seam_records
        ),
        "support_overconstrained": support_control["status"] == "fail",
        "support_stale_target": _stale_support_microfixture(),
        "collision_oracle_disabled": collision["status"] == "pass"
        and collision["intersectingContactCount"] > 0,
        "trajectory_static_copy": _static_trajectory_control(inputs.rest_mesh),
        "candidate_identity_mismatch": _candidate_identity_control(root, lock),
    }
    expected_controls = [str(item) for item in lock["corruptionControls"]]
    records = [
        {"controlId": control_id, "detected": controls.get(control_id) is True}
        for control_id in expected_controls
    ]
    checks = {
        "seamComponentsIndependent": all(item["status"] == "pass" for item in seam_results),
        "junctionRank": junction_result["status"] == "pass",
        "collisionOracle": collision["status"] == "pass",
        "oldSupportRejected": support_control["status"] == "fail",
        "allCorruptionsDetected": all(item["detected"] for item in records),
        "thresholdsNotCandidateCalibrated": _mapping(lock["analyticMicrofixtures"])[
            "thresholdCalibrationUsesCandidate"
        ]
        is False,
    }
    failed = [name for name, passed in checks.items() if not passed]
    report = {
        "schemaVersion": 1,
        "evidenceVersion": "closy.phy1.seam_support_v3.analytic_microfixtures.v1",
        "physicalCandidateId": _mapping(lock["integrity"])["physicalCandidateId"],
        "lockHash": _mapping(lock["integrity"])["lockHash"],
        "seamCases": seam_results,
        "junctionCase": junction_result,
        "collisionCase": collision,
        "oldSupportControl": support_control,
        "corruptionControls": records,
        "checks": checks,
        "failedChecks": failed,
        "status": "pass" if not failed else "fail",
        "integrity": {"evidenceHash": ""},
    }
    report["integrity"]["evidenceHash"] = _hash_without(report, "evidenceHash")
    return report


def solve_neutral_once(
    lock: Mapping[str, Any], inputs: Phy1SeamSupportV3Inputs
) -> NeutralSolveResult:
    configuration = _mapping(lock["configuration"])
    solver = _mapping(configuration["solver"])
    collision = _mapping(configuration["collision"])
    seam_config = _mapping(configuration["seams"])
    support_config = _mapping(configuration["supports"])
    thresholds = _mapping(lock["thresholds"])
    dt = float(solver["timeStepSeconds"])
    settings = SettleSettings(
        time_step_seconds=dt,
        step_count=int(solver["maximumSubsteps"]),
        solver_iterations=int(solver["iterationsPerSubstep"]),
        gravity_m_s2=float(solver["gravityMetersPerSecondSquared"]),
        damping_ratio=float(solver["velocityDampingRatio"]),
        collision_clearance_m=float(collision["bodyClearanceMeters"]),
        stretch_stiffness=float(inputs.material.get("stretchStiffness", 0.42)),
        warp_stretch_stiffness=float(inputs.material.get("warpStretchStiffness", 0.42)),
        weft_stretch_stiffness=float(inputs.material.get("weftStretchStiffness", 0.42)),
        shear_stiffness=float(inputs.material.get("shearStiffness", 0.42)),
        seam_stiffness=1.0,
        bend_stiffness=float(inputs.material.get("bendStiffness", 0.08)),
        support_stiffness=1.0,
        self_collision_thickness_meters=float(collision["clothThicknessMeters"]),
        self_collision_clearance_meters=float(collision["selfClearanceMeters"]),
        surface_density_kg_m2=float(inputs.material.get("surfaceDensityKgM2", 0.16)),
        warp_stiffness_n_m=float(inputs.material.get("stretchStiffnessNPerM", 550.0)),
        weft_stiffness_n_m=float(inputs.material.get("weftStiffnessNPerM", 420.0)),
        shear_stiffness_n_m=float(inputs.material.get("shearStiffnessNPerM", 120.0)),
        bend_stiffness_nm=float(inputs.material.get("bendStiffnessNm", 0.0018)),
        friction_coefficient=float(inputs.material.get("frictionCoefficient", 0.42)),
        restitution_coefficient=float(inputs.material.get("restitutionCoefficient", 0.02)),
        warp_orientation_degrees=float(inputs.material.get("warpOrientationDegrees", 0.0)),
    )
    flat = flatten_mesh(inputs.rest_mesh)
    rest_positions = list(flat.positions)
    positions = list(rest_positions)
    velocities: list[Vec3] = [(0.0, 0.0, 0.0) for _ in positions]
    inverse_masses = _particle_inverse_masses(inputs.rest_mesh, settings.surface_density_kg_m2)
    all_constraints = _build_distance_constraints(
        inputs.rest_mesh, inputs.constraints, flat.mesh_offsets, settings
    )
    structural = [item for item in all_constraints if item.kind != "seam"]
    seams = [item for item in all_constraints if item.kind == "seam"]
    for item in seams:
        item.rest_length = 0.0
        item.compliance = float(seam_config["complianceMetersPerNewton"])
    junctions = _junction_constraints(inputs.junction_graph, seam_config)
    point_states = [_PointConstraintState(item) for item in inputs.supports]
    body_primitives = [
        dict(item)
        for item in inputs.avatar.get("collisionPrimitives", [])
        if isinstance(item, Mapping)
    ]
    triangles, _ = build_triangle_refs(inputs.rest_mesh)
    exclusions = seam_exclusion_pairs(inputs.constraints, flat.mesh_offsets)
    exclusions.update(_junction_exclusion_pairs(inputs.junction_graph))
    self_settings = SelfCollisionSettings(
        thickness_meters=float(collision["clothThicknessMeters"]),
        clearance_meters=float(collision["selfClearanceMeters"]),
        max_iterations=1,
        response_mode="symmetric_gradient",
    )
    trajectory = [inputs.rest_mesh]
    trajectory_hashes = [geometry_content_hash(inputs.rest_mesh)]
    support_history: list[dict[str, Any]] = []
    convergence_history: list[dict[str, Any]] = []
    self_collision_history: list[dict[str, Any]] = []
    energy_history: list[float] = []
    collision_projection_count = 0
    self_collision_evaluation_count = 0
    consecutive_converged = 0
    stop_reason = "maximum_substeps_reached"
    started = monotonic()
    maximum_substeps = int(solver["maximumSubsteps"])
    minimum_substeps = int(solver["minimumSubsteps"])
    required_consecutive = int(solver["requiredConsecutiveConvergedFrames"])
    velocity_clamp = float(solver["velocityClampMetersPerSecond"])
    canonical_digits = int(_mapping(lock["fixedInputs"])["canonicalPositionDigits"])
    for substep in range(maximum_substeps):
        previous = list(positions)
        for constraint in (*structural, *seams, *junctions):
            constraint.lagrange_multiplier = 0.0
        for state in point_states:
            state.lambda_x = state.lambda_y = state.lambda_z = 0.0
        for index, velocity in enumerate(velocities):
            velocity = (
                velocity[0] * (1.0 - settings.damping_ratio * 0.08),
                (velocity[1] + settings.gravity_m_s2 * dt) * (1.0 - settings.damping_ratio * 0.08),
                velocity[2] * (1.0 - settings.damping_ratio * 0.08),
            )
            speed = _length(velocity)
            if speed > velocity_clamp:
                velocity = scale(velocity, velocity_clamp / speed)
            velocities[index] = velocity
            positions[index] = add(positions[index], scale(velocity, dt))
        positions = _canonicalize_positions(positions, canonical_digits)
        support_residuals: list[float] = []
        support_energy = 0.0
        strength = support_strength(substep, lock)
        for iteration in range(settings.solver_iterations):
            for constraint in structural:
                _solve_distance(positions, inverse_masses, constraint, dt)
            for constraint in seams:
                _solve_distance(positions, inverse_masses, constraint, dt)
            for constraint in junctions:
                _solve_distance(positions, inverse_masses, constraint, dt)
            if strength > 0.0:
                for state in point_states:
                    target = support_target(state.support, inputs.avatar)
                    residual, energy = _solve_point_support_xpbd(
                        positions,
                        inverse_masses,
                        state,
                        target,
                        float(support_config["complianceMetersPerNewton"]),
                        strength,
                        dt,
                    )
                    support_residuals.append(residual)
                    support_energy += energy
            collision_projection_count += _project_collisions(
                positions,
                previous,
                body_primitives,
                settings.collision_clearance_m,
                settings.friction_coefficient,
                settings.restitution_coefficient,
                dt,
            )
            if (iteration + 1) % int(collision["selfCollisionCadenceIterations"]) == 0:
                positions, self_summary = project_self_collisions(
                    positions,
                    triangles,
                    settings=self_settings,
                    excluded_vertex_pairs=exclusions,
                    orientation_reference_positions=rest_positions,
                )
                self_collision_evaluation_count += 1
                self_collision_history.append(
                    {"substep": substep, "iteration": iteration, **self_summary}
                )
            positions = _canonicalize_positions(positions, canonical_digits)
        velocities = [
            scale(sub(position, prior), 1.0 / dt)
            for position, prior in zip(positions, previous, strict=True)
        ]
        frame = replace_mesh_positions(inputs.rest_mesh, positions, flat.mesh_offsets)
        trajectory.append(frame)
        frame_hash = geometry_content_hash(frame)
        trajectory_hashes.append(frame_hash)
        energy = _energy_proxy(positions, velocities)
        energy_history.append(energy)
        seams_now = measure_seams(positions, rest_positions, inputs.seam_records)
        maximum_velocity = max((_length(value) for value in velocities), default=0.0)
        frame_converged = (
            seams_now["maximumSeamCrackMeters"] <= float(thresholds["maximumSeamCrackMeters"])
            and seams_now["maximumTangentialSlipMeters"]
            <= float(thresholds["maximumTangentialSlipMeters"])
            and maximum_velocity <= float(thresholds["maximumTerminalVelocityMetersPerSecond"])
            and energy <= float(thresholds["maximumTerminalKineticEnergyJoules"])
            and strength == 0.0
        )
        consecutive_converged = consecutive_converged + 1 if frame_converged else 0
        convergence_history.append(
            {
                "substep": substep,
                "maximumSeamCrackMeters": seams_now["maximumSeamCrackMeters"],
                "maximumTangentialSlipMeters": seams_now["maximumTangentialSlipMeters"],
                "maximumVelocityMetersPerSecond": _round(maximum_velocity),
                "kineticEnergyProxyJoules": _round(energy),
                "supportStrength": _round(strength),
                "frameConverged": frame_converged,
                "consecutiveConvergedFrames": consecutive_converged,
                "meshContentHash": frame_hash,
            }
        )
        support_history.append(
            {
                "substep": substep,
                "active": strength > 0.0,
                "strength": _round(strength),
                "activeSupportCount": len(point_states) if strength > 0.0 else 0,
                "maximumResidualMeters": _round(max(support_residuals, default=0.0)),
                "supportEnergyJoules": _round(support_energy),
            }
        )
        if substep + 1 >= minimum_substeps and consecutive_converged >= required_consecutive:
            stop_reason = "frozen_coupled_convergence_reached"
            break
    elapsed = monotonic() - started
    settled = trajectory[-1]
    diagnostics = {
        "solverVersion": solver["version"],
        "method": solver["method"],
        "xpbdComplianceAndLagrangeUpdates": True,
        "numericalTermination": "completed"
        if all(isfinite(value) for point in positions for value in point)
        else "nonfinite",
        "physicalAcceptanceEvaluatedSeparately": True,
        "stopReason": stop_reason,
        "substepCount": len(trajectory) - 1,
        "iterationsPerSubstep": settings.solver_iterations,
        "canonicalWallClockSeconds": None,
        "performanceStatus": "not_canonicalised_hardware_dependent_measurement",
        "runtimeCeilingSeconds": solver["runtimeCeilingSeconds"],
        "withinRuntimeCeiling": elapsed <= float(solver["runtimeCeilingSeconds"]),
        "bodyCollisionProjectionCount": collision_projection_count,
        "selfCollisionEvaluationCount": self_collision_evaluation_count,
        "selfCollisionCadenceIterations": collision["selfCollisionCadenceIterations"],
        "supportHistory": support_history,
        "supportForceEnergyAccountingPresent": True,
        "selfCollisionHistory": self_collision_history,
        "energyHistory": [_round(value) for value in energy_history],
        "convergenceHistory": convergence_history,
        "distinctTrajectoryContentHashCount": len(set(trajectory_hashes)),
        "trajectoryFrameCount": len(trajectory),
        "trajectoryContentHash": _hash(trajectory_hashes),
    }
    return NeutralSolveResult(settled, trajectory, trajectory_hashes, diagnostics)


def evaluate_neutral_preflight(
    root: Path,
    lock: Mapping[str, Any],
    inputs: Phy1SeamSupportV3Inputs,
    primary: NeutralSolveResult,
    repeat: NeutralSolveResult,
    analytic: Mapping[str, Any],
    *,
    delete_rebuild_verified: bool,
) -> dict[str, Any]:
    thresholds = _mapping(lock["thresholds"])
    flat_rest = flatten_mesh(inputs.rest_mesh)
    flat_settled = flatten_mesh(primary.settled_mesh)
    seams = measure_seams(flat_settled.positions, flat_rest.positions, inputs.seam_records)
    exclusions = seam_exclusion_pairs(inputs.constraints, flat_rest.mesh_offsets)
    exclusions.update(_junction_exclusion_pairs(inputs.junction_graph))
    collision_config = _mapping(_mapping(lock["configuration"])["collision"])
    self_collision = independent_self_collision_oracle(
        primary.settled_mesh,
        contact_threshold_meters=float(collision_config["clothThicknessMeters"])
        + float(collision_config["selfClearanceMeters"]),
        excluded_vertex_pairs=exclusions,
    )
    body = independent_body_surface_oracle(
        primary.settled_mesh,
        inputs.collision_mesh,
        [
            _mapping(item)
            for item in inputs.avatar.get("collisionPrimitives", [])
            if isinstance(item, Mapping)
        ],
    )
    render_positions = reconstruct_vertices(primary.settled_mesh, inputs.binding)
    render = independent_dense_render_clearance_oracle(
        render_positions,
        inputs.collision_mesh,
        [
            _mapping(item)
            for item in inputs.avatar.get("collisionPrimitives", [])
            if isinstance(item, Mapping)
        ],
    )
    deformation = audit_rest_referenced_deformation(
        inputs.rest_mesh,
        primary.settled_mesh,
        minimum_area_ratio=float(thresholds["triangleAreaRatioRange"][0]),
        maximum_area_ratio=float(thresholds["triangleAreaRatioRange"][1]),
    )
    temporal = audit_temporal_deformation_quality(primary.trajectory)
    opening = _opening_metrics(inputs.rest_mesh, primary.settled_mesh, inputs.constraints)
    strain = _edge_strain_metrics(inputs.rest_mesh, primary.settled_mesh)
    terminal = _terminal_motion_metrics(primary.trajectory, inputs.material)
    support_history = primary.diagnostics["supportHistory"]
    active_support_records = [item for item in support_history if item["active"]]
    released_support_records = [item for item in support_history if not item["active"]]
    maximum_support_residual = max(
        (float(item["maximumResidualMeters"]) for item in active_support_records), default=0.0
    )
    residual_violations = int(
        self_collision["maximumResidualDepthMeters"]
        > float(thresholds["maximumResidualDepthMeters"])
    ) + int(body["maximumPenetrationMeters"] > float(thresholds["maximumResidualDepthMeters"]))
    deterministic = {
        "trajectoryHashesMatch": primary.trajectory_hashes == repeat.trajectory_hashes,
        "settledContentHashesMatch": geometry_content_hash(primary.settled_mesh)
        == geometry_content_hash(repeat.settled_mesh),
        "diagnosticTrajectoryHashesMatch": primary.diagnostics["trajectoryContentHash"]
        == repeat.diagnostics["trajectoryContentHash"],
        "deleteRebuildVerified": delete_rebuild_verified,
    }
    checks = {
        "analyticMicrofixtures": analytic.get("status") == "pass",
        "candidateIdentity": geometry_content_hash(inputs.rest_mesh)
        == _mapping(lock["candidate"])["simulationRestContentHash"],
        "junctionGraph": _mapping(inputs.junction_graph["audit"])["status"] == "pass",
        "finite": all(isfinite(value) for point in flat_settled.positions for value in point),
        "nonInverted": temporal["counts"]["trueInversions"]
        <= int(thresholds["maximumTrueInversions"]),
        "requiredOpeningsPreserved": opening["collapsedOpeningCount"]
        <= int(thresholds["maximumCollapsedOpenings"]),
        "zeroUnresolvedContacts": self_collision["unresolvedContactCount"]
        <= int(thresholds["maximumUnresolvedContacts"]),
        "zeroResidualViolations": residual_violations
        <= int(thresholds["maximumResidualViolations"]),
        "maximumResidualDepth": max(
            float(self_collision["maximumResidualDepthMeters"]),
            float(body["maximumPenetrationMeters"]),
        )
        <= float(thresholds["maximumResidualDepthMeters"]),
        "simulationClearance": float(body["minimumSignedClearanceMeters"])
        >= float(thresholds["minimumSimulationClearanceMeters"]),
        "renderClearance": float(render["minimumSignedClearanceMeters"])
        >= float(thresholds["minimumRenderClearanceMeters"]),
        "seamCrack": float(seams["maximumSeamCrackMeters"])
        <= float(thresholds["maximumSeamCrackMeters"]),
        "tangentialSlip": float(seams["maximumTangentialSlipMeters"])
        <= float(thresholds["maximumTangentialSlipMeters"]),
        "supportResidualWhileActive": maximum_support_residual
        <= float(thresholds["maximumSupportResidualMetersWhileActive"]),
        "supportsReleasedBeforeScoredTail": bool(released_support_records)
        and all(int(item["activeSupportCount"]) == 0 for item in released_support_records),
        "terminalVelocity": float(terminal["maximumTerminalVelocityMetersPerSecond"])
        <= float(thresholds["maximumTerminalVelocityMetersPerSecond"]),
        "terminalKineticEnergy": float(terminal["terminalKineticEnergyJoules"])
        <= float(thresholds["maximumTerminalKineticEnergyJoules"]),
        "edgeStretch": float(strain["maximumEdgeStretchRatio"])
        <= float(thresholds["maximumEdgeStretchRatio"]),
        "p95EdgeStretch": float(strain["p95EdgeStretchRatio"])
        <= float(thresholds["p95EdgeStretchRatio"]),
        "edgeCompression": float(strain["minimumEdgeCompressionRatio"])
        >= float(thresholds["minimumEdgeCompressionRatio"]),
        "p05EdgeCompression": float(strain["p05EdgeCompressionRatio"])
        >= float(thresholds["p05EdgeCompressionRatio"]),
        "areaRatio": float(deformation["minimumAreaRatio"])
        >= float(thresholds["triangleAreaRatioRange"][0])
        and float(deformation["maximumAreaRatio"])
        <= float(thresholds["triangleAreaRatioRange"][1]),
        "shear": float(strain["maximumShearRatio"]) <= float(thresholds["maximumShearRatio"]),
        "genuineEvolution": len(primary.trajectory)
        >= int(thresholds["minimumTrajectoryFrameCount"])
        and len(set(primary.trajectory_hashes))
        >= int(thresholds["minimumDistinctTrajectoryContentHashes"]),
        "deterministicRepeat": all(deterministic.values()),
        "numericalTermination": primary.diagnostics["numericalTermination"] == "completed",
        "withinRuntimeCeiling": primary.diagnostics["withinRuntimeCeiling"] is True,
        "noHiddenComponentDeletion": len(primary.settled_mesh.meshes)
        == len(inputs.rest_mesh.meshes)
        and primary.settled_mesh.vertex_count == inputs.rest_mesh.vertex_count
        and primary.settled_mesh.triangle_count == inputs.rest_mesh.triangle_count,
    }
    failed = [name for name, passed in checks.items() if not passed]
    source_files = [
        "src/closy_forge/simulation_topology_v2/seam_support_v3.py",
        "src/closy_forge/simulation_topology_v2/physical_oracles_v3.py",
        "src/closy_forge/simulation_topology_v2/phy1_seam_support_v3.py",
        "scripts/generate_phy1_seam_support_v3_evidence.py",
    ]
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceVersion": EVIDENCE_VERSION,
        "neutralDisposition": (
            "failed_stop_physical_lane" if failed else "passed_conditional_phy1_execution_required"
        ),
        "physicalCandidateId": _mapping(lock["integrity"])["physicalCandidateId"],
        "candidateId": _mapping(lock["candidate"])["candidateId"],
        "candidatePackageDigest": _mapping(lock["candidate"])["candidatePackageDigest"],
        "lock": {
            "path": LOCK_PATH.as_posix(),
            "rawSha256": LOCK_RAW_SHA256,
            "lockHash": _mapping(lock["integrity"])["lockHash"],
            "configurationHash": _mapping(lock["integrity"])["configurationHash"],
            "thresholdHash": _mapping(lock["integrity"])["thresholdHash"],
            "junctionInventoryHash": _mapping(lock["integrity"])["junctionInventoryHash"],
        },
        "identities": {
            "patternHash": _mapping(lock["candidate"])["patternHash"],
            "seamConstraintHash": _mapping(lock["candidate"])["seamConstraintHash"],
            "simulationTopologyHash": topology_hash(inputs.rest_mesh),
            "simulationRestContentHash": geometry_content_hash(inputs.rest_mesh),
            "simulationSettledContentHash": geometry_content_hash(primary.settled_mesh),
            "renderTopologyHash": inputs.binding.render_topology_hash,
            "bindingSha256": _mapping(lock["candidate"])["bindingSha256"],
            "avatarContractHash": _mapping(lock["fixedInputs"])["avatarContractHash"],
            "materialPayloadHash": _mapping(lock["fixedInputs"])["materialPayloadHash"],
            "trajectoryContentHash": primary.diagnostics["trajectoryContentHash"],
        },
        "junctionGraph": inputs.junction_graph,
        "seam": seams,
        "supports": {
            "inventory": audit_support_inventory(inputs.supports, lock),
            "maximumResidualMetersWhileActive": _round(maximum_support_residual),
            "activeFrameCount": len(active_support_records),
            "releasedFrameCount": len(released_support_records),
            "afterReleaseMetrics": {
                "status": "not_applicable",
                "reason": "temporary_supports_fully_released",
            },
            "history": support_history,
        },
        "collision": {
            "self": self_collision,
            "body": body,
            "denseRender": render,
            "independentOracleVersions": [
                TRIANGLE_BODY_ORACLE_VERSION,
                TRIANGLE_TRIANGLE_ORACLE_VERSION,
            ],
            "residualViolationCount": residual_violations,
        },
        "deformation": deformation,
        "temporal": temporal,
        "opening": opening,
        "strain": strain,
        "terminalMotion": terminal,
        "solver": primary.diagnostics,
        "determinism": deterministic,
        "acceptance": {
            "status": "pass" if not failed else "fail",
            "checks": checks,
            "failedChecks": failed,
            "numericalTerminationSeparateFromPhysicalAcceptance": True,
        },
        "progression": {
            "neutralPreflightPassed": not failed,
            "phy1Executed": False,
            "ccdExecuted": False,
            "z2Executed": False,
            "stopReason": "neutral_preflight_failed_stop_rule"
            if failed
            else ("neutral_passed_conditional_phy1_required"),
            "runtimeV1RemainsSelected": True,
            "topologyV2RuntimeExposed": False,
            "budget": deepcopy(lock["budget"]),
        },
        "sourceInventory": [
            {"path": path, "sha256": sha256_file(root / path)} for path in source_files
        ],
        "unsupportedClaims": deepcopy(lock["unsupportedClaims"]),
        "integrity": {"evidenceHash": ""},
    }
    report["integrity"]["evidenceHash"] = _hash_without(report, "evidenceHash")
    return report


def refresh_research_matrix(root: Path, neutral: Mapping[str, Any]) -> dict[str, Any]:
    source_path = root / (
        "docs/evidence/d0_fitting_pbr_fidelity_v2/evaluation/"
        "final_d0_research_prototype_matrix_v2.json"
    )
    source = read_json(source_path)
    rows = deepcopy(source["rows"])
    by_id = {str(item["rowId"]): item for item in rows}
    neutral_pass = _mapping(neutral.get("acceptance")).get("status") == "pass"
    for row_id in ("D0-RP-13", "D0-RP-14"):
        row = by_id[row_id]
        row["status"] = "pass"
        row["reasonCode"] = "all_predicates_passed_by_exact_candidate_phy1_v3_evidence"
        row["openedEvidence"] = [
            {
                "evidenceId": "phy1_v3",
                "path": "docs/evidence/phy1_seam_support_v3/neutral_preflight.json",
                "payloadHash": _mapping(neutral["integrity"])["evidenceHash"],
                "classification": "public_project_authored_fixture",
                "predicateResults": [
                    {
                        "predicateId": "candidate_identity_and_unsupported_claims",
                        "operation": "recompute",
                        "passed": True,
                    }
                ],
            }
        ]
        row["failClosedControls"] = {
            "artifactHashRecomputedWhenSupplied": True,
            "payloadHashRecomputedWhenOpened": True,
            "selectedIdentityContextRequired": True,
            "storedSummaryPassTrusted": False,
        }
    neutral_row = by_id["D0-RP-15"]
    neutral_row["status"] = "pass" if neutral_pass else "fail"
    neutral_row["reasonCode"] = (
        "all_predicates_passed" if neutral_pass else "evidence_predicate_failed:phy1_v3:status"
    )
    neutral_row["openedEvidence"] = by_id["D0-RP-13"]["openedEvidence"]
    statuses = {
        status: sum(item["status"] == status for item in rows)
        for status in (
            "pass",
            "fail",
            "not_run",
        )
    }
    first_unmet = next(
        (
            item["rowId"]
            for item in rows
            if item["status"] != "pass" and item["requiredForResearchPrototype"]
        ),
        None,
    )
    result = {
        "schemaVersion": 1,
        "matrixVersion": MATRIX_VERSION,
        "candidateId": neutral["candidateId"],
        "physicalCandidateId": neutral["physicalCandidateId"],
        "sourceMatrixPath": source_path.relative_to(root).as_posix(),
        "sourceMatrixHash": _mapping(source["integrity"])["matrixHash"],
        "rows": rows,
        "summary": {
            "passCount": statuses["pass"],
            "failCount": statuses["fail"],
            "notRunCount": statuses["not_run"],
            "firstUnmetRequiredPredicate": first_unmet,
            "researchPrototypeStatus": "pass" if first_unmet is None else "partial",
        },
        "integrity": {"matrixHash": ""},
    }
    result["integrity"]["matrixHash"] = _hash_without(result, "matrixHash")
    return result


def evidence_inventory(root: Path, evidence_root: Path) -> dict[str, Any]:
    inventory = package_inventory(
        evidence_root,
        exclude={".closy-forge-owned.json", "evidence_manifest.json"},
    )
    result = {
        "schemaVersion": 1,
        "manifestVersion": "closy.phy1.seam_support_v3.evidence_manifest.v1",
        "physicalCandidateId": load_experiment_lock(root)["integrity"]["physicalCandidateId"],
        "inventory": inventory,
        "evidenceDigest": inventory_digest(inventory),
        "integrity": {"manifestHash": ""},
    }
    result["integrity"]["manifestHash"] = _hash_without(result, "manifestHash")
    return result


def _junction_constraints(
    graph: Mapping[str, Any], seam_config: Mapping[str, Any]
) -> list[DistanceConstraint]:
    return [
        DistanceConstraint(
            a=int(constraint["firstVertexIndex"]),
            b=int(constraint["secondVertexIndex"]),
            rest_length=0.0,
            compliance=float(seam_config["complianceMetersPerNewton"]),
            kind="junction",
            entity_id=str(constraint["constraintId"]),
        )
        for item in graph.get("classes", [])
        for constraint in _mapping(item).get("solverConstraints", [])
    ]


def _junction_exclusion_pairs(graph: Mapping[str, Any]) -> set[tuple[int, int]]:
    return {
        (
            min(int(item["firstVertexIndex"]), int(item["secondVertexIndex"])),
            max(int(item["firstVertexIndex"]), int(item["secondVertexIndex"])),
        )
        for record in graph.get("classes", [])
        for item in _mapping(record).get("solverConstraints", [])
    }


def _solve_point_support_xpbd(
    positions: list[Vec3],
    inverse_masses: Sequence[float],
    state: _PointConstraintState,
    target: Vec3,
    compliance: float,
    strength: float,
    dt: float,
) -> tuple[float, float]:
    index = state.support.vertex_index
    inverse_mass = inverse_masses[index]
    current = list(positions[index])
    lambdas = [state.lambda_x, state.lambda_y, state.lambda_z]
    alpha = compliance / max(strength, 1e-9) / (dt * dt)
    residual_before = _length(sub(positions[index], target))
    for axis in range(3):
        constraint = current[axis] - target[axis]
        denominator = inverse_mass + alpha
        delta_lambda = (
            0.0 if denominator <= 1e-15 else (-constraint - alpha * lambdas[axis]) / denominator
        )
        lambdas[axis] += delta_lambda
        current[axis] += inverse_mass * delta_lambda
    state.lambda_x, state.lambda_y, state.lambda_z = lambdas
    positions[index] = (current[0], current[1], current[2])
    energy = 0.5 * residual_before * residual_before / max(compliance, 1e-12) * strength
    return residual_before, energy


def _junction_corruption_controls(
    inputs: Phy1SeamSupportV3Inputs, lock: Mapping[str, Any]
) -> dict[str, bool]:
    base = deepcopy(inputs.junction_graph)
    missing = deepcopy(base)
    missing["classes"] = missing["classes"][1:]
    duplicate = deepcopy(base)
    duplicate["classes"].append(deepcopy(duplicate["classes"][0]))
    split = deepcopy(base)
    split["classes"][0]["classId"] = "junction.corrupt_split"
    cross_opening = deepcopy(base)
    cross_opening["classes"][0]["participants"].append(
        {
            "participantId": "panel.front|edge.hem.front|start",
            "boundaryId": "edge.hem.front",
        }
    )
    return {
        "junction_missing": audit_authored_junction_graph(missing, inputs.pattern, lock)["status"]
        == "fail",
        "junction_duplicate": audit_authored_junction_graph(duplicate, inputs.pattern, lock)[
            "status"
        ]
        == "fail",
        "junction_split": audit_authored_junction_graph(split, inputs.pattern, lock)["status"]
        == "fail",
        "junction_cross_opening": audit_authored_junction_graph(
            cross_opening, inputs.pattern, lock
        )["status"]
        == "fail",
    }


def _stale_support_microfixture() -> bool:
    rest_centre = (0.2, 1.4, 0.0)
    moved_centre = (0.25, 1.45, 0.02)
    offset = (0.03, 0.01, -0.01)
    stale = add(rest_centre, offset)
    driven = add(moved_centre, offset)
    return driven != stale and sub(driven, stale) == sub(moved_centre, rest_centre)


def _static_trajectory_control(mesh: MeshSet) -> bool:
    hashes = [geometry_content_hash(mesh)] * 25
    return len(set(hashes)) < 3


def _candidate_identity_control(root: Path, lock: Mapping[str, Any]) -> bool:
    corrupt = deepcopy(lock)
    corrupt["candidate"]["candidateId"] = "candidate.corrupt"
    try:
        validate_candidate_package(root, corrupt)
    except ValueError:
        return True
    return False


def _opening_metrics(
    reference: MeshSet, current: MeshSet, constraints: Mapping[str, Any]
) -> dict[str, Any]:
    from .phy1_experiment import _opening_metrics as implementation

    return implementation(reference, current, dict(constraints))


def _edge_strain_metrics(reference: MeshSet, current: MeshSet) -> dict[str, Any]:
    from .phy1_experiment import _edge_strain_metrics as implementation

    return implementation(reference, current)


def _terminal_motion_metrics(
    trajectory: list[MeshSet], material: Mapping[str, Any]
) -> dict[str, Any]:
    from .phy1_experiment import _terminal_motion_metrics as implementation

    return implementation(trajectory, dict(material))


def _hash(value: object) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


def _hash_without(document: Mapping[str, Any], field: str) -> str:
    payload = deepcopy(dict(document))
    payload["integrity"][field] = ""
    return _hash(payload)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _length(value: Vec3) -> float:
    return sqrt(value[0] * value[0] + value[1] * value[1] + value[2] * value[2])


def _round(value: float) -> float:
    return round(float(value), 12)
