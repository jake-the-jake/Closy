from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from closy_forge.geometry.mesh_model import Vec3, cross, normalize, sub
from closy_forge.simulation.self_collision import (
    SelfCollisionSettings,
    TriangleRef,
    _closest_point_and_barycentric_on_triangle,
    broad_phase_candidates,
    narrow_phase_contacts,
)
from closy_forge.zeroone.dynamic_oracle import triangles_intersect


@dataclass(frozen=True)
class Witness:
    pair: tuple[int, int]
    kind: str
    distance: float
    depth: float
    normal: Vec3
    coefficients: tuple[tuple[int, float], ...]
    position: Vec3
    correction_allowed: bool = True


def contacts(
    positions: list[Vec3],
    triangles: list[TriangleRef],
    triangle_layers: list[str],
    materials: dict[str, tuple[float, float]],
    order: list[tuple[str, str, float, float, bool]],
) -> tuple[list[Witness], dict[str, Any]]:
    """Two-sided thickness queries, not an inside/outside test for open cloth.

    Frozen grid and VF/EE kernels are reused without changing their old entry points.
    The additional triangle crossing test catches edge-through-face intersections
    far from vertices/edges. Coplanar overlap is explicitly retained as a witness.
    Regional order NEVER suppresses detection, only the permitted correction.
    """
    threshold = max(t / 2 + c for t, c in materials.values()) * 2
    # Broad-phase expansion is deliberately larger than some material-pair
    # clearances. With no witness only the smallest narrow-phase pair clearance
    # is a valid global lower bound, not the broad-phase search distance.
    values = list(materials.values())
    separation_lower_bound = min(
        (
            (ta + tb) / 2 + max(ca, cb)
            for i, (ta, ca) in enumerate(values)
            for tb, cb in values[i + 1 :]
        ),
        default=0.0,
    )
    settings = SelfCollisionSettings(thickness_meters=threshold, clearance_meters=0)
    candidates = [
        (a, b)
        for a, b in broad_phase_candidates(positions, triangles, settings, set())
        if triangle_layers[a] != triangle_layers[b]
    ]
    witnesses = []
    orders_violated = 0
    for a, b in candidates:
        ta, tb = triangles[a], triangles[b]
        la, lb = triangle_layers[a], triangle_layers[b]
        pa = tuple(positions[i] for i in ta.vertex_indices)
        pb = tuple(positions[i] for i in tb.vertex_indices)
        center: Vec3 = tuple(sum(p[i] for p in (*pa, *pb)) / 6 for i in range(3))  # type: ignore[assignment]
        selected = [o for o in order if {o[0], o[1]} == {la, lb} and o[2] <= center[1] <= o[3]]
        allowed = bool(selected) and all(o[4] for o in selected)
        ta_size, ca = materials[la]
        tb_size, cb = materials[lb]
        distance = (ta_size + tb_size) / 2 + max(ca, cb)
        local_settings = SelfCollisionSettings(thickness_meters=distance, clearance_meters=0)
        # Two local refs avoid recomputing broad-phase arrays for the whole outfit.
        raw = narrow_phase_contacts(positions, [ta, tb], [(0, 1)], local_settings)
        outer = selected[-1][1] if selected else max(la, lb)
        for item in raw:
            normal = item.normal
            positive = next(i for i, w in item.gradient_coefficients if w > 0)
            positive_layer = la if positive in ta.vertex_indices else lb
            direction = 1 if positive_layer == outer else -1
            if direction * (normal[0] * center[0] + normal[2] * center[2]) < 0:
                normal = tuple(-v for v in normal)  # type: ignore[assignment]
            witnesses.append(
                Witness(
                    (a, b),
                    item.contact_kind,
                    item.distance_meters,
                    item.penetration_meters,
                    normal,
                    item.gradient_coefficients,
                    center,
                    allowed,
                )
            )
        na = normalize(cross(sub(pa[1], pa[0]), sub(pa[2], pa[0])))
        nb = normalize(cross(sub(pb[1], pb[0]), sub(pb[2], pb[0])))
        coplanar = (
            math.dist(cross(na, nb), (0, 0, 0)) < 1e-7
            and abs(sum(na[i] * (pb[0][i] - pa[0][i]) for i in range(3))) < 1e-7
        )
        coincident = False
        if coplanar:
            for left, right in ((pa, pb), (pb, pa)):
                centroid: Vec3 = tuple(sum(p[i] for p in left) / 3 for i in range(3))  # type: ignore[assignment]
                point, _ = _closest_point_and_barycentric_on_triangle(centroid, *right)
                coincident = coincident or math.dist(centroid, point) < 1e-8
        if coincident or triangles_intersect(pa, pb):
            # Interval deficit along a local face normal is a conservative projection
            # distance, NOT a calibrated cloth volume-penetration measurement.
            normal = na
            radial_dot = normal[0] * center[0] + normal[2] * center[2]
            if radial_dot < 0:
                normal = tuple(-v for v in normal)  # type: ignore[assignment]
            sign = 1 if la == outer else -1
            inside, outside = (pb, pa) if la == outer else (pa, pb)

            def dot(p: Vec3, normal: Vec3 = normal) -> float:
                return sum(p[i] * normal[i] for i in range(3))

            deficit = max(distance, max(map(dot, inside)) - min(map(dot, outside)) + distance)
            coefficients = tuple((i, sign / 3) for i in ta.vertex_indices) + tuple(
                (i, -sign / 3) for i in tb.vertex_indices
            )
            witnesses.append(
                Witness(
                    (a, b),
                    "coplanar_overlap" if coplanar else "triangle_crossing",
                    0,
                    deficit,
                    normal,
                    coefficients,
                    center,
                    allowed,
                )
            )
        # Order is local to actual near-contact coverage, not a global radius assertion.
        if selected and raw:
            ca3 = tuple(sum(p[i] for p in pa) / 3 for i in range(3))
            cb3 = tuple(sum(p[i] for p in pb) / 3 for i in range(3))
            radial = normalize((center[0], 0, center[2]))
            delta = sum((ca3[i] - cb3[i]) * radial[i] for i in range(3))
            orders_violated += int((delta > 1e-5) != (la == selected[-1][1]))
    counts = {k: sum(w.kind == k for w in witnesses) for k in sorted({w.kind for w in witnesses})}
    return witnesses, {
        "candidatePairs": len(candidates),
        "contactCount": len(witnesses),
        "kinds": counts,
        "maximumThicknessDeficitM": max((w.depth for w in witnesses), default=0),
        "depthScope": "proximity_thickness_deficit_or_crossing_normal_interval_deficit",
        "minimumQueriedSeparationM": min(
            (w.distance for w in witnesses), default=separation_lower_bound
        ),
        "noContactSeparationIsLowerBound": not witnesses,
        "crossings": sum(w.kind in {"triangle_crossing", "coplanar_overlap"} for w in witnesses),
        "layerOrderViolations": orders_violated,
        "policyBlockedContacts": sum(not w.correction_allowed for w in witnesses),
    }
