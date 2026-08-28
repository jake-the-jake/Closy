from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from typing import Any

from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.garments.tshirt.assembly import build_constraints, build_simulation_mesh
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.geometry.mesh_model import finite_mesh
from closy_forge.inspection.cpu_raster import rasterize_settled_garment
from closy_forge.package_io.hashing import geometry_content_hash, topology_hash
from closy_forge.simulation.material_motion_suite import MATERIAL_MOTION_CANONICAL_POSITION_DIGITS
from closy_forge.simulation.reference_cloth_solver import settle_reference_cloth

D0_OPTIMIZER_VERSION = "closy.tshirt_fit.bounded_coordinate_search.d0_v2"

_SEARCH_PARAMETERS = {
    "garment_body_length": 0.055,
    "half_chest_width": 0.028,
    "shoulder_width": 0.045,
    "front_neckline_depth": 0.025,
    "armhole_depth": 0.028,
    "sleeve_length": 0.045,
    "sleeve_opening_width": 0.025,
    "sleeve_cap_height": 0.02,
}

_PARAMETER_BOUNDS = {
    "garment_body_length": (0.52, 0.82),
    "half_chest_width": (0.22, 0.38),
    "shoulder_width": (0.52, 0.84),
    "front_neckline_depth": (0.035, 0.16),
    "armhole_depth": (0.14, 0.30),
    "sleeve_length": (0.14, 0.38),
    "sleeve_opening_width": (0.12, 0.28),
    "sleeve_cap_height": (0.06, 0.17),
}


@dataclass(frozen=True)
class D0OptimizationResult:
    initial_parameters: dict[str, float]
    final_parameters: dict[str, float]
    initial_evaluation: dict[str, Any]
    final_evaluation: dict[str, Any]
    history: list[dict[str, Any]]
    convergence: dict[str, Any]
    full_solver_verification: dict[str, Any]
    alternatives: list[dict[str, Any]]
    uncertainty: dict[str, Any]


def optimize_tshirt_d0(
    visual_observations: Mapping[str, Any],
    multiview_fusion: Mapping[str, Any],
    prior: TShirtParameters,
) -> D0OptimizationResult:
    _validate_evidence(visual_observations, multiview_fusion)
    current = _perturbed_start(prior)
    current_eval = evaluate_candidate(visual_observations, multiview_fusion, current, prior)
    initial = current
    initial_eval = current_eval
    history = [_history_record(0, 0, "baseline", current, current_eval, True)]
    sequence = 1
    accepted_moves = 0
    bounded_termination = "maximum_sweeps_reached"
    for sweep in range(5):
        sweep_improved = False
        scale = 0.5**sweep
        for parameter, base_step in _SEARCH_PARAMETERS.items():
            candidates: list[tuple[TShirtParameters, dict[str, Any], float]] = []
            for direction in (-1.0, 1.0):
                candidate = _with_parameter(current, parameter, base_step * scale * direction)
                evaluation = evaluate_candidate(
                    visual_observations, multiview_fusion, candidate, prior
                )
                candidates.append((candidate, evaluation, direction))
            candidate, evaluation, direction = min(
                candidates,
                key=lambda item: (
                    float(item[1]["objective"]),
                    asdict(item[0])[parameter],
                ),
            )
            accepted = float(evaluation["objective"]) + 1e-10 < float(current_eval["objective"])
            history.append(
                _history_record(
                    sequence,
                    sweep + 1,
                    f"{parameter}:{'increase' if direction > 0 else 'decrease'}",
                    candidate,
                    evaluation,
                    accepted,
                )
            )
            sequence += 1
            if accepted:
                current = candidate
                current_eval = evaluation
                accepted_moves += 1
                sweep_improved = True
        if not sweep_improved:
            bounded_termination = "coordinate_stationary"
            break
    full_solver = _full_solver_verification(visual_observations, current)
    alternatives = _alternatives(visual_observations, multiview_fusion, current, prior)
    improvement = float(initial_eval["objective"]) - float(current_eval["objective"])
    converged = (
        improvement >= 0.015
        and float(current_eval["objective"]) <= 0.16
        and full_solver["status"] == "pass"
    )
    return D0OptimizationResult(
        initial_parameters=asdict(initial),
        final_parameters=asdict(current),
        initial_evaluation=initial_eval,
        final_evaluation=current_eval,
        history=history,
        convergence={
            "status": "converged_d0_public_fixture" if converged else "bounded_without_acceptance",
            "terminationReason": bounded_termination,
            "candidateEvaluationCount": len(history) * 2 - 1,
            "persistedHistoryCount": len(history),
            "acceptedMoveCount": accepted_moves,
            "initialObjective": _round(float(initial_eval["objective"])),
            "finalObjective": _round(float(current_eval["objective"])),
            "absoluteImprovement": _round(improvement),
            "relativeImprovement": _round(
                improvement / max(1e-9, float(initial_eval["objective"]))
            ),
            "noOpCandidateAccepted": False,
            "bounded": True,
            "deterministic": True,
        },
        full_solver_verification=full_solver,
        alternatives=alternatives,
        uncertainty={
            "mode": "local_coordinate_neighbourhood_spread",
            "alternativeCount": len(alternatives),
            "objectiveSpread": _round(
                max(float(item["objective"]) for item in alternatives)
                - min(float(item["objective"]) for item in alternatives)
            ),
            "privateUserConfidenceCalibrated": False,
            "providerShellConfidenceCalibrated": False,
        },
    )


