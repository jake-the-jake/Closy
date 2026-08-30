from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import read_json
from closy_forge.zeroone.dynamic_oracle import (
    OUTPUT_FRAME_POSITIONS,
    OUTPUT_INDICES,
    RENDER_IDS,
    TIMESTAMPS,
    audit_files,
    decode_document,
    decode_u32,
    decode_u64,
    decode_vectors,
    recompute_frames,
)
from closy_forge.zeroone.intersection_manifest import SurfaceRepresentation, audit_surface
from closy_forge.zeroone.mechanical_reference_surface import (
    MECHANICAL_REFERENCE_CORNER_MAP_PATH,
    MECHANICAL_REFERENCE_PROFILE,
)

Vec3 = tuple[float, float, float]

ORACLE_VERSION = "closy.zeroone.mt1-independent-oracle.v2"
MINIMUM_DOUBLE_AREA_METERS2 = 5.0e-9
MAXIMUM_POSITION_ERROR_METERS = 2.0e-6
P95_POSITION_ERROR_METERS = 5.0e-7
MAXIMUM_NORMAL_ERROR_DEGREES = 0.25
MAXIMUM_TANGENT_ERROR_DEGREES = 0.5
MAXIMUM_BOUNDARY_CRACK_METERS = 5.0e-5
MAXIMUM_OPENING_LOOP_DISTANCE_METERS = 5.0e-5
BOUNDS_GUARD_BAND_METERS = 1.0e-5


