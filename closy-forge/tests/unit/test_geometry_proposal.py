from __future__ import annotations

from closy_forge.appearance import build_texture_identity_report
from closy_forge.capture import build_synthetic_capture_record
from closy_forge.fitting import fit_tshirt_parameters_from_visual_observations
from closy_forge.garments.tshirt.assembly import build_simulation_mesh
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.garments.tshirt.semantic_graph import build_semantic_graph
from closy_forge.geometry.glb_io import write_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.proposals import (
    PARTIAL_BINDING_VALIDATION_REJECTION_REASONS,
    PARTIAL_CLEANUP_REJECTION_REASONS,
    PARTIAL_REPAIR_RETOPOLOGY_PLAN_REJECTION_REASONS,
    PARTIAL_SEMANTIC_TRANSFER_REJECTION_REASONS,
    REQUIRED_CLEAN_REJECTION_REASONS,
    build_clean_geometry_proposal_rejection,
    build_geometry_binding_candidate_report,
    build_geometry_binding_validation_report,
    build_geometry_cleanup_plan,
    build_geometry_cleanup_result,
    build_geometry_provider_registry,
    build_geometry_repair_retopology_plan,
    build_geometry_semantic_transfer_report,
    build_manual_geometry_proposal,
    build_null_geometry_proposal,
    build_raw_geometry_topology_report,
    clean_geometry_proposal_quality_report,
    geometry_proposal_quality_report,
    hash_clean_geometry_proposal,
    hash_geometry_binding_candidate_report,
    hash_geometry_binding_validation_report,
    hash_geometry_cleanup_plan,
    hash_geometry_cleanup_result,
    hash_geometry_proposal,
    hash_geometry_repair_retopology_plan,
    hash_geometry_semantic_transfer_report,
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


def test_geometry_semantic_transfer_classifies_cleanup_preview_without_acceptance(
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
    pattern = build_tshirt_pattern(TShirtParameters())
    semantic = build_semantic_graph(pattern)
    rest_mesh, _ = build_simulation_mesh(pattern)
    asset = tmp_path / "manual_visual.glb"
    cleanup_asset = tmp_path / "manual_cleanup_preview.glb"
    write_glb(asset, rest_mesh, "manual_visual_material", (0.8, 0.8, 0.9, 1.0))
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

    semantic_transfer = build_geometry_semantic_transfer_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        semantic_graph=semantic,
        pattern=pattern,
        cleanup_result_report=cleanup_result,
        cleanup_asset_path=cleanup_asset,
    )
    clean = build_clean_geometry_proposal_rejection(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=raw,
        provider_registry=registry,
        raw_topology_report=topology,
        cleanup_plan_report=cleanup_plan,
        cleanup_result_report=cleanup_result,
        semantic_transfer_report=semantic_transfer,
    )

    assert semantic_transfer["execution"]["semanticTransferRun"] is True
    assert semantic_transfer["execution"]["boundaryClassificationRun"] is True
    assert semantic_transfer["aggregate"]["transferredPanelCount"] == 5
    assert semantic_transfer["aggregate"]["classifiedBoundaryEdgeCount"] == 218
    assert semantic_transfer["aggregate"]["unclassifiedBoundaryEdgeCount"] == 0
    assert semantic_transfer["readiness"]["acceptedForCleanProposal"] is False
    assert semantic_transfer["integrity"]["geometrySemanticTransferHash"] == (
        hash_geometry_semantic_transfer_report(semantic_transfer)
    )
    assert (
        clean["sourceGeometrySemanticTransferHash"]
        == (semantic_transfer["integrity"]["geometrySemanticTransferHash"])
    )
    assert clean["cleanupPipeline"]["semanticTransferReportGenerated"] is True
    assert clean["cleanupPipeline"]["semanticTransferRun"] is True
    assert clean["cleanupPipeline"]["boundaryClassificationRun"] is True
    assert clean["cleanupPipeline"]["simulationBindingRun"] is False
    assert set(PARTIAL_SEMANTIC_TRANSFER_REJECTION_REASONS).issubset(
        clean["quality"]["rejectionReasons"]
    )
    assert "semantic_transfer_missing" not in clean["quality"]["rejectionReasons"]
    assert clean["quality"]["acceptedForCanonical"] is False


def test_geometry_binding_candidate_maps_cleanup_preview_without_runtime_binding(
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
    pattern = build_tshirt_pattern(TShirtParameters())
    semantic = build_semantic_graph(pattern)
    rest_mesh, _ = build_simulation_mesh(pattern)
    asset = tmp_path / "manual_visual.glb"
    cleanup_asset = tmp_path / "manual_cleanup_preview.glb"
    write_glb(asset, rest_mesh, "manual_visual_material", (0.8, 0.8, 0.9, 1.0))
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
    semantic_transfer = build_geometry_semantic_transfer_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        semantic_graph=semantic,
        pattern=pattern,
        cleanup_result_report=cleanup_result,
        cleanup_asset_path=cleanup_asset,
    )

    binding_candidate = build_geometry_binding_candidate_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        semantic_transfer_report=semantic_transfer,
        cleanup_asset_path=cleanup_asset,
        simulation_mesh=rest_mesh,
        simulation_mesh_path="simulation/simulation_mesh.glb",
    )
    clean = build_clean_geometry_proposal_rejection(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=raw,
        provider_registry=registry,
        raw_topology_report=topology,
        cleanup_plan_report=cleanup_plan,
        cleanup_result_report=cleanup_result,
        semantic_transfer_report=semantic_transfer,
        binding_candidate_report=binding_candidate,
    )

    assert binding_candidate["execution"]["candidateBindingRun"] is True
    assert binding_candidate["execution"]["simulationBindingRun"] is False
    assert binding_candidate["execution"]["runtimeBindingWritten"] is False
    assert binding_candidate["aggregate"]["cleanupVertexCount"] == rest_mesh.vertex_count
    assert binding_candidate["aggregate"]["mappedVertexCount"] == rest_mesh.vertex_count
    assert binding_candidate["aggregate"]["unmappedVertexCount"] == 0
    assert binding_candidate["aggregate"]["candidateCompleteness"] == 1.0
    assert binding_candidate["readiness"]["acceptedForCleanProposal"] is False
    assert binding_candidate["integrity"]["geometryBindingCandidateHash"] == (
        hash_geometry_binding_candidate_report(binding_candidate)
    )
    assert (
        clean["sourceGeometryBindingCandidateHash"]
        == (binding_candidate["integrity"]["geometryBindingCandidateHash"])
    )
    assert clean["cleanupPipeline"]["bindingCandidateReportGenerated"] is True
    assert clean["cleanupPipeline"]["candidateBindingRun"] is True
    assert clean["cleanupPipeline"]["simulationBindingRun"] is False
    assert (
        clean["cleanGeometryAudit"]["bindingCandidateMappedVertexCount"] == rest_mesh.vertex_count
    )
    assert clean["quality"]["acceptedForCanonical"] is False


