from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .common import canonical_digest, sha256_bytes
from .render_types import runs_to_mask

CHECKER_VERSION = "closy.capture_reconstruction_v2_independent_checker.v2"
PARAMETER_FIELDS = ("bodyLength", "bodyWidth", "openingWidth", "sleeveLength", "hemWidth")


def check_locked_publication(
    protocol: Mapping[str, Any],
    manifest: Mapping[str, Any],
    commitments: Mapping[str, Any],
    output: Mapping[str, Any],
    envelope: Mapping[str, Any],
    disclosure: Mapping[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    result = envelope.get("result", {})
    receipt = envelope.get("receipt", {})
    if protocol.get("protocolDigest") != canonical_digest(protocol, "protocolDigest"):
        failures.append("checker_protocol_digest_invalid")
    if manifest.get("observableManifestDigest") != canonical_digest(
        manifest, "observableManifestDigest"
    ):
        failures.append("checker_observable_manifest_digest_invalid")
    if commitments.get("commitmentManifestDigest") != canonical_digest(
        commitments, "commitmentManifestDigest"
    ):
        failures.append("checker_commitment_manifest_digest_invalid")
    if output.get("contestantOutputDigest") != canonical_digest(output, "contestantOutputDigest"):
        failures.append("checker_contestant_output_digest_invalid")
    if result.get("resultDigest") != canonical_digest(result, "resultDigest"):
        failures.append("checker_result_digest_invalid")
    if receipt.get("receiptDigest") != canonical_digest(receipt, "receiptDigest"):
        failures.append("checker_receipt_digest_invalid")
    if envelope.get("publicationDigest") != canonical_digest(envelope, "publicationDigest"):
        failures.append("checker_publication_digest_invalid")
    if disclosure.get("disclosureDigest") != canonical_digest(disclosure, "disclosureDigest"):
        failures.append("checker_disclosure_digest_invalid")
    if disclosure.get("canonicalResultDigest") != result.get("resultDigest"):
        failures.append("checker_disclosure_result_lineage_invalid")
    protocol_digest = protocol.get("protocolDigest")
    if any(
        value != protocol_digest
        for value in (
            manifest.get("protocolDigest"),
            commitments.get("protocolDigest"),
            output.get("protocolDigest"),
            result.get("protocolDigest"),
            receipt.get("protocolDigest"),
            disclosure.get("protocolDigest"),
        )
    ):
        failures.append("checker_protocol_lineage_invalid")
    if output.get("observableManifestDigest") != manifest.get(
        "observableManifestDigest"
    ) or result.get("observableManifestDigest") != manifest.get("observableManifestDigest"):
        failures.append("checker_observable_manifest_lineage_invalid")
    if result.get("commitmentManifestDigest") != commitments.get(
        "commitmentManifestDigest"
    ) or receipt.get("truthCommitmentManifestDigest") != commitments.get(
        "commitmentManifestDigest"
    ):
        failures.append("checker_commitment_lineage_invalid")
    if result.get("contestantOutputDigest") != output.get("contestantOutputDigest") or receipt.get(
        "contestantOutputDigest"
    ) != output.get("contestantOutputDigest"):
        failures.append("checker_contestant_output_lineage_invalid")
    if receipt.get("resultDigest") != result.get("resultDigest"):
        failures.append("checker_receipt_result_lineage_invalid")
    if result.get("frozenSourceCommit") != manifest.get("frozenSourceCommit") or result.get(
        "frozenSourceTree"
    ) != manifest.get("frozenSourceTree"):
        failures.append("checker_frozen_source_lineage_invalid")
    expected_access_log = [
        {
            "sequence": index,
            "sessionId": row["sessionId"],
            "purpose": "single_locked_evaluation",
            "commitmentVerifiedBeforeScoring": True,
            "privateNameAndPathRedacted": True,
        }
        for index, row in enumerate(manifest.get("sessions", []), start=1)
    ]
    if (
        receipt.get("evaluatorAccessLogDigest") != canonical_digest(expected_access_log)
        or receipt.get("truthAccessCount") != 30
        or receipt.get("singleCanonicalEvaluation") is not True
    ):
        failures.append("checker_truth_access_receipt_invalid")
    truth_by_id = _verify_disclosure(commitments, disclosure, failures)
    output_by_id = {str(row["sessionId"]): row for row in output.get("rows", [])}
    expected_rows: list[dict[str, Any]] = []
    if set(output_by_id) != set(truth_by_id) or len(output_by_id) != 30:
        failures.append("checker_session_denominator_invalid")
    else:
        for session in manifest["sessions"]:
            session_id = str(session["sessionId"])
            expected_rows.append(
                _recompute_session(output_by_id[session_id], truth_by_id[session_id])
            )
    published_rows = {str(row["sessionId"]): row for row in result.get("rows", [])}
    for expected in expected_rows:
        published = published_rows.get(str(expected["sessionId"]))
        if published is None or published.get("metrics") != expected["metrics"]:
            failures.append("checker_session_metric_recompute_mismatch")
            break
        if published.get("terminalOutcome") != expected["terminalOutcome"]:
            failures.append("checker_session_terminal_recompute_mismatch")
            break
        if published.get("cameraNegativeControls") != expected["cameraNegativeControls"]:
            failures.append("checker_camera_control_recompute_mismatch")
            break
    expected_metrics = _aggregate(expected_rows)
    if result.get("metrics") != expected_metrics:
        failures.append("checker_aggregate_metric_recompute_mismatch")
    thresholds = _thresholds(protocol, expected_metrics)
    if result.get("thresholdResults") != thresholds:
        failures.append("checker_threshold_recompute_mismatch")
    cells = _cells(protocol, expected_rows)
    if result.get("modeFamilyResults") != cells:
        failures.append("checker_cell_recompute_mismatch")
    controls = [control for row in expected_rows for control in row["appearanceControls"]]
    if len(controls) != 150 or result.get("appearanceControls") != controls:
        failures.append("checker_appearance_control_denominator_mismatch")
    denominators = _denominators(manifest, expected_rows, controls)
    if result.get("denominators") != denominators:
        failures.append("checker_denominator_recompute_mismatch")
    terminal_counts = Counter(str(row["terminalOutcome"]) for row in expected_rows)
    terminal_conservation = {
        "attemptedSessions": 30,
        "terminalSessionCounts": dict(sorted(terminal_counts.items())),
        "terminalSessionCount": sum(terminal_counts.values()),
        "equation": f"{sum(terminal_counts.values())}=30",
        "conserved": sum(terminal_counts.values()) == 30,
        "droppedSessions": 30 - sum(terminal_counts.values()),
    }
    if result.get("terminalConservation") != terminal_conservation:
        failures.append("checker_terminal_conservation_mismatch")
    package_validity = sum(bool(row["package"]["intrinsicPackageValid"]) for row in expected_rows)
    expected_package_validity = {
        "valid": package_validity,
        "attempted": 30,
        "rate": round(package_validity / 30, 8),
    }
    if result.get("packageValidity") != expected_package_validity:
        failures.append("checker_package_validity_conservation_mismatch")
    expected_journal = _invocation_journal(expected_rows)
    if result.get("invocationJournal") != expected_journal:
        failures.append("checker_invocation_journal_mismatch")
    first_unmet = next(
        (str(row["id"]) for row in thresholds if row["terminalOutcome"] != "passed"),
        next((str(row["cell"]) for row in cells if row["terminalOutcome"] != "passed"), None),
    )
    if result.get("firstUnmetPredicate") != first_unmet:
        failures.append("checker_first_unmet_predicate_mismatch")
    expected_outcome = (
        "source_guarded_synthetic_capture_reconstruction_v2_passed"
        if first_unmet is None
        else "source_guarded_synthetic_capture_reconstruction_v2_failed"
    )
    if result.get("terminalOutcome") != expected_outcome:
        failures.append("checker_terminal_classification_mismatch")
    report: dict[str, Any] = {
        "schemaVersion": 2,
        "checkerVersion": CHECKER_VERSION,
        "terminalOutcome": "passed" if not failures else "integrity_error",
        "failureReasons": sorted(set(failures)),
        "sessionCount": len(expected_rows),
        "controlCount": len(controls),
        "recomputedMetricCount": len(expected_metrics),
        "recomputedThresholdCount": len(thresholds),
        "recomputedCellCount": len(cells),
        "contestantRerun": False,
        "syntheticTruthCommitmentsVerified": not any("commitment" in row for row in failures),
    }
    report["checkerDigest"] = canonical_digest(report)
    return report


def check_publication_paths(
    protocol_path: Path,
    manifest_path: Path,
    commitments_path: Path,
    output_path: Path,
    envelope_path: Path,
    disclosure_path: Path,
) -> dict[str, Any]:
    paths = (
        protocol_path,
        manifest_path,
        commitments_path,
        output_path,
        envelope_path,
        disclosure_path,
    )
    values = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    return check_locked_publication(*values)


def _verify_disclosure(
    commitments: Mapping[str, Any],
    disclosure: Mapping[str, Any],
    failures: list[str],
) -> dict[str, dict[str, Any]]:
    commitment_by_id = {str(row["sessionId"]): row for row in commitments.get("rows", [])}
    truth_by_id: dict[str, dict[str, Any]] = {}
    for truth in disclosure.get("truthRows", []):
        session_id = str(truth.get("sessionId", ""))
        commitment = commitment_by_id.get(session_id)
        if commitment is None:
            failures.append("checker_truth_commitment_row_missing")
            continue
        payload = (
            json.dumps(truth, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        ).encode()
        if sha256_bytes(payload) != commitment.get("truthCommitment"):
            failures.append("checker_truth_commitment_mismatch")
        seed = str(truth.get("seed", ""))
        try:
            seed_commitment = sha256_bytes(bytes.fromhex(seed))
        except ValueError:
            seed_commitment = "invalid"
        if seed_commitment != commitment.get("seedCommitment"):
            failures.append("checker_seed_commitment_mismatch")
        if truth.get("truthDigest") != canonical_digest(truth, "truthDigest"):
            failures.append("checker_truth_digest_invalid")
        truth_by_id[session_id] = dict(truth)
    if len(truth_by_id) != 30 or len(commitment_by_id) != 30:
        failures.append("checker_truth_disclosure_denominator_invalid")
    return truth_by_id


def _recompute_session(output: Mapping[str, Any], truth: Mapping[str, Any]) -> dict[str, Any]:
    observations = output["observations"]
    targets = truth["observations"]
    segmentation = [
        _segmentation(left, right) for left, right in zip(observations, targets, strict=True)
    ]
    cameras = [
        _camera(estimate, observed, target)
        for estimate, observed, target in zip(
            output["cameraEstimates"], observations, targets, strict=True
        )
    ]
    bodies = [
        _body(estimate, target)
        for estimate, target in zip(output["bodyPoseEstimates"], targets, strict=True)
        if estimate.get("status") == "estimated"
    ]
    target_parameters = targets[0]["targetParameters"]
    appearance = output["appearance"]
    appearance_metrics = _appearance_score(
        bytes.fromhex(appearance["rgbaHex"]),
        bytes.fromhex(appearance["observedHex"]),
        str(truth["family"]),
        target_parameters,
    )
    controls = _recompute_controls(appearance["controls"])
    metrics: dict[str, float] = {
        "qc.decode_rate": 1.0,
        "qc.accepted_rate": output["qc"]["accepted"] / max(1, output["qc"]["attempted"]),
        "segmentation.garment_iou": _mean(segmentation, "garmentIou"),
        "segmentation.boundary_fscore": _mean(segmentation, "boundaryFscore"),
        "segmentation.part_accuracy": _mean(segmentation, "partAccuracy"),
        "landmarks.normalized_error": _mean(segmentation, "landmarkNormalizedError"),
        "camera.rotation_degrees": _mean(cameras, "rotationDegrees"),
        "camera.focal_relative_error": _mean(cameras, "focalRelativeError"),
        "camera.principal_point_error": _mean(cameras, "principalPointError"),
        "camera.scale_relative_error": _mean(cameras, "scaleRelativeError"),
        "camera.reprojection_pixels": _mean(cameras, "reprojectionPixels"),
        "body.pose_normalized_error": _mean(bodies, "poseNormalizedError") if bodies else 0.0,
        "fit.silhouette_error": _parameter_error(
            output["fit"].get("selectedParameters", {}), target_parameters
        ),
        "fit.seam_relative_error": _solver(output, "residual", 0.02),
        "fit.body_clearance_error": 0.0
        if output["fit"].get("terminalOutcome") == "fitted"
        else 1.0,
        "fit.temporal_drift": _drift(cameras),
        "package.overall_validity": 1.0 if output["package"]["intrinsicPackageValid"] else 0.0,
        "package.family_validity": 1.0 if output["package"]["intrinsicPackageValid"] else 0.0,
        "appearance.delta_e_proxy": appearance_metrics["deltaEProxy"],
        "appearance.ssim_proxy": appearance_metrics["ssimProxy"],
        "appearance.visible_texel_coverage": appearance["report"]["visibleTexelCoverage"],
        "video.distinct_frame_rate": (
            len({row["quality"]["pixelDigest"] for row in observations}) / len(observations)
            if truth["mode"] == "D"
            else 1.0
        ),
        "video.temporal_consistency": max(0.0, 1.0 - _drift(cameras)),
        "mode_e.hypothesis_coverage": (
            _hypotheses(output["fit"], target_parameters) if truth["mode"] == "E" else 1.0
        ),
        "controls.pass_rate": sum(row["terminalOutcome"] == "passed" for row in controls)
        / max(1, len(controls)),
        "privacy.integrity_pass": 1.0,
    }
    terminal = (
        "qc_rejected"
        if output["qc"]["accepted"] == 0
        else str(output["fit"]["terminalOutcome"])
        if output["fit"].get("terminalOutcome")
        in {"timeout", "crash", "abstained", "physically_invalid"}
        else "invalid_package"
        if not output["package"]["intrinsicPackageValid"]
        else "passed"
    )
    return {
        "sessionId": truth["sessionId"],
        "mode": truth["mode"],
        "family": truth["family"],
        "stratum": truth["stratum"],
        "terminalOutcome": terminal,
        "metrics": metrics,
        "appearanceControls": controls,
        "cameraNegativeControls": output["cameraNegativeControls"],
        "qc": output["qc"],
        "package": output["package"],
        "candidateCount": output["fit"].get("candidateCount", 0),
    }


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    values: defaultdict[str, list[float]] = defaultdict(list)
    for row in rows:
        for name, value in row["metrics"].items():
            values[str(name)].append(float(value))
    result = {name: round(statistics.mean(items), 8) for name, items in sorted(values.items())}
    result["package.family_validity"] = round(
        min(
            statistics.mean(
                float(row["metrics"]["package.family_validity"])
                for row in rows
                if row["family"] == family
            )
            for family in ("tshirt", "sleeveless_top", "simple_skirt")
        ),
        8,
    )
    return result


def _denominators(
    manifest: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    controls: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    sessions = manifest["sessions"]
    source_attempted = sum(int(row["expectedSourceCount"]) for row in sessions)
    observations = sum(int(row["qc"]["attempted"]) for row in rows)
    accepted = sum(int(row["qc"]["accepted"]) for row in rows)
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
        "rejectedObservationsOrFrames": observations - accepted,
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


def _recompute_controls(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    expected_names = {
        "localized_source_pixel_intervention",
        "evaluator_hidden_target_mutation",
        "estimated_camera_perturbation",
        "visibility_occlusion_perturbation",
        "association_mismatch",
    }
    if len(rows) != 5 or {str(row.get("control")) for row in rows} != expected_names:
        return []
    recomputed = []
    for source in rows:
        row = dict(source)
        name = str(row["control"])
        measured = row.get("measured")
        passed = False
        if isinstance(measured, Mapping):
            if name == "localized_source_pixel_intervention":
                changed = int(measured.get("changedTexels", -1))
                total = int(measured.get("totalTexels", 0))
                maximum = float(measured.get("maximumChangedFraction", -1.0))
                passed = total > 0 and changed > 0 and changed < total * maximum
            elif name == "visibility_occlusion_perturbation":
                passed = int(measured.get("interventionObservedSum", -1)) < int(
                    measured.get("baselineObservedSum", -1)
                )
            elif name == "evaluator_hidden_target_mutation":
                passed = measured.get("outputsBitIdentical") is True
            else:
                passed = measured.get("outputsBitIdentical") is False
        row["terminalOutcome"] = "passed" if passed else "failed"
        recomputed.append(row)
    return recomputed


def _thresholds(protocol: Mapping[str, Any], metrics: Mapping[str, float]) -> list[dict[str, Any]]:
    rows = []
    for threshold in protocol["thresholdRegistry"]:
        value = float(metrics[str(threshold["metric"])])
        limit = float(threshold["limit"])
        passed = value >= limit if threshold["direction"] == "minimum" else value <= limit
        rows.append(
            {
                "id": threshold["id"],
                "metric": threshold["metric"],
                "direction": threshold["direction"],
                "limit": limit,
                "observed": value,
                "evaluatorFunction": threshold["evaluatorFunction"],
                "terminalOutcome": "passed" if passed else "failed",
            }
        )
    return rows


def _cells(protocol: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    registry = {str(row["metric"]): row for row in protocol["thresholdRegistry"]}
    hard = (
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
            values = {
                metric: round(statistics.mean(float(row["metrics"][metric]) for row in selected), 8)
                for metric in hard
            }
            failures = [
                metric
                for metric, value in values.items()
                if not (
                    value >= float(registry[metric]["limit"])
                    if registry[metric]["direction"] == "minimum"
                    else value <= float(registry[metric]["limit"])
                )
            ]
            results.append(
                {
                    "cell": f"{mode}:{family}",
                    "sessionCount": 2,
                    "strata": ["cross_generator", "in_model"],
                    "hardMetrics": values,
                    "terminalOutcome": "passed" if not failures else "failed",
                    "firstUnmetPredicate": failures[0] if failures else None,
                }
            )
    return results


def _segmentation(observed: Mapping[str, Any], truth: Mapping[str, Any]) -> dict[str, float]:
    length = int(observed["width"]) * int(observed["height"])
    predicted = {key: runs_to_mask(value, length) for key, value in observed["maskRuns"].items()}
    target = {key: runs_to_mask(value, length) for key, value in truth["maskRuns"].items()}
    hair_hands = bytes(max(a, b) for a, b in zip(target["hair"], target["hands"], strict=True))
    parts = (
        _iou(predicted["body"], target["body"]),
        _iou(predicted["hair_hands"], hair_hands),
        _iou(predicted["occluder"], target["occluder"]),
        _iou(predicted["scale_target"], target["scale_target"]),
    )
    landmarks = [
        (
            math.dist(observed["landmarks"][name], point) / math.sqrt(2.0)
            if name in observed["landmarks"]
            else 1.0
        )
        for name, point in truth["landmarks"].items()
    ]
    return {
        "garmentIou": round(_iou(predicted["garment"], target["garment"]), 8),
        "boundaryFscore": round(
            _boundary_score(predicted["garment"], target["garment"], int(observed["width"])), 8
        ),
        "partAccuracy": round(statistics.mean(parts), 8),
        "landmarkNormalizedError": round(statistics.mean(landmarks), 8),
    }


def _camera(
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
    return {
        "rotationDegrees": round(
            math.hypot(
                float(estimate["yawDegrees"]) - float(target["yawDegrees"]),
                float(estimate["pitchDegrees"]) - float(target["pitchDegrees"]),
            ),
            8,
        ),
        "focalRelativeError": round(
            abs(float(estimate["focalPixels"]) - float(target["focalPixels"]))
            / max(abs(float(target["focalPixels"])), 1e-6),
            8,
        ),
        "principalPointError": round(
            math.hypot(
                float(estimate["principalX"]) - float(target["principalX"]),
                float(estimate["principalY"]) - float(target["principalY"]),
            )
            / math.hypot(float(truth["width"]), float(truth["height"])),
            8,
        ),
        "scaleRelativeError": round(
            abs(float(estimate["scaleMetersPerPixel"]) - float(target["scaleMetersPerPixel"]))
            / max(abs(float(target["scaleMetersPerPixel"])), 1e-9),
            8,
        ),
        "reprojectionPixels": round(
            statistics.mean(
                math.dist(observed["landmarks"].get(name, [0.5, 0.5]), point)
                * math.hypot(truth["width"], truth["height"])
                for name, point in truth["landmarks"].items()
            ),
            8,
        ),
    }


def _body(estimate: Mapping[str, Any], truth: Mapping[str, Any]) -> dict[str, float]:
    fields = ("leftArmDegrees", "rightArmDegrees", "leftLegDegrees", "rightLegDegrees")
    return {
        "poseNormalizedError": round(
            statistics.mean(
                abs(float(estimate[field]) - float(truth["bodyPose"][field])) / 180.0
                for field in fields
            ),
            8,
        )
    }


def _appearance_score(
    rgba: bytes, observed: bytes, family: str, parameters: Mapping[str, Any]
) -> dict[str, float]:
    # Reimplement the frozen analytic novel-view raster locally. The checker deliberately
    # does not import the evaluator renderer, but it must reproduce its exact public math.
    indexes = [index for index, value in enumerate(observed) if value]
    reference_rgba, reference_mask = _independent_reference_raster(family, parameters)
    reference_indexes = [index for index, value in enumerate(reference_mask) if value]
    if not indexes or not reference_indexes:
        return {"deltaEProxy": 1.0, "ssimProxy": 0.0}
    atlas_mean = _mean_rgb(rgba, indexes)
    reference_mean = _mean_rgb(reference_rgba, reference_indexes)
    delta = math.sqrt(
        sum((left - right) ** 2 for left, right in zip(atlas_mean, reference_mean, strict=True))
    ) / math.sqrt(3 * 255**2)
    contrast = _contrast(rgba, indexes, atlas_mean)
    reference_contrast = _contrast(reference_rgba, reference_indexes, reference_mean)
    structure = 1.0 - min(1.0, abs(contrast - reference_contrast) / 90.0)
    return {
        "deltaEProxy": round(min(1.0, delta), 8),
        "ssimProxy": round(max(0.0, structure * (1.0 - delta * 0.5)), 8),
    }


def _independent_reference_raster(
    family: str,
    parameters: Mapping[str, Any],
    *,
    width: int = 96,
    height: int = 128,
) -> tuple[bytes, bytes]:
    body_length = float(parameters.get("bodyLength", 0.56))
    body_width = float(parameters.get("bodyWidth", 0.50))
    opening = float(parameters.get("openingWidth", 0.16))
    color = {
        "tshirt": (54, 126, 196),
        "sleeveless_top": (215, 86, 108),
        "simple_skirt": (124, 91, 179),
    }[family]
    pixels = bytearray(width * height * 4)
    foreground = bytearray(width * height)
    center_x = width * 0.5
    top = height * 0.22
    pixel_height = max(24.0, min(height * 0.62, body_length / 0.82 * height * 0.62))
    half_top = max(9.0, min(width * 0.34, body_width / 0.78 * width * 0.32))
    half_bottom = half_top * (1.12 if family == "simple_skirt" else 0.86)
    for y in range(height):
        t = (y - top) / pixel_height
        if not 0.0 <= t <= 1.0:
            continue
        half = half_top * (1.0 - t) + half_bottom * t
        for x in range(width):
            local = abs(x - center_x)
            neck_cutout = t < 0.12 and local < opening / 0.28 * width * 0.055
            if local <= half and not neck_cutout:
                index = y * width + x
                shade = 0.84 + 0.16 * max(0.0, math.cos((x - center_x) / half * 1.2))
                rgb = tuple(max(0, min(255, round(channel * shade))) for channel in color)
                pixels[index * 4 : index * 4 + 4] = bytes((*rgb, 255))
                foreground[index] = 255
    return bytes(pixels), bytes(foreground)


def _mean_rgb(rgba: bytes, indexes: list[int]) -> tuple[float, float, float]:
    return tuple(
        sum(rgba[index * 4 + channel] for index in indexes) / len(indexes) for channel in range(3)
    )  # type: ignore[return-value]


def _contrast(rgba: bytes, indexes: list[int], mean: tuple[float, float, float]) -> float:
    return math.sqrt(
        sum(
            sum((rgba[index * 4 + channel] - mean[channel]) ** 2 for channel in range(3)) / 3
            for index in indexes
        )
        / len(indexes)
    )


def _parameter_error(estimate: Mapping[str, Any], target: Mapping[str, Any]) -> float:
    if not all(field in estimate for field in PARAMETER_FIELDS):
        return 1.0
    spans = {
        "bodyLength": 0.46,
        "bodyWidth": 0.48,
        "openingWidth": 0.18,
        "sleeveLength": 0.38,
        "hemWidth": 0.46,
    }
    return round(
        statistics.mean(
            abs(float(estimate[field]) - float(target[field])) / spans[field]
            for field in PARAMETER_FIELDS
        ),
        8,
    )


def _solver(output: Mapping[str, Any], field: str, scale: float) -> float:
    value = output["fit"].get("solver", {}).get(field)
    return round(abs(float(value)) / scale, 8) if value is not None else 1.0


def _hypotheses(fit: Mapping[str, Any], target: Mapping[str, Any]) -> float:
    rows = fit.get("alternativeHypotheses", [])
    return (
        1.0
        if rows and min(_parameter_error(row["parameters"], target) for row in rows) <= 0.25
        else 0.0
    )


def _drift(rows: Sequence[Mapping[str, Any]]) -> float:
    values = [float(row["rotationDegrees"]) for row in rows]
    return round(statistics.pstdev(values) / 90.0, 8) if len(values) > 1 else 0.0


def _mean(rows: Sequence[Mapping[str, Any]], field: str) -> float:
    return round(statistics.mean(float(row[field]) for row in rows), 8) if rows else 1.0


def _iou(left: bytes, right: bytes) -> float:
    intersection = sum(bool(a) and bool(b) for a, b in zip(left, right, strict=True))
    union = sum(bool(a) or bool(b) for a, b in zip(left, right, strict=True))
    return intersection / union if union else 1.0


def _boundary_score(left: bytes, right: bytes, width: int) -> float:
    left_indexes = _boundary(left, width)
    right_indexes = _boundary(right, width)
    if not left_indexes and not right_indexes:
        return 1.0
    if not left_indexes or not right_indexes:
        return 0.0
    tolerance = width * 2 + 2
    precision = sum(
        any(abs(index - other) <= tolerance for other in right_indexes) for index in left_indexes
    ) / len(left_indexes)
    recall = sum(
        any(abs(index - other) <= tolerance for other in left_indexes) for index in right_indexes
    ) / len(right_indexes)
    return 2 * precision * recall / max(precision + recall, 1e-9)


def _boundary(mask: bytes, width: int) -> list[int]:
    height = len(mask) // width
    return [
        index
        for y in range(1, height - 1)
        for x in range(1, width - 1)
        for index in [y * width + x]
        if mask[index] and any(not mask[index + offset] for offset in (-1, 1, -width, width))
    ]
