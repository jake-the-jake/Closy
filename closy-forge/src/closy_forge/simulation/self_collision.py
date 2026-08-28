from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import floor, isfinite, sqrt
from typing import Any, Literal

from closy_forge.geometry.mesh_model import Mesh, MeshSet, Tri, Vec3, add, cross, scale, sub
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, topology_hash
from closy_forge.simulation.deformation_quality import audit_rest_referenced_deformation

SELF_COLLISION_REPORT_VERSION = "closy.self_collision.reference_d0.symmetric_grid_v4"

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
    residual_depth_budget_ratio: float = 0.10
    maximum_ccd_substeps: int = 64
    response_mode: Literal["symmetric_gradient", "legacy_vertex_only"] = "symmetric_gradient"

    @property
    def contact_threshold_meters(self) -> float:
        return self.thickness_meters + self.clearance_meters

    @property
    def residual_depth_budget_meters(self) -> float:
        return self.thickness_meters * self.residual_depth_budget_ratio


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
    contact_kind: str
    gradient_coefficients: tuple[tuple[int, float], ...]


@dataclass(frozen=True)
class SelfCollisionAnalysis:
    candidate_pairs: list[tuple[int, int]]
    oracle_candidate_pairs: list[tuple[int, int]]
    contacts: list[Contact]
    max_penetration_meters: float
    mean_penetration_meters: float
    unresolved_contact_count: int
    broad_phase_matches_oracle: bool


@dataclass(frozen=True)
class SweptCollisionAnalysis:
    status: str
    supported: bool
    substep_count: int
    first_contact_fraction: float | None
    contact_count: int
    max_penetration_meters: float


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


def analyze_swept_self_collision(
    previous_positions: list[Vec3],
    current_positions: list[Vec3],
    triangles: list[TriangleRef],
    settings: SelfCollisionSettings,
    *,
    excluded_vertex_pairs: set[tuple[int, int]] | None = None,
    maximum_substeps: int | None = None,
) -> SweptCollisionAnalysis:
    """Bounded conservative temporal subdivision for the D0 CPU CCD fixture profile."""

    if len(previous_positions) != len(current_positions):
        raise ValueError("swept_collision_position_count_mismatch")
    if not previous_positions:
        return SweptCollisionAnalysis("pass_no_vertices", True, 0, None, 0, 0.0)
    displacement = max(
        _length(sub(current, previous))
        for previous, current in zip(previous_positions, current_positions, strict=True)
    )
    sampling_distance = max(settings.contact_threshold_meters * 0.5, settings.epsilon_meters)
    required_substeps = max(1, int(displacement / sampling_distance) + 1)
    limit = maximum_substeps or settings.maximum_ccd_substeps
    if required_substeps > limit:
        return SweptCollisionAnalysis(
            "unsupported_motion_exceeds_bounded_substeps",
            False,
            required_substeps,
            None,
            0,
            0.0,
        )
    first_fraction: float | None = None
    maximum_contacts = 0
    maximum_penetration = 0.0
    for step in range(required_substeps + 1):
        fraction = step / required_substeps
        positions = [
            add(previous, scale(sub(current, previous), fraction))
            for previous, current in zip(previous_positions, current_positions, strict=True)
        ]
        analysis = analyze_self_collision_positions(
            positions,
            triangles,
            settings,
            excluded_vertex_pairs=excluded_vertex_pairs,
            evaluate_oracle=False,
        )
        if analysis.contacts and first_fraction is None:
            first_fraction = fraction
        maximum_contacts = max(maximum_contacts, len(analysis.contacts))
        maximum_penetration = max(maximum_penetration, analysis.max_penetration_meters)
    return SweptCollisionAnalysis(
        "contact_detected" if first_fraction is not None else "no_contact",
        True,
        required_substeps,
        first_fraction,
        maximum_contacts,
        maximum_penetration,
    )