def validate_d0_fit_evidence(
    visual_observations: Mapping[str, Any], multiview_fusion: Mapping[str, Any]
) -> None:
    _validate_evidence(visual_observations, multiview_fusion)


def run_fit_corruption_controls(
    visual_observations: Mapping[str, Any],
    multiview_fusion: Mapping[str, Any],
    final: TShirtParameters,
    prior: TShirtParameters,
) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    corrupt_mask = deepcopy(visual_observations)
    first_view = _views(corrupt_mask)[0]
    target_record = _target_mask_record(first_view)
    rle = _mapping(target_record.get("rle"))
    if isinstance(rle, dict):
        rle["runs"] = [[int(rle.get("width", 0)) * int(rle.get("height", 0)), 2]]
    controls.append(
        _rejection_control(
            "corrupted_mask_rle",
            lambda: evaluate_candidate(corrupt_mask, multiview_fusion, final, prior),
            "d0_fit_corrupt_mask_rle",
        )
    )
    corrupt_camera = deepcopy(visual_observations)
    camera = _mapping(_views(corrupt_camera)[0].get("camera"))
    if isinstance(camera, dict):
        camera["azimuthDegrees"] = 90.0
    controls.append(
        _rejection_control(
            "camera_azimuth_perturbation",
            lambda: _validate_evidence(corrupt_camera, multiview_fusion),
            "d0_fit_camera_evidence_invalid",
        )
    )
    return controls


