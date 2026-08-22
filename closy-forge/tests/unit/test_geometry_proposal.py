from __future__ import annotations

from closy_forge.appearance import build_texture_identity_report
from closy_forge.capture import build_synthetic_capture_record
from closy_forge.fitting import fit_tshirt_parameters_from_visual_observations
from closy_forge.geometry.glb_io import write_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.proposals import (
    PARTIAL_CLEANUP_REJECTION_REASONS,
    REQUIRED_CLEAN_REJECTION_REASONS,
    build_clean_geometry_proposal_rejection,
    build_geometry_cleanup_plan,
    build_geometry_cleanup_result,
    build_geometry_provider_registry,
    build_manual_geometry_proposal,
    build_null_geometry_proposal,
    build_raw_geometry_topology_report,
    clean_geometry_proposal_quality_report,
    geometry_proposal_quality_report,
    hash_clean_geometry_proposal,
    hash_geometry_cleanup_plan,
    hash_geometry_cleanup_result,
    hash_geometry_proposal,
    hash_raw_geometry_topology_report,
)
from closy_forge.visual_understanding import build_tshirt_visual_observations


def test_null_geometry_proposal_is_deterministic_and_rejected() -> None:
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    fit = fit_tshirt_parameters_from_visual_observations(visual)
    texture = build_texture_identity_report(
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        render_materials={"schemaVersion": 1, "materials": []},
    )

    first = build_null_geometry_proposal(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
    )
    second = build_null_geometry_proposal(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
    )
    quality = geometry_proposal_quality_report(first)

    assert first == second
    assert first["rawProposal"]["available"] is False
    assert first["cleanProposal"]["available"] is False
    assert first["quality"]["status"] == "rejected"
    assert first["quality"]["acceptedForCanonical"] is False
    assert first["request"]["supportedDomain"] == "avatar_garment_only"
    assert first["integrity"]["geometryProposalHash"] == hash_geometry_proposal(first)
    assert quality["status"] == "rejected"
    assert quality["failureReason"] == "null_provider_no_geometry_generated"


def test_manual_geometry_proposal_audits_glb_and_remains_non_canonical(tmp_path) -> None:  # type: ignore[no-untyped-def]
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    fit = fit_tshirt_parameters_from_visual_observations(visual)
    texture = build_texture_identity_report(
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        render_materials={"schemaVersion": 1, "materials": []},
    )
    asset = tmp_path / "manual_visual.glb"
    write_glb(asset, _tiny_mesh(), "manual_visual_material", (0.8, 0.8, 0.9, 1.0))

    proposal = build_manual_geometry_proposal(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
        asset_path=asset,
        package_asset_path="proposals/manual_visual.glb",
    )
    quality = geometry_proposal_quality_report(proposal)

    assert proposal["provider"]["providerId"] == "closy.manual_local_glb_import.v1"
    assert proposal["rawProposal"]["available"] is True
    assert proposal["rawProposal"]["noCanonicalUse"] is True
    assert proposal["cleanProposal"]["available"] is False
    assert proposal["quality"]["status"] == "accepted_visual_reference"
    assert proposal["quality"]["acceptedForCanonical"] is False
    assert proposal["quality"]["acceptedForVisualReference"] is True
    assert proposal["geometryAudit"]["triangleEstimate"] == 1
    assert proposal["integrity"]["geometryProposalHash"] == hash_geometry_proposal(proposal)
    assert quality["status"] == "accepted_visual_reference"


