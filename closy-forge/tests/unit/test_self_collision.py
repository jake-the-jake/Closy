from __future__ import annotations

from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.simulation.self_collision import (
    SelfCollisionSettings,
    _correction_preserves_local_orientation,
    analyze_self_collision,
    analyze_swept_self_collision,
    broad_phase_candidates,
    brute_force_candidate_oracle,
    build_self_collision_report,
    build_triangle_refs,
    hash_self_collision_report,
    project_self_collisions,
)
from closy_forge.validation.validator import validate_package
from tests.helpers import build_demo, clone_package, issue_codes, read_json, write_json


def test_self_collision_broad_phase_matches_bruteforce_oracle() -> None:
    mesh = _close_parallel_triangle_mesh(0.001)
    settings = SelfCollisionSettings()
    positions = [vertex for item in mesh.meshes for vertex in item.vertices]
    triangles, _ = build_triangle_refs(mesh)

    broad_phase = broad_phase_candidates(positions, triangles, settings)
    oracle = brute_force_candidate_oracle(positions, triangles, settings)
    analysis = analyze_self_collision(mesh, settings=settings)

    assert set(oracle).issubset(broad_phase)
    assert analysis.broad_phase_matches_oracle is True
    assert analysis.contacts
    assert analysis.max_penetration_meters > 0.0


def test_self_collision_projection_is_bounded_and_reduces_penetration() -> None:
    mesh = _close_parallel_triangle_mesh(0.001)
    settings = SelfCollisionSettings()
    positions = [vertex for item in mesh.meshes for vertex in item.vertices]
    triangles, _ = build_triangle_refs(mesh)
    before = analyze_self_collision(mesh, settings=settings)

    corrected_positions, diagnostics = project_self_collisions(
        positions,
        triangles,
        settings=settings,
    )
    corrected_mesh = MeshSet(
        [
            Mesh(
                mesh.meshes[0].name,
                mesh.meshes[0].panel_id,
                corrected_positions,
                mesh.meshes[0].panel_uvs,
                mesh.meshes[0].triangles,
            )
        ]
    )
    after = analyze_self_collision(corrected_mesh, settings=settings)

    assert diagnostics["totalCorrectionCount"] > 0
    assert after.max_penetration_meters < before.max_penetration_meters
    assert len(corrected_positions) == len(positions)


def test_self_collision_projection_is_symmetric_and_preserves_equal_mass_centroid() -> None:
    mesh = _close_parallel_triangle_mesh(0.001)
    settings = SelfCollisionSettings(correction_fraction=0.35, max_iterations=1)
    positions = [vertex for item in mesh.meshes for vertex in item.vertices]
    triangles, _ = build_triangle_refs(mesh)

    corrected, diagnostics = project_self_collisions(
        positions,
        triangles,
        settings=settings,
    )

    assert diagnostics["totalCorrectionCount"] > 0
    assert any(corrected[index] != positions[index] for index in range(3))
    assert any(corrected[index] != positions[index] for index in range(3, 6))
    before_centroid = tuple(sum(point[axis] for point in positions) / 6.0 for axis in range(3))
    after_centroid = tuple(sum(point[axis] for point in corrected) / 6.0 for axis in range(3))
    assert max(abs(a - b) for a, b in zip(before_centroid, after_centroid, strict=True)) < 1e-12


def test_self_collision_projection_respects_fixed_support_inverse_mass() -> None:
    mesh = _close_parallel_triangle_mesh(0.001)
    positions = [vertex for item in mesh.meshes for vertex in item.vertices]
    triangles, _ = build_triangle_refs(mesh)

    corrected, diagnostics = project_self_collisions(
        positions,
        triangles,
        fixed_indices={0, 1, 2},
        settings=SelfCollisionSettings(correction_fraction=0.35, max_iterations=1),
    )

    assert diagnostics["totalCorrectionCount"] > 0
    assert corrected[:3] == positions[:3]
    assert any(corrected[index] != positions[index] for index in range(3, 6))


def test_orientation_guard_rejects_gradual_crossing_of_frozen_rest_normal() -> None:
    reference = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    current = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.01, 1.0)]
    deltas = {2: (0.0, -0.02, 0.0)}

    accepted = _correction_preserves_local_orientation(
        current,
        reference,
        deltas,
        1.0,
        {2: ((0, 1, 2),)},
    )

    assert accepted is False


def test_uniform_grid_broad_phase_is_deterministic_and_oracle_complete() -> None:
    mesh = _close_parallel_triangle_mesh(0.001)
    settings = SelfCollisionSettings()
    positions = [vertex for item in mesh.meshes for vertex in item.vertices]
    triangles, _ = build_triangle_refs(mesh)

    first = broad_phase_candidates(positions, triangles, settings)
    second = broad_phase_candidates(positions, triangles, settings)
    oracle = brute_force_candidate_oracle(positions, triangles, settings)

    assert first == second == sorted(first)
    assert set(oracle).issubset(first)


