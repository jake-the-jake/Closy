from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from closy_forge.raster import DecodedPng

from .protocol import PARAMETER_RANGES

OBSERVABLE_METRICS: tuple[str, ...] = (
    "garment_body_length",
    "effective_half_chest_width",
    "shoulder_width",
    "shoulder_slope",
    "neckline_width",
    "front_neckline_depth",
    "back_neckline_depth",
    "armhole_depth",
    "sleeve_length",
    "sleeve_opening_width",
)


def observable_parameter_errors(
    prediction: Mapping[str, Any], target: Mapping[str, Any]
) -> dict[str, Any]:
    values: dict[str, float] = {}
    for name in OBSERVABLE_METRICS:
        if name == "effective_half_chest_width":
            predicted = float(prediction["half_chest_width"]) + float(prediction["body_ease"])
            expected = float(target["half_chest_width"]) + float(target["body_ease"])
            span = (
                PARAMETER_RANGES["half_chest_width"][1]
                - PARAMETER_RANGES["half_chest_width"][0]
                + PARAMETER_RANGES["body_ease"][1]
                - PARAMETER_RANGES["body_ease"][0]
            )
        else:
            predicted = float(prediction[name])
            expected = float(target[name])
            span = PARAMETER_RANGES[name][1] - PARAMETER_RANGES[name][0]
        values[name] = round(abs(predicted - expected) / span, 9)
    return {
        "byParameter": values,
        "macroNormalizedError": round(math.fsum(values.values()) / len(values), 9),
        "worstNormalizedError": max(values.values()),
    }


def compare_rasters(candidate: DecodedPng, target: DecodedPng) -> dict[str, Any]:
    if candidate.width != target.width or candidate.height != target.height:
        raise ValueError("d0_disjoint_raster_size_mismatch")
    background = (236, 234, 228)
    candidate_mask: set[int] = set()
    target_mask: set[int] = set()
    colour_errors: list[float] = []
    for index in range(candidate.width * candidate.height):
        c = tuple(candidate.rgba[index * 4 : index * 4 + 3])
        t = tuple(target.rgba[index * 4 : index * 4 + 3])
        if c != background:
            candidate_mask.add(index)
        if t != background:
            target_mask.add(index)
        if index in target_mask:
            colour_errors.append(sum(abs(a - b) for a, b in zip(c, t, strict=True)) / (3 * 255))
    union = candidate_mask | target_mask
    intersection = candidate_mask & target_mask
    return {
        "silhouetteIoU": round(len(intersection) / max(1, len(union)), 9),
        "foregroundSrgbMae": round(math.fsum(colour_errors) / max(1, len(colour_errors)), 9),
        "candidateForegroundPixels": len(candidate_mask),
        "targetForegroundPixels": len(target_mask),
        "blank": not candidate_mask,
    }


def appearance_predicates(
    candidate: DecodedPng,
    target: DecodedPng,
    appearance: Mapping[str, Any],
) -> dict[str, Any]:
    comparison = compare_rasters(candidate, target)
    logo_values = appearance["logoColorSrgb"]
    logo_colour = (int(logo_values[0]), int(logo_values[1]), int(logo_values[2]))
    candidate_logo = _colour_pixels(candidate, logo_colour)
    target_logo = _colour_pixels(target, logo_colour)
    logo_present = appearance["logoShape"] != "none"
    if logo_present:
        union = candidate_logo | target_logo
        logo_iou = len(candidate_logo & target_logo) / max(1, len(union))
        displacement = math.dist(
            _centroid(candidate_logo, candidate.width), _centroid(target_logo, target.width)
        ) / math.hypot(target.width, target.height)
        logo_pass = logo_iou >= 0.02 and displacement <= 0.14
        false_positive = None
    else:
        logo_iou = None
        displacement = None
        false_positive = len(candidate_logo) / max(1, candidate.width * candidate.height)
        logo_pass = false_positive <= 0.002
    predicates = {
        "nonBlank": not comparison["blank"],
        "silhouetteIoU": comparison["silhouetteIoU"] >= 0.30,
        "foregroundColourMae": comparison["foregroundSrgbMae"] <= 0.12,
        "logoPredicate": logo_pass,
        "sourceContributionCloses": True,
    }
    return {
        **comparison,
        "logoPresent": logo_present,
        "logoIoU": None if logo_iou is None else round(logo_iou, 9),
        "logoDisplacementNormalized": None if displacement is None else round(displacement, 9),
        "logoFalsePositiveFraction": None if false_positive is None else round(false_positive, 9),
        "sourceObservedFraction": 1.0,
        "generatedControlledFillFraction": 0.0,
        "predicates": predicates,
        "status": "pass" if all(predicates.values()) else "fail",
    }


def paired_bootstrap(
    primary: Sequence[float],
    baseline: Sequence[float],
    *,
    lower_is_better: bool,
    seed: int,
    resamples: int = 10_000,
) -> dict[str, float | int]:
    if len(primary) != len(baseline) or not primary:
        raise ValueError("d0_disjoint_bootstrap_inventory_invalid")
    rng = random.Random(seed)
    differences: list[float] = []
    for _ in range(resamples):
        indices = [rng.randrange(len(primary)) for _ in primary]
        p = math.fsum(primary[index] for index in indices) / len(indices)
        b = math.fsum(baseline[index] for index in indices) / len(indices)
        differences.append((b - p) if lower_is_better else (p - b))
    differences.sort()
    return {
        "resamples": resamples,
        "seed": seed,
        "meanImprovement": round(math.fsum(differences) / resamples, 9),
        "lower95": round(differences[int(resamples * 0.025)], 9),
        "upper95": round(differences[min(resamples - 1, int(resamples * 0.975))], 9),
    }


def mode_colour(image: DecodedPng) -> list[int]:
    ignored = {(236, 234, 228), (238, 231, 214), (188, 184, 177)}
    colours = Counter(
        tuple(image.rgba[index : index + 3])
        for index in range(0, len(image.rgba), 4)
        if tuple(image.rgba[index : index + 3]) not in ignored
    )
    return list(colours.most_common(1)[0][0]) if colours else [128, 128, 128]


def _colour_pixels(image: DecodedPng, colour: tuple[int, int, int]) -> set[int]:
    return {
        index
        for index in range(image.width * image.height)
        if tuple(image.rgba[index * 4 : index * 4 + 3]) == colour
    }


def _centroid(pixels: set[int], width: int) -> tuple[float, float]:
    if not pixels:
        return (0.0, 0.0)
    return (
        math.fsum(index % width for index in pixels) / len(pixels),
        math.fsum(index // width for index in pixels) / len(pixels),
    )
