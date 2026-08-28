from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, radians, sin, sqrt
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet, Tri, Vec3, add, cross, scale, sub
from closy_forge.package_io.hashing import geometry_content_hash, topology_hash
from closy_forge.simulation.self_collision import (
    SelfCollisionSettings,
    analyze_self_collision,
    build_triangle_refs,
    project_self_collisions,
    seam_exclusion_pairs,
)

SOLVER_VERSION = "closy.reference_xpbd_cpu.v2.0_material_coupled_d0"
NECK_BAND_SEAM_TARGET_LENGTH_METERS = 0.02
MAX_SEAM_CRACK_METERS = 0.008
MAX_BODY_PENETRATION_METERS = 0.0005
MAX_P95_STRAIN = 0.35
MAX_STRAIN = 1.0


@dataclass(frozen=True)
class SettleSettings:
    time_step_seconds: float = 1.0 / 60.0
    step_count: int = 35
    solver_iterations: int = 6
    gravity_m_s2: float = -9.81
    damping_ratio: float = 0.18
    collision_clearance_m: float = 0.006
    stretch_stiffness: float = 0.42
    warp_stretch_stiffness: float = 0.42
    weft_stretch_stiffness: float = 0.42
    shear_stiffness: float = 0.42
    seam_stiffness: float = 0.96
    bend_stiffness: float = 0.08
    support_stiffness: float = 0.03
    self_collision_thickness_meters: float = 0.0016
    self_collision_clearance_meters: float = 0.0008
    surface_density_kg_m2: float = 0.16
    warp_stiffness_n_m: float = 550.0
    weft_stiffness_n_m: float = 420.0
    shear_stiffness_n_m: float = 120.0
    bend_stiffness_nm: float = 0.0018
    friction_coefficient: float = 0.42
    restitution_coefficient: float = 0.02
    warp_orientation_degrees: float = 0.0


@dataclass
class DistanceConstraint:
    a: int
    b: int
    rest_length: float
    compliance: float
    kind: str
    entity_id: str
    lagrange_multiplier: float = 0.0
    a_next: int | None = None
    b_next: int | None = None
    a_weight: float = 0.0
    b_weight: float = 0.0


@dataclass(frozen=True)
class SupportConstraint:
    index: int
    target: Vec3
    stiffness: float
    entity_id: str


@dataclass(frozen=True)
class FlattenedMesh:
    positions: list[Vec3]
    mesh_offsets: list[int]


@dataclass(frozen=True)
class SettleResult:
    rest_mesh: MeshSet
    settled_mesh: MeshSet
    diagnostics: dict[str, Any]
    settings: SettleSettings


@dataclass(frozen=True)
class MotionStateResult:
    state_id: str
    mesh: MeshSet
    diagnostics: dict[str, Any]
    settings: SettleSettings


