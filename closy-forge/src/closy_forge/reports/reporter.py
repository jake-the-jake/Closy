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
