from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from closy_forge.geometry.mesh_model import MeshSet, Tri, Vec3, add, cross, scale, sub
from closy_forge.simulation import reference_cloth_solver as legacy

from .geometry import require_mesh


@dataclass(frozen=True)
class GuardedSettings:
    steps: int = 35
    iterations: int = 6
    minimum_rest_area_ratio: float = 0.02
    maximum_backtracks: int = 24


DEFAULT_SETTINGS = GuardedSettings()


def guarded_update(
    previous: list[Vec3],
    proposed: list[Vec3],
    triangles: list[Tri],
    minimum_areas: list[float],
    *,
    backtracks: int = 24,
) -> tuple[list[Vec3], int]:
    """Backtrack the numerical update, never delete/export-filter a collapsed face.

    Every accepted substep preserves positive area and local orientation. Comparing
    consecutive normals permits real rotations; an absolute rest-normal test does not.
    """
    normals = [
        cross(sub(previous[b], previous[a]), sub(previous[c], previous[a])) for a, b, c in triangles
    ]
    for attempt in range(backtracks + 1):
        alpha = 2.0**-attempt
        candidate = [
            add(a, scale(sub(b, a), alpha)) for a, b in zip(previous, proposed, strict=True)
        ]
        valid = all(math.isfinite(n) for p in candidate for n in p)
        if valid:
            for (a, b, c), old, minimum in zip(triangles, normals, minimum_areas, strict=True):
                normal = cross(sub(candidate[b], candidate[a]), sub(candidate[c], candidate[a]))
                if (
                    sum(n * n for n in normal) < (2 * minimum) ** 2
                    or sum(x * y for x, y in zip(old, normal, strict=True)) <= 0
                ):
                    valid = False
                    break
        if valid:
            return candidate, attempt
    return list(previous), backtracks + 1