def evaluate_candidate(
    visual_observations: Mapping[str, Any],
    multiview_fusion: Mapping[str, Any],
    candidate: TShirtParameters,
    prior: TShirtParameters,
) -> dict[str, Any]:
    view_metrics = [_view_metrics(view, candidate) for view in _views(visual_observations)]
    silhouette_loss = _mean(1.0 - float(item["silhouetteIoU"]) for item in view_metrics)
    boundary_loss = _mean(float(item["boundaryChamferNormalised"]) for item in view_metrics)
    landmark_loss = _mean(float(item["landmarkRmsNormalised"]) for item in view_metrics)
    front = next((item for item in view_metrics if item["label"] == "front"), None)
    back = next((item for item in view_metrics if item["label"] == "back"), None)
    front_rear = (
        abs(float(front["silhouetteIoU"]) - float(back["silhouetteIoU"])) if front and back else 1.0
    )
    regularization = _regularization(candidate, prior)
    seam_penalty = _seam_penalty(candidate)
    invalid_penalty, drape_penalty, validity = _geometry_validity(candidate)
    camera_penalty = _camera_penalty(_views(visual_observations))
    confidence = _evidence_confidence(visual_observations, multiview_fusion)
    objective = (
        silhouette_loss * 0.34
        + boundary_loss * 0.17
        + landmark_loss * 0.20
        + front_rear * 0.05
        + regularization * 0.06
        + seam_penalty * 0.05
        + invalid_penalty * 0.06
        + drape_penalty * 0.04
        + camera_penalty * 0.03
    ) * (1.04 - min(1.0, confidence) * 0.04)
    return {
        "evaluationMode": "decoded_mask_landmark_projection_surrogate",
        "objective": _round(objective),
        "terms": {
            "silhouetteLoss": _round(silhouette_loss),
            "boundaryChamferNormalised": _round(boundary_loss),
            "landmarkReprojectionRmsNormalised": _round(landmark_loss),
            "frontRearConsistencyPenalty": _round(front_rear),
            "patternRegularisationPenalty": _round(regularization),
            "seamLengthCompatibilityPenalty": _round(seam_penalty),
            "invalidGeometryPenalty": _round(invalid_penalty),
            "drapeValidityPenalty": _round(drape_penalty),
            "cameraValidityPenalty": _round(camera_penalty),
        },
        "viewMetrics": view_metrics,
        "evidenceConfidence": _round(confidence),
        "patternValidity": validity,
    }


def _full_solver_verification(
    visual_observations: Mapping[str, Any], candidate: TShirtParameters
) -> dict[str, Any]:
    pattern = build_tshirt_pattern(candidate)
    rest_mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)
    avatar_mesh = build_reference_avatar_mesh()
    collision_mesh = build_collision_mesh()
    settled = settle_reference_cloth(
        rest_mesh,
        constraints,
        avatar_contract(avatar_mesh, collision_mesh),
        {
            "dampingRatio": 0.18,
            "source": "fixed_d0_cotton_reference_for_fit_verification",
        },
        canonical_position_digits=MATERIAL_MOTION_CANONICAL_POSITION_DIGITS,
    )
    rendered_views: list[dict[str, Any]] = []
    for view in _views(visual_observations):
        width, height = _dimensions(view)
        raster = rasterize_settled_garment(
            settled.settled_mesh,
            label=str(view.get("label", "front")),
            width=width,
            height=height,
            camera=_mapping(view.get("camera")),
        )
        target = _target_mask(view)
        rendered_views.append(
            {
                "viewId": str(view.get("viewId", "")),
                "label": str(view.get("label", "")),
                "silhouetteIoU": _round(_iou(set(raster.foreground), target)),
                "renderedForegroundPixels": len(raster.foreground),
                "sourceForegroundPixels": len(target),
                "renderedTriangleCount": raster.rendered_triangle_count,
                "camera": raster.camera,
            }
        )
    mean_iou = _mean(float(item["silhouetteIoU"]) for item in rendered_views)
    diagnostics = settled.diagnostics
    pass_state = (
        diagnostics.get("convergenceState") == "converged"
        and int(diagnostics.get("nonFiniteValueCount", 1)) == 0
        and mean_iou >= 0.30
    )
    return {
        "status": "pass" if pass_state else "fail",
        "evaluationMode": "actual_reference_xpbd_settle_then_independent_cpu_triangle_raster",
        "solverVersion": diagnostics.get("solverVersion"),
        "settledTopologyHash": topology_hash(settled.settled_mesh),
        "settledContentHash": geometry_content_hash(settled.settled_mesh),
        "restTopologyHash": topology_hash(rest_mesh),
        "constraintCount": len(constraints.get("constraints", [])),
        "convergenceState": diagnostics.get("convergenceState"),
        "nonFiniteValueCount": diagnostics.get("nonFiniteValueCount"),
        "maximumBodyPenetrationMeters": diagnostics.get("maximumBodyPenetrationMeters"),
        "maximumSeamResidualMeters": diagnostics.get("maximumSeamResidualMeters"),
        "meanSettledSilhouetteIoU": _round(mean_iou),
        "minimumSettledSilhouetteIoU": 0.30,
        "viewMetrics": rendered_views,
        "fullSolverRun": True,
        "renderedCandidateEvaluated": True,
    }