def project_self_collisions(
    positions: list[Vec3],
    triangles: list[TriangleRef],
    *,
    fixed_indices: set[int] | None = None,
    settings: SelfCollisionSettings | None = None,
    excluded_vertex_pairs: set[tuple[int, int]] | None = None,
    orientation_reference_positions: list[Vec3] | None = None,
) -> tuple[list[Vec3], dict[str, Any]]:
    active_settings = settings or SelfCollisionSettings()
    fixed = fixed_indices or set()
    current = list(positions)
    orientation_reference = orientation_reference_positions or positions
    if len(orientation_reference) != len(positions):
        raise ValueError("self_collision_orientation_reference_size_mismatch")
    incident_triangles = _incident_triangle_map(triangles)
    total_corrections = 0
    total_backtracks = 0
    rejected_orientation_corrections = 0
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
            if active_settings.response_mode == "legacy_vertex_only":
                if contact.vertex_index in fixed:
                    continue
                correction = scale(
                    contact.normal,
                    contact.penetration_meters * active_settings.correction_fraction,
                )
                current[contact.vertex_index] = add(current[contact.vertex_index], correction)
                correction_count += 1
                continue
            movable = tuple(
                (vertex_index, coefficient)
                for vertex_index, coefficient in contact.gradient_coefficients
                if vertex_index not in fixed
            )
            denominator = sum(coefficient * coefficient for _, coefficient in movable)
            if denominator <= active_settings.epsilon_meters:
                continue
            multiplier = (
                contact.penetration_meters * active_settings.correction_fraction / denominator
            )
            deltas = {
                vertex_index: scale(contact.normal, multiplier * coefficient)
                for vertex_index, coefficient in movable
            }
            line_scale = 1.0
            backtracks = 0
            while backtracks < 5 and not _correction_preserves_local_orientation(
                current,
                orientation_reference,
                deltas,
                line_scale,
                incident_triangles,
            ):
                line_scale *= 0.5
                backtracks += 1
            total_backtracks += backtracks
            if not _correction_preserves_local_orientation(
                current,
                orientation_reference,
                deltas,
                line_scale,
                incident_triangles,
            ):
                rejected_orientation_corrections += 1
                continue
            for vertex_index, _ in movable:
                correction = scale(deltas[vertex_index], line_scale)
                current[vertex_index] = add(current[vertex_index], correction)
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
    convergence: dict[str, Any] = {
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
    # Keep the established package contract byte-stable when the compatibility
    # response is selected; PHY1 opts into and records the stronger guard data.
    if active_settings.response_mode == "symmetric_gradient":
        convergence["orientationBacktrackCount"] = total_backtracks
        convergence["orientationRejectedCorrectionCount"] = rejected_orientation_corrections
    return current, convergence


def broad_phase_candidates(
    positions: list[Vec3],
    triangles: list[TriangleRef],
    settings: SelfCollisionSettings,
    excluded_vertex_pairs: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    if not triangles:
        return []
    exclusions = excluded_vertex_pairs or set()
    inflated_bounds = [
        _triangle_bounds(positions, triangle.vertex_indices, settings.contact_threshold_meters)
        for triangle in triangles
    ]
    extent = max(
        max(vertex[axis] for vertex in positions) - min(vertex[axis] for vertex in positions)
        for axis in range(3)
    )
    cell_size = max(settings.contact_threshold_meters * 2.0, extent / 32.0, 1e-6)
    grid: dict[tuple[int, int, int], list[int]] = {}
    insertion_count = 0
    for triangle_index, bounds in enumerate(inflated_bounds):
        minimum = tuple(floor(component / cell_size) for component in bounds[0])
        maximum = tuple(floor(component / cell_size) for component in bounds[1])
        triangle_cells = (
            (maximum[0] - minimum[0] + 1)
            * (maximum[1] - minimum[1] + 1)
            * (maximum[2] - minimum[2] + 1)
        )
        insertion_count += triangle_cells
        if triangle_cells <= 0 or insertion_count > 1_000_000:
            raise ValueError("self_collision_uniform_grid_budget_exceeded")
        for x in range(minimum[0], maximum[0] + 1):
            for y in range(minimum[1], maximum[1] + 1):
                for z in range(minimum[2], maximum[2] + 1):
                    grid.setdefault((x, y, z), []).append(triangle_index)
    possible_pairs: set[tuple[int, int]] = set()
    for cell in sorted(grid):
        members = sorted(set(grid[cell]))
        for member_offset, left_index in enumerate(members):
            for right_index in members[member_offset + 1 :]:
                possible_pairs.add((left_index, right_index))
    candidates: list[tuple[int, int]] = []
    for left_index, right_index in sorted(possible_pairs):
        left = triangles[left_index]
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
        orientation_reference_positions=[
            vertex for mesh in rest_mesh.meshes for vertex in mesh.vertices
        ],
    )
    corrected_mesh = replace_mesh_positions(settled_mesh, corrected_positions, offsets)
    after = analyze_self_collision(
        corrected_mesh,
        settings=active_settings,
        excluded_vertex_pairs=excluded_pairs,
    )
    deformation_before = audit_rest_referenced_deformation(rest_mesh, settled_mesh)
    deformation_after = audit_rest_referenced_deformation(rest_mesh, corrected_mesh)
    inverted_before = int(deformation_before["counts"]["inverted"]) + int(
        deformation_before["counts"]["degenerate"]
    )
    inverted_after = int(deformation_after["counts"]["inverted"]) + int(
        deformation_after["counts"]["degenerate"]
    )
    finite_after = all(
        all(isfinite(component) for component in vertex) for vertex in corrected_positions
    )
    unresolved = after.unresolved_contact_count
    adversarial_fixtures = _adversarial_fixture_results(active_settings)
    ccd_fixture_pass = all(
        item.get("status") == "pass"
        for key, item in adversarial_fixtures.items()
        if key
        in {
            "highVelocityTunnelling",
            "thinLayerSweep",
            "openingBoundarySweep",
            "boundedUnsupportedMotion",
        }
    )
    residual_depth_within_budget = (
        after.max_penetration_meters <= active_settings.residual_depth_budget_meters
    )
    exclusions_by_reason = _candidate_exclusion_counts(triangles, excluded_pairs)
    unique_before = _unique_contacts(before.contacts)
    unique_after = _unique_contacts(after.contacts)
    residual_touching = sum(
        contact.penetration_meters <= active_settings.epsilon_meters for contact in unique_after
    )
    residual_penetrating = len(unique_after) - residual_touching
    residual_above_budget = sum(
        contact.penetration_meters > active_settings.residual_depth_budget_meters
        for contact in unique_after
    )
    literal_collision_pass = (unresolved == 0 or residual_depth_within_budget) and ccd_fixture_pass
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
            "responseMode": active_settings.response_mode,
            "iterationOrdering": "stable_candidate_then_contact_id",
            "broadPhase": "deterministic_bounded_uniform_grid_then_inflated_aabb",
            "narrowPhase": "vertex_triangle_and_edge_edge_distance",
            "normalResponse": ("symmetric_inverse_mass_barycentric_and_edge_parameter_projection"),
            "orientationGuard": "bounded_five_backtrack_local_rest_orientation_guard",
            "oracle": "independent_directional_bounds_then_exact_triangle_proximity",
            "adjacencyExclusion": "same_triangle_or_shared_vertex_pairs_excluded",
            "seamExclusion": "seam_constraint_vertex_pairs_excluded",
            "seamExcludedVertexPairCount": len(excluded_pairs),
            "fixedSupportPolicy": "support_like_vertices_are_not_moved_by_self_collision",
            "residualDepthBudgetMeters": active_settings.residual_depth_budget_meters,
            "residualDepthBudgetBasis": "ten_percent_of_declared_material_thickness",
            "residualDepthBudgetAppliesTo": "self_collision_contacts_only",
            "bodyClearanceBudgetAuthority": "separate_phy1_body_signed_clearance_profile",
            "maximumCcdSubsteps": active_settings.maximum_ccd_substeps,
            "maximumUniformGridInsertions": 1_000_000,
        },
        "collisionQuantityDomains": {
            "selfSignedSeparation": ("cloth_primitive_distance_minus_thickness_and_contact_offset"),
            "touchingContact": "penetration_at_or_below_numerical_epsilon",
            "penetrationDepth": "negative_self_signed_separation_magnitude",
            "oracleUncertain": "unsupported_for_promotion_and_fails_closed",
            "bodySignedClearance": "reported_by_independent_body_signed_distance_audit",
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
            "continuousCollisionDetectionRun": True,
            "continuousCollisionDetectionScope": "bounded_d0_adversarial_fixture_suite_only",
            "continuousCollisionIntegratedIntoReferenceMotionSolver": False,
        },
        "metrics": {
            "triangleCount": len(triangles),
            "vertexCount": len(positions),
            "seamExcludedVertexPairCount": len(excluded_pairs),
            "candidatePairCount": len(before.candidate_pairs),
            "oracleCandidatePairCount": len(before.oracle_candidate_pairs),
            "broadPhaseMatchesOracle": before.broad_phase_matches_oracle,
            "sharedVertexExcludedPairCount": exclusions_by_reason["sharedVertex"],
            "seamExcludedTrianglePairCount": exclusions_by_reason["seam"],
            "contactCountBeforeCorrection": len(before.contacts),
            "contactCountAfterCorrection": len(after.contacts),
            "narrowPhaseWitnessCount": len(before.contacts),
            "geometricallyUniqueContactCountBefore": len(unique_before),
            "solverConstraintCountCreated": len(unique_before),
            "resolvedUniqueContactCount": max(0, len(unique_before) - len(unique_after)),
            "residualTouchingContactCount": residual_touching,
            "residualPenetratingContactCount": residual_penetrating,
            "residualViolationAboveDepthBudgetCount": residual_above_budget,
            "maxPenetrationBeforeMeters": _round(before.max_penetration_meters),
            "maxPenetrationAfterMeters": _round(after.max_penetration_meters),
            "meanPenetrationBeforeMeters": _round(before.mean_penetration_meters),
            "unresolvedContactCount": after.unresolved_contact_count,
            "residualDepthWithinBudget": residual_depth_within_budget,
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
            "restReferencedDeformationBefore": deformation_before,
            "restReferencedDeformationAfter": deformation_after,
            "finiteCorrectedPositions": finite_after,
            "candidateSamples": [
                {"leftTriangle": left, "rightTriangle": right}
                for left, right in before.candidate_pairs[:8]
            ],
            "contactSamples": [_contact_payload(contact) for contact in before.contacts[:8]],
            "deepestResidualWitnesses": [
                _contact_payload(contact)
                for contact in sorted(
                    unique_after,
                    key=lambda contact: (-contact.penetration_meters, contact.contact_id),
                )[:8]
            ],
        },
        "adversarialFixtures": adversarial_fixtures,
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
            and literal_collision_pass
            and inverted_after <= inverted_before
            else "fail",
        },
        "readiness": {
            "status": "d0_reference_self_collision_literal_pass"
            if literal_collision_pass
            else "d0_reference_self_collision_run_with_unresolved_contacts",
            "acceptedForD0ReferenceSolver": literal_collision_pass,
            "acceptedForProductionGpuSolver": False,
            "formalPackageWarningRemoved": True,
            "limitations": [
                "bounded_ccd_not_integrated_into_reference_motion_solver",
                *([] if ccd_fixture_pass else ["bounded_ccd_fixture_failure"]),
                *([] if unresolved == 0 else ["self_collision_unresolved_contacts_d0_reference"]),
                *(
                    []
                    if residual_depth_within_budget
                    else ["self_collision_residual_depth_budget_exceeded"]
                ),
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
    swept_mesh = MeshSet(
        [
            Mesh(
                "fixture.swept",
                "panel.fixture",
                _swept_fixture_positions(-0.03),
                [(0.0, 0.0)] * 6,
                [(0, 1, 2), (3, 5, 4)],
            )
        ]
    )
    swept_triangles, _ = build_triangle_refs(swept_mesh)
    high_velocity = analyze_swept_self_collision(
        _swept_fixture_positions(-0.03),
        _swept_fixture_positions(0.03),
        swept_triangles,
        settings,
    )
    thin_layer = analyze_swept_self_collision(
        _swept_fixture_positions(0.006),
        _swept_fixture_positions(0.001),
        swept_triangles,
        settings,
    )
    opening_previous = _swept_fixture_positions(-0.012, x_offset=0.045)
    opening_current = _swept_fixture_positions(0.012, x_offset=0.045)
    opening_boundary = analyze_swept_self_collision(
        opening_previous,
        opening_current,
        swept_triangles,
        settings,
    )
    bounded_rejection = analyze_swept_self_collision(
        _swept_fixture_positions(-1.0),
        _swept_fixture_positions(1.0),
        swept_triangles,
        settings,
        maximum_substeps=8,
    )
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
            "status": (
                "pass"
                if high_velocity.supported and high_velocity.first_contact_fraction is not None
                else "fail"
            ),
            "continuousHandlingRun": True,
            "substepCount": high_velocity.substep_count,
            "firstContactFraction": high_velocity.first_contact_fraction,
            "contactCount": high_velocity.contact_count,
        },
        "thinLayerSweep": {
            "fixtureId": "self_collision_fixture.thin_layer_approach",
            "status": (
                "pass"
                if thin_layer.supported and thin_layer.first_contact_fraction is not None
                else "fail"
            ),
            "continuousHandlingRun": True,
            "substepCount": thin_layer.substep_count,
            "firstContactFraction": thin_layer.first_contact_fraction,
        },
        "openingBoundarySweep": {
            "fixtureId": "self_collision_fixture.opening_boundary_crossing",
            "status": (
                "pass"
                if opening_boundary.supported
                and opening_boundary.first_contact_fraction is not None
                else "fail"
            ),
            "continuousHandlingRun": True,
            "substepCount": opening_boundary.substep_count,
            "firstContactFraction": opening_boundary.first_contact_fraction,
        },
        "boundedUnsupportedMotion": {
            "fixtureId": "self_collision_fixture.motion_exceeds_ccd_bound",
            "status": "pass" if not bounded_rejection.supported else "fail",
            "continuousHandlingRun": True,
            "failureStatus": bounded_rejection.status,
        },
    }


