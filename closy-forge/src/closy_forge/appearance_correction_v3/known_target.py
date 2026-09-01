from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.appearance.bitmap_atlas import BITMAP_PATHS
from closy_forge.appearance_correction_v3.prediction import (
    DEFAULT_OUTPUT,
    validate_frozen_candidate,
)
from closy_forge.appearance_correction_v3.projection import (
    ACTIVE_MASK_PATH,
    PROVENANCE_MANIFEST_PATH,
    PROVENANCE_PATH,
    audit_geometric_source_atlas,
)
from closy_forge.appearance_correction_v3.protocol import load_correction_protocol
from closy_forge.appearance_correction_v3.source_inputs import load_locked_source_inputs
from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.inspection.cpu_raster import rasterize_settled_garment
from closy_forge.inspection.source_render_fidelity import (
    _atlas_sampler,
    compare_decoded_source_and_render,
)
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.raster import DecodedPng, decode_png_rgba, encode_png_rgba

EVALUATION_VERSION = "closy.d0_texture_rerender.known_target_regression.v3"
DEFAULT_EVALUATION_OUTPUT = Path("docs/evidence/d0_texture_rerender_correction_v3/evaluation")
_PARENT_ATTEMPT_REGISTRY = Path("docs/evidence/d0_evidence_integrity_v4/attempt_registry_v3.json")