def _view_metrics(view: Mapping[str, Any], candidate: TShirtParameters) -> dict[str, Any]:
    width, height = _dimensions(view)
    target = _target_mask(view)
    predicted = _predicted_mask(width, height, str(view.get("label", "front")), candidate)
    target_boundary = _boundary(target, width, height)
    predicted_boundary = _boundary(predicted, width, height)
    observed_landmarks = {
        str(item.get("id", "")): _point(item.get("position2d"))
        for item in view.get("landmarks", [])
        if isinstance(item, Mapping)
    }
    predicted_landmarks = _predicted_landmarks(candidate)
    lean = {
        "left_three_quarter": 0.025,
        "right_three_quarter": -0.025,
    }.get(str(view.get("label", "")), 0.0)
    predicted_landmarks = {
        key: (point[0] + lean, point[1]) for key, point in predicted_landmarks.items()
    }
    errors = [
        _distance(observed, predicted_landmarks[key])
        for key, observed in observed_landmarks.items()
        if key in predicted_landmarks
    ]
    return {
        "viewId": str(view.get("viewId", "")),
        "label": str(view.get("label", "")),
        "silhouetteIoU": _round(_iou(predicted, target)),
        "boundaryChamferNormalised": _round(
            _chamfer(target_boundary, predicted_boundary, width, height)
        ),
        "landmarkRmsNormalised": _round(
            math.sqrt(sum(value * value for value in errors) / max(1, len(errors)))
        ),
        "targetPixelCount": len(target),
        "predictedPixelCount": len(predicted),
        "sourceMaskHash": str(_target_mask_record(view).get("maskHash", "")),
    }


def _predicted_mask(width: int, height: int, label: str, candidate: TShirtParameters) -> set[int]:
    lean = {
        "left_three_quarter": 0.025,
        "right_three_quarter": -0.025,
    }.get(label, 0.0)
    torso_half = (candidate.half_chest_width + candidate.body_ease) / 1.8857142857
    shoulder_half = candidate.shoulder_width / 2.3333333333 / 2.0
    top = 0.20
    bottom = top + candidate.garment_body_length / (0.68 / 0.58)
    sleeve_reach = candidate.sleeve_length / 0.255 * 0.135
    sleeve_drop = 0.16 + (candidate.armhole_depth - 0.205) * 0.35
    opening_half = candidate.sleeve_opening_width / 0.18 * 0.03
    left = [
        (0.5 - shoulder_half + lean, top + 0.035),
        (0.5 - shoulder_half - sleeve_reach * 0.48 + lean, top + 0.135),
        (0.5 - shoulder_half - sleeve_reach + lean, top + 0.23),
        (0.5 - shoulder_half - sleeve_reach + opening_half * 2 + lean, top + 0.23 + 0.065),
        (0.5 - shoulder_half + 0.08 + lean, top + sleeve_drop),
    ]
    right = [(1.0 - x + lean * 2.0, y) for x, y in left]
    torso = [
        (0.5 - shoulder_half + lean, top),
        (0.5 + shoulder_half + lean, top),
        (0.5 + torso_half + lean, bottom),
        (0.5 - torso_half + lean, bottom),
    ]
    mask: set[int] = set()
    for y in range(height):
        ny = (y + 0.5) / height
        for x in range(width):
            nx = (x + 0.5) / width
            if any(_inside_polygon(nx, ny, poly) for poly in (torso, left, right)):
                neck_rx = candidate.neckline_width / 0.19 * 0.062
                neck_ry = candidate.front_neckline_depth / 0.085 * 0.038
                if not _ellipse(nx, ny, 0.5 + lean, top + 0.005, neck_rx, neck_ry):
                    mask.add(y * width + x)
    return mask