def settle_reference_cloth(
    rest_mesh: MeshSet,
    seam_constraints: dict[str, Any],
    avatar_contract: dict[str, Any],
    material: dict[str, Any],
    *,
    settings: SettleSettings | None = None,
    canonical_position_digits: int | None = None,
) -> SettleResult:
    """Run a deterministic CPU reference settle pass for the fixed T-shirt fixture.

    This is deliberately a conservative MVP solver. It exercises real cloth-style constraints and
    body collision, but does not claim self-collision or production-grade drape fidelity.
    """

    active_settings = settings or SettleSettings(
        damping_ratio=float(material.get("dampingRatio", SettleSettings.damping_ratio)),
        collision_clearance_m=max(
            float(material.get("collisionClearanceMeters", SettleSettings.collision_clearance_m)),
            0.5
            * float(
                material.get("thicknessMeters", SettleSettings.self_collision_thickness_meters)
            ),
        ),
        stretch_stiffness=float(material.get("stretchStiffness", SettleSettings.stretch_stiffness)),
        warp_stretch_stiffness=float(
            material.get("warpStretchStiffness", SettleSettings.warp_stretch_stiffness)
        ),
        weft_stretch_stiffness=float(
            material.get("weftStretchStiffness", SettleSettings.weft_stretch_stiffness)
        ),
        shear_stiffness=float(material.get("shearStiffness", SettleSettings.shear_stiffness)),
        bend_stiffness=float(material.get("bendStiffness", SettleSettings.bend_stiffness)),
        self_collision_thickness_meters=float(
            material.get(
                "selfCollisionThicknessMeters", SettleSettings.self_collision_thickness_meters
            )
        ),
        surface_density_kg_m2=float(
            material.get("surfaceDensityKgM2", SettleSettings.surface_density_kg_m2)
        ),
        warp_stiffness_n_m=float(
            material.get("stretchStiffnessNPerM", SettleSettings.warp_stiffness_n_m)
        ),
        weft_stiffness_n_m=float(
            material.get("weftStretchStiffnessNPerM", SettleSettings.weft_stiffness_n_m)
        ),
        shear_stiffness_n_m=float(
            material.get("shearStiffnessNPerM", SettleSettings.shear_stiffness_n_m)
        ),
        bend_stiffness_nm=float(material.get("bendStiffnessNm", SettleSettings.bend_stiffness_nm)),
        friction_coefficient=float(
            material.get("frictionCoefficient", SettleSettings.friction_coefficient)
        ),
        restitution_coefficient=float(
            material.get("restitutionCoefficient", SettleSettings.restitution_coefficient)
        ),
        warp_orientation_degrees=float(
            material.get("warpOrientationDegrees", SettleSettings.warp_orientation_degrees)
        ),
    )
    flat = flatten_mesh(rest_mesh)
    positions = list(flat.positions)
    previous = list(flat.positions)
    velocities = [(0.0, 0.0, 0.0) for _ in positions]
    constraints = _build_distance_constraints(
        rest_mesh, seam_constraints, flat.mesh_offsets, active_settings
    )
    structural_constraints = [constraint for constraint in constraints if constraint.kind != "seam"]
    stitch_constraints = [constraint for constraint in constraints if constraint.kind == "seam"]
    inverse_masses = _particle_inverse_masses(rest_mesh, active_settings.surface_density_kg_m2)
    supports = _build_support_constraints(rest_mesh, flat.mesh_offsets, active_settings)
    primitives = list(avatar_contract.get("collisionPrimitives", []))
    self_collision_settings = SelfCollisionSettings(
        thickness_meters=active_settings.self_collision_thickness_meters,
        clearance_meters=active_settings.self_collision_clearance_meters,
        max_iterations=1,
        response_mode="legacy_vertex_only",
    )
    self_collision_triangles, _ = build_triangle_refs(rest_mesh)
    fixed_support_indices = {support.index for support in supports}
    self_collision_exclusions = seam_exclusion_pairs(seam_constraints, flat.mesh_offsets)

    energy_history: list[float] = []
    collision_events = 0
    self_collision_corrections = 0
    self_collision_convergence: list[dict[str, Any]] = []
    dt = active_settings.time_step_seconds
    for step in range(active_settings.step_count):
        for constraint in constraints:
            constraint.lagrange_multiplier = 0.0
        for index, velocity in enumerate(velocities):
            previous[index] = positions[index]
            velocities[index] = (
                velocity[0],
                (velocity[1] + active_settings.gravity_m_s2 * dt)
                * (1.0 - active_settings.damping_ratio * 0.08),
                velocity[2],
            )
            positions[index] = add(positions[index], scale(velocities[index], dt))
        positions = _canonicalize_positions(positions, canonical_position_digits)

        for _iteration in range(active_settings.solver_iterations):
            for constraint in structural_constraints:
                _solve_distance(
                    positions,
                    inverse_masses,
                    constraint,
                    active_settings.time_step_seconds,
                )
            for support in supports:
                _solve_support(positions, support)
            positions = _canonicalize_positions(positions, canonical_position_digits)
            collision_events += _project_collisions(
                positions,
                previous,
                primitives,
                active_settings.collision_clearance_m,
                active_settings.friction_coefficient,
                active_settings.restitution_coefficient,
                dt,
            )
            for constraint in stitch_constraints:
                _solve_distance(
                    positions,
                    inverse_masses,
                    constraint,
                    active_settings.time_step_seconds,
                )
            positions = _canonicalize_positions(positions, canonical_position_digits)

        # Projection is part of deterministic solver substeps, not a report-only cleanup pass.
        if (step + 1) % 10 == 0:
            positions, convergence = project_self_collisions(
                positions,
                self_collision_triangles,
                fixed_indices=fixed_support_indices,
                settings=self_collision_settings,
                excluded_vertex_pairs=self_collision_exclusions,
                orientation_reference_positions=flat.positions,
            )
            self_collision_corrections += int(convergence.get("totalCorrectionCount", 0))
            self_collision_convergence.append({"substep": step + 1, **convergence})
            positions = _canonicalize_positions(positions, canonical_position_digits)

        for index, position in enumerate(positions):
            velocities[index] = scale(sub(position, previous[index]), 1.0 / dt)
        energy_history.append(_energy_proxy(positions, velocities))

    collision_events += _project_collisions(
        positions,
        previous,
        primitives,
        active_settings.collision_clearance_m,
        active_settings.friction_coefficient,
        active_settings.restitution_coefficient,
        dt,
    )
    positions = _canonicalize_positions(positions, canonical_position_digits)
    positions, self_collision_metrics = project_self_collisions(
        positions,
        self_collision_triangles,
        fixed_indices=fixed_support_indices,
        settings=self_collision_settings,
        excluded_vertex_pairs=self_collision_exclusions,
        orientation_reference_positions=flat.positions,
    )
    positions = _canonicalize_positions(positions, canonical_position_digits)
    for _ in range(active_settings.solver_iterations * 2):
        for constraint in structural_constraints:
            _solve_distance(positions, inverse_masses, constraint, dt)
        for support in supports:
            _solve_support(positions, support)
        _project_collisions(
            positions,
            previous,
            primitives,
            active_settings.collision_clearance_m,
            active_settings.friction_coefficient,
            active_settings.restitution_coefficient,
            dt,
        )
        for constraint in stitch_constraints:
            _solve_distance(positions, inverse_masses, constraint, dt)
        positions = _canonicalize_positions(positions, canonical_position_digits)
    collision_events += _project_collisions(
        positions,
        previous,
        primitives,
        active_settings.collision_clearance_m,
        active_settings.friction_coefficient,
        active_settings.restitution_coefficient,
        dt,
    )
    positions = _canonicalize_positions(positions, canonical_position_digits)
    self_collision_corrections += int(self_collision_metrics.get("totalCorrectionCount", 0))
    self_collision_convergence.append(
        {"substep": active_settings.step_count, "finalProjection": True, **self_collision_metrics}
    )
    settled_mesh = replace_mesh_positions(rest_mesh, positions, flat.mesh_offsets)
    diagnostics = _diagnostics(
        rest_mesh,
        settled_mesh,
        seam_constraints,
        constraints,
        primitives,
        collision_events,
        energy_history,
        active_settings,
        self_collision_settings,
        self_collision_corrections,
        self_collision_convergence,
    )
    if canonical_position_digits is not None:
        diagnostics = _canonicalize_numeric_payload(diagnostics, canonical_position_digits)
        diagnostics["canonicalPositionDigits"] = canonical_position_digits
    return SettleResult(rest_mesh, settled_mesh, diagnostics, active_settings)


