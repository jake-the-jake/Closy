from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import audit_glb
from closy_forge.package_io.canonical_json import read_json

Vec3 = tuple[float, float, float]
Triangle = tuple[int, int, int]


def validate_frames(frames: Sequence[Mapping[str, Any]]) -> list[str]:
    issues: list[str] = []
    for ordinal, frame in enumerate(frames):
        normal = _vec3(frame.get("normal"))
        tangent = _vec3(frame.get("tangent"))
        handedness = frame.get("handedness")
        if not all(math.isfinite(value) for value in (*normal, *tangent)):
            issues.append(f"c3_frame_nonfinite:{ordinal}")
            continue
        if abs(_length(normal) - 1.0) > 1e-6:
            issues.append(f"c3_normal_not_unit:{ordinal}")
        if abs(_length(tangent) - 1.0) > 1e-6:
            issues.append(f"c3_tangent_not_unit:{ordinal}")
        if abs(_dot(normal, tangent)) > 1e-6:
            issues.append(f"c3_frame_not_orthogonal:{ordinal}")
        if handedness not in {-1, 1}:
            issues.append(f"c3_tangent_handedness_invalid:{ordinal}")
    return issues


def indexed_components(vertex_count: int, triangles: Sequence[Triangle]) -> list[list[int]]:
    adjacency: dict[int, set[int]] = {index: set() for index in range(vertex_count)}
    for triangle in triangles:
        if len(set(triangle)) != 3 or any(index < 0 or index >= vertex_count for index in triangle):
            raise ValueError("c3_triangle_invalid")
        for left, right in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        ):
            adjacency[left].add(right)
            adjacency[right].add(left)
    components: list[list[int]] = []
    unseen = set(range(vertex_count))
    while unseen:
        seed = min(unseen)
        stack = [seed]
        component: list[int] = []
        unseen.remove(seed)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbour in sorted(adjacency[current]):
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    stack.append(neighbour)
        components.append(sorted(component))
    return components


def semantic_components(
    vertex_count: int,
    triangles: Sequence[Triangle],
    ancestry_ids: Sequence[str],
) -> list[list[str]]:
    if len(ancestry_ids) != vertex_count or any(not value for value in ancestry_ids):
        raise ValueError("c3_stable_ancestry_incomplete")
    graph: dict[str, set[str]] = {value: set() for value in ancestry_ids}
    for indexed_component in indexed_components(vertex_count, triangles):
        identities = sorted({ancestry_ids[index] for index in indexed_component})
        for left in identities:
            graph[left].update(value for value in identities if value != left)
    result: list[list[str]] = []
    unseen = set(graph)
    while unseen:
        seed = min(unseen)
        stack = [seed]
        unseen.remove(seed)
        semantic_component: list[str] = []
        while stack:
            current = stack.pop()
            semantic_component.append(current)
            for neighbour in sorted(graph[current]):
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    stack.append(neighbour)
        result.append(sorted(semantic_component))
    return result


def boundary_cycles(
    triangles: Sequence[Triangle], semantic_labels: Mapping[str, Sequence[int]]
) -> dict[str, list[int]]:
    edge_counts: dict[tuple[int, int], int] = {}
    for triangle in triangles:
        for left, right in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        ):
            edge = (min(left, right), max(left, right))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    boundary = {edge for edge, count in edge_counts.items() if count == 1}
    result: dict[str, list[int]] = {}
    for label, declared_vertices in semantic_labels.items():
        allowed = set(declared_vertices)
        edges = [edge for edge in boundary if set(edge) <= allowed]
        adjacency: dict[int, list[int]] = {vertex: [] for vertex in allowed}
        for left, right in edges:
            adjacency[left].append(right)
            adjacency[right].append(left)
        if not adjacency or any(len(neighbours) != 2 for neighbours in adjacency.values()):
            raise ValueError(f"c3_opening_not_simple_cycle:{label}")
        start = min(adjacency)
        cycle = [start]
        previous = -1
        current = start
        while True:
            next_values = sorted(value for value in adjacency[current] if value != previous)
            next_vertex = next_values[0]
            if next_vertex == start:
                break
            if next_vertex in cycle:
                raise ValueError(f"c3_opening_cycle_repeats:{label}")
            cycle.append(next_vertex)
            previous, current = current, next_vertex
        if len(cycle) != len(allowed):
            raise ValueError(f"c3_opening_cycle_incomplete:{label}")
        result[label] = cycle
    return result