def settle_family(
    rest: MeshSet,
    seams: dict[str, Any],
    avatar: dict[str, Any],
    *,
    settings: GuardedSettings = DEFAULT_SETTINGS,
) -> tuple[MeshSet, dict[str, Any]]:
    """Versioned numerical lane reusing immutable V2 XPBD constraint primitives.

    No old import/default is redirected. Seam, stretch, support and body projections
    remain active. Self-collision and physical convergence are NOT claimed here.
    """
    require_mesh(rest, family="all_family", stage="rest")
    flat = legacy.flatten_mesh(rest)
    triangles = [
        tuple(i + offset for i in triangle)
        for mesh, offset in zip(rest.meshes, flat.mesh_offsets, strict=True)
        for triangle in mesh.triangles
    ]
    typed_triangles: list[Tri] = [(t[0], t[1], t[2]) for t in triangles]
    minimum = []
    for a, b, c in typed_triangles:
        normal = cross(
            sub(flat.positions[b], flat.positions[a]), sub(flat.positions[c], flat.positions[a])
        )
        minimum.append(
            max(1e-10, math.sqrt(sum(n * n for n in normal)) / 2 * settings.minimum_rest_area_ratio)
        )
    config = legacy.SettleSettings()
    constraints = legacy._build_distance_constraints(rest, seams, flat.mesh_offsets, config)
    supports = legacy._build_support_constraints(rest, flat.mesh_offsets, config)
    masses = legacy._particle_inverse_masses(rest, config.surface_density_kg_m2)
    positions = list(flat.positions)
    velocity = [(0.0, 0.0, 0.0) for _ in positions]
    incident: list[list[int]] = [[] for _ in positions]
    for index, triangle in enumerate(typed_triangles):
        for vertex in triangle:
            incident[vertex].append(index)
    backtrack_count = 0
    rejected = 0
    dt = config.time_step_seconds
    for _step in range(settings.steps):
        old_step = list(positions)
        for constraint in constraints:
            constraint.lagrange_multiplier = 0
        for iteration in range(settings.iterations):
            previous = list(positions)
            if iteration == 0:
                proposed = [
                    add(p, add(scale(v, dt), (0.0, config.gravity_m_s2 * dt * dt, 0.0)))
                    for p, v in zip(positions, velocity, strict=True)
                ]
                positions, count = guarded_update(previous, proposed, typed_triangles, minimum)
                backtrack_count += count
            for constraint in constraints:
                if constraint.kind != "seam":
                    saved = {
                        i: positions[i]
                        for i in (constraint.a, constraint.b, constraint.a_next, constraint.b_next)
                        if i is not None
                    }
                    legacy._solve_distance(positions, masses, constraint, dt)
                    backtrack_count += _guard_local(
                        positions, saved, typed_triangles, incident, minimum
                    )
            for support in supports:
                saved = {support.index: positions[support.index]}
                legacy._solve_support(positions, support)
                backtrack_count += _guard_local(
                    positions, saved, typed_triangles, incident, minimum
                )
            proposed = list(positions)
            legacy._project_collisions(
                proposed,
                list(previous),
                avatar.get("collisionPrimitives", []),
                config.collision_clearance_m,
                config.friction_coefficient,
                config.restitution_coefficient,
                dt,
            )
            for index, target in enumerate(proposed):
                if target != positions[index]:
                    saved = {index: positions[index]}
                    positions[index] = target
                    backtrack_count += _guard_local(
                        positions, saved, typed_triangles, incident, minimum
                    )
            for constraint in constraints:
                if constraint.kind == "seam":
                    saved = {
                        i: positions[i]
                        for i in (constraint.a, constraint.b, constraint.a_next, constraint.b_next)
                        if i is not None
                    }
                    legacy._solve_distance(positions, masses, constraint, dt)
                    count = _guard_local(positions, saved, typed_triangles, incident, minimum)
                    backtrack_count += count
                    rejected += int(count > settings.maximum_backtracks)
        velocity = [
            scale(sub(p, old), 0.8 / dt) for p, old in zip(positions, old_step, strict=True)
        ]
    result = legacy.replace_mesh_positions(rest, positions, flat.mesh_offsets)
    residuals = [
        abs(legacy._distance_constraint_length(positions, c) - c.rest_length)
        for c in constraints
        if c.kind == "seam"
    ]
    return result, {
        "solverVersion": "closy.guarded_family_settling.development.v1",
        "steps": settings.steps,
        "iterations": settings.iterations,
        "minimumRestAreaRatio": settings.minimum_rest_area_ratio,
        "backtrackCount": backtrack_count,
        "rejectedUpdates": rejected,
        "seamConstraintCount": len(residuals),
        "maximumSeamResidualM": max(residuals, default=0.0),
        "physicalConvergenceClaimed": False,
        "selfCollisionExecuted": False,
        "canonicalTopologyChanged": False,
    }


def _guard_local(
    positions: list[Vec3],
    saved: dict[int, Vec3],
    triangles: list[Tri],
    incident: list[list[int]],
    minimum: list[float],
) -> int:
    affected = sorted({t for vertex in saved for t in incident[vertex]})
    proposed = {i: positions[i] for i in saved}
    normals = {}
    for index in affected:
        a, b, c = (saved.get(i, positions[i]) for i in triangles[index])
        normals[index] = cross(sub(b, a), sub(c, a))
    for attempt in range(25):
        for i, old in saved.items():
            positions[i] = add(old, scale(sub(proposed[i], old), 2.0**-attempt))
        valid = True
        for index in affected:
            a, b, c = (positions[i] for i in triangles[index])
            normal = cross(sub(b, a), sub(c, a))
            area2 = sum(n * n for n in normal)
            if (
                not math.isfinite(area2)
                or area2 < (2 * minimum[index]) ** 2
                or sum(x * y for x, y in zip(normals[index], normal, strict=True)) <= 0
            ):
                valid = False
                break
        if valid:
            return attempt
    for i, old in saved.items():
        positions[i] = old
    return 25