def simulate_reference_motion_state(
    settled_mesh: MeshSet,
    seam_constraints: dict[str, Any],
    avatar_contract: dict[str, Any],
    material: dict[str, Any],
    state_id: str,
    *,
    canonical_position_digits: int | None = None,
) -> MotionStateResult:
    """Generate a bounded solver-produced state without touching a render mesh."""

    settings = SettleSettings(
        time_step_seconds=1.0 / 60.0,
        step_count=6,
        solver_iterations=5,
        gravity_m_s2=-2.2,
        damping_ratio=float(material.get("dampingRatio", 0.18)),
        stretch_stiffness=float(material.get("stretchStiffness", 0.42)),
        warp_stretch_stiffness=float(material.get("warpStretchStiffness", 0.42)),
        weft_stretch_stiffness=float(material.get("weftStretchStiffness", 0.34)),
        shear_stiffness=float(material.get("shearStiffness", 0.28)),
        seam_stiffness=0.97,
        bend_stiffness=float(material.get("bendStiffness", 0.08)),
        support_stiffness=0.018,
        collision_clearance_m=float(material.get("collisionClearanceMeters", 0.006)),
        self_collision_thickness_meters=float(material.get("selfCollisionThicknessMeters", 0.0016)),
    )
    flat = flatten_mesh(settled_mesh)
    panel_ids = [mesh.panel_id for mesh in settled_mesh.meshes for _ in mesh.vertices]
    positions = [
        add(position, _motion_seed_offset(panel_ids[index], position, state_id))
        for index, position in enumerate(flat.positions)
    ]
    positions = _canonicalize_positions(positions, canonical_position_digits)
    previous = list(flat.positions)
    constraints = _build_distance_constraints(
        settled_mesh, seam_constraints, flat.mesh_offsets, settings
    )
    structural_constraints = [constraint for constraint in constraints if constraint.kind != "seam"]
    stitch_constraints = [constraint for constraint in constraints if constraint.kind == "seam"]
    inverse_masses = _particle_inverse_masses(settled_mesh, settings.surface_density_kg_m2)
    supports = _build_support_constraints(settled_mesh, flat.mesh_offsets, settings)
    primitives = list(avatar_contract.get("collisionPrimitives", []))
    triangles, _ = build_triangle_refs(settled_mesh)
    exclusions = seam_exclusion_pairs(seam_constraints, flat.mesh_offsets)
    fixed = {support.index for support in supports}
    collision_settings = SelfCollisionSettings(
        thickness_meters=settings.self_collision_thickness_meters,
        clearance_meters=settings.self_collision_clearance_meters,
        max_iterations=1,
        response_mode="legacy_vertex_only",
    )
    convergence: list[dict[str, Any]] = []
    energy_history: list[float] = []
    dt = settings.time_step_seconds
    for step in range(settings.step_count):
        for constraint in constraints:
            constraint.lagrange_multiplier = 0.0
        for index, position in enumerate(positions):
            velocity = scale(sub(position, previous[index]), (1.0 - settings.damping_ratio) / dt)
            previous[index] = position
            force = _motion_step_acceleration(panel_ids[index], position, state_id, step)
            acceleration = add((0.0, settings.gravity_m_s2, 0.0), force)
            velocity = add(velocity, scale(acceleration, dt))
            positions[index] = add(position, scale(velocity, dt))
        positions = _canonicalize_positions(positions, canonical_position_digits)
        for _iteration in range(settings.solver_iterations):
            for constraint in structural_constraints:
                _solve_distance(positions, inverse_masses, constraint, dt)
            for support in supports:
                _solve_support(positions, support)
            positions = _canonicalize_positions(positions, canonical_position_digits)
            _project_collisions(
                positions,
                previous,
                primitives,
                settings.collision_clearance_m,
                settings.friction_coefficient,
                settings.restitution_coefficient,
                dt,
            )
            for constraint in stitch_constraints:
                _solve_distance(positions, inverse_masses, constraint, dt)
            positions = _canonicalize_positions(positions, canonical_position_digits)
        if step + 1 == settings.step_count:
            positions, collision = project_self_collisions(
                positions,
                triangles,
                fixed_indices=fixed,
                settings=collision_settings,
                excluded_vertex_pairs=exclusions,
                orientation_reference_positions=flat.positions,
            )
            convergence.append({"substep": step + 1, **collision})
            positions = _canonicalize_positions(positions, canonical_position_digits)
        velocities = [
            scale(sub(position, old), 1.0 / dt)
            for position, old in zip(positions, previous, strict=True)
        ]
        energy_history.append(_energy_proxy(positions, velocities))

    mesh = replace_mesh_positions(settled_mesh, positions, flat.mesh_offsets)
    diagnostics = {
        "solverVersion": SOLVER_VERSION,
        "stateId": state_id,
        "stateGenerator": "bounded_reference_cloth_impulse_solver",
        "stepCount": settings.step_count,
        "solverIterations": settings.solver_iterations,
        "energyHistory": [_round(value) for value in energy_history],
        "selfCollisionConvergence": convergence,
        "finitePositions": all(isfinite(value) for point in positions for value in point),
        "invertedOrDegenerateTriangleCount": _inverted_or_degenerate_triangle_count(mesh),
    }
    if canonical_position_digits is not None:
        diagnostics["canonicalPositionDigits"] = canonical_position_digits
    return MotionStateResult(state_id, mesh, diagnostics, settings)


def _canonicalize_positions(positions: list[Vec3], digits: int | None) -> list[Vec3]:
    if digits is None:
        return positions
    if not 0 <= digits <= 12:
        raise ValueError("canonical_position_digits must be between 0 and 12")
    return [
        (
            round(float(position[0]), digits),
            round(float(position[1]), digits),
            round(float(position[2]), digits),
        )
        for position in positions
    ]


def _canonicalize_numeric_payload(value: Any, digits: int) -> Any:
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, dict):
        return {key: _canonicalize_numeric_payload(item, digits) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonicalize_numeric_payload(item, digits) for item in value]
    return value


