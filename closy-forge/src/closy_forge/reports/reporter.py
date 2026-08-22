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
    fitting = read_json(package_dir / "fitting" / "tshirt_fit.json")
    texture = read_json(package_dir / "textures" / "texture_identity.json")
    proposal = read_json(package_dir / "proposals" / "raw_geometry_proposal.json")
    raw_topology = read_json(package_dir / "reports" / "raw_geometry_topology.json")
    cleanup_plan = read_json(package_dir / "reports" / "geometry_cleanup_plan.json")
    cleanup_result = read_json(package_dir / "reports" / "geometry_cleanup_result.json")
    clean_proposal = read_json(package_dir / "proposals" / "clean_geometry_proposal.json")
    provider_registry = read_json(package_dir / "proposals" / "provider_registry.json")
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
            "maskCount": visual["aggregate"]["maskCount"],
            "observedLandmarkCount": len(visual["aggregate"]["observedLandmarks"]),
            "requiredLandmarkCount": len(visual["aggregate"]["requiredLandmarks"]),
            "meanMaskConfidence": visual["aggregate"]["meanMaskConfidence"],
            "meanLandmarkConfidence": visual["aggregate"]["meanLandmarkConfidence"],
            "correctionRecordId": correction["correctionRecordId"],
            "correctionOperationCount": len(correction["operations"]),
        },
        "fitting": {
            "fitReportId": fitting["fitReportId"],
            "fitterVersion": fitting["fitterVersion"],
            "status": fitting["status"],
            "accepted": fitting["accepted"],
            "landmarkRmsNormalised": fitting["losses"]["landmarkRmsNormalised"],
            "maskWidthErrorMeters": fitting["losses"]["maskWidthErrorMeters"],
        },
        "texture": {
            "textureIdentityId": texture["textureIdentityId"],
            "status": texture["status"],
            "sourceTextureAvailable": texture["sourceTextureAvailable"],
            "generatedAtlasAvailable": texture["generatedAtlasAvailable"],
            "textureProjectionRun": texture["textureProjectionRun"],
            "materialRegionCount": len(texture["observedMaterialRegions"]),
            "recommendedAtlasSizePx": texture["projectionPlan"]["recommendedAtlasSizePx"],
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
            "cleanupRun": clean_proposal["cleanupPipeline"]["cleanupRun"],
            "repairRun": clean_proposal["cleanupPipeline"]["repairRun"],
            "semanticTransferRun": clean_proposal["cleanupPipeline"]["semanticTransferRun"],
            "simulationBindingRun": clean_proposal["cleanupPipeline"]["simulationBindingRun"],
            "failureReason": clean_proposal["cleanGeometryAudit"]["failureReason"],
            "rejectionReasons": clean_proposal["quality"]["rejectionReasons"],
        },
        "providerRegistry": {
            "registryId": provider_registry["registryId"],
            "selectedProviderId": provider_registry["selectedProviderId"],
            "selectionReason": provider_registry["selectionReason"],
            "providerCount": len(provider_registry["providers"]),
            "manualLocalImportAdapterDeclared": provider_registry["d0Capabilities"][
                "manualLocalImportAdapterDeclared"
            ],
            "manualLocalImportAssetAvailable": provider_registry["d0Capabilities"][
                "manualLocalImportAssetAvailable"
            ],
            "externalProvidersConfigured": provider_registry["d0Capabilities"][
                "externalProvidersConfigured"
            ],
            "cleanProposalProviderAvailable": provider_registry["d0Capabilities"][
                "cleanProposalProviderAvailable"
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
    fitting = summary["fitting"]
    texture = summary["texture"]
    proposal = summary["geometryProposal"]
    raw_topology = summary["rawGeometryTopology"]
    cleanup_plan = summary["geometryCleanupPlan"]
    cleanup_result = summary["geometryCleanupResult"]
    clean_proposal = summary["cleanGeometryProposal"]
    provider_registry = summary["providerRegistry"]
    settle = summary["settle"]
    lines.extend(
        [
            (
                f"Capture: {capture['viewCount']} synthetic metadata-only views, "
                f"quality {capture['overallScore']:.6f} ({capture['overallStatus']})"
            ),
            (
                f"Visual observations: {visual['maskCount']} masks, "
                f"{visual['observedLandmarkCount']} landmarks, "
                f"{visual['correctionOperationCount']} corrections"
            ),
            (
                f"Fitting: {fitting['status']} via {fitting['fitterVersion']}, "
                f"landmark RMS {fitting['landmarkRmsNormalised']:.6f}"
            ),
            (
                f"Texture identity: {texture['status']}, "
                f"{texture['materialRegionCount']} PBR material observations, "
                f"source textures available={texture['sourceTextureAvailable']}"
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
                f"Binding: {binding['recordCount']} records, "
                f"max error {binding['maxError']:.8f}, RMS {binding['rmsError']:.8f}"
            ),
            (
                f"Settle: {settle['convergenceState']} via {settle['solverVersion']}, "
                f"seam RMS {settle['rmsSeamResidualMeters']:.8f} m, max penetration "
                f"{settle['maximumBodyPenetrationMeters']:.8f} m"
            ),
            f"Validation: {summary['validation']}",
            "Warnings: " + ", ".join(summary["warnings"]),
            "ZeroOne: unavailable and optional",
            "Self-collision: not implemented in the reference CPU solver v1",
        ]
    )
    return "\n".join(lines) + "\n"


def _operation_removed_count(cleanup_result: dict[str, Any], operation_id: str) -> int:
    for operation in cleanup_result["executedOperations"]:
        if operation["operationId"] == operation_id:
            return int(operation["removedCount"])
    return 0
