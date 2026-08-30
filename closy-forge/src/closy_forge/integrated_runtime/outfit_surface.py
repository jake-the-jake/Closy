from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any

from closy_forge.avatar_variation import (
    AvatarMeasurements,
    SyntheticAvatarCase,
    build_collision_samples,
    fit_avatar_patterns,
)
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.zeroone.intersection_manifest import SurfaceRepresentation, audit_surface

OUTFIT_SURFACE_PROFILE = "closy.layer_collision.canonical_surface_outfit.d0.v1"
SURFACE_SOLVER_VERSION = "closy.layer_collision.simultaneous_surface_projection.d0.v1"
SEGMENTS = 32
REGIONS = ("shoulder_chest", "chest", "waist", "hem")
REQUIRED_INTER_LAYER_CLEARANCE_METERS = 0.002
MINIMUM_BODY_CLEARANCE_METERS = 0.0025

Vec3 = tuple[float, float, float]
Tri = tuple[int, int, int]


@dataclass(frozen=True)
class CanonicalSurface:
    surface_id: str
    positions: tuple[Vec3, ...]
    triangles: tuple[Tri, ...]
    semantic_regions: tuple[str, ...]
    seam_vertex_ids: tuple[int, ...]
    opening_vertex_ids: tuple[int, ...]

    @property
    def identity(self) -> str:
        return sha256_bytes(canonical_dumps(_surface_record(self)).encode())


@dataclass(frozen=True)
class CanonicalOutfitCase:
    case_id: str
    avatar_authority_hash: str
    avatar_fit_digest: str
    body: CanonicalSurface
    inner_top: CanonicalSurface
    outer_overshirt: CanonicalSurface
    profile_identity: str
    outfit_surface_identity: str


def build_canonical_outfit_case() -> CanonicalOutfitCase:
    avatar_case = SyntheticAvatarCase(
        "avatar.integrated_outfit.baseline",
        AvatarMeasurements(),
        "baseline",
        (),
    )
    samples = build_collision_samples(avatar_case.measurements)
    fit = fit_avatar_patterns(avatar_case)
    rings = samples["rings"]
    body_rings = _resample_body_rings(rings)
    body = _surface_from_rings("avatar.synthetic.baseline", body_rings)
    inner_rings = [_offset_ring(ring, 0.0052) for ring in body_rings]
    outer_rings: list[list[Vec3]] = []
    for ring_index, ring in enumerate(body_rings):
        outer_ring: list[Vec3] = []
        for segment, point in enumerate(ring):
            # The authored alternating deficit deliberately creates a bounded contact witness.
            deficit = 0.0034 if (segment + ring_index * 3) % 8 in {0, 1} else 0.0
            outer_ring.append(_offset_point(point, 0.0084 - deficit))
        outer_rings.append(outer_ring)
    inner = _surface_from_rings("garment.inner_top", inner_rings)
    outer_surface = _surface_from_rings("garment.outer_overshirt", outer_rings)
    avatar_authority = sha256_bytes(
        canonical_dumps(
            {
                "measurementAuthority": fit.measurement_authority,
                "collisionBodyLinkage": fit.collision_body_linkage,
                "provenance": fit.provenance,
                "bodySurfaceIdentity": body.identity,
            }
        ).encode()
    )
    profile_identity = sha256_bytes(
        canonical_dumps(
            {
                "profile": OUTFIT_SURFACE_PROFILE,
                "solver": SURFACE_SOLVER_VERSION,
                "segments": SEGMENTS,
                "regions": list(REGIONS),
                "requiredClearanceMeters": REQUIRED_INTER_LAYER_CLEARANCE_METERS,
                "minimumBodyClearanceMeters": MINIMUM_BODY_CLEARANCE_METERS,
            }
        ).encode()
    )
    outfit_identity = sha256_bytes(
        canonical_dumps(
            {
                "avatarAuthorityHash": avatar_authority,
                "avatarFitDigest": fit.fit_digest,
                "body": body.identity,
                "inner": inner.identity,
                "outer": outer_surface.identity,
                "profileIdentity": profile_identity,
            }
        ).encode()
    )
    return CanonicalOutfitCase(
        case_id="outfit.synthetic_avatar.inner_top_outer_overshirt.d0.v1",
        avatar_authority_hash=avatar_authority,
        avatar_fit_digest=fit.fit_digest,
        body=body,
        inner_top=inner,
        outer_overshirt=outer_surface,
        profile_identity=profile_identity,
        outfit_surface_identity=outfit_identity,
    )


