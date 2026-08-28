from __future__ import annotations

from math import isfinite, sqrt
from typing import Any

from closy_forge.geometry.mesh_model import MeshSet, Tri, Vec3

DEFORMATION_QUALITY_VERSION = "closy.deformation_quality.rest_referenced.v1"


def audit_rest_referenced_deformation(
    rest: MeshSet,
    deformed: MeshSet,
    *,
    minimum_area_ratio: float = 0.65,
    maximum_area_ratio: float = 1.5,
    degenerate_double_area_meters2: float = 1e-12,
    near_degenerate_minimum_altitude_meters: float = 1e-6,
) -> dict[str, Any]:
    if len(rest.meshes) != len(deformed.meshes):
        raise ValueError("deformation_quality_mesh_inventory_mismatch")
    records: list[dict[str, Any]] = []
    global_index = 0
    for mesh_index, (rest_mesh, current_mesh) in enumerate(
        zip(rest.meshes, deformed.meshes, strict=True)
    ):
        if rest_mesh.triangles != current_mesh.triangles:
            raise ValueError("deformation_quality_topology_mismatch")
        if len(rest_mesh.vertices) != len(current_mesh.vertices):
            raise ValueError("deformation_quality_vertex_inventory_mismatch")
        for local_index, triangle in enumerate(rest_mesh.triangles):
            records.append(
                _triangle_record(
                    rest_mesh.vertices,
                    current_mesh.vertices,
                    triangle,
                    mesh_index=mesh_index,
                    mesh_name=rest_mesh.name,
                    local_triangle_index=local_index,
                    global_triangle_index=global_index,
                    minimum_area_ratio=minimum_area_ratio,
                    maximum_area_ratio=maximum_area_ratio,
                    degenerate_double_area_meters2=degenerate_double_area_meters2,
                    near_degenerate_minimum_altitude_meters=(
                        near_degenerate_minimum_altitude_meters
                    ),
                )
            )
            global_index += 1
    counts = {
        "nonfinite": sum(record["nonfinite"] for record in records),
        "degenerate": sum(record["degenerate"] for record in records),
        "nearDegenerate": sum(record["nearDegenerate"] for record in records),
        "inverted": sum(record["inverted"] for record in records),
        "normalFlipped": sum(record["normalFlipped"] for record in records),
        "excessiveAreaStrain": sum(record["excessiveAreaStrain"] for record in records),
    }
    failing = [
        record
        for record in records
        if any(
            record[key]
            for key in (
                "nonfinite",
                "degenerate",
                "nearDegenerate",
                "inverted",
                "normalFlipped",
                "excessiveAreaStrain",
            )
        )
    ]
    return {
        "schemaVersion": 1,
        "auditVersion": DEFORMATION_QUALITY_VERSION,
        "triangleCount": len(records),
        "policy": {
            "minimumAreaRatio": minimum_area_ratio,
            "maximumAreaRatio": maximum_area_ratio,
            "degenerateDoubleAreaMeters2": degenerate_double_area_meters2,
            "nearDegenerateMinimumAltitudeMeters": near_degenerate_minimum_altitude_meters,
            "orientation": "dot_deformed_cross_with_rest_unit_normal",
        },
        "counts": counts,
        "minimumAreaRatio": min((record["areaRatio"] for record in records), default=0.0),
        "maximumAreaRatio": max((record["areaRatio"] for record in records), default=0.0),
        "minimumNormalAgreement": min(
            (record["normalAgreement"] for record in records), default=0.0
        ),
        "minimumAltitudeMeters": min(
            (record["minimumAltitudeMeters"] for record in records), default=0.0
        ),
        "minimumConditioningRatio": min(
            (record["conditioningRatio"] for record in records), default=0.0
        ),
        "worstWitnesses": sorted(
            failing,
            key=lambda record: (
                record["signedOrientationMeters2"],
                record["minimumAltitudeMeters"],
                record["globalTriangleIndex"],
            ),
        )[:8],
        "status": "pass" if not failing else "fail",
    }


def _triangle_record(
    rest_vertices: list[Vec3],
    current_vertices: list[Vec3],
    triangle: Tri,
    *,
    mesh_index: int,
    mesh_name: str,
    local_triangle_index: int,
    global_triangle_index: int,
    minimum_area_ratio: float,
    maximum_area_ratio: float,
    degenerate_double_area_meters2: float,
    near_degenerate_minimum_altitude_meters: float,
) -> dict[str, Any]:
    rest_points = tuple(rest_vertices[index] for index in triangle)
    current_points = tuple(current_vertices[index] for index in triangle)
    finite = all(isfinite(value) for point in (*rest_points, *current_points) for value in point)
    rest_cross = _cross(_sub(rest_points[1], rest_points[0]), _sub(rest_points[2], rest_points[0]))
    current_cross = _cross(
        _sub(current_points[1], current_points[0]),
        _sub(current_points[2], current_points[0]),
    )
    rest_double_area = _length(rest_cross)
    current_double_area = _length(current_cross)
    rest_normal = (
        _scale(rest_cross, 1.0 / rest_double_area) if rest_double_area > 0.0 else (0.0, 0.0, 0.0)
    )
    current_normal = (
        _scale(current_cross, 1.0 / current_double_area)
        if current_double_area > 0.0
        else (0.0, 0.0, 0.0)
    )
    signed_orientation = _dot(current_cross, rest_normal)
    normal_agreement = _dot(current_normal, rest_normal)
    area_ratio = current_double_area / rest_double_area if rest_double_area > 0.0 else 0.0
    edge_lengths = (
        _distance(current_points[0], current_points[1]),
        _distance(current_points[1], current_points[2]),
        _distance(current_points[2], current_points[0]),
    )
    longest_edge = max(edge_lengths)
    minimum_altitude = current_double_area / longest_edge if longest_edge > 0.0 else 0.0
    conditioning = minimum_altitude / longest_edge if longest_edge > 0.0 else 0.0
    degenerate = current_double_area <= degenerate_double_area_meters2
    return {
        "triangleId": f"{mesh_name}:triangle.{local_triangle_index}",
        "meshIndex": mesh_index,
        "meshName": mesh_name,
        "localTriangleIndex": local_triangle_index,
        "globalTriangleIndex": global_triangle_index,
        "vertexIndices": list(triangle),
        "finite": finite,
        "nonfinite": not finite,
        "restDoubleAreaMeters2": _round(rest_double_area),
        "currentDoubleAreaMeters2": _round(current_double_area),
        "signedOrientationMeters2": _round(signed_orientation),
        "normalAgreement": _round(normal_agreement),
        "areaRatio": _round(area_ratio),
        "minimumAltitudeMeters": _round(minimum_altitude),
        "conditioningRatio": _round(conditioning),
        "degenerate": degenerate,
        "nearDegenerate": not degenerate
        and minimum_altitude <= near_degenerate_minimum_altitude_meters,
        "inverted": not degenerate and signed_orientation < 0.0,
        "normalFlipped": not degenerate and normal_agreement < 0.0,
        "excessiveAreaStrain": not degenerate
        and not minimum_area_ratio <= area_ratio <= maximum_area_ratio,
    }


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _scale(value: Vec3, factor: float) -> Vec3:
    return (value[0] * factor, value[1] * factor, value[2] * factor)


def _length(value: Vec3) -> float:
    return sqrt(_dot(value, value))


def _distance(a: Vec3, b: Vec3) -> float:
    return _length(_sub(a, b))


def _round(value: float) -> float:
    return round(float(value), 9)