def _predicted_landmarks(candidate: TShirtParameters) -> dict[str, tuple[float, float]]:
    shoulder_half = candidate.shoulder_width / 2.3333333333 / 2.0
    top = 0.20
    bottom = top + candidate.garment_body_length / (0.68 / 0.58)
    sleeve_reach = candidate.sleeve_length / 0.255 * 0.135
    shoulder_y = top + 0.055
    torso_half = (candidate.half_chest_width + candidate.body_ease) / 1.8857142857
    return {
        "landmark.neck.center": (0.5, top + 0.005),
        "landmark.shoulder.left": (0.5 - shoulder_half + 0.022, shoulder_y),
        "landmark.shoulder.right": (0.5 + shoulder_half - 0.022, shoulder_y),
        "landmark.armhole.left": (0.5 - shoulder_half - 0.028, top + 0.155),
        "landmark.armhole.right": (0.5 + shoulder_half + 0.028, top + 0.155),
        "landmark.cuff.left": (0.5 - shoulder_half - sleeve_reach, top + 0.237),
        "landmark.cuff.right": (0.5 + shoulder_half + sleeve_reach, top + 0.237),
        "landmark.hem.left": (0.5 - torso_half + 0.012, bottom),
        "landmark.hem.right": (0.5 + torso_half - 0.012, bottom),
        "landmark.hem.center": (0.5, bottom + 0.00375),
    }


def _geometry_validity(candidate: TShirtParameters) -> tuple[float, float, dict[str, Any]]:
    try:
        candidate.validate()
        pattern = build_tshirt_pattern(candidate)
        mesh, edge_maps = build_simulation_mesh(pattern)
        constraints = build_constraints(pattern, edge_maps)
        finite = finite_mesh(mesh)
        triangle_count = mesh.triangle_count
        constraint_count = len(constraints.get("constraints", []))
        invalid = 0.0 if finite and triangle_count > 0 and constraint_count > 0 else 1.0
        drape = 0.0 if mesh.vertex_count >= 100 and len(pattern.get("panels", [])) == 5 else 0.5
        return (
            invalid,
            drape,
            {
                "status": "pass" if invalid == 0.0 and drape == 0.0 else "fail",
                "panelCount": len(pattern.get("panels", [])),
                "vertexCount": mesh.vertex_count,
                "triangleCount": triangle_count,
                "seamConstraintCount": constraint_count,
                "finiteMesh": finite,
            },
        )
    except (KeyError, ValueError, TypeError):
        return 1.0, 1.0, {"status": "fail", "reason": "invalid_pattern_geometry"}


def _perturbed_start(prior: TShirtParameters) -> TShirtParameters:
    values = asdict(prior)
    perturbations = {
        "garment_body_length": -0.055,
        "half_chest_width": 0.028,
        "shoulder_width": -0.045,
        "front_neckline_depth": -0.025,
        "armhole_depth": 0.028,
        "sleeve_length": -0.045,
        "sleeve_opening_width": 0.025,
        "sleeve_cap_height": -0.02,
    }
    for key, delta in perturbations.items():
        low, high = _PARAMETER_BOUNDS[key]
        values[key] = min(high, max(low, values[key] + delta))
    return TShirtParameters(**values)


def _with_parameter(candidate: TShirtParameters, parameter: str, delta: float) -> TShirtParameters:
    low, high = _PARAMETER_BOUNDS[parameter]
    value = min(high, max(low, float(getattr(candidate, parameter)) + delta))
    return replace(candidate, **{parameter: value})


