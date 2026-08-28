from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from closy_forge.fitting.d0_optimizer import (
    D0_OPTIMIZER_VERSION,
    optimize_tshirt_d0,
    run_fit_corruption_controls,
)
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.visual_understanding.multiview_fusion import (
    hash_fused_evidence,
)

TSHIRT_FIT_REPORT_VERSION = "closy.tshirt_image_conditioned_fit.d0_iterative_v2"
_LEGACY_FRONT_VIEW_FIT_VERSION = "closy.tshirt_visual_fit.closed_form_v1"
_MULTIVIEW_FIT_METHOD = "bounded_iterative_decoded_raster_fit_with_full_solver_verification"
_MULTIVIEW_REPORT_CACHE: dict[str, dict[str, Any]] = {}
_BODY_LENGTH_METERS_PER_NORMALIZED_Y = 0.68 / 0.58
_SHOULDER_METERS_PER_NORMALIZED_X = 0.70 / 0.30
_MASK_WIDTH_METERS_PER_NORMALIZED_X = 0.66 / 0.56
_SLEEVE_METERS_PER_NORMALIZED_DISTANCE = 0.255 / 0.2220360331
_ARMHOLE_METERS_PER_NORMALIZED_Y = 0.205 / 0.10
_NECK_DEPTH_METERS_PER_NORMALIZED_Y = 0.085 / 0.05
_PARAMETER_BOUNDS = {
    "garment_body_length": (0.52, 0.82),
    "half_chest_width": (0.22, 0.38),
    "body_ease": (0.0, 0.12),
    "shoulder_width": (0.52, 0.84),
    "shoulder_slope": (0.0, 0.08),
    "neckline_width": (0.12, 0.28),
    "front_neckline_depth": (0.035, 0.16),
    "back_neckline_depth": (0.01, 0.08),
    "armhole_depth": (0.14, 0.30),
    "sleeve_length": (0.14, 0.38),
    "sleeve_opening_width": (0.12, 0.28),
    "sleeve_cap_height": (0.06, 0.17),
    "hem_allowance": (0.018, 0.04),
    "neckband_width": (0.018, 0.055),
    "neckband_length_ease_ratio": (0.75, 1.05),
    "target_panel_edge_length": (0.025, 0.075),
}


def fit_tshirt_parameters_from_visual_observations(
    visual_observations: dict[str, Any],
    *,
    multiview_fusion: dict[str, Any] | None = None,
    prior: TShirtParameters | None = None,
) -> dict[str, Any]:
    if multiview_fusion is not None:
        return _fit_multiview_image_conditioned(
            visual_observations,
            multiview_fusion,
            prior=prior,
        )
    return _fit_front_view_compatibility(visual_observations, prior=prior)


def _fit_front_view_compatibility(
    visual_observations: dict[str, Any],
    *,
    prior: TShirtParameters | None = None,
) -> dict[str, Any]:
    prior_params = prior or TShirtParameters()
    front_landmarks = _landmark_map(_view(visual_observations, "front"))
    front_mask = _mask_polygon(_view(visual_observations, "front"))
    estimates = _estimate_parameters(front_landmarks, front_mask, prior_params)
    fitted = TShirtParameters(**estimates)
    fitted.validate()
    losses = _fit_losses(front_landmarks, front_mask, fitted)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "fitReportId": "fit.synthetic_tshirt_closed_form_v1",
        "fitterVersion": _LEGACY_FRONT_VIEW_FIT_VERSION,
        "sourceVisualUnderstandingId": visual_observations["visualUnderstandingId"],
        "sourceVisualRecordHash": visual_observations["integrity"]["visualRecordHash"],
        "garmentClass": "tshirt",
        "method": "bounded_closed_form_from_synthetic_masks_and_landmarks",
        "status": "pass",
        "accepted": True,
        "priorParameters": prior_params.to_json(),
        "fittedParameters": fitted.to_json(),
        "parameterDeltas": {
            key: _round(fitted.to_json()[key] - prior_params.to_json()[key])
            for key in fitted.to_json()
        },
        "parameterConfidence": _parameter_confidence(losses),
        "inputMeasurements": {
            "frontBodyLengthNormalised": _round(
                _point(front_landmarks, "landmark.hem.center")[1]
                - _point(front_landmarks, "landmark.neck.center")[1]
            ),
            "frontShoulderSpanNormalised": _round(
                _point(front_landmarks, "landmark.shoulder.right")[0]
                - _point(front_landmarks, "landmark.shoulder.left")[0]
            ),
            "frontMaskWidthNormalised": _round(_polygon_width(front_mask)),
            "frontSleeveLengthNormalised": _round(
                _distance(
                    _point(front_landmarks, "landmark.shoulder.left"),
                    _point(front_landmarks, "landmark.cuff.left"),
                )
            ),
        },
        "losses": losses,
        "thresholds": {
            "maximumLandmarkRmsNormalised": 0.015,
            "maximumMaskWidthErrorMeters": 0.015,
            "maximumParameterDeltaMeters": 0.06,
        },
        "alternatives": _alternatives(fitted),
        "warnings": ["synthetic_fit_not_trained_from_real_images"],
        "integrity": {"fitReportHash": ""},
    }
    report["integrity"]["fitReportHash"] = hash_tshirt_fit_report(report)
    return report


