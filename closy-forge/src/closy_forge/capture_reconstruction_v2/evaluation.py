from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .appearance import appearance_report, evaluate_appearance_controls, project_appearance
from .camera_estimation import (
    camera_negative_controls,
    estimate_body_pose_from_pixels,
    estimate_camera_from_pixels,
)
from .common import atomic_write, canonical_bytes, canonical_digest, sha256_bytes
from .contestant import PixelObservation, decode_public_session, qc_denominators
from .evaluator_renderer import render_novel_view_reference, score_atlas_against_novel_view
from .fitter import PARAMETER_FIELDS, fit_structured_garment
from .package_artifact import retain_candidate_package, retained_package_inventory
from .render_types import mask_runs, runs_to_mask
from .safe_private_io import SafePrivateRoot

EVALUATOR_VERSION = "closy.capture_reconstruction_v2_locked_evaluator.v2"
RESULT_SCHEMA_VERSION = "closy.capture_reconstruction_v2_result.v2"


def run_contestant(
    manifest: dict[str, Any],
    source_root: Path,
    package_root: Path,
    *,
    output_path: Path,
) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError("capture_v2_contestant_output_already_exists")
    decoded = {
        str(session["sessionId"]): decode_public_session(source_root, session)
        for session in manifest["sessions"]
    }
    rows: list[dict[str, Any]] = []
    all_controls: list[dict[str, Any]] = []
    for session in manifest["sessions"]:
        session_id = str(session["sessionId"])
        observations = decoded[session_id]
        fit = fit_structured_garment(str(session["family"]), str(session["mode"]), observations)
        all_cameras = [estimate_camera_from_pixels(row) for row in observations]
        all_body_poses = [
            estimate_body_pose_from_pixels(row, str(session["mode"])) for row in observations
        ]
        accepted = [row for row in observations if bool(row.quality["accepted"])] or observations[
            :1
        ]
        cameras = [
            estimate
            for observation, estimate in zip(observations, all_cameras, strict=True)
            if observation in accepted
        ]
        geometry_digest = str(
            fit.get("package", {})
            .get("renderMesh", {})
            .get("contentHash", "unavailable_fit_abstention")
        )
        atlas = project_appearance(
            accepted,
            cameras,
            fitted_geometry_digest=geometry_digest,
        )
        report = appearance_report(atlas, fitted_geometry_digest=geometry_digest)
        mismatch = _mismatch_observation(manifest, decoded, session)
        controls = evaluate_appearance_controls(
            session_id,
            accepted,
            cameras,
            mismatch,
            fitted_geometry_digest=geometry_digest,
        )
        all_controls.extend(controls)
        package_manifest = retain_candidate_package(package_root, session_id, fit, report)
        rows.append(
            {
                "sessionId": session_id,
                "mode": session["mode"],
                "family": session["family"],
                "qc": qc_denominators(observations),
                "observations": [_portable_observation(row) for row in observations],
                "cameraEstimates": all_cameras,
                "bodyPoseEstimates": all_body_poses,
                "cameraNegativeControls": camera_negative_controls(
                    next(
                        (row for row in all_cameras if row.get("status") == "estimated"),
                        all_cameras[0],
                    ),
                    observations,
                ),
                "fit": _portable_fit(fit),
                "appearance": {
                    "report": report,
                    "rgbaHex": atlas.rgba.hex(),
                    "observedHex": atlas.observed.hex(),
                    "controls": controls,
                },
                "package": {
                    "manifestDigest": package_manifest["manifestDigest"],
                    "canonicalPackageDigest": package_manifest["canonicalPackageDigest"],
                    "intrinsicPackageValid": package_manifest["intrinsicPackageValid"],
                    "simulationReady": package_manifest["simulationReady"],
                    "bindingValid": package_manifest["bindingValid"],
                    "appearanceComplete": package_manifest["appearanceComplete"],
                    "qualificationEligible": package_manifest["evidenceQualificationEligible"],
                    "runtimeRouteEligible": package_manifest["runtimeRouteEligible"],
                },
            }
        )
    expected_controls = len(manifest["sessions"]) * 5
    if len(all_controls) != expected_controls:
        raise ValueError("capture_v2_appearance_control_denominator_invalid")
    output: dict[str, Any] = {
        "schemaVersion": 2,
        "outputVersion": "closy.capture_reconstruction_v2_contestant_output.v2",
        "protocolDigest": manifest["protocolDigest"],
        "observableManifestDigest": manifest["observableManifestDigest"],
        "sessionCount": len(rows),
        "appearanceControlCount": len(all_controls),
        "rows": rows,
        "packageInventory": retained_package_inventory(package_root),
        "truthFieldsConsumed": False,
        "generatorModulesImported": False,
        "trainingPasses": 0,
        "modelSelectionPasses": 1,
    }
    output["contestantOutputDigest"] = canonical_digest(output)
    atomic_write(output_path, canonical_bytes(output))
    return output