def flatten_mesh(meshset: MeshSet) -> FlattenedMesh:
    positions: list[Vec3] = []
    offsets: list[int] = []
    for mesh in meshset.meshes:
        offsets.append(len(positions))
        positions.extend(mesh.vertices)
    return FlattenedMesh(positions, offsets)


def _particle_inverse_masses(meshset: MeshSet, surface_density_kg_m2: float) -> list[float]:
    if not isfinite(surface_density_kg_m2) or surface_density_kg_m2 <= 0.0:
        raise ValueError("surface_density_must_be_positive")
    inverse_masses: list[float] = []
    for mesh in meshset.meshes:
        masses = [0.0 for _ in mesh.vertices]
        for triangle in mesh.triangles:
            area = _triangle_area2(mesh.vertices, triangle) * 0.5
            contribution = surface_density_kg_m2 * area / 3.0
            for vertex_index in triangle:
                masses[vertex_index] += contribution
        mean_mass = sum(masses) / max(1, len(masses))
        minimum_mass = max(surface_density_kg_m2 * 1e-10, mean_mass * 0.1)
        inverse_masses.extend(1.0 / max(minimum_mass, mass) for mass in masses)
    return inverse_masses


def replace_mesh_positions(meshset: MeshSet, positions: list[Vec3], offsets: list[int]) -> MeshSet:
    meshes: list[Mesh] = []
    for mesh_index, mesh in enumerate(meshset.meshes):
        start = offsets[mesh_index]
        end = start + len(mesh.vertices)
        meshes.append(
            Mesh(
                name=mesh.name,
                panel_id=mesh.panel_id,
                vertices=positions[start:end],
                panel_uvs=mesh.panel_uvs,
                triangles=mesh.triangles,
                material_id=mesh.material_id,
            )
        )
    return MeshSet(meshes)


def simulation_state_json(
    *,
    state_id: str,
    meshset: MeshSet,
    source_mesh: MeshSet | None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "stateId": state_id,
        "solverVersion": SOLVER_VERSION,
        "meshTopologyHash": topology_hash(meshset),
        "meshContentHash": geometry_content_hash(meshset),
        "sourceContentHash": geometry_content_hash(source_mesh) if source_mesh else None,
        "diagnosticsRef": "simulation/settle_diagnostics.json" if diagnostics else None,
        "meshes": [
            {
                "name": mesh.name,
                "panelId": mesh.panel_id,
                "positions": [list(vertex) for vertex in mesh.vertices],
            }
            for mesh in meshset.meshes
        ],
    }


def _build_distance_constraints(
    meshset: MeshSet,
    seam_constraints: dict[str, Any],
    offsets: list[int],
    settings: SettleSettings,
) -> list[DistanceConstraint]:
    constraints: list[DistanceConstraint] = []
    for mesh_index, mesh in enumerate(meshset.meshes):
        seen_edges: set[tuple[int, int]] = set()
        for triangle in mesh.triangles:
            for local_a, local_b in _triangle_edges(triangle):
                edge = (min(local_a, local_b), max(local_a, local_b))
                if edge in seen_edges:
                    continue
                seen_edges.add(edge)
                a = offsets[mesh_index] + local_a
                b = offsets[mesh_index] + local_b
                kind, compliance = _edge_material_constraint(mesh, local_a, local_b, settings)
                constraints.append(
                    DistanceConstraint(
                        a,
                        b,
                        _distance(mesh.vertices[local_a], mesh.vertices[local_b]),
                        compliance,
                        kind,
                        f"{mesh.panel_id}:{local_a}-{local_b}",
                    )
                )
        for a, b in _bend_pairs(mesh.triangles):
            constraints.append(
                DistanceConstraint(
                    offsets[mesh_index] + a,
                    offsets[mesh_index] + b,
                    _distance(mesh.vertices[a], mesh.vertices[b]),
                    1.0
                    / max(
                        1e-9,
                        settings.bend_stiffness_nm * max(0.05, settings.bend_stiffness),
                    ),
                    "bend",
                    f"{mesh.panel_id}:{a}-{b}",
                )
            )

    for seam_doc in seam_constraints.get("constraints", []):
        span_a = seam_doc["spanA"]
        span_b = seam_doc["spanB"]
        a = offsets[int(span_a["meshIndex"])] + int(span_a["vertexIndex"])
        b = offsets[int(span_b["meshIndex"])] + int(span_b["vertexIndex"])
        a_next = offsets[int(span_a["meshIndex"])] + int(
            span_a.get("nextVertexIndex", span_a["vertexIndex"])
        )
        b_next = offsets[int(span_b["meshIndex"])] + int(
            span_b.get("nextVertexIndex", span_b["vertexIndex"])
        )
        a_weight = float(span_a.get("interpolationWeight", 0.0))
        b_weight = float(span_b.get("interpolationWeight", 0.0))
        panel_a = str(span_a["panelId"])
        panel_b = str(span_b["panelId"])
        target_length = 0.0
        if "panel.neck_band" in {panel_a, panel_b}:
            mesh_a = meshset.meshes[int(span_a["meshIndex"])]
            mesh_b = meshset.meshes[int(span_b["meshIndex"])]
            point_a = _weighted_point(
                mesh_a.vertices[int(span_a["vertexIndex"])],
                mesh_a.vertices[int(span_a.get("nextVertexIndex", span_a["vertexIndex"]))],
                a_weight,
            )
            point_b = _weighted_point(
                mesh_b.vertices[int(span_b["vertexIndex"])],
                mesh_b.vertices[int(span_b.get("nextVertexIndex", span_b["vertexIndex"]))],
                b_weight,
            )
            rest_distance = _distance(point_a, point_b)
            target_length = min(NECK_BAND_SEAM_TARGET_LENGTH_METERS, rest_distance * 0.50)
        constraints.append(
            DistanceConstraint(
                a,
                b,
                target_length,
                max(0.0, 1.0 - settings.seam_stiffness) * 1e-6,
                "seam",
                str(seam_doc["seamId"]),
                a_next=a_next,
                b_next=b_next,
                a_weight=a_weight,
                b_weight=b_weight,
            )
        )
    return constraints