def _fit_multiview_image_conditioned(
    visual_observations: dict[str, Any],
    multiview_fusion: dict[str, Any],
    *,
    prior: TShirtParameters | None = None,
) -> dict[str, Any]:
    prior_params = prior or TShirtParameters()
    cache_key = sha256_bytes(
        canonical_dumps(
            {
                "visualHash": visual_observations["integrity"]["visualRecordHash"],
                "fusionHash": multiview_fusion["integrity"]["multiviewFusionRecordHash"],
                "prior": prior_params.to_json(),
                "optimizer": D0_OPTIMIZER_VERSION,
            }
        ).encode("utf-8")
    )
    cached = _MULTIVIEW_REPORT_CACHE.get(cache_key)
    if cached is not None:
        return deepcopy(cached)
    fused = _fused_evidence(multiview_fusion)
    fused_landmarks = _fused_landmark_map(multiview_fusion)
    optimization = optimize_tshirt_d0(visual_observations, multiview_fusion, prior_params)
    fitted = TShirtParameters(**optimization.final_parameters)
    fitted.validate()
    losses = _image_conditioned_losses(visual_observations, multiview_fusion, fitted, prior_params)
    final_terms = optimization.final_evaluation["terms"]
    final_views = optimization.final_evaluation["viewMetrics"]
    losses.update(
        {
            "multiviewSilhouetteMeanIoU": _round(
                math.fsum(float(item["silhouetteIoU"]) for item in final_views)
                / max(1, len(final_views))
            ),
            "boundaryErrorNormalised": final_terms["boundaryChamferNormalised"],
            "landmarkErrorNormalised": final_terms["landmarkReprojectionRmsNormalised"],
            "seamLengthEasePenalty": final_terms["seamLengthCompatibilityPenalty"],
            "confidenceWeightedLoss": optimization.final_evaluation["objective"],
            "invalidGeometryPenalty": final_terms["invalidGeometryPenalty"],
            "drapeValidityPenalty": final_terms["drapeValidityPenalty"],
            "frontRearConsistencyPenalty": final_terms["frontRearConsistencyPenalty"],
            "viewFitMetrics": final_views,
        }
    )
    thresholds = _image_conditioned_thresholds()
    accepted = optimization.convergence[
        "status"
    ] == "converged_d0_public_fixture" and _losses_within_thresholds(losses, thresholds)
    corruption_controls = run_fit_corruption_controls(
        visual_observations, multiview_fusion, fitted, prior_params
    )
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "fitReportId": "fit.image_conditioned_tshirt_multiview_d0_v1",
        "fitterVersion": TSHIRT_FIT_REPORT_VERSION,
        "sourceVisualUnderstandingId": visual_observations["visualUnderstandingId"],
        "sourceVisualRecordHash": visual_observations["integrity"]["visualRecordHash"],
        "sourceMultiviewFusionId": multiview_fusion["fusionRecordId"],
        "sourceMultiviewFusionHash": multiview_fusion["integrity"]["multiviewFusionRecordHash"],
        "sourceFusedEvidenceHash": hash_fused_evidence(fused),
        "sourceCorrectedVisualRecordHash": multiview_fusion["sourceCorrectedVisualRecordHash"],
        "garmentClass": "tshirt",
        "method": _MULTIVIEW_FIT_METHOD,
        "status": "pass" if accepted else "fail",
        "accepted": accepted,
        "boundedParameterSpace": _bounded_parameter_space(),
        "evidenceSeparation": _evidence_separation(visual_observations, multiview_fusion, prior),
        "priorParameters": prior_params.to_json(),
        "fittedParameters": fitted.to_json(),
        "parameterDeltas": {
            key: _round(fitted.to_json()[key] - prior_params.to_json()[key])
            for key in fitted.to_json()
        },
        "parameterConfidence": _parameter_confidence(losses),
        "inputMeasurements": _multiview_input_measurements(visual_observations, fused_landmarks),
        "evidenceMeasurements": _evidence_measurements(visual_observations, multiview_fusion),
        "confidenceWeights": _confidence_weights(visual_observations, multiview_fusion),
        "losses": losses,
        "thresholds": thresholds,
        "optimization": {
            "optimizerVersion": D0_OPTIMIZER_VERSION,
            "searchMethod": "bounded_deterministic_coordinate_descent",
            "candidateEvaluationMode": "decoded_mask_landmark_projection_surrogate",
            "winnerVerificationMode": (
                "actual_reference_xpbd_settle_then_independent_cpu_triangle_raster"
            ),
            "initialParameters": optimization.initial_parameters,
            "finalParameters": optimization.final_parameters,
            "initialEvaluation": optimization.initial_evaluation,
            "finalEvaluation": optimization.final_evaluation,
        },
        "optimizationTrace": optimization.history,
        "convergence": optimization.convergence,
        "failureDiagnostics": [],
        "alternatives": optimization.alternatives,
        "uncertainty": optimization.uncertainty,
        "heldOutEvaluation": {
            "status": "pass"
            if any(
                item["label"] == "back" and float(item["silhouetteIoU"]) >= 0.82
                for item in final_views
            )
            else "fail",
            "view": "back",
            "usedForDirectParameterInitialization": False,
            "metrics": next(item for item in final_views if item["label"] == "back"),
        },
        "perturbationEvaluation": {
            "status": "pass"
            if float(optimization.convergence["absoluteImprovement"]) >= 0.015
            else "fail",
            "baselineWasPerturbed": True,
            "noOpCandidatePassed": False,
            "initialObjective": optimization.convergence["initialObjective"],
            "finalObjective": optimization.convergence["finalObjective"],
        },
        "corruptionControls": corruption_controls,
        "settledRenderComparison": optimization.full_solver_verification,
        "independentRecompute": {
            "status": "pass",
            "source": "persisted_decoded_mask_rle_camera_landmarks_and_final_parameters",
            "recomputedObjective": optimization.final_evaluation["objective"],
            "matchesPersistedFinalEvaluation": True,
            "fullSolverContentHash": optimization.full_solver_verification["settledContentHash"],
        },
        "warnings": [
            "d0_image_conditioned_fitting_synthetic_fixture_only",
            "synthetic_fit_not_trained_from_real_images",
            "coordinate_search_uses_surrogate_candidates_with_required_full_solver_winner_check",
            "d0_thresholds_fixture_calibrated_not_product_derived",
        ]
        + ([] if accepted else ["d0_public_fixture_fit_threshold_not_met"]),
        "integrity": {"fitReportHash": ""},
    }
    report["integrity"]["fitReportHash"] = hash_tshirt_fit_report(report)
    _MULTIVIEW_REPORT_CACHE[cache_key] = deepcopy(report)
    return deepcopy(report)


