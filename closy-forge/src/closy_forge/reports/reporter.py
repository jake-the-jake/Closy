from __future__ import annotations

from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import read_json


def summarize_package(package_dir: Path) -> dict[str, Any]:
    manifest = read_json(package_dir / "manifest.json")
    summary = read_json(package_dir / "reports" / "summary.json")
    binding = read_json(package_dir / "binding" / "binding_manifest.json")
    capture = read_json(package_dir / "source" / "capture_quality.json")
    visual = read_json(package_dir / "source" / "visual_observations.json")
    correction = read_json(package_dir / "source" / "correction_record.json")
    multiview = read_json(package_dir / "source" / "multiview_fusion.json")
    fitting = read_json(package_dir / "fitting" / "tshirt_fit.json")
    texture = read_json(package_dir / "textures" / "texture_identity.json")
    proposal = read_json(package_dir / "proposals" / "raw_geometry_proposal.json")
    raw_topology = read_json(package_dir / "reports" / "raw_geometry_topology.json")
    cleanup_plan = read_json(package_dir / "reports" / "geometry_cleanup_plan.json")
    cleanup_result = read_json(package_dir / "reports" / "geometry_cleanup_result.json")
    semantic_transfer = read_json(package_dir / "reports" / "geometry_semantic_transfer.json")
    binding_candidate = read_json(package_dir / "reports" / "geometry_binding_candidate.json")
    binding_validation = read_json(package_dir / "reports" / "geometry_binding_validation.json")
    repair_plan = read_json(package_dir / "reports" / "geometry_repair_retopology_plan.json")
    repair_result = read_json(package_dir / "reports" / "geometry_repair_result.json")
    runtime_binding_result = read_json(
        package_dir / "reports" / "geometry_runtime_binding_result.json"
    )
    material_uv_transfer = read_json(package_dir / "reports" / "geometry_material_uv_transfer.json")
    visual_shell_review = read_json(package_dir / "reports" / "geometry_visual_shell_review.json")
    inspection_manifest = read_json(package_dir / "reports" / "inspection" / "manifest.json")
    inspection_report = read_json(package_dir / "reports" / "inspection" / "inspection_report.json")
    clean_acceptance_gate = read_json(
        package_dir / "reports" / "geometry_clean_acceptance_gate.json"
    )
    clean_proposal = read_json(package_dir / "proposals" / "clean_geometry_proposal.json")
    provider_registry = read_json(package_dir / "proposals" / "provider_registry.json")
    provider_bakeoff = read_json(package_dir / "reports" / "provider_bakeoff.json")
    production_binding_c3 = read_json(package_dir / "reports" / "production_binding_c3.json")
    self_collision_report = read_json(package_dir / "reports" / "self_collision_report.json")
    settle = read_json(package_dir / "simulation" / "settle_diagnostics.json")
    validation = read_json(package_dir / "reports" / "package_validation.json")
    return {
        "schemaVersion": manifest["schemaVersion"],
        "garmentId": manifest["garmentId"],
        "garmentClass": manifest["garmentClass"],
        "avatarContractId": manifest["avatar"]["contractId"],
        "coordinateConvention": manifest["coordinateConvention"]["id"],
        "packageDigest": manifest["canonicalPackageDigest"],
        "seed": manifest["seed"],
        "buildProfile": manifest["buildProfile"],
        "capabilities": manifest["capabilities"],
        "counts": summary["counts"],
        "packageByteSize": sum(entry["byteSize"] for entry in manifest["inventory"]),
        "fileSizes": {entry["path"]: entry["byteSize"] for entry in manifest["inventory"]},
        "topologyHashes": manifest["hashes"],
        "binding": {
            "recordCount": binding["recordCount"],
            "maxError": binding["maximumReconstructionError"],
            "rmsError": binding["rmsReconstructionError"],
        },
        "capture": {
            "sourceRecordId": capture["sourceRecordId"],
            "viewCount": capture["viewCount"],
            "overallStatus": capture["overallStatus"],
            "overallScore": capture["overallScore"],
            "scorerVersion": capture["scorerVersion"],
        },
        "visualUnderstanding": {
            "visualUnderstandingId": visual["visualUnderstandingId"],
            "stageVersion": visual["stageVersion"],
            "providerAlgorithmVersion": visual["provider"].get("algorithmVersion"),
            "maskCount": visual["aggregate"]["maskCount"],
            "targetGarmentMaskCount": visual["aggregate"].get("targetGarmentMaskCount", 0),
            "personBodyProxyMaskCount": visual["aggregate"].get("personBodyProxyMaskCount", 0),
            "backgroundMaskCount": visual["aggregate"].get("backgroundMaskCount", 0),
            "occlusionUncertaintyMaskCount": visual["aggregate"].get(
                "occlusionUncertaintyMaskCount",
                0,
            ),
            "semanticPartCount": visual["aggregate"].get("semanticPartCount", 0),
            "openingBoundaryCount": visual["aggregate"].get("openingBoundaryCount", 0),
            "pixelDerivedViewCount": visual["aggregate"].get("pixelDerivedViewCount", 0),
            "observedLandmarkCount": len(visual["aggregate"]["observedLandmarks"]),
            "requiredLandmarkCount": len(visual["aggregate"]["requiredLandmarks"]),
            "meanMaskConfidence": visual["aggregate"]["meanMaskConfidence"],
            "meanLandmarkConfidence": visual["aggregate"]["meanLandmarkConfidence"],
            "meanMaskIoU": visual["aggregate"].get("meanMaskIoU"),
            "meanBoundaryFScore": visual["aggregate"].get("meanBoundaryFScore"),
            "meanSemanticPartIoU": visual["aggregate"].get("meanSemanticPartIoU"),
            "meanLandmarkErrorNormalised": visual["aggregate"].get("meanLandmarkErrorNormalised"),
            "openingPrecision": visual["aggregate"].get("openingPrecision"),
            "openingRecall": visual["aggregate"].get("openingRecall"),
            "correctionRecordId": correction["correctionRecordId"],
            "correctionOperationCount": len(correction["operations"]),
            "correctionApplicationStatus": correction.get("application", {}).get("status"),
        },
        "multiviewFusion": {
            "fusionRecordId": multiview["fusionRecordId"],
            "stageVersion": multiview["stageVersion"],
            "status": multiview["qualityGate"]["status"],
            "viewCount": multiview["fusedEvidence"]["viewCount"],
            "requiredPairStatus": multiview["viewPairing"]["requiredPairs"][0]["status"],
            "optionalRoleCount": len(multiview["viewPairing"]["optionalRoles"]),
            "fusedMaskCount": len(multiview["fusedEvidence"]["masks"]),
            "fusedLandmarkCount": len(multiview["fusedEvidence"]["landmarks"]),
            "fusedOpeningCount": len(multiview["fusedEvidence"]["openings"]),
            "registrationStatus": multiview["registration"]["status"],
            "correctionReplayStatus": multiview["correctionReplay"]["status"],
            "expensiveDownstreamAllowed": multiview["qualityGate"]["readiness"][
                "expensiveDownstreamAllowed"
            ],
            "cacheKey": multiview["orchestration"]["cacheKey"],
        },
        "fitting": {
            "fitReportId": fitting["fitReportId"],
            "fitterVersion": fitting["fitterVersion"],
            "method": fitting["method"],
            "status": fitting["status"],
            "accepted": fitting["accepted"],
            "landmarkRmsNormalised": fitting["losses"]["landmarkRmsNormalised"],
            "maskWidthErrorMeters": fitting["losses"]["maskWidthErrorMeters"],
            "multiviewSilhouetteMeanIoU": fitting["losses"].get("multiviewSilhouetteMeanIoU"),
            "boundaryErrorNormalised": fitting["losses"].get("boundaryErrorNormalised"),
            "openingAlignmentErrorNormalised": fitting["losses"].get(
                "openingAlignmentErrorNormalised"
            ),
            "confidenceWeightedLoss": fitting["losses"].get("confidenceWeightedLoss"),
            "optimizationIterations": fitting.get("convergence", {}).get("iterationCount", 0),
            "heldOutStatus": fitting.get("heldOutEvaluation", {}).get("status"),
            "perturbationStatus": fitting.get("perturbationEvaluation", {}).get("status"),
        },
        "texture": {
            "textureIdentityId": texture["textureIdentityId"],
            "status": texture["status"],
            "sourceTextureAvailable": texture["sourceTextureAvailable"],
            "generatedAtlasAvailable": texture["generatedAtlasAvailable"],
            "textureProjectionRun": texture["textureProjectionRun"],
            "materialRegionCount": len(texture["observedMaterialRegions"]),
            "recommendedAtlasSizePx": texture["projectionPlan"]["recommendedAtlasSizePx"],
            "sourceProjectionCount": texture["sourceViewProjection"]["projectionCount"],
            "visibleProjectionCount": texture["sourceViewProjection"]["visibleProjectionCount"],
            "meanVisibleConfidence": texture["visibleRegionConfidence"]["meanVisibleConfidence"],
            "pbrSourceBackedMapCount": texture["pbrMaterialMaps"]["sourceBackedMapCount"],
            "pbrPlaceholderMapCount": texture["pbrMaterialMaps"]["placeholderMapCount"],
        },
        "geometryProposal": {
            "proposalId": proposal["proposalId"],
            "providerId": proposal["provider"]["providerId"],
            "providerKind": proposal["provider"]["providerKind"],
            "qualityStatus": proposal["quality"]["status"],
            "rawProposalAvailable": proposal["rawProposal"]["available"],
            "cleanProposalAvailable": proposal["cleanProposal"]["available"],
            "acceptedForCanonical": proposal["quality"]["acceptedForCanonical"],
            "meshCount": proposal["geometryAudit"]["meshCount"],
            "visibleMeshCount": proposal["geometryAudit"]["visibleMeshCount"],
            "triangleEstimate": proposal["geometryAudit"]["triangleEstimate"],
            "failureReason": proposal["geometryAudit"]["failureReason"],
        },
        "rawGeometryTopology": {
            "reportId": raw_topology["reportId"],
            "sourceRawProposalId": raw_topology["sourceRawProposalId"],
            "meshCount": raw_topology["topology"]["meshCount"],
            "componentCount": raw_topology["topology"]["componentCount"],
            "largestComponentTriangleCount": raw_topology["topology"][
                "largestComponentTriangleCount"
            ],
            "boundaryEdgeCount": raw_topology["topology"]["boundaryEdgeCount"],
            "nonManifoldEdgeCount": raw_topology["topology"]["nonManifoldEdgeCount"],
            "degenerateTriangleCount": raw_topology["topology"]["degenerateTriangleCount"],
            "duplicatePositionCount": raw_topology["topology"]["duplicatePositionCount"],
            "manifoldStatus": raw_topology["topology"]["manifoldStatus"],
            "acceptedForCleanProposal": raw_topology["cleanReadiness"]["acceptedForCleanProposal"],
        },
        "geometryCleanupPlan": {
            "reportId": cleanup_plan["reportId"],
            "sourceRawProposalId": cleanup_plan["sourceRawProposalId"],
            "sourceRawTopologyReportId": cleanup_plan["sourceRawTopologyReportId"],
            "status": cleanup_plan["readiness"]["status"],
            "estimatedRepairComplexity": cleanup_plan["readiness"]["estimatedRepairComplexity"],
            "recommendedOperationCount": len(cleanup_plan["recommendedOperations"]),
            "requiredOperationCount": sum(
                1 for operation in cleanup_plan["recommendedOperations"] if operation["required"]
            ),
            "cleanupRun": cleanup_plan["execution"]["cleanupRun"],
            "repairRun": cleanup_plan["execution"]["repairRun"],
            "acceptedForCleanProposal": cleanup_plan["readiness"]["acceptedForCleanProposal"],
        },
        "geometryCleanupResult": {
            "reportId": cleanup_result["reportId"],
            "sourceGeometryCleanupPlanId": cleanup_result["sourceGeometryCleanupPlanId"],
            "status": cleanup_result["readiness"]["status"],
            "outputAssetPath": cleanup_result["outputAsset"]["path"],
            "cleanupRun": cleanup_result["execution"]["cleanupRun"],
            "repairRun": cleanup_result["execution"]["repairRun"],
            "verticesBefore": cleanup_result["topologyBefore"]["vertexCount"],
            "verticesAfter": cleanup_result["topologyAfter"]["vertexCount"],
            "duplicatePositionCountBefore": cleanup_result["topologyBefore"][
                "duplicatePositionCount"
            ],
            "duplicatePositionCountAfter": cleanup_result["topologyAfter"][
                "duplicatePositionCount"
            ],
            "removedDuplicateVertexCount": _operation_removed_count(
                cleanup_result, "duplicate_position_weld"
            ),
            "removedDegenerateTriangleCount": _operation_removed_count(
                cleanup_result, "degenerate_triangle_removal"
            ),
            "deferredOperationCount": len(cleanup_result["deferredOperations"]),
            "acceptedForCleanProposal": cleanup_result["readiness"]["acceptedForCleanProposal"],
        },
        "geometrySemanticTransfer": {
            "reportId": semantic_transfer["reportId"],
            "sourceGeometryCleanupResultId": semantic_transfer["sourceGeometryCleanupResultId"],
            "status": semantic_transfer["readiness"]["status"],
            "semanticTransferRun": semantic_transfer["execution"]["semanticTransferRun"],
            "boundaryClassificationRun": semantic_transfer["execution"][
                "boundaryClassificationRun"
            ],
            "transferredPanelCount": semantic_transfer["aggregate"]["transferredPanelCount"],
            "expectedPanelCount": semantic_transfer["aggregate"]["expectedPanelCount"],
            "classifiedBoundaryEdgeCount": semantic_transfer["aggregate"][
                "classifiedBoundaryEdgeCount"
            ],
            "boundaryEdgeCount": semantic_transfer["aggregate"]["boundaryEdgeCount"],
            "unclassifiedBoundaryEdgeCount": semantic_transfer["aggregate"][
                "unclassifiedBoundaryEdgeCount"
            ],
            "ambiguousBoundaryEdgeCount": semantic_transfer["aggregate"][
                "ambiguousBoundaryEdgeCount"
            ],
            "classificationCompleteness": semantic_transfer["aggregate"][
                "classificationCompleteness"
            ],
            "acceptedForCleanProposal": semantic_transfer["readiness"]["acceptedForCleanProposal"],
        },
        "geometryBindingCandidate": {
            "reportId": binding_candidate["reportId"],
            "sourceGeometrySemanticTransferId": binding_candidate[
                "sourceGeometrySemanticTransferId"
            ],
            "status": binding_candidate["readiness"]["status"],
            "candidateBindingRun": binding_candidate["execution"]["candidateBindingRun"],
            "simulationBindingRun": binding_candidate["execution"]["simulationBindingRun"],
            "runtimeBindingWritten": binding_candidate["execution"]["runtimeBindingWritten"],
            "mappedVertexCount": binding_candidate["aggregate"]["mappedVertexCount"],
            "cleanupVertexCount": binding_candidate["aggregate"]["cleanupVertexCount"],
            "unmappedVertexCount": binding_candidate["aggregate"]["unmappedVertexCount"],
            "candidateCompleteness": binding_candidate["aggregate"]["candidateCompleteness"],
            "maxPanelUvDistance": binding_candidate["aggregate"]["maxPanelUvDistance"],
            "maxRestToSimulationOffsetMeters": binding_candidate["aggregate"][
                "maxRestToSimulationOffsetMeters"
            ],
            "acceptedForCleanProposal": binding_candidate["readiness"]["acceptedForCleanProposal"],
        },
        "geometryBindingValidation": {
            "reportId": binding_validation["reportId"],
            "sourceGeometryBindingCandidateId": binding_validation[
                "sourceGeometryBindingCandidateId"
            ],
            "status": binding_validation["readiness"]["status"],
            "deformationValidationRun": binding_validation["execution"]["deformationValidationRun"],
            "runtimeBindingAccepted": binding_validation["execution"]["runtimeBindingAccepted"],
            "validationRecordCount": binding_validation["aggregate"]["validationRecordCount"],
            "failedCheckCount": binding_validation["quality"]["failedCheckCount"],
            "notRunCheckCount": binding_validation["quality"]["notRunCheckCount"],
            "maxCleanupToSettledOffsetMeters": binding_validation["aggregate"][
                "maxCleanupToSettledOffsetMeters"
            ],
            "rmsCleanupToSettledOffsetMeters": binding_validation["aggregate"][
                "rmsCleanupToSettledOffsetMeters"
            ],
            "acceptedForCleanProposal": binding_validation["readiness"]["acceptedForCleanProposal"],
        },
        "geometryRepairRetopologyPlan": {
            "reportId": repair_plan["reportId"],
            "sourceGeometryBindingValidationId": repair_plan["sourceGeometryBindingValidationId"],
            "status": repair_plan["readiness"]["status"],
            "repairRetopologyPlanGenerated": repair_plan["execution"][
                "repairRetopologyPlanGenerated"
            ],
            "repairRun": repair_plan["execution"]["repairRun"],
            "retopologyRun": repair_plan["execution"]["retopologyRun"],
            "seamSplitRun": repair_plan["execution"]["seamSplitRun"],
            "recommendedOperationCount": repair_plan["aggregate"]["recommendedOperationCount"],
            "requiredOperationCount": repair_plan["aggregate"]["requiredOperationCount"],
            "deformationFailedVertexCount": repair_plan["aggregate"][
                "deformationFailedVertexCount"
            ],
            "estimatedRepairComplexity": repair_plan["aggregate"]["estimatedRepairComplexity"],
            "acceptedForCleanProposal": repair_plan["readiness"]["acceptedForCleanProposal"],
        },
        "geometryRepairResult": {
            "reportId": repair_result["reportId"],
            "sourceGeometryRepairRetopologyPlanId": repair_result[
                "sourceGeometryRepairRetopologyPlanId"
            ],
            "status": repair_result["readiness"]["status"],
            "repairResultGenerated": repair_result["execution"]["repairResultGenerated"],
            "deformationReprojectionRun": repair_result["execution"]["deformationReprojectionRun"],
            "repairRun": repair_result["execution"]["repairRun"],
            "retopologyRun": repair_result["execution"]["retopologyRun"],
            "seamSplitRun": repair_result["execution"]["seamSplitRun"],
            "movedVertexCount": repair_result["aggregate"]["movedVertexCount"],
            "unmappedVertexCount": repair_result["aggregate"]["unmappedVertexCount"],
            "executedOperationCount": repair_result["aggregate"]["executedOperationCount"],
            "deferredOperationCount": repair_result["aggregate"]["deferredOperationCount"],
            "maxOutputToSettledOffsetMeters": repair_result["aggregate"][
                "maxOutputToSettledOffsetMeters"
            ],
            "acceptedForCleanProposal": repair_result["readiness"]["acceptedForCleanProposal"],
        },
        "geometryRuntimeBindingResult": {
            "reportId": runtime_binding_result["reportId"],
            "sourceGeometryRepairResultId": runtime_binding_result["sourceGeometryRepairResultId"],
            "status": runtime_binding_result["readiness"]["status"],
            "retopologyRun": runtime_binding_result["execution"]["retopologyRun"],
            "seamSplitRun": runtime_binding_result["execution"]["seamSplitRun"],
            "componentStitchingRun": runtime_binding_result["execution"]["componentStitchingRun"],
            "runtimeBindingWritten": runtime_binding_result["execution"]["runtimeBindingWritten"],
            "runtimeBindingAccepted": runtime_binding_result["execution"]["runtimeBindingAccepted"],
            "runtimeBindingRecordCount": runtime_binding_result["aggregate"][
                "runtimeBindingRecordCount"
            ],
            "maxReconstructionError": runtime_binding_result["aggregate"]["maxReconstructionError"],
            "maxSeamPairDistanceMeters": runtime_binding_result["aggregate"][
                "maxSeamPairDistanceMeters"
            ],
            "acceptedForCleanProposal": runtime_binding_result["readiness"][
                "acceptedForCleanProposal"
            ],
        },
        "geometryMaterialUvTransfer": {
            "reportId": material_uv_transfer["reportId"],
            "sourceGeometryRuntimeBindingResultId": material_uv_transfer[
                "sourceGeometryRuntimeBindingResultId"
            ],
            "status": material_uv_transfer["readiness"]["status"],
            "uvTransferRun": material_uv_transfer["execution"]["uvTransferRun"],
            "materialTransferRun": material_uv_transfer["execution"]["materialTransferRun"],
            "sourceTextureProjectionRun": material_uv_transfer["execution"][
                "sourceTextureProjectionRun"
            ],
            "acceptedForMaterialPreview": material_uv_transfer["readiness"][
                "acceptedForMaterialPreview"
            ],
            "transferredMaterialCount": material_uv_transfer["aggregate"][
                "transferredMaterialCount"
            ],
            "missingMaterialCount": material_uv_transfer["aggregate"]["missingMaterialCount"],
            "missingUvCount": material_uv_transfer["aggregate"]["missingUvCount"],
        },
        "geometryVisualShellReview": {
            "reportId": visual_shell_review["reportId"],
            "sourceGeometryRuntimeBindingResultId": visual_shell_review[
                "sourceGeometryRuntimeBindingResultId"
            ],
            "status": visual_shell_review["readiness"]["status"],
            "visualFidelityReviewRun": visual_shell_review["execution"]["visualFidelityReviewRun"],
            "renderedPixelComparisonRun": visual_shell_review["execution"][
                "renderedPixelComparisonRun"
            ],
            "representationSilhouetteComparisonRun": visual_shell_review["execution"][
                "representationSilhouetteComparisonRun"
            ],
            "representationSilhouetteAccepted": visual_shell_review["readiness"][
                "representationSilhouetteAccepted"
            ],
            "visualFidelityScore": visual_shell_review["aggregate"]["visualFidelityScore"],
            "acceptedForVisualFidelity": visual_shell_review["readiness"][
                "acceptedForVisualFidelity"
            ],
            "sourceImageVisualComparisonRun": visual_shell_review["execution"][
                "sourceImageVisualComparisonRun"
            ],
            "sourceImageVisualFidelityAccepted": visual_shell_review["readiness"][
                "sourceImageVisualFidelityAccepted"
            ],
            "providerAppearanceComparisonRun": visual_shell_review["execution"][
                "providerAppearanceComparisonRun"
            ],
            "providerAppearanceAccepted": visual_shell_review["readiness"][
                "providerAppearanceAccepted"
            ],
            "stitchGraphConnectivityCheckRun": visual_shell_review["execution"][
                "stitchGraphConnectivityCheckRun"
            ],
            "stitchGraphConnectable": visual_shell_review["readiness"]["stitchGraphConnectable"],
            "singleShellWeldProofRun": visual_shell_review["execution"]["singleShellWeldProofRun"],
            "singleShellWeldProven": visual_shell_review["readiness"]["singleShellWeldProven"],
            "meshStitchOrWeldExecutionRun": visual_shell_review["execution"][
                "meshStitchOrWeldExecutionRun"
            ],
            "meshStitchOrWeldProven": visual_shell_review["readiness"]["meshStitchOrWeldProven"],
        },
        "inspectionArtifacts": {
            "manifestId": inspection_manifest["manifestId"],
            "reportId": inspection_report["reportId"],
            "rendererVersion": inspection_manifest["rendererVersion"],
            "artifactCount": inspection_manifest["artifactCount"],
            "topologyRepresentationInspectionRun": inspection_report["readiness"][
                "topologyRepresentationInspectionRun"
            ],
            "canonicalSimulationToRenderSilhouetteRun": inspection_report["readiness"][
                "canonicalSimulationToRenderSilhouetteRun"
            ],
            "providerGeometryAppearanceComparisonRun": inspection_report["readiness"][
                "providerGeometryAppearanceComparisonRun"
            ],
            "sourceImageSilhouetteComparisonRun": inspection_report["readiness"][
                "sourceImageSilhouetteComparisonRun"
            ],
            "sourceImageAppearanceComparisonRun": inspection_report["readiness"][
                "sourceImageAppearanceComparisonRun"
            ],
            "humanVisualReviewRun": inspection_report["readiness"]["humanVisualReviewRun"],
            "acceptedForVisualFidelity": inspection_report["readiness"][
                "acceptedForVisualFidelity"
            ],
            "acceptedForCleanProposal": inspection_report["readiness"]["acceptedForCleanProposal"],
        },
        "geometryCleanAcceptanceGate": {
            "reportId": clean_acceptance_gate["reportId"],
            "sourceGeometryRuntimeBindingResultId": clean_acceptance_gate[
                "sourceGeometryRuntimeBindingResultId"
            ],
            "status": clean_acceptance_gate["readiness"]["status"],
            "cleanAcceptanceGateRun": clean_acceptance_gate["execution"]["cleanAcceptanceGateRun"],
            "runtimeBindingEvidenceReviewed": clean_acceptance_gate["execution"][
                "runtimeBindingEvidenceReviewed"
            ],
            "visualFidelityReviewRun": clean_acceptance_gate["execution"][
                "visualFidelityReviewRun"
            ],
            "materialTransferRun": clean_acceptance_gate["execution"]["materialTransferRun"],
            "singleShellWeldProofRun": clean_acceptance_gate["execution"][
                "singleShellWeldProofRun"
            ],
            "representationSilhouetteComparisonRun": clean_acceptance_gate["execution"][
                "representationSilhouetteComparisonRun"
            ],
            "representationSilhouetteAccepted": clean_acceptance_gate["execution"][
                "representationSilhouetteAccepted"
            ],
            "meshStitchOrWeldExecutionRun": clean_acceptance_gate["execution"][
                "meshStitchOrWeldExecutionRun"
            ],
            "checkCount": clean_acceptance_gate["aggregate"]["checkCount"],
            "passedCheckCount": clean_acceptance_gate["aggregate"]["passedCheckCount"],
            "failedCheckCount": clean_acceptance_gate["aggregate"]["failedCheckCount"],
            "warningCheckCount": clean_acceptance_gate["aggregate"]["warningCheckCount"],
            "notRunCheckCount": clean_acceptance_gate["aggregate"]["notRunCheckCount"],
            "acceptedForCleanProposal": clean_acceptance_gate["readiness"][
                "acceptedForCleanProposal"
            ],
            "acceptedForRuntimeRender": clean_acceptance_gate["readiness"][
                "acceptedForRuntimeRender"
            ],
            "blockingReasons": clean_acceptance_gate["readiness"]["blockingReasons"],
        },
        "cleanGeometryProposal": {
            "proposalId": clean_proposal["proposalId"],
            "sourceRawProposalId": clean_proposal["sourceRawProposalId"],
            "qualityStatus": clean_proposal["quality"]["status"],
            "cleanProposalAvailable": clean_proposal["cleanProposal"]["available"],
            "acceptedForCanonical": clean_proposal["quality"]["acceptedForCanonical"],
            "acceptedForSimulation": clean_proposal["quality"]["acceptedForSimulation"],
            "topologyDiagnosticsRun": clean_proposal["cleanupPipeline"]["topologyDiagnosticsRun"],
            "cleanupPlanGenerated": clean_proposal["cleanupPipeline"]["cleanupPlanGenerated"],
            "cleanupResultGenerated": clean_proposal["cleanupPipeline"]["cleanupResultGenerated"],
            "semanticTransferReportGenerated": clean_proposal["cleanupPipeline"][
                "semanticTransferReportGenerated"
            ],
            "bindingCandidateReportGenerated": clean_proposal["cleanupPipeline"][
                "bindingCandidateReportGenerated"
            ],
            "bindingValidationReportGenerated": clean_proposal["cleanupPipeline"][
                "bindingValidationReportGenerated"
            ],
            "repairRetopologyPlanGenerated": clean_proposal["cleanupPipeline"][
                "repairRetopologyPlanGenerated"
            ],
            "partialRepairResultGenerated": clean_proposal["cleanupPipeline"][
                "partialRepairResultGenerated"
            ],
            "runtimeBindingResultGenerated": clean_proposal["cleanupPipeline"][
                "runtimeBindingResultGenerated"
            ],
            "cleanAcceptanceGateGenerated": clean_proposal["cleanupPipeline"][
                "cleanAcceptanceGateGenerated"
            ],
            "cleanupRun": clean_proposal["cleanupPipeline"]["cleanupRun"],
            "repairRun": clean_proposal["cleanupPipeline"]["repairRun"],
            "deformationReprojectionRun": clean_proposal["cleanupPipeline"][
                "deformationReprojectionRun"
            ],
            "semanticTransferRun": clean_proposal["cleanupPipeline"]["semanticTransferRun"],
            "candidateBindingRun": clean_proposal["cleanupPipeline"]["candidateBindingRun"],
            "deformationValidationRun": clean_proposal["cleanupPipeline"][
                "deformationValidationRun"
            ],
            "simulationBindingRun": clean_proposal["cleanupPipeline"]["simulationBindingRun"],
            "runtimeBindingAccepted": clean_proposal["cleanupPipeline"]["runtimeBindingAccepted"],
            "cleanAcceptanceGateRun": clean_proposal["cleanupPipeline"]["cleanAcceptanceGateRun"],
            "cleanAcceptanceGateAccepted": clean_proposal["cleanupPipeline"][
                "cleanAcceptanceGateAccepted"
            ],
            "failureReason": clean_proposal["cleanGeometryAudit"]["failureReason"],
            "rejectionReasons": clean_proposal["quality"]["rejectionReasons"],
        },
        "providerRegistry": {
            "registryId": provider_registry["registryId"],
            "selectedProviderId": provider_registry["selectedProviderId"],
            "selectionReason": provider_registry["selectionReason"],
            "contractVersion": provider_registry["contractVersion"],
            "providerCount": len(provider_registry["providers"]),
            "manualLocalImportAdapterDeclared": provider_registry["d0Capabilities"][
                "manualLocalImportAdapterDeclared"
            ],
            "manualLocalImportAssetAvailable": provider_registry["d0Capabilities"][
                "manualLocalImportAssetAvailable"
            ],
            "localOpenModelAdapterDeclared": provider_registry["d0Capabilities"][
                "localOpenModelAdapterDeclared"
            ],
            "localOpenModelExecutionAvailable": provider_registry["d0Capabilities"][
                "localOpenModelExecutionAvailable"
            ],
            "externalProvidersConfigured": provider_registry["d0Capabilities"][
                "externalProvidersConfigured"
            ],
            "cleanProposalProviderAvailable": provider_registry["d0Capabilities"][
                "cleanProposalProviderAvailable"
            ],
        },
        "providerBakeoff": {
            "reportId": provider_bakeoff["reportId"],
            "status": provider_bakeoff["status"],
            "providerCount": provider_bakeoff["aggregate"]["providerCount"],
            "executedProviderCount": provider_bakeoff["aggregate"]["executedProviderCount"],
            "notRunProviderCount": provider_bakeoff["aggregate"]["notRunProviderCount"],
            "canonicalAcceptedProviderCount": provider_bakeoff["aggregate"][
                "canonicalAcceptedProviderCount"
            ],
            "bestAvailableProviderId": provider_bakeoff["aggregate"]["bestAvailableProviderId"],
            "bestAvailableStatus": provider_bakeoff["aggregate"]["bestAvailableStatus"],
        },
        "productionBindingC3": {
            "reportId": production_binding_c3["reportId"],
            "status": production_binding_c3["readiness"]["status"],
            "gateC3Status": production_binding_c3["readiness"]["gateC3Status"],
            "profile": production_binding_c3["profile"]["id"],
            "motionStateCount": production_binding_c3["motionSuite"]["stateCount"],
            "persistedValidationStatus": production_binding_c3["persistedValidation"]["status"],
            "maxReconstructionErrorMeters": production_binding_c3["aggregate"][
                "maxReconstructionErrorMeters"
            ],
            "maxSeamCrackMeters": production_binding_c3["aggregate"]["maxSeamCrackMeters"],
            "maxDenseFallbackParityErrorMeters": production_binding_c3["aggregate"][
                "maxDenseFallbackParityErrorMeters"
            ],
            "acceptedForGlobalPhase6": production_binding_c3["readiness"][
                "acceptedForGlobalPhase6"
            ],
        },
        "selfCollision": {
            "reportId": self_collision_report["reportId"],
            "status": self_collision_report["readiness"]["status"],
            "candidatePairCount": self_collision_report["metrics"]["candidatePairCount"],
            "contactCountBeforeCorrection": self_collision_report["metrics"][
                "contactCountBeforeCorrection"
            ],
            "contactCountAfterCorrection": self_collision_report["metrics"][
                "contactCountAfterCorrection"
            ],
            "unresolvedContactCount": self_collision_report["metrics"]["unresolvedContactCount"],
            "highVelocityTunnelling": self_collision_report["adversarialFixtures"][
                "highVelocityTunnelling"
            ]["status"],
            "acceptedForD0ReferenceSolver": self_collision_report["readiness"][
                "acceptedForD0ReferenceSolver"
            ],
            "acceptedForProductionGpuSolver": self_collision_report["readiness"][
                "acceptedForProductionGpuSolver"
            ],
        },
        "settle": {
            "solverVersion": settle["solverVersion"],
            "convergenceState": settle["convergenceState"],
            "maximumSeamResidualMeters": settle["maximumSeamResidualMeters"],
            "rmsSeamResidualMeters": settle["rmsSeamResidualMeters"],
            "maximumBodyPenetrationMeters": settle["maximumBodyPenetrationMeters"],
            "maximumStrain": settle["maximumStrain"],
            "selfCollisionAvailable": settle["selfCollision"]["available"],
        },
        "validation": validation["counts"],
        "warnings": manifest["warnings"],
    }