def _edge_material_constraint(
    mesh: Mesh, local_a: int, local_b: int, settings: SettleSettings
) -> tuple[str, float]:
    """Classify a panel edge in pattern UV space for anisotropic D0 constraints."""

    uv_a = mesh.panel_uvs[local_a]
    uv_b = mesh.panel_uvs[local_b]
    delta_u = abs(uv_b[0] - uv_a[0])
    delta_v = abs(uv_b[1] - uv_a[1])
    largest = max(delta_u, delta_v)
    if largest <= 1e-12:
        effective = settings.warp_stiffness_n_m * max(0.05, settings.stretch_stiffness)
        return "stretch", 1.0 / max(1e-9, effective)
    theta = radians(settings.warp_orientation_degrees)
    warp_u, warp_v = -sin(theta), cos(theta)
    edge_length = sqrt(delta_u * delta_u + delta_v * delta_v)
    warp_alignment = abs((delta_u * warp_u + delta_v * warp_v) / edge_length)
    weft_alignment = sqrt(max(0.0, 1.0 - warp_alignment * warp_alignment))
    if min(warp_alignment, weft_alignment) >= 0.22:
        effective = settings.shear_stiffness_n_m * max(0.05, settings.shear_stiffness)
        return "shear", 1.0 / max(1e-9, effective)
    if warp_alignment > weft_alignment:
        effective = settings.warp_stiffness_n_m * max(0.05, settings.warp_stretch_stiffness)
        return "warp_stretch", 1.0 / max(1e-9, effective)
    effective = settings.weft_stiffness_n_m * max(0.05, settings.weft_stretch_stiffness)
    return "weft_stretch", 1.0 / max(1e-9, effective)


def _build_support_constraints(
    meshset: MeshSet, offsets: list[int], settings: SettleSettings
) -> list[SupportConstraint]:
    supports: list[SupportConstraint] = []
    for mesh_index, mesh in enumerate(meshset.meshes):
        panel_top = max(vertex[1] for vertex in mesh.vertices)
        lower_body_panel = any(
            token in mesh.panel_id
            for token in (
                "simple_skirt",
                "simple_trousers",
                "dress.skirt",
                "layered_asymmetric",
            )
        )
        for vertex_index, vertex in enumerate(mesh.vertices):
            if (
                mesh.panel_id == "panel.neck_band"
                or vertex[1] >= 1.345
                or (lower_body_panel and vertex[1] >= panel_top - 0.025)
            ):
                supports.append(
                    SupportConstraint(
                        offsets[mesh_index] + vertex_index,
                        vertex,
                        settings.support_stiffness,
                        f"support.{mesh.panel_id}.{vertex_index}",
                    )
                )
    return supports


def _solve_distance(
    positions: list[Vec3],
    inverse_masses: list[float],
    constraint: DistanceConstraint,
    time_step_seconds: float,
) -> None:
    a_next = constraint.a if constraint.a_next is None else constraint.a_next
    b_next = constraint.b if constraint.b_next is None else constraint.b_next
    a = _weighted_point(positions[constraint.a], positions[a_next], constraint.a_weight)
    b = _weighted_point(positions[constraint.b], positions[b_next], constraint.b_weight)
    delta = sub(b, a)
    length = _length(delta)
    if length <= 1e-10:
        return
    direction = scale(delta, 1.0 / length)
    a_coefficients = (
        (constraint.a, 1.0 - constraint.a_weight),
        (a_next, constraint.a_weight),
    )
    b_coefficients = (
        (constraint.b, 1.0 - constraint.b_weight),
        (b_next, constraint.b_weight),
    )
    weighted_inverse_mass = sum(
        inverse_masses[index] * coefficient * coefficient
        for index, coefficient in (*a_coefficients, *b_coefficients)
    )
    alpha = constraint.compliance / (time_step_seconds * time_step_seconds)
    denominator = weighted_inverse_mass + alpha
    if denominator <= 1e-12:
        return
    delta_lambda = (
        -(length - constraint.rest_length) - alpha * constraint.lagrange_multiplier
    ) / denominator
    constraint.lagrange_multiplier += delta_lambda
    for index, coefficient in a_coefficients:
        positions[index] = add(
            positions[index],
            scale(direction, -inverse_masses[index] * coefficient * delta_lambda),
        )
    for index, coefficient in b_coefficients:
        positions[index] = add(
            positions[index],
            scale(direction, inverse_masses[index] * coefficient * delta_lambda),
        )


def _solve_support(positions: list[Vec3], support: SupportConstraint) -> None:
    current = positions[support.index]
    positions[support.index] = add(current, scale(sub(support.target, current), support.stiffness))


def _project_collisions(
    positions: list[Vec3],
    previous: list[Vec3],
    primitives: list[dict[str, Any]],
    clearance: float,
    friction: float,
    restitution: float,
    time_step_seconds: float,
) -> int:
    events = 0
    for index, position in enumerate(positions):
        projected = position
        for primitive in primitives:
            candidate, penetrated = _project_primitive(projected, primitive, clearance)
            if penetrated:
                normal_delta = sub(candidate, projected)
                normal_length = _length(normal_delta)
                if normal_length > 1e-12:
                    normal = scale(normal_delta, 1.0 / normal_length)
                    velocity = scale(sub(projected, previous[index]), 1.0 / time_step_seconds)
                    normal_speed = _dot(velocity, normal)
                    normal_velocity = scale(normal, normal_speed)
                    tangent_velocity = sub(velocity, normal_velocity)
                    response = scale(tangent_velocity, max(0.0, 1.0 - friction))
                    if normal_speed < 0.0:
                        response = add(response, scale(normal, -normal_speed * restitution))
                    previous[index] = sub(candidate, scale(response, time_step_seconds))
                projected = candidate
                events += 1
        positions[index] = projected
    return events


