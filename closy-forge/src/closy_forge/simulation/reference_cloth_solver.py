from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet, Tri, Vec3, add, cross, scale, sub
from closy_forge.package_io.hashing import geometry_content_hash, topology_hash

SOLVER_VERSION = "closy.reference_xpbd_cpu.v1.1"
NECK_BAND_SEAM_TARGET_LENGTH_METERS = 0.02


@dataclass(frozen=True)
class SettleSettings:
    time_step_seconds: float = 1.0 / 60.0
    step_count: int = 35
    solver_iterations: int = 6
    gravity_m_s2: float = -9.81
    damping_ratio: float = 0.18
    collision_clearance_m: float = 0.006
    stretch_stiffness: float = 0.42
    seam_stiffness: float = 0.96
    bend_stiffness: float = 0.08
    support_stiffness: float = 0.03


@dataclass(frozen=True)
class DistanceConstraint:
    a: int
    b: int
    rest_length: float
    stiffness: float
    kind: str
    entity_id: str


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


def settle_reference_cloth(
    rest_mesh: MeshSet,
    seam_constraints: dict[str, Any],
    avatar_contract: dict[str, Any],
    material: dict[str, Any],
    *,
    settings: SettleSettings | None = None,
) -> SettleResult:
    """Run a deterministic CPU reference settle pass for the fixed T-shirt fixture.

    This is deliberately a conservative MVP solver. It exercises real cloth-style constraints and
    body collision, but does not claim self-collision or production-grade drape fidelity.
    """

    active_settings = settings or SettleSettings(
        damping_ratio=float(material.get("dampingRatio", SettleSettings.damping_ratio)),
    )
    flat = flatten_mesh(rest_mesh)
    positions = list(flat.positions)
    previous = list(flat.positions)
    velocities = [(0.0, 0.0, 0.0) for _ in positions]
    constraints = _build_distance_constraints(
        rest_mesh, seam_constraints, flat.mesh_offsets, active_settings
    )
    supports = _build_support_constraints(rest_mesh, flat.mesh_offsets, active_settings)
    primitives = list(avatar_contract.get("collisionPrimitives", []))

    energy_history: list[float] = []
    collision_events = 0
    dt = active_settings.time_step_seconds
    for _step in range(active_settings.step_count):
        for index, velocity in enumerate(velocities):
            previous[index] = positions[index]
            velocities[index] = (
                velocity[0],
                (velocity[1] + active_settings.gravity_m_s2 * dt)
                * (1.0 - active_settings.damping_ratio * 0.08),
                velocity[2],
            )
            positions[index] = add(positions[index], scale(velocities[index], dt))

        for _iteration in range(active_settings.solver_iterations):
            for constraint in constraints:
                _solve_distance(positions, constraint)
            for support in supports:
                _solve_support(positions, support)
            collision_events += _project_collisions(
                positions, primitives, active_settings.collision_clearance_m
            )

        for index, position in enumerate(positions):
            velocities[index] = scale(sub(position, previous[index]), 1.0 / dt)
        energy_history.append(_energy_proxy(positions, velocities))

    collision_events += _project_collisions(
        positions, primitives, active_settings.collision_clearance_m
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
    )
    return SettleResult(rest_mesh, settled_mesh, diagnostics, active_settings)


def flatten_mesh(meshset: MeshSet) -> FlattenedMesh:
    positions: list[Vec3] = []
    offsets: list[int] = []
    for mesh in meshset.meshes:
        offsets.append(len(positions))
        positions.extend(mesh.vertices)
    return FlattenedMesh(positions, offsets)


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
                constraints.append(
                    DistanceConstraint(
                        a,
                        b,
                        _distance(mesh.vertices[local_a], mesh.vertices[local_b]),
                        settings.stretch_stiffness,
                        "stretch",
                        f"{mesh.panel_id}:{local_a}-{local_b}",
                    )
                )
        for a, b in _bend_pairs(mesh.triangles):
            constraints.append(
                DistanceConstraint(
                    offsets[mesh_index] + a,
                    offsets[mesh_index] + b,
                    _distance(mesh.vertices[a], mesh.vertices[b]),
                    settings.bend_stiffness,
                    "bend",
                    f"{mesh.panel_id}:{a}-{b}",
                )
            )

    for seam_doc in seam_constraints.get("constraints", []):
        span_a = seam_doc["spanA"]
        span_b = seam_doc["spanB"]
        a = offsets[int(span_a["meshIndex"])] + int(span_a["vertexIndex"])
        b = offsets[int(span_b["meshIndex"])] + int(span_b["vertexIndex"])
        panel_a = str(span_a["panelId"])
        panel_b = str(span_b["panelId"])
        target_length = 0.0
        if "panel.neck_band" in {panel_a, panel_b}:
            mesh_a = meshset.meshes[int(span_a["meshIndex"])]
            mesh_b = meshset.meshes[int(span_b["meshIndex"])]
            rest_distance = _distance(
                mesh_a.vertices[int(span_a["vertexIndex"])],
                mesh_b.vertices[int(span_b["vertexIndex"])],
            )
            target_length = min(NECK_BAND_SEAM_TARGET_LENGTH_METERS, rest_distance * 0.50)
        constraints.append(
            DistanceConstraint(
                a,
                b,
                target_length,
                settings.seam_stiffness,
                "seam",
                str(seam_doc["seamId"]),
            )
        )
    return constraints