def test_geometry_binding_validation_rejects_unverified_deformation_candidate(
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
    pattern = build_tshirt_pattern(TShirtParameters())
    semantic = build_semantic_graph(pattern)
    rest_mesh, _ = build_simulation_mesh(pattern)
    settled_mesh = _offset_mesh(rest_mesh, (0.0, -0.12, 0.0))
    asset = tmp_path / "manual_visual.glb"
    cleanup_asset = tmp_path / "manual_cleanup_preview.glb"
    write_glb(asset, rest_mesh, "manual_visual_material", (0.8, 0.8, 0.9, 1.0))
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
    semantic_transfer = build_geometry_semantic_transfer_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        semantic_graph=semantic,
        pattern=pattern,
        cleanup_result_report=cleanup_result,
        cleanup_asset_path=cleanup_asset,
    )
    binding_candidate = build_geometry_binding_candidate_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        semantic_transfer_report=semantic_transfer,
        cleanup_asset_path=cleanup_asset,
        simulation_mesh=settled_mesh,
        simulation_mesh_path="simulation/simulation_mesh.glb",
    )
    binding_validation = build_geometry_binding_validation_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        binding_candidate_report=binding_candidate,
        cleanup_asset_path=cleanup_asset,
        rest_simulation_mesh=rest_mesh,
        settled_simulation_mesh=settled_mesh,
        rest_state_path="simulation/rest_state.json",
        settled_simulation_mesh_path="simulation/simulation_mesh.glb",
    )
    repair_plan = build_geometry_repair_retopology_plan(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_topology_report=topology,
        cleanup_result_report=cleanup_result,
        semantic_transfer_report=semantic_transfer,
        binding_candidate_report=binding_candidate,
        binding_validation_report=binding_validation,
    )
    clean = build_clean_geometry_proposal_rejection(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        raw_geometry_proposal=raw,
        provider_registry=registry,
        raw_topology_report=topology,
        cleanup_plan_report=cleanup_plan,
        cleanup_result_report=cleanup_result,
        semantic_transfer_report=semantic_transfer,
        binding_candidate_report=binding_candidate,
        binding_validation_report=binding_validation,
        repair_retopology_plan_report=repair_plan,
    )

    assert binding_validation["execution"]["deformationValidationRun"] is True
    assert binding_validation["execution"]["runtimeBindingAccepted"] is False
    assert binding_validation["readiness"]["status"] == (
        "deformation_validation_failed_runtime_binding_rejected"
    )
    assert binding_validation["quality"]["status"] == "failed_rejected"
    assert binding_validation["quality"]["failedCheckCount"] == 1
    assert binding_validation["quality"]["notRunCheckCount"] == 4
    assert binding_validation["aggregate"]["mappedVertexCount"] == rest_mesh.vertex_count
    assert 0.119 <= binding_validation["aggregate"]["maxCleanupToSettledOffsetMeters"] <= 0.121
    assert binding_validation["integrity"]["geometryBindingValidationHash"] == (
        hash_geometry_binding_validation_report(binding_validation)
    )
    assert repair_plan["execution"]["repairRetopologyPlanGenerated"] is True
    assert repair_plan["execution"]["repairRun"] is False
    assert repair_plan["execution"]["retopologyRun"] is False
    assert repair_plan["readiness"]["status"] == (
        "repair_retopology_plan_generated_execution_pending"
    )
    assert repair_plan["quality"]["status"] == "plan_only_rejected"
    assert repair_plan["aggregate"]["requiredOperationCount"] == 8
    assert repair_plan["aggregate"]["deformationFailedVertexCount"] == rest_mesh.vertex_count
    assert repair_plan["aggregate"]["estimatedRepairComplexity"] == "retopology_required"
    assert repair_plan["integrity"]["geometryRepairRetopologyPlanHash"] == (
        hash_geometry_repair_retopology_plan(repair_plan)
    )
    assert (
        clean["sourceGeometryBindingValidationHash"]
        == (binding_validation["integrity"]["geometryBindingValidationHash"])
    )
    assert (
        clean["sourceGeometryRepairRetopologyPlanHash"]
        == (repair_plan["integrity"]["geometryRepairRetopologyPlanHash"])
    )
    assert clean["cleanupPipeline"]["bindingValidationReportGenerated"] is True
    assert clean["cleanupPipeline"]["repairRetopologyPlanGenerated"] is True
    assert clean["cleanupPipeline"]["deformationValidationRun"] is True
    assert clean["cleanupPipeline"]["runtimeBindingAccepted"] is False
    assert clean["cleanGeometryAudit"]["bindingValidationFailedCheckCount"] == 1
    assert clean["cleanGeometryAudit"]["repairRetopologyRequiredOperationCount"] == 8
    assert set(PARTIAL_REPAIR_RETOPOLOGY_PLAN_REJECTION_REASONS).issubset(
        clean["quality"]["rejectionReasons"]
    )
    assert not set(PARTIAL_BINDING_VALIDATION_REJECTION_REASONS).issubset(
        clean["quality"]["rejectionReasons"]
    )
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


def _offset_mesh(meshset: MeshSet, delta: tuple[float, float, float]) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                name=mesh.name,
                panel_id=mesh.panel_id,
                vertices=[
                    (
                        vertex[0] + delta[0],
                        vertex[1] + delta[1],
                        vertex[2] + delta[2],
                    )
                    for vertex in mesh.vertices
                ],
                panel_uvs=mesh.panel_uvs,
                triangles=mesh.triangles,
                material_id=mesh.material_id,
            )
            for mesh in meshset.meshes
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
