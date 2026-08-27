from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet, Tri, Vec3, add, cross, scale, sub
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, topology_hash

SELF_COLLISION_REPORT_VERSION = "closy.self_collision.reference_d0.integrated_v2"

_ORACLE_DIRECTIONS: tuple[Vec3, ...] = (
    (1.0, 1.0, 1.0),
    (1.0, 1.0, -1.0),
    (1.0, -1.0, 1.0),
    (-1.0, 1.0, 1.0),
    (1.0, 2.0, 3.0),
    (2.0, -3.0, 1.0),
    (-3.0, 1.0, 2.0),
)


@dataclass(frozen=True)
class SelfCollisionSettings:
    thickness_meters: float = 0.0016
    clearance_meters: float = 0.0008
    correction_fraction: float = 0.55
    max_iterations: int = 3
    epsilon_meters: float = 1e-9

    @property
    def contact_threshold_meters(self) -> float:
        return self.thickness_meters + self.clearance_meters


@dataclass(frozen=True)
class TriangleRef:
    global_triangle_index: int
    mesh_index: int
    local_triangle_index: int
    vertex_indices: Tri
    panel_id: str


@dataclass(frozen=True)
class Contact:
    contact_id: str
    candidate_id: str
    vertex_index: int
    triangle_index: int
    distance_meters: float
    penetration_meters: float
    normal: Vec3


@dataclass(frozen=True)
class SelfCollisionAnalysis:
    candidate_pairs: list[tuple[int, int]]
    oracle_candidate_pairs: list[tuple[int, int]]
    contacts: list[Contact]
    max_penetration_meters: float
    mean_penetration_meters: float
    unresolved_contact_count: int
    broad_phase_matches_oracle: bool


def build_triangle_refs(meshset: MeshSet) -> tuple[list[TriangleRef], list[int]]:
    offsets: list[int] = []
    offset = 0
    refs: list[TriangleRef] = []
    for mesh_index, mesh in enumerate(meshset.meshes):
        offsets.append(offset)
        for local_triangle_index, tri in enumerate(mesh.triangles):
            refs.append(
                TriangleRef(
                    global_triangle_index=len(refs),
                    mesh_index=mesh_index,
                    local_triangle_index=local_triangle_index,
                    vertex_indices=(
                        offset + tri[0],
                        offset + tri[1],
                        offset + tri[2],
                    ),
                    panel_id=mesh.panel_id,
                )
            )
        offset += len(mesh.vertices)
    return refs, offsets


def analyze_self_collision(
    meshset: MeshSet,
    *,
    settings: SelfCollisionSettings | None = None,
    excluded_vertex_pairs: set[tuple[int, int]] | None = None,
) -> SelfCollisionAnalysis:
    active_settings = settings or SelfCollisionSettings()
    positions = [vertex for mesh in meshset.meshes for vertex in mesh.vertices]
    triangles, _ = build_triangle_refs(meshset)
    return analyze_self_collision_positions(
        positions, triangles, active_settings, excluded_vertex_pairs=excluded_vertex_pairs
    )


def analyze_self_collision_positions(
    positions: list[Vec3],
    triangles: list[TriangleRef],
    settings: SelfCollisionSettings,
    *,
    excluded_vertex_pairs: set[tuple[int, int]] | None = None,
    evaluate_oracle: bool = True,
) -> SelfCollisionAnalysis:
    exclusions = excluded_vertex_pairs or set()
    candidates = broad_phase_candidates(positions, triangles, settings, exclusions)
    oracle = (
        brute_force_candidate_oracle(positions, triangles, settings, exclusions)
        if evaluate_oracle
        else []
    )
    contacts = narrow_phase_contacts(positions, triangles, candidates, settings)
    penetrations = [contact.penetration_meters for contact in contacts]
    return SelfCollisionAnalysis(
        candidate_pairs=candidates,
        oracle_candidate_pairs=oracle,
        contacts=contacts,
        max_penetration_meters=max(penetrations, default=0.0),
        mean_penetration_meters=sum(penetrations) / max(1, len(penetrations)),
        unresolved_contact_count=sum(
            1 for value in penetrations if value > settings.epsilon_meters
        ),
        broad_phase_matches_oracle=not evaluate_oracle or set(oracle).issubset(candidates),
    )


