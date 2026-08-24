from __future__ import annotations

from closy_forge.appearance import build_texture_identity_report
from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.binding.binary_format import write_binding
from closy_forge.capture import build_synthetic_capture_record
from closy_forge.fitting import fit_tshirt_parameters_from_visual_observations
from closy_forge.garments.tshirt.assembly import build_constraints, build_simulation_mesh
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.garments.tshirt.semantic_graph import build_semantic_graph
from closy_forge.geometry.glb_io import write_glb, write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.proposals import (
    CLEAN_ACCEPTANCE_GATE_REJECTION_REASONS,
    PARTIAL_BINDING_VALIDATION_REJECTION_REASONS,
    PARTIAL_CLEANUP_REJECTION_REASONS,
    PARTIAL_REPAIR_RESULT_REJECTION_REASONS,
    PARTIAL_REPAIR_RETOPOLOGY_PLAN_REJECTION_REASONS,
    PARTIAL_RUNTIME_BINDING_RESULT_REJECTION_REASONS,
    PARTIAL_SEMANTIC_TRANSFER_REJECTION_REASONS,
    REQUIRED_CLEAN_REJECTION_REASONS,
    build_clean_geometry_proposal_rejection,
    build_geometry_binding_candidate_report,
    build_geometry_binding_validation_report,
    build_geometry_clean_acceptance_gate_report,
    build_geometry_cleanup_plan,
    build_geometry_cleanup_result,
    build_geometry_material_uv_transfer_report,
    build_geometry_provider_registry,
    build_geometry_repair_result_report,
    build_geometry_repair_retopology_plan,
    build_geometry_runtime_binding_result_report,
    build_geometry_semantic_transfer_report,
    build_geometry_visual_shell_review_report,
    build_manual_geometry_proposal,
    build_null_geometry_proposal,
    build_proposal_runtime_binding,
    build_proposal_runtime_render_mesh,
    build_raw_geometry_topology_report,
    build_stitched_shell_assets,
    clean_geometry_proposal_quality_report,
    geometry_proposal_quality_report,
    hash_clean_geometry_proposal,
    hash_geometry_binding_candidate_report,
    hash_geometry_binding_validation_report,
    hash_geometry_clean_acceptance_gate,
    hash_geometry_cleanup_plan,
    hash_geometry_cleanup_result,
    hash_geometry_material_uv_transfer,
    hash_geometry_proposal,
    hash_geometry_repair_result,
    hash_geometry_repair_retopology_plan,
    hash_geometry_runtime_binding_result,
    hash_geometry_semantic_transfer_report,
    hash_geometry_stitched_shell_report,
    hash_geometry_visual_shell_review,
    hash_raw_geometry_topology_report,
    hash_stitched_analysis_shell,
    reproject_cleanup_preview_to_settled_simulation,
)
from closy_forge.proposals.geometry_stitched_shell import audit_stitched_shell
from closy_forge.simulation.reference_cloth_solver import settle_reference_cloth
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


def test_geometry_material_uv_transfer_accepts_authored_runtime_preview_metadata() -> None:
    runtime_result = _runtime_ready_report()
    semantic_transfer = _semantic_transfer_report()
    texture_identity = _texture_identity_report()
    render_materials = _render_materials_report()
    runtime_mesh = _tiny_mesh()

    report = build_geometry_material_uv_transfer_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        runtime_binding_result_report=runtime_result,
        semantic_transfer_report=semantic_transfer,
        texture_identity_report=texture_identity,
        render_materials=render_materials,
        runtime_render_mesh=runtime_mesh,
    )

    assert report["reportId"] == "material_uv_transfer.runtime_bound_tshirt_visual_geometry_v1"
    assert report["execution"]["uvTransferRun"] is True
    assert report["execution"]["materialTransferRun"] is True
    assert report["readiness"]["acceptedForMaterialPreview"] is True
    assert report["readiness"]["acceptedForCleanProposal"] is False
    assert report["aggregate"]["missingUvCount"] == 0
    assert report["aggregate"]["missingMaterialCount"] == 0
    assert report["integrity"]["geometryMaterialUvTransferHash"] == (
        hash_geometry_material_uv_transfer(report)
    )