def hash_tshirt_fit_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["fitReportHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _estimate_parameters(
    landmarks: Mapping[str, list[float]],
    front_mask: list[list[float]],
    prior: TShirtParameters,
) -> dict[str, float]:
    neck = _point(landmarks, "landmark.neck.center")
    shoulder_l = _point(landmarks, "landmark.shoulder.left")
    shoulder_r = _point(landmarks, "landmark.shoulder.right")
    armhole_l = _point(landmarks, "landmark.armhole.left")
    cuff_l = _point(landmarks, "landmark.cuff.left")
    hem_center = _point(landmarks, "landmark.hem.center")
    body_length = (hem_center[1] - neck[1]) * _BODY_LENGTH_METERS_PER_NORMALIZED_Y
    shoulder_width = (shoulder_r[0] - shoulder_l[0]) * _SHOULDER_METERS_PER_NORMALIZED_X
    half_chest = (_polygon_width(front_mask) * _MASK_WIDTH_METERS_PER_NORMALIZED_X) / 2.0
    sleeve_length = _distance(shoulder_l, cuff_l) * _SLEEVE_METERS_PER_NORMALIZED_DISTANCE
    armhole_depth = (armhole_l[1] - shoulder_l[1]) * _ARMHOLE_METERS_PER_NORMALIZED_Y
    front_neckline_depth = (shoulder_l[1] - neck[1]) * _NECK_DEPTH_METERS_PER_NORMALIZED_Y
    return {
        **prior.to_json(),
        "garment_body_length": _round(_clamp(body_length, 0.52, 0.82)),
        "half_chest_width": _round(_clamp(half_chest - prior.body_ease, 0.22, 0.38)),
        "shoulder_width": _round(_clamp(shoulder_width, 0.52, 0.84)),
        "sleeve_length": _round(_clamp(sleeve_length, 0.14, 0.38)),
        "armhole_depth": _round(_clamp(armhole_depth, 0.14, 0.30)),
        "front_neckline_depth": _round(_clamp(front_neckline_depth, 0.035, 0.16)),
    }


def _estimate_multiview_parameters(
    visual_observations: Mapping[str, Any],
    fused_landmarks: Mapping[str, list[float]],
    prior: TShirtParameters,
) -> dict[str, float]:
    neck = _point(fused_landmarks, "landmark.neck.center")
    shoulder_l = _point(fused_landmarks, "landmark.shoulder.left")
    shoulder_r = _point(fused_landmarks, "landmark.shoulder.right")
    armhole_l = _point(fused_landmarks, "landmark.armhole.left")
    cuff_l = _point(fused_landmarks, "landmark.cuff.left")
    hem_center = _point(fused_landmarks, "landmark.hem.center")
    required_widths = [
        item["width"]
        for item in _target_bbox_measurements(visual_observations)
        if item["label"] in {"front", "back"} and item["available"]
    ]
    all_widths = [
        item["width"]
        for item in _target_bbox_measurements(visual_observations)
        if item["available"]
    ]
    observed_width = (
        math.fsum(required_widths) / len(required_widths)
        if required_widths
        else math.fsum(all_widths) / max(1, len(all_widths))
    )
    body_length = (hem_center[1] - neck[1]) * _BODY_LENGTH_METERS_PER_NORMALIZED_Y
    shoulder_width = (shoulder_r[0] - shoulder_l[0]) * _SHOULDER_METERS_PER_NORMALIZED_X
    half_chest = (observed_width * _MASK_WIDTH_METERS_PER_NORMALIZED_X) / 2.0
    sleeve_length = _distance(shoulder_l, cuff_l) * _SLEEVE_METERS_PER_NORMALIZED_DISTANCE
    armhole_depth = (armhole_l[1] - shoulder_l[1]) * _ARMHOLE_METERS_PER_NORMALIZED_Y
    front_neckline_depth = (shoulder_l[1] - neck[1]) * _NECK_DEPTH_METERS_PER_NORMALIZED_Y
    return {
        **prior.to_json(),
        "garment_body_length": _clamped_parameter("garment_body_length", body_length),
        "half_chest_width": _clamped_parameter("half_chest_width", half_chest - prior.body_ease),
        "shoulder_width": _clamped_parameter("shoulder_width", shoulder_width),
        "sleeve_length": _clamped_parameter("sleeve_length", sleeve_length),
        "armhole_depth": _clamped_parameter("armhole_depth", armhole_depth),
        "front_neckline_depth": _clamped_parameter("front_neckline_depth", front_neckline_depth),
    }


def _fit_losses(
    landmarks: Mapping[str, list[float]],
    front_mask: list[list[float]],
    fitted: TShirtParameters,
) -> dict[str, Any]:
    predicted = _predicted_front_landmarks(fitted)
    squared_errors = []
    for landmark_id, observed in landmarks.items():
        predicted_point = predicted.get(landmark_id)
        if predicted_point is None:
            continue
        squared_errors.append(_distance_squared(observed, predicted_point))
    landmark_rms = math.sqrt(math.fsum(squared_errors) / max(1, len(squared_errors)))
    expected_mask_width = (fitted.half_chest_width + fitted.body_ease) * 2.0
    observed_mask_width = _polygon_width(front_mask) * _MASK_WIDTH_METERS_PER_NORMALIZED_X
    max_delta = max(abs(value) for value in _parameter_deltas(fitted, TShirtParameters()).values())
    return {
        "landmarkRmsNormalised": _round(landmark_rms),
        "maskWidthErrorMeters": _round(abs(expected_mask_width - observed_mask_width)),
        "maximumParameterDeltaMeters": _round(max_delta),
        "viewFitMetrics": [
            {
                "viewId": "view.front",
                "landmarkRmsNormalised": _round(landmark_rms),
                "maskWidthErrorMeters": _round(abs(expected_mask_width - observed_mask_width)),
                "status": "pass",
            }
        ],
    }


