from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from .model import Panel, Seam, SeamSide, Vec3


@dataclass(frozen=True)
class SpanSample:
    vertex_id: str
    next_vertex_id: str
    interpolation_weight: float


@dataclass(frozen=True)
class CorrespondenceSample:
    sample_id: str
    normalized_arclength_a: float
    normalized_arclength_b: float
    side_a: SpanSample
    side_b: SpanSample


def build_correspondence(seam: Seam, panels: tuple[Panel, ...]) -> tuple[CorrespondenceSample, ...]:
    if len(seam.sides) < 2:
        raise ValueError("strategy3_seam_requires_two_sides")
    panel_map = {panel.panel_id: panel for panel in panels}
    left, right = seam.sides[:2]
    samples: list[CorrespondenceSample] = []
    for ordinal in range(seam.sample_count):
        normalized_a = ordinal / max(1, seam.sample_count - 1)
        eased = apply_ease(normalized_a, seam.ease_profile)
        normalized_b = eased if left.orientation == right.orientation else 1.0 - eased
        samples.append(
            CorrespondenceSample(
                sample_id=f"{seam.seam_id}.sample.{ordinal}",
                normalized_arclength_a=normalized_a,
                normalized_arclength_b=normalized_b,
                side_a=sample_side(left, panel_map[left.panel_id], normalized_a),
                side_b=sample_side(right, panel_map[right.panel_id], normalized_b),
            )
        )
    return tuple(samples)


def apply_ease(value: float, profile: tuple[tuple[float, float], ...]) -> float:
    _validate_ease(profile)
    bounded = max(0.0, min(1.0, value))
    for (left_x, left_y), (right_x, right_y) in zip(profile, profile[1:], strict=False):
        if bounded <= right_x:
            parameter = (bounded - left_x) / max(right_x - left_x, 1e-15)
            return left_y * (1.0 - parameter) + right_y * parameter
    return 1.0


def sample_side(side: SeamSide, panel: Panel, normalized: float) -> SpanSample:
    if len(side.vertices) < 2:
        raise ValueError("strategy3_seam_side_too_short")
    vertices = panel.vertex_map()
    lengths = [
        _distance(vertices[left].position, vertices[right].position)
        for left, right in zip(side.vertices, side.vertices[1:], strict=False)
    ]
    total = sum(lengths)
    if total <= 1e-15:
        raise ValueError("strategy3_zero_length_seam_side")
    distance = max(0.0, min(1.0, normalized)) * total
    accumulated = 0.0
    for ordinal, length in enumerate(lengths):
        last = ordinal == len(lengths) - 1
        if distance < accumulated + length or last:
            weight = (distance - accumulated) / max(length, 1e-15)
            return SpanSample(
                side.vertices[ordinal],
                side.vertices[ordinal + 1],
                max(0.0, min(1.0, weight)),
            )
        accumulated += length
    raise AssertionError("strategy3_unreachable_seam_interval")


def validate_correspondence(seam: Seam, samples: tuple[CorrespondenceSample, ...]) -> list[str]:
    issues: list[str] = []
    expected_ids = tuple(f"{seam.seam_id}.sample.{index}" for index in range(seam.sample_count))
    if tuple(sample.sample_id for sample in samples) != expected_ids:
        issues.append("semantic_sequence_incomplete_or_reordered")
    values_a = [sample.normalized_arclength_a for sample in samples]
    expected_a = [index / max(1, seam.sample_count - 1) for index in range(seam.sample_count)]
    if values_a != expected_a or any(b <= a for a, b in zip(values_a, values_a[1:], strict=False)):
        issues.append("semantic_arclength_non_monotonic")
    expected_b = [
        apply_ease(value, seam.ease_profile)
        if seam.sides[0].orientation == seam.sides[1].orientation
        else 1.0 - apply_ease(value, seam.ease_profile)
        for value in expected_a
    ]
    if [sample.normalized_arclength_b for sample in samples] != expected_b:
        issues.append("semantic_orientation_or_ease_invalid")
    for sample in samples:
        for span in (sample.side_a, sample.side_b):
            if not 0.0 <= span.interpolation_weight <= 1.0:
                issues.append("semantic_partition_weight_out_of_range")
    if len(samples) != seam.sample_count:
        issues.append("semantic_sample_count_changed")
    return sorted(set(issues))


def validate_semantic_incidence(seams: tuple[Seam, ...]) -> list[str]:
    issues: list[str] = []
    for seam in seams:
        if len(seam.sides) < 2:
            issues.append("semantic_pair_missing")
            continue
        left, right = seam.sides[:2]
        expected_right = (
            left.endpoint_classes
            if left.orientation == right.orientation
            else tuple(reversed(left.endpoint_classes))
        )
        if right.endpoint_classes != expected_right:
            issues.append("semantic_endpoint_class_mismatch")
    if len(seams) == 3:
        junctions = {seam.junction_id for seam in seams}
        if len(junctions) != 1 or None in junctions:
            issues.append("semantic_three_way_junction_incidence_invalid")
    elif any(seam.junction_id is not None for seam in seams):
        issues.append("semantic_unexpected_junction")
    return sorted(set(issues))


def semantic_mutation_report(
    seam: Seam, samples: tuple[CorrespondenceSample, ...]
) -> dict[str, bool]:
    if len(samples) < 3:
        raise ValueError("strategy3_mutation_sample_count_too_small")
    reversed_samples = tuple(reversed(samples))
    duplicated = (*samples, samples[-1])
    dropped = samples[:-1]
    nonmonotonic = list(samples)
    nonmonotonic[1], nonmonotonic[2] = nonmonotonic[2], nonmonotonic[1]
    wrong_orientation = tuple(
        CorrespondenceSample(
            row.sample_id,
            row.normalized_arclength_a,
            1.0 - row.normalized_arclength_b,
            row.side_a,
            row.side_b,
        )
        for row in samples
    )
    bad_partition = tuple(
        [
            *samples[:-1],
            CorrespondenceSample(
                samples[-1].sample_id,
                samples[-1].normalized_arclength_a,
                samples[-1].normalized_arclength_b,
                samples[-1].side_a,
                SpanSample(
                    samples[-1].side_b.vertex_id,
                    samples[-1].side_b.next_vertex_id,
                    1.25,
                ),
            ),
        ]
    )
    return {
        "reversed": bool(validate_correspondence(seam, reversed_samples)),
        "duplicated": bool(validate_correspondence(seam, tuple(duplicated))),
        "dropped": bool(validate_correspondence(seam, dropped)),
        "nonMonotonic": bool(validate_correspondence(seam, tuple(nonmonotonic))),
        "wrongOrientation": bool(validate_correspondence(seam, wrong_orientation)),
        "nonPartitioning": bool(validate_correspondence(seam, bad_partition)),
    }


def _validate_ease(profile: tuple[tuple[float, float], ...]) -> None:
    if len(profile) < 2 or profile[0] != (0.0, 0.0) or profile[-1] != (1.0, 1.0):
        raise ValueError("strategy3_ease_endpoints_invalid")
    if any(
        right_x <= left_x or right_y < left_y
        for (left_x, left_y), (right_x, right_y) in zip(profile, profile[1:], strict=False)
    ):
        raise ValueError("strategy3_ease_not_monotone")


def _distance(left: Vec3, right: Vec3) -> float:
    return sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))
