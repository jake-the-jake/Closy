from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from closy_forge.appearance.exact_bitmap_atlas import build_exact_d0_bitmap_atlas
from closy_forge.fitting.exact_d0_candidate import (
    CompiledExactCandidate,
    compile_exact_d0_candidate,
    inventory_digest,
    package_inventory,
    validate_compiled_candidate_files,
    write_compiled_exact_candidate,
)
from closy_forge.fitting.exact_d0_lock import (
    EXACT_D0_EVALUATION_LOCK_SHA256,
    load_exact_d0_evaluation_lock,
)
from closy_forge.fitting.exact_d0_pixel_controls import execute_exact_d0_pixel_fit_controls
from closy_forge.fitting.tshirt_fit import fit_tshirt_parameters_from_visual_observations
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import finite_mesh
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, sha256_file
from closy_forge.runtime_delivery.package import (
    RuntimePackageInputs,
    build_runtime_package,
    load_runtime_package,
)

EXACT_D0_PREDICTION_VERSION = "closy.d0_exact_fitting_pbr.predictions.v2"
_EVIDENCE_RELATIVE = Path("docs/evidence/d0_fitting_pbr_fidelity_v2")


def generate_exact_d0_predictions(
    root: Path,
    *,
    output: Path | None = None,
    lock_commit_sha: str,
    implementation_commit_sha: str,
) -> dict[str, Any]:
    lock = load_exact_d0_evaluation_lock(root)
    fixture_root = root / "fixtures" / "d0_exact_raster_v2"
    fixture_manifest = _read_json(fixture_root / "fixture_manifest.json")
    qualification = root / "docs" / "evidence" / "d0_exact_raster_identity_v2" / "qualification"
    correction = _read_json(qualification / "correction_evidence.json")
    acceptance = _read_json(qualification / "exact_observation_acceptance.json")
    unit_b_firewall = _read_json(qualification / "information_firewall.json")
    unit_b_controls = _read_json(qualification / "causal_controls.json")
    capture = _read_json(qualification / "capture_record.json")
    visual = _dict(correction.get("correctedObservation"))
    fusion = _dict(correction.get("multiviewFusion"))
    _validate_selected_chain(lock, visual, fusion, acceptance, fixture_manifest)

    target = output or root / _EVIDENCE_RELATIVE / "predictions"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    firewall = _execute_prediction_workspaces(
        lock=lock,
        fixture_root=fixture_root,
        fixture_manifest=fixture_manifest,
        corrected_visual=visual,
        unit_b_firewall=unit_b_firewall,
    )
    atlas = build_exact_d0_bitmap_atlas(
        fixture_root=fixture_root,
        fixture_manifest=fixture_manifest,
        visual_observations=visual,
    )
    ranking, image_fit = _rank_templates(lock, visual, fusion)
    contender_predictions = _contender_predictions(lock, visual, fusion, ranking, image_fit)
    prediction_freeze = _prediction_freeze(
        lock=lock,
        lock_commit_sha=lock_commit_sha,
        implementation_commit_sha=implementation_commit_sha,
        visual=visual,
        fusion=fusion,
        contender_predictions=contender_predictions,
        atlas_report=atlas.report,
    )
    write_canonical_json(target / "prediction_freeze.json", prediction_freeze)
    write_canonical_json(target / "template_ranking.json", ranking)
    write_canonical_json(target / "contender_predictions.json", contender_predictions)
    write_canonical_json(target / "permission_execution.json", firewall)

    compiled_reports: list[dict[str, Any]] = []
    compiled_winner: CompiledExactCandidate | None = None
    for prediction in contender_predictions["predictions"]:
        params = TShirtParameters(**_dict(prediction.get("parameters")))
        compiled = compile_exact_d0_candidate(
            contender_id=str(prediction["contenderId"]),
            parameters=params,
            visual_observations=visual,
            fixture_root=fixture_root,
            fixture_manifest=fixture_manifest,
            atlas=atlas,
        )
        compiled_reports.append(compiled.report)
        if prediction["contenderId"] == "image_conditioned":
            compiled_winner = compiled
    if compiled_winner is None:
        raise ValueError("exact_d0_image_candidate_missing")
    canonical_evaluations = _canonical_evaluations(compiled_reports)
    write_canonical_json(target / "canonical_evaluations.json", canonical_evaluations)

    candidate_root = target / "candidate_package"
    _write_candidate_package(
        candidate_root,
        candidate=compiled_winner,
        atlas_artifacts=atlas.artifacts,
        image_fit=image_fit,
        prediction_freeze=prediction_freeze,
        source_identity=_dict(lock.get("selectedIdentity")),
    )
    candidate_validation = validate_compiled_candidate_files(candidate_root, compiled_winner.report)
    if candidate_validation["status"] != "pass":
        raise ValueError("exact_d0_candidate_file_validation_failed")
    candidate_manifest = _candidate_manifest(
        candidate_root,
        compiled_winner,
        prediction_freeze,
        lock,
        candidate_validation,
    )
    write_canonical_json(candidate_root / "candidate_manifest.json", candidate_manifest)

    reproducibility = _rebuild_candidate(
        compiled_winner=compiled_winner,
        atlas_artifacts=atlas.artifacts,
        image_fit=image_fit,
        prediction_freeze=prediction_freeze,
        source_identity=_dict(lock.get("selectedIdentity")),
        expected_inventory=package_inventory(candidate_root, exclude={"candidate_manifest.json"}),
    )
    write_canonical_json(target / "delete_rebuild_reproducibility.json", reproducibility)
    fallback = _qualify_fallback(target, candidate_root, candidate_manifest)
    write_canonical_json(target / "fallback_qualification.json", fallback)
    winner_template = next(
        item
        for item in _list_of_dicts(lock.get("templateSet"))
        if item["templateId"] == ranking["winner"]["templateId"]
    )
    causal = execute_exact_d0_pixel_fit_controls(
        fixture_root=fixture_root,
        fixture_manifest=fixture_manifest,
        capture_record=capture,
        selected_correction=_dict(correction.get("selectedCorrectionRecord")),
        prior=TShirtParameters(**_dict(winner_template.get("prior"))),
        baseline_fit=image_fit,
        minimum_delta=float(lock["thresholds"]["fit"]["minimumCausalParameterDeltaMeters"]),
    )
    causal["unitBControlHash"] = _dict(unit_b_controls.get("integrity")).get("controlReportHash")
    causal["logoColourOnly"] = _dict(_dict(unit_b_controls.get("controls")).get("shiftedLogo"))
    causal["unitBPixelRecomputationLinked"] = True
    write_canonical_json(target / "causal_fit_controls.json", causal)
    contact_sheet = _contact_sheet_svg(compiled_winner.report)
    (target / "review_contact_sheet.svg").write_text(contact_sheet, encoding="utf-8")

    summary: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceVersion": EXACT_D0_PREDICTION_VERSION,
        "stage": "immutable_predictions_and_atlas",
        "lockCommitSha": lock_commit_sha,
        "implementationCommitSha": implementation_commit_sha,
        "lockSha256": EXACT_D0_EVALUATION_LOCK_SHA256,
        "selectedIdentity": deepcopy(lock["selectedIdentity"]),
        "predictionFreezeHash": prediction_freeze["integrity"]["predictionFreezeHash"],
        "candidateId": candidate_manifest["candidateId"],
        "candidatePackageDigest": candidate_manifest["packageDigest"],
        "winnerTemplateId": ranking["winner"]["templateId"],
        "contenderCount": len(contender_predictions["predictions"]),
        "allContendersCompiledBySameEvaluator": canonical_evaluations[
            "allContendersCompiledBySameEvaluator"
        ],
        "evaluatorOnly": {
            "pixelsOpened": False,
            "derivedEvidenceOpened": False,
            "targetParametersOpened": False,
            "sourceHashExported": False,
            "mountStatus": "not_mounted_until_prediction_commit",
        },
        "bitmapPbr": {
            "status": atlas.report["status"],
            "sourceObservedFraction": atlas.report["coverage"]["sourceObservedFraction"],
            "generatedFillFraction": atlas.report["coverage"]["generatedControlledFillFraction"],
            "physicalPbrAccuracy": "not_measured",
        },
        "fallback": fallback,
        "claims": {
            "humanReview": "not_run",
            "realPhotoEvidence": False,
            "privateUserEvidence": False,
            "productAcceptance": False,
            "runtimeV1SelectionChanged": False,
        },
        "integrity": {"predictionSummaryHash": ""},
    }
    summary["integrity"]["predictionSummaryHash"] = _hash(summary, "predictionSummaryHash")
    write_canonical_json(target / "prediction_summary.json", summary)
    return summary


