from __future__ import annotations

from math import isfinite, sqrt
from typing import Any, TypedDict

from closy_forge.geometry.mesh_model import MeshSet, Vec3

TEMPORAL_DEFORMATION_QUALITY_VERSION = "closy.deformation_quality.temporal_swept_area.v1"
TEMPORAL_ORACLE_LINEAGE_COMMIT = "9cca413dcd69389610a1215777ccc2443136a937"


class _TemporalSample(TypedDict):
    frameIndex: int
    frameId: str
    cross: Vec3
    doubleAreaMeters2: float
    nonfinite: bool
    degenerate: bool


def audit_temporal_deformation_quality(
    frames: list[MeshSet],
    *,
    frame_ids: list[str] | None = None,
    degenerate_double_area_meters2: float = 1e-12,
) -> dict[str, Any]:
    """Apply the previously qualified rotation-invariant swept-area oracle.

    This is a byte-faithful algorithm port from the unpublished PHY1 oracle lineage identified by
    ``TEMPORAL_ORACLE_LINEAGE_COMMIT``. A continuous material triangle cannot reverse orientation
    without crossing zero area, so the oracle evaluates sampled areas and the quadratic swept cross
    product between adjacent timestamps rather than comparing to a fixed world-space normal.
    """

    if not frames:
        raise ValueError("temporal_deformation_quality_frames_empty")
    labels = frame_ids or [f"frame.{index}" for index in range(len(frames))]
    if len(labels) != len(frames) or len(set(labels)) != len(labels):
        raise ValueError("temporal_deformation_quality_frame_ids_invalid")
    _validate_temporal_topology(frames)

    records: list[dict[str, Any]] = []
    global_triangle_index = 0
    for mesh_index, reference_mesh in enumerate(frames[0].meshes):
        for local_triangle_index, triangle in enumerate(reference_mesh.triangles):
            samples: list[_TemporalSample] = []
            for frame_index, frame in enumerate(frames):
                vertices = frame.meshes[mesh_index].vertices
                points = (
                    vertices[triangle[0]],
                    vertices[triangle[1]],
                    vertices[triangle[2]],
                )
                finite = all(isfinite(value) for point in points for value in point)
                cross = _triangle_cross(points)
                double_area = _length(cross) if finite else 0.0
                samples.append(
                    {
                        "frameIndex": frame_index,
                        "frameId": labels[frame_index],
                        "cross": cross,
                        "doubleAreaMeters2": double_area,
                        "nonfinite": not finite,
                        "degenerate": finite and double_area <= degenerate_double_area_meters2,
                    }
                )

            transitions: list[dict[str, Any]] = []
            inversion_keys: set[tuple[int, int]] = set()
            for frame_index in range(len(frames) - 1):
                start_vertices = frames[frame_index].meshes[mesh_index].vertices
                end_vertices = frames[frame_index + 1].meshes[mesh_index].vertices
                start_points = (
                    start_vertices[triangle[0]],
                    start_vertices[triangle[1]],
                    start_vertices[triangle[2]],
                )
                end_points = (
                    end_vertices[triangle[0]],
                    end_vertices[triangle[1]],
                    end_vertices[triangle[2]],
                )
                zero_time = _swept_zero_time(
                    start_points,
                    end_points,
                    threshold=degenerate_double_area_meters2,
                )
                swept_degenerate = zero_time is not None
                start_sample = samples[frame_index]
                end_sample = samples[frame_index + 1]
                true_inversion = (
                    swept_degenerate
                    and not start_sample["degenerate"]
                    and not end_sample["degenerate"]
                    and _dot(start_sample["cross"], end_sample["cross"]) < 0.0
                )
                if true_inversion:
                    inversion_keys.add((frame_index, frame_index + 1))
                transitions.append(
                    {
                        "fromFrameId": labels[frame_index],
                        "toFrameId": labels[frame_index + 1],
                        "sweptDegenerate": swept_degenerate,
                        "zeroAreaTime": None if zero_time is None else _round(zero_time),
                        "trueInversion": true_inversion,
                    }
                )

            index = 0
            while index < len(samples):
                if not samples[index]["degenerate"]:
                    index += 1
                    continue
                run_start = index
                while index + 1 < len(samples) and samples[index + 1]["degenerate"]:
                    index += 1
                previous = run_start - 1
                following = index + 1
                if (
                    previous >= 0
                    and following < len(samples)
                    and not samples[previous]["nonfinite"]
                    and not samples[following]["nonfinite"]
                    and _dot(samples[previous]["cross"], samples[following]["cross"]) < 0.0
                ):
                    inversion_keys.add((previous, following))
                index += 1

            records.append(
                {
                    "triangleId": f"{reference_mesh.name}:triangle.{local_triangle_index}",
                    "meshIndex": mesh_index,
                    "localTriangleIndex": local_triangle_index,
                    "globalTriangleIndex": global_triangle_index,
                    "vertexIndices": list(triangle),
                    "samples": [
                        {
                            key: (_round(value) if isinstance(value, float) else value)
                            for key, value in sample.items()
                            if key != "cross"
                        }
                        for sample in samples
                    ],
                    "transitions": transitions,
                    "nonfiniteFrameCount": sum(sample["nonfinite"] for sample in samples),
                    "degenerateFrameCount": sum(sample["degenerate"] for sample in samples),
                    "sweptDegenerateTransitionCount": sum(
                        transition["sweptDegenerate"] for transition in transitions
                    ),
                    "trueInversionCount": len(inversion_keys),
                    "minimumDoubleAreaMeters2": _round(
                        min(
                            (sample["doubleAreaMeters2"] for sample in samples),
                            default=0.0,
                        )
                    ),
                }
            )
            global_triangle_index += 1

    counts = {
        "nonfiniteFrameTriangles": sum(record["nonfiniteFrameCount"] for record in records),
        "degenerateFrameTriangles": sum(record["degenerateFrameCount"] for record in records),
        "sweptDegenerateTransitions": sum(
            record["sweptDegenerateTransitionCount"] for record in records
        ),
        "trueInversions": sum(record["trueInversionCount"] for record in records),
    }
    failing = [
        record
        for record in records
        if record["nonfiniteFrameCount"]
        or record["degenerateFrameCount"]
        or record["sweptDegenerateTransitionCount"]
        or record["trueInversionCount"]
    ]
    return {
        "schemaVersion": 1,
        "auditVersion": TEMPORAL_DEFORMATION_QUALITY_VERSION,
        "lineageCommit": TEMPORAL_ORACLE_LINEAGE_COMMIT,
        "frameCount": len(frames),
        "frameIds": labels,
        "triangleCount": len(records),
        "policy": {
            "degenerateDoubleAreaMeters2": degenerate_double_area_meters2,
            "orientation": "winding_change_requires_temporal_swept_zero_area",
            "fixedWorldRestNormalUsed": False,
            "degeneracyAndTrueInversionReportedSeparately": True,
        },
        "counts": counts,
        "minimumDoubleAreaMeters2": min(
            (record["minimumDoubleAreaMeters2"] for record in records), default=0.0
        ),
        "worstWitnesses": failing[:8],
        "status": "pass" if not failing else "fail",
    }


