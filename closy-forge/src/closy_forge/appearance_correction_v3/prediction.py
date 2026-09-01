from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.appearance.bitmap_atlas import BITMAP_PATHS
from closy_forge.appearance_correction_v3.controls import execute_source_only_controls
from closy_forge.appearance_correction_v3.freeze import load_implementation_freeze
from closy_forge.appearance_correction_v3.projection import (
    PROVENANCE_PATH,
    GeometricAtlasBundle,
    build_geometric_source_atlas,
)
from closy_forge.appearance_correction_v3.protocol import PROTOCOL_SHA256, load_correction_protocol
from closy_forge.appearance_correction_v3.source_inputs import load_locked_source_inputs
from closy_forge.fitting.exact_d0_candidate import inventory_digest, package_inventory
from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.inspection.cpu_raster import rasterize_settled_garment
from closy_forge.inspection.source_render_fidelity import (
    _atlas_sampler,
    compare_decoded_source_and_render,
)
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.raster import DecodedPng, decode_png_rgba, encode_png_rgba
from closy_forge.runtime_delivery.package import (
    RuntimePackageInputs,
    build_runtime_package,
    load_runtime_package,
)

PREDICTION_VERSION = "closy.d0_texture_rerender.source_only_prediction.v3"
PARENT_EVIDENCE = Path("docs/evidence/d0_fitting_pbr_fidelity_v2/predictions")
DEFAULT_OUTPUT = Path("docs/evidence/d0_texture_rerender_correction_v3/predictions")
_GEOMETRY_PATHS = (
    "pattern/pattern.json",
    "simulation/constraints.json",
    "simulation/topology_manifest.json",
    "simulation/seam_audit.json",
    "simulation/rest_mesh.glb",
    "simulation/settled_mesh.glb",
    "render/render_mesh.glb",
    "binding/sim_to_render.bin",
    "binding/binding_manifest.json",
    "binding/binding_audit.json",
)