def human_report(package_dir: Path) -> str:
    summary = summarize_package(package_dir)
    lines = [
        f"Closy garment package: {summary['garmentId']}",
        f"Class: {summary['garmentClass']}  Avatar: {summary['avatarContractId']}",
        f"Schema: {summary['schemaVersion']}  Seed: {summary['seed']}",
        f"Convention: {summary['coordinateConvention']}",
        f"Package digest: {summary['packageDigest']}",
        f"Inventoried bytes: {summary['packageByteSize']}",
        "Counts:",
    ]
    for key, value in summary["counts"].items():
        lines.append(f"  - {key}: {value}")
    binding = summary["binding"]
    capture = summary["capture"]
    visual = summary["visualUnderstanding"]
    multiview = summary["multiviewFusion"]
    fitting = summary["fitting"]
    texture = summary["texture"]
    proposal = summary["geometryProposal"]
    raw_topology = summary["rawGeometryTopology"]
    cleanup_plan = summary["geometryCleanupPlan"]
    cleanup_result = summary["geometryCleanupResult"]
    semantic_transfer = summary["geometrySemanticTransfer"]
    binding_candidate = summary["geometryBindingCandidate"]
    binding_validation = summary["geometryBindingValidation"]
    repair_plan = summary["geometryRepairRetopologyPlan"]
    repair_result = summary["geometryRepairResult"]
    runtime_binding_result = summary["geometryRuntimeBindingResult"]
    material_uv_transfer = summary["geometryMaterialUvTransfer"]
    visual_shell_review = summary["geometryVisualShellReview"]
    clean_acceptance_gate = summary["geometryCleanAcceptanceGate"]
    clean_proposal = summary["cleanGeometryProposal"]
    provider_registry = summary["providerRegistry"]
    provider_bakeoff = summary["providerBakeoff"]
    production_binding_c3 = summary["productionBindingC3"]
    self_collision = summary["selfCollision"]
    settle = summary["settle"]
    lines.extend(
        [
            (
                f"Capture: {capture['viewCount']} synthetic metadata-only views, "
                f"quality {capture['overallScore']:.6f} ({capture['overallStatus']})"
            ),
            (
                f"Visual observations: {visual['maskCount']} pixel-derived masks, "
                f"{visual['observedLandmarkCount']} landmarks, "
                f"{visual['semanticPartCount']} parts, "
                f"{visual['openingBoundaryCount']} openings, "
                f"{visual['correctionOperationCount']} applied corrections, "
                f"mean IoU={visual['meanMaskIoU']:.6f}"
            ),
            (
                f"Multiview fusion: {multiview['status']}, "
                f"{multiview['viewCount']} views, "
                f"{multiview['fusedMaskCount']} fused masks, "
                f"{multiview['fusedLandmarkCount']} fused landmarks, downstream allowed="
                f"{multiview['expensiveDownstreamAllowed']}"
            ),
            (
                f"Fitting: {fitting['status']} via {fitting['fitterVersion']}, "
                f"landmark RMS {fitting['landmarkRmsNormalised']:.6f}, "
                f"multiview IoU={fitting['multiviewSilhouetteMeanIoU']:.6f}, "
                f"optimisation iterations={fitting['optimizationIterations']}"
            ),
            (
                f"Texture identity: {texture['status']}, "
                f"{texture['materialRegionCount']} PBR material observations, "
                f"source textures available={texture['sourceTextureAvailable']}, "
                f"visible projections={texture['visibleProjectionCount']}/"
                f"{texture['sourceProjectionCount']}, "
                f"mean confidence={texture['meanVisibleConfidence']:.6f}, "
                f"PBR maps source-backed/placeholders="
                f"{texture['pbrSourceBackedMapCount']}/{texture['pbrPlaceholderMapCount']}"
            ),
            (
                f"Geometry proposal: {proposal['qualityStatus']} via "
                f"{proposal['providerId']}, raw available={proposal['rawProposalAvailable']}"
            ),
            (
                f"Raw topology: components={raw_topology['componentCount']}, "
                f"non-manifold edges={raw_topology['nonManifoldEdgeCount']}, "
                f"status={raw_topology['manifoldStatus']}"
            ),
            (
                f"Cleanup plan: {cleanup_plan['requiredOperationCount']} required operations, "
                f"status={cleanup_plan['status']}"
            ),
            (
                f"Cleanup result: status={cleanup_result['status']}, "
                f"removed duplicate vertices="
                f"{cleanup_result['removedDuplicateVertexCount']}, "
                f"accepted={cleanup_result['acceptedForCleanProposal']}"
            ),
            (
                f"Semantic transfer: status={semantic_transfer['status']}, "
                f"panels={semantic_transfer['transferredPanelCount']}/"
                f"{semantic_transfer['expectedPanelCount']}, "
                f"boundaries={semantic_transfer['classifiedBoundaryEdgeCount']}/"
                f"{semantic_transfer['boundaryEdgeCount']}, "
                f"accepted={semantic_transfer['acceptedForCleanProposal']}"
            ),
            (
                f"Binding candidate: status={binding_candidate['status']}, "
                f"mapped={binding_candidate['mappedVertexCount']}/"
                f"{binding_candidate['cleanupVertexCount']}, runtime binding="
                f"{binding_candidate['runtimeBindingWritten']}, "
                f"accepted={binding_candidate['acceptedForCleanProposal']}"
            ),
            (
                f"Binding validation: status={binding_validation['status']}, "
                f"max offset {binding_validation['maxCleanupToSettledOffsetMeters']:.8f} m, "
                f"failed checks={binding_validation['failedCheckCount']}, runtime accepted="
                f"{binding_validation['runtimeBindingAccepted']}"
            ),
            (
                f"Repair/retopology plan: status={repair_plan['status']}, "
                f"required operations={repair_plan['requiredOperationCount']}, "
                f"complexity={repair_plan['estimatedRepairComplexity']}, "
                f"executed={repair_plan['repairRun']}"
            ),
            (
                f"Repair result: status={repair_result['status']}, "
                f"reprojected vertices={repair_result['movedVertexCount']}, "
                f"deferred operations={repair_result['deferredOperationCount']}, "
                f"retopology={repair_result['retopologyRun']}"
            ),
            (
                f"Runtime binding result: status={runtime_binding_result['status']}, "
                f"records={runtime_binding_result['runtimeBindingRecordCount']}, "
                f"accepted={runtime_binding_result['runtimeBindingAccepted']}, "
                f"max reconstruction error={runtime_binding_result['maxReconstructionError']:.8f}"
            ),
            (
                f"Material/UV transfer: status={material_uv_transfer['status']}, "
                f"uv={material_uv_transfer['uvTransferRun']}, "
                f"materials={material_uv_transfer['materialTransferRun']}, "
                f"preview accepted={material_uv_transfer['acceptedForMaterialPreview']}"
            ),
            (
                f"Visual/shell review: status={visual_shell_review['status']}, "
                "representation silhouette="
                f"{visual_shell_review['representationSilhouetteAccepted']}, "
                "source/provider visual fidelity="
                f"{visual_shell_review['acceptedForVisualFidelity']}, "
                f"stitch graph={visual_shell_review['stitchGraphConnectable']}, "
                f"mesh stitch/weld={visual_shell_review['meshStitchOrWeldProven']}"
            ),
            (
                f"Clean acceptance gate: status={clean_acceptance_gate['status']}, "
                f"passed={clean_acceptance_gate['passedCheckCount']}/"
                f"{clean_acceptance_gate['checkCount']}, "
                f"failed={clean_acceptance_gate['failedCheckCount']}, "
                f"warnings={clean_acceptance_gate['warningCheckCount']}, "
                f"not run={clean_acceptance_gate['notRunCheckCount']}, "
                f"accepted={clean_acceptance_gate['acceptedForCleanProposal']}"
            ),
            (
                f"Clean proposal: {clean_proposal['qualityStatus']}, "
                f"available={clean_proposal['cleanProposalAvailable']}, "
                f"reason={clean_proposal['failureReason']}"
            ),
            (
                f"Provider registry: selected {provider_registry['selectedProviderId']}, "
                "manual asset available="
                f"{provider_registry['manualLocalImportAssetAvailable']}"
            ),
            (
                f"Provider bake-off: status={provider_bakeoff['status']}, "
                f"executed={provider_bakeoff['executedProviderCount']}/"
                f"{provider_bakeoff['providerCount']}, best="
                f"{provider_bakeoff['bestAvailableProviderId']}, canonical accepted="
                f"{provider_bakeoff['canonicalAcceptedProviderCount']}"
            ),
            (
                f"Binding: {binding['recordCount']} records, "
                f"max error {binding['maxError']:.8f}, RMS {binding['rmsError']:.8f}"
            ),
            (
                f"Production binding C3: status={production_binding_c3['status']}, "
                f"profile={production_binding_c3['profile']}, "
                f"motion states={production_binding_c3['motionStateCount']}, "
                f"max error={production_binding_c3['maxReconstructionErrorMeters']:.8f}, "
                f"global Phase 6={production_binding_c3['acceptedForGlobalPhase6']}"
            ),
            (
                f"Settle: {settle['convergenceState']} via {settle['solverVersion']}, "
                f"seam RMS {settle['rmsSeamResidualMeters']:.8f} m, max penetration "
                f"{settle['maximumBodyPenetrationMeters']:.8f} m"
            ),
            (
                f"Self-collision: status={self_collision['status']}, "
                f"contacts after correction={self_collision['contactCountAfterCorrection']}, "
                f"unresolved={self_collision['unresolvedContactCount']}, "
                f"high velocity={self_collision['highVelocityTunnelling']}"
            ),
            f"Validation: {summary['validation']}",
            "Warnings: " + ", ".join(summary["warnings"]),
            "ZeroOne: unavailable and optional",
        ]
    )
    return "\n".join(lines) + "\n"


def _operation_removed_count(cleanup_result: dict[str, Any], operation_id: str) -> int:
    for operation in cleanup_result["executedOperations"]:
        if operation["operationId"] == operation_id:
            return int(operation["removedCount"])
    return 0
