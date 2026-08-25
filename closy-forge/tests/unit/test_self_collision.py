from __future__ import annotations

from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.simulation.self_collision import (
    SelfCollisionSettings,
    analyze_self_collision,
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

    assert broad_phase == oracle
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
    assert report["adversarialFixtures"]["highVelocityTunnelling"]["status"] == (
        "unsupported_high_velocity_tunnelling"
    )
    assert report["readiness"]["acceptedForProductionGpuSolver"] is False


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
        "self_collision_unresolved_contacts"
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