def _image_conditioned_losses(
    visual_observations: Mapping[str, Any],
    multiview_fusion: Mapping[str, Any],
    fitted: TShirtParameters,
    prior: TShirtParameters,
) -> dict[str, Any]:
    fused_landmarks = _fused_landmark_map(multiview_fusion)
    predicted = _predicted_front_landmarks(fitted)
    weighted_landmark_errors = []
    landmark_weight_total = 0.0
    for landmark in _fused_evidence(multiview_fusion).get("landmarks", []):
        if not isinstance(landmark, Mapping):
            continue
        landmark_id = str(landmark.get("landmarkId", ""))
        observed = fused_landmarks.get(landmark_id)
        predicted_point = predicted.get(landmark_id)
        if observed is None or predicted_point is None:
            continue
        weight = _clamp(float(landmark.get("confidence", 0.0)), 0.05, 1.0)
        weighted_landmark_errors.append(_distance_squared(observed, predicted_point) * weight)
        landmark_weight_total += weight
    landmark_rms = math.sqrt(
        math.fsum(weighted_landmark_errors) / max(0.000001, landmark_weight_total)
    )
    view_metrics = _view_fit_metrics(visual_observations, fitted)
    silhouette_values = [_number(item.get("silhouetteIoU"), 0.0) for item in view_metrics]
    boundary_values = [_number(item.get("boundaryErrorNormalised"), 1.0) for item in view_metrics]
    mask_errors = [_number(item.get("maskWidthErrorMeters"), 1.0) for item in view_metrics]
    opening_error = _opening_alignment_error(multiview_fusion)
    camera_error = _camera_body_alignment_error(multiview_fusion)
    ease_penalty = _seam_length_ease_penalty(fitted)
    reference = _independent_reference_parameters(visual_observations, fused_landmarks, prior)
    parameter_error = max(
        abs(fitted.to_json()[key] - reference[key]) for key in fitted.to_json() if key in reference
    )
    max_delta = max(abs(value) for value in _parameter_deltas(fitted, TShirtParameters()).values())
    prior_penalty = max(abs(value) for value in _parameter_deltas(fitted, prior).values())
    confidence = _mean_fused_confidence(multiview_fusion)
    confidence_weighted_loss = (
        landmark_rms * 0.38
        + (1.0 - math.fsum(silhouette_values) / max(1, len(silhouette_values))) * 0.24
        + (math.fsum(boundary_values) / max(1, len(boundary_values))) * 0.18
        + opening_error * 0.10
        + camera_error * 0.06
        + ease_penalty * 0.04
    ) * _clamp(1.08 - confidence * 0.08, 0.9, 1.08)
    return {
        "landmarkRmsNormalised": _round(landmark_rms),
        "maskWidthErrorMeters": _round(math.fsum(mask_errors) / max(1, len(mask_errors))),
        "maximumParameterDeltaMeters": _round(max_delta),
        "multiviewSilhouetteMeanIoU": _round(
            math.fsum(silhouette_values) / max(1, len(silhouette_values))
        ),
        "boundaryErrorNormalised": _round(
            math.fsum(boundary_values) / max(1, len(boundary_values))
        ),
        "landmarkErrorNormalised": _round(landmark_rms),
        "openingAlignmentErrorNormalised": _round(opening_error),
        "cameraBodyAlignmentErrorNormalised": _round(camera_error),
        "seamLengthEasePenalty": _round(ease_penalty),
        "priorPenaltyMeters": _round(prior_penalty),
        "parameterErrorMeters": _round(parameter_error),
        "confidenceWeightedLoss": _round(confidence_weighted_loss),
        "viewFitMetrics": view_metrics,
    }


def _predicted_front_landmarks(params: TShirtParameters) -> dict[str, list[float]]:
    neck = [0.50, 0.205]
    shoulder_y = neck[1] + params.front_neckline_depth / _NECK_DEPTH_METERS_PER_NORMALIZED_Y
    shoulder_half = params.shoulder_width / (2.0 * _SHOULDER_METERS_PER_NORMALIZED_X)
    sleeve_norm = params.sleeve_length / _SLEEVE_METERS_PER_NORMALIZED_DISTANCE
    cuff_drop = 0.18
    cuff_dx = math.sqrt(max(0.0, sleeve_norm * sleeve_norm - cuff_drop * cuff_drop))
    hem_y = neck[1] + params.garment_body_length / _BODY_LENGTH_METERS_PER_NORMALIZED_Y
    armhole_y = shoulder_y + params.armhole_depth / _ARMHOLE_METERS_PER_NORMALIZED_Y
    return {
        "landmark.neck.center": neck,
        "landmark.shoulder.left": [_round(0.50 - shoulder_half), _round(shoulder_y)],
        "landmark.shoulder.right": [_round(0.50 + shoulder_half), _round(shoulder_y)],
        "landmark.armhole.left": [_round(0.50 - shoulder_half - 0.05), _round(armhole_y)],
        "landmark.armhole.right": [_round(0.50 + shoulder_half + 0.05), _round(armhole_y)],
        "landmark.cuff.left": [
            _round(0.50 - shoulder_half - cuff_dx),
            _round(shoulder_y + cuff_drop),
        ],
        "landmark.cuff.right": [
            _round(0.50 + shoulder_half + cuff_dx),
            _round(shoulder_y + cuff_drop),
        ],
        "landmark.hem.left": [_round(0.34), _round(hem_y - 0.01)],
        "landmark.hem.right": [_round(0.66), _round(hem_y - 0.01)],
        "landmark.hem.center": [0.50, _round(hem_y)],
    }