def evaluate_known_target_once(
    root: Path,
    *,
    prediction_commit_sha: str,
    evaluator_anchor_sha: str,
    predictions: Path | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    _require_commit(prediction_commit_sha, "prediction_commit")
    _require_commit(evaluator_anchor_sha, "evaluator_anchor")
    prediction_root = predictions or root / DEFAULT_OUTPUT
    target = output or root / DEFAULT_EVALUATION_OUTPUT
    if target.exists():
        raise ValueError("d0_appearance_known_target_trial_already_exists")
    protocol = load_correction_protocol(root)
    freeze = _read(prediction_root / "prediction_freeze.json")
    _validate_prediction_freeze(freeze, prediction_commit_sha)
    candidate = prediction_root / "candidate_package"
    candidate_validation = validate_frozen_candidate(candidate)
    if candidate_validation["status"] != "pass":
        raise ValueError("d0_appearance_frozen_candidate_invalid")
    target.mkdir(parents=True)
    manifest = _read(candidate / "candidate_manifest.json")
    atlas_report = _read(candidate / BITMAP_PATHS["pbrReport"])
    artifacts = _atlas_artifacts(candidate, atlas_report)
    atlas_audit = audit_geometric_source_atlas(artifacts, atlas_report)
    atlas = decode_png_rgba(_bytes(artifacts[BITMAP_PATHS["baseColor"]]))
    contribution = decode_png_rgba(_bytes(artifacts[BITMAP_PATHS["sourceContribution"]]))
    mesh = read_glb_meshset(candidate / "simulation/settled_mesh.glb")

    views = list(load_locked_source_inputs(root))
    evaluator = _mount_known_evaluator(root, protocol)
    views.append(evaluator)
    view_records = []
    for view in views:
        rendered = rasterize_settled_garment(
            mesh,
            label=view.label,
            width=view.image.width,
            height=view.image.height,
            camera=view.camera,
            texture_sampler=_atlas_sampler(atlas, view.label),
        )
        rendered_contribution = rasterize_settled_garment(
            mesh,
            label=view.label,
            width=view.image.width,
            height=view.image.height,
            camera=view.camera,
            texture_sampler=_atlas_sampler(contribution, view.label),
        )
        render_bytes = encode_png_rgba(rendered.width, rendered.height, rendered.rgba)
        contribution_bytes = encode_png_rgba(
            rendered_contribution.width,
            rendered_contribution.height,
            rendered_contribution.rgba,
        )
        render_path = target / "renders" / f"{view.label}.png"
        contribution_path = target / "renders" / f"{view.label}_contribution.png"
        render_path.parent.mkdir(parents=True, exist_ok=True)
        render_path.write_bytes(render_bytes)
        contribution_path.write_bytes(contribution_bytes)
        metrics = compare_decoded_source_and_render(
            view.image,
            DecodedPng(rendered.width, rendered.height, rendered.rgba),
            contribution=DecodedPng(
                rendered_contribution.width,
                rendered_contribution.height,
                rendered_contribution.rgba,
            ),
        )
        view_records.append(
            {
                "viewId": view.view_id,
                "label": view.label,
                "classification": (
                    "known_evaluator_only_after_prediction_freeze"
                    if view.label == "left_three_quarter"
                    else "source_only_recomputed_after_freeze"
                ),
                "sourceSha256": sha256_bytes(view.payload),
                "camera": rendered.camera,
                "renderPath": render_path.relative_to(target).as_posix(),
                "renderSha256": sha256_bytes(render_bytes),
                "contributionPath": contribution_path.relative_to(target).as_posix(),
                "contributionSha256": sha256_bytes(contribution_bytes),
                "metrics": metrics,
            }
        )

    predicates = _predicate_table(
        protocol=protocol,
        freeze=freeze,
        manifest=manifest,
        candidate_validation=candidate_validation,
        atlas_report=atlas_report,
        atlas_audit=atlas_audit,
        views=view_records,
    )
    all_passed = all(bool(record["passed"]) for record in predicates)
    outcome = "known_target_regression_pass" if all_passed else "known_target_regression_fail"
    predicate_table: dict[str, Any] = {
        "schemaVersion": 1,
        "tableVersion": EVALUATION_VERSION,
        "atomic": True,
        "records": predicates,
        "passedCount": sum(1 for record in predicates if record["passed"]),
        "failedCount": sum(1 for record in predicates if not record["passed"]),
        "allApplicablePredicatesPassed": all_passed,
        "integrity": {"predicateTableHash": ""},
    }
    _rehash(predicate_table, "predicateTableHash")
    write_canonical_json(target / "predicate_table.json", predicate_table)
    attempt_registry = _attempt_registry(
        root,
        manifest=manifest,
        prediction_commit_sha=prediction_commit_sha,
        evaluator_anchor_sha=evaluator_anchor_sha,
        outcome=outcome,
        predicate_table=predicate_table,
    )
    write_canonical_json(target / "attempt_registry.json", attempt_registry)
    matrix_effect: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "closy.d0_texture_rerender.known_target_matrix_effect.v3",
        "knownTargetOutcome": outcome,
        "d0Rp07Before": "fail",
        "d0Rp07After": "fail",
        "d0Rp07Promoted": False,
        "researchPrototypePromoted": False,
        "matrixV3Changed": False,
        "reasonCode": "known_target_regression_cannot_establish_held_out_or_cohort_fidelity",
        "requiredNextEvidence": "unit_g_identity_disjoint_evaluator_cohort",
        "integrity": {"matrixEffectHash": ""},
    }
    _rehash(matrix_effect, "matrixEffectHash")
    write_canonical_json(target / "matrix_effect.json", matrix_effect)
    diagnostic: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceVersion": EVALUATION_VERSION,
        "classification": "known_target_regression_engineering_diagnostic_not_qualification",
        "outcome": outcome,
        "candidateId": manifest["candidateId"],
        "candidatePackageDigest": manifest["packageDigest"],
        "predictionCommitSha": prediction_commit_sha,
        "evaluatorAnchorSha": evaluator_anchor_sha,
        "knownTargetTrialNumber": 1,
        "knownTargetTrialBudget": 1,
        "sourceAndEvaluatorViews": view_records,
        "predicateTableHash": _mapping(predicate_table.get("integrity")).get("predicateTableHash"),
        "frontLogoIdentity": _front_logo(view_records),
        "atlasCoverage": dict(_mapping(atlas_report.get("coverage"))),
        "provenanceAudit": atlas_audit,
        "candidateValidation": candidate_validation,
        "evaluatorOnlyInfluencedPrediction": False,
        "generatedPixelsScoredAsSourceFidelity": False,
        "d0Rp07Status": "fail_preserved_pending_unit_g",
        "researchPrototypePromoted": False,
        "physicalPbrAccuracy": "not_measured",
        "runtimeV1SelectionChanged": False,
        "integrity": {"diagnosticHash": ""},
    }
    _rehash(diagnostic, "diagnosticHash")
    write_canonical_json(target / "known_target_diagnostic.json", diagnostic)
    summary: dict[str, Any] = {
        "schemaVersion": 1,
        "summaryVersion": EVALUATION_VERSION,
        "outcome": outcome,
        "candidateId": manifest["candidateId"],
        "knownTargetTrialCount": 1,
        "failedPredicateReasonCodes": [
            record["reasonCode"] for record in predicates if not record["passed"]
        ],
        "d0Rp07Status": "fail",
        "unitGRequired": True,
        "unsupportedClaims": [
            "held_out_texture_qualification",
            "identity_disjoint_fidelity",
            "real_photo_fidelity",
            "physical_pbr",
            "human_review",
            "private_user_evidence",
            "product_acceptance",
        ],
        "integrity": {"qualificationSummaryHash": ""},
    }
    _rehash(summary, "qualificationSummaryHash")
    write_canonical_json(target / "qualification_summary.json", summary)
    return summary