def _project_primitive(
    point: Vec3, primitive: dict[str, Any], clearance: float
) -> tuple[Vec3, bool]:
    if primitive.get("type") == "ellipsoid":
        center = _vec3(primitive["center"])
        radii = _vec3(primitive["radii"])
        local = (
            (point[0] - center[0]) / radii[0],
            (point[1] - center[1]) / radii[1],
            (point[2] - center[2]) / radii[2],
        )
        length = _length(local)
        inflated = 1.0 + clearance / max(1e-6, min(radii))
        if length >= inflated:
            return point, False
        direction = (0.0, 1.0, 0.0) if length <= 1e-9 else scale(local, 1.0 / length)
        projected = (
            center[0] + direction[0] * radii[0] * inflated,
            center[1] + direction[1] * radii[1] * inflated,
            center[2] + direction[2] * radii[2] * inflated,
        )
        return projected, True
    if primitive.get("type") == "capsule":
        a = _vec3(primitive["a"])
        b = _vec3(primitive["b"])
        radius = float(primitive["radius"]) + clearance
        nearest = _closest_point_on_segment(point, a, b)
        delta = sub(point, nearest)
        length = _length(delta)
        if length >= radius:
            return point, False
        direction = (0.0, 1.0, 0.0) if length <= 1e-9 else scale(delta, 1.0 / length)
        return add(nearest, scale(direction, radius)), True
    return point, False


def _diagnostics(
    rest_mesh: MeshSet,
    settled_mesh: MeshSet,
    seam_constraints: dict[str, Any],
    constraints: list[DistanceConstraint],
    primitives: list[dict[str, Any]],
    collision_events: int,
    energy_history: list[float],
    settings: SettleSettings,
    self_collision_settings: SelfCollisionSettings,
    self_collision_corrections: int,
    self_collision_convergence: list[dict[str, Any]],
) -> dict[str, Any]:
    flat_settled = flatten_mesh(settled_mesh)
    seam_residuals = [
        abs(_distance_constraint_length(flat_settled.positions, c) - c.rest_length)
        for c in constraints
        if c.kind == "seam"
    ]
    strains = [
        abs(_distance_constraint_length(flat_settled.positions, c) / c.rest_length - 1.0)
        for c in constraints
        if c.kind in {"stretch", "warp_stretch", "weft_stretch", "shear"} and c.rest_length > 1e-8
    ]
    penetrations = [
        _penetration_depth(vertex, primitives, settings.collision_clearance_m)
        for vertex in flat_settled.positions
    ]
    inverted = _inverted_or_degenerate_triangle_count(settled_mesh)
    nonfinite = sum(
        1
        for vertex in flat_settled.positions
        if not all(isfinite(component) for component in vertex)
    )
    max_seam = max(seam_residuals, default=0.0)
    rms_seam = _rms(seam_residuals)
    max_penetration = max(penetrations, default=0.0)
    mean_penetration = sum(penetrations) / max(1, len(penetrations))
    max_strain = max(strains, default=0.0)
    p95_strain = _percentile(strains, 0.95)
    mean_strain = sum(strains) / max(1, len(strains))
    self_collision_analysis = analyze_self_collision(
        settled_mesh,
        settings=self_collision_settings,
        excluded_vertex_pairs=seam_exclusion_pairs(
            seam_constraints, flatten_mesh(settled_mesh).mesh_offsets
        ),
    )
    numerical_termination = "completed" if nonfinite == 0 and inverted == 0 else "failed"
    constraint_convergence = (
        "passed"
        if max_seam <= MAX_SEAM_CRACK_METERS and rms_seam <= MAX_SEAM_CRACK_METERS * 0.5
        else "failed"
    )
    collision_resolution = (
        "passed"
        if max_penetration <= MAX_BODY_PENETRATION_METERS
        and self_collision_analysis.unresolved_contact_count == 0
        else "failed"
    )
    strain_quality = (
        "passed" if max_strain <= MAX_STRAIN and p95_strain <= MAX_P95_STRAIN else "failed"
    )
    energy_growth_ratio = (
        energy_history[-1] / energy_history[0]
        if energy_history and energy_history[0] > 1e-12
        else 0.0
    )
    energy_decay = "passed" if energy_growth_ratio <= 1.25 else "failed"
    physical_quality_accepted = (
        all(
            status == "passed"
            for status in (
                constraint_convergence,
                collision_resolution,
                strain_quality,
                energy_decay,
            )
        )
        and numerical_termination == "completed"
    )
    convergence = "converged" if physical_quality_accepted else "failed"
    return {
        "schemaVersion": 1,
        "solverVersion": SOLVER_VERSION,
        "backend": "deterministic_cpu_reference_xpbd",
        "convergenceState": convergence,
        "numericalTermination": numerical_termination,
        "constraintConvergence": constraint_convergence,
        "collisionResolution": collision_resolution,
        "strainQuality": strain_quality,
        "energyDecay": energy_decay,
        "physicalQualityAccepted": physical_quality_accepted,
        "settings": {
            "timeStepSeconds": settings.time_step_seconds,
            "stepCount": settings.step_count,
            "solverIterations": settings.solver_iterations,
            "gravityMS2": settings.gravity_m_s2,
            "dampingRatio": settings.damping_ratio,
            "collisionClearanceMeters": settings.collision_clearance_m,
            "stretchStiffness": settings.stretch_stiffness,
            "warpStretchStiffness": settings.warp_stretch_stiffness,
            "weftStretchStiffness": settings.weft_stretch_stiffness,
            "shearStiffness": settings.shear_stiffness,
            "seamStiffness": settings.seam_stiffness,
            "bendStiffness": settings.bend_stiffness,
            "supportStiffness": settings.support_stiffness,
            "selfCollisionThicknessMeters": settings.self_collision_thickness_meters,
            "selfCollisionClearanceMeters": settings.self_collision_clearance_meters,
            "surfaceDensityKgM2": settings.surface_density_kg_m2,
            "warpStiffnessNPerM": settings.warp_stiffness_n_m,
            "weftStiffnessNPerM": settings.weft_stiffness_n_m,
            "shearStiffnessNPerM": settings.shear_stiffness_n_m,
            "bendStiffnessNm": settings.bend_stiffness_nm,
            "frictionCoefficient": settings.friction_coefficient,
            "restitutionCoefficient": settings.restitution_coefficient,
            "warpOrientationDegrees": settings.warp_orientation_degrees,
            "constraintProjection": "xpbd_compliance_with_per_substep_lagrange_accumulation",
            "particleMassPolicy": "triangle_area_times_areal_density_lumped_one_third",
            "constraintOrder": (
                "integrate_prediction_then_structural_then_support_then_body_collision_then_"
                "seams_per_iteration_then_self_collision_at_declared_frame_cadence"
            ),
            "selfCollisionCadenceFrames": 10,
            "selfCollisionCadenceSeconds": _round(10 * settings.time_step_seconds),
            "selfCollisionTerminalProjection": True,
            "constraintOrderConvergenceReady": False,
        },
        "elapsedTimeSeconds": 0.0,
        "elapsedTimePolicy": "wall_clock_omitted_from_canonical_package_for_determinism",
        "iterations": settings.step_count * settings.solver_iterations,
        "substeps": settings.step_count,
        "maximumSeamResidualMeters": max_seam,
        "rmsSeamResidualMeters": rms_seam,
        "maximumBodyPenetrationMeters": max_penetration,
        "meanBodyPenetrationMeters": mean_penetration,
        "collisionCount": collision_events,
        "invertedOrDegenerateElementCount": inverted,
        "nonFiniteValueCount": nonfinite,
        "maximumStrain": max_strain,
        "meanStrain": mean_strain,
        "p95Strain": p95_strain,
        "energyGrowthRatio": _round(energy_growth_ratio),
        "energyHistory": energy_history,
        "selfCollision": {
            "available": True,
            "profile": "d0_reference_vertex_triangle",
            "reportRef": "reports/self_collision_report.json",
            "broadPhaseRun": True,
            "narrowPhaseRun": True,
            "correctionRun": True,
            "bruteForceOracleRun": True,
            "candidatePairCount": len(self_collision_analysis.candidate_pairs),
            "contactCount": len(self_collision_analysis.contacts),
            "unresolvedContactCount": self_collision_analysis.unresolved_contact_count,
            "maxPenetrationMeters": _round(self_collision_analysis.max_penetration_meters),
            "totalCorrectionCount": self_collision_corrections,
            "solverSubstepConvergence": self_collision_convergence,
            "integratedIntoSolverSubsteps": True,
            "highVelocityTunnelling": "unsupported_high_velocity_tunnelling",
            "acceptedForD0ReferenceSolver": collision_resolution == "passed",
            "acceptedForProductionGpuSolver": False,
        },
        "restTopologyHash": topology_hash(rest_mesh),
        "settledTopologyHash": topology_hash(settled_mesh),
        "restContentHash": geometry_content_hash(rest_mesh),
        "settledContentHash": geometry_content_hash(settled_mesh),
        "perPanelWarnings": [],
        "perSeamWarnings": _seam_warnings(seam_constraints, seam_residuals),
    }


