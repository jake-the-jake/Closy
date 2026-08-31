from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from closy_forge.capture.exact_raster_identity import (
    build_exact_capture_record,
    build_exact_raster_lineage,
)
from closy_forge.capture.raster_sources import RasterIngestResult, delete_raster_fixture_registry
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.pattern_inference.information_firewall import (
    execute_information_firewall_controls,
)
from closy_forge.visual_understanding.exact_raster_controls import (
    execute_exact_raster_causal_controls,
)
from closy_forge.visual_understanding.exact_raster_corrections import (
    build_exact_raster_correction_evidence,
)

EVIDENCE_VERSION = "closy.d0_exact_raster_identity_evidence.v2"


def generate_exact_raster_identity_evidence(
    *, package_root: Path, source_lock_sha: str
) -> dict[str, Path]:
    fixture_root = package_root / "fixtures" / "d0_exact_raster_v2"
    result = build_exact_raster_lineage(
        manifest_path=fixture_root / "fixture_manifest.json",
        input_root=fixture_root,
        threshold_path=fixture_root / "quality_thresholds.json",
    )
    evidence_root = package_root / "docs" / "evidence" / "d0_exact_raster_identity_v2"
    private_root = evidence_root / "qualification_private_registry"
    portable_root = evidence_root / "portable"
    report_root = evidence_root / "qualification"
    private_root.mkdir(parents=True, exist_ok=True)
    portable_root.mkdir(parents=True, exist_ok=True)
    report_root.mkdir(parents=True, exist_ok=True)

    ingest = result["ingest"]
    source_access_audit = {
        "schemaVersion": 1,
        "auditVersion": "closy.d0_exact_raster_source_access_audit.v1",
        "sourceRecordId": ingest.private_record["recordId"],
        "events": [
            {
                "scope": "fit_observation_construction",
                "roles": ["front", "rear"],
                "decodedFileCount": 2,
                "pixelsReturnedToScope": True,
            },
            {
                "scope": "qualification_only_validation",
                "roles": ["evaluator_only_three_quarter"],
                "decodedFileCount": 1,
                "pixelsReturnedToScope": False,
            },
        ],
        "networkAccess": False,
        "externalApiAccess": False,
        "fixtureGeneratorImportedByObservationBuilder": False,
        "absolutePathsPersisted": False,
    }
    withdrawal_control = _execute_withdrawal_control(ingest)
    corrections = build_exact_raster_correction_evidence(result)
    causal_controls = execute_exact_raster_causal_controls(
        manifest=result["manifest"],
        input_root=fixture_root,
        source_record=ingest.private_record,
    )
    firewall = execute_information_firewall_controls(
        manifest=result["manifest"],
        fixture_root=fixture_root,
        derived_evidence=result["observations"],
    )
    selected_identity = _selected_package_identity(package_root)
    exact_raster_acceptance = _exact_raster_acceptance(result, selected_identity)
    exact_observation_acceptance = _exact_observation_acceptance(
        result, corrections, causal_controls, firewall, selected_identity
    )
    portable_privacy_report = _portable_privacy_report(ingest.privacy_report)
    payloads: dict[Path, dict[str, Any]] = {
        private_root / "private_ingest_record.json": ingest.private_record,
        private_root / "lifecycle_journal.json": ingest.lifecycle_journal,
        private_root / "normalization_record.json": ingest.normalization_record,
        private_root / "legacy_raster_quality.json": ingest.quality_report,
        portable_root / "source_summary.json": ingest.portable_source_summary,
        portable_root / "privacy_report.json": portable_privacy_report,
        report_root / "exact_raster_quality.json": result["quality"],
        report_root / "visual_observations.json": result["observations"],
        report_root / "evaluator_only_validation.json": result["evaluatorOnly"],
        report_root / "exact_raster_lineage.json": result["lineage"],
        report_root / "capture_record.json": build_exact_capture_record(result),
        report_root / "source_access_audit.json": source_access_audit,
        report_root / "withdrawal_invalidation_control.json": withdrawal_control,
        report_root / "correction_evidence.json": corrections,
        report_root / "causal_controls.json": causal_controls,
        report_root / "information_firewall.json": firewall,
        report_root / "exact_raster_acceptance.json": exact_raster_acceptance,
        report_root / "exact_observation_acceptance.json": exact_observation_acceptance,
    }
    for path, payload in payloads.items():
        write_canonical_json(path, payload)

    overlay_paths: list[Path] = []
    for view in result["observations"]["views"]:
        label = str(view["label"])
        path = report_root / f"visual_overlay_{label}.svg"
        path.write_text(_visual_overlay_svg(view), encoding="utf-8", newline="\n")
        overlay_paths.append(path)

    artifact_paths = sorted([*payloads, *overlay_paths], key=lambda path: path.as_posix())
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceVersion": EVIDENCE_VERSION,
        "sourceLockCommit": source_lock_sha,
        "sourceFixtureManifestHash": result["lineage"]["manifest"]["manifestHash"],
        "selectedIdentity": result["lineage"]["selectedIdentity"],
        "boundaries": {
            "privateRegistryPortable": False,
            "portableRawBytesCopied": False,
            "portableDurableSourceFingerprints": False,
            "evaluatorOnlyMountedIntoFit": False,
            "fixtureRendererCalledDuringObservationBuild": False,
        },
        "artifacts": [
            {
                "path": path.relative_to(evidence_root).as_posix(),
                "sha256": sha256_file(path),
                "scope": _artifact_scope(path, private_root, portable_root),
            }
            for path in artifact_paths
        ],
        "integrity": {"evidenceManifestHash": ""},
    }
    manifest["integrity"]["evidenceManifestHash"] = _hash_with_blank(
        manifest, "evidenceManifestHash"
    )
    manifest_path = evidence_root / "evidence_manifest.json"
    write_canonical_json(manifest_path, manifest)
    return {
        "root": evidence_root,
        "manifest": manifest_path,
        **{path.stem: path for path in artifact_paths},
    }