def generate_source_only_prediction(
    root: Path,
    *,
    protocol_commit_sha: str,
    implementation_anchor_sha: str,
    output: Path | None = None,
) -> dict[str, Any]:
    _require_commit(protocol_commit_sha, "protocol_commit")
    _require_commit(implementation_anchor_sha, "implementation_anchor")
    protocol = load_correction_protocol(root)
    implementation = load_implementation_freeze(root)
    target = output or root / DEFAULT_OUTPUT
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    parent = root / PARENT_EVIDENCE
    parent_candidate = parent / "candidate_package"
    parent_manifest = _read(parent_candidate / "candidate_manifest.json")
    mesh = read_glb_meshset(parent_candidate / "simulation/settled_mesh.glb")
    source_views = load_locked_source_inputs(root)
    controls = execute_source_only_controls(mesh, source_views)
    if not (
        controls.get("allControlsPassed") is True
        and controls.get("noMagicLocationConstant") is True
        and controls.get("geometryInvariantAcrossControls") is True
    ):
        raise ValueError("d0_appearance_source_controls_failed")
    atlas = build_geometric_source_atlas(mesh, source_views)
    thresholds = _mapping(protocol.get("thresholds"))
    coverage = _mapping(atlas.report.get("coverage"))
    if float(coverage.get("sourceObservedFraction", 0.0)) < float(
        thresholds.get("minimumSourceObservedAtlasFraction", 1.0)
    ):
        raise ValueError("d0_appearance_source_coverage_below_lock")
    if float(coverage.get("generatedControlledFillFraction", 1.0)) > float(
        thresholds.get("maximumGeneratedRegionShare", 0.0)
    ):
        raise ValueError("d0_appearance_generated_share_above_lock")

    candidate = target / "candidate_package"
    shutil.copytree(parent_candidate, candidate)
    (candidate / "candidate_manifest.json").unlink()
    for relative, payload in atlas.artifacts.items():
        path = candidate / relative
        if isinstance(payload, bytes):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        else:
            write_canonical_json(path, payload)

    source_report, rendered = _source_only_rerenders(mesh, source_views, atlas)
    for label, payload in rendered.items():
        path = candidate / "reports" / "renders" / f"{label}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    compiled = _read(candidate / "reports/compiled_candidate.json")
    compiled["compilerVersion"] = "closy.exact_d0.canonical_candidate.topology_v2.appearance_v3"
    compiled["inSampleSourceRerender"] = source_report
    compiled["atlas"] = {
        "reportHash": _mapping(atlas.report.get("integrity")).get("bitmapPbrReportHash"),
        "sourceObservedFraction": coverage.get("sourceObservedFraction"),
        "generatedControlledFillFraction": coverage.get("generatedControlledFillFraction"),
        "evaluatorOnlyViewUsed": False,
        "provenanceSha256": sha256_bytes(_artifact_bytes(atlas, PROVENANCE_PATH)),
    }
    compiled["appearanceCorrection"] = {
        "strategyId": _mapping(protocol.get("strategy")).get("strategyId"),
        "protocolSha256": PROTOCOL_SHA256,
        "knownTargetClassification": "not_mounted_source_only_prediction",
    }
    _rehash(compiled, "compiledCandidateHash")
    write_canonical_json(candidate / "reports/compiled_candidate.json", compiled)

    freeze = _prediction_freeze(
        protocol_commit_sha=protocol_commit_sha,
        implementation_anchor_sha=implementation_anchor_sha,
        implementation=implementation,
        parent_manifest=parent_manifest,
        atlas=atlas,
        source_views=source_views,
        source_report=source_report,
    )
    write_canonical_json(target / "prediction_freeze.json", freeze)
    write_canonical_json(target / "source_only_controls.json", controls)
    write_canonical_json(target / "source_only_rerender.json", source_report)
    write_canonical_json(candidate / "provenance/prediction_freeze.json", freeze)
    source_projection_identity = {
        "schemaVersion": 1,
        "identityVersion": PREDICTION_VERSION,
        "protocolSha256": PROTOCOL_SHA256,
        "implementationBundleHash": implementation["implementationBundleHash"],
        "sourceClosureHash": freeze["sourceClosureHash"],
        "atlasHash": freeze["atlasHash"],
        "provenanceHash": freeze["provenanceHash"],
        "evaluatorOnlyMounted": False,
        "integrity": {"sourceProjectionIdentityHash": ""},
    }
    _rehash(source_projection_identity, "sourceProjectionIdentityHash")
    write_canonical_json(
        candidate / "provenance/source_projection_identity.json",
        source_projection_identity,
    )

    inventory = package_inventory(candidate, exclude={"candidate_manifest.json"})
    package_digest = inventory_digest(inventory)
    candidate_id = (
        "candidate.d0_texture_rerender_v3."
        + sha256_bytes(
            canonical_dumps(
                {
                    "parentCandidateId": parent_manifest["candidateId"],
                    "parentPackageDigest": parent_manifest["packageDigest"],
                    "atlasHash": freeze["atlasHash"],
                    "provenanceHash": freeze["provenanceHash"],
                    "packageDigest": package_digest,
                }
            ).encode("utf-8")
        )[:24]
    )
    manifest = {
        "schemaVersion": 1,
        "manifestVersion": "closy.d0_texture_rerender_candidate_manifest.v3",
        "candidateId": candidate_id,
        "candidateClass": "known_target_regression_research_candidate",
        "parentCandidateId": parent_manifest["candidateId"],
        "parentPackageDigest": parent_manifest["packageDigest"],
        "packageDigest": package_digest,
        "inventory": inventory,
        "runtimeSelected": False,
        "runtimeV1RemainsSelected": True,
        "fallbackPath": "render/render_mesh.glb",
        "identityGraph": {
            "protocolSha256": PROTOCOL_SHA256,
            "predictionFreezeHash": _mapping(freeze.get("integrity")).get("predictionFreezeHash"),
            "sourceProjectionIdentityHash": _mapping(
                source_projection_identity.get("integrity")
            ).get("sourceProjectionIdentityHash"),
            "atlasHash": freeze["atlasHash"],
            "provenanceHash": freeze["provenanceHash"],
            "geometryParent": parent_manifest["candidateId"],
        },
        "validation": {
            "status": "pass",
            "sourceOnlyControlsPassed": True,
            "evaluatorOnlyMounted": False,
            "knownTargetTrialCount": 0,
        },
        "integrity": {"manifestHash": ""},
    }
    _rehash(manifest, "manifestHash")
    write_canonical_json(candidate / "candidate_manifest.json", manifest)

    invalidation = _invalidation_report(
        parent_candidate, candidate, parent_manifest, manifest, atlas, freeze
    )
    write_canonical_json(target / "identity_invalidation.json", invalidation)
    runtime = _runtime_package(target, candidate, manifest)
    write_canonical_json(target / "runtime_qualification.json", runtime)
    summary: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceVersion": PREDICTION_VERSION,
        "stage": "frozen_source_only_prediction_before_known_target_mount",
        "candidateId": candidate_id,
        "candidatePackageDigest": package_digest,
        "parentCandidateId": parent_manifest["candidateId"],
        "protocolCommitSha": protocol_commit_sha,
        "implementationAnchorSha": implementation_anchor_sha,
        "sourceOnlyControlsPassed": True,
        "sourceOnlyRerenderPredicatesPassed": source_report["allPredicatesPassed"],
        "sourceObservedFraction": coverage.get("sourceObservedFraction"),
        "generatedControlledFillFraction": coverage.get("generatedControlledFillFraction"),
        "evaluatorOnly": {
            "pixelsOpened": False,
            "derivedEvidenceOpened": False,
            "target3dOpened": False,
            "mountStatus": "not_mounted",
        },
        "knownTargetTrialCount": 0,
        "d0Rp07Status": "fail_preserved_pending_unit_g",
        "researchPrototypePromoted": False,
        "runtimeV1SelectionChanged": False,
        "integrity": {"predictionSummaryHash": ""},
    }
    _rehash(summary, "predictionSummaryHash")
    write_canonical_json(target / "prediction_summary.json", summary)
    return summary