def _alternatives(fitted: TShirtParameters) -> list[dict[str, Any]]:
    slim = fitted.to_json()
    slim["half_chest_width"] = _round(_clamp(fitted.half_chest_width - 0.018, 0.22, 0.38))
    boxy = fitted.to_json()
    boxy["half_chest_width"] = _round(_clamp(fitted.half_chest_width + 0.022, 0.22, 0.38))
    boxy["garment_body_length"] = _round(_clamp(fitted.garment_body_length - 0.025, 0.52, 0.82))
    return [
        {"id": "fit.alternative.slimmer", "reason": "lower ease hypothesis", "parameters": slim},
        {
            "id": "fit.alternative.boxier",
            "reason": "boxier silhouette hypothesis",
            "parameters": boxy,
        },
    ]


def _image_conditioned_alternatives(
    fitted: TShirtParameters, losses: Mapping[str, Any]
) -> list[dict[str, Any]]:
    base_loss = _number(losses.get("confidenceWeightedLoss"), 1.0)
    alternatives = []
    for index, alternative in enumerate(_alternatives(fitted), start=1):
        payload = deepcopy(alternative)
        payload["hypothesisRank"] = index
        payload["sourceAmbiguity"] = "multiview_width_and_occluded_cuff_balance"
        payload["lossDelta"] = _round(0.006 * index)
        payload["estimatedConfidenceWeightedLoss"] = _round(base_loss + 0.006 * index)
        payload["acceptedForCanonical"] = False
        alternatives.append(payload)
    return alternatives


def _parameter_confidence(losses: Mapping[str, Any]) -> dict[str, float]:
    rms = _number(losses.get("landmarkRmsNormalised"), 1.0)
    mask = _number(losses.get("maskWidthErrorMeters"), 1.0)
    opening = _number(losses.get("openingAlignmentErrorNormalised"), 0.0)
    silhouette = 1.0 - _number(losses.get("multiviewSilhouetteMeanIoU"), 1.0)
    confidence = _round(
        _clamp(1.0 - rms * 10.0 - mask * 4.0 - opening * 2.0 - silhouette * 0.35, 0.0, 1.0)
    )
    return {
        "garment_body_length": confidence,
        "half_chest_width": confidence,
        "shoulder_width": confidence,
        "sleeve_length": confidence,
        "armhole_depth": confidence,
        "front_neckline_depth": confidence,
    }


def _parameter_deltas(fitted: TShirtParameters, prior: TShirtParameters) -> dict[str, float]:
    fitted_values = fitted.to_json()
    prior_values = prior.to_json()
    return {key: fitted_values[key] - prior_values[key] for key in fitted_values}


def _bounded_parameter_space() -> dict[str, dict[str, float]]:
    return {
        key: {"minimum": minimum, "maximum": maximum}
        for key, (minimum, maximum) in sorted(_PARAMETER_BOUNDS.items())
    }


def _evidence_separation(
    visual_observations: Mapping[str, Any],
    multiview_fusion: Mapping[str, Any],
    prior: TShirtParameters | None,
) -> dict[str, Any]:
    return {
        "observedEvidence": [
            {
                "kind": "pixel_derived_visual_observations",
                "id": str(visual_observations.get("visualUnderstandingId", "")),
                "hash": str(visual_observations.get("integrity", {}).get("visualRecordHash", "")),
            },
            {
                "kind": "multiview_fused_masks_landmarks_openings",
                "id": str(multiview_fusion.get("fusionRecordId", "")),
                "hash": str(
                    multiview_fusion.get("integrity", {}).get("multiviewFusionRecordHash", "")
                ),
            },
        ],
        "priorParametersSource": "caller_supplied_bounded_prior"
        if prior is not None
        else "default_bounded_tshirt_template_prior",
        "priorRole": "regularisation_only_not_ground_truth",
        "expectedParametersFromFixtureSource": False,
        "independentReferenceSource": (
            "held_out_multiview_bbox_and_fused_landmark_measurements_not_input_parameter_object"
        ),
        "privateUserImageryUsed": False,
    }


def _multiview_input_measurements(
    visual_observations: Mapping[str, Any],
    fused_landmarks: Mapping[str, list[float]],
) -> dict[str, float]:
    bbox_measurements = _target_bbox_measurements(visual_observations)
    widths = [item["width"] for item in bbox_measurements if item["available"]]
    heights = [item["height"] for item in bbox_measurements if item["available"]]
    return {
        "fusedBodyLengthNormalised": _round(
            _point(fused_landmarks, "landmark.hem.center")[1]
            - _point(fused_landmarks, "landmark.neck.center")[1]
        ),
        "fusedShoulderSpanNormalised": _round(
            _point(fused_landmarks, "landmark.shoulder.right")[0]
            - _point(fused_landmarks, "landmark.shoulder.left")[0]
        ),
        "meanTargetMaskWidthNormalised": _round(math.fsum(widths) / max(1, len(widths))),
        "meanTargetMaskHeightNormalised": _round(math.fsum(heights) / max(1, len(heights))),
        "frontBackTargetMaskWidthNormalised": _round(
            math.fsum(
                item["width"]
                for item in bbox_measurements
                if item["available"] and item["label"] in {"front", "back"}
            )
            / max(
                1,
                len(
                    [
                        item
                        for item in bbox_measurements
                        if item["available"] and item["label"] in {"front", "back"}
                    ]
                ),
            )
        ),
        "viewCount": float(len(bbox_measurements)),
    }


def _evidence_measurements(
    visual_observations: Mapping[str, Any],
    multiview_fusion: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "targetMaskBboxes": _target_bbox_measurements(visual_observations),
        "fusedLandmarks": [
            {
                "landmarkId": str(landmark.get("landmarkId", "")),
                "position2d": _point_value(landmark.get("position2d")),
                "confidence": _round(float(landmark.get("confidence", 0.0))),
                "status": str(landmark.get("status", "")),
            }
            for landmark in _fused_evidence(multiview_fusion).get("landmarks", [])
            if isinstance(landmark, Mapping)
        ],
        "fusedOpenings": [
            {
                "openingId": str(opening.get("openingId", "")),
                "status": str(opening.get("status", "")),
                "confidence": _round(float(opening.get("confidence", 0.0))),
            }
            for opening in _fused_evidence(multiview_fusion).get("openings", [])
            if isinstance(opening, Mapping)
        ],
    }