def _seam_residuals(
    seam_constraints: dict[str, Any], positions: list[Vec3], offsets: list[int]
) -> list[float]:
    residuals = []
    for seam_doc in seam_constraints.get("constraints", []):
        span_a = seam_doc["spanA"]
        span_b = seam_doc["spanB"]
        residuals.append(
            _distance(
                _span_position_from_flat(positions, offsets, span_a),
                _span_position_from_flat(positions, offsets, span_b),
            )
        )
    return residuals


def _seam_warnings(
    seam_constraints: dict[str, Any], residuals: list[float]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for seam_doc, residual in zip(seam_constraints.get("constraints", []), residuals, strict=False):
        if residual > MAX_SEAM_CRACK_METERS:
            out.append(
                {
                    "seamId": seam_doc["seamId"],
                    "code": "seam_residual_above_reference_threshold",
                    "residualMeters": residual,
                }
            )
    return out


def _penetration_depth(point: Vec3, primitives: list[dict[str, Any]], clearance: float) -> float:
    depths = [_primitive_penetration_depth(point, primitive, clearance) for primitive in primitives]
    return max(depths, default=0.0)


def _primitive_penetration_depth(point: Vec3, primitive: dict[str, Any], clearance: float) -> float:
    if primitive.get("type") == "ellipsoid":
        center = _vec3(primitive["center"])
        radii = _vec3(primitive["radii"])
        local = (
            (point[0] - center[0]) / radii[0],
            (point[1] - center[1]) / radii[1],
            (point[2] - center[2]) / radii[2],
        )
        length = _length(local)
        inflated = 1.0 + clearance / max(1e-6, min(radii))
        if length >= inflated:
            return 0.0
        return (inflated - length) * min(radii)
    if primitive.get("type") == "capsule":
        a = _vec3(primitive["a"])
        b = _vec3(primitive["b"])
        nearest = _closest_point_on_segment(point, a, b)
        return max(0.0, float(primitive["radius"]) + clearance - _distance(point, nearest))
    return 0.0


def _inverted_or_degenerate_triangle_count(meshset: MeshSet) -> int:
    count = 0
    for mesh in meshset.meshes:
        for tri in mesh.triangles:
            if _triangle_area2(mesh.vertices, tri) <= 1e-10:
                count += 1
    return count


def _motion_seed_offset(panel_id: str, point: Vec3, state_id: str) -> Vec3:
    x, y, _z = point
    left = panel_id == "panel.sleeve.left"
    right = panel_id == "panel.sleeve.right"
    torso = panel_id in {"panel.front", "panel.back", "panel.neck_band"}
    if state_id == "neutral_settled":
        return (0.0, 0.0, 0.0)
    if state_id == "left_arm_raise" and left:
        return (-0.018, 0.050, 0.004)
    if state_id == "right_arm_raise" and right:
        return (0.018, 0.050, -0.004)
    if state_id == "forward_bend":
        return (0.0, -0.008 * max(0.0, y - 1.0), 0.030 * max(0.0, y - 0.9))
    if state_id == "side_bend":
        return (0.025 * max(0.0, y - 0.9), 0.0, 0.0)
    if state_id == "torso_twist" and torso:
        return (0.012 * point[2], 0.0, -0.012 * x)
    if state_id == "moderate_gust":
        return (0.0, 0.0, 0.022 * max(0.0, 1.4 - y))
    if state_id == "lightweight_material_extreme":
        return (0.0, -0.014 * max(0.0, 1.35 - y), 0.008)
    if state_id == "stiff_material_extreme":
        return (0.004 * x, 0.004 * max(0.0, y - 1.0), 0.0)
    if state_id == "opening_stress":
        return ((-0.010 if x < 0.0 else 0.010), 0.006, 0.0)
    if state_id == "seam_stress":
        return ((-0.008 if left else 0.008 if right else 0.0), 0.0, 0.006)
    return (0.0, 0.0, 0.0)


def _motion_step_acceleration(panel_id: str, point: Vec3, state_id: str, step: int) -> Vec3:
    decay = max(0.0, 1.0 - step / 10.0)
    left = panel_id == "panel.sleeve.left"
    right = panel_id == "panel.sleeve.right"
    if state_id == "left_arm_raise" and left:
        return (-1.1 * decay, 2.4 * decay, 0.0)
    if state_id == "right_arm_raise" and right:
        return (1.1 * decay, 2.4 * decay, 0.0)
    if state_id == "moderate_gust":
        return (0.0, 0.0, 1.8 * decay)
    if state_id == "torso_twist":
        return (0.9 * point[2] * decay, 0.0, -0.9 * point[0] * decay)
    if state_id == "side_bend":
        return (0.8 * max(0.0, point[1] - 0.9) * decay, 0.0, 0.0)
    return (0.0, 0.0, 0.0)


def _bend_pairs(triangles: list[Tri]) -> list[tuple[int, int]]:
    edge_to_opposites: dict[tuple[int, int], list[int]] = {}
    for tri in triangles:
        a, b, c = tri
        for edge, opposite in [
            ((min(a, b), max(a, b)), c),
            ((min(b, c), max(b, c)), a),
            ((min(c, a), max(c, a)), b),
        ]:
            edge_to_opposites.setdefault(edge, []).append(opposite)
    pairs = []
    for opposites in edge_to_opposites.values():
        if len(opposites) == 2:
            pairs.append((opposites[0], opposites[1]))
    return pairs


def _triangle_edges(tri: Tri) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    return ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0]))