def validate_frozen_candidate(candidate: Path) -> dict[str, Any]:
    manifest = _read(candidate / "candidate_manifest.json")
    inventory = package_inventory(candidate, exclude={"candidate_manifest.json"})
    digest = inventory_digest(inventory)
    issues = []
    if inventory != manifest.get("inventory"):
        issues.append("candidate_inventory_mismatch")
    if digest != manifest.get("packageDigest"):
        issues.append("candidate_package_digest_mismatch")
    expected_hash = _mapping(manifest.get("integrity")).get("manifestHash")
    copy = deepcopy(manifest)
    _rehash(copy, "manifestHash")
    if _mapping(copy.get("integrity")).get("manifestHash") != expected_hash:
        issues.append("candidate_manifest_hash_mismatch")
    return {"status": "pass" if not issues else "fail", "issues": issues, "digest": digest}


def _source_only_rerenders(
    mesh: Any,
    source_views: tuple[Any, ...],
    atlas: GeometricAtlasBundle,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    contribution = decode_png_rgba(_artifact_bytes(atlas, BITMAP_PATHS["sourceContribution"]))
    records = []
    rendered_payloads = {}
    for view in sorted(source_views, key=lambda item: item.label):
        rendered = rasterize_settled_garment(
            mesh,
            label=view.label,
            width=view.image.width,
            height=view.image.height,
            camera=view.camera,
            texture_sampler=_atlas_sampler(atlas.decoded_atlas, view.label),
        )
        rendered_contribution = rasterize_settled_garment(
            mesh,
            label=view.label,
            width=view.image.width,
            height=view.image.height,
            camera=view.camera,
            texture_sampler=_atlas_sampler(contribution, view.label),
        )
        payload = encode_png_rgba(rendered.width, rendered.height, rendered.rgba)
        rendered_payloads[view.label] = payload
        metrics = compare_decoded_source_and_render(
            view.image,
            DecodedPng(rendered.width, rendered.height, rendered.rgba),
            contribution=DecodedPng(
                rendered_contribution.width,
                rendered_contribution.height,
                rendered_contribution.rgba,
            ),
        )
        records.append(
            {
                "viewId": view.view_id,
                "label": view.label,
                "sourceSha256": sha256_bytes(view.payload),
                "camera": rendered.camera,
                "renderSha256": sha256_bytes(payload),
                "renderedTriangleCount": rendered.rendered_triangle_count,
                "renderedForegroundPixels": len(rendered.foreground),
                "metrics": metrics,
            }
        )
    all_pass = all(_source_metrics_pass(_mapping(record.get("metrics"))) for record in records)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "closy.d0_texture_rerender.source_only_rerender.v3",
        "classification": "front_rear_source_only_not_held_out",
        "viewComparisons": records,
        "frontRearSilhouetteDelta": round(
            abs(
                float(_mapping(records[0]["metrics"])["silhouetteIoU"])
                - float(_mapping(records[1]["metrics"])["silhouetteIoU"])
            ),
            9,
        ),
        "allPredicatesPassed": all_pass,
        "renderer": "closy_independent_cpu_triangle_raster_v1",
        "sourceFixtureGeneratorReused": False,
        "evaluatorOnlyMounted": False,
        "integrity": {"sourceOnlyRerenderHash": ""},
    }
    _rehash(report, "sourceOnlyRerenderHash")
    return report, rendered_payloads