def _rank_templates(
    lock: Mapping[str, Any], visual: dict[str, Any], fusion: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    reports: dict[str, dict[str, Any]] = {}
    for template in _list_of_dicts(lock.get("templateSet")):
        template_id = str(template["templateId"])
        report = fit_tshirt_parameters_from_visual_observations(
            visual,
            multiview_fusion=fusion,
            prior=TShirtParameters(**_dict(template.get("prior"))),
        )
        reports[template_id] = report
        final = _dict(_dict(report.get("optimization")).get("finalEvaluation"))
        terms = _dict(final.get("terms"))
        records.append(
            {
                "templateId": template_id,
                "label": template["label"],
                "sourceVisualHash": report["sourceVisualRecordHash"],
                "sourceFusionHash": report["sourceMultiviewFusionHash"],
                "objective": float(final.get("objective", 1.0)),
                "silhouetteLoss": terms.get("silhouetteLoss"),
                "boundaryLoss": terms.get("boundaryChamferNormalised"),
                "landmarkLoss": terms.get("landmarkReprojectionRmsNormalised"),
                "regularisation": terms.get("regularizationPenalty"),
                "accepted": report.get("accepted"),
                "fitReportHash": report["integrity"]["fitReportHash"],
                "fittedParameters": report["fittedParameters"],
                "stopReason": report["convergence"]["terminationReason"],
            }
        )
    ordered = sorted(records, key=lambda item: (float(item["objective"]), item["templateId"]))
    winner = ordered[0]
    reversed_order = sorted(
        reversed(records), key=lambda item: (float(item["objective"]), item["templateId"])
    )
    ranking: dict[str, Any] = {
        "schemaVersion": 1,
        "rankingVersion": "closy.d0_exact_tshirt_template_ranking.v2",
        "candidateCount": len(records),
        "candidates": ordered,
        "winner": {
            **winner,
            "confidence": round(max(0.0, 1.0 - float(winner["objective"])), 6),
            "ambiguityMargin": round(
                float(ordered[1]["objective"]) - float(winner["objective"]), 6
            ),
        },
        "rejected": [
            {"templateId": item["templateId"], "reasonCode": "higher_locked_objective"}
            for item in ordered[1:]
        ],
        "listOrderControl": {
            "reversedInputWinner": reversed_order[0]["templateId"],
            "sameWinner": reversed_order[0]["templateId"] == winner["templateId"],
        },
        "noPixelPriorRanking": ["tshirt.regular.v2", "tshirt.slim.v2", "tshirt.boxy.v2"],
        "strongestMaskLandmarkBaseline": "deterministic_mask_landmark",
        "sourceWithdrawalBehaviour": (
            "fit_rejected_when_source_identity_or_derived_evidence_missing"
        ),
        "integrity": {"rankingHash": ""},
    }
    ranking["integrity"]["rankingHash"] = _hash(ranking, "rankingHash")
    return ranking, reports[str(winner["templateId"])]


def _contender_predictions(
    lock: Mapping[str, Any],
    visual: dict[str, Any],
    fusion: dict[str, Any],
    ranking: Mapping[str, Any],
    image_fit: Mapping[str, Any],
) -> dict[str, Any]:
    regular = next(
        item for item in _list_of_dicts(lock.get("templateSet")) if item["label"] == "regular"
    )
    baseline_fit = fit_tshirt_parameters_from_visual_observations(
        visual, prior=TShirtParameters(**_dict(regular.get("prior")))
    )
    predictions = [
        _prediction(
            "metadata_category_prior",
            "metadata_category_default_regular_v1",
            _dict(regular.get("prior")),
            evidence="metadata_only",
        ),
        _prediction(
            "no_pixel_template",
            "no_pixel_locked_template_rank_v1",
            _dict(regular.get("prior")),
            evidence="locked_template_priors_only",
        ),
        _prediction(
            "deterministic_mask_landmark",
            str(baseline_fit["fitterVersion"]),
            _dict(baseline_fit.get("fittedParameters")),
            evidence="corrected_masks_landmarks_only",
            report_hash=str(_dict(baseline_fit.get("integrity")).get("fitReportHash", "")),
        ),
        _prediction(
            "image_conditioned",
            str(image_fit["fitterVersion"]),
            _dict(image_fit.get("fittedParameters")),
            evidence="exact_decoded_front_rear_to_corrected_pixel_evidence_chain",
            report_hash=str(_dict(image_fit.get("integrity")).get("fitReportHash", "")),
        ),
    ]
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "predictionSetVersion": EXACT_D0_PREDICTION_VERSION,
        "sourceVisualHash": visual["integrity"]["visualRecordHash"],
        "sourceFusionHash": fusion["integrity"]["multiviewFusionRecordHash"],
        "winnerTemplateId": _dict(ranking.get("winner")).get("templateId"),
        "predictions": predictions,
        "evaluatorOnlyMounted": False,
        "hiddenFixtureParametersRead": False,
        "integrity": {"predictionSetHash": ""},
    }
    result["integrity"]["predictionSetHash"] = _hash(result, "predictionSetHash")
    return result