def test_self_collision_report_documents_fixtures_and_tunnelling_limit() -> None:
    mesh = _close_parallel_triangle_mesh(0.001)
    report = build_self_collision_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        rest_mesh=mesh,
        settled_mesh=mesh,
    )

    assert report["execution"]["selfCollisionRun"] is True
    assert report["metrics"]["broadPhaseMatchesOracle"] is True
    assert report["adversarialFixtures"]["knownContact"]["status"] == "pass"
    assert report["adversarialFixtures"]["knownNonContact"]["status"] == "pass"
    assert report["adversarialFixtures"]["adjacentTriangleExclusion"]["status"] == "pass"
    assert report["adversarialFixtures"]["seamPairExclusion"]["status"] == "pass"
    assert report["adversarialFixtures"]["crossingEdges"]["status"] == "pass"
    assert report["adversarialFixtures"]["highVelocityTunnelling"]["status"] == "pass"
    assert report["adversarialFixtures"]["thinLayerSweep"]["status"] == "pass"
    assert report["adversarialFixtures"]["openingBoundarySweep"]["status"] == "pass"
    assert report["adversarialFixtures"]["boundedUnsupportedMotion"]["status"] == "pass"
    assert report["execution"]["continuousCollisionDetectionRun"] is True
    assert report["readiness"]["acceptedForProductionGpuSolver"] is False
    assert report["settings"]["residualDepthBudgetAppliesTo"] == ("self_collision_contacts_only")
    assert report["settings"]["broadPhase"] == (
        "deterministic_bounded_uniform_grid_then_inflated_aabb"
    )
    assert (
        report["metrics"]["narrowPhaseWitnessCount"]
        >= report["metrics"]["geometricallyUniqueContactCountBefore"]
    )
    assert report["metrics"]["solverConstraintCountCreated"] > 0
    assert report["metrics"]["sharedVertexExcludedPairCount"] >= 0
    assert report["metrics"]["residualViolationAboveDepthBudgetCount"] >= 0
    assert report["collisionQuantityDomains"]["bodySignedClearance"] == (
        "reported_by_independent_body_signed_distance_audit"
    )


def test_swept_collision_detects_crossing_and_fails_closed_when_bound_is_exceeded() -> None:
    mesh = _close_parallel_triangle_mesh(0.02)
    triangles, _ = build_triangle_refs(mesh)
    previous = [*mesh.meshes[0].vertices[:3], *_moving_triangle(-0.03)]
    current = [*mesh.meshes[0].vertices[:3], *_moving_triangle(0.03)]
    settings = SelfCollisionSettings()

    detected = analyze_swept_self_collision(previous, current, triangles, settings)
    rejected = analyze_swept_self_collision(
        [*mesh.meshes[0].vertices[:3], *_moving_triangle(-1.0)],
        [*mesh.meshes[0].vertices[:3], *_moving_triangle(1.0)],
        triangles,
        settings,
        maximum_substeps=8,
    )

    assert detected.supported is True
    assert detected.first_contact_fraction is not None
    assert detected.contact_count > 0
    assert rejected.supported is False
    assert rejected.status == "unsupported_motion_exceeds_bounded_substeps"


def test_package_self_collision_evidence_is_recomputed_and_not_silent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = build_demo(tmp_path)
    manifest = read_json(package / "manifest.json")
    report = read_json(package / "reports" / "self_collision_report.json")
    validation = validate_package(package)

    assert manifest["capabilities"]["selfCollisionAvailable"] is True
    assert manifest["capabilities"]["selfCollisionEvidenceAvailable"] is True
    assert "self_collision_not_run" not in manifest["warnings"]
    assert report["execution"]["selfCollisionRun"] is True
    assert report["readiness"]["acceptedForProductionGpuSolver"] is False
    assert [issue["code"] for issue in validation["issues"]] == [
        "tshirt_fit_not_accepted_for_public_fixture",
        "tshirt_fit_solver_quality_gate_partial",
        "tshirt_fit_settled_render_quality_partial",
        "cloth_settle_constraintconvergence_failed",
        "cloth_settle_collisionresolution_failed",
        "cloth_settle_strainquality_failed",
        "self_collision_unresolved_contacts",
    ]

    corrupt = clone_package(package, tmp_path / "bad_self_collision_report.closygarment")
    tampered = read_json(corrupt / "reports" / "self_collision_report.json")
    tampered["metrics"]["candidatePairCount"] += 1
    tampered["integrity"]["selfCollisionReportHash"] = hash_self_collision_report(tampered)
    write_json(corrupt / "reports" / "self_collision_report.json", tampered)

    codes = issue_codes(validate_package(corrupt))

    assert "file_hash_mismatch" in codes
    assert "self_collision_report_recompute_mismatch" in codes


def _close_parallel_triangle_mesh(distance: float) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                "fixture.close_parallel",
                "panel.fixture",
                [
                    (-0.05, 0.0, 0.0),
                    (0.05, 0.0, 0.0),
                    (0.0, 0.05, 0.0),
                    (-0.05, 0.0, distance),
                    (0.05, 0.0, distance),
                    (0.0, 0.05, distance),
                ],
                [(0.0, 0.0)] * 6,
                [(0, 1, 2), (3, 5, 4)],
            )
        ]
    )


def _moving_triangle(z: float) -> list[tuple[float, float, float]]:
    return [(-0.04, 0.005, z), (0.04, 0.005, z), (0.0, 0.045, z)]