def _source_metrics_pass(metrics: Mapping[str, Any]) -> bool:
    logo_applicable = metrics.get("logoMetricApplicable") is True
    return (
        float(metrics.get("silhouetteIoU", 0.0)) >= 0.30
        and float(metrics.get("boundaryChamferNormalised", 1.0)) <= 0.095
        and float(metrics.get("landmarkReprojectionNormalised", 1.0)) <= 0.14
        and float(metrics.get("foregroundLinearSrgbMae", 1.0)) <= 0.24
        and float(metrics.get("renderedSeamDiscontinuityLinear", 1.0)) <= 0.22
        and float(metrics.get("visibleCoverage", 0.0)) >= 0.30
        and float(metrics.get("generatedRegionShare", 1.0)) <= 0.55
        and (
            not logo_applicable
            or (
                float(metrics.get("logoIoU", 0.0)) >= 0.02
                and float(metrics.get("logoDisplacementNormalised", 1.0)) <= 0.14
            )
        )
    )


def _prediction_freeze(
    *,
    protocol_commit_sha: str,
    implementation_anchor_sha: str,
    implementation: Mapping[str, Any],
    parent_manifest: Mapping[str, Any],
    atlas: GeometricAtlasBundle,
    source_views: tuple[Any, ...],
    source_report: Mapping[str, Any],
) -> dict[str, Any]:
    source_closure_hash = sha256_bytes(
        canonical_dumps(
            [
                {
                    "viewId": view.view_id,
                    "sha256": sha256_bytes(view.payload),
                    "camera": dict(view.camera),
                }
                for view in sorted(source_views, key=lambda item: item.label)
            ]
        ).encode("utf-8")
    )
    freeze: dict[str, Any] = {
        "schemaVersion": 1,
        "freezeVersion": PREDICTION_VERSION,
        "state": "frozen_before_known_target_mount",
        "protocolCommitSha": protocol_commit_sha,
        "protocolSha256": PROTOCOL_SHA256,
        "implementationAnchorSha": implementation_anchor_sha,
        "implementationBundleHash": implementation["implementationBundleHash"],
        "parentCandidateId": parent_manifest["candidateId"],
        "parentPackageDigest": parent_manifest["packageDigest"],
        "sourceClosureHash": source_closure_hash,
        "sourceOnlyRerenderHash": _mapping(source_report.get("integrity")).get(
            "sourceOnlyRerenderHash"
        ),
        "atlasHash": sha256_bytes(_artifact_bytes(atlas, BITMAP_PATHS["baseColor"])),
        "materialMapHashes": {
            key: sha256_bytes(_artifact_bytes(atlas, path))
            for key, path in BITMAP_PATHS.items()
            if key != "pbrReport"
        },
        "provenanceHash": sha256_bytes(_artifact_bytes(atlas, PROVENANCE_PATH)),
        "candidatePredictionProtocol": (
            "parent_geometry_byte_preserved_source_pixels_projected_through_visible_triangle_"
            "barycentric_material_uv_then_package_identity_rebuilt"
        ),
        "evaluatorOnlyPixelsMounted": False,
        "evaluatorOnlyDerivedEvidenceMounted": False,
        "evaluatorOnlyTarget3dMounted": False,
        "knownTargetTrialCount": 0,
        "integrity": {"predictionFreezeHash": ""},
    }
    _rehash(freeze, "predictionFreezeHash")
    return freeze