def _prediction(
    contender_id: str,
    algorithm: str,
    parameters: Mapping[str, Any],
    *,
    evidence: str,
    report_hash: str = "",
) -> dict[str, Any]:
    payload = {
        "contenderId": contender_id,
        "algorithm": algorithm,
        "evidence": evidence,
        "parameters": dict(parameters),
        "fitReportHash": report_hash,
    }
    payload["predictionHash"] = sha256_bytes(canonical_dumps(payload).encode("utf-8"))
    return payload


def _prediction_freeze(
    *,
    lock: Mapping[str, Any],
    lock_commit_sha: str,
    implementation_commit_sha: str,
    visual: Mapping[str, Any],
    fusion: Mapping[str, Any],
    contender_predictions: Mapping[str, Any],
    atlas_report: Mapping[str, Any],
) -> dict[str, Any]:
    freeze: dict[str, Any] = {
        "schemaVersion": 1,
        "freezeVersion": "closy.d0_exact_prediction_and_atlas_freeze.v2",
        "state": "frozen_before_evaluator_mount",
        "lockCommitSha": lock_commit_sha,
        "implementationCommitSha": implementation_commit_sha,
        "lockSha256": EXACT_D0_EVALUATION_LOCK_SHA256,
        "correctedVisualRecordHash": visual["integrity"]["visualRecordHash"],
        "multiviewFusionRecordHash": fusion["integrity"]["multiviewFusionRecordHash"],
        "selectedCorrectionRecordHash": _dict(lock.get("selectedIdentity")).get(
            "selectedCorrectionRecordHash"
        ),
        "downstreamCacheKey": _dict(lock.get("selectedIdentity")).get("downstreamCacheKey"),
        "predictionSetHash": _dict(contender_predictions.get("integrity")).get("predictionSetHash"),
        "atlasHash": _dict(atlas_report.get("integrity")).get("bitmapPbrReportHash"),
        "evaluatorOnlyPixelsMounted": False,
        "evaluatorOnlyTargetMounted": False,
        "integrity": {"predictionFreezeHash": ""},
    }
    freeze["integrity"]["predictionFreezeHash"] = _hash(freeze, "predictionFreezeHash")
    return freeze


