from __future__ import annotations

import math
from collections.abc import Mapping
from io import BytesIO
from typing import Any

from PIL import Image

from closy_forge.disjoint_benchmark_v1.compiler import compile_structural_candidate
from closy_forge.disjoint_benchmark_v1.protocol import (
    OBSERVABLE_PARAMETERS,
    PARAMETER_RANGES,
)

from .corpus import render_tshirt_capture
from .model import predict_structured
from .observation import ObservationRejected, apply_crop_and_padding, extract_observation

FITTING_VERSION = "closy.d0_v4.bounded_source_conditioned_fit.v1"


def infer_hybrid(
    model: Mapping[str, Any],
    front_png: bytes,
    rear_png: bytes | None,
    *,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        observation = extract_observation(front_png, rear_png, metadata=metadata)
    except ObservationRejected as exc:
        return _rejection(f"observation_rejected:{exc}")
    learned = predict_structured(model, observation)
    if learned.get("status") != "predicted":
        return _rejection("learned_initialization_rejected")
    try:
        fitted = fit_source_conditioned(
            _mapping(learned["parameters"]),
            front_png,
            rear_png,
            metadata=metadata,
        )
        selected_parameters, compiled, compile_selection = _select_compile_valid_hypothesis(
            _mapping(fitted["parameters"]), _mapping(learned["parameters"])
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return _rejection(f"bounded_fit_or_compile_rejected:{type(exc).__name__}:{exc}")
    report = compiled.report
    if (
        report.get("finite") is not True
        or report.get("bindingStatus") != "pass"
        or report.get("seamStatus") != "pass"
    ):
        return _rejection("canonical_compiler_validation_failed")
    return {
        "status": "predicted",
        "parameters": selected_parameters,
        "learnedInitialization": learned["parameters"],
        "rawLogits": learned["rawLogits"],
        "constraintSaturation": learned["constraintSaturation"],
        "uncertainty95": learned["uncertainty95"],
        "alternatives": learned["alternatives"],
        "confidence": learned["confidence"],
        "fit": {**fitted, "compileSelection": compile_selection},
        "compile": report,
        "evidenceClass": "learned_initialization_plus_bounded_source_pixel_refinement",
        "targetParametersRead": False,
        "fittingVersion": FITTING_VERSION,
        "observationRoute": observation["route"],
        "frontOnlyUnobservedParameters": (
            ["back_neckline_depth"] if observation["route"] == "front_only_bounded" else []
        ),
    }


def fit_source_conditioned(
    initialization: Mapping[str, Any],
    front_png: bytes,
    rear_png: bytes | None,
    *,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    learned_parameters = {
        name: _clamp(float(initialization[name]), *PARAMETER_RANGES[name])
        for name in OBSERVABLE_PARAMETERS
    }
    parameters = {name: value for name, value in learned_parameters.items()}
    parameters.update(_fixed_parameters())
    parameters.update(_landmark_initialization(front_png, rear_png, metadata))
    sources = [("front", front_png)]
    if rear_png is not None:
        sources.append(("rear", rear_png))
    source_masks = {role: _foreground_mask(png) for role, png in sources}
    renderer_families = {role: _observable_renderer_family(png) for role, png in sources}
    initial_score = _fit_score(parameters, source_masks, metadata, renderer_families)
    joint = _fit_shoulder_and_sleeve(
        parameters,
        learned_parameters,
        source_masks,
        metadata,
        renderer_families,
        initial_score=initial_score,
    )
    parameters.update(joint["parameters"])
    current_score = float(joint["score"])
    evaluations = 1 + int(joint["candidateEvaluationCount"])
    trace: list[dict[str, Any]] = [
        {
            "pass": "joint_shoulder_sleeve",
            "score": round(current_score, 9),
            "selectedNormalized": joint["selectedNormalized"],
            "nearOptimalBand": 0.003,
            "selectionPolicy": joint["selectionPolicy"],
        }
    ]
    refined_parameters = (
        "half_chest_width",
        "body_ease",
        "neckline_width",
        "front_neckline_depth",
        "back_neckline_depth",
    )
    for pass_index in range(2):
        for name in refined_parameters:
            low, high = PARAMETER_RANGES[name]
            current_normalized = (parameters[name] - low) / (high - low)
            deltas = (
                (-0.20, -0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15, 0.20)
                if pass_index == 0
                else (-0.10, -0.05, -0.025, 0.0, 0.025, 0.05, 0.10)
            )
            candidates = [_clamp(current_normalized + delta, 0.0, 1.0) for delta in deltas]
            ranked: list[tuple[float, float, float]] = []
            for normalized in sorted(set(candidates)):
                proposal = dict(parameters)
                proposal[name] = low + (high - low) * normalized
                score = _fit_score(proposal, source_masks, metadata, renderer_families)
                evaluations += 1
                ranked.append((score, -abs(normalized - current_normalized), normalized))
            best_score, _, best_normalized = max(ranked)
            parameters[name] = low + (high - low) * best_normalized
            current_score = best_score
            trace.append(
                {
                    "pass": pass_index,
                    "parameter": name,
                    "selectedNormalized": round(best_normalized, 9),
                    "score": round(best_score, 9),
                }
            )
    parameters = {name: round(float(value), 9) for name, value in parameters.items()}
    return {
        "fittingVersion": FITTING_VERSION,
        "parameters": parameters,
        "initialSilhouetteObjective": round(initial_score, 9),
        "finalSilhouetteObjective": round(current_score, 9),
        "objectiveNonDecreasing": current_score + 1e-12 >= initial_score,
        "objectiveWithinPlateauTolerance": current_score + 0.003 + 1e-12 >= initial_score,
        "objectiveDelta": round(current_score - initial_score, 9),
        "boundedIterationCount": 2,
        "refinedParameters": list(refined_parameters),
        "candidateEvaluationCount": evaluations,
        "targetAccessed": False,
        "trace": trace,
    }


def _fit_shoulder_and_sleeve(
    parameters: Mapping[str, Any],
    learned_parameters: Mapping[str, Any],
    source_masks: Mapping[str, set[int]],
    metadata: Mapping[str, Any],
    renderer_families: Mapping[str, str],
    *,
    initial_score: float,
) -> dict[str, Any]:
    shoulder_low, shoulder_high = PARAMETER_RANGES["shoulder_width"]
    sleeve_low, sleeve_high = PARAMETER_RANGES["sleeve_length"]
    source_prior = (
        (float(parameters["shoulder_width"]) - shoulder_low) / (shoulder_high - shoulder_low),
        (float(parameters["sleeve_length"]) - sleeve_low) / (sleeve_high - sleeve_low),
    )
    learned_prior = (
        (float(learned_parameters["shoulder_width"]) - shoulder_low)
        / (shoulder_high - shoulder_low),
        (float(learned_parameters["sleeve_length"]) - sleeve_low) / (sleeve_high - sleeve_low),
    )
    candidates: list[tuple[float, float, float, float]] = []
    for shoulder_index in range(11):
        for sleeve_index in range(11):
            shoulder_normalized = shoulder_index / 10.0
            sleeve_normalized = sleeve_index / 10.0
            proposal = dict(parameters)
            proposal["shoulder_width"] = (
                shoulder_low + (shoulder_high - shoulder_low) * shoulder_normalized
            )
            proposal["sleeve_length"] = sleeve_low + (sleeve_high - sleeve_low) * sleeve_normalized
            score = _fit_score(proposal, source_masks, metadata, renderer_families)
            prior_distance = 0.6 * (
                abs(shoulder_normalized - source_prior[0])
                + abs(sleeve_normalized - source_prior[1])
            ) + 0.4 * (
                abs(shoulder_normalized - learned_prior[0])
                + abs(sleeve_normalized - learned_prior[1])
            )
            candidates.append((score, prior_distance, shoulder_normalized, sleeve_normalized))
    maximum_score = max(score for score, _, _, _ in candidates)
    near_optimal = [candidate for candidate in candidates if candidate[0] >= maximum_score - 0.003]
    best_silhouette = min(
        near_optimal,
        key=lambda item: (-item[0], item[1], item[2], item[3]),
    )
    # Shoulder width and sleeve length trade almost perfectly at a fixed outer-arm span.
    # Blend independent pixel evidence instead of letting one rasterized edge choose an extreme.
    selected_normalized = (
        _clamp(
            0.45 * best_silhouette[2] + 0.45 * source_prior[0] + 0.10 * learned_prior[0],
            0.0,
            1.0,
        ),
        _clamp(
            0.45 * best_silhouette[3] + 0.45 * source_prior[1] + 0.10 * learned_prior[1],
            0.0,
            1.0,
        ),
    )
    selected_parameters = dict(parameters)
    selected_parameters["shoulder_width"] = (
        shoulder_low + (shoulder_high - shoulder_low) * selected_normalized[0]
    )
    selected_parameters["sleeve_length"] = (
        sleeve_low + (sleeve_high - sleeve_low) * selected_normalized[1]
    )
    selected_score = _fit_score(selected_parameters, source_masks, metadata, renderer_families)
    return {
        "parameters": {
            "shoulder_width": round(selected_parameters["shoulder_width"], 9),
            "sleeve_length": round(selected_parameters["sleeve_length"], 9),
        },
        "score": selected_score,
        "selectedNormalized": {
            "shoulder_width": round(selected_normalized[0], 9),
            "sleeve_length": round(selected_normalized[1], 9),
        },
        "candidateEvaluationCount": len(candidates) + 1,
        "selectionPolicy": "silhouette_45_contour_45_learned_10_bounded_blend",
    }


def hybrid_for_record(model: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    front = record.get("frontPng")
    rear = record.get("rearPng")
    if not isinstance(front, bytes) or (rear is not None and not isinstance(rear, bytes)):
        raise ValueError("d0_v4_record_capture_bytes_missing")
    capture = _mapping(record.get("capture"))
    metadata = {
        "front": {
            "camera": _mapping(capture.get("frontCamera")),
            "observationToOriginalTransform": capture.get("frontTransform"),
        },
        "rear": {
            "camera": _mapping(capture.get("rearCamera")),
            "observationToOriginalTransform": capture.get("rearTransform"),
        },
    }
    return infer_hybrid(model, front, rear, metadata=metadata)


def _select_compile_valid_hypothesis(
    fitted: Mapping[str, Any], learned: Mapping[str, Any]
) -> tuple[dict[str, float], Any, dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for edge_length in (0.075, 0.070, 0.065, 0.060, 0.055):
        parameters = {name: round(float(fitted[name]), 9) for name in OBSERVABLE_PARAMETERS}
        parameters.update(_fixed_parameters())
        parameters["target_panel_edge_length"] = edge_length
        try:
            compiled = compile_structural_candidate(parameters)
        except ValueError as exc:
            failures.append(
                {
                    "fittedWeight": 1.0,
                    "targetPanelEdgeLength": edge_length,
                    "reason": f"{type(exc).__name__}:{exc}",
                }
            )
            continue
        return (
            parameters,
            compiled,
            {
                "status": "compile_valid",
                "selectedFittedWeight": 1.0,
                "selectedTargetPanelEdgeLength": edge_length,
                "failedHypotheses": failures,
                "silentDefaultUsed": False,
            },
        )
    # Repair a compiler-quality boundary with the smallest source-only normalized move.
    # This search never observes target parameters and is deterministic under ties.
    for normalized_delta in (0.01, 0.02, 0.03, 0.04, 0.05, 0.075, 0.10, 0.15, 0.20):
        for name in OBSERVABLE_PARAMETERS:
            low, high = PARAMETER_RANGES[name]
            current = (float(fitted[name]) - low) / (high - low)
            for direction in (-1.0, 1.0):
                repaired = _clamp(current + direction * normalized_delta, 0.0, 1.0)
                if repaired == current:
                    continue
                parameters = {
                    parameter: round(float(fitted[parameter]), 9)
                    for parameter in OBSERVABLE_PARAMETERS
                }
                parameters[name] = round(low + (high - low) * repaired, 9)
                parameters.update(_fixed_parameters())
                try:
                    compiled = compile_structural_candidate(parameters)
                except ValueError as exc:
                    failures.append(
                        {
                            "repairParameter": name,
                            "normalizedDelta": direction * normalized_delta,
                            "reason": f"{type(exc).__name__}:{exc}",
                        }
                    )
                    continue
                return (
                    parameters,
                    compiled,
                    {
                        "status": "compile_valid_local_repair",
                        "repairParameter": name,
                        "normalizedDelta": direction * normalized_delta,
                        "failedHypotheses": failures,
                        "silentDefaultUsed": False,
                    },
                )
    for fitted_weight in (1.0, 0.85, 0.70, 0.55, 0.40, 0.25, 0.0):
        parameters = {
            name: round(
                float(fitted[name]) * fitted_weight + float(learned[name]) * (1.0 - fitted_weight),
                9,
            )
            for name in OBSERVABLE_PARAMETERS
        }
        parameters.update(_fixed_parameters())
        try:
            compiled = compile_structural_candidate(parameters)
        except ValueError as exc:
            failures.append(
                {
                    "fittedWeight": fitted_weight,
                    "reason": f"{type(exc).__name__}:{exc}",
                }
            )
            continue
        return (
            parameters,
            compiled,
            {
                "status": "compile_valid",
                "selectedFittedWeight": fitted_weight,
                "selectedTargetPanelEdgeLength": parameters["target_panel_edge_length"],
                "failedHypotheses": failures,
                "silentDefaultUsed": False,
            },
        )
    raise ValueError("all_source_conditioned_and_learned_hypotheses_compile_invalid")


def _fit_score(
    parameters: Mapping[str, Any],
    source_masks: Mapping[str, set[int]],
    metadata: Mapping[str, Any],
    renderer_families: Mapping[str, str],
) -> float:
    scores: list[float] = []
    for role, source_mask in source_masks.items():
        view = _mapping(metadata.get(role))
        variation = _variation_from_metadata(view)
        background = _background_from_mask_context(view)
        rendered = render_tshirt_capture(
            parameters,
            {
                "baseColorSrgb": [42, 96, 155],
                "logoShape": "none",
                "logoColorSrgb": [238, 231, 214],
                "logoCenterNormalized": [0.5, 0.5],
                "logoScaleNormalized": 0.1,
            },
            background=background,
            variation=variation,
            role=role,
            renderer_family=renderer_families[role],
        )
        transform = _mapping(view.get("observationToOriginalTransform"))
        crop_box = transform.get("cropBoxPixels", [0, 0, 128, 160])
        padding = transform.get("paddingPixels", [0, 0])
        crop_fraction = float(crop_box[0]) / 128.0
        cropped_width = max(1, int(crop_box[2]) - int(crop_box[0]))
        padding_fraction = float(padding[0]) / cropped_width
        rendered, _ = apply_crop_and_padding(
            rendered,
            crop_fraction=crop_fraction,
            padding_fraction=padding_fraction,
            background_rgb=background,
        )
        candidate_mask = _foreground_mask(rendered)
        intersection = len(source_mask & candidate_mask)
        union = len(source_mask | candidate_mask)
        scores.append(intersection / max(1, union))
    return math.fsum(scores) / len(scores)


def _variation_from_metadata(view: Mapping[str, Any]) -> dict[str, Any]:
    camera = _mapping(view.get("camera"))
    principal = camera.get("principalPointNormalized", [0.5, 0.5])
    scale = 1.12 / max(1e-6, float(camera.get("orthographicScale", 1.12)))
    return {
        "scale": scale,
        "translation": [
            round((float(principal[0]) - 0.5) * 128.0),
            round((float(principal[1]) - 0.5) * 160.0),
        ],
        "lighting": 1.0,
        "cropFraction": 0.0,
        "paddingFraction": 0.0,
        "occlusionFraction": 0.0,
        "rearMissing": False,
    }


def _background_from_mask_context(view: Mapping[str, Any]) -> tuple[int, int, int]:
    del view
    return (236, 234, 228)


def _foreground_mask(png: bytes) -> set[int]:
    with Image.open(BytesIO(png)) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        pixels = list(rgba.getdata())
    corners = [pixels[0], pixels[width - 1], pixels[(height - 1) * width], pixels[-1]]
    background = tuple(
        round(math.fsum(pixel[channel] for pixel in corners) / 4.0) for channel in range(3)
    )
    return {
        index
        for index, pixel in enumerate(pixels)
        if max(abs(pixel[channel] - background[channel]) for channel in range(3)) >= 24
    }


def _observable_renderer_family(png: bytes) -> str:
    with Image.open(BytesIO(png)) as image:
        colours = image.convert("RGB").getcolors(maxcolors=image.width * image.height)
    colour_count = len(colours) if colours is not None else 257
    return "supersampled_antialias_v1" if colour_count > 24 else "polygon_scanline_v1"


def _landmark_initialization(
    front_png: bytes,
    rear_png: bytes | None,
    metadata: Mapping[str, Any],
) -> dict[str, float]:
    front = _contour_landmarks(front_png, _mapping(metadata.get("front")))
    result = {
        "garment_body_length": _parameter_from_linear(
            "garment_body_length", front["bodyLength"], 72.0, 30.0
        ),
        "half_chest_width": _parameter_from_linear(
            "half_chest_width", front["chestHalfWidth"], 18.0, 8.0
        ),
        "shoulder_width": _parameter_from_linear(
            "shoulder_width", front["shoulderHalfWidth"], 22.0, 7.0
        ),
        "shoulder_slope": _parameter_from_linear(
            "shoulder_slope", front["shoulderSlope"], 1.5, 7.0
        ),
        "neckline_width": _parameter_from_linear(
            "neckline_width", front["neckHalfWidth"], 7.0, 9.0
        ),
        "front_neckline_depth": _parameter_from_linear(
            "front_neckline_depth", front["neckDepth"], 4.0, 11.0
        ),
        "sleeve_length": _parameter_from_linear("sleeve_length", front["sleeveReach"], 10.0, 18.0),
        "sleeve_opening_width": _parameter_from_linear(
            "sleeve_opening_width", front["cuffDepth"], 5.0, 9.0
        ),
        "armhole_depth": _parameter_from_linear("armhole_depth", front["armholeDepth"], 15.0, 15.0),
    }
    hem_extra = max(1.0, front["hemHalfWidth"] - front["chestHalfWidth"])
    result["body_ease"] = _parameter_from_linear("body_ease", hem_extra, 1.0, 7.0)
    if rear_png is not None:
        rear = _contour_landmarks(rear_png, _mapping(metadata.get("rear")))
        result["back_neckline_depth"] = _parameter_from_linear(
            "back_neckline_depth", rear["neckDepth"], 4.0, 11.0
        )
        rear_neck = _parameter_from_linear("neckline_width", rear["neckHalfWidth"], 7.0, 9.0)
        result["neckline_width"] = round((result["neckline_width"] + rear_neck) / 2.0, 9)
    return result


def _contour_landmarks(png: bytes, view: Mapping[str, Any]) -> dict[str, float]:
    with Image.open(BytesIO(png)) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        pixels = list(rgba.getdata())
    corners = [pixels[0], pixels[width - 1], pixels[(height - 1) * width], pixels[-1]]
    background = tuple(
        round(math.fsum(pixel[channel] for pixel in corners) / 4.0) for channel in range(3)
    )
    maximum_contrast = max(
        max(abs(pixel[channel] - background[channel]) for channel in range(3)) for pixel in pixels
    )
    contour_threshold = max(24.0, min(96.0, maximum_contrast * 0.45))
    transform = _mapping(view.get("observationToOriginalTransform"))
    affine = transform.get(
        "outputToOriginalAffine3x3",
        [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
    )
    offset_x = float(affine[2])
    offset_y = float(affine[5])
    rows: dict[int, list[float]] = {}
    high_confidence_rows: dict[int, list[float]] = {}
    for index, pixel in enumerate(pixels):
        distance = max(abs(pixel[channel] - background[channel]) for channel in range(3))
        if distance < 24:
            continue
        y = round(index // width + offset_y)
        x = index % width + offset_x
        rows.setdefault(y, []).append(x)
        if distance >= contour_threshold:
            high_confidence_rows.setdefault(y, []).append(x)
    if not rows or not high_confidence_rows:
        raise ValueError("d0_v4_contour_empty")
    camera = _mapping(view.get("camera"))
    principal = camera.get("principalPointNormalized", [0.5, 0.5])
    center = float(principal[0]) * 128.0
    translation_y = (float(principal[1]) - 0.5) * 160.0
    top = 24.0 + translation_y
    scale = 1.12 / max(1e-6, float(camera.get("orthographicScale", 1.12)))
    first_y = min(y for y, xs in rows.items() if len(xs) >= 2)
    last_y = max(rows)
    left_by_y = {y: min(xs) for y, xs in rows.items()}
    right_by_y = {y: max(xs) for y, xs in rows.items()}
    high_left_by_y = {y: min(xs) for y, xs in high_confidence_rows.items()}
    outer_left = min(left_by_y.values())
    sleeve_y = min(y for y, value in left_by_y.items() if value == outer_left)
    high_outer_left = min(high_left_by_y.values())
    high_sleeve_y = min(y for y, value in high_left_by_y.items() if value == high_outer_left)
    # The supersampled family has a valid low-contrast first row. Taking a later
    # high-confidence row aliases shoulder width into sleeve slope by several pixels.
    shoulder_left = left_by_y[first_y]
    selected_outer_left = outer_left
    torso_rows = [y for y in left_by_y if sleeve_y <= y <= first_y + 70]
    torso_left = max(left_by_y[y] for y in torso_rows)
    body_start_y = min(y for y in torso_rows if left_by_y[y] == torso_left)
    chest_half = (center - torso_left) / scale
    hem_half = ((center - left_by_y[last_y]) + (right_by_y[last_y] - center)) / (2.0 * scale)
    neck_gaps: list[tuple[float, int]] = []
    gap_started = False
    for y in range(first_y, min(last_y, first_y + 30) + 1):
        xs = rows.get(y, [])
        left = max((x for x in xs if x < center), default=center)
        right = min((x for x in xs if x > center), default=center)
        if left < center < right and right - left > 2.0:
            neck_gaps.append((right - left - 1.0, y))
            gap_started = True
        elif gap_started:
            break
    widest_gap = max((gap for gap, _ in neck_gaps), default=0.0)
    deepest_neck = max((y for _, y in neck_gaps), default=round(top + 4.0 * scale))
    return {
        "bodyLength": (last_y - top) / scale,
        "chestHalfWidth": chest_half,
        "hemHalfWidth": hem_half,
        "shoulderHalfWidth": (center - shoulder_left) / scale,
        "shoulderSlope": (first_y - top) / scale,
        "neckHalfWidth": max(0.0, (widest_gap - 1.0) / (2.0 * scale)),
        "neckDepth": (deepest_neck - first_y) / scale,
        "sleeveReach": (shoulder_left - selected_outer_left) / scale,
        "cuffDepth": (high_sleeve_y - first_y) / scale,
        "armholeDepth": (body_start_y - first_y) / scale,
    }


def _parameter_from_linear(name: str, measured: float, base: float, span: float) -> float:
    low, high = PARAMETER_RANGES[name]
    normalized = _clamp((measured - base) / span, 0.0, 1.0)
    return round(low + (high - low) * normalized, 9)


def _fixed_parameters() -> dict[str, float]:
    return {
        "sleeve_cap_height": 0.105,
        "hem_allowance": 0.025,
        "neckband_width": 0.035,
        "neckband_length_ease_ratio": 0.92,
        "target_panel_edge_length": 0.075,
    }


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _rejection(reason: str) -> dict[str, Any]:
    return {
        "status": "rejected",
        "reason": reason,
        "parameters": None,
        "targetParametersRead": False,
        "fittingVersion": FITTING_VERSION,
    }


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