def test_geometry_visual_shell_review_runs_without_clean_acceptance() -> None:
    runtime_result = _runtime_ready_report()
    semantic_transfer = _semantic_transfer_report()
    texture_identity = _texture_identity_report()
    material_transfer = build_geometry_material_uv_transfer_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        runtime_binding_result_report=runtime_result,
        semantic_transfer_report=semantic_transfer,
        texture_identity_report=texture_identity,
        render_materials=_render_materials_report(),
        runtime_render_mesh=_tiny_mesh(),
    )

    report = build_geometry_visual_shell_review_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        runtime_binding_result_report=runtime_result,
        semantic_transfer_report=semantic_transfer,
        material_uv_transfer_report=material_transfer,
        runtime_render_mesh=_tiny_mesh(),
    )

    assert report["reportId"] == "visual_shell_review.runtime_bound_tshirt_visual_geometry_v1"
    assert report["execution"]["visualFidelityReviewRun"] is False
    assert report["execution"]["renderedPixelComparisonRun"] is False
    assert report["execution"]["representationSilhouetteComparisonRun"] is False
    assert report["execution"]["sourceImageVisualComparisonRun"] is False
    assert report["execution"]["providerAppearanceComparisonRun"] is False
    assert report["execution"]["singleShellWeldProofRun"] is False
    assert report["execution"]["meshStitchOrWeldExecutionRun"] is False
    assert report["readiness"]["acceptedForVisualFidelity"] is False
    assert report["readiness"]["representationSilhouetteAccepted"] is False
    assert report["readiness"]["singleShellWeldProven"] is False
    assert report["readiness"]["meshStitchOrWeldProven"] is False
    assert report["readiness"]["acceptedForCleanProposal"] is False
    assert "representation_silhouette_comparison_not_run" in report["readiness"]["blockingReasons"]
    assert "source_image_visual_comparison_not_run" in report["readiness"]["blockingReasons"]
    assert "provider_appearance_comparison_not_run" in report["readiness"]["blockingReasons"]
    assert "mesh_stitch_or_weld_not_executed" in report["readiness"]["blockingReasons"]
    assert report["integrity"]["geometryVisualShellReviewHash"] == (
        hash_geometry_visual_shell_review(report)
    )


def test_geometry_visual_shell_review_accepts_silhouette_and_stitch_graph() -> None:
    runtime_result = _runtime_ready_report()
    semantic_transfer = _semantic_transfer_report()
    texture_identity = _texture_identity_report()
    material_transfer = build_geometry_material_uv_transfer_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        runtime_binding_result_report=runtime_result,
        semantic_transfer_report=semantic_transfer,
        texture_identity_report=texture_identity,
        render_materials=_render_materials_report(),
        runtime_render_mesh=_stitched_pair_mesh(),
    )

    report = build_geometry_visual_shell_review_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        runtime_binding_result_report=runtime_result,
        semantic_transfer_report=semantic_transfer,
        material_uv_transfer_report=material_transfer,
        runtime_render_mesh=_stitched_pair_mesh(),
        reference_simulation_mesh=_stitched_pair_mesh(),
        constraints={
            "constraints": [
                {
                    "id": "constraint.test_seam.000",
                    "seamId": "seam.test",
                    "spanA": {"meshIndex": 0, "vertexIndex": 1},
                    "spanB": {"meshIndex": 1, "vertexIndex": 0},
                }
            ]
        },
    )

    assert report["execution"]["renderedPixelComparisonRun"] is True
    assert report["visualFidelity"]["renderedPixelComparison"]["minimumIou"] == 1.0
    assert report["readiness"]["representationSilhouetteAccepted"] is True
    assert report["readiness"]["acceptedForVisualFidelity"] is False
    assert report["shellProof"]["stitchGraphConnectivityCheckRun"] is True
    assert report["shellProof"]["stitchGraphConnectable"] is True
    assert report["shellProof"]["singleShellWeldExecutionRun"] is False
    assert report["shellProof"]["meshStitchOrWeldExecutionRun"] is False
    assert report["shellProof"]["initialShellCount"] == 2
    assert report["shellProof"]["postStitchShellCount"] == 1
    assert report["readiness"]["stitchGraphConnectable"] is True
    assert report["readiness"]["singleShellWeldProven"] is False
    assert report["readiness"]["meshStitchOrWeldProven"] is False
    assert "representation_silhouette_not_accepted" not in report["readiness"]["blockingReasons"]
    assert "source_image_visual_comparison_not_run" in report["readiness"]["blockingReasons"]
    assert "mesh_stitch_or_weld_not_executed" in report["readiness"]["blockingReasons"]
    assert report["readiness"]["acceptedForCleanProposal"] is False
    assert report["integrity"]["geometryVisualShellReviewHash"] == (
        hash_geometry_visual_shell_review(report)
    )