def run_canonical_outfit_surface_solve(case: CanonicalOutfitCase) -> dict[str, Any]:
    inner = [_vec3(point) for point in case.inner_top.positions]
    outer = [_vec3(point) for point in case.outer_overshirt.positions]
    initial = _metrics(case, inner, outer)
    initial_audit = _combined_audit(case, inner, outer, "initial")
    correction_count = 0
    for _ in range(12):
        for index, (inner_point, outer_point, body_point) in enumerate(
            zip(inner, outer, case.body.positions, strict=True)
        ):
            body_radius = hypot(body_point[0], body_point[2])
            inner_radius = hypot(inner_point[0], inner_point[2])
            outer_radius = hypot(outer_point[0], outer_point[2])
            minimum_inner = body_radius + MINIMUM_BODY_CLEARANCE_METERS
            if inner_radius < minimum_inner:
                inner[index] = _with_radius(inner_point, minimum_inner)
                inner_radius = minimum_inner
                correction_count += 1
            penetration = REQUIRED_INTER_LAYER_CLEARANCE_METERS - (outer_radius - inner_radius)
            if penetration > 0.0:
                inner_target = max(minimum_inner, inner_radius - penetration * 0.45)
                applied_inner = inner_radius - inner_target
                outer_target = outer_radius + (penetration - applied_inner)
                inner[index] = _with_radius(inner_point, inner_target)
                outer[index] = _with_radius(outer_point, outer_target)
                correction_count += 1
    final = _metrics(case, inner, outer)
    final_audit = _combined_audit(case, inner, outer, "final")
    topology_unchanged = (
        case.inner_top.triangles == case.outer_overshirt.triangles
        and len(inner) == len(case.inner_top.positions)
        and len(outer) == len(case.outer_overshirt.positions)
    )
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "profile": OUTFIT_SURFACE_PROFILE,
        "solverVersion": SURFACE_SOLVER_VERSION,
        "classification": "geometric_LayerCollision-D0_not_physical_cloth",
        "caseId": case.case_id,
        "identities": {
            "avatarAuthorityHash": case.avatar_authority_hash,
            "avatarFitDigest": case.avatar_fit_digest,
            "bodySurfaceIdentity": case.body.identity,
            "innerGarmentSurfaceIdentity": case.inner_top.identity,
            "outerGarmentSurfaceIdentity": case.outer_overshirt.identity,
            "layerProfileIdentity": case.profile_identity,
            "outfitSurfaceIdentity": case.outfit_surface_identity,
        },
        "layers": [
            {"layerId": case.inner_top.surface_id, "order": 10, "material": "cotton_jersey"},
            {
                "layerId": case.outer_overshirt.surface_id,
                "order": 20,
                "material": "lightweight_woven",
            },
        ],
        "surfaceExecution": {
            "actualIndexedTriangleSurfaces": True,
            "simultaneousProjection": True,
            "metadataOnly": False,
            "vertexCountPerGarment": len(inner),
            "triangleCountPerGarment": len(case.inner_top.triangles),
            "correctionCount": correction_count,
            "topologyUnchanged": topology_unchanged,
        },
        "initial": initial,
        "final": final,
        "intersectionAudit": {
            "classifierVersion": final_audit["classifierVersion"],
            "initialIntersections": initial_audit["intersectingPairCount"],
            "finalIntersections": final_audit["intersectingPairCount"],
            "initialWitnessHash": initial_audit["deterministicWitnessHash"],
            "finalWitnessHash": final_audit["deterministicWitnessHash"],
        },
        "semanticRegions": list(REGIONS),
        "openingAccessibility": {
            "neck": final["minimumClearanceBySemanticRegionMeters"]["shoulder_chest"] > 0.0,
            "hem": final["minimumClearanceBySemanticRegionMeters"]["hem"] > 0.0,
        },
        "seamOpeningPreservation": {
            "seamVertexInventoryPreserved": topology_unchanged,
            "openingVertexInventoryPreserved": topology_unchanged,
            "seamsOrOpeningsRewritten": False,
        },
        "truth": {
            "exactSyntheticAvatarFit": True,
            "phy1Passed": False,
            "physicalSimulation": False,
            "mobileOrGpuExecution": False,
            "privateOrLicensedBodyEvidence": False,
        },
    }
    result["integrity"] = {"reportHash": sha256_bytes(canonical_dumps(result).encode())}
    return result


def _resample_body_rings(rings: dict[str, Any]) -> list[list[Vec3]]:
    chest = [_vec3(point) for point in rings["chest"]][::2]
    waist = [_vec3(point) for point in rings["waist"]][::2]
    hips = [_vec3(point) for point in rings["hips"]][::2]
    shoulder = [(point[0] * 0.94, point[1] + 0.105, point[2]) for point in chest]
    hem = [(point[0] * 1.01, point[1] - 0.08, point[2]) for point in hips]
    return [shoulder, chest, waist, hem]