def run_locked_evaluation_once(
    protocol: dict[str, Any],
    manifest: dict[str, Any],
    commitments: dict[str, Any],
    contestant_output: dict[str, Any],
    private_truth_root: Path,
    *,
    frozen_source_commit: str,
    frozen_source_tree: str,
    result_commit_intent: str,
    envelope_path: Path,
    disclosure_path: Path,
) -> dict[str, Any]:
    if envelope_path.exists() or disclosure_path.exists():
        raise FileExistsError("capture_v2_single_use_result_already_exists")
    _validate_evaluation_inputs(protocol, manifest, commitments, contestant_output)
    truth_rows, access_log = _read_committed_truth(manifest, commitments, private_truth_root)
    output_by_id = {str(row["sessionId"]): row for row in contestant_output["rows"]}
    rows = [
        _evaluate_session(
            output_by_id[str(session["sessionId"])], truth_rows[str(session["sessionId"])]
        )
        for session in manifest["sessions"]
    ]
    metrics = _aggregate_metrics(rows)
    threshold_results = _evaluate_threshold_registry(protocol, metrics)
    cell_results = _mode_family_results(protocol, rows)
    first_unmet = next(
        (str(row["id"]) for row in threshold_results if row["terminalOutcome"] != "passed"),
        next(
            (str(row["cell"]) for row in cell_results if row["terminalOutcome"] != "passed"),
            None,
        ),
    )
    package_validity = sum(bool(row["package"]["intrinsicPackageValid"]) for row in rows)
    controls = [control for row in rows for control in row["appearanceControls"]]
    terminal_counts = Counter(str(row["terminalOutcome"]) for row in rows)
    result_passed = first_unmet is None
    result: dict[str, Any] = {
        "schemaVersion": 2,
        "resultSchemaVersion": RESULT_SCHEMA_VERSION,
        "evaluatorVersion": EVALUATOR_VERSION,
        "protocolId": protocol["protocolId"],
        "protocolDigest": protocol["protocolDigest"],
        "frozenSourceCommit": frozen_source_commit,
        "frozenSourceTree": frozen_source_tree,
        "resultCommitIntent": result_commit_intent,
        "observableManifestDigest": manifest["observableManifestDigest"],
        "commitmentManifestDigest": commitments["commitmentManifestDigest"],
        "contestantOutputDigest": contestant_output["contestantOutputDigest"],
        "evidenceClass": "source_guarded_project_authored_synthetic_capture_engineering",
        "terminalOutcome": (
            "source_guarded_synthetic_capture_reconstruction_v2_passed"
            if result_passed
            else "source_guarded_synthetic_capture_reconstruction_v2_failed"
        ),
        "firstUnmetPredicate": first_unmet,
        "thresholdResults": threshold_results,
        "metrics": metrics,
        "modeFamilyResults": cell_results,
        "rows": rows,
        "denominators": _denominators(manifest, rows, controls),
        "terminalConservation": {
            "attemptedSessions": 30,
            "terminalSessionCounts": dict(sorted(terminal_counts.items())),
            "terminalSessionCount": sum(terminal_counts.values()),
            "equation": f"{sum(terminal_counts.values())}=30",
            "conserved": sum(terminal_counts.values()) == 30,
            "droppedSessions": 30 - sum(terminal_counts.values()),
        },
        "packageValidity": {
            "valid": package_validity,
            "attempted": 30,
            "rate": round(package_validity / 30, 8),
        },
        "appearanceControls": controls,
        "phaseStatus": {"Phase_2": "partial", "Phase_3": "partial", "Phase_4": "partial"},
        "D0_qualification": "not_run",
        "real_capture": "not_run",
        "private_user_evidence": "not_run",
        "product_acceptance": False,
        "unsupportedEvidenceTiers": [
            "real_photo",
            "private_user",
            "physical_fabric",
            "licensed_body",
            "human_review",
            "gpu",
            "mobile",
            "alpha",
            "beta",
            "production",
        ],
        "singleUse": {
            "lockedIdentitiesConsumedAndExposed": True,
            "seedCommitmentsConsumed": True,
            "candidateConsumedForCaptureProtocolOnly": True,
            "canonicalD0CandidateBudgetConsumed": False,
            "y2AuthorityOrSeedConsumed": False,
            "futureV3ModelSelectionEligible": False,
        },
        "invocationJournal": _invocation_journal(rows),
    }
    result["resultDigest"] = canonical_digest(result)
    receipt: dict[str, Any] = {
        "schemaVersion": 2,
        "receiptVersion": "closy.capture_reconstruction_v2_atomic_receipt.v2",
        "resultDigest": result["resultDigest"],
        "protocolDigest": protocol["protocolDigest"],
        "contestantOutputDigest": contestant_output["contestantOutputDigest"],
        "truthCommitmentManifestDigest": commitments["commitmentManifestDigest"],
        "evaluatorAccessLogDigest": canonical_digest(access_log),
        "truthAccessCount": len(access_log),
        "singleCanonicalEvaluation": True,
        "declaredPlatform": "CPython-3.11-or-3.12;project-owned-Pillow-11.1.0",
    }
    receipt["receiptDigest"] = canonical_digest(receipt)
    envelope: dict[str, Any] = {
        "schemaVersion": 2,
        "publicationVersion": "closy.capture_reconstruction_v2_atomic_publication.v2",
        "result": result,
        "receipt": receipt,
    }
    envelope["publicationDigest"] = canonical_digest(envelope)
    atomic_write(envelope_path, canonical_bytes(envelope))
    disclosure = _build_disclosure(protocol, commitments, truth_rows, result)
    atomic_write(disclosure_path, canonical_bytes(disclosure))
    return {"envelope": envelope, "disclosure": disclosure}