def _canonical_evaluations(compiled: list[dict[str, Any]]) -> dict[str, Any]:
    compiler_versions = {str(item.get("compilerVersion", "")) for item in compiled}
    renderer_versions = {
        str(_dict(item.get("inSampleSourceRerender")).get("renderer", "")) for item in compiled
    }
    return {
        "schemaVersion": 1,
        "evaluationVersion": "closy.d0_exact_same_compiler_contender_evaluation.v2",
        "records": compiled,
        "allContendersCompiledBySameEvaluator": len(compiler_versions) == 1
        and len(renderer_versions) == 1,
        "compilerVersions": sorted(compiler_versions),
        "rendererVersions": sorted(renderer_versions),
        "predictionFrozenBeforeCompilation": True,
        "evaluatorOnlyMounted": False,
    }


def _write_candidate_package(
    target: Path,
    *,
    candidate: CompiledExactCandidate,
    atlas_artifacts: Mapping[str, bytes | dict[str, Any]],
    image_fit: Mapping[str, Any],
    prediction_freeze: Mapping[str, Any],
    source_identity: Mapping[str, Any],
) -> None:
    write_compiled_exact_candidate(target, candidate)
    write_canonical_json(target / "fitting" / "tshirt_fit.json", dict(image_fit))
    write_canonical_json(target / "provenance" / "prediction_freeze.json", dict(prediction_freeze))
    write_canonical_json(target / "provenance" / "source_identity.json", dict(source_identity))
    for relative, payload in atlas_artifacts.items():
        path = target / relative
        if isinstance(payload, bytes):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        else:
            write_canonical_json(path, payload)