def _closest_point_on_segment(point: Vec3, a: Vec3, b: Vec3) -> Vec3:
    ab = sub(b, a)
    denom = max(1e-12, sum(component * component for component in ab))
    t = max(0.0, min(1.0, sum(sub(point, a)[i] * ab[i] for i in range(3)) / denom))
    return add(a, scale(ab, t))


def _energy_proxy(positions: list[Vec3], velocities: list[Vec3]) -> float:
    kinetic = sum(sum(component * component for component in velocity) for velocity in velocities)
    potential = sum(max(0.0, position[1]) for position in positions)
    return kinetic * 0.5 + potential * 0.01


def _rms(values: list[float]) -> float:
    if not values:
        return 0.0
    return sqrt(sum(value * value for value in values) / len(values))


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[index]


def _triangle_area2(vertices: list[Vec3], tri: Tri) -> float:
    a, b, c = vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]
    normal = cross(sub(b, a), sub(c, a))
    return _length(normal)


def _distance(a: Vec3, b: Vec3) -> float:
    return _length(sub(a, b))


def _weighted_point(left: Vec3, right: Vec3, weight: float) -> Vec3:
    return add(scale(left, 1.0 - weight), scale(right, weight))


def _distance_constraint_length(positions: list[Vec3], constraint: DistanceConstraint) -> float:
    a_next = constraint.a if constraint.a_next is None else constraint.a_next
    b_next = constraint.b if constraint.b_next is None else constraint.b_next
    return _distance(
        _weighted_point(positions[constraint.a], positions[a_next], constraint.a_weight),
        _weighted_point(positions[constraint.b], positions[b_next], constraint.b_weight),
    )


def _span_position_from_flat(
    positions: list[Vec3], offsets: list[int], span: dict[str, Any]
) -> Vec3:
    offset = offsets[int(span["meshIndex"])]
    current = offset + int(span["vertexIndex"])
    following = offset + int(span.get("nextVertexIndex", span["vertexIndex"]))
    return _weighted_point(
        positions[current], positions[following], float(span.get("interpolationWeight", 0.0))
    )


def _length(value: Vec3) -> float:
    return sqrt(sum(component * component for component in value))


def _dot(left: Vec3, right: Vec3) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _round(value: float) -> float:
    return round(float(value), 9)


def _vec3(value: Any) -> Vec3:
    return (float(value[0]), float(value[1]), float(value[2]))