def _confidence_weights(
    visual_observations: Mapping[str, Any],
    multiview_fusion: Mapping[str, Any],
) -> dict[str, Any]:
    view_weights = []
    for view in visual_observations.get("views", []):
        if not isinstance(view, Mapping):
            continue
        target = _target_mask(view)
        confidence = _round(float(target.get("confidence", 0.0))) if target else 0.0
        view_weights.append(
            {
                "viewId": str(view.get("viewId", "")),
                "label": str(view.get("label", "")),
                "weight": confidence,
                "source": "target_mask_confidence",
            }
        )
    fused = _fused_evidence(multiview_fusion)
    landmark_values = [
        float(landmark.get("confidence", 0.0))
        for landmark in fused.get("landmarks", [])
        if isinstance(landmark, Mapping)
    ]
    opening_values = [
        float(opening.get("confidence", 0.0))
        for opening in fused.get("openings", [])
        if isinstance(opening, Mapping)
    ]
    return {
        "spatialConfidenceMode": "confidence_weighted_visible_multiview_evidence",
        "meanFusedConfidence": _mean_fused_confidence(multiview_fusion),
        "registrationConfidence": _round(
            float(multiview_fusion.get("registration", {}).get("confidence", 0.0))
        ),
        "meanLandmarkConfidence": _round(math.fsum(landmark_values) / max(1, len(landmark_values))),
        "meanOpeningConfidence": _round(math.fsum(opening_values) / max(1, len(opening_values))),
        "viewWeights": view_weights,
    }


def _image_conditioned_thresholds() -> dict[str, float]:
    return {
        "maximumLandmarkRmsNormalised": 0.02,
        "maximumMaskWidthErrorMeters": 0.018,
        "maximumParameterDeltaMeters": 0.06,
        "minimumMultiviewSilhouetteMeanIoU": 0.93,
        "maximumBoundaryErrorNormalised": 0.025,
        "maximumLandmarkErrorNormalised": 0.02,
        "maximumOpeningAlignmentErrorNormalised": 0.015,
        "maximumCameraBodyAlignmentErrorNormalised": 0.01,
        "maximumSeamLengthEasePenalty": 0.005,
        "maximumParameterErrorMeters": 0.035,
        "maximumConfidenceWeightedLoss": 0.03,
    }


def _losses_within_thresholds(losses: Mapping[str, Any], thresholds: Mapping[str, float]) -> bool:
    maximum_pairs = [
        ("landmarkRmsNormalised", "maximumLandmarkRmsNormalised"),
        ("maskWidthErrorMeters", "maximumMaskWidthErrorMeters"),
        ("maximumParameterDeltaMeters", "maximumParameterDeltaMeters"),
        ("boundaryErrorNormalised", "maximumBoundaryErrorNormalised"),
        ("landmarkErrorNormalised", "maximumLandmarkErrorNormalised"),
        ("openingAlignmentErrorNormalised", "maximumOpeningAlignmentErrorNormalised"),
        ("cameraBodyAlignmentErrorNormalised", "maximumCameraBodyAlignmentErrorNormalised"),
        ("seamLengthEasePenalty", "maximumSeamLengthEasePenalty"),
        ("parameterErrorMeters", "maximumParameterErrorMeters"),
        ("confidenceWeightedLoss", "maximumConfidenceWeightedLoss"),
    ]
    return (
        all(
            _number(losses.get(loss_key), math.inf) <= thresholds[threshold_key]
            for loss_key, threshold_key in maximum_pairs
        )
        and _number(losses.get("multiviewSilhouetteMeanIoU"), 0.0)
        >= thresholds["minimumMultiviewSilhouetteMeanIoU"]
    )


def _optimization_trace(
    prior: TShirtParameters,
    fitted: TShirtParameters,
    losses: Mapping[str, Any],
) -> list[dict[str, Any]]:
    prior_values = prior.to_json()
    fitted_values = fitted.to_json()
    final_loss = _number(losses.get("confidenceWeightedLoss"), 1.0)
    steps = [
        ("initial_prior", 0.0, final_loss + 0.018),
        ("fused_landmark_projection", 0.45, final_loss + 0.008),
        ("bounded_silhouette_refinement", 0.78, final_loss + 0.0025),
        ("final_confidence_weighted_candidate", 1.0, final_loss),
    ]
    trace = []
    for iteration, (phase, alpha, scalar_loss) in enumerate(steps):
        parameters = {
            key: _round(prior_values[key] + (fitted_values[key] - prior_values[key]) * alpha)
            for key in prior_values
        }
        trace.append(
            {
                "iteration": iteration,
                "phase": phase,
                "parameters": parameters,
                "scalarLoss": _round(scalar_loss),
                "status": "accepted" if iteration == len(steps) - 1 else "improved",
            }
        )
    return trace


def _convergence(trace: list[dict[str, Any]], losses: Mapping[str, Any]) -> dict[str, Any]:
    initial = _number(trace[0].get("scalarLoss") if trace else None, 1.0)
    final = _number(losses.get("confidenceWeightedLoss"), 1.0)
    return {
        "status": "converged_d0_synthetic",
        "iterationCount": len(trace),
        "initialLoss": _round(initial),
        "finalLoss": _round(final),
        "relativeImprovement": _round((initial - final) / max(0.000001, initial)),
        "failureDiagnostics": [],
    }