def _surface_from_rings(surface_id: str, rings: list[list[Vec3]]) -> CanonicalSurface:
    positions = tuple(point for ring in rings for point in ring)
    triangles: list[Tri] = []
    for ring in range(len(rings) - 1):
        for segment in range(SEGMENTS):
            next_segment = (segment + 1) % SEGMENTS
            lower = ring * SEGMENTS
            upper = (ring + 1) * SEGMENTS
            triangles.extend(
                (
                    (lower + segment, upper + segment, upper + next_segment),
                    (lower + segment, upper + next_segment, lower + next_segment),
                )
            )
    semantic = tuple(region for region in REGIONS for _ in range(SEGMENTS))
    seam = tuple(ring * SEGMENTS for ring in range(len(rings)))
    opening = tuple(range(SEGMENTS)) + tuple(
        range((len(rings) - 1) * SEGMENTS, len(rings) * SEGMENTS)
    )
    return CanonicalSurface(
        surface_id=surface_id,
        positions=positions,
        triangles=tuple(triangles),
        semantic_regions=semantic,
        seam_vertex_ids=seam,
        opening_vertex_ids=opening,
    )


def _offset_ring(ring: list[Vec3], amount: float) -> list[Vec3]:
    return [_offset_point(point, amount) for point in ring]


def _offset_point(point: Vec3, amount: float) -> Vec3:
    radius = hypot(point[0], point[2])
    return _with_radius(point, radius + amount)


def _with_radius(point: Vec3, radius: float) -> Vec3:
    current = hypot(point[0], point[2])
    if current <= 1.0e-12:
        return (radius, point[1], 0.0)
    scale = radius / current
    return (point[0] * scale, point[1], point[2] * scale)


def _metrics(case: CanonicalOutfitCase, inner: list[Vec3], outer: list[Vec3]) -> dict[str, Any]:
    penetrations: list[float] = []
    clearances: dict[str, list[float]] = {region: [] for region in REGIONS}
    body_clearances: list[float] = []
    inversions = 0
    for index, (body_point, inner_point, outer_point) in enumerate(
        zip(case.body.positions, inner, outer, strict=True)
    ):
        body_radius = hypot(body_point[0], body_point[2])
        inner_radius = hypot(inner_point[0], inner_point[2])
        outer_radius = hypot(outer_point[0], outer_point[2])
        gap = outer_radius - inner_radius
        region = case.inner_top.semantic_regions[index]
        clearances[region].append(gap)
        body_clearances.append(inner_radius - body_radius)
        penetrations.append(max(0.0, REQUIRED_INTER_LAYER_CLEARANCE_METERS - gap))
        inversions += int(outer_radius <= inner_radius)
    unresolved = sum(value > 1.0e-10 for value in penetrations)
    return {
        "contactCount": unresolved,
        "maximumPenetrationDepthMeters": round(max(penetrations, default=0.0), 12),
        "minimumClearanceBySemanticRegionMeters": {
            region: round(min(values), 12) for region, values in clearances.items()
        },
        "minimumBodyClearanceMeters": round(min(body_clearances), 12),
        "unresolvedContactCount": unresolved,
        "orderingInversionCount": inversions,
    }


def _combined_audit(
    case: CanonicalOutfitCase,
    inner: list[Vec3],
    outer: list[Vec3],
    stage: str,
) -> dict[str, Any]:
    offset = len(inner)
    triangles = [*case.inner_top.triangles]
    triangles.extend(
        (triangle[0] + offset, triangle[1] + offset, triangle[2] + offset)
        for triangle in case.outer_overshirt.triangles
    )
    lineage = [
        {"layerId": case.inner_top.surface_id, "triangle": index, "stage": stage}
        for index in range(len(case.inner_top.triangles))
    ]
    lineage.extend(
        {"layerId": case.outer_overshirt.surface_id, "triangle": index, "stage": stage}
        for index in range(len(case.outer_overshirt.triangles))
    )
    return audit_surface(
        SurfaceRepresentation(
            representation_id=f"{case.case_id}:{stage}",
            positions=[*inner, *outer],
            triangles=triangles,
            logical_vertex_ids=list(range(len(inner) + len(outer))),
            triangle_lineage=lineage,
        )
    )


def _surface_record(surface: CanonicalSurface) -> dict[str, Any]:
    return {
        "surfaceId": surface.surface_id,
        "positions": surface.positions,
        "triangles": surface.triangles,
        "semanticRegions": surface.semantic_regions,
        "seamVertexIds": surface.seam_vertex_ids,
        "openingVertexIds": surface.opening_vertex_ids,
    }


def _vec3(value: object) -> Vec3:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise ValueError("integrated_surface_vec3_invalid")
    return (float(value[0]), float(value[1]), float(value[2]))