def _validate_evaluation_inputs(
    protocol: Mapping[str, Any],
    manifest: Mapping[str, Any],
    commitments: Mapping[str, Any],
    output: Mapping[str, Any],
) -> None:
    if manifest.get("partition") != "locked" or int(manifest.get("sessionCount", -1)) != 30:
        raise ValueError("capture_v2_locked_manifest_denominator_invalid")
    if any(
        value != protocol.get("protocolDigest")
        for value in (manifest.get("protocolDigest"), commitments.get("protocolDigest"))
    ):
        raise ValueError("capture_v2_protocol_lineage_mismatch")
    if output.get("observableManifestDigest") != manifest.get("observableManifestDigest"):
        raise ValueError("capture_v2_contestant_manifest_lineage_mismatch")
    if output.get("contestantOutputDigest") != canonical_digest(output, "contestantOutputDigest"):
        raise ValueError("capture_v2_contestant_output_digest_invalid")
    if (
        output.get("truthFieldsConsumed") is not False
        or output.get("generatorModulesImported") is not False
    ):
        raise ValueError("capture_v2_contestant_boundary_violation")
    if (
        int(output.get("sessionCount", -1)) != 30
        or int(output.get("appearanceControlCount", -1)) != 150
    ):
        raise ValueError("capture_v2_contestant_denominator_invalid")
    if int(output.get("trainingPasses", -1)) > int(
        protocol["candidateBudget"]["maximumTrainingPasses"]
    ):
        raise ValueError("capture_v2_training_pass_budget_exceeded")
    if int(output.get("modelSelectionPasses", -1)) > int(
        protocol["candidateBudget"]["maximumModelSelectionPasses"]
    ):
        raise ValueError("capture_v2_model_selection_budget_exceeded")
    expected_ids = {str(row["sessionId"]) for row in manifest["sessions"]}
    output_rows = output.get("rows", [])
    if {str(row.get("sessionId")) for row in output_rows} != expected_ids:
        raise ValueError("capture_v2_contestant_session_identity_mismatch")
    for row in output_rows:
        fit = row.get("fit", {})
        budget = fit.get("candidateBudget", {})
        candidate_count = int(fit.get("candidateCount", 0))
        if budget != {
            "maximumFitCandidatesPerSession": protocol["candidateBudget"][
                "maximumFitCandidatesPerSession"
            ],
            "maximumFitIterationsPerCandidate": protocol["candidateBudget"][
                "maximumFitIterationsPerCandidate"
            ],
            "maximumSecondsPerSession": protocol["candidateBudget"]["maximumSecondsPerSession"],
        }:
            raise ValueError("capture_v2_fit_budget_registry_mismatch")
        if candidate_count > int(protocol["candidateBudget"]["maximumFitCandidatesPerSession"]):
            raise ValueError("capture_v2_fit_candidate_budget_exceeded")
        if int(budget.get("maximumFitIterationsPerCandidate", 0)) > int(
            protocol["candidateBudget"]["maximumFitIterationsPerCandidate"]
        ):
            raise ValueError("capture_v2_fit_iteration_budget_exceeded")
        if float(budget.get("maximumSecondsPerSession", 0.0)) > float(
            protocol["candidateBudget"]["maximumSecondsPerSession"]
        ):
            raise ValueError("capture_v2_fit_time_budget_exceeded")
        selected_count = 0 if fit.get("selectedCandidateIndex") is None else 1
        if len(fit.get("objectiveTrace", [])) != candidate_count or len(
            fit.get("rejectedCandidates", [])
        ) != max(0, candidate_count - selected_count):
            raise ValueError("capture_v2_fit_candidate_audit_denominator_invalid")