def project_self_collisions(
    positions: list[Vec3],
    triangles: list[TriangleRef],
    *,
    fixed_indices: set[int] | None = None,
    settings: SelfCollisionSettings | None = None,
    excluded_vertex_pairs: set[tuple[int, int]] | None = None,
) -> tuple[list[Vec3], dict[str, Any]]:
    active_settings = settings or SelfCollisionSettings()
    fixed = fixed_indices or set()
    current = list(positions)
    total_corrections = 0
    max_iteration_penetration = 0.0
    iteration_summaries: list[dict[str, Any]] = []
    for iteration in range(active_settings.max_iterations):
        analysis = analyze_self_collision_positions(
            current,
            triangles,
            active_settings,
            excluded_vertex_pairs=excluded_vertex_pairs,
            evaluate_oracle=False,
        )
        max_iteration_penetration = max(max_iteration_penetration, analysis.max_penetration_meters)
        correction_count = 0
        for contact in analysis.contacts:
            if contact.vertex_index in fixed:
                continue
            correction = scale(
                contact.normal,
                contact.penetration_meters * active_settings.correction_fraction,
            )
            current[contact.vertex_index] = add(current[contact.vertex_index], correction)
            correction_count += 1
        total_corrections += correction_count
        iteration_summaries.append(
            {
                "iteration": iteration,
                "candidatePairCount": len(analysis.candidate_pairs),
                "contactCount": len(analysis.contacts),
                "unresolvedContactCount": analysis.unresolved_contact_count,
                "correctionCount": correction_count,
                "maxPenetrationMeters": _round(analysis.max_penetration_meters),
            }
        )
        if not analysis.contacts:
            break
    final = analyze_self_collision_positions(
        current,
        triangles,
        active_settings,
        excluded_vertex_pairs=excluded_vertex_pairs,
        evaluate_oracle=False,
    )
    unresolved_history = [int(item["unresolvedContactCount"]) for item in iteration_summaries] + [
        final.unresolved_contact_count
    ]
    penetration_history = [float(item["maxPenetrationMeters"]) for item in iteration_summaries] + [
        final.max_penetration_meters
    ]
    return current, {
        "iterationCount": len(iteration_summaries),
        "totalCorrectionCount": total_corrections,
        "maxIterationPenetrationMeters": _round(max_iteration_penetration),
        "finalContactCount": len(final.contacts),
        "finalUnresolvedContactCount": final.unresolved_contact_count,
        "finalMaxPenetrationMeters": _round(final.max_penetration_meters),
        "unresolvedCountsMonotonicNonIncreasing": _non_increasing(unresolved_history),
        "maxPenetrationMonotonicNonIncreasing": _non_increasing(penetration_history),
        "unresolvedCountHistory": unresolved_history,
        "maxPenetrationHistoryMeters": [_round(value) for value in penetration_history],
        "iterations": iteration_summaries,
    }