def test_clean_geometry_proposal_rejects_uncleaned_raw_visual_reference(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    fit = fit_tshirt_parameters_from_visual_observations(visual)
    texture = build_texture_identity_report(
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        render_materials={"schemaVersion": 1, "materials": []},
    )
    asset = tmp_path / "manual_visual.glb"
    write_glb(asset, _tiny_mesh(), "manual_visual_material", (0.8, 0.8, 0.9, 1.0))
    raw = build_manual_geometry_proposal(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
        asset_path=asset,
        package_asset_path="proposals/manual_visual.glb",
    )
    registry = build_geometry_provider_registry(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
        geometry_proposal=raw,
        manual_asset_path=asset,
        manual_asset_rights_reviewed=True,
        manual_asset_rights_status="project_authored_fixture_no_third_party_asset",
    )
    topology = build_raw_geometry_topology_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=raw,
        asset_path=asset,
    )
    cleanup_plan = build_geometry_cleanup_plan(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=raw,
        raw_topology_report=topology,
    )

    clean = build_clean_geometry_proposal_rejection(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=raw,
        provider_registry=registry,
        raw_topology_report=topology,
        cleanup_plan_report=cleanup_plan,
    )
    quality = clean_geometry_proposal_quality_report(clean)

    assert clean["sourceRawProposalHash"] == raw["integrity"]["geometryProposalHash"]
    assert clean["sourceProviderRegistryHash"] == registry["integrity"]["providerRegistryHash"]
    assert (
        clean["sourceRawTopologyReportHash"]
        == topology["integrity"]["rawGeometryTopologyReportHash"]
    )
    assert (
        clean["sourceGeometryCleanupPlanHash"]
        == cleanup_plan["integrity"]["geometryCleanupPlanHash"]
    )
    assert clean["cleanProposal"]["available"] is False
    assert clean["quality"]["status"] == "rejected"
    assert clean["quality"]["acceptedForCanonical"] is False
    assert clean["cleanupPipeline"]["topologyDiagnosticsRun"] is True
    assert clean["cleanupPipeline"]["cleanupPlanGenerated"] is True
    assert clean["cleanupPipeline"]["cleanupRun"] is False
    assert clean["cleanupPipeline"]["semanticTransferRun"] is False
    assert clean["cleanGeometryAudit"]["connectedComponentCount"] == 1
    assert clean["cleanGeometryAudit"]["cleanupPlanStatus"] == "blocked_not_executed"
    assert set(REQUIRED_CLEAN_REJECTION_REASONS).issubset(clean["quality"]["rejectionReasons"])
    assert clean["integrity"]["cleanGeometryProposalHash"] == hash_clean_geometry_proposal(clean)
    assert quality["status"] == "rejected"
    assert quality["cleanProposalAvailable"] is False


def test_raw_geometry_topology_report_reads_glb_and_rejects_clean_readiness(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    fit = fit_tshirt_parameters_from_visual_observations(visual)
    texture = build_texture_identity_report(
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        render_materials={"schemaVersion": 1, "materials": []},
    )
    asset = tmp_path / "manual_visual.glb"
    write_glb(asset, _tiny_mesh(), "manual_visual_material", (0.8, 0.8, 0.9, 1.0))
    raw = build_manual_geometry_proposal(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
        asset_path=asset,
        package_asset_path="proposals/manual_visual.glb",
    )

    topology = build_raw_geometry_topology_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=raw,
        asset_path=asset,
    )

    assert topology["inputAudit"]["triangleEstimate"] == 1
    assert topology["topology"]["componentCount"] == 1
    assert topology["topology"]["boundaryEdgeCount"] == 3
    assert topology["topology"]["nonManifoldEdgeCount"] == 0
    assert topology["topology"]["degenerateTriangleCount"] == 0
    assert topology["cleanReadiness"]["acceptedForCleanProposal"] is False
    assert topology["integrity"]["rawGeometryTopologyReportHash"] == (
        hash_raw_geometry_topology_report(topology)
    )


def test_geometry_cleanup_plan_recommends_required_repairs_without_acceptance(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    fit = fit_tshirt_parameters_from_visual_observations(visual)
    texture = build_texture_identity_report(
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        render_materials={"schemaVersion": 1, "materials": []},
    )
    asset = tmp_path / "manual_visual.glb"
    write_glb(asset, _tiny_mesh(), "manual_visual_material", (0.8, 0.8, 0.9, 1.0))
    raw = build_manual_geometry_proposal(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
        asset_path=asset,
        package_asset_path="proposals/manual_visual.glb",
    )
    topology = build_raw_geometry_topology_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=raw,
        asset_path=asset,
    )

    cleanup_plan = build_geometry_cleanup_plan(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=raw,
        raw_topology_report=topology,
    )
    operations = {
        operation["operationId"]: operation for operation in cleanup_plan["recommendedOperations"]
    }

    assert (
        cleanup_plan["sourceRawTopologyReportHash"]
        == topology["integrity"]["rawGeometryTopologyReportHash"]
    )
    assert cleanup_plan["topologySnapshot"]["boundaryEdgeCount"] == 3
    assert operations["boundary_loop_classification"]["required"] is True
    assert operations["non_manifold_edge_repair"]["required"] is False
    assert operations["degenerate_triangle_removal"]["required"] is False
    assert cleanup_plan["execution"]["cleanupRun"] is False
    assert cleanup_plan["execution"]["repairRun"] is False
    assert cleanup_plan["readiness"]["status"] == "blocked_not_executed"
    assert cleanup_plan["readiness"]["acceptedForCleanProposal"] is False
    assert cleanup_plan["integrity"]["geometryCleanupPlanHash"] == (
        hash_geometry_cleanup_plan(cleanup_plan)
    )