def _build_support_constraints(
    meshset: MeshSet, offsets: list[int], settings: SettleSettings
) -> list[SupportConstraint]:
    supports: list[SupportConstraint] = []
    for mesh_index, mesh in enumerate(meshset.meshes):
        for vertex_index, vertex in enumerate(mesh.vertices):
            if mesh.panel_id == "panel.neck_band" or vertex[1] >= 1.345:
                supports.append(
                    SupportConstraint(
                        offsets[mesh_index] + vertex_index,
                        vertex,
                        settings.support_stiffness,
                        f"support.{mesh.panel_id}.{vertex_index}",
                    )
                )
    return supports


def _solve_distance(positions: list[Vec3], constraint: DistanceConstraint) -> None:
    a = positions[constraint.a]
    b = positions[constraint.b]
    delta = sub(b, a)
    length = _length(delta)
    if length <= 1e-10:
        return
    correction = (length - constraint.rest_length) * constraint.stiffness * 0.5
    direction = scale(delta, 1.0 / length)
    positions[constraint.a] = add(a, scale(direction, correction))
    positions[constraint.b] = add(b, scale(direction, -correction))


def _solve_support(positions: list[Vec3], support: SupportConstraint) -> None:
    current = positions[support.index]
    positions[support.index] = add(current, scale(sub(support.target, current), support.stiffness))


def _project_collisions(
    positions: list[Vec3], primitives: list[dict[str, Any]], clearance: float
) -> int:
    events = 0
    for index, position in enumerate(positions):
        projected = position
        for primitive in primitives:
            candidate, penetrated = _project_primitive(projected, primitive, clearance)
            if penetrated:
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
) -> dict[str, Any]:
    flat_settled = flatten_mesh(settled_mesh)
    seam_residuals = [
        abs(_distance(flat_settled.positions[c.a], flat_settled.positions[c.b]) - c.rest_length)
        for c in constraints
        if c.kind == "seam"
    ]
    strains = [
        abs(
            _distance(flat_settled.positions[c.a], flat_settled.positions[c.b]) / c.rest_length
            - 1.0
        )
        for c in constraints
        if c.kind == "stretch" and c.rest_length > 1e-8
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
    convergence = (
        "converged"
        if max_seam <= 0.12
        and rms_seam <= 0.035
        and max_penetration <= 0.012
        and p95_strain <= 2.0
        and mean_strain <= 2.0
        and inverted == 0
        and nonfinite == 0
        else "failed"
    )
    return {
        "schemaVersion": 1,
        "solverVersion": SOLVER_VERSION,
        "backend": "deterministic_cpu_reference_xpbd",
        "convergenceState": convergence,
        "settings": {
            "timeStepSeconds": settings.time_step_seconds,
            "stepCount": settings.step_count,
            "solverIterations": settings.solver_iterations,
            "gravityMS2": settings.gravity_m_s2,
            "dampingRatio": settings.damping_ratio,
            "collisionClearanceMeters": settings.collision_clearance_m,
            "stretchStiffness": settings.stretch_stiffness,
            "seamStiffness": settings.seam_stiffness,
            "bendStiffness": settings.bend_stiffness,
            "supportStiffness": settings.support_stiffness,
            "constraintOrder": "mesh_stretch_then_bend_then_seams_then_support_then_collision",
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
        "energyHistory": energy_history,
        "selfCollision": {
            "available": False,
            "reason": "not_implemented_in_reference_cpu_solver_v1",
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
        a = offsets[int(span_a["meshIndex"])] + int(span_a["vertexIndex"])
        b = offsets[int(span_b["meshIndex"])] + int(span_b["vertexIndex"])
        residuals.append(_distance(positions[a], positions[b]))
    return residuals


def _seam_warnings(
    seam_constraints: dict[str, Any], residuals: list[float]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for seam_doc, residual in zip(seam_constraints.get("constraints", []), residuals, strict=False):
        if residual > 0.12:
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


def _length(value: Vec3) -> float:
    return sqrt(sum(component * component for component in value))


def _vec3(value: Any) -> Vec3:
    return (float(value[0]), float(value[1]), float(value[2]))