def _invalidation_report(
    parent: Path,
    candidate: Path,
    parent_manifest: Mapping[str, Any],
    manifest: Mapping[str, Any],
    atlas: GeometricAtlasBundle,
    freeze: Mapping[str, Any],
) -> dict[str, Any]:
    geometry = [
        {
            "path": relative,
            "parentSha256": sha256_file(parent / relative),
            "candidateSha256": sha256_file(candidate / relative),
            "byteIdentical": (parent / relative).read_bytes()
            == (candidate / relative).read_bytes(),
        }
        for relative in _GEOMETRY_PATHS
    ]
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "closy.d0_texture_rerender.identity_invalidation.v3",
        "parentCandidateId": parent_manifest["candidateId"],
        "candidateId": manifest["candidateId"],
        "invalidated": [
            "atlas",
            "material_maps",
            "source_contribution",
            "source_to_texel_provenance",
            "candidate_package",
            "runtime_package",
            "matrix_evidence_binding",
            "downstream_cache",
            "reports",
        ],
        "newIdentities": {
            "atlasHash": freeze["atlasHash"],
            "provenanceHash": freeze["provenanceHash"],
            "candidatePackageDigest": manifest["packageDigest"],
            "downstreamCacheKey": sha256_bytes(
                canonical_dumps(
                    {
                        "candidateId": manifest["candidateId"],
                        "atlasHash": freeze["atlasHash"],
                        "provenanceHash": freeze["provenanceHash"],
                    }
                ).encode("utf-8")
            ),
        },
        "retainedGeometryPhysics": geometry,
        "allRetainedGeometryPhysicsByteIdentical": all(item["byteIdentical"] for item in geometry),
        "matrixV3StatusChanged": False,
        "d0Rp07Promoted": False,
        "integrity": {"invalidationReportHash": ""},
    }
    _rehash(report, "invalidationReportHash")
    return report


def _runtime_package(target: Path, candidate: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    runtime_target = target / "candidate_runtime.closyruntime"
    build_runtime_package(
        runtime_target,
        inputs=RuntimePackageInputs(
            conventional_fallback_glb=candidate / "render/render_mesh.glb",
            source_link={
                "opaqueId": "src_public_d0_texture_v3_" + str(manifest["candidateId"])[-24:],
                "consentScope": "project_authored_public_fixture",
                "retentionPolicy": "portable_candidate_assets_only",
                "deletionPolicy": "source_registry_withdrawal_supported",
                "derivationPolicy": "known_target_regression_not_product_selected",
                "withdrawalStatus": "withdrawn",
            },
            platform_profile="portable-static-reference",
        ),
        force=True,
    )
    loaded = load_runtime_package(runtime_target, offline=True, support_zeroone_static=False)
    return {
        "status": "pass" if loaded.selected_bytes else "fail",
        "candidateId": manifest["candidateId"],
        "selectedSource": loaded.selected_source,
        "offline": loaded.offline,
        "runtimePackageDigest": loaded.package_digest,
        "runtimeV1SelectionChanged": False,
        "zeroOneStatic": "not_run_supplemental",
        "zeroOneDynamic": "not_run_supplemental",
    }


def _artifact_bytes(atlas: GeometricAtlasBundle, path: str) -> bytes:
    value = atlas.artifacts[path]
    if not isinstance(value, bytes):
        raise ValueError("d0_appearance_expected_atlas_bytes")
    return value


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"d0_appearance_expected_object:{path.name}")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rehash(document: dict[str, Any], key: str) -> None:
    payload = deepcopy(document)
    payload["integrity"] = dict(_mapping(document.get("integrity")))
    payload["integrity"][key] = ""
    document["integrity"][key] = sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _require_commit(value: str, label: str) -> None:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"d0_appearance_{label}_invalid")