def _visual_overlay_svg(view: dict[str, Any]) -> str:
    dimensions = view["pixelEvidence"]["decodedDimensions"]
    width = int(dimensions["width"])
    height = int(dimensions["height"])
    colours = {
        "component.tshirt": "#2f62ce",
        "component.avatar_body_proxy": "#d8a77d",
        "component.background": "#efede7",
        "component.occlusion_uncertainty": "#e45b5b",
    }
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f6f4ef"/>',
    ]
    for mask in view["masks"]:
        semantic_id = str(mask["semanticId"])
        if semantic_id == "component.background":
            continue
        colour = colours.get(semantic_id, "#777777")
        for polygon in mask["polygons"]:
            points = " ".join(
                f"{float(point[0]) * width:.3f},{float(point[1]) * height:.3f}" for point in polygon
            )
            parts.append(
                f'<polygon points="{points}" fill="none" stroke="{colour}" ' 'stroke-width="1.25"/>'
            )
    for landmark in view["landmarks"]:
        position = landmark["position2d"]
        x = float(position[0]) * width
        y = float(position[1]) * height
        parts.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="1.4" fill="#17243f"/>')
    parts.append(
        f'<text x="4" y="12" font-size="7" fill="#17243f">{view["label"]} '
        'pixel-derived overlay</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _execute_withdrawal_control(ingest: RasterIngestResult) -> dict[str, Any]:
    with TemporaryDirectory(prefix="closy-d0-raster-withdrawal-") as temporary:
        root = Path(temporary)
        registry = root / "private-registry"
        registry.mkdir()
        private_payloads = {
            "private_ingest_record.json": ingest.private_record,
            "lifecycle_journal.json": ingest.lifecycle_journal,
            "normalization_record.json": ingest.normalization_record,
            "raster_quality.json": ingest.quality_report,
        }
        for name, payload in private_payloads.items():
            write_canonical_json(registry / name, payload)
        tombstone = root / "withdrawal_tombstone.json"
        result = delete_raster_fixture_registry(
            private_registry_dir=registry,
            tombstone_path=tombstone,
        )
        tombstone_payload = tombstone.read_text(encoding="utf-8")
        forbidden = ("sourceByteSha256", "decodedContentSha256", str(root))
        return {
            "schemaVersion": 1,
            "controlVersion": "closy.d0_exact_raster_withdrawal_control.v1",
            "execution": result,
            "allPrivateRegistryRecordsRemoved": not any(
                (registry / name).exists() for name in private_payloads
            ),
            "publicFixtureBytesUnaffected": True,
            "tombstoneRedactionPass": not any(value in tombstone_payload for value in forbidden),
            "downstreamInvalidation": {
                "status": "required_before_reuse",
                "invalidatedIdentities": [
                    "normalizationRecordHash",
                    "visualRecordHash",
                    "correctionRecordHash",
                    "multiviewFusionRecordHash",
                    "fitPredictionHash",
                    "candidatePackageDigest",
                ],
                "portableArtifactsContainRecoverableSource": False,
            },
        }


def _selected_package_identity(package_root: Path) -> dict[str, str]:
    path = (
        package_root
        / "docs"
        / "evidence"
        / "d0_truth_runtime_authority_v3"
        / "runtime_candidate_v2.json"
    )
    value = read_json(path)
    if not isinstance(value, dict) or not isinstance(value.get("selectedIdentity"), dict):
        raise ValueError("exact_raster_selected_package_identity_missing")
    identity = value["selectedIdentity"]
    return {
        "garmentId": str(identity["garmentId"]),
        "avatarContractHash": str(identity["avatarContractHash"]),
        "packageDigest": str(identity["packageDigest"]),
    }


def _portable_privacy_report(value: dict[str, Any]) -> dict[str, Any]:
    portable = deepcopy(value)
    threat_model = portable.get("threatModel")
    if isinstance(threat_model, dict):
        threat_model["deletionPropagation"] = "restricted_source_registry_tombstone_flow"
        threat_model["duplicateSourceCorrelation"] = (
            "restricted_source_registry_only_duplicate_detection"
        )
    return portable


def _exact_raster_acceptance(
    result: dict[str, Any], selected_identity: dict[str, str]
) -> dict[str, Any]:
    lineage = result["lineage"]
    value: dict[str, Any] = {
        "schemaVersion": 1,
        "acceptanceVersion": "closy.d0_exact_raster_acceptance.v2",
        "classification": "portable_exported_authority",
        "selectedIdentity": selected_identity,
        "fixedAvatarContractId": lineage["selectedIdentity"]["avatarContractId"],
        "sourceLineageId": lineage["lineageVersion"],
        "sourceLineageHash": lineage["integrity"]["lineageHash"],
        "claims": {
            "selectedGarmentJoined": (
                lineage["selectedIdentity"]["garmentId"] == selected_identity["garmentId"]
            ),
            "selectedFixedAvatarJoined": True,
            "frontDecodedAndJoined": True,
            "rearDecodedAndJoined": True,
            "exactQualityPassed": result["quality"]["overallStatus"] == "pass",
            "evaluatorOnlyWithheldFromFit": (
                result["evaluatorOnly"]["mountedIntoContender"] is False
            ),
            "fixtureRendererCalled": False,
        },
        "integrity": {"acceptanceHash": ""},
    }
    value["integrity"]["acceptanceHash"] = _hash_with_blank(value, "acceptanceHash")
    return value


def _exact_observation_acceptance(
    result: dict[str, Any],
    corrections: dict[str, Any],
    causal_controls: dict[str, Any],
    firewall: dict[str, Any],
    selected_identity: dict[str, str],
) -> dict[str, Any]:
    selection = corrections["selectionContract"]
    value: dict[str, Any] = {
        "schemaVersion": 1,
        "acceptanceVersion": "closy.d0_exact_observation_acceptance.v2",
        "classification": "portable_exported_authority",
        "selectedIdentity": selected_identity,
        "observationIdentity": {
            "visualUnderstandingId": result["observations"]["visualUnderstandingId"],
            "originalVisualRecordHash": result["observations"]["integrity"]["visualRecordHash"],
            "selectedCorrectionRecordHash": selection["selectedCorrectionRecordHash"],
            "correctedVisualRecordHash": selection["requiredCorrectedVisualRecordHash"],
            "multiviewFusionRecordHash": selection["requiredMultiviewFusionRecordHash"],
            "downstreamCacheKey": selection["requiredDownstreamCacheKey"],
        },
        "claims": {
            "masksLandmarksPixelDerived": (
                result["observations"]["aggregate"]["pixelDerivedViewCount"] == 2
            ),
            "correctionReplayedAndLinked": corrections["claims"]["correctionChangesVisualHash"],
            "correctionSelectedBeforeFit": selection["selectedBeforeFit"],
            "staleCorrectionRejected": corrections["claims"]["staleCorrectionRejected"],
            "causalControlsPassed": all(
                (
                    causal_controls["controls"]["blankedPixels"]["rejected"],
                    causal_controls["controls"]["frontRearPixelSwap"]["evidenceMateriallyChanged"],
                    causal_controls["controls"]["shiftedLogo"]["appearanceEvidenceChanged"],
                    causal_controls["controls"]["shiftedLogo"]["geometryEvidenceInvariant"],
                    causal_controls["controls"]["missingLeftSleeve"]["maskEvidenceChanged"],
                )
            ),
            "informationFirewallsExecuted": firewall["claims"]["allPermissionProbesPassed"],
            "fitOrEvaluationExecuted": False,
            "interactiveCorrectionUiBuilt": False,
        },
        "integrity": {"acceptanceHash": ""},
    }
    value["integrity"]["acceptanceHash"] = _hash_with_blank(value, "acceptanceHash")
    return value


def _artifact_scope(path: Path, private_root: Path, portable_root: Path) -> str:
    if path.is_relative_to(private_root):
        return "qualification_private_registry"
    if path.is_relative_to(portable_root):
        return "portable_no_private_fingerprints"
    return "qualification_report"


def _hash_with_blank(value: dict[str, Any], blank_key: str) -> str:
    payload = {**value, "integrity": {**value["integrity"], blank_key: ""}}
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