def _mount_known_evaluator(root: Path, protocol: Mapping[str, Any]) -> Any:
    known = _mapping(protocol.get("knownEvaluatorTarget"))
    ground_truth_path = root / str(known.get("groundTruthPath", ""))
    if sha256_file(ground_truth_path) != known.get("groundTruthSha256"):
        raise ValueError("d0_appearance_known_target_ground_truth_hash_mismatch")
    _read(ground_truth_path)
    manifest = _read(root / "fixtures/d0_exact_raster_v2/fixture_manifest.json")
    fixture = next(
        item
        for item in _list(manifest.get("fixtures"))
        if item.get("viewId") == known.get("viewId")
    )
    path = root / "fixtures/d0_exact_raster_v2" / str(fixture.get("relativePath", ""))
    payload = path.read_bytes()
    if sha256_bytes(payload) != known.get("sourceSha256"):
        raise ValueError("d0_appearance_known_target_source_hash_mismatch")
    image = decode_png_rgba(payload)
    from closy_forge.appearance_correction_v3.projection import SourceViewInput

    return SourceViewInput(
        view_id=str(fixture.get("viewId", "")),
        source_id="source.d0_tshirt_exact_evaluator_three_quarter_v2",
        label=str(fixture.get("label", "")),
        expected_sha256=str(known.get("sourceSha256", "")),
        payload=payload,
        image=image,
        camera=dict(_mapping(fixture.get("camera"))),
        garment_pixels=frozenset(),
        logo_pixels=frozenset(),
    )


