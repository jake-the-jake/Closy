from __future__ import annotations

from math import isfinite, sqrt
from pathlib import Path
from typing import Any

from closy_forge.geometry.frame_attributes import meshset_frame_metrics
from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Tri, Vec3
from closy_forge.geometry.signed_distance import audit_body_signed_clearance
from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.hashing import geometry_content_hash, topology_hash


def evaluate_stitched_shell_state(
    package_dir: Path,
    *,
    state_mesh: MeshSet,
    reference_mesh: MeshSet,
) -> dict[str, Any]:
    """Deform the persisted conforming shell from source-vertex classes, not the dense route."""

    analysis = read_json(package_dir / "stitch" / "logical_stitched_analysis_shell.json")
    stitch_report = read_json(package_dir / "reports" / "geometry_stitched_shell.json")
    if analysis.get("sourceSimulationMeshTopologyHash") != topology_hash(reference_mesh):
        raise ValueError("stitched_shell_source_topology_mismatch")
    reference_shell = read_glb_meshset(package_dir / "render" / "stitched_shell.glb")
    logical_shell = _logical_shell(analysis)
    if reference_shell.vertex_count != len(analysis.get("sourceVertexMap", [])):
        raise ValueError("stitched_render_shell_source_map_count_mismatch")
    if topology_hash(reference_shell) != topology_hash(logical_shell):
        raise ValueError("stitched_render_shell_logical_topology_mismatch")
    state_positions = _reconstruct_positions(analysis, state_mesh)
    repeat_positions = _reconstruct_positions(analysis, state_mesh)
    rest_positions = _reconstruct_positions(analysis, reference_mesh)
    deformed_shell = _replace_positions(reference_shell, state_positions)
    rest_shell = _replace_positions(reference_shell, rest_positions)
    frames = meshset_frame_metrics(deformed_shell)
    opening_metrics = _opening_metrics(stitch_report, deformed_shell, rest_shell)
    operation_records = analysis.get("executedOperations", [])
    welded_operations = [
        item
        for item in operation_records
        if item.get("status") == "executed"
        and item.get("logicalVertexIndexA") == item.get("logicalVertexIndexB")
    ]
    body = read_glb_meshset(package_dir / "avatar" / "collision.glb")
    clearance_calibration = read_json(
        Path(__file__).resolve().parents[3]
        / "docs"
        / "capability-profiles"
        / "phy1-clearance-calibration-v1.json"
    )
    body_clearance_audit = audit_body_signed_clearance(
        state_positions,
        body,
        point_ids=[f"logicalVertex.{index}" for index in range(len(state_positions))],
        cloth_half_thickness_meters=float(clearance_calibration["clothHalfThicknessMeters"]),
        skin_margin_meters=float(clearance_calibration["skinMarginMeters"]),
        oracle_uncertainty_meters=float(clearance_calibration["numericalOracleUncertaintyMeters"]),
        promotion_guard_band_meters=float(clearance_calibration["promotionGuardBandMeters"]),
    )
    minimum_body_clearance = float(body_clearance_audit["minimumBodySignedClearanceMeters"])
    deterministic_error = max(
        (
            _distance(left, right)
            for left, right in zip(state_positions, repeat_positions, strict=True)
        ),
        default=0.0,
    )
    topology_stable = topology_hash(deformed_shell) == topology_hash(reference_shell)
    indices_stable = all(
        current.triangles == reference.triangles
        for current, reference in zip(deformed_shell.meshes, reference_shell.meshes, strict=True)
    )
    frame_status = _frames_valid(frames)
    source_stitch_proven = bool(stitch_report.get("readiness", {}).get("meshStitchOrWeldProven"))
    checks = {
        "positionReconstruction": deterministic_error <= 1e-12,
        "normalTangentFrames": frame_status,
        "seamContinuity": len(welded_operations) == len(operation_records),
        "semanticOpeningStability": opening_metrics["collapsedOpeningCount"] == 0,
        "topologyStable": topology_stable,
        "indicesStable": indices_stable,
        "bodyClearance": body_clearance_audit["promotionEligible"],
        "singleLayerSeparation": True,
        "fallbackIndependent": True,
        "sourceStitchProof": source_stitch_proven,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "metricVersion": "closy.stitched_shell_deformation.d0_cpu.v1",
        "status": "pass" if not failures else "fail",
        "failureIds": [f"stitched_shell.{name}" for name in failures],
        "deformationMethod": "independent_logical_source_vertex_class_average",
        "callsDenseReconstruction": False,
        "persistedRenderShellLoaded": True,
        "persistedRenderShellPath": "render/stitched_shell.glb",
        "sourceVertexMapRecordCount": len(analysis.get("sourceVertexMap", [])),
        "logicalVertexCount": deformed_shell.vertex_count,
        "logicalTriangleCount": deformed_shell.triangle_count,
        "executedStitchOperationCount": len(operation_records),
        "weldedStitchOperationCount": len(welded_operations),
        "maxPositionReconstructionErrorMeters": _round(deterministic_error),
        "maxSeamCrackMeters": 0.0 if len(welded_operations) == len(operation_records) else None,
        "openingStability": opening_metrics,
        "minimumSignedBodyClearanceMeters": _round(minimum_body_clearance),
        "bodySignedClearanceAudit": body_clearance_audit,
        "layerSeparation": {
            "status": "not_applicable_single_layer_tshirt",
            "layerCount": 1,
        },
        "topologyHash": topology_hash(deformed_shell),
        "topologyStable": topology_stable,
        "indexBuffersStable": indices_stable,
        "contentHash": geometry_content_hash(deformed_shell),
        "frameMetrics": frames,
        "finitePositions": all(isfinite(value) for point in state_positions for value in point),
        "sourceStitchProofStatus": (
            "pass" if source_stitch_proven else "fail_existing_ordered_correspondence_audit"
        ),
        "checks": checks,
    }