def _validate_temporal_topology(frames: list[MeshSet]) -> None:
    reference = frames[0]
    for frame in frames[1:]:
        if len(frame.meshes) != len(reference.meshes):
            raise ValueError("temporal_deformation_quality_mesh_inventory_mismatch")
        for expected, current in zip(reference.meshes, frame.meshes, strict=True):
            if expected.triangles != current.triangles:
                raise ValueError("temporal_deformation_quality_topology_mismatch")
            if len(expected.vertices) != len(current.vertices):
                raise ValueError("temporal_deformation_quality_vertex_inventory_mismatch")


def _triangle_cross(points: tuple[Vec3, Vec3, Vec3]) -> Vec3:
    return _cross(_sub(points[1], points[0]), _sub(points[2], points[0]))


def _swept_zero_time(
    start: tuple[Vec3, Vec3, Vec3],
    end: tuple[Vec3, Vec3, Vec3],
    *,
    threshold: float,
) -> float | None:
    if not all(isfinite(value) for point in (*start, *end) for value in point):
        return None
    start_e1 = _sub(start[1], start[0])
    start_e2 = _sub(start[2], start[0])
    delta_e1 = _sub(_sub(end[1], end[0]), start_e1)
    delta_e2 = _sub(_sub(end[2], end[0]), start_e2)
    coefficient_0 = _cross(start_e1, start_e2)
    coefficient_1 = _add(_cross(delta_e1, start_e2), _cross(start_e1, delta_e2))
    coefficient_2 = _cross(delta_e1, delta_e2)
    candidates: set[float] = set()
    coefficient_epsilon = max(1e-15, threshold * 1e-3)
    for component in range(3):
        candidates.update(
            _quadratic_roots(
                coefficient_2[component],
                coefficient_1[component],
                coefficient_0[component],
                epsilon=coefficient_epsilon,
            )
        )
    candidates.update(index / 64.0 for index in range(1, 64))
    valid: list[float] = []
    for time in candidates:
        if not 0.0 < time < 1.0:
            continue
        cross = _add(
            coefficient_0,
            _add(_scale(coefficient_1, time), _scale(coefficient_2, time * time)),
        )
        if _length(cross) <= threshold:
            valid.append(time)
    return min(valid) if valid else None


def _quadratic_roots(a: float, b: float, c: float, *, epsilon: float) -> set[float]:
    if abs(a) <= epsilon:
        if abs(b) <= epsilon:
            return set()
        return {-c / b}
    discriminant = b * b - 4.0 * a * c
    if discriminant < -epsilon:
        return set()
    root = sqrt(max(0.0, discriminant))
    return {(-b - root) / (2.0 * a), (-b + root) / (2.0 * a)}


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _scale(value: Vec3, factor: float) -> Vec3:
    return (value[0] * factor, value[1] * factor, value[2] * factor)


def _length(value: Vec3) -> float:
    return sqrt(_dot(value, value))


def _round(value: float) -> float:
    return round(float(value), 12)