def test_geometry_stitched_shell_outputs_material_artifacts_but_rejects_unproven_topology() -> None:
    pattern = build_tshirt_pattern(TShirtParameters())
    rest_mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)
    avatar = avatar_contract(build_reference_avatar_mesh(), build_collision_mesh())
    settled = settle_reference_cloth(
        rest_mesh,
        constraints,
        avatar,
        {"dampingRatio": 0.18},
    ).settled_mesh

    report, analysis, stitched_mesh = build_stitched_shell_assets(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        source_simulation_mesh=settled,
        constraints=constraints,
        analysis_asset_path="stitch/logical_stitched_analysis_shell.json",
        render_asset_path="render/stitched_shell.glb",
    )

    assert report["execution"]["meshStitchOrWeldExecutionRun"] is True
    assert report["execution"]["sourceVertexClassRewriteRun"] is True
    assert report["execution"]["faceIndexRewriteRun"] is True
    assert report["execution"]["analysisAssetWritten"] is False
    assert report["execution"]["renderAssetWritten"] is False
    assert report["packageWriterEvidence"]["status"] == "pending_package_writer"
    assert report["execution"]["operationCount"] == len(constraints["constraints"])
    assert report["topologyAudit"]["executedOperationCount"] == len(constraints["constraints"])
    assert report["topologyAudit"]["seamSpanCoverage"]["coverageRatio"] == 1.0
    assert report["topologyAudit"]["seamSpanCoverage"]["duplicateExecutedOperationCount"] == 5
    assert report["topologyAudit"]["logicalShellCount"] == 1
    assert report["topologyAudit"]["maxPostStitchResidualMeters"] == 0.0
    assert report["topologyAudit"]["bindingCoverage"] == 0.0
    assert report["topologyAudit"]["bindingReconstructionStatus"] == "not_run"
    assert report["topologyAudit"]["bindingEvidence"]["boundRenderVertexCount"] == 0
    assert report["topologyAudit"]["uvMaterialPanelProvenance"]["coverageRatio"] == 1.0
    assert report["topologyAudit"]["missingExpectedOpeningCount"] == 4
    assert report["topologyAudit"]["boundaryBranchVertexCount"] == 7
    assert report["topologyAudit"]["semanticOpeningAssignmentStatus"] == "fail"
    assert report["topologyAudit"]["semanticOpeningAudit"]["boundaryComponentCount"] == 3
    assert report["topologyAudit"]["semanticOpeningAudit"]["simpleBoundaryCycleCount"] == 2
    assert report["topologyAudit"]["semanticOpeningAudit"]["panelEdgeProvenanceStatus"] == "fail"
    assert report["topologyAudit"]["semanticOpeningAudit"]["failureReasons"] == [
        "boundary_branch_vertices_present",
        "boundary_component_count_mismatch",
        "panel_edge_provenance_missing",
        "semantic_assignment_incomplete",
        "simple_boundary_cycle_count_mismatch",
    ]
    assert report["topologyAudit"]["boundaryComponents"][0]["isSimpleCycle"] is False
    assert report["topologyAudit"]["boundaryComponents"][0]["perimeterMeters"] > 0.0
    assert report["topologyAudit"]["executedTopologyAuditCount"] == 5
    assert report["topologyAudit"]["tJunctionCheckStatus"] == "pass"
    assert report["topologyAudit"]["tJunctionAudit"]["tJunctionCount"] == 0
    assert report["topologyAudit"]["inconsistentWindingCheckStatus"] == "fail"
    assert report["topologyAudit"]["inconsistentWindingAudit"]["inconsistentSharedEdgeCount"] == 29
    assert report["topologyAudit"]["normalInversionCheckStatus"] == "fail"
    assert report["topologyAudit"]["normalInversionAudit"]["invertedAdjacentPairCount"] == 40
    assert report["topologyAudit"]["selfIntersectionCheckStatus"] == "fail"
    assert report["topologyAudit"]["selfIntersectionAudit"]["selfIntersectionPairCount"] == 321
    assert report["topologyAudit"]["hiddenInternalComponentCheckStatus"] == "pass"
    assert (
        report["topologyAudit"]["hiddenInternalComponentAudit"]["internalClosedComponentCount"] == 0
    )
    assert report["topologyAudit"]["sourceDisplacement"]["maxSourceDisplacementMeters"] > 0.0
    assert report["topologyAudit"]["vertexCount"] == stitched_mesh.vertex_count
    assert report["topologyAudit"]["triangleCount"] == stitched_mesh.triangle_count
    assert report["readiness"]["meshStitchOrWeldProven"] is False
    assert report["readiness"]["acceptedForCleanProposal"] is False
    assert "mesh_stitch_or_weld_not_proven" in report["readiness"]["blockingReasons"]
    assert "self_intersections_detected" in report["readiness"]["blockingReasons"]
    assert "semantic_opening_assignment_failed" in report["readiness"]["blockingReasons"]
    assert "opening_panel_edge_provenance_missing" in report["readiness"]["blockingReasons"]
    assert "self_intersection_not_run" not in report["readiness"]["blockingReasons"]
    assert (
        report["analysisAsset"]["payloadHash"] == analysis["integrity"]["stitchedAnalysisShellHash"]
    )
    assert analysis["logicalShell"]["vertexCount"] == stitched_mesh.vertex_count
    assert analysis["openingProof"]["expectedOpeningCount"] == 4
    assert analysis["openingProof"]["status"] == "fail"
    assert analysis["openingProof"]["semanticOpeningAssignmentRun"] is True
    assert analysis["openingProof"]["semanticOpeningAssignmentStatus"] == "fail"
    assert analysis["openingProof"]["candidateOpeningMappings"] == []
    assert analysis["openingProof"]["missingExpectedOpeningIds"] == [
        "opening.neck",
        "opening.hem",
        "opening.cuff.left",
        "opening.cuff.right",
    ]
    assert report["integrity"]["geometryStitchedShellHash"] == (
        hash_geometry_stitched_shell_report(report)
    )
    assert analysis["integrity"]["stitchedAnalysisShellHash"] == (
        hash_stitched_analysis_shell(analysis)
    )