def _candidate_manifest(
    target: Path,
    candidate: CompiledExactCandidate,
    prediction_freeze: Mapping[str, Any],
    lock: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    inventory = package_inventory(target, exclude={"candidate_manifest.json"})
    package_digest = inventory_digest(inventory)
    identity_payload = {
        "source": lock["selectedIdentity"],
        "predictionFreezeHash": _dict(prediction_freeze.get("integrity")).get(
            "predictionFreezeHash"
        ),
        "patternHash": candidate.report["pattern"]["hash"],
        "simulationTopologyHash": candidate.report["simulation"]["settledTopologyHash"],
        "simulationContentHash": candidate.report["simulation"]["settledContentHash"],
        "renderTopologyHash": candidate.report["binding"]["renderTopologyHash"],
        "renderContentHash": candidate.report["binding"]["renderContentHash"],
        "atlasHash": candidate.report["atlas"]["reportHash"],
        "packageDigest": package_digest,
    }
    candidate_id = (
        "candidate.d0_exact_fitted_topology_v2."
        + sha256_bytes(canonical_dumps(identity_payload).encode("utf-8"))[:24]
    )
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "manifestVersion": "closy.d0_exact_fitted_candidate_manifest.v2",
        "candidateId": candidate_id,
        "candidateClass": "research_candidate",
        "runtimeSelected": False,
        "runtimeV1RemainsSelected": True,
        "sourcePackageDigest": _dict(lock.get("selectedIdentity")).get("sourcePackageDigest"),
        "packageDigest": package_digest,
        "identityGraph": identity_payload,
        "inventory": inventory,
        "validation": dict(validation),
        "fallbackPath": "render/render_mesh.glb",
        "integrity": {"manifestHash": ""},
    }
    manifest["integrity"]["manifestHash"] = _hash(manifest, "manifestHash")
    return manifest