def _alternatives(
    visual: Mapping[str, Any],
    fusion: Mapping[str, Any],
    final: TShirtParameters,
    prior: TShirtParameters,
) -> list[dict[str, Any]]:
    alternatives = [
        replace(final, half_chest_width=max(0.22, final.half_chest_width - 0.008)),
        replace(final, half_chest_width=min(0.38, final.half_chest_width + 0.008)),
        replace(final, garment_body_length=min(0.82, final.garment_body_length + 0.012)),
    ]
    return [
        {
            "id": f"fit.alternative.local_{index + 1}",
            "parameters": asdict(candidate),
            "objective": evaluate_candidate(visual, fusion, candidate, prior)["objective"],
            "reason": "bounded_local_ambiguity_hypothesis",
        }
        for index, candidate in enumerate(alternatives)
    ]


def _history_record(
    sequence: int,
    sweep: int,
    move: str,
    candidate: TShirtParameters,
    evaluation: Mapping[str, Any],
    accepted: bool,
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "sweep": sweep,
        "move": move,
        "parameters": asdict(candidate),
        "objective": evaluation["objective"],
        "terms": deepcopy(evaluation["terms"]),
        "accepted": accepted,
        "evaluationMode": evaluation["evaluationMode"],
        "patternValidityStatus": _mapping(evaluation.get("patternValidity")).get("status"),
    }


def _validate_evidence(
    visual_observations: Mapping[str, Any], multiview_fusion: Mapping[str, Any]
) -> None:
    labels = {str(view.get("label", "")) for view in _views(visual_observations)}
    if not {"front", "back"} <= labels:
        raise ValueError("d0_fit_requires_front_and_back_views")
    for view in _views(visual_observations):
        width, height = _dimensions(view)
        if width < 16 or height < 16 or not _target_mask(view):
            raise ValueError("d0_fit_invalid_decoded_mask_evidence")
    gate = _mapping(multiview_fusion.get("qualityGate"))
    if gate.get("status") != "passed_d0_synthetic":
        raise ValueError("d0_fit_multiview_quality_gate_failed")
    if _camera_penalty(_views(visual_observations)) >= 0.2:
        raise ValueError("d0_fit_camera_evidence_invalid")


def _rejection_control(control_id: str, operation: Any, expected_code: str) -> dict[str, Any]:
    try:
        operation()
    except ValueError as exc:
        code = str(exc)
        return {
            "controlId": control_id,
            "status": "pass_rejected",
            "observedFailureCode": code,
            "expectedFailureCode": expected_code,
            "accepted": code == expected_code,
        }
    return {
        "controlId": control_id,
        "status": "fail_not_rejected",
        "observedFailureCode": None,
        "expectedFailureCode": expected_code,
        "accepted": False,
    }


def _target_mask(view: Mapping[str, Any]) -> set[int]:
    record = _target_mask_record(view)
    rle = _mapping(record.get("rle"))
    width = int(rle.get("width", 0))
    height = int(rle.get("height", 0))
    mask: set[int] = set()
    for run in rle.get("runs", []):
        if not isinstance(run, list) or len(run) != 2:
            continue
        start, length = int(run[0]), int(run[1])
        if start < 0 or length < 0 or start + length > width * height:
            raise ValueError("d0_fit_corrupt_mask_rle")
        mask.update(range(start, start + length))
    return mask


def _target_mask_record(view: Mapping[str, Any]) -> Mapping[str, Any]:
    for mask in view.get("masks", []):
        if isinstance(mask, Mapping) and mask.get("semanticId") == "component.tshirt":
            return mask
    return {}


def _dimensions(view: Mapping[str, Any]) -> tuple[int, int]:
    dims = _mapping(_mapping(view.get("pixelEvidence")).get("decodedDimensions"))
    return int(dims.get("width", 0)), int(dims.get("height", 0))