def test_stitched_shell_topology_audits_fail_on_synthetic_defects() -> None:
    mesh = Mesh(
        name="synthetic_topology_defects",
        panel_id="panel.synthetic",
        vertices=[
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.5, 0.0, 0.0),
            (0.5, 0.4, 0.0),
            (0.8, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (3.0, 0.0, 0.0),
            (2.5, 0.8, 0.0),
            (2.5, 0.3, 0.8),
        ],
        panel_uvs=[(0.0, 0.0) for _ in range(10)],
        triangles=[
            (0, 1, 2),
            (3, 4, 5),
            (6, 7, 8),
            (6, 9, 7),
            (7, 9, 8),
            (8, 9, 6),
        ],
    )
    audit = audit_stitched_shell(
        MeshSet([mesh]),
        source_vertex_map=[],
        operations=[],
        constraints={"constraints": []},
    )

    assert audit["executedTopologyAuditCount"] == 5
    assert audit["tJunctionCheckStatus"] == "fail"
    assert audit["tJunctionAudit"]["tJunctionCount"] >= 1
    assert audit["hiddenInternalComponentCheckStatus"] == "fail"
    assert audit["hiddenInternalComponentAudit"]["internalClosedComponentCount"] == 1


def test_geometry_visual_shell_review_records_stitched_artifact_without_clean_proof() -> None:
    runtime_result = _runtime_ready_report()
    semantic_transfer = _semantic_transfer_report()
    texture_identity = _texture_identity_report()
    source_mesh = _stitched_pair_mesh()
    constraints = {
        "constraints": [
            {
                "id": "constraint.test_seam.000",
                "seamId": "seam.test",
                "spanA": {"meshIndex": 0, "vertexIndex": 1},
                "spanB": {"meshIndex": 1, "vertexIndex": 0},
            }
        ]
    }
    stitched_report, _analysis, _mesh = build_stitched_shell_assets(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        source_simulation_mesh=source_mesh,
        constraints=constraints,
        analysis_asset_path="stitch/logical_stitched_analysis_shell.json",
        render_asset_path="render/stitched_shell.glb",
    )
    material_transfer = build_geometry_material_uv_transfer_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        runtime_binding_result_report=runtime_result,
        semantic_transfer_report=semantic_transfer,
        texture_identity_report=texture_identity,
        render_materials=_render_materials_report(),
        runtime_render_mesh=source_mesh,
    )

    report = build_geometry_visual_shell_review_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        runtime_binding_result_report=runtime_result,
        semantic_transfer_report=semantic_transfer,
        material_uv_transfer_report=material_transfer,
        runtime_render_mesh=source_mesh,
        reference_simulation_mesh=source_mesh,
        constraints=constraints,
        stitched_shell_report=stitched_report,
    )

    assert report["shellProof"]["status"] == "fail"
    assert report["shellProof"]["meshStitchOrWeldExecutionRun"] is True
    assert report["shellProof"]["meshStitchOrWeldProven"] is False
    assert report["shellProof"]["meshStitchOrWeldOutputAssetPath"] == "render/stitched_shell.glb"
    assert "mesh_stitch_or_weld_not_executed" not in report["readiness"]["blockingReasons"]
    assert "mesh_stitch_or_weld_not_proven" in report["readiness"]["blockingReasons"]
    assert report["integrity"]["geometryVisualShellReviewHash"] == (
        hash_geometry_visual_shell_review(report)
    )