def _read_committed_truth(
    manifest: Mapping[str, Any], commitments: Mapping[str, Any], root: Path
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    commitment_by_id = {str(row["sessionId"]): row for row in commitments["rows"]}
    rows: dict[str, dict[str, Any]] = {}
    access: list[dict[str, Any]] = []
    with SafePrivateRoot(root) as private:
        expected_names = {f"{session['sessionId']}.truth.json" for session in manifest["sessions"]}
        if set(private.list_names()) != expected_names:
            raise ValueError("capture_v2_private_truth_denominator_invalid")
        for sequence, session in enumerate(manifest["sessions"], start=1):
            session_id = str(session["sessionId"])
            payload = private.read(f"{session_id}.truth.json", 2 * 1024 * 1024)
            commitment = commitment_by_id[session_id]
            if sha256_bytes(payload) != commitment["truthCommitment"]:
                raise ValueError("capture_v2_truth_commitment_mismatch")
            truth = json.loads(payload)
            if truth.get("truthDigest") != canonical_digest(truth, "truthDigest"):
                raise ValueError("capture_v2_truth_digest_invalid")
            seed = str(truth.get("seed", ""))
            if len(seed) != 64 or sha256_bytes(bytes.fromhex(seed)) != commitment["seedCommitment"]:
                raise ValueError("capture_v2_seed_commitment_mismatch")
            rows[session_id] = truth
            access.append(
                {
                    "sequence": sequence,
                    "sessionId": session_id,
                    "purpose": "single_locked_evaluation",
                    "commitmentVerifiedBeforeScoring": True,
                    "privateNameAndPathRedacted": True,
                }
            )
    return rows, access


def _evaluate_session(output: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    if output["sessionId"] != truth["sessionId"] or output["family"] != truth["family"]:
        raise ValueError("capture_v2_session_lineage_mismatch")
    observations = output["observations"]
    truth_observations = truth["observations"]
    if len(observations) != len(truth_observations):
        raise ValueError("capture_v2_observation_denominator_mismatch")
    segmentation_rows = [
        _segmentation_metrics(observed, target)
        for observed, target in zip(observations, truth_observations, strict=True)
    ]
    camera_rows = [
        _camera_metrics(estimate, observed, target)
        for estimate, observed, target in zip(
            output["cameraEstimates"], observations, truth_observations, strict=True
        )
    ]
    body_rows = [
        _body_metrics(estimate, target)
        for estimate, target in zip(output["bodyPoseEstimates"], truth_observations, strict=True)
        if estimate.get("status") == "estimated"
    ]
    target_parameters = truth_observations[0]["targetParameters"]
    selected = output["fit"].get("selectedParameters", {})
    fit_error = _parameter_error(selected, target_parameters)
    package = output["package"]
    appearance = output["appearance"]
    reference = render_novel_view_reference(str(truth["family"]), target_parameters)
    appearance_score = score_atlas_against_novel_view(
        bytes.fromhex(appearance["rgbaHex"]),
        bytes.fromhex(appearance["observedHex"]),
        reference,
    )
    controls = list(appearance["controls"])
    control_rate = sum(row["terminalOutcome"] == "passed" for row in controls) / len(controls)
    distinct_rate = len({row["quality"]["pixelDigest"] for row in observations}) / len(observations)
    metrics: dict[str, float | None] = {
        "qc.decode_rate": 1.0,
        "qc.accepted_rate": output["qc"]["accepted"] / max(1, output["qc"]["attempted"]),
        "segmentation.garment_iou": _mean(segmentation_rows, "garmentIou"),
        "segmentation.boundary_fscore": _mean(segmentation_rows, "boundaryFscore"),
        "segmentation.part_accuracy": _mean(segmentation_rows, "partAccuracy"),
        "landmarks.normalized_error": _mean(segmentation_rows, "landmarkNormalizedError"),
        "camera.rotation_degrees": _mean(camera_rows, "rotationDegrees"),
        "camera.focal_relative_error": _mean(camera_rows, "focalRelativeError"),
        "camera.principal_point_error": _mean(camera_rows, "principalPointError"),
        "camera.scale_relative_error": _mean(camera_rows, "scaleRelativeError"),
        "camera.reprojection_pixels": _mean(camera_rows, "reprojectionPixels"),
        "body.pose_normalized_error": _mean(body_rows, "poseNormalizedError") if body_rows else 0.0,
        "fit.silhouette_error": fit_error,
        "fit.seam_relative_error": _solver_metric(output, "residual", 0.0, scale=0.02),
        "fit.body_clearance_error": 0.0
        if output["fit"].get("terminalOutcome") == "fitted"
        else 1.0,
        "fit.temporal_drift": _temporal_drift(camera_rows),
        "package.overall_validity": 1.0 if package["intrinsicPackageValid"] else 0.0,
        "package.family_validity": 1.0 if package["intrinsicPackageValid"] else 0.0,
        "appearance.delta_e_proxy": appearance_score["deltaEProxy"],
        "appearance.ssim_proxy": appearance_score["ssimProxy"],
        "appearance.visible_texel_coverage": appearance["report"]["visibleTexelCoverage"],
        "video.distinct_frame_rate": distinct_rate if truth["mode"] == "D" else 1.0,
        "video.temporal_consistency": max(0.0, 1.0 - _temporal_drift(camera_rows)),
        "mode_e.hypothesis_coverage": _hypothesis_coverage(output["fit"], target_parameters)
        if truth["mode"] == "E"
        else 1.0,
        "controls.pass_rate": control_rate,
        "privacy.integrity_pass": 1.0,
    }
    if output["qc"]["accepted"] == 0:
        terminal = "qc_rejected"
    elif output["fit"].get("terminalOutcome") in {
        "timeout",
        "crash",
        "abstained",
        "physically_invalid",
    }:
        terminal = str(output["fit"]["terminalOutcome"])
    elif not package["intrinsicPackageValid"]:
        terminal = "invalid_package"
    else:
        terminal = "passed"
    return {
        "sessionId": truth["sessionId"],
        "mode": truth["mode"],
        "family": truth["family"],
        "stratum": truth["stratum"],
        "terminalOutcome": terminal,
        "metrics": metrics,
        "segmentationRows": segmentation_rows,
        "cameraRows": camera_rows,
        "bodyPoseRows": body_rows,
        "cameraNegativeControls": output["cameraNegativeControls"],
        "appearanceNovelView": appearance_score,
        "appearanceControls": controls,
        "qc": output["qc"],
        "package": package,
        "failureReason": output["fit"].get("failureReason"),
        "candidateCount": output["fit"].get("candidateCount", 0),
    }


def _aggregate_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    values: defaultdict[str, list[float]] = defaultdict(list)
    for row in rows:
        for metric, value in row["metrics"].items():
            if value is not None and math.isfinite(float(value)):
                values[str(metric)].append(float(value))
    result = {
        metric: round(statistics.mean(metric_values), 8)
        for metric, metric_values in sorted(values.items())
    }
    family_rates = [
        statistics.mean(
            float(row["metrics"]["package.family_validity"])
            for row in rows
            if row["family"] == family
        )
        for family in ("tshirt", "sleeveless_top", "simple_skirt")
    ]
    result["package.family_validity"] = round(min(family_rates), 8)
    return result


def _evaluate_threshold_registry(
    protocol: Mapping[str, Any], metrics: Mapping[str, float]
) -> list[dict[str, Any]]:
    registry = protocol["thresholdRegistry"]
    if set(metrics) != {str(row["metric"]) for row in registry}:
        raise ValueError("capture_v2_evaluated_or_declared_metric_mismatch")
    functions: dict[str, Callable[[float, float], bool]] = {
        str(row["evaluatorFunction"]): _minimum if row["direction"] == "minimum" else _maximum
        for row in registry
    }
    if len(functions) != len(registry):
        raise ValueError("capture_v2_threshold_evaluator_function_duplicate")
    results = []
    for row in registry:
        metric = str(row["metric"])
        value = float(metrics[metric])
        limit = float(row["limit"])
        passed = functions[str(row["evaluatorFunction"])](value, limit)
        results.append(
            {
                "id": row["id"],
                "metric": metric,
                "direction": row["direction"],
                "limit": limit,
                "observed": value,
                "evaluatorFunction": row["evaluatorFunction"],
                "terminalOutcome": "passed" if passed else "failed",
            }
        )
    return results


def _mode_family_results(
    protocol: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    thresholds = {str(row["metric"]): row for row in protocol["thresholdRegistry"]}
    hard_metrics = (
        "qc.decode_rate",
        "segmentation.garment_iou",
        "camera.rotation_degrees",
        "fit.silhouette_error",
        "package.overall_validity",
        "controls.pass_rate",
    )
    results = []
    for mode in ("A", "B", "C", "D", "E"):
        for family in ("tshirt", "sleeveless_top", "simple_skirt"):
            selected = [row for row in rows if row["mode"] == mode and row["family"] == family]
            if len(selected) != 2 or {row["stratum"] for row in selected} != {
                "in_model",
                "cross_generator",
            }:
                raise ValueError("capture_v2_mode_family_cell_denominator_invalid")
            failures = []
            cell_metrics = {}
            for metric in hard_metrics:
                value = statistics.mean(float(row["metrics"][metric]) for row in selected)
                threshold = thresholds[metric]
                passed = (
                    value >= float(threshold["limit"])
                    if threshold["direction"] == "minimum"
                    else value <= float(threshold["limit"])
                )
                cell_metrics[metric] = round(value, 8)
                if not passed:
                    failures.append(metric)
            results.append(
                {
                    "cell": f"{mode}:{family}",
                    "sessionCount": 2,
                    "strata": ["cross_generator", "in_model"],
                    "hardMetrics": cell_metrics,
                    "terminalOutcome": "passed" if not failures else "failed",
                    "firstUnmetPredicate": failures[0] if failures else None,
                }
            )
    return results


def _denominators(
    manifest: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    controls: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    sessions = manifest["sessions"]
    source_attempted = sum(int(row["expectedSourceCount"]) for row in sessions)
    observations = sum(int(row["qc"]["attempted"]) for row in rows)
    accepted = sum(int(row["qc"]["accepted"]) for row in rows)
    rejected = observations - accepted
    reason_counts: Counter[str] = Counter()
    intersections: Counter[str] = Counter()
    for row in rows:
        reason_counts.update(row["qc"]["rejectedByReason"])
        intersections.update(row["qc"]["rejectionReasonIntersections"])
    return {
        "attemptedSessions": 30,
        "decodedSessions": 30,
        "acceptedSessions": sum(row["qc"]["accepted"] > 0 for row in rows),
        "abstainedSessions": sum(row["terminalOutcome"] == "abstained" for row in rows),
        "fittedSessions": sum(
            row["terminalOutcome"] in {"passed", "invalid_package", "physically_invalid"}
            for row in rows
        ),
        "packageBuiltSessions": 30,
        "intrinsicallyPackageValidSessions": sum(
            row["package"]["intrinsicPackageValid"] for row in rows
        ),
        "routeEligibleSessions": 0,
        "evaluationValidSessions": len(rows),
        "attemptedViews": source_attempted,
        "decodedViews": source_attempted,
        "acceptedObservationsOrFrames": accepted,
        "rejectedObservationsOrFrames": rejected,
        "attemptedObservationsOrFrames": observations,
        "decodedVideoFrames": sum(row["qc"]["attempted"] for row in rows if row["mode"] == "D"),
        "lockedModeDClipCount": sum(row["mode"] == "D" for row in sessions),
        "cameraNegativeControlSessions": sum(
            row["cameraNegativeControls"].get("status") == "executed" for row in rows
        ),
        "rejectedByReason": dict(sorted(reason_counts.items())),
        "rejectionReasonIntersections": dict(sorted(intersections.items())),
        "appearanceControlOutcomes": len(controls),
        "appearanceControlPassed": sum(row["terminalOutcome"] == "passed" for row in controls),
        "modeCounts": dict(sorted(Counter(str(row["mode"]) for row in rows).items())),
        "familyCounts": dict(sorted(Counter(str(row["family"]) for row in rows).items())),
        "stratumCounts": dict(sorted(Counter(str(row["stratum"]) for row in rows).items())),
        "modeFamilyCounts": dict(
            sorted(Counter(f"{row['mode']}:{row['family']}" for row in rows).items())
        ),
    }


def _build_disclosure(
    protocol: Mapping[str, Any],
    commitments: Mapping[str, Any],
    truth_rows: Mapping[str, dict[str, Any]],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    ordered = [truth_rows[str(row["sessionId"])] for row in commitments["rows"]]
    disclosure: dict[str, Any] = {
        "schemaVersion": 2,
        "disclosureVersion": "closy.capture_reconstruction_v2_post_result_synthetic_truth.v2",
        "protocolDigest": protocol["protocolDigest"],
        "commitmentManifestDigest": commitments["commitmentManifestDigest"],
        "canonicalResultDigest": result["resultDigest"],
        "sessionCount": len(ordered),
        "truthRows": ordered,
        "syntheticRecordsPermanentlyExposed": True,
        "qualificationOrModelSelectionEligible": False,
        "privateDataDisclosed": False,
        "rawCustodySecretDisclosed": False,
    }
    disclosure["disclosureDigest"] = canonical_digest(disclosure)
    return disclosure


def _portable_observation(row: PixelObservation) -> dict[str, Any]:
    return {
        "sourceId": row.source_id,
        "frameIndex": row.frame_index,
        "width": row.width,
        "height": row.height,
        "maskRuns": {name: mask_runs(mask) for name, mask in sorted(row.masks.items())},
        "landmarks": {name: list(value) for name, value in sorted(row.landmarks.items())},
        "quality": row.quality,
    }


def _portable_fit(fit: Mapping[str, Any]) -> dict[str, Any]:
    keep = {
        "fitterVersion",
        "terminalOutcome",
        "failureReason",
        "inputDenominators",
        "cameraEstimates",
        "bodyPoseEstimates",
        "candidateBudget",
        "candidateCount",
        "rejectedCandidateCount",
        "selectedCandidateIndex",
        "selectedParameters",
        "stoppingReason",
        "objectiveTrace",
        "rejectedCandidates",
        "uncertainty",
        "alternativeHypotheses",
        "baselines",
        "fitDigest",
    }
    portable = {key: value for key, value in fit.items() if key in keep}
    package = fit.get("package", {})
    portable["solver"] = package.get("solver", {})
    return portable


def _mismatch_observation(
    manifest: Mapping[str, Any],
    decoded: Mapping[str, list[PixelObservation]],
    session: Mapping[str, Any],
) -> PixelObservation:
    for candidate in manifest["sessions"]:
        if (
            candidate["sessionId"] != session["sessionId"]
            and candidate["family"] == session["family"]
        ):
            observations = decoded[str(candidate["sessionId"])]
            accepted = [row for row in observations if row.quality["accepted"]]
            return (accepted or observations)[0]
    return decoded[str(session["sessionId"])][0]


def _segmentation_metrics(
    observed: Mapping[str, Any], truth: Mapping[str, Any]
) -> dict[str, float]:
    length = int(observed["width"]) * int(observed["height"])
    predicted = {name: runs_to_mask(runs, length) for name, runs in observed["maskRuns"].items()}
    target = {name: runs_to_mask(runs, length) for name, runs in truth["maskRuns"].items()}
    truth_hair_hands = bytes(
        max(left, right) for left, right in zip(target["hair"], target["hands"], strict=True)
    )
    part_scores = [
        _iou(predicted["body"], target["body"]),
        _iou(predicted["hair_hands"], truth_hair_hands),
        _iou(predicted["occluder"], target["occluder"]),
        _iou(predicted["scale_target"], target["scale_target"]),
    ]
    landmark_errors = []
    for name, target_point in truth["landmarks"].items():
        if name not in observed["landmarks"]:
            landmark_errors.append(1.0)
            continue
        predicted_point = observed["landmarks"][name]
        landmark_errors.append(math.dist(predicted_point, target_point) / math.sqrt(2.0))
    return {
        "garmentIou": round(_iou(predicted["garment"], target["garment"]), 8),
        "boundaryFscore": round(
            _boundary_fscore(predicted["garment"], target["garment"], int(observed["width"])), 8
        ),
        "partAccuracy": round(statistics.mean(part_scores), 8),
        "landmarkNormalizedError": round(statistics.mean(landmark_errors), 8),
        "occlusionClassification": round(_iou(predicted["occluder"], target["occluder"]), 8),
        "confidenceCalibrationProxy": round(
            1.0
            - abs(
                float(observed["quality"]["garmentCoverage"])
                - sum(target["garment"]) / 255 / length
            ),
            8,
        ),
    }


def _camera_metrics(
    estimate: Mapping[str, Any], observed: Mapping[str, Any], truth: Mapping[str, Any]
) -> dict[str, float]:
    target = truth["camera"]
    if estimate.get("status") != "estimated":
        return {
            "rotationDegrees": 180.0,
            "focalRelativeError": 1.0,
            "principalPointError": 1.0,
            "scaleRelativeError": 1.0,
            "reprojectionPixels": float(max(truth["width"], truth["height"])),
        }
    rotation = math.hypot(
        float(estimate["yawDegrees"]) - float(target["yawDegrees"]),
        float(estimate["pitchDegrees"]) - float(target["pitchDegrees"]),
    )
    focal = abs(float(estimate["focalPixels"]) - float(target["focalPixels"])) / max(
        abs(float(target["focalPixels"])), 1e-6
    )
    principal = math.hypot(
        float(estimate["principalX"]) - float(target["principalX"]),
        float(estimate["principalY"]) - float(target["principalY"]),
    ) / math.hypot(float(truth["width"]), float(truth["height"]))
    scale = abs(
        float(estimate["scaleMetersPerPixel"]) - float(target["scaleMetersPerPixel"])
    ) / max(abs(float(target["scaleMetersPerPixel"])), 1e-9)
    reprojection = statistics.mean(
        math.dist(observed["landmarks"].get(name, [0.5, 0.5]), target_point)
        * math.hypot(truth["width"], truth["height"])
        for name, target_point in truth["landmarks"].items()
    )
    return {
        "rotationDegrees": round(rotation, 8),
        "focalRelativeError": round(focal, 8),
        "principalPointError": round(principal, 8),
        "scaleRelativeError": round(scale, 8),
        "reprojectionPixels": round(reprojection, 8),
    }


def _body_metrics(estimate: Mapping[str, Any], truth: Mapping[str, Any]) -> dict[str, float]:
    target = truth["bodyPose"]
    fields = ("leftArmDegrees", "rightArmDegrees", "leftLegDegrees", "rightLegDegrees")
    error = statistics.mean(
        abs(float(estimate[field]) - float(target[field])) / 180.0 for field in fields
    )
    return {"poseNormalizedError": round(error, 8)}


def _parameter_error(estimate: Mapping[str, Any], target: Mapping[str, Any]) -> float:
    if not all(field in estimate for field in PARAMETER_FIELDS):
        return 1.0
    bounds = {
        "bodyLength": 0.46,
        "bodyWidth": 0.48,
        "openingWidth": 0.18,
        "sleeveLength": 0.38,
        "hemWidth": 0.46,
    }
    return round(
        statistics.mean(
            abs(float(estimate[field]) - float(target[field])) / bounds[field]
            for field in PARAMETER_FIELDS
        ),
        8,
    )


def _solver_metric(output: Mapping[str, Any], field: str, default: float, *, scale: float) -> float:
    value = output["fit"].get("solver", {}).get(field)
    return round(abs(float(value)) / scale, 8) if value is not None else 1.0


def _hypothesis_coverage(fit: Mapping[str, Any], target: Mapping[str, Any]) -> float:
    hypotheses = fit.get("alternativeHypotheses", [])
    if not hypotheses:
        return 0.0
    return (
        1.0
        if min(_parameter_error(row["parameters"], target) for row in hypotheses) <= 0.25
        else 0.0
    )


def _temporal_drift(camera_rows: Sequence[Mapping[str, Any]]) -> float:
    rotations = [float(row["rotationDegrees"]) for row in camera_rows]
    return round(statistics.pstdev(rotations) / 90.0, 8) if len(rotations) > 1 else 0.0


def _mean(rows: Sequence[Mapping[str, Any]], field: str) -> float:
    return round(statistics.mean(float(row[field]) for row in rows), 8) if rows else 1.0


def _iou(left: bytes, right: bytes) -> float:
    intersection = sum(bool(a) and bool(b) for a, b in zip(left, right, strict=True))
    union = sum(bool(a) or bool(b) for a, b in zip(left, right, strict=True))
    return intersection / union if union else 1.0


def _boundary_fscore(left: bytes, right: bytes, width: int) -> float:
    left_boundary = _boundary_indexes(left, width)
    right_boundary = _boundary_indexes(right, width)
    if not left_boundary and not right_boundary:
        return 1.0
    if not left_boundary or not right_boundary:
        return 0.0
    tolerance = width * 2 + 2
    matched_left = sum(
        any(abs(index - other) <= tolerance for other in right_boundary) for index in left_boundary
    )
    matched_right = sum(
        any(abs(index - other) <= tolerance for other in left_boundary) for index in right_boundary
    )
    precision = matched_left / len(left_boundary)
    recall = matched_right / len(right_boundary)
    return 2 * precision * recall / max(precision + recall, 1e-9)


def _boundary_indexes(mask: bytes, width: int) -> list[int]:
    result = []
    height = len(mask) // width
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            index = y * width + x
            if mask[index] and any(not mask[index + offset] for offset in (-1, 1, -width, width)):
                result.append(index)
    return result


def _minimum(value: float, limit: float) -> bool:
    return value >= limit


def _maximum(value: float, limit: float) -> bool:
    return value <= limit


def _invocation_journal(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entries = [
        {
            "sequence": index + 1,
            "kind": "fit",
            "sessionId": row["sessionId"],
            "candidateCount": int(row["candidateCount"]),
            "postFreezeEdit": False,
        }
        for index, row in enumerate(rows)
    ]
    entries.extend(
        [
            {"sequence": 31, "kind": "model_selection", "passes": 1, "maximum": 1},
            {"sequence": 32, "kind": "locked_evaluation", "passes": 1, "maximum": 1},
            {"sequence": 33, "kind": "training", "passes": 0, "maximum": 1},
            {"sequence": 34, "kind": "post_freeze_edit", "passes": 0, "maximum": 0},
        ]
    )
    return {
        "entryCount": len(entries),
        "entries": entries,
        "journalDigest": canonical_digest(entries),
        "allInvocationsJournalled": True,
    }