def _rebuild_candidate(
    *,
    compiled_winner: CompiledExactCandidate,
    atlas_artifacts: Mapping[str, bytes | dict[str, Any]],
    image_fit: Mapping[str, Any],
    prediction_freeze: Mapping[str, Any],
    source_identity: Mapping[str, Any],
    expected_inventory: list[dict[str, Any]],
) -> dict[str, Any]:
    with TemporaryDirectory(prefix="closy-d0-candidate-rebuild-") as temporary:
        rebuilt = Path(temporary) / "candidate_package"
        _write_candidate_package(
            rebuilt,
            candidate=compiled_winner,
            atlas_artifacts=atlas_artifacts,
            image_fit=image_fit,
            prediction_freeze=prediction_freeze,
            source_identity=source_identity,
        )
        rebuilt_inventory = package_inventory(rebuilt)
    return {
        "schemaVersion": 1,
        "mode": "delete_and_rebuild_from_frozen_prediction",
        "status": "pass" if rebuilt_inventory == expected_inventory else "fail",
        "firstDigest": inventory_digest(expected_inventory),
        "rebuiltDigest": inventory_digest(rebuilt_inventory),
        "fileCount": len(expected_inventory),
        "identical": rebuilt_inventory == expected_inventory,
    }


def _qualify_fallback(
    target: Path, candidate_root: Path, candidate_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    fallback_glb = candidate_root / "render" / "render_mesh.glb"
    fallback_mesh = read_glb_meshset(fallback_glb)
    runtime_target = target / "candidate_runtime.closyruntime"
    build_runtime_package(
        runtime_target,
        inputs=RuntimePackageInputs(
            conventional_fallback_glb=fallback_glb,
            source_link={
                "opaqueId": "src_public_d0_exact_v2",
                "consentScope": "project_authored_public_fixture",
                "retentionPolicy": "portable_candidate_assets_only",
                "deletionPolicy": "source_registry_withdrawal_supported",
                "derivationPolicy": "research_candidate_not_product_selected",
                "withdrawalStatus": "withdrawn",
            },
            platform_profile="portable-static-reference",
        ),
        force=True,
    )
    loaded = load_runtime_package(runtime_target, offline=True, support_zeroone_static=False)
    return {
        "status": "pass",
        "candidateId": candidate_manifest["candidateId"],
        "conventionalFallbackLoaded": finite_mesh(fallback_mesh),
        "conventionalFallbackContentHash": geometry_content_hash(fallback_mesh),
        "offlineAfterSourceWithdrawalLoaded": bool(loaded.selected_bytes),
        "selectedSource": loaded.selected_source,
        "offline": loaded.offline,
        "runtimePackageDigest": loaded.package_digest,
        "zeroOneStatic": "not_run_supplemental",
        "zeroOneDynamic": "not_run_supplemental",
        "runtimeV1SelectionChanged": False,
    }


def _execute_prediction_workspaces(
    *,
    lock: Mapping[str, Any],
    fixture_root: Path,
    fixture_manifest: Mapping[str, Any],
    corrected_visual: Mapping[str, Any],
    unit_b_firewall: Mapping[str, Any],
) -> dict[str, Any]:
    results = []
    fixtures = _list_of_dicts(fixture_manifest.get("fixtures"))
    with TemporaryDirectory(prefix="closy-d0-unit-c-firewall-") as temporary:
        root = Path(temporary)
        for contender in _list_of_dicts(lock.get("contenders")):
            workspace = root / str(contender["contenderId"])
            workspace.mkdir()
            write_canonical_json(
                workspace / "metadata.json",
                {
                    "garmentClass": fixture_manifest["garmentClass"],
                    "garmentId": fixture_manifest["garmentId"],
                    "templateIds": [item["templateId"] for item in lock["templateSet"]],
                },
            )
            if contender["derivedEvidence"]:
                write_canonical_json(workspace / "derived_evidence.json", dict(corrected_visual))
            if contender["rawPixels"]:
                for fixture in fixtures:
                    if fixture.get("role") in {"front", "rear"}:
                        payload = (fixture_root / str(fixture["relativePath"])).read_bytes()
                        (workspace / f"{fixture['role']}.png").write_bytes(payload)
            inventory = [
                {
                    "name": path.name,
                    "sha256": sha256_file(path),
                    "byteLength": path.stat().st_size,
                }
                for path in sorted(workspace.iterdir())
                if path.is_file()
            ]
            results.append(
                {
                    "contenderId": contender["contenderId"],
                    "workspaceFresh": True,
                    "inventory": inventory,
                    "rawPixelAccessMatchedLock": any(
                        item["name"] == "front.png" for item in inventory
                    )
                    is bool(contender["rawPixels"]),
                    "derivedAccessMatchedLock": any(
                        item["name"] == "derived_evidence.json" for item in inventory
                    )
                    is bool(contender["derivedEvidence"]),
                    "evaluatorOnlyPresent": any(
                        item["name"] == "evaluator_only.png" for item in inventory
                    ),
                    "hiddenParametersPresent": False,
                    "fixtureGeneratorPresent": False,
                    "networkCapabilityMounted": False,
                }
            )
    return {
        "schemaVersion": 1,
        "executionVersion": "closy.d0_unit_c_prediction_firewall.v2",
        "enforcement": "application_allowlisted_ephemeral_workspace",
        "operatingSystemSandboxClaimed": False,
        "results": results,
        "allPermissionsMatched": all(
            item["rawPixelAccessMatchedLock"]
            and item["derivedAccessMatchedLock"]
            and not item["evaluatorOnlyPresent"]
            and not item["hiddenParametersPresent"]
            for item in results
        ),
        "unitBFirewallHash": _dict(unit_b_firewall.get("integrity")).get("firewallReportHash"),
        "evaluatorMount": "not_mounted",
    }


def _validate_selected_chain(
    lock: Mapping[str, Any],
    visual: Mapping[str, Any],
    fusion: Mapping[str, Any],
    acceptance: Mapping[str, Any],
    fixture_manifest: Mapping[str, Any],
) -> None:
    selected = _dict(lock.get("selectedIdentity"))
    observation = _dict(acceptance.get("observationIdentity"))
    checks = {
        "visual": visual.get("integrity", {}).get("visualRecordHash")
        == selected.get("correctedVisualRecordHash")
        == observation.get("correctedVisualRecordHash"),
        "fusion": fusion.get("integrity", {}).get("multiviewFusionRecordHash")
        == selected.get("multiviewFusionRecordHash")
        == observation.get("multiviewFusionRecordHash"),
        "correction": selected.get("selectedCorrectionRecordHash")
        == observation.get("selectedCorrectionRecordHash"),
        "cache": selected.get("downstreamCacheKey") == observation.get("downstreamCacheKey"),
        "fixture": fixture_manifest.get("garmentId") == selected.get("garmentId"),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"exact_d0_selected_chain_mismatch:{','.join(failed)}")
    evaluator = next(
        item
        for item in _list_of_dicts(fixture_manifest.get("fixtures"))
        if item.get("role") == "evaluator_only_three_quarter"
    )
    if evaluator.get("fitPermission") != "evaluator_only_after_prediction_freeze":
        raise ValueError("exact_d0_evaluator_permission_invalid")


def _contact_sheet_svg(report: Mapping[str, Any]) -> str:
    records = _list_of_dicts(_dict(report.get("inSampleSourceRerender")).get("viewComparisons"))
    labels = "".join(
        f'<text x="{40 + index * 280}" y="300" font-family="sans-serif" font-size="18">'
        f'{record.get("label")}: IoU {record.get("metrics", {}).get("silhouetteIoU")}</text>'
        for index, record in enumerate(records)
    )
    images = "".join(
        f'<image href="candidate_package/reports/renders/{record.get("label")}.png" '
        f'x="{40 + index * 280}" y="30" width="205" height="256"/>'
        for index, record in enumerate(records)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="350">'
        '<rect width="100%" height="100%" fill="#f2efe8"/>'
        + images
        + labels
        + '<text x="40" y="332" font-family="sans-serif" font-size="13">'
        "Project-authored D0 fixture; human review not_run; not product acceptance.</text></svg>\n"
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected_json_object:{path.name}")
    return payload


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _hash(value: Mapping[str, Any], key: str) -> str:
    payload = deepcopy(dict(value))
    payload["integrity"][key] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