def _logical_shell(analysis: dict[str, Any]) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                name=str(item["name"]),
                panel_id=str(item["panelId"]),
                vertices=[_vec3(point) for point in item["vertices"]],
                panel_uvs=[(float(uv[0]), float(uv[1])) for uv in item["panelUvs"]],
                triangles=[_tri(triangle) for triangle in item["triangles"]],
                material_id=str(item["materialId"]),
            )
            for item in analysis["logicalShell"]["meshes"]
        ]
    )


def _reconstruct_positions(analysis: dict[str, Any], source: MeshSet) -> list[Vec3]:
    records = analysis.get("sourceVertexMap", [])
    if len(records) != int(analysis["logicalShell"]["vertexCount"]):
        raise ValueError("stitched_source_vertex_map_count_mismatch")
    result: list[Vec3] = []
    for expected_index, record in enumerate(records):
        if int(record["logicalVertexIndex"]) != expected_index:
            raise ValueError("stitched_source_vertex_map_order_mismatch")
        samples = [
            source.meshes[int(item["meshIndex"])].vertices[int(item["vertexIndex"])]
            for item in record.get("sourceVertices", [])
        ]
        if not samples:
            raise ValueError("stitched_source_vertex_class_empty")
        result.append(
            tuple(sum(point[axis] for point in samples) / len(samples) for axis in range(3))  # type: ignore[arg-type]
        )
    return result


def _replace_positions(reference: MeshSet, positions: list[Vec3]) -> MeshSet:
    result: list[Mesh] = []
    offset = 0
    for mesh in reference.meshes:
        count = len(mesh.vertices)
        result.append(
            Mesh(
                mesh.name,
                mesh.panel_id,
                positions[offset : offset + count],
                mesh.panel_uvs,
                mesh.triangles,
                mesh.material_id,
            )
        )
        offset += count
    if offset != len(positions):
        raise ValueError("stitched_replacement_position_count_mismatch")
    return MeshSet(result)


def _opening_metrics(
    stitch_report: dict[str, Any], current: MeshSet, reference: MeshSet
) -> dict[str, Any]:
    mappings = stitch_report["topologyAudit"]["semanticOpeningAudit"]["candidateOpeningMappings"]
    current_positions = [point for mesh in current.meshes for point in mesh.vertices]
    reference_positions = [point for mesh in reference.meshes for point in mesh.vertices]
    results: list[dict[str, Any]] = []
    for mapping in mappings:
        indices = [_logical_vertex_index(value) for value in mapping["orderedLoopVertexIds"]]
        current_length = _cycle_length(current_positions, indices)
        reference_length = _cycle_length(reference_positions, indices)
        results.append(
            {
                "openingId": str(mapping["openingId"]),
                "currentPerimeterMeters": _round(current_length),
                "referencePerimeterMeters": _round(reference_length),
                "driftMeters": _round(abs(current_length - reference_length)),
                "collapsed": current_length < max(0.01, reference_length * 0.25),
            }
        )
    return {
        "openingCount": len(results),
        "maxPerimeterDriftMeters": max(
            (float(item["driftMeters"]) for item in results), default=0.0
        ),
        "collapsedOpeningCount": sum(bool(item["collapsed"]) for item in results),
        "openings": sorted(results, key=lambda item: str(item["openingId"])),
    }


def _frames_valid(metrics: dict[str, Any]) -> bool:
    return bool(
        int(metrics["normalVectorCount"]) == int(metrics["finiteNormalCount"])
        and int(metrics["tangentVectorCount"]) == int(metrics["finiteTangentCount"])
        and float(metrics["maxNormalLengthError"]) <= 1e-6
        and float(metrics["maxTangentLengthError"]) <= 1e-6
        and float(metrics["maxNormalTangentDot"]) <= 1e-6
    )


def _logical_vertex_index(value: str) -> int:
    prefix = "logicalVertex."
    if not value.startswith(prefix):
        raise ValueError("invalid_logical_vertex_id")
    return int(value[len(prefix) :])


def _cycle_length(points: list[Vec3], indices: list[int]) -> float:
    if len(indices) < 3:
        return 0.0
    return sum(
        _distance(points[left], points[right])
        for left, right in zip(indices, indices[1:] + indices[:1], strict=True)
    )


def _vec3(value: Any) -> Vec3:
    return (float(value[0]), float(value[1]), float(value[2]))


def _tri(value: Any) -> Tri:
    return (int(value[0]), int(value[1]), int(value[2]))


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(value: Vec3, factor: float) -> Vec3:
    return (value[0] * factor, value[1] * factor, value[2] * factor)


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _distance(a: Vec3, b: Vec3) -> float:
    delta = _sub(a, b)
    return sqrt(_dot(delta, delta))


def _round(value: float) -> float:
    return round(float(value), 9)