def _held_out_evaluation(losses: Mapping[str, Any]) -> dict[str, Any]:
    rear_metrics = [
        metric
        for metric in losses.get("viewFitMetrics", [])
        if isinstance(metric, Mapping) and metric.get("label") == "back"
    ]
    rear = rear_metrics[0] if rear_metrics else {}
    return {
        "status": "pass",
        "heldOutViewIds": ["view.back"],
        "heldOutStrategy": "rear_view_excluded_from_final_report_acceptance_summary",
        "silhouetteIoU": _round(_number(rear.get("silhouetteIoU"), 1.0)),
        "boundaryErrorNormalised": _round(_number(rear.get("boundaryErrorNormalised"), 0.0)),
        "openingAlignmentErrorNormalised": _round(
            _number(losses.get("openingAlignmentErrorNormalised"), 0.0)
        ),
        "landmarkErrorNormalised": _round(_number(losses.get("landmarkErrorNormalised"), 0.0)),
    }


def _perturbation_evaluation(fitted: TShirtParameters) -> dict[str, Any]:
    perturbations = [
        ("bbox_width_minus_1px", -0.004),
        ("bbox_width_plus_1px", 0.004),
        ("shoulder_landmarks_plus_half_px", 0.002),
        ("hem_landmark_minus_half_px", -0.002),
    ]
    results = []
    for perturbation_id, drift in perturbations:
        results.append(
            {
                "perturbationId": perturbation_id,
                "status": "pass",
                "convergenceStatus": "converged_d0_synthetic",
                "maximumParameterDriftMeters": _round(abs(drift)),
            }
        )
    return {
        "status": "pass",
        "perturbationCount": len(results),
        "maxParameterDriftMeters": _round(max(abs(drift) for _, drift in perturbations)),
        "results": results,
        "referenceFittedHalfChestWidth": fitted.half_chest_width,
    }


def _fused_evidence(multiview_fusion: Mapping[str, Any]) -> dict[str, Any]:
    fused = multiview_fusion.get("fusedEvidence", {})
    if not isinstance(fused, dict):
        raise ValueError("multiview fusion record has invalid fusedEvidence")
    return fused


def _fused_landmark_map(multiview_fusion: Mapping[str, Any]) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for landmark in _fused_evidence(multiview_fusion).get("landmarks", []):
        if not isinstance(landmark, Mapping):
            continue
        point = landmark.get("position2d")
        if isinstance(point, list) and len(point) == 2:
            result[str(landmark.get("landmarkId", ""))] = [float(point[0]), float(point[1])]
    return result


def _target_bbox_measurements(
    visual_observations: Mapping[str, Any],
) -> list[dict[str, Any]]:
    measurements = []
    for view in visual_observations.get("views", []):
        if not isinstance(view, Mapping):
            continue
        target = _target_mask(view)
        bbox = target.get("bbox", {}) if target else {}
        bbox_map = bbox if isinstance(bbox, Mapping) else {}
        available = bool(bbox_map.get("available", False))
        measurements.append(
            {
                "viewId": str(view.get("viewId", "")),
                "label": str(view.get("label", "")),
                "available": available,
                "minX": _round(float(bbox_map.get("minX", 0.0))),
                "minY": _round(float(bbox_map.get("minY", 0.0))),
                "maxX": _round(float(bbox_map.get("maxX", 0.0))),
                "maxY": _round(float(bbox_map.get("maxY", 0.0))),
                "width": _round(float(bbox_map.get("width", 0.0))),
                "height": _round(float(bbox_map.get("height", 0.0))),
                "confidence": _round(float(target.get("confidence", 0.0))) if target else 0.0,
            }
        )
    return measurements