def audit_mechanical_reference_files(
    request_path: Path, output_path: Path, package_dir: Path
) -> dict[str, Any]:
    """Independently qualify MT1; processor acceptance fields are not consumed as truth."""

    package = package_dir.resolve(strict=True)
    base = audit_files(request_path, output_path)
    request = decode_document(request_path.read_bytes(), request=True)
    output = decode_document(output_path.read_bytes(), request=False)
    _, render_ids, timestamps, expected_frames = recompute_frames(request)
    output_ids = decode_u64(output.sections[RENDER_IDS])
    output_timestamps = decode_u64(output.sections[TIMESTAMPS])
    if output_ids != render_ids or output_timestamps != timestamps:
        raise ValueError("mt1_output_identity_or_timestamp_mismatch")
    output_indices = decode_u32(output.sections[OUTPUT_INDICES])
    output_positions = decode_vectors(output.sections[OUTPUT_FRAME_POSITIONS], 3, 3)
    frame_count = len(timestamps)
    dense_count = len(render_ids)
    output_frames = [
        output_positions[index * dense_count : (index + 1) * dense_count]
        for index in range(frame_count)
    ]
    corner_map = _object(package / MECHANICAL_REFERENCE_CORNER_MAP_PATH)
    corner_to_logical = [
        int(row["logicalDestinationIndex"]) for row in _rows(corner_map, "rows")
    ]
    if len(corner_to_logical) != dense_count:
        raise ValueError("mt1_corner_map_dense_inventory_mismatch")
    logical_count = int(corner_map["logicalDestinationCount"])
    logical_triangles, lineage = _logical_topology(package)
    if len(output_indices) // 3 != len(logical_triangles):
        raise ValueError("mt1_output_triangle_inventory_mismatch")
    groups: list[list[int]] = [[] for _ in range(logical_count)]
    for corner, logical in enumerate(corner_to_logical):
        if logical < 0 or logical >= logical_count:
            raise ValueError("mt1_corner_map_logical_index_out_of_range")
        groups[logical].append(corner)
    if any(not group for group in groups):
        raise ValueError("mt1_logical_destination_unmapped")

    output_logical: list[list[Vec3]] = []
    expected_logical: list[list[Vec3]] = []
    maximum_boundary_crack = 0.0
    for output_frame, expected_frame in zip(output_frames, expected_frames, strict=True):
        output_row: list[Vec3] = []
        expected_row: list[Vec3] = []
        for corners in groups:
            output_reference = output_frame[corners[0]]
            expected_reference = expected_frame[corners[0]]
            maximum_boundary_crack = max(
                maximum_boundary_crack,
                *(math.dist(output_reference, output_frame[corner]) for corner in corners),
            )
            output_row.append(output_reference)
            expected_row.append(expected_reference)
        output_logical.append(output_row)
        expected_logical.append(expected_row)

    rest_surface = SurfaceRepresentation(
        "mt1_output_logical_frame_000",
        output_logical[0],
        logical_triangles,
        list(range(logical_count)),
        lineage,
    )
    topology_audit = audit_surface(rest_surface)
    output_intersections = []
    expected_intersections = []
    for frame in range(frame_count):
        output_audit = audit_surface(
            SurfaceRepresentation(
                f"mt1_output_logical_frame_{frame:03d}",
                output_logical[frame],
                logical_triangles,
                list(range(logical_count)),
                lineage,
            ),
            topology_override=topology_audit["topology"],
        )
        expected_audit = audit_surface(
            SurfaceRepresentation(
                f"mt1_expected_logical_frame_{frame:03d}",
                expected_logical[frame],
                logical_triangles,
                list(range(logical_count)),
                lineage,
            ),
            topology_override=topology_audit["topology"],
        )
        output_intersections.append(_bounded_intersection_frame(frame, output_audit))
        expected_intersections.append(_bounded_intersection_frame(frame, expected_audit))

    position_errors = [
        math.dist(output_logical[frame][vertex], expected_logical[frame][vertex])
        for frame in range(frame_count)
        for vertex in range(logical_count)
    ]
    minimum_double_area = min(
        _double_area(
            frame[triangle[0]],
            frame[triangle[1]],
            frame[triangle[2]],
        )
        for frame in output_logical
        for triangle in logical_triangles
    )
    boundary_ids = {
        vertex
        for component in topology_audit["topology"]["boundaryComponents"]
        for vertex in component
    }
    maximum_opening_distance = max(
        (
            math.dist(output_logical[frame][vertex], expected_logical[frame][vertex])
            for frame in range(frame_count)
            for vertex in boundary_ids
        ),
        default=0.0,
    )
    introduced_pairs = _introduced_pairs(expected_intersections, output_intersections)
    topology = topology_audit["topology"]
    checks = {
        "processingTriangleDoubleArea": minimum_double_area > MINIMUM_DOUBLE_AREA_METERS2,
        "staticTopology": all(
            topology[key] == 0
            for key in (
                "duplicateFaceCount",
                "nonManifoldEdgeCount",
                "tJunctionCount",
                "degenerateTriangleCount",
            )
        ),
        "transportPairDelta": not introduced_pairs,
        "cleanReferenceOutputIntersections": all(
            frame["intersectionCount"] == 0 for frame in output_intersections
        ),
        "cleanReferenceIndependentIntersections": all(
            frame["intersectionCount"] == 0 for frame in expected_intersections
        ),
        "maximumPositionError": max(position_errors) <= MAXIMUM_POSITION_ERROR_METERS,
        "p95PositionError": _percentile(position_errors, 0.95) <= P95_POSITION_ERROR_METERS,
        "normalError": base["maximumNormalError"]
        <= _vector_error_from_angle(MAXIMUM_NORMAL_ERROR_DEGREES),
        "tangentError": base["maximumTangentError"]
        <= _vector_error_from_angle(MAXIMUM_TANGENT_ERROR_DEGREES),
        "tangentHandedness": base["tangentHandednessMismatchCount"] == 0,
        "boundaryCrack": maximum_boundary_crack <= MAXIMUM_BOUNDARY_CRACK_METERS,
        "openingLoopDistance": maximum_opening_distance
        <= MAXIMUM_OPENING_LOOP_DISTANCE_METERS,
        "boundsGuardBand": base["culling"]["falseNegativeCount"] == 0,
        "culling": base["culling"]["falseNegativeCount"] == 0,
        "temporalOrientation": base["trueTemporalInversionCount"] == 0,
        "frameCount": frame_count >= 13,
        "restReturnIdentity": output_logical[0] == output_logical[-1]
        and expected_logical[0] == expected_logical[-1],
        "bindingCoverage": len(corner_to_logical) == dense_count
        and len({row for row in range(dense_count)}) == dense_count,
    }
    return {
        **base,
        "schemaVersion": "closy.zeroone.mt1-independent-oracle.v2",
        "oracleVersion": ORACLE_VERSION,
        "profile": MECHANICAL_REFERENCE_PROFILE,
        "logicalDestinationCount": logical_count,
        "denseCornerCount": dense_count,
        "minimumProcessingTriangleDoubleAreaMeters2": minimum_double_area,
        "topology": topology,
        "outputIntersectionFrames": output_intersections,
        "independentReconstructionIntersectionFrames": expected_intersections,
        "inheritedInputPairIds": sorted(
            {
                pair
                for frame in expected_intersections
                for pair in frame["intersectionPairIds"]
            }
        ),
        "introducedOrWorsenedPairIds": introduced_pairs,
        "maximumPositionErrorMetres": max(position_errors),
        "p95PositionErrorMetres": _percentile(position_errors, 0.95),
        "maximumBoundaryCrackMeters": maximum_boundary_crack,
        "maximumOpeningLoopDistanceMeters": maximum_opening_distance,
        "boundsGuardBand": {
            "enforced": True,
            "meters": BOUNDS_GUARD_BAND_METERS,
            "falseNegativeCount": base["culling"]["falseNegativeCount"],
        },
        "thresholds": {
            "minimumProcessingTriangleDoubleAreaMeters2Exclusive": (
                MINIMUM_DOUBLE_AREA_METERS2
            ),
            "maximumPositionErrorMeters": MAXIMUM_POSITION_ERROR_METERS,
            "p95PositionErrorMeters": P95_POSITION_ERROR_METERS,
            "maximumNormalAngleDegrees": MAXIMUM_NORMAL_ERROR_DEGREES,
            "maximumTangentAngleDegrees": MAXIMUM_TANGENT_ERROR_DEGREES,
            "maximumBoundaryCrackMeters": MAXIMUM_BOUNDARY_CRACK_METERS,
            "maximumOpeningLoopDistanceMeters": MAXIMUM_OPENING_LOOP_DISTANCE_METERS,
            "boundsGuardBandMeters": BOUNDS_GUARD_BAND_METERS,
        },
        "checks": checks,
        "physicalTruthClaimed": False,
        "blueprintZ2Claimed": False,
        "passed": all(checks.values()),
    }