def _views(visual: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [view for view in visual.get("views", []) if isinstance(view, Mapping)]


def _regularization(candidate: TShirtParameters, prior: TShirtParameters) -> float:
    values = asdict(candidate)
    priors = asdict(prior)
    deltas = []
    for key in _SEARCH_PARAMETERS:
        low, high = _PARAMETER_BOUNDS[key]
        deltas.append(abs(values[key] - priors[key]) / (high - low))
    return _mean(deltas)


def _seam_penalty(candidate: TShirtParameters) -> float:
    sleeve_balance = abs(candidate.sleeve_length - 1.24 * candidate.armhole_depth) / 0.38
    ease = max(0.0, 0.02 - candidate.body_ease, candidate.body_ease - 0.10) / 0.10
    cap = abs(candidate.sleeve_cap_height - candidate.armhole_depth * 0.51) / 0.17
    return min(1.0, sleeve_balance * 0.45 + ease * 0.2 + cap * 0.35)


def _camera_penalty(views: list[Mapping[str, Any]]) -> float:
    penalties = []
    expected = {
        "front": 0.0,
        "back": 180.0,
        "left_three_quarter": 62.0,
        "right_three_quarter": -62.0,
    }
    for view in views:
        camera = _mapping(view.get("camera"))
        if camera.get("projection") != "orthographic":
            penalties.append(1.0)
            continue
        try:
            azimuth = float(camera.get("azimuthDegrees", math.nan))
            elevation = float(camera.get("elevationDegrees", math.nan))
        except (TypeError, ValueError):
            penalties.append(1.0)
            continue
        if not math.isfinite(azimuth) or not math.isfinite(elevation):
            penalties.append(1.0)
            continue
        label = str(view.get("label", ""))
        penalties.append(min(1.0, abs(azimuth - expected.get(label, azimuth)) / 45.0))
    return _mean(penalties)


def _evidence_confidence(visual: Mapping[str, Any], fusion: Mapping[str, Any]) -> float:
    masks = [float(_target_mask_record(view).get("confidence", 0.0)) for view in _views(visual)]
    fused = _mapping(fusion.get("fusedEvidence"))
    confidence = _mapping(fused.get("confidence"))
    return min(1.0, (_mean(masks) + float(confidence.get("meanFusedConfidence", 0.0))) / 2)


def _boundary(mask: set[int], width: int, height: int) -> set[int]:
    boundary = set()
    for index in mask:
        x = index % width
        y = index // width
        neighbours = []
        if x > 0:
            neighbours.append(index - 1)
        if x + 1 < width:
            neighbours.append(index + 1)
        if y > 0:
            neighbours.append(index - width)
        if y + 1 < height:
            neighbours.append(index + width)
        if len(neighbours) < 4 or any(item not in mask for item in neighbours):
            boundary.add(index)
    return boundary


def _chamfer(left: set[int], right: set[int], width: int, height: int) -> float:
    if not left or not right:
        return 1.0
    diagonal = math.sqrt(width * width + height * height)

    def directed(source: set[int], target: set[int]) -> float:
        source_sample = sorted(source)[:: max(1, len(source) // 96)]
        target_points = [(item % width, item // width) for item in sorted(target)]
        distances = []
        for item in source_sample:
            x, y = item % width, item // width
            distances.append(
                math.sqrt(min((x - tx) ** 2 + (y - ty) ** 2 for tx, ty in target_points))
            )
        return _mean(distances) / diagonal

    return (directed(left, right) + directed(right, left)) / 2.0


def _iou(left: set[int], right: set[int]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _inside_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if (current[1] > y) != (previous[1] > y) and x < (
            (previous[0] - current[0]) * (y - current[1]) / (previous[1] - current[1]) + current[0]
        ):
            inside = not inside
        previous = current
    return inside


def _ellipse(x: float, y: float, cx: float, cy: float, rx: float, ry: float) -> bool:
    return ((x - cx) / max(1e-9, rx)) ** 2 + ((y - cy) / max(1e-9, ry)) ** 2 <= 1.0


def _point(value: object) -> tuple[float, float]:
    if isinstance(value, list | tuple) and len(value) >= 2:
        return float(value[0]), float(value[1])
    return (0.0, 0.0)


def _distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _mean(values: Any) -> float:
    items = list(values)
    return sum(float(value) for value in items) / max(1, len(items))


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _round(value: float) -> float:
    return round(float(value), 9)