def rest_relative_inversions(
    rest_positions: Sequence[Vec3],
    current_positions: Sequence[Vec3],
    triangles: Sequence[Triangle],
) -> int:
    if len(rest_positions) != len(current_positions):
        raise ValueError("c3_position_denominator_mismatch")
    count = 0
    for triangle in triangles:
        rest = _normal(rest_positions, triangle)
        current = _normal(current_positions, triangle)
        if _length(rest) <= 1e-15 or _length(current) <= 1e-15 or _dot(rest, current) <= 0.0:
            count += 1
    return count


def audit_persisted_glb(path: Path) -> dict[str, Any]:
    audit = audit_glb(path)
    semantic_types = _mapping(audit.get("semanticAccessorTypes"))
    return {
        "primitiveCount": audit.get("primitiveCount"),
        "normalPersisted": semantic_types.get("NORMAL") == ["VEC3"],
        "tangentPersisted": semantic_types.get("TANGENT") == ["VEC4"],
        "semanticAccessorTypes": semantic_types,
    }


def build_historical_v5_scope(root: Path) -> dict[str, Any]:
    outcome_path = root / "docs/evidence/d0_strict_c3_confirmation_v5/outcome_report.json"
    outcome = read_json(outcome_path)
    if not isinstance(outcome, Mapping):
        raise ValueError("c3_v5_outcome_mapping_required")
    aggregate = _mapping(outcome.get("aggregate"))
    return {
        "schemaVersion": 1,
        "auditVersion": "closy.strict_c3_v5.scope_audit.v2",
        "historicalBytesChanged": False,
        "qualificationReplayed": False,
        "poseDenominator": outcome.get("poseCount", aggregate.get("poseCount")),
        "rawIndexedSimulationComponents": 614,
        "rawIndexedRenderComponents": 614,
        "rawComponentEqualityIsCoherentShellProof": False,
        "stableAncestryPresentInFrozenArtifact": False,
        "predicates": {
            "densePositionFollowsDeclaredSimulationBinding": "pass",
            "candidateOracleAnalyticAgreement": "pass",
            "absoluteSimulationSeamGap": "not_measured",
            "absoluteDenseShellSeamGap": "not_measured",
            "physicalDeformationCorrectness": "not_measured",
            "restRelativeInversion": "not_measured",
            "persistedDeformedNormalTangent": "not_measured",
            "coherentRenderShell": "not_measured",
        },
        "timingClasses": {
            "evaluatorWallTime": "measured",
            "processCpuTime": "not_measured",
            "processRss": "not_measured_tracemalloc_only",
        },
        "rowDecision": {
            "rowId": "D0-RP-08",
            "result": "pass",
            "scope": "exact_unit_f_pre_topology_binding_reconstruction_only",
            "invalidation": "any_topology_or_binding_change",
        },
    }


def generic_c3_mutation_report() -> dict[str, bool]:
    frames = [{"normal": [0.0, 0.0, 1.0], "tangent": [1.0, 0.0, 0.0], "handedness": 1}]
    invalid = [{**frames[0], "handedness": 0}]
    positions = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
    triangles = [(0, 1, 2), (0, 2, 3)]
    inverted = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, -1.0, 0.0), (0.0, -1.0, 0.0)]
    return {
        "validFrameAccepted": not validate_frames(frames),
        "invalidTangentHandednessRejected": bool(validate_frames(invalid)),
        "hiddenComponentDetected": len(indexed_components(5, triangles)) == 2,
        "deletionDisconnectionDetected": len(indexed_components(4, [(0, 1, 2)])) == 2,
        "restRelativeInversionDetected": (
            rest_relative_inversions(positions, inverted, triangles) == 2
        ),
        "openingDerivedFromBoundary": (
            boundary_cycles(triangles, {"opening": [0, 1, 2, 3]})["opening"][0] == 0
        ),
    }


def _normal(positions: Sequence[Vec3], triangle: Triangle) -> Vec3:
    a, b, c = (positions[index] for index in triangle)
    left = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    right = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _vec3(value: object) -> Vec3:
    if not isinstance(value, list | tuple) or len(value) != 3:  # noqa: UP038
        return (math.nan, math.nan, math.nan)
    return (float(value[0]), float(value[1]), float(value[2]))


def _length(value: Vec3) -> float:
    return math.sqrt(_dot(value, value))


def _dot(left: Vec3, right: Vec3) -> float:
    return math.fsum(a * b for a, b in zip(left, right, strict=True))


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