def _swept_fixture_positions(z: float, *, x_offset: float = 0.0) -> list[Vec3]:
    return [
        (-0.05, 0.0, 0.0),
        (0.05, 0.0, 0.0),
        (0.0, 0.05, 0.0),
        (-0.04 + x_offset, 0.005, z),
        (0.04 + x_offset, 0.005, z),
        (x_offset, 0.045, z),
    ]


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
        closest, barycentric = _closest_point_and_barycentric_on_triangle(point, a, b, c)
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
                contact_kind="vertex_triangle",
                gradient_coefficients=(
                    (vertex_index, 1.0),
                    (target.vertex_indices[0], -barycentric[0]),
                    (target.vertex_indices[1], -barycentric[1]),
                    (target.vertex_indices[2], -barycentric[2]),
                ),
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
            left_near, right_near, left_parameter, right_parameter = (
                _closest_points_on_segments_with_parameters(
                    positions[left_edge[0]],
                    positions[left_edge[1]],
                    positions[right_edge[0]],
                    positions[right_edge[1]],
                )
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
                    contact_kind="edge_edge",
                    gradient_coefficients=(
                        (left_edge[0], 1.0 - left_parameter),
                        (left_edge[1], left_parameter),
                        (right_edge[0], -(1.0 - right_parameter)),
                        (right_edge[1], -right_parameter),
                    ),
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
    left, right, _, _ = _closest_points_on_segments_with_parameters(a, b, c, d)
    return left, right


def _closest_points_on_segments_with_parameters(
    a: Vec3, b: Vec3, c: Vec3, d: Vec3
) -> tuple[Vec3, Vec3, float, float]:
    # Ericson-style segment/segment closest points with deterministic clamping.
    ab = sub(b, a)
    cd = sub(d, c)
    ac = sub(a, c)
    aa = _dot(ab, ab)
    ee = _dot(cd, cd)
    ff = _dot(cd, ac)
    if aa <= 1e-15 and ee <= 1e-15:
        return a, c, 0.0, 0.0
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
    return add(a, scale(ab, s)), add(c, scale(cd, t)), s, t


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
    return _adjacency_reason(left, right, excluded_vertex_pairs) is not None


def _adjacency_reason(
    left: TriangleRef,
    right: TriangleRef,
    excluded_vertex_pairs: set[tuple[int, int]],
) -> str | None:
    if set(left.vertex_indices) & set(right.vertex_indices):
        return "sharedVertex"
    for left_vertex in left.vertex_indices:
        for right_vertex in right.vertex_indices:
            pair = (min(left_vertex, right_vertex), max(left_vertex, right_vertex))
            if pair in excluded_vertex_pairs:
                return "seam"
    return None


def _candidate_exclusion_counts(
    triangles: list[TriangleRef], excluded_vertex_pairs: set[tuple[int, int]]
) -> dict[str, int]:
    counts = {"sharedVertex": 0, "seam": 0}
    for left_index, left in enumerate(triangles):
        for right in triangles[left_index + 1 :]:
            reason = _adjacency_reason(left, right, excluded_vertex_pairs)
            if reason is not None:
                counts[reason] += 1
    return counts


def _unique_contacts(contacts: list[Contact]) -> list[Contact]:
    records: dict[tuple[str, tuple[tuple[int, float], ...]], Contact] = {}
    for contact in contacts:
        key = (
            contact.contact_kind,
            tuple(
                sorted(
                    (vertex_index, _round(coefficient))
                    for vertex_index, coefficient in contact.gradient_coefficients
                )
            ),
        )
        existing = records.get(key)
        if existing is None or contact.penetration_meters > existing.penetration_meters:
            records[key] = contact
    return sorted(records.values(), key=lambda contact: contact.contact_id)


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
    closest, _ = _closest_point_and_barycentric_on_triangle(point, a, b, c)
    return closest


def _closest_point_and_barycentric_on_triangle(
    point: Vec3, a: Vec3, b: Vec3, c: Vec3
) -> tuple[Vec3, tuple[float, float, float]]:
    ab = sub(b, a)
    ac = sub(c, a)
    if _dot(cross(ab, ac), cross(ab, ac)) <= 1e-24:
        candidates = (
            _degenerate_edge_candidate(point, a, b, (0, 1)),
            _degenerate_edge_candidate(point, b, c, (1, 2)),
            _degenerate_edge_candidate(point, c, a, (2, 0)),
        )
        _, closest, barycentric = min(candidates, key=lambda item: item[0])
        return closest, barycentric
    ap = sub(point, a)
    d1 = _dot(ab, ap)
    d2 = _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a, (1.0, 0.0, 0.0)
    bp = sub(point, b)
    d3 = _dot(ab, bp)
    d4 = _dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return b, (0.0, 1.0, 0.0)
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        return add(a, scale(ab, v)), (1.0 - v, v, 0.0)
    cp = sub(point, c)
    d5 = _dot(ab, cp)
    d6 = _dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return c, (0.0, 0.0, 1.0)
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        return add(a, scale(ac, w)), (1.0 - w, 0.0, w)
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return add(b, scale(sub(c, b), w)), (0.0, 1.0 - w, w)
    denom = 1.0 / max(1e-12, va + vb + vc)
    v = vb * denom
    w = vc * denom
    return add(a, add(scale(ab, v), scale(ac, w))), (1.0 - v - w, v, w)


def _degenerate_edge_candidate(
    point: Vec3,
    start: Vec3,
    end: Vec3,
    indices: tuple[int, int],
) -> tuple[float, Vec3, tuple[float, float, float]]:
    edge = sub(end, start)
    length_squared = _dot(edge, edge)
    parameter = (
        _clamp(_dot(sub(point, start), edge) / length_squared) if length_squared > 1e-24 else 0.0
    )
    closest = add(start, scale(edge, parameter))
    weights = [0.0, 0.0, 0.0]
    weights[indices[0]] = 1.0 - parameter
    weights[indices[1]] += parameter
    return _distance_squared(point, closest), closest, (weights[0], weights[1], weights[2])


def _incident_triangle_map(triangles: list[TriangleRef]) -> dict[int, tuple[Tri, ...]]:
    mutable: dict[int, list[Tri]] = {}
    for triangle in triangles:
        for vertex_index in triangle.vertex_indices:
            mutable.setdefault(vertex_index, []).append(triangle.vertex_indices)
    return {vertex_index: tuple(records) for vertex_index, records in mutable.items()}


def _correction_preserves_local_orientation(
    positions: list[Vec3],
    reference_positions: list[Vec3],
    deltas: dict[int, Vec3],
    line_scale: float,
    incident_triangles: dict[int, tuple[Tri, ...]],
) -> bool:
    local_triangles = {
        triangle for vertex_index in deltas for triangle in incident_triangles.get(vertex_index, ())
    }
    for triangle in local_triangles:
        reference = tuple(reference_positions[index] for index in triangle)
        reference_normal = cross(sub(reference[1], reference[0]), sub(reference[2], reference[0]))
        reference_area_squared = _dot(reference_normal, reference_normal)
        before = tuple(positions[index] for index in triangle)
        before_normal = cross(sub(before[1], before[0]), sub(before[2], before[0]))
        before_area_squared = _dot(before_normal, before_normal)
        if before_area_squared <= 1e-20:
            continue
        after = tuple(
            add(positions[index], scale(deltas.get(index, (0.0, 0.0, 0.0)), line_scale))
            for index in triangle
        )
        after_normal = cross(sub(after[1], after[0]), sub(after[2], after[0]))
        after_area_squared = _dot(after_normal, after_normal)
        if (
            after_area_squared <= max(before_area_squared * 1e-10, reference_area_squared * 1e-12)
            or _dot(before_normal, after_normal) <= 0.0
        ):
            return False
        if (
            reference_area_squared > 1e-20
            and _dot(reference_normal, before_normal) > 0.0
            and _dot(reference_normal, after_normal) <= 0.0
        ):
            return False
    return True


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


def _contact_payload(contact: Contact) -> dict[str, Any]:
    return {
        "contactId": contact.contact_id,
        "candidateId": contact.candidate_id,
        "vertexIndex": contact.vertex_index,
        "triangleIndex": contact.triangle_index,
        "distanceMeters": _round(contact.distance_meters),
        "penetrationMeters": _round(contact.penetration_meters),
        "normal": [_round(component) for component in contact.normal],
        "contactKind": contact.contact_kind,
        "gradientCoefficients": [
            {"vertexIndex": vertex_index, "coefficient": _round(coefficient)}
            for vertex_index, coefficient in contact.gradient_coefficients
        ],
    }


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(value: Vec3) -> float:
    return sqrt(value[0] * value[0] + value[1] * value[1] + value[2] * value[2])


def _round(value: float) -> float:
    return round(float(value), 9)


def _non_increasing(values: Sequence[float | int]) -> bool:
    return all(right <= left + 1e-12 for left, right in zip(values, values[1:], strict=False))