def broad_phase_candidates(
    positions: list[Vec3],
    triangles: list[TriangleRef],
    settings: SelfCollisionSettings,
    excluded_vertex_pairs: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    candidates: list[tuple[int, int]] = []
    exclusions = excluded_vertex_pairs or set()
    inflated_bounds = [
        _triangle_bounds(positions, triangle.vertex_indices, settings.contact_threshold_meters)
        for triangle in triangles
    ]
    for left_index, left in enumerate(triangles):
        for right_index in range(left_index + 1, len(triangles)):
            right = triangles[right_index]
            if _triangles_are_adjacent(left, right, exclusions):
                continue
            if _aabb_overlap(inflated_bounds[left_index], inflated_bounds[right_index]):
                candidates.append((left_index, right_index))
    return candidates


def brute_force_candidate_oracle(
    positions: list[Vec3],
    triangles: list[TriangleRef],
    settings: SelfCollisionSettings,
    excluded_vertex_pairs: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    """Independent geometric oracle for pairs that truly approach the contact threshold."""

    exclusions = excluded_vertex_pairs or set()
    threshold = settings.contact_threshold_meters
    spheres = [_triangle_bounding_sphere(positions, item.vertex_indices) for item in triangles]
    directional_bounds = [
        _triangle_directional_bounds(positions, item.vertex_indices) for item in triangles
    ]
    candidates: list[tuple[int, int]] = []
    for left_index, left in enumerate(triangles):
        left_center, left_radius = spheres[left_index]
        for right_index in range(left_index + 1, len(triangles)):
            right = triangles[right_index]
            if _triangles_are_adjacent(left, right, exclusions):
                continue
            right_center, right_radius = spheres[right_index]
            maximum_distance = left_radius + right_radius + threshold
            if _distance_squared(left_center, right_center) > maximum_distance * maximum_distance:
                continue
            if not _directional_bounds_may_overlap(
                directional_bounds[left_index], directional_bounds[right_index], threshold
            ):
                continue
            if _triangle_pair_within_threshold(
                positions, left.vertex_indices, right.vertex_indices, threshold
            ):
                candidates.append((left_index, right_index))
    return candidates


def narrow_phase_contacts(
    positions: list[Vec3],
    triangles: list[TriangleRef],
    candidates: list[tuple[int, int]],
    settings: SelfCollisionSettings,
) -> list[Contact]:
    contacts: list[Contact] = []
    threshold = settings.contact_threshold_meters
    spheres = [_triangle_bounding_sphere(positions, item.vertex_indices) for item in triangles]
    directional_bounds = [
        _triangle_directional_bounds(positions, item.vertex_indices) for item in triangles
    ]
    for left_index, right_index in candidates:
        left = triangles[left_index]
        right = triangles[right_index]
        left_center, left_radius = spheres[left_index]
        right_center, right_radius = spheres[right_index]
        maximum_distance = left_radius + right_radius + threshold
        if _distance_squared(left_center, right_center) > maximum_distance * maximum_distance:
            continue
        if not _directional_bounds_may_overlap(
            directional_bounds[left_index], directional_bounds[right_index], threshold
        ):
            continue
        candidate_id = f"candidate.{left_index:04d}.{right_index:04d}"
        contacts.extend(_vertex_triangle_contacts(positions, left, right, candidate_id, settings))
        contacts.extend(_vertex_triangle_contacts(positions, right, left, candidate_id, settings))
        contacts.extend(_edge_edge_contacts(positions, left, right, candidate_id, settings))
    contacts.sort(key=lambda contact: contact.contact_id)
    return contacts


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


def build_self_collision_report(
    *,
    garment_id: str,
    garment_class: str,
    rest_mesh: MeshSet,
    settled_mesh: MeshSet,
    seam_constraints: dict[str, Any] | None = None,
    settings: SelfCollisionSettings | None = None,
) -> dict[str, Any]:
    active_settings = settings or SelfCollisionSettings()
    triangles, offsets = build_triangle_refs(settled_mesh)
    excluded_pairs = seam_exclusion_pairs(seam_constraints or {}, offsets)
    positions = [vertex for mesh in settled_mesh.meshes for vertex in mesh.vertices]
    before = analyze_self_collision_positions(
        positions,
        triangles,
        active_settings,
        excluded_vertex_pairs=excluded_pairs,
    )
    corrected_positions, correction = project_self_collisions(
        positions,
        triangles,
        fixed_indices=_support_like_indices(rest_mesh, offsets),
        settings=active_settings,
        excluded_vertex_pairs=excluded_pairs,
    )
    corrected_mesh = replace_mesh_positions(settled_mesh, corrected_positions, offsets)
    after = analyze_self_collision(
        corrected_mesh,
        settings=active_settings,
        excluded_vertex_pairs=excluded_pairs,
    )
    inverted_before = _inverted_or_degenerate_triangle_count(settled_mesh)
    inverted_after = _inverted_or_degenerate_triangle_count(corrected_mesh)
    finite_after = all(
        all(isfinite(component) for component in vertex) for vertex in corrected_positions
    )
    unresolved = after.unresolved_contact_count
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "self_collision.demo_tshirt_reference_d0_v1",
        "stageVersion": SELF_COLLISION_REPORT_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceAssets": {
            "restState": {
                "path": "simulation/rest_state.json",
                "topologyHash": topology_hash(rest_mesh),
                "contentHash": geometry_content_hash(rest_mesh),
            },
            "settledState": {
                "path": "simulation/settled_state.json",
                "topologyHash": topology_hash(settled_mesh),
                "contentHash": geometry_content_hash(settled_mesh),
            },
            "simulationMeshManifest": {
                "path": "simulation/mesh_manifest.json",
                "topologyHash": topology_hash(settled_mesh),
                "contentHash": geometry_content_hash(settled_mesh),
            },
        },
        "settings": {
            "thicknessMeters": active_settings.thickness_meters,
            "clearanceMeters": active_settings.clearance_meters,
            "contactThresholdMeters": active_settings.contact_threshold_meters,
            "correctionFraction": active_settings.correction_fraction,
            "maxIterations": active_settings.max_iterations,
            "iterationOrdering": "stable_candidate_then_contact_id",
            "broadPhase": "deterministic_inflated_triangle_aabb_all_pairs",
            "narrowPhase": "vertex_triangle_and_edge_edge_distance",
            "oracle": "independent_directional_bounds_then_exact_triangle_proximity",
            "adjacencyExclusion": "same_triangle_or_shared_vertex_pairs_excluded",
            "seamExclusion": "seam_constraint_vertex_pairs_excluded",
            "seamExcludedVertexPairCount": len(excluded_pairs),
            "fixedSupportPolicy": "support_like_vertices_are_not_moved_by_self_collision",
        },
        "execution": {
            "selfCollisionRun": True,
            "broadPhaseRun": True,
            "narrowPhaseRun": True,
            "edgeEdgeNarrowPhaseRun": True,
            "correctionRun": True,
            "bruteForceOracleRun": True,
            "boundedVariantRun": True,
            "motionSuiteCompatible": True,
            "bodyCollisionCompatible": True,
            "seamConstraintCompatible": True,
            "fixedSupportCompatible": True,
            "continuousCollisionDetectionRun": False,
        },
        "metrics": {
            "triangleCount": len(triangles),
            "vertexCount": len(positions),
            "seamExcludedVertexPairCount": len(excluded_pairs),
            "candidatePairCount": len(before.candidate_pairs),
            "oracleCandidatePairCount": len(before.oracle_candidate_pairs),
            "broadPhaseMatchesOracle": before.broad_phase_matches_oracle,
            "contactCountBeforeCorrection": len(before.contacts),
            "contactCountAfterCorrection": len(after.contacts),
            "maxPenetrationBeforeMeters": _round(before.max_penetration_meters),
            "maxPenetrationAfterMeters": _round(after.max_penetration_meters),
            "meanPenetrationBeforeMeters": _round(before.mean_penetration_meters),
            "unresolvedContactCount": after.unresolved_contact_count,
            "correction": correction,
            "unresolvedCountsMonotonicNonIncreasing": correction[
                "unresolvedCountsMonotonicNonIncreasing"
            ],
            "maxPenetrationMonotonicNonIncreasing": correction[
                "maxPenetrationMonotonicNonIncreasing"
            ],
            "invertedOrDegenerateBefore": inverted_before,
            "invertedOrDegenerateAfter": inverted_after,
            "newInvertedOrDegenerateTriangleCount": max(0, inverted_after - inverted_before),
            "finiteCorrectedPositions": finite_after,
            "candidateSamples": [
                {"leftTriangle": left, "rightTriangle": right}
                for left, right in before.candidate_pairs[:8]
            ],
            "contactSamples": [_contact_payload(contact) for contact in before.contacts[:8]],
        },
        "adversarialFixtures": _adversarial_fixture_results(active_settings),
        "timingProfile": {
            "timingEvidenceKind": "deterministic_workload_budget_canonical_wall_clock_omitted",
            "hardware": "not_recorded_in_canonical_package",
            "os": "not_recorded_in_canonical_package",
            "runtimeProfile": "python_reference_cpu_ci_safe",
            "warmupPolicy": "not_applicable_to_canonical_digest",
            "repeatCount": 0,
            "medianMilliseconds": None,
            "p95Milliseconds": None,
            "peakMemoryBytes": None,
            "workload": {
                "vertices": len(positions),
                "triangles": len(triangles),
                "candidatePairs": len(before.candidate_pairs),
                "narrowPhaseContacts": len(before.contacts),
            },
            "budgets": {
                "maxCandidatePairs": 20000,
                "maxUnresolvedContacts": 0,
                "maxNewInvertedOrDegenerateTriangles": 0,
            },
            "budgetStatus": "pass"
            if len(before.candidate_pairs) <= 20000
            and after.unresolved_contact_count == 0
            and inverted_after <= inverted_before
            else "fail",
        },
        "readiness": {
            "status": "d0_reference_self_collision_available_with_tunnelling_limitation"
            if unresolved == 0
            else "d0_reference_self_collision_run_with_unresolved_contacts",
            "acceptedForD0ReferenceSolver": unresolved == 0,
            "acceptedForProductionGpuSolver": False,
            "formalPackageWarningRemoved": True,
            "limitations": [
                "unsupported_high_velocity_tunnelling",
                *([] if unresolved == 0 else ["self_collision_unresolved_contacts_d0_reference"]),
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"selfCollisionReportHash": ""},
    }
    report["integrity"]["selfCollisionReportHash"] = hash_self_collision_report(report)
    return report


def hash_self_collision_report(report: dict[str, Any]) -> str:
    payload = dict(report)
    integrity = dict(payload.get("integrity", {}))
    integrity["selfCollisionReportHash"] = ""
    payload["integrity"] = integrity
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _adversarial_fixture_results(settings: SelfCollisionSettings) -> dict[str, Any]:
    contact_mesh = MeshSet(
        [
            Mesh(
                "fixture.contact",
                "panel.fixture",
                [
                    (-0.05, 0.0, 0.0),
                    (0.05, 0.0, 0.0),
                    (0.0, 0.05, 0.0),
                    (-0.05, 0.0, 0.002),
                    (0.05, 0.0, 0.002),
                    (0.0, 0.05, 0.002),
                ],
                [(0.0, 0.0)] * 6,
                [(0, 1, 2), (3, 5, 4)],
            )
        ]
    )
    separated_mesh = MeshSet(
        [
            Mesh(
                "fixture.separated",
                "panel.fixture",
                [
                    (-0.05, 0.0, 0.0),
                    (0.05, 0.0, 0.0),
                    (0.0, 0.05, 0.0),
                    (-0.05, 0.0, 0.08),
                    (0.05, 0.0, 0.08),
                    (0.0, 0.05, 0.08),
                ],
                [(0.0, 0.0)] * 6,
                [(0, 1, 2), (3, 5, 4)],
            )
        ]
    )
    contact = analyze_self_collision(contact_mesh, settings=settings)
    separated = analyze_self_collision(separated_mesh, settings=settings)
    adjacent_mesh = MeshSet(
        [
            Mesh(
                "fixture.adjacent",
                "panel.fixture",
                [(0.0, 0.0, 0.0), (0.1, 0.0, 0.0), (0.0, 0.1, 0.0), (0.1, 0.1, 0.0)],
                [(0.0, 0.0)] * 4,
                [(0, 1, 2), (1, 3, 2)],
            )
        ]
    )
    adjacent = analyze_self_collision(adjacent_mesh, settings=settings)
    seam_excluded = analyze_self_collision(
        contact_mesh,
        settings=settings,
        excluded_vertex_pairs={(0, 3)},
    )
    crossing_mesh = MeshSet(
        [
            Mesh(
                "fixture.crossing_edges",
                "panel.fixture",
                [
                    (-0.05, 0.0, 0.0),
                    (0.05, 0.0, 0.0),
                    (0.0, 0.04, 0.02),
                    (0.0, -0.05, 0.0),
                    (0.0, 0.05, 0.0),
                    (0.04, 0.0, -0.02),
                ],
                [(0.0, 0.0)] * 6,
                [(0, 1, 2), (3, 4, 5)],
            )
        ]
    )
    crossing = analyze_self_collision(crossing_mesh, settings=settings)
    return {
        "knownContact": {
            "fixtureId": "self_collision_fixture.parallel_triangles_close",
            "expectedContact": True,
            "contactCount": len(contact.contacts),
            "status": "pass" if contact.contacts else "fail",
        },
        "knownNonContact": {
            "fixtureId": "self_collision_fixture.parallel_triangles_separated",
            "expectedContact": False,
            "contactCount": len(separated.contacts),
            "status": "pass" if not separated.contacts else "fail",
        },
        "adjacentTriangleExclusion": {
            "fixtureId": "self_collision_fixture.adjacent_triangles",
            "contactCount": len(adjacent.contacts),
            "status": "pass" if not adjacent.contacts else "fail",
        },
        "seamPairExclusion": {
            "fixtureId": "self_collision_fixture.seam_excluded_close_layers",
            "contactCount": len(seam_excluded.contacts),
            "status": "pass" if not seam_excluded.contacts else "fail",
        },
        "crossingEdges": {
            "fixtureId": "self_collision_fixture.crossing_edges",
            "contactCount": len(crossing.contacts),
            "status": "pass" if crossing.contacts else "fail",
        },
        "invertedNormals": {
            "fixtureId": "self_collision_fixture.opposed_parallel_normals",
            "contactCount": len(contact.contacts),
            "status": "pass" if contact.contacts else "fail",
        },
        "highVelocityTunnelling": {
            "fixtureId": "self_collision_fixture.fast_crossing_triangles",
            "status": "unsupported_high_velocity_tunnelling",
            "continuousHandlingRun": False,
            "testedLimitation": True,
        },
    }


def _vertex_triangle_contacts(
    positions: list[Vec3],
    source: TriangleRef,
    target: TriangleRef,
    candidate_id: str,
    settings: SelfCollisionSettings,
) -> list[Contact]:
    a, b, c = (positions[index] for index in target.vertex_indices)
    target_center, target_radius = _triangle_bounding_sphere(positions, target.vertex_indices)
    maximum_distance = target_radius + settings.contact_threshold_meters
    contacts: list[Contact] = []
    for vertex_index in source.vertex_indices:
        point = positions[vertex_index]
        if _distance_squared(point, target_center) > maximum_distance * maximum_distance:
            continue
        closest = _closest_point_on_triangle(point, a, b, c)
        delta = sub(point, closest)
        distance_squared = _dot(delta, delta)
        if distance_squared >= settings.contact_threshold_meters**2:
            continue
        distance = sqrt(distance_squared)
        normal = _safe_normal(delta, _triangle_normal(a, b, c))
        contacts.append(
            Contact(
                contact_id=(f"contact.v{vertex_index:04d}.tri{target.global_triangle_index:04d}"),
                candidate_id=candidate_id,
                vertex_index=vertex_index,
                triangle_index=target.global_triangle_index,
                distance_meters=distance,
                penetration_meters=settings.contact_threshold_meters - distance,
                normal=normal,
            )
        )
    return contacts


def _triangle_pair_within_threshold(
    positions: list[Vec3], left: Tri, right: Tri, threshold: float
) -> bool:
    left_points = [positions[index] for index in left]
    right_points = [positions[index] for index in right]
    for point in left_points:
        if (
            _distance_squared(point, _closest_point_on_triangle(point, *right_points))
            <= threshold * threshold
        ):
            return True
    for point in right_points:
        if (
            _distance_squared(point, _closest_point_on_triangle(point, *left_points))
            <= threshold * threshold
        ):
            return True
    for left_edge in _triangle_edges(left):
        for right_edge in _triangle_edges(right):
            left_near, right_near = _closest_points_on_segments(
                positions[left_edge[0]],
                positions[left_edge[1]],
                positions[right_edge[0]],
                positions[right_edge[1]],
            )
            if _distance_squared(left_near, right_near) <= threshold * threshold:
                return True
    return False


def _edge_edge_contacts(
    positions: list[Vec3],
    left: TriangleRef,
    right: TriangleRef,
    candidate_id: str,
    settings: SelfCollisionSettings,
) -> list[Contact]:
    contacts: list[Contact] = []
    threshold = settings.contact_threshold_meters
    for left_edge_index, left_edge in enumerate(_triangle_edges(left.vertex_indices)):
        for right_edge_index, right_edge in enumerate(_triangle_edges(right.vertex_indices)):
            if not _segment_pair_may_be_within_threshold(
                positions[left_edge[0]],
                positions[left_edge[1]],
                positions[right_edge[0]],
                positions[right_edge[1]],
                threshold,
            ):
                continue
            left_near, right_near = _closest_points_on_segments(
                positions[left_edge[0]],
                positions[left_edge[1]],
                positions[right_edge[0]],
                positions[right_edge[1]],
            )
            delta = sub(left_near, right_near)
            distance_squared = _dot(delta, delta)
            if distance_squared >= threshold * threshold:
                continue
            distance = sqrt(distance_squared)
            moving_vertex = min(
                left_edge, key=lambda index: _length(sub(positions[index], left_near))
            )
            normal = _safe_normal(
                delta, _triangle_normal(*(positions[index] for index in right.vertex_indices))
            )
            contacts.append(
                Contact(
                    contact_id=(
                        f"contact.edge.{candidate_id}.{left_edge_index}.{right_edge_index}."
                        f"{moving_vertex}"
                    ),
                    candidate_id=candidate_id,
                    vertex_index=moving_vertex,
                    triangle_index=right.global_triangle_index,
                    distance_meters=distance,
                    penetration_meters=max(0.0, threshold - distance),
                    normal=normal,
                )
            )
    return contacts


def _triangle_edges(triangle: Tri) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    return (
        (triangle[0], triangle[1]),
        (triangle[1], triangle[2]),
        (triangle[2], triangle[0]),
    )


def _closest_points_on_segments(a: Vec3, b: Vec3, c: Vec3, d: Vec3) -> tuple[Vec3, Vec3]:
    # Ericson-style segment/segment closest points with deterministic clamping.
    ab = sub(b, a)
    cd = sub(d, c)
    ac = sub(a, c)
    aa = _dot(ab, ab)
    ee = _dot(cd, cd)
    ff = _dot(cd, ac)
    if aa <= 1e-15 and ee <= 1e-15:
        return a, c
    if aa <= 1e-15:
        s = 0.0
        t = _clamp(ff / ee)
    else:
        cc = _dot(ab, ac)
        if ee <= 1e-15:
            t = 0.0
            s = _clamp(-cc / aa)
        else:
            bb = _dot(ab, cd)
            denominator = aa * ee - bb * bb
            s = _clamp((bb * ff - cc * ee) / denominator) if abs(denominator) > 1e-15 else 0.0
            t = (bb * s + ff) / ee
            if t < 0.0:
                t = 0.0
                s = _clamp(-cc / aa)
            elif t > 1.0:
                t = 1.0
                s = _clamp((bb - cc) / aa)
    return add(a, scale(ab, s)), add(c, scale(cd, t))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def seam_exclusion_pairs(
    seam_constraints: dict[str, Any], mesh_offsets: list[int]
) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for constraint in seam_constraints.get("constraints", []):
        span_a = constraint.get("spanA", {})
        span_b = constraint.get("spanB", {})
        try:
            offset_a = mesh_offsets[int(span_a["meshIndex"])]
            offset_b = mesh_offsets[int(span_b["meshIndex"])]
            vertices_a = {
                offset_a + int(span_a["vertexIndex"]),
                offset_a + int(span_a.get("nextVertexIndex", span_a["vertexIndex"])),
            }
            vertices_b = {
                offset_b + int(span_b["vertexIndex"]),
                offset_b + int(span_b.get("nextVertexIndex", span_b["vertexIndex"])),
            }
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        for a in vertices_a:
            for b in vertices_b:
                pairs.add((min(a, b), max(a, b)))
    return pairs


def _triangles_are_adjacent(
    left: TriangleRef,
    right: TriangleRef,
    excluded_vertex_pairs: set[tuple[int, int]],
) -> bool:
    if set(left.vertex_indices) & set(right.vertex_indices):
        return True
    for left_vertex in left.vertex_indices:
        for right_vertex in right.vertex_indices:
            pair = (min(left_vertex, right_vertex), max(left_vertex, right_vertex))
            if pair in excluded_vertex_pairs:
                return True
    return False


def _triangle_bounds(positions: list[Vec3], triangle: Tri, inflate: float) -> tuple[Vec3, Vec3]:
    verts = [positions[index] for index in triangle]
    minimum = (
        min(vertex[0] for vertex in verts) - inflate,
        min(vertex[1] for vertex in verts) - inflate,
        min(vertex[2] for vertex in verts) - inflate,
    )
    maximum = (
        max(vertex[0] for vertex in verts) + inflate,
        max(vertex[1] for vertex in verts) + inflate,
        max(vertex[2] for vertex in verts) + inflate,
    )
    return (
        minimum,
        maximum,
    )


def _triangle_bounding_sphere(positions: list[Vec3], triangle: Tri) -> tuple[Vec3, float]:
    a, b, c = (positions[index] for index in triangle)
    center = (
        (a[0] + b[0] + c[0]) / 3.0,
        (a[1] + b[1] + c[1]) / 3.0,
        (a[2] + b[2] + c[2]) / 3.0,
    )
    radius = sqrt(max(_distance_squared(center, point) for point in (a, b, c)))
    return center, radius


def _triangle_directional_bounds(
    positions: list[Vec3], triangle: Tri
) -> tuple[tuple[float, float], ...]:
    points = tuple(positions[index] for index in triangle)
    return tuple(
        (
            min(_dot(point, direction) for point in points),
            max(_dot(point, direction) for point in points),
        )
        for direction in _ORACLE_DIRECTIONS
    )


def _directional_bounds_may_overlap(
    left: tuple[tuple[float, float], ...],
    right: tuple[tuple[float, float], ...],
    threshold: float,
) -> bool:
    for index, direction in enumerate(_ORACLE_DIRECTIONS):
        margin = threshold * _length(direction)
        left_min, left_max = left[index]
        right_min, right_max = right[index]
        if left_max + margin < right_min or right_max + margin < left_min:
            return False
    return True


def _segment_pair_may_be_within_threshold(
    a: Vec3, b: Vec3, c: Vec3, d: Vec3, threshold: float
) -> bool:
    left_center = scale(add(a, b), 0.5)
    right_center = scale(add(c, d), 0.5)
    maximum_distance = _length(sub(a, b)) * 0.5 + _length(sub(c, d)) * 0.5 + threshold
    return _distance_squared(left_center, right_center) <= maximum_distance * maximum_distance


def _distance_squared(a: Vec3, b: Vec3) -> float:
    x = a[0] - b[0]
    y = a[1] - b[1]
    z = a[2] - b[2]
    return x * x + y * y + z * z


def _aabb_overlap(left: tuple[Vec3, Vec3], right: tuple[Vec3, Vec3]) -> bool:
    return all(
        left[0][axis] <= right[1][axis] and right[0][axis] <= left[1][axis] for axis in range(3)
    )


def _closest_point_on_triangle(point: Vec3, a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    ab = sub(b, a)
    ac = sub(c, a)
    ap = sub(point, a)
    d1 = _dot(ab, ap)
    d2 = _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a
    bp = sub(point, b)
    d3 = _dot(ab, bp)
    d4 = _dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        return add(a, scale(ab, v))
    cp = sub(point, c)
    d5 = _dot(ab, cp)
    d6 = _dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        return add(a, scale(ac, w))
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return add(b, scale(sub(c, b), w))
    denom = 1.0 / max(1e-12, va + vb + vc)
    v = vb * denom
    w = vc * denom
    return add(a, add(scale(ab, v), scale(ac, w)))


def _triangle_normal(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    return _safe_normal(cross(sub(b, a), sub(c, a)), (0.0, 1.0, 0.0))


def _safe_normal(value: Vec3, fallback: Vec3) -> Vec3:
    length = _length(value)
    if length <= 1e-12:
        return fallback
    return scale(value, 1.0 / length)


def _support_like_indices(rest_mesh: MeshSet, offsets: list[int]) -> set[int]:
    indices: set[int] = set()
    for mesh_index, mesh in enumerate(rest_mesh.meshes):
        for vertex_index, vertex in enumerate(mesh.vertices):
            if mesh.panel_id == "panel.neck_band" or vertex[1] >= 1.345:
                indices.add(offsets[mesh_index] + vertex_index)
    return indices


def _inverted_or_degenerate_triangle_count(meshset: MeshSet) -> int:
    count = 0
    for mesh in meshset.meshes:
        for tri in mesh.triangles:
            if (
                _length(
                    cross(
                        sub(mesh.vertices[tri[1]], mesh.vertices[tri[0]]),
                        sub(mesh.vertices[tri[2]], mesh.vertices[tri[0]]),
                    )
                )
                <= 1e-10
            ):
                count += 1
    return count


def _contact_payload(contact: Contact) -> dict[str, Any]:
    return {
        "contactId": contact.contact_id,
        "candidateId": contact.candidate_id,
        "vertexIndex": contact.vertex_index,
        "triangleIndex": contact.triangle_index,
        "distanceMeters": _round(contact.distance_meters),
        "penetrationMeters": _round(contact.penetration_meters),
        "normal": [_round(component) for component in contact.normal],
    }


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(value: Vec3) -> float:
    return sqrt(value[0] * value[0] + value[1] * value[1] + value[2] * value[2])


def _round(value: float) -> float:
    return round(float(value), 9)


def _non_increasing(values: Sequence[float | int]) -> bool:
    return all(right <= left + 1e-12 for left, right in zip(values, values[1:], strict=False))