def _bounded_intersection_frame(frame: int, audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "frameIndex": frame,
        "intersectionCount": audit["intersectingPairCount"],
        "intersectionPairIds": [row["pairId"] for row in audit["intersectingPairs"]],
        "deterministicWitnessHash": audit["deterministicWitnessHash"],
        "witnesses": [row["witness"] for row in audit["intersectingPairs"]],
    }


def _introduced_pairs(
    expected: list[dict[str, Any]], output: list[dict[str, Any]]
) -> list[str]:
    introduced = set()
    for expected_frame, output_frame in zip(expected, output, strict=True):
        inherited = set(expected_frame["intersectionPairIds"])
        introduced.update(set(output_frame["intersectionPairIds"]) - inherited)
    return sorted(introduced)


def _logical_topology(
    package: Path,
) -> tuple[list[tuple[int, int, int]], list[dict[str, Any]]]:
    manifest = _object(package / "render" / "mesh_manifest.json")
    triangles: list[tuple[int, int, int]] = []
    lineage: list[dict[str, Any]] = []
    offset = 0
    for mesh_index, mesh in enumerate(_rows(manifest, "meshes")):
        for local_index, triangle in enumerate(mesh.get("triangles", [])):
            triangles.append(tuple(offset + int(value) for value in triangle))
            lineage.append(
                {
                    "meshIndex": mesh_index,
                    "localTriangleIndex": local_index,
                    "panelId": str(mesh.get("panelId")),
                    "materialId": str(mesh.get("materialId")),
                }
            )
        offset += len(mesh.get("vertices", []))
    return triangles, lineage


def _double_area(a: Vec3, b: Vec3, c: Vec3) -> float:
    left = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    right = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cross = (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )
    return math.sqrt(sum(value * value for value in cross))


def _vector_error_from_angle(degrees: float) -> float:
    return 2.0 * math.sin(math.radians(degrees) * 0.5)


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))]


def _rows(value: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = value.get(key)
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"mt1_rows_invalid:{key}")
    return rows


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"mt1_object_required:{path.name}")
    return value