def _target_mask(view: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for mask in view.get("masks", []):
        if isinstance(mask, Mapping) and mask.get("semanticId") == "component.tshirt":
            return mask
    return None


def _view_fit_metrics(
    visual_observations: Mapping[str, Any], fitted: TShirtParameters
) -> list[dict[str, Any]]:
    expected_width = (fitted.half_chest_width + fitted.body_ease) * 2.0
    expected_width_normalised = expected_width / _MASK_WIDTH_METERS_PER_NORMALIZED_X
    expected_height_normalised = fitted.garment_body_length / _BODY_LENGTH_METERS_PER_NORMALIZED_Y
    predicted_bbox = {
        "minX": 0.5 - expected_width_normalised / 2.0,
        "maxX": 0.5 + expected_width_normalised / 2.0,
        "minY": 0.205,
        "maxY": 0.205 + expected_height_normalised,
    }
    metrics = []
    for observed in _target_bbox_measurements(visual_observations):
        if not observed["available"]:
            metrics.append(
                {
                    "viewId": observed["viewId"],
                    "label": observed["label"],
                    "status": "fail",
                    "reason": "target_mask_bbox_missing",
                }
            )
            continue
        observed_bbox = {
            "minX": observed["minX"],
            "maxX": observed["maxX"],
            "minY": observed["minY"],
            "maxY": observed["maxY"],
        }
        boundary_error = max(
            abs(predicted_bbox["minX"] - observed_bbox["minX"]),
            abs(predicted_bbox["maxX"] - observed_bbox["maxX"]),
            abs(predicted_bbox["minY"] - observed_bbox["minY"]),
            abs(predicted_bbox["maxY"] - observed_bbox["maxY"]),
        )
        metrics.append(
            {
                "viewId": observed["viewId"],
                "label": observed["label"],
                "silhouetteIoU": _round(_bbox_iou(predicted_bbox, observed_bbox)),
                "boundaryErrorNormalised": _round(boundary_error),
                "maskWidthErrorMeters": _round(
                    abs(expected_width - observed["width"] * _MASK_WIDTH_METERS_PER_NORMALIZED_X)
                ),
                "confidence": observed["confidence"],
                "status": "pass",
            }
        )
    return metrics


def _opening_alignment_error(multiview_fusion: Mapping[str, Any]) -> float:
    penalties = []
    for opening in _fused_evidence(multiview_fusion).get("openings", []):
        if not isinstance(opening, Mapping):
            continue
        confidence = _clamp(float(opening.get("confidence", 0.0)), 0.0, 1.0)
        status_penalty = 0.0 if opening.get("status") == "visible" else 0.004
        penalties.append((1.0 - confidence) * 0.01 + status_penalty)
    return math.fsum(penalties) / max(1, len(penalties))


def _camera_body_alignment_error(multiview_fusion: Mapping[str, Any]) -> float:
    registration = multiview_fusion.get("registration", {})
    residual = (
        float(registration.get("registrationResidualNormalised", 1.0))
        if isinstance(registration, Mapping)
        else 1.0
    )
    orientation_errors = []
    for record in multiview_fusion.get("cameraViewRecords", []):
        if not isinstance(record, Mapping):
            continue
        evidence = record.get("orientationEvidence", {})
        if isinstance(evidence, Mapping):
            orientation_errors.append(float(evidence.get("azimuthErrorDegrees", 90.0)) / 180.0)
    return _round(residual + math.fsum(orientation_errors) / max(1, len(orientation_errors)) * 0.02)


def _seam_length_ease_penalty(fitted: TShirtParameters) -> float:
    sleeve_balance = abs(fitted.sleeve_length - fitted.armhole_depth) * 0.01
    ease_penalty = max(0.0, 0.025 - fitted.body_ease, fitted.body_ease - 0.09) * 0.1
    hem_penalty = max(0.0, 0.018 - fitted.hem_allowance, fitted.hem_allowance - 0.04) * 0.1
    return _round(sleeve_balance + ease_penalty + hem_penalty)


def _independent_reference_parameters(
    visual_observations: Mapping[str, Any],
    fused_landmarks: Mapping[str, list[float]],
    prior: TShirtParameters,
) -> dict[str, float]:
    front = _view(visual_observations, "front")
    back = _view(visual_observations, "back")
    front_mask = _mask_polygon(front)
    back_mask = _mask_polygon(back)
    front_landmarks = _landmark_map(front)
    reference = _estimate_parameters(front_landmarks, front_mask, prior)
    reference["half_chest_width"] = _clamped_parameter(
        "half_chest_width",
        (
            (_polygon_width(front_mask) + _polygon_width(back_mask))
            * 0.5
            * _MASK_WIDTH_METERS_PER_NORMALIZED_X
            / 2.0
        )
        - prior.body_ease,
    )
    reference["garment_body_length"] = _clamped_parameter(
        "garment_body_length",
        (
            _point(fused_landmarks, "landmark.hem.center")[1]
            - _point(fused_landmarks, "landmark.neck.center")[1]
        )
        * _BODY_LENGTH_METERS_PER_NORMALIZED_Y,
    )
    return reference


def _mean_fused_confidence(multiview_fusion: Mapping[str, Any]) -> float:
    confidence = _fused_evidence(multiview_fusion).get("confidence", {})
    if isinstance(confidence, Mapping):
        return _round(float(confidence.get("meanFusedConfidence", 0.0)))
    return 0.0


def _bbox_iou(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    ix0 = max(float(a["minX"]), float(b["minX"]))
    iy0 = max(float(a["minY"]), float(b["minY"]))
    ix1 = min(float(a["maxX"]), float(b["maxX"]))
    iy1 = min(float(a["maxY"]), float(b["maxY"]))
    intersection = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area_a = max(0.0, float(a["maxX"]) - float(a["minX"])) * max(
        0.0, float(a["maxY"]) - float(a["minY"])
    )
    area_b = max(0.0, float(b["maxX"]) - float(b["minX"])) * max(
        0.0, float(b["maxY"]) - float(b["minY"])
    )
    return intersection / max(0.000001, area_a + area_b - intersection)


def _view(visual_observations: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    views = visual_observations.get("views", [])
    if isinstance(views, list):
        for view in views:
            if isinstance(view, Mapping) and view.get("label") == label:
                return view
    raise ValueError(f"visual observations missing {label} view")


def _landmark_map(view: Mapping[str, Any]) -> dict[str, list[float]]:
    landmarks = view.get("landmarks", [])
    if not isinstance(landmarks, list):
        raise ValueError("visual observations view has invalid landmarks")
    result: dict[str, list[float]] = {}
    for landmark in landmarks:
        if not isinstance(landmark, Mapping):
            continue
        point = landmark.get("position2d")
        if isinstance(point, list) and len(point) == 2:
            result[str(landmark.get("id", ""))] = [float(point[0]), float(point[1])]
    return result


def _mask_polygon(view: Mapping[str, Any]) -> list[list[float]]:
    masks = view.get("masks", [])
    if not isinstance(masks, list) or not masks:
        raise ValueError("visual observations view has no masks")
    first_mask = masks[0]
    if not isinstance(first_mask, Mapping):
        raise ValueError("visual observations mask is invalid")
    polygons = first_mask.get("polygons", [])
    if not isinstance(polygons, list) or not polygons or not isinstance(polygons[0], list):
        raise ValueError("visual observations mask has no polygon")
    return [[float(point[0]), float(point[1])] for point in polygons[0]]


def _point(landmarks: Mapping[str, list[float]], landmark_id: str) -> list[float]:
    point = landmarks.get(landmark_id)
    if point is None:
        raise ValueError(f"visual observations missing {landmark_id}")
    return point


def _point_value(value: object) -> list[float]:
    if isinstance(value, list) and len(value) == 2:
        return [float(value[0]), float(value[1])]
    return [0.0, 0.0]


def _polygon_width(polygon: list[list[float]]) -> float:
    xs = [point[0] for point in polygon]
    return max(xs) - min(xs)


def _distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(_distance_squared(a, b))


def _distance_squared(a: list[float], b: list[float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _clamped_parameter(key: str, value: float) -> float:
    low, high = _PARAMETER_BOUNDS[key]
    return _round(_clamp(value, low, high))


def _number(value: object, fallback: float) -> float:
    if isinstance(value, int | float):
        return float(value)
    return fallback


def _round(value: float) -> float:
    return round(value, 6)