def _predicate_table(
    *,
    protocol: Mapping[str, Any],
    freeze: Mapping[str, Any],
    manifest: Mapping[str, Any],
    candidate_validation: Mapping[str, Any],
    atlas_report: Mapping[str, Any],
    atlas_audit: Mapping[str, Any],
    views: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    thresholds = _mapping(protocol.get("thresholds"))
    records: list[dict[str, Any]] = []
    limits = {
        "silhouetteIoU": ("gte", thresholds["minimumSilhouetteIoU"]),
        "boundaryChamferNormalised": (
            "lte",
            thresholds["maximumBoundaryChamferNormalised"],
        ),
        "landmarkReprojectionNormalised": (
            "lte",
            thresholds["maximumLandmarkReprojectionNormalised"],
        ),
        "foregroundLinearSrgbMae": (
            "lte",
            thresholds["maximumForegroundLinearSrgbMae"],
        ),
        "renderedSeamDiscontinuityLinear": (
            "lte",
            thresholds["maximumSeamDiscontinuity"],
        ),
        "visibleCoverage": ("gte", thresholds["minimumVisibleCoverage"]),
        "generatedRegionShare": ("lte", thresholds["maximumGeneratedRegionShare"]),
    }
    for view in views:
        metrics = _mapping(view.get("metrics"))
        for metric, (operation, threshold) in limits.items():
            _append_numeric(
                records,
                predicate_id=f"{view['label']}.{metric}",
                scope=str(view["classification"]),
                observed=metrics.get(metric),
                operation=operation,
                threshold=threshold,
            )
    front_metrics = _mapping(next(item for item in views if item["label"] == "front")["metrics"])
    _append_numeric(
        records,
        predicate_id="front.logoIoU",
        scope="front_source_logo",
        observed=front_metrics.get("logoIoU"),
        operation="gte",
        threshold=thresholds["minimumLogoIoU"],
    )
    _append_numeric(
        records,
        predicate_id="front.logoDisplacementNormalised",
        scope="front_source_logo",
        observed=front_metrics.get("logoDisplacementNormalised"),
        operation="lte",
        threshold=thresholds["maximumLogoDisplacementNormalised"],
    )
    source = [item for item in views if item["label"] in {"front", "back"}]
    silhouette_delta = abs(
        float(_mapping(source[0]["metrics"])["silhouetteIoU"])
        - float(_mapping(source[1]["metrics"])["silhouetteIoU"])
    )
    _append_numeric(
        records,
        predicate_id="frontRearSilhouetteDelta",
        scope="source_views",
        observed=silhouette_delta,
        operation="lte",
        threshold=thresholds["maximumFrontRearSilhouetteDelta"],
    )
    coverage = _mapping(atlas_report.get("coverage"))
    _append_numeric(
        records,
        predicate_id="atlas.sourceObservedFraction",
        scope="active_semantic_islands",
        observed=coverage.get("sourceObservedFraction"),
        operation="gte",
        threshold=thresholds["minimumSourceObservedAtlasFraction"],
    )
    _append_numeric(
        records,
        predicate_id="atlas.generatedFillNonzero",
        scope="active_semantic_islands",
        observed=coverage.get("generatedControlledFillFraction"),
        operation="gt",
        threshold=thresholds["minimumGeneratedFillFractionExclusive"],
    )
    pbr = _mapping(atlas_report.get("pbr"))
    _append_numeric(
        records,
        predicate_id="pbr.metallicFactor",
        scope="material",
        observed=pbr.get("metallicFactor"),
        operation="lte",
        threshold=thresholds["maximumMetallicFactor"],
    )
    _append_numeric(
        records,
        predicate_id="pbr.minimumRoughnessFactor",
        scope="material",
        observed=pbr.get("minimumRoughnessFactor"),
        operation="gte",
        threshold=thresholds["minimumRoughnessFactor"],
    )
    _append_equals(
        records,
        "pbr.physicalAccuracy",
        "material",
        pbr.get("normalRoughnessAoPhysicalAccuracy"),
        thresholds["physicalNormalRoughnessAoAccuracy"],
    )
    _append_equals(
        records,
        "provenance.audit",
        "candidate_package",
        atlas_audit.get("status"),
        "pass",
    )
    _append_equals(
        records,
        "candidate.validation",
        "candidate_package",
        candidate_validation.get("status"),
        "pass",
    )
    _append_equals(
        records,
        "prediction.evaluatorOnlyPixelsMounted",
        "information_boundary",
        freeze.get("evaluatorOnlyPixelsMounted"),
        False,
    )
    _append_equals(
        records,
        "prediction.knownTargetTrialCountBeforeMount",
        "information_boundary",
        freeze.get("knownTargetTrialCount"),
        0,
    )
    _append_equals(
        records,
        "candidate.identity",
        "candidate_package",
        bool(manifest.get("candidateId")) and bool(manifest.get("packageDigest")),
        True,
    )
    return records


def _append_numeric(
    records: list[dict[str, Any]],
    *,
    predicate_id: str,
    scope: str,
    observed: object,
    operation: str,
    threshold: object,
) -> None:
    value = (
        float(observed)
        if isinstance(observed, int | float) and not isinstance(observed, bool)
        else None
    )
    if not isinstance(threshold, int | float) or isinstance(threshold, bool):
        raise ValueError(f"d0_appearance_nonnumeric_threshold:{predicate_id}")
    limit = float(threshold)
    passed = (
        value is not None
        and {
            "gte": value >= limit,
            "lte": value <= limit,
            "gt": value > limit,
        }[operation]
    )
    records.append(
        {
            "predicateId": predicate_id,
            "scope": scope,
            "operation": operation,
            "threshold": limit,
            "observed": value,
            "passed": passed,
            "reasonCode": "predicate_passed" if passed else f"predicate_failed:{predicate_id}",
        }
    )


def _append_equals(
    records: list[dict[str, Any]],
    predicate_id: str,
    scope: str,
    observed: object,
    expected: object,
) -> None:
    passed = observed == expected
    records.append(
        {
            "predicateId": predicate_id,
            "scope": scope,
            "operation": "equals",
            "threshold": expected,
            "observed": observed,
            "passed": passed,
            "reasonCode": "predicate_passed" if passed else f"predicate_failed:{predicate_id}",
        }
    )


def _attempt_registry(
    root: Path,
    *,
    manifest: Mapping[str, Any],
    prediction_commit_sha: str,
    evaluator_anchor_sha: str,
    outcome: str,
    predicate_table: Mapping[str, Any],
) -> dict[str, Any]:
    parent = _read(root / _PARENT_ATTEMPT_REGISTRY)
    predecessor = str(parent["headHash"])
    record: dict[str, Any] = {
        "sequence": int(parent["recordCount"]) + 1,
        "attemptId": "attempt.unit_f.known_target_texture.001",
        "lineageId": "lineage.known_target_texture.source_projection_v3",
        "rowId": "D0-RP-07",
        "scope": "known_target_regression_not_qualification",
        "strategyId": "geometric_source_surface_atlas_projection",
        "candidateId": manifest["candidateId"],
        "candidatePackageDigest": manifest["packageDigest"],
        "predictionCommitSha": prediction_commit_sha,
        "evaluatorAnchorSha": evaluator_anchor_sha,
        "attemptState": outcome,
        "currentD0Rp07Status": "attempted_fail",
        "reasonCode": (
            "known_target_predicates_passed_unit_g_still_required"
            if outcome == "known_target_regression_pass"
            else "known_target_predicates_failed_no_second_unit_f_trial"
        ),
        "predicateTableHash": _mapping(predicate_table.get("integrity")).get("predicateTableHash"),
        "predecessorHash": predecessor,
        "recordHash": "",
    }
    record["recordHash"] = sha256_bytes(canonical_dumps(record).encode("utf-8"))
    return {
        "schemaVersion": 1,
        "registryVersion": "closy.d0_texture_rerender.attempt_registry.v3",
        "appendOnly": True,
        "parentRegistryPath": _PARENT_ATTEMPT_REGISTRY.as_posix(),
        "parentHeadHash": predecessor,
        "recordCount": 1,
        "maximumKnownTargetTrials": 1,
        "records": [record],
        "headHash": record["recordHash"],
    }


def _validate_prediction_freeze(freeze: Mapping[str, Any], prediction_commit_sha: str) -> None:
    if freeze.get("state") != "frozen_before_known_target_mount":
        raise ValueError("d0_appearance_prediction_not_frozen")
    if freeze.get("evaluatorOnlyPixelsMounted") is not False:
        raise ValueError("d0_appearance_evaluator_influenced_prediction")
    if freeze.get("knownTargetTrialCount") != 0:
        raise ValueError("d0_appearance_trial_budget_already_spent")
    if not prediction_commit_sha:
        raise ValueError("d0_appearance_prediction_commit_missing")


def _front_logo(views: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = _mapping(next(item for item in views if item["label"] == "front")["metrics"])
    return {
        "logoIoU": metrics.get("logoIoU"),
        "logoDisplacementNormalised": metrics.get("logoDisplacementNormalised"),
        "applicable": metrics.get("logoMetricApplicable"),
    }


def _atlas_artifacts(
    candidate: Path, report: Mapping[str, Any]
) -> dict[str, bytes | Mapping[str, Any]]:
    paths = [
        *(str(item["path"]) for item in _list(report.get("maps"))),
        PROVENANCE_PATH,
        PROVENANCE_MANIFEST_PATH,
        ACTIVE_MASK_PATH,
    ]
    artifacts: dict[str, bytes | Mapping[str, Any]] = {}
    for relative in sorted(set(paths)):
        path = candidate / relative
        if path.suffix == ".json":
            artifacts[relative] = _read(path)
        else:
            artifacts[relative] = path.read_bytes()
    return artifacts


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"d0_appearance_expected_object:{path.name}")
    return value


def _list(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bytes(value: bytes | Mapping[str, Any]) -> bytes:
    if not isinstance(value, bytes):
        raise ValueError("d0_appearance_expected_bytes")
    return value


def _rehash(document: dict[str, Any], key: str) -> None:
    payload = deepcopy(document)
    payload["integrity"] = dict(_mapping(document.get("integrity")))
    payload["integrity"][key] = ""
    document["integrity"][key] = sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _require_commit(value: str, label: str) -> None:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"d0_appearance_{label}_invalid")