def test_geometry_cleanup_result_welds_preview_without_clean_acceptance(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    fit = fit_tshirt_parameters_from_visual_observations(visual)
    texture = build_texture_identity_report(
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        render_materials={"schemaVersion": 1, "materials": []},
    )
    asset = tmp_path / "manual_visual.glb"
    cleanup_asset = tmp_path / "manual_cleanup_preview.glb"
    write_glb(asset, _quad_mesh(), "manual_visual_material", (0.8, 0.8, 0.9, 1.0))
    raw = build_manual_geometry_proposal(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
        asset_path=asset,
        package_asset_path="proposals/manual_visual.glb",
    )
    registry = build_geometry_provider_registry(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
        geometry_proposal=raw,
        manual_asset_path=asset,
        manual_asset_rights_reviewed=True,
        manual_asset_rights_status="project_authored_fixture_no_third_party_asset",
    )
    topology = build_raw_geometry_topology_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=raw,
        asset_path=asset,
    )
    cleanup_plan = build_geometry_cleanup_plan(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=raw,
        raw_topology_report=topology,
    )

    cleanup_result = build_geometry_cleanup_result(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=raw,
        raw_topology_report=topology,
        cleanup_plan_report=cleanup_plan,
        source_asset_path=asset,
        output_asset_path=cleanup_asset,
        output_package_asset_path="proposals/manual_cleanup_preview.glb",
    )
    clean = build_clean_geometry_proposal_rejection(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=raw,
        provider_registry=registry,
        raw_topology_report=topology,
        cleanup_plan_report=cleanup_plan,
        cleanup_result_report=cleanup_result,
    )

    assert cleanup_asset.exists()
    assert cleanup_result["execution"]["cleanupRun"] is True
    assert cleanup_result["execution"]["repairRun"] is False
    assert cleanup_result["topologyBefore"]["duplicatePositionCount"] == 2
    assert cleanup_result["topologyAfter"]["duplicatePositionCount"] == 0
    assert cleanup_result["topologyBefore"]["vertexCount"] == 6
    assert cleanup_result["topologyAfter"]["vertexCount"] == 4
    assert cleanup_result["executedOperations"][0]["operationId"] == "duplicate_position_weld"
    assert cleanup_result["executedOperations"][0]["removedCount"] == 2
    assert cleanup_result["readiness"]["status"] == "partial_cleanup_completed"
    assert cleanup_result["readiness"]["acceptedForCleanProposal"] is False
    assert cleanup_result["integrity"]["geometryCleanupResultHash"] == (
        hash_geometry_cleanup_result(cleanup_result)
    )
    assert (
        clean["sourceGeometryCleanupResultHash"]
        == (cleanup_result["integrity"]["geometryCleanupResultHash"])
    )
    assert clean["cleanupPipeline"]["cleanupResultGenerated"] is True
    assert clean["cleanupPipeline"]["cleanupRun"] is True
    assert clean["cleanupPipeline"]["repairRun"] is False
    assert clean["cleanGeometryAudit"]["cleanupResultStatus"] == "partial_cleanup_completed"
    assert clean["cleanGeometryAudit"]["postCleanupDuplicatePositionCount"] == 0
    assert set(PARTIAL_CLEANUP_REJECTION_REASONS).issubset(clean["quality"]["rejectionReasons"])
    assert clean["quality"]["acceptedForCanonical"] is False


def _tiny_mesh() -> MeshSet:
    return MeshSet(
        [
            Mesh(
                name="manual_candidate_triangle",
                panel_id="panel.front",
                vertices=[(0.0, 0.0, 0.0), (0.12, 0.0, 0.0), (0.0, 0.12, 0.0)],
                panel_uvs=[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
                triangles=[(0, 1, 2)],
            )
        ]
    )


def _quad_mesh() -> MeshSet:
    return MeshSet(
        [
            Mesh(
                name="manual_candidate_quad",
                panel_id="panel.front",
                vertices=[
                    (0.0, 0.0, 0.0),
                    (0.12, 0.0, 0.0),
                    (0.12, 0.12, 0.0),
                    (0.0, 0.12, 0.0),
                ],
                panel_uvs=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
                triangles=[(0, 1, 2), (0, 2, 3)],
            )
        ]
    )