def test_geometry_clean_acceptance_gate_rejects_runtime_preview_after_material_transfer() -> None:
    runtime_result = _runtime_ready_report()
    semantic_transfer = _semantic_transfer_report()
    texture_identity = _texture_identity_report()
    material_transfer = build_geometry_material_uv_transfer_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        runtime_binding_result_report=runtime_result,
        semantic_transfer_report=semantic_transfer,
        texture_identity_report=texture_identity,
        render_materials=_render_materials_report(),
        runtime_render_mesh=_tiny_mesh(),
    )
    visual_shell_review = build_geometry_visual_shell_review_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        runtime_binding_result_report=runtime_result,
        semantic_transfer_report=semantic_transfer,
        material_uv_transfer_report=material_transfer,
        runtime_render_mesh=_tiny_mesh(),
    )
    provider_registry = _provider_registry_report()

    gate = build_geometry_clean_acceptance_gate_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        runtime_binding_result_report=runtime_result,
        semantic_transfer_report=semantic_transfer,
        texture_identity_report=texture_identity,
        material_uv_transfer_report=material_transfer,
        visual_shell_review_report=visual_shell_review,
        provider_registry=provider_registry,
    )

    assert gate["reportId"] == "clean_acceptance_gate.runtime_bound_tshirt_visual_geometry_v1"
    assert gate["execution"]["cleanAcceptanceGateRun"] is True
    assert gate["readiness"]["acceptedForRuntimeRender"] is True
    assert gate["readiness"]["acceptedForCleanProposal"] is False
    assert gate["readiness"]["acceptedForCanonical"] is False
    assert gate["readiness"]["status"] == "clean_acceptance_rejected_representation_failed"
    assert gate["quality"]["status"] == "rejected"
    assert gate["aggregate"]["checkCount"] == 13
    assert gate["aggregate"]["passedCheckCount"] == 7
    assert gate["aggregate"]["failedCheckCount"] == 2
    assert gate["aggregate"]["warningCheckCount"] == 2
    assert gate["aggregate"]["notRunCheckCount"] == 2
    assert (
        gate["aggregate"]["passedCheckCount"]
        + gate["aggregate"]["failedCheckCount"]
        + gate["aggregate"]["warningCheckCount"]
        + gate["aggregate"]["notRunCheckCount"]
        == gate["aggregate"]["checkCount"]
    )
    assert gate["execution"]["materialTransferRun"] is True
    assert gate["execution"]["visualFidelityReviewRun"] is False
    assert gate["execution"]["representationSilhouetteComparisonRun"] is False
    assert gate["execution"]["singleShellWeldProofRun"] is False
    assert gate["execution"]["meshStitchOrWeldExecutionRun"] is False
    assert set(CLEAN_ACCEPTANCE_GATE_REJECTION_REASONS).issubset(
        gate["quality"]["rejectionReasons"]
    )
    assert gate["integrity"]["geometryCleanAcceptanceGateHash"] == (
        hash_geometry_clean_acceptance_gate(gate)
    )


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
    rest_mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)
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
    repair_asset = tmp_path / "manual_repair_preview.glb"
    repair_mesh = reproject_cleanup_preview_to_settled_simulation(
        cleanup_asset_path=cleanup_asset,
        binding_candidate_report=binding_candidate,
        settled_simulation_mesh=settled_mesh,
    )
    write_indexed_glb(
        repair_asset,
        repair_mesh,
        "closy_partial_repair_reprojection_preview_v1",
        (0.68, 0.78, 0.92, 1.0),
    )
    repair_result = build_geometry_repair_result_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        repair_retopology_plan_report=repair_plan,
        binding_candidate_report=binding_candidate,
        binding_validation_report=binding_validation,
        cleanup_asset_path=cleanup_asset,
        output_asset_path=repair_asset,
        output_package_asset_path="proposals/manual_repair_preview.glb",
        output_mesh=repair_mesh,
        settled_simulation_mesh=settled_mesh,
        settled_simulation_mesh_path="simulation/simulation_mesh.glb",
    )
    runtime_asset = tmp_path / "manual_runtime_retopology_preview.glb"
    runtime_mesh, runtime_binding_seeds = build_proposal_runtime_render_mesh(settled_mesh)
    runtime_binding, runtime_binding_manifest = build_proposal_runtime_binding(
        settled_simulation_mesh=settled_mesh,
        runtime_render_mesh=runtime_mesh,
        render_binding_seeds=runtime_binding_seeds,
        target_render_path="proposals/manual_runtime_retopology_preview.glb",
    )
    write_indexed_glb(
        runtime_asset,
        runtime_mesh,
        "closy_proposal_runtime_retopology_preview_v1",
        (0.54, 0.70, 0.90, 1.0),
    )
    runtime_binding_asset = tmp_path / "proposal_sim_to_render.bin"
    write_binding(runtime_binding_asset, runtime_binding)
    runtime_result = build_geometry_runtime_binding_result_report(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        repair_result_report=repair_result,
        semantic_transfer_report=semantic_transfer,
        binding_candidate_report=binding_candidate,
        binding_validation_report=binding_validation,
        repair_asset_path=repair_asset,
        output_render_asset_path=runtime_asset,
        output_render_package_path="proposals/manual_runtime_retopology_preview.glb",
        output_binding_path=runtime_binding_asset,
        output_binding_package_path="binding/proposal_sim_to_render.bin",
        output_binding_manifest=runtime_binding_manifest,
        output_binding_manifest_package_path="binding/proposal_binding_manifest.json",
        output_render_mesh=runtime_mesh,
        settled_simulation_mesh=settled_mesh,
        settled_simulation_mesh_path="simulation/simulation_mesh.glb",
        constraints=constraints,
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
        repair_result_report=repair_result,
        runtime_binding_result_report=runtime_result,
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
    assert repair_result["execution"]["repairResultGenerated"] is True
    assert repair_result["execution"]["deformationReprojectionRun"] is True
    assert repair_result["execution"]["retopologyRun"] is False
    assert repair_result["execution"]["runtimeBindingAccepted"] is False
    assert repair_result["readiness"]["status"] == "partial_repair_completed_retopology_pending"
    assert repair_result["quality"]["status"] == "partial_repair_rejected"
    assert repair_result["aggregate"]["movedVertexCount"] == rest_mesh.vertex_count
    assert repair_result["aggregate"]["deferredOperationCount"] == 7
    assert repair_result["aggregate"]["maxOutputToSettledOffsetMeters"] == 0.0
    assert repair_result["integrity"]["geometryRepairResultHash"] == (
        hash_geometry_repair_result(repair_result)
    )
    assert runtime_result["execution"]["runtimeBindingResultGenerated"] is True
    assert runtime_result["execution"]["retopologyRun"] is True
    assert runtime_result["execution"]["seamSplitRun"] is True
    assert runtime_result["execution"]["componentStitchingRun"] is True
    assert runtime_result["execution"]["runtimeBindingWritten"] is True
    assert runtime_result["execution"]["runtimeBindingAccepted"] is False
    assert runtime_result["readiness"]["status"] == "runtime_binding_generated_but_rejected"
    assert runtime_result["quality"]["status"] == "runtime_binding_failed_rejected"
    assert runtime_result["aggregate"]["runtimeBindingRecordCount"] == runtime_mesh.vertex_count
    assert runtime_result["aggregate"]["maxReconstructionError"] == 0.0
    assert runtime_result["readiness"]["acceptedForCleanProposal"] is False
    assert runtime_result["integrity"]["geometryRuntimeBindingResultHash"] == (
        hash_geometry_runtime_binding_result(runtime_result)
    )
    assert (
        clean["sourceGeometryBindingValidationHash"]
        == (binding_validation["integrity"]["geometryBindingValidationHash"])
    )
    assert (
        clean["sourceGeometryRepairRetopologyPlanHash"]
        == (repair_plan["integrity"]["geometryRepairRetopologyPlanHash"])
    )
    assert (
        clean["sourceGeometryRepairResultHash"]
        == (repair_result["integrity"]["geometryRepairResultHash"])
    )
    assert (
        clean["sourceGeometryRuntimeBindingResultHash"]
        == (runtime_result["integrity"]["geometryRuntimeBindingResultHash"])
    )
    assert clean["cleanupPipeline"]["bindingValidationReportGenerated"] is True
    assert clean["cleanupPipeline"]["repairRetopologyPlanGenerated"] is True
    assert clean["cleanupPipeline"]["partialRepairResultGenerated"] is True
    assert clean["cleanupPipeline"]["runtimeBindingResultGenerated"] is True
    assert clean["cleanupPipeline"]["deformationValidationRun"] is True
    assert clean["cleanupPipeline"]["deformationReprojectionRun"] is True
    assert clean["cleanupPipeline"]["retopologyRun"] is True
    assert clean["cleanupPipeline"]["seamSplitRun"] is True
    assert clean["cleanupPipeline"]["componentStitchingRun"] is True
    assert clean["cleanupPipeline"]["runtimeBindingWritten"] is True
    assert clean["cleanupPipeline"]["simulationBindingRun"] is False
    assert clean["cleanupPipeline"]["runtimeBindingAccepted"] is False
    assert clean["cleanGeometryAudit"]["bindingValidationFailedCheckCount"] == 1
    assert clean["cleanGeometryAudit"]["repairRetopologyRequiredOperationCount"] == 8
    assert clean["cleanGeometryAudit"]["repairResultMovedVertexCount"] == rest_mesh.vertex_count
    assert clean["cleanGeometryAudit"]["repairResultDeferredOperationCount"] == 7
    assert clean["cleanGeometryAudit"]["runtimeBindingRecordCount"] == runtime_mesh.vertex_count
    assert clean["cleanGeometryAudit"]["runtimeBindingAccepted"] is False
    assert set(PARTIAL_REPAIR_RESULT_REJECTION_REASONS).issubset(
        clean["quality"]["rejectionReasons"]
    )
    assert not set(PARTIAL_RUNTIME_BINDING_RESULT_REJECTION_REASONS).issubset(
        clean["quality"]["rejectionReasons"]
    )
    assert not set(PARTIAL_REPAIR_RETOPOLOGY_PLAN_REJECTION_REASONS).issubset(
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


def _runtime_ready_report() -> dict[str, object]:
    return {
        "reportId": "runtime_binding_result.cleanup_preview_tshirt_visual_geometry_v1",
        "integrity": {"geometryRuntimeBindingResultHash": "0" * 64},
        "execution": {"runtimeBindingAccepted": True},
        "readiness": {"acceptedForRuntimeRender": True},
        "aggregate": {
            "runtimeBindingRecordCount": 1308,
            "runtimeRenderVertexCount": 1308,
            "runtimeRenderTriangleCount": 872,
            "maxReconstructionError": 0.0,
            "rmsReconstructionError": 0.0,
            "maxSeamPairDistanceMeters": 0.131918884,
            "rmsSeamPairDistanceMeters": 0.033197204,
            "maxNormalAngleDegrees": 57.5,
            "maxTangentAngleDegrees": 61.25,
        },
        "retopology": {
            "providerTopologyRetainedForRuntime": False,
            "vertexWeldedSingleShell": False,
        },
        "seamContinuity": {
            "normalContinuityStatus": "warn",
            "tangentContinuityStatus": "warn",
            "thresholds": {
                "warnNormalAngleDegrees": 45.0,
                "warnTangentAngleDegrees": 45.0,
            },
        },
        "outputRenderAsset": {
            "path": "proposals/manual_runtime_retopology_preview.glb",
            "sourceAssetHash": "1" * 64,
            "runtimePreviewUseAllowed": True,
        },
        "outputBinding": {
            "path": "binding/proposal_sim_to_render.bin",
            "sourceAssetHash": "2" * 64,
        },
    }


def _semantic_transfer_report() -> dict[str, object]:
    return {
        "reportId": "semantic_transfer.cleanup_preview_tshirt_visual_geometry_v1",
        "integrity": {"geometrySemanticTransferHash": "3" * 64},
        "aggregate": {
            "transferredPanelCount": 5,
            "expectedPanelCount": 5,
            "classificationCompleteness": 1.0,
        },
    }


def _texture_identity_report() -> dict[str, object]:
    return {
        "textureIdentityId": "texture.synthetic_tshirt_identity_v1",
        "integrity": {"textureIdentityHash": "4" * 64},
        "sourceTextureAvailable": False,
        "generatedAtlasAvailable": False,
        "textureProjectionRun": False,
        "observedMaterialRegions": [
            {
                "regionId": "texture.region.00",
                "materialId": "material.cotton_jersey_reference_v1",
                "label": "Fixture cotton jersey blue",
                "evidenceKind": "authored_fixture_pbr_not_photo_recovered",
                "pbr": {
                    "baseColorFactor": [0.08, 0.26, 0.78, 1.0],
                    "roughnessFactor": 0.86,
                    "metallicFactor": 0.0,
                },
                "textureSource": "authored_color_only_until_source_projection",
            }
        ],
        "pbrSafety": {
            "materialModel": "mobile_safe_mesh_standard_pbr",
            "maxTextureSizePx": 1024,
            "unsupportedAdvancedShading": [
                "transmission",
                "dispersion",
                "clearcoat",
                "subsurface_scattering",
            ],
        },
    }


def _render_materials_report() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "materials": [
            {
                "id": "material.cotton_jersey_reference_v1",
                "label": "Fixture cotton jersey blue",
                "pbr": {
                    "baseColorFactor": [0.08, 0.26, 0.78, 1.0],
                    "roughnessFactor": 0.86,
                    "metallicFactor": 0.0,
                },
                "textureSource": "authored_color_only",
            }
        ],
    }


def _provider_registry_report() -> dict[str, object]:
    return {
        "registryId": "provider_registry.geometry_tshirt_reference_v1",
        "integrity": {"providerRegistryHash": "5" * 64},
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
    }


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


def _stitched_pair_mesh() -> MeshSet:
    return MeshSet(
        [
            Mesh(
                name="left_panel_triangle",
                panel_id="panel.left",
                vertices=[(0.0, 0.0, 0.0), (0.5, 0.0, 0.0), (0.0, 0.5, 0.0)],
                panel_uvs=[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
                triangles=[(0, 1, 2)],
            ),
            Mesh(
                name="right_panel_triangle",
                panel_id="panel.right",
                vertices=[(0.5, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 0.5, 0.0)],
                panel_uvs=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
                triangles=[(0, 1, 2)],
            ),
        ]
    )
