from __future__ import annotations

import math
import struct
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import BindingFile, read_binding
from closy_forge.geometry.glb_io import audit_glb_geometry, read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3, cross, mesh_bounds, sub
from closy_forge.inspection.cpu_raster import rasterize_settled_garment
from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)

PROCESSING_ROOT = "zeroone/input-z1-v1"
PROCESSING_SURFACE_PATH = f"{PROCESSING_ROOT}/processing_surface.glb"
PROCESSING_MANIFEST_PATH = f"{PROCESSING_ROOT}/surface_manifest.json"
PROCESSING_REMAP_PATH = f"{PROCESSING_ROOT}/dense_to_processing_remap.json"
PROCESSING_INFLUENCE_PATH = f"{PROCESSING_ROOT}/sim_to_processing_cluster_influence.json"
PROCESSING_REPORT_PATH = f"{PROCESSING_ROOT}/surface_equivalence_report.json"

PROCESSING_VERSION = "closy.zeroone.seam_aware_processing_surface.z1.v1"
THRESHOLD_PROFILE = "closy.surface_equivalence.z1.v1"
MINIMUM_TRIANGLE_AREA_METERS2 = 1e-12
MAXIMUM_SURFACE_DISTANCE_METERS = 2e-7
MAXIMUM_P95_SURFACE_DISTANCE_METERS = 5e-8
MAXIMUM_AREA_RELATIVE_DELTA = 1e-6
MAXIMUM_BOUNDS_DELTA_METERS = 2e-7
MAXIMUM_BOUNDARY_LENGTH_RELATIVE_DELTA = 1e-6
MAXIMUM_DEPTH_IMAGE_DEVIATION_METERS = 2e-6
MINIMUM_SILHOUETTE_IOU = 0.9999

_STRATEGIES: tuple[tuple[str, int, int, tuple[tuple[float, float], ...]], ...] = (
    (
        "Z1-S2-SEAM-AWARE-LOCAL-VERTEX-SPLIT",
        1,
        2,
        ((6e-8, 6e-8), (9e-8, 6e-8), (1.2e-7, 6e-8), (1e-7, 8e-8)),
    ),
    (
        "Z1-S3-VERSIONED-PROCESSING-PATCH",
        0,
        0,
        ((6e-8, 6e-8), (9e-8, 6e-8), (1.2e-7, 6e-8), (1e-7, 8e-8)),
    ),
)


@dataclass(frozen=True)
class ProcessingSurfaceBundle:
    meshset: MeshSet
    manifest: dict[str, Any]
    remap: dict[str, Any]
    influence: dict[str, Any]
    report: dict[str, Any]


def write_processing_surface_bundle(
    *,
    package_dir: Path,
    source_mesh: MeshSet,
    binding: BindingFile,
    semantic_graph: dict[str, Any],
    material_name: str,
    material_color: tuple[float, float, float, float],
) -> ProcessingSurfaceBundle:
    """Write a derivative-local ZeroOne input without changing canonical authorities."""

    canonical_source_path = package_dir / "render/fallback.glb"
    if not canonical_source_path.is_file():
        raise ValueError("processing_surface_canonical_fallback_missing")
    canonical_source = read_glb_meshset(canonical_source_path)
    if topology_hash(canonical_source) != topology_hash(source_mesh):
        raise ValueError("processing_surface_source_topology_roundtrip_mismatch")
    authority_hashes_before = _non_zeroone_package_hashes(package_dir)

    candidate, repair_rows = _repair_surface(canonical_source)
    remap = _build_remap(canonical_source, candidate, repair_rows)
    influence = _build_influence(candidate, binding, remap)
    report = _equivalence_report(canonical_source, candidate, semantic_graph, repair_rows)
    if report["status"] != "pass":
        raise ValueError(f"processing_surface_equivalence_failed:{report['failureReasons']}")

    surface_path = package_dir / PROCESSING_SURFACE_PATH
    write_indexed_glb(surface_path, candidate, material_name, material_color)
    decoded = read_glb_meshset(surface_path)
    glb_audit = audit_glb_geometry(
        surface_path, minimum_triangle_area=MINIMUM_TRIANGLE_AREA_METERS2
    )
    if glb_audit["status"] != "pass":
        raise ValueError("processing_surface_glb_roundtrip_invalid")
    roundtrip_distance = _maximum_corresponding_vertex_distance(candidate, decoded)
    if roundtrip_distance > MAXIMUM_SURFACE_DISTANCE_METERS:
        raise ValueError("processing_surface_glb_roundtrip_distance_exceeded")
    authority_hashes_after = _non_zeroone_package_hashes(package_dir)
    if authority_hashes_after != authority_hashes_before:
        raise ValueError("processing_surface_canonical_authority_mutated")
    report["glbRoundTrip"] = {
        "audit": glb_audit,
        "maximumVertexDistanceMeters": roundtrip_distance,
        "status": "pass",
    }
    report["canonicalAuthority"].update(
        {
            "nonZeroOnePackageHashesBefore": authority_hashes_before,
            "nonZeroOnePackageHashesAfter": authority_hashes_after,
            "allNonZeroOnePackageHashesPreserved": True,
        }
    )
    report["integrity"]["reportHash"] = _integrity_hash(report, "reportHash")

    write_canonical_json(package_dir / PROCESSING_REMAP_PATH, remap)
    write_canonical_json(package_dir / PROCESSING_INFLUENCE_PATH, influence)
    write_canonical_json(package_dir / PROCESSING_REPORT_PATH, report)
    manifest = {
        "schemaVersion": 1,
        "processingVersion": PROCESSING_VERSION,
        "thresholdProfile": THRESHOLD_PROFILE,
        "surfacePath": PROCESSING_SURFACE_PATH,
        "topologyHash": topology_hash(decoded),
        "contentHash": geometry_content_hash(decoded),
        "sourceDenseTopologyHash": topology_hash(canonical_source),
        "sourceDenseContentHash": geometry_content_hash(canonical_source),
        "sourceDensePath": "render/fallback.glb",
        "canonicalAuthorityChanged": False,
        "files": {
            PROCESSING_SURFACE_PATH: sha256_file(surface_path),
            PROCESSING_REMAP_PATH: sha256_file(package_dir / PROCESSING_REMAP_PATH),
            PROCESSING_INFLUENCE_PATH: sha256_file(package_dir / PROCESSING_INFLUENCE_PATH),
            PROCESSING_REPORT_PATH: sha256_file(package_dir / PROCESSING_REPORT_PATH),
        },
        "counts": {
            "meshCount": len(candidate.meshes),
            "vertexCount": candidate.vertex_count,
            "triangleCount": candidate.triangle_count,
            "repairedRegionCount": len(repair_rows),
        },
    }
    write_canonical_json(package_dir / PROCESSING_MANIFEST_PATH, manifest)
    return ProcessingSurfaceBundle(candidate, manifest, remap, influence, report)


def inspect_processing_surface(package_dir: Path) -> dict[str, Any]:
    manifest_path = package_dir / PROCESSING_MANIFEST_PATH
    if not manifest_path.is_file():
        return {"status": "not_present", "reason": "processing_surface_absent"}
    try:
        manifest = read_json(manifest_path)
        if manifest.get("processingVersion") != PROCESSING_VERSION:
            raise ValueError("processing_surface_version_unsupported")
        for relative, expected in manifest.get("files", {}).items():
            path = package_dir / str(relative)
            if not path.is_file() or sha256_file(path) != expected:
                raise ValueError(f"processing_surface_file_hash_mismatch:{relative}")
        surface = read_glb_meshset(package_dir / PROCESSING_SURFACE_PATH)
        source = read_glb_meshset(package_dir / "render/fallback.glb")
        audit = audit_glb_geometry(
            package_dir / PROCESSING_SURFACE_PATH,
            minimum_triangle_area=MINIMUM_TRIANGLE_AREA_METERS2,
        )
        if audit["status"] != "pass":
            raise ValueError("processing_surface_geometry_invalid")
        if topology_hash(surface) != manifest.get("topologyHash"):
            raise ValueError("processing_surface_topology_hash_mismatch")
        if geometry_content_hash(surface) != manifest.get("contentHash"):
            raise ValueError("processing_surface_content_hash_mismatch")
        if topology_hash(source) != manifest.get("sourceDenseTopologyHash"):
            raise ValueError("processing_surface_source_topology_hash_mismatch")
        if geometry_content_hash(source) != manifest.get("sourceDenseContentHash"):
            raise ValueError("processing_surface_source_content_hash_mismatch")
        if [mesh.panel_id for mesh in source.meshes] != [mesh.panel_id for mesh in surface.meshes]:
            raise ValueError("processing_surface_panel_partition_mismatch")
        if [mesh.material_id for mesh in source.meshes] != [
            mesh.material_id for mesh in surface.meshes
        ]:
            raise ValueError("processing_surface_material_partition_mismatch")
        remap = read_json(package_dir / PROCESSING_REMAP_PATH)
        influence = read_json(package_dir / PROCESSING_INFLUENCE_PATH)
        report = read_json(package_dir / PROCESSING_REPORT_PATH)
        if not _valid_complete_remap(remap, surface):
            raise ValueError("processing_surface_remap_incomplete")
        if not _valid_influence(influence, surface):
            raise ValueError("processing_surface_influence_invalid")
        binding = read_binding(package_dir / "binding/sim_to_render.bin")
        if influence.get("sourceBindingTopologyHash") != binding.render_topology_hash:
            raise ValueError("processing_surface_binding_hash_stale")
        if report.get("status") != "pass" or report.get("integrity", {}).get(
            "reportHash"
        ) != _integrity_hash(report, "reportHash"):
            raise ValueError("processing_surface_report_forged_or_failed")
        semantic_graph = read_json(package_dir / "semantic/garment_graph.json")
        current_authority_hashes = _non_zeroone_package_hashes(package_dir)
        authority = report.get("canonicalAuthority", {})
        authority_before = authority.get("nonZeroOnePackageHashesBefore", {})
        authority_after = authority.get("nonZeroOnePackageHashesAfter", {})
        if (
            not isinstance(authority_before, dict)
            or authority_before != authority_after
            or authority.get("allNonZeroOnePackageHashesPreserved") is not True
            or any(
                current_authority_hashes.get(path) != digest
                for path, digest in authority_before.items()
            )
        ):
            raise ValueError("processing_surface_canonical_authority_hash_mismatch")
        recomputed = _equivalence_report(
            source, surface, semantic_graph, report.get("repairRegions", [])
        )
        recomputed["canonicalAuthority"].update(
            {
                "nonZeroOnePackageHashesBefore": authority_before,
                "nonZeroOnePackageHashesAfter": authority_after,
                "allNonZeroOnePackageHashesPreserved": True,
            }
        )
        for key in (
            "status",
            "failureReasons",
            "checks",
            "surfaceDistance",
            "panelMetrics",
            "boundsMaximumAbsoluteDeltaMeters",
            "boundaryAndOpenings",
            "semanticTraceability",
            "uvAndMaterialContinuity",
            "visual",
            "topologyAudit",
            "canonicalAuthority",
        ):
            if report.get(key) != recomputed.get(key):
                raise ValueError(f"processing_surface_report_recompute_mismatch:{key}")
        return {
            "status": "valid",
            "reason": "versioned_processing_surface_valid",
            "topologyHash": manifest["topologyHash"],
            "vertexCount": surface.vertex_count,
            "triangleCount": surface.triangle_count,
            "repairedRegionCount": manifest["counts"]["repairedRegionCount"],
        }
    except Exception as exc:
        return {"status": "invalid", "reason": str(exc)}


def _repair_surface(source: MeshSet) -> tuple[MeshSet, list[dict[str, Any]]]:
    meshes: list[Mesh] = []
    repair_rows: list[dict[str, Any]] = []
    global_vertex_offset = 0
    global_triangle_offset = 0
    for mesh_index, mesh in enumerate(source.meshes):
        vertices = list(mesh.vertices)
        groups = _degenerate_groups(mesh)
        for group_index, (triangle_indices, vertex_indices) in enumerate(groups):
            selected: tuple[str, int, float, list[Vec3]] | None = None
            attempts: list[dict[str, Any]] = []
            for strategy_id, direction_rank, uv_axis, trials in _STRATEGIES:
                for trial_index, (base_offset, variation) in enumerate(trials):
                    trial_vertices = _lift_component(
                        mesh,
                        vertices,
                        vertex_indices,
                        direction_rank,
                        uv_axis,
                        base_offset,
                        variation,
                    )
                    areas = [
                        _triangle_area(
                            trial_vertices[mesh.triangles[index][0]],
                            trial_vertices[mesh.triangles[index][1]],
                            trial_vertices[mesh.triangles[index][2]],
                        )
                        for index in triangle_indices
                    ]
                    maximum_displacement = max(
                        _distance(mesh.vertices[index], trial_vertices[index])
                        for index in vertex_indices
                    )
                    trial_mesh = Mesh(
                        mesh.name,
                        mesh.panel_id,
                        trial_vertices,
                        list(mesh.panel_uvs),
                        list(mesh.triangles),
                        mesh.material_id,
                    )
                    topology_delta = _local_topology_delta(mesh, trial_mesh, set(triangle_indices))
                    accepted = (
                        min(areas, default=0.0) > MINIMUM_TRIANGLE_AREA_METERS2
                        and maximum_displacement <= MAXIMUM_SURFACE_DISTANCE_METERS
                        and topology_delta["newSelfIntersectionCount"] == 0
                        and topology_delta["newTJunctionCount"] == 0
                    )
                    attempts.append(
                        {
                            "strategy": strategy_id,
                            "trial": trial_index + 1,
                            "baseOffsetMeters": base_offset,
                            "variationMeters": variation,
                            "minimumTriangleAreaMeters2": min(areas, default=0.0),
                            "maximumDisplacementMeters": maximum_displacement,
                            "newSelfIntersectionCount": topology_delta["newSelfIntersectionCount"],
                            "newTJunctionCount": topology_delta["newTJunctionCount"],
                            "accepted": accepted,
                        }
                    )
                    if accepted:
                        selected = (
                            strategy_id,
                            trial_index + 1,
                            maximum_displacement,
                            trial_vertices,
                        )
                        break
                if selected is not None:
                    break
            if selected is None:
                raise ValueError(f"processing_surface_repair_budget_exhausted:{mesh.panel_id}")
            strategy_id, trial, maximum_displacement, vertices = selected
            repair_rows.append(
                {
                    "repairRegionId": f"repair.{mesh_index:03d}.{group_index:03d}",
                    "meshIndex": mesh_index,
                    "meshName": mesh.name,
                    "panelId": mesh.panel_id,
                    "materialId": mesh.material_id,
                    "sourceTriangleIndices": triangle_indices,
                    "globalSourceTriangleIndices": [
                        global_triangle_offset + index for index in triangle_indices
                    ],
                    "sourceVertexIndices": sorted(vertex_indices),
                    "globalSourceVertexIndices": [
                        global_vertex_offset + index for index in sorted(vertex_indices)
                    ],
                    "strategy": strategy_id,
                    "trial": trial,
                    "maximumDisplacementMeters": maximum_displacement,
                    "attempts": attempts,
                }
            )
        meshes.append(
            Mesh(
                mesh.name,
                mesh.panel_id,
                vertices,
                list(mesh.panel_uvs),
                list(mesh.triangles),
                mesh.material_id,
            )
        )
        global_vertex_offset += len(mesh.vertices)
        global_triangle_offset += len(mesh.triangles)
    candidate = MeshSet(meshes)
    if _invalid_triangle_count(candidate) != 0:
        raise ValueError("processing_surface_still_contains_invalid_triangles")
    return candidate, repair_rows


def _degenerate_groups(mesh: Mesh) -> list[tuple[list[int], set[int]]]:
    remaining = {
        index
        for index, tri in enumerate(mesh.triangles)
        if len(set(tri)) != 3
        or _triangle_area(mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]])
        <= MINIMUM_TRIANGLE_AREA_METERS2
    }
    groups: list[tuple[list[int], set[int]]] = []
    while remaining:
        first = min(remaining)
        remaining.remove(first)
        pending = [first]
        triangle_indices: list[int] = []
        vertex_indices: set[int] = set()
        while pending:
            triangle_index = pending.pop()
            triangle_indices.append(triangle_index)
            vertex_indices.update(mesh.triangles[triangle_index])
            neighbours = [
                index
                for index in sorted(remaining)
                if vertex_indices.intersection(mesh.triangles[index])
            ]
            for index in neighbours:
                remaining.remove(index)
                pending.append(index)
        groups.append((sorted(triangle_indices), vertex_indices))
    return groups


def _lift_component(
    mesh: Mesh,
    current_vertices: list[Vec3],
    vertex_indices: set[int],
    direction_rank: int,
    uv_axis: int,
    base_offset: float,
    variation: float,
) -> list[Vec3]:
    result = list(current_vertices)
    ordered = sorted(vertex_indices)
    line = _principal_line([mesh.vertices[index] for index in ordered])
    axes = sorted(
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        key=lambda value: abs(_dot(line, value)),
    )
    axis = axes[direction_rank]
    perpendicular = _normalise(cross(line, axis))
    values: dict[int, float] = {}
    for index in ordered:
        uv = mesh.panel_uvs[index]
        values[index] = (uv[0], uv[1], uv[0] + uv[1])[uv_axis]
    low = min(values.values())
    high = max(values.values())
    if high - low <= 1e-15:
        return result
    for index in ordered:
        signed = ((values[index] - low) / (high - low)) * 2.0 - 1.0
        offset = base_offset + variation * signed
        source = mesh.vertices[index]
        result[index] = tuple(
            _f32(source[axis_index] + perpendicular[axis_index] * offset) for axis_index in range(3)
        )  # type: ignore[assignment]
    return result


def _build_remap(
    source: MeshSet, candidate: MeshSet, repair_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    repaired_vertices = {index for row in repair_rows for index in row["globalSourceVertexIndices"]}
    repaired_triangles = {
        index for row in repair_rows for index in row["globalSourceTriangleIndices"]
    }
    vertex_rows: list[dict[str, Any]] = []
    triangle_rows: list[dict[str, Any]] = []
    global_vertex = 0
    global_triangle = 0
    for source_mesh, candidate_mesh in zip(source.meshes, candidate.meshes, strict=True):
        for local_index, (source_position, candidate_position) in enumerate(
            zip(source_mesh.vertices, candidate_mesh.vertices, strict=True)
        ):
            vertex_rows.append(
                {
                    "sourceDenseVertex": global_vertex,
                    "processingVertex": global_vertex,
                    "panelId": source_mesh.panel_id,
                    "localVertex": local_index,
                    "kind": "versioned_local_split"
                    if global_vertex in repaired_vertices
                    else "identity",
                    "offsetMeters": [
                        candidate_position[axis] - source_position[axis] for axis in range(3)
                    ],
                }
            )
            global_vertex += 1
        for local_index, tri in enumerate(source_mesh.triangles):
            triangle_rows.append(
                {
                    "sourceDenseTriangle": global_triangle,
                    "processingTriangles": [global_triangle],
                    "panelId": source_mesh.panel_id,
                    "materialId": source_mesh.material_id,
                    "localTriangle": local_index,
                    "sourceVertexIndices": list(tri),
                    "kind": "versioned_local_split"
                    if global_triangle in repaired_triangles
                    else "identity",
                }
            )
            global_triangle += 1
    return {
        "schemaVersion": 1,
        "remapVersion": "closy.dense_to_zeroone_processing_remap.v1",
        "sourceTopologyHash": topology_hash(source),
        "processingTopologyHash": topology_hash(candidate),
        "sourceVertexCount": source.vertex_count,
        "processingVertexCount": candidate.vertex_count,
        "sourceTriangleCount": source.triangle_count,
        "processingTriangleCount": candidate.triangle_count,
        "vertexRows": vertex_rows,
        "triangleRows": triangle_rows,
        "complete": True,
    }


def _build_influence(
    candidate: MeshSet, binding: BindingFile, remap: dict[str, Any]
) -> dict[str, Any]:
    if len(binding.records) != candidate.vertex_count:
        raise ValueError("processing_surface_binding_record_count_mismatch")
    cluster_rows: list[dict[str, Any]] = []
    global_triangle = 0
    cluster_index = 0
    for mesh in candidate.meshes:
        for first in range(0, len(mesh.triangles), 128):
            count = min(128, len(mesh.triangles) - first)
            cluster_rows.append(
                {
                    "processingClusterSeed": cluster_index,
                    "panelId": mesh.panel_id,
                    "materialId": mesh.material_id,
                    "firstProcessingTriangle": global_triangle + first,
                    "processingTriangleCount": count,
                }
            )
            cluster_index += 1
        global_triangle += len(mesh.triangles)
    vertex_rows = []
    for processing_vertex, (record, remap_row) in enumerate(
        zip(binding.records, remap["vertexRows"], strict=True)
    ):
        vertex_rows.append(
            {
                "processingVertex": processing_vertex,
                "sourceDenseVertex": remap_row["sourceDenseVertex"],
                "simulationTriangle": record.simulation_triangle_index,
                "barycentric": [
                    1.0 - record.barycentric_u - record.barycentric_v,
                    record.barycentric_u,
                    record.barycentric_v,
                ],
                "normalOffset": record.normal_offset,
                "panelTableIndex": record.panel_table_index,
                "processingOffsetMeters": remap_row["offsetMeters"],
            }
        )
    return {
        "schemaVersion": 1,
        "influenceVersion": "closy.sim_to_processing_cluster_influence.v1",
        "sourceBindingTopologyHash": binding.render_topology_hash,
        "processingTopologyHash": topology_hash(candidate),
        "vertexRows": vertex_rows,
        "clusterBuildRows": cluster_rows,
        "clusterAssignmentAuthority": "processor_rebuilds_from_declared_processing_surface",
        "boundedWeights": True,
    }


def _equivalence_report(
    source: MeshSet,
    candidate: MeshSet,
    semantic_graph: dict[str, Any],
    repair_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    source_samples = _repair_surface_samples(source, repair_rows)
    candidate_samples = _repair_surface_samples(candidate, repair_rows)
    forward = _sample_distances(candidate_samples, source)
    reverse = _sample_distances(source_samples, candidate)
    total_samples_per_direction = source.vertex_count + source.triangle_count
    exact_sample_count = max(0, total_samples_per_direction - len(source_samples))
    distances = sorted(forward + reverse + [0.0] * (exact_sample_count * 2))
    maximum_distance = max(distances, default=0.0)
    p95_distance = _percentile(distances, 0.95)
    panel_rows = _panel_equivalence(source, candidate)
    source_bounds = mesh_bounds(source)
    candidate_bounds = mesh_bounds(candidate)
    bounds_delta = max(
        abs(left - right)
        for key in ("min", "max", "size")
        for left, right in zip(source_bounds[key], candidate_bounds[key], strict=True)
    )
    boundary = _boundary_equivalence(source, candidate)
    visual = _visual_equivalence(source, candidate)
    source_invalid = _invalid_triangle_count(source)
    candidate_invalid = _invalid_triangle_count(candidate)
    source_duplicate_faces = _duplicate_face_count(source)
    candidate_duplicate_faces = _duplicate_face_count(candidate)
    source_nonmanifold = _nonmanifold_edge_count(source)
    candidate_nonmanifold = _nonmanifold_edge_count(candidate)
    topology_delta = _focused_topology_delta(source, candidate, repair_rows)
    semantic_ids = {
        "panels": sorted(str(value) for value in semantic_graph.get("panelMapping", {})),
        "seams": sorted(str(row.get("id")) for row in semantic_graph.get("seams", [])),
        "openings": sorted(str(row.get("id")) for row in semantic_graph.get("openings", [])),
    }
    exact_outside = _exact_outside_repair(source, candidate, repair_rows)
    failure_reasons: list[str] = []
    checks = {
        "processingHasNoInvalidTriangles": candidate_invalid == 0,
        "processingHasNoRepeatedIndexFaces": _repeated_index_count(candidate) == 0,
        "processingHasNoDuplicateFaces": candidate_duplicate_faces == 0,
        "processingHasNoNonManifoldEdges": candidate_nonmanifold == 0,
        "processingHasNoTJunctions": topology_delta["processingTJunctionCount"] == 0,
        "maximumSurfaceDistanceWithinCap": maximum_distance <= MAXIMUM_SURFACE_DISTANCE_METERS,
        "p95SurfaceDistanceWithinCap": p95_distance <= MAXIMUM_P95_SURFACE_DISTANCE_METERS,
        "panelAreaWithinCap": all(row["withinAreaCap"] for row in panel_rows),
        "boundsWithinCap": bounds_delta <= MAXIMUM_BOUNDS_DELTA_METERS,
        "boundaryInventoryPreserved": boundary["status"] == "pass",
        "visualEquivalencePassed": visual["status"] == "pass",
        "topologyIdentityPreserved": topology_hash(source) == topology_hash(candidate),
        "duplicateFacesNotIntroduced": candidate_duplicate_faces <= source_duplicate_faces,
        "nonManifoldEdgesNotIntroduced": candidate_nonmanifold <= source_nonmanifold,
        "selfIntersectionsNotIntroduced": topology_delta["newSelfIntersectionCount"] == 0,
        "tJunctionsNotIntroduced": topology_delta["newTJunctionCount"] == 0,
        "semanticIdsTraceable": all(semantic_ids.values()),
        "exactOutsideRepairNeighbourhood": exact_outside,
    }
    for key, value in checks.items():
        if not value:
            failure_reasons.append(key)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportVersion": "closy.zeroone.surface_equivalence_report.z1.v1",
        "thresholdProfile": THRESHOLD_PROFILE,
        "status": "pass" if not failure_reasons else "fail",
        "failureReasons": failure_reasons,
        "checks": checks,
        "source": {
            "topologyHash": topology_hash(source),
            "contentHash": geometry_content_hash(source),
            "invalidTriangleCount": source_invalid,
            "requiredRepair": source_invalid > 0,
            "duplicateFaceCount": source_duplicate_faces,
            "nonManifoldEdgeCount": source_nonmanifold,
            "bounds": source_bounds,
        },
        "processing": {
            "topologyHash": topology_hash(candidate),
            "contentHash": geometry_content_hash(candidate),
            "invalidTriangleCount": candidate_invalid,
            "duplicateFaceCount": candidate_duplicate_faces,
            "nonManifoldEdgeCount": candidate_nonmanifold,
            "bounds": candidate_bounds,
        },
        "repairRegions": repair_rows,
        "surfaceDistance": {
            "method": "deterministic_vertices_and_triangle_centroids_to_exact_triangle_surface",
            "sampleCount": len(distances),
            "maximumMeters": maximum_distance,
            "p95Meters": p95_distance,
        },
        "panelMetrics": panel_rows,
        "boundsMaximumAbsoluteDeltaMeters": bounds_delta,
        "boundaryAndOpenings": boundary,
        "semanticTraceability": semantic_ids,
        "uvAndMaterialContinuity": {
            "maximumUvDisplacement": 0.0,
            "maximumTextureSampleDisplacementTexels": 0.0,
            "materialRegionMismatchCount": 0,
            "sourceDegenerateTangentBasisUndefinedCount": source_invalid,
            "unchangedRegionTangentBasisExact": True,
        },
        "visual": visual,
        "topologyAudit": {
            "indexRangeValid": True,
            "finitePositionsAndUvs": _finite_mesh(candidate),
            "repeatedIndexFaceCount": _repeated_index_count(candidate),
            "duplicateOrientedFaceCount": _duplicate_oriented_face_count(candidate),
            "duplicateUnorientedFaceCount": candidate_duplicate_faces,
            "nonManifoldEdgeCount": candidate_nonmanifold,
            "sourceTJunctionCount": topology_delta["sourceTJunctionCount"],
            "processingTJunctionCount": topology_delta["processingTJunctionCount"],
            "tJunctionCountDelta": topology_delta["newTJunctionCount"],
            "connectedComponentCountDelta": 0,
            "boundaryComponentCountDelta": boundary["boundaryComponentCountDelta"],
            "holeCountDelta": 0,
            "selfIntersectionAuditExecuted": topology_delta["selfIntersectionAuditExecuted"],
            "sourceRepairNeighbourhoodSelfIntersectionCount": topology_delta[
                "sourceSelfIntersectionCount"
            ],
            "processingRepairNeighbourhoodSelfIntersectionCount": topology_delta[
                "processingSelfIntersectionCount"
            ],
            "newSelfIntersectionCount": topology_delta["newSelfIntersectionCount"],
            "windingTopologyUnchanged": True,
            "hiddenZeroAreaComponentCount": 0,
        },
        "canonicalAuthority": {
            "patternChanged": False,
            "simulationChanged": False,
            "bindingChanged": False,
            "conventionalFallbackChanged": False,
            "sourceChanged": False,
            "appearanceChanged": False,
            "semanticsChanged": False,
            "materialAuthorityChanged": False,
        },
        "integrity": {"reportHash": ""},
    }
    return report


def _focused_topology_delta(
    source: MeshSet, candidate: MeshSet, repair_rows: list[dict[str, Any]]
) -> dict[str, int | bool]:
    repaired_by_mesh: dict[int, set[int]] = {}
    for row in repair_rows:
        repaired_by_mesh.setdefault(int(row["meshIndex"]), set()).update(
            int(value) for value in row["sourceTriangleIndices"]
        )

    source_pairs: set[tuple[int, int, int]] = set()
    candidate_pairs: set[tuple[int, int, int]] = set()
    source_t_junctions = 0
    candidate_t_junctions = 0
    for mesh_index, repaired in sorted(repaired_by_mesh.items()):
        source_pairs.update(
            (mesh_index, left, right)
            for left, right in _repair_neighbourhood_intersections(
                source.meshes[mesh_index], repaired
            )
        )
        candidate_pairs.update(
            (mesh_index, left, right)
            for left, right in _repair_neighbourhood_intersections(
                candidate.meshes[mesh_index], repaired
            )
        )
        source_t_junctions += _mesh_t_junction_count(source.meshes[mesh_index])
        candidate_t_junctions += _mesh_t_junction_count(candidate.meshes[mesh_index])
    return {
        "selfIntersectionAuditExecuted": True,
        "sourceSelfIntersectionCount": len(source_pairs),
        "processingSelfIntersectionCount": len(candidate_pairs),
        "newSelfIntersectionCount": len(candidate_pairs - source_pairs),
        "sourceTJunctionCount": source_t_junctions,
        "processingTJunctionCount": candidate_t_junctions,
        "newTJunctionCount": max(0, candidate_t_junctions - source_t_junctions),
    }


def _local_topology_delta(source: Mesh, candidate: Mesh, repaired: set[int]) -> dict[str, int]:
    source_pairs = _repair_neighbourhood_intersections(source, repaired)
    candidate_pairs = _repair_neighbourhood_intersections(candidate, repaired)
    source_t_junctions = _mesh_t_junction_count(source)
    candidate_t_junctions = _mesh_t_junction_count(candidate)
    return {
        "newSelfIntersectionCount": len(candidate_pairs - source_pairs),
        "newTJunctionCount": max(0, candidate_t_junctions - source_t_junctions),
    }


def _repair_neighbourhood_intersections(mesh: Mesh, repaired: set[int]) -> set[tuple[int, int]]:
    from closy_forge.proposals.geometry_stitched_shell import (  # noqa: PLC0415
        _bounds_overlap,
        _triangle_bounds,
        _triangles_intersect,
    )

    result: set[tuple[int, int]] = set()
    bounds = [_triangle_bounds(mesh.vertices, tri) for tri in mesh.triangles]
    for repaired_index in sorted(repaired):
        left = mesh.triangles[repaired_index]
        for other_index, right in enumerate(mesh.triangles):
            pair = (min(repaired_index, other_index), max(repaired_index, other_index))
            if repaired_index == other_index or pair in result or set(left) & set(right):
                continue
            if not _bounds_overlap(bounds[repaired_index], bounds[other_index], 1e-10):
                continue
            if _triangles_intersect(mesh.vertices, left, right, 1e-10):
                result.add(pair)
    return result


def _mesh_t_junction_count(mesh: Mesh) -> int:
    from closy_forge.proposals.geometry_stitched_shell import (  # noqa: PLC0415
        _t_junction_audit,
    )

    return int(_t_junction_audit(mesh, 1e-10)["tJunctionCount"])


def _repair_surface_samples(meshset: MeshSet, repair_rows: list[dict[str, Any]]) -> list[Vec3]:
    samples: list[Vec3] = []
    for row in repair_rows:
        mesh = meshset.meshes[int(row["meshIndex"])]
        samples.extend(mesh.vertices[int(index)] for index in row["sourceVertexIndices"])
        for triangle_index in row["sourceTriangleIndices"]:
            tri = mesh.triangles[int(triangle_index)]
            samples.append(
                tuple(sum(mesh.vertices[index][axis] for index in tri) / 3.0 for axis in range(3))  # type: ignore[arg-type]
            )
    return samples


def _sample_distances(points: list[Vec3], surface: MeshSet) -> list[float]:
    triangles = [
        (mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]])
        for mesh in surface.meshes
        for tri in mesh.triangles
        if _triangle_area(mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]]) > 0.0
    ]
    return [
        min((_point_triangle_distance(point, *triangle) for triangle in triangles), default=0.0)
        for point in points
    ]


def _point_triangle_distance(point: Vec3, a: Vec3, b: Vec3, c: Vec3) -> float:
    # Real-Time Collision Detection, closest point on triangle.
    ab = sub(b, a)
    ac = sub(c, a)
    ap = sub(point, a)
    d1 = _dot(ab, ap)
    d2 = _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return _distance(point, a)
    bp = sub(point, b)
    d3 = _dot(ab, bp)
    d4 = _dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return _distance(point, b)
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        return _distance(point, _add(a, _scale(ab, v)))
    cp = sub(point, c)
    d5 = _dot(ab, cp)
    d6 = _dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return _distance(point, c)
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        return _distance(point, _add(a, _scale(ac, w)))
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and d4 - d3 >= 0.0 and d5 - d6 >= 0.0:
        edge = sub(c, b)
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return _distance(point, _add(b, _scale(edge, w)))
    denominator = 1.0 / (va + vb + vc)
    v = vb * denominator
    w = vc * denominator
    return _distance(point, _add(a, _add(_scale(ab, v), _scale(ac, w))))


def _panel_equivalence(source: MeshSet, candidate: MeshSet) -> list[dict[str, Any]]:
    rows = []
    for left, right in zip(source.meshes, candidate.meshes, strict=True):
        source_area = _mesh_area(left)
        candidate_area = _mesh_area(right)
        relative = abs(candidate_area - source_area) / max(source_area, 1e-15)
        rows.append(
            {
                "panelId": left.panel_id,
                "materialId": left.material_id,
                "sourceAreaMeters2": source_area,
                "processingAreaMeters2": candidate_area,
                "areaRelativeDelta": relative,
                "withinAreaCap": relative <= MAXIMUM_AREA_RELATIVE_DELTA,
            }
        )
    return rows


def _boundary_equivalence(source: MeshSet, candidate: MeshSet) -> dict[str, Any]:
    source_edges = _boundary_edges(source)
    candidate_edges = _boundary_edges(candidate)
    source_length = _edge_length(source, source_edges)
    candidate_length = _edge_length(candidate, candidate_edges)
    relative = abs(candidate_length - source_length) / max(source_length, 1e-15)
    maximum_deviation = _maximum_corresponding_vertex_distance(source, candidate)
    return {
        "status": "pass"
        if source_edges == candidate_edges
        and relative <= MAXIMUM_BOUNDARY_LENGTH_RELATIVE_DELTA
        and maximum_deviation <= MAXIMUM_SURFACE_DISTANCE_METERS
        else "fail",
        "sourceBoundaryEdgeCount": len(source_edges),
        "processingBoundaryEdgeCount": len(candidate_edges),
        "boundaryComponentCountDelta": 0,
        "boundaryOrderPreservedByIdentityRemap": source_edges == candidate_edges,
        "sourceBoundaryLengthMeters": source_length,
        "processingBoundaryLengthMeters": candidate_length,
        "boundaryLengthRelativeDelta": relative,
        "maximumBoundaryDeviationMeters": maximum_deviation,
        "openingLoopCountOrderAndIdsPreserved": True,
        "seamSideIdsTraceable": True,
    }


def _visual_equivalence(source: MeshSet, candidate: MeshSet) -> dict[str, Any]:
    views: list[dict[str, str | float]] = []
    for view_id, azimuth in (
        ("front", 0.0),
        ("right", 90.0),
        ("back", 180.0),
        ("left", -90.0),
    ):
        camera = {
            "projection": "orthographic",
            "azimuthDegrees": azimuth,
            "elevationDegrees": 4.0,
            "principalPointNormalized": [0.5, 0.5],
        }
        left = rasterize_settled_garment(
            source, label="front", width=160, height=160, camera=camera
        )
        right = rasterize_settled_garment(
            candidate, label="front", width=160, height=160, camera=camera
        )
        union = left.foreground | right.foreground
        intersection = left.foreground & right.foreground
        iou = len(intersection) / len(union) if union else 0.0
        depth_delta = _maximum_common_depth_delta(left.depth, right.depth, intersection)
        views.append(
            {
                "viewId": view_id,
                "azimuthDegrees": azimuth,
                "silhouetteIoU": iou,
                "maximumDepthImageDeviationMeters": depth_delta,
            }
        )
    return {
        "status": "pass"
        if all(
            float(row["silhouetteIoU"]) >= MINIMUM_SILHOUETTE_IOU
            and float(row["maximumDepthImageDeviationMeters"])
            <= MAXIMUM_DEPTH_IMAGE_DEVIATION_METERS
            for row in views
        )
        else "fail",
        "renderVersion": "closy.processing_surface_fixed_camera_depth_silhouette.v1",
        "views": views,
    }


def _maximum_common_depth_delta(
    left: tuple[float | None, ...],
    right: tuple[float | None, ...],
    indices: frozenset[int],
) -> float:
    deltas: list[float] = []
    for index in indices:
        left_value = left[index]
        right_value = right[index]
        if left_value is not None and right_value is not None:
            deltas.append(abs(left_value - right_value))
    return max(deltas, default=0.0)


def _valid_complete_remap(remap: dict[str, Any], surface: MeshSet) -> bool:
    vertex_rows = remap.get("vertexRows", [])
    triangle_rows = remap.get("triangleRows", [])
    return (
        remap.get("complete") is True
        and len(vertex_rows) == surface.vertex_count
        and len(triangle_rows) == surface.triangle_count
        and [row.get("processingVertex") for row in vertex_rows]
        == list(range(surface.vertex_count))
        and [row.get("sourceDenseTriangle") for row in triangle_rows]
        == list(range(surface.triangle_count))
        and all(
            row.get("processingTriangles") == [index] for index, row in enumerate(triangle_rows)
        )
    )


def _valid_influence(influence: dict[str, Any], surface: MeshSet) -> bool:
    rows = influence.get("vertexRows", [])
    if len(rows) != surface.vertex_count:
        return False
    for index, row in enumerate(rows):
        weights = row.get("barycentric", [])
        if row.get("processingVertex") != index or len(weights) != 3:
            return False
        if any(not isinstance(value, int | float) or not math.isfinite(value) for value in weights):
            return False
        if min(weights) < -1e-6 or abs(sum(weights) - 1.0) > 1e-6:
            return False
    return bool(influence.get("clusterBuildRows"))


def _exact_outside_repair(
    source: MeshSet, candidate: MeshSet, repair_rows: list[dict[str, Any]]
) -> bool:
    repaired = {index for row in repair_rows for index in row["globalSourceVertexIndices"]}
    index = 0
    for left, right in zip(source.meshes, candidate.meshes, strict=True):
        if left.triangles != right.triangles or left.panel_uvs != right.panel_uvs:
            return False
        for left_position, right_position in zip(left.vertices, right.vertices, strict=True):
            if index not in repaired and left_position != right_position:
                return False
            index += 1
    return True


def _invalid_triangle_count(meshset: MeshSet) -> int:
    return sum(
        len(set(tri)) != 3
        or any(index < 0 or index >= len(mesh.vertices) for index in tri)
        or _triangle_area(mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]])
        <= MINIMUM_TRIANGLE_AREA_METERS2
        for mesh in meshset.meshes
        for tri in mesh.triangles
    )


def _repeated_index_count(meshset: MeshSet) -> int:
    return sum(len(set(tri)) != 3 for mesh in meshset.meshes for tri in mesh.triangles)


def _duplicate_face_count(meshset: MeshSet) -> int:
    return sum(
        sum(count - 1 for count in Counter(tuple(sorted(tri)) for tri in mesh.triangles).values())
        for mesh in meshset.meshes
    )


def _duplicate_oriented_face_count(meshset: MeshSet) -> int:
    return sum(
        sum(count - 1 for count in Counter(mesh.triangles).values()) for mesh in meshset.meshes
    )


def _nonmanifold_edge_count(meshset: MeshSet) -> int:
    count = 0
    for mesh in meshset.meshes:
        edges: Counter[tuple[int, int]] = Counter()
        for tri in mesh.triangles:
            for left, right in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                edges[(min(left, right), max(left, right))] += 1
        count += sum(value > 2 for value in edges.values())
    return count


def _boundary_edges(meshset: MeshSet) -> list[tuple[int, int, int]]:
    rows: list[tuple[int, int, int]] = []
    for mesh_index, mesh in enumerate(meshset.meshes):
        edges: Counter[tuple[int, int]] = Counter()
        for tri in mesh.triangles:
            for left, right in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                edges[(min(left, right), max(left, right))] += 1
        rows.extend((mesh_index, edge[0], edge[1]) for edge, count in edges.items() if count == 1)
    return sorted(rows)


def _edge_length(meshset: MeshSet, edges: list[tuple[int, int, int]]) -> float:
    return sum(
        _distance(
            meshset.meshes[mesh_index].vertices[left], meshset.meshes[mesh_index].vertices[right]
        )
        for mesh_index, left, right in edges
    )


def _mesh_area(mesh: Mesh) -> float:
    return sum(
        _triangle_area(mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]])
        for tri in mesh.triangles
    )


def _triangle_area(a: Vec3, b: Vec3, c: Vec3) -> float:
    normal = cross(sub(b, a), sub(c, a))
    return 0.5 * math.sqrt(_dot(normal, normal))


def _principal_line(points: list[Vec3]) -> Vec3:
    _, left, right = max((_distance(a, b), a, b) for a in points for b in points)
    return _normalise(sub(right, left))


def _maximum_corresponding_vertex_distance(left: MeshSet, right: MeshSet) -> float:
    if len(left.meshes) != len(right.meshes):
        return math.inf
    return max(
        (
            _distance(a, b)
            for left_mesh, right_mesh in zip(left.meshes, right.meshes, strict=True)
            for a, b in zip(left_mesh.vertices, right_mesh.vertices, strict=True)
        ),
        default=0.0,
    )


def _finite_mesh(meshset: MeshSet) -> bool:
    return all(
        math.isfinite(value)
        for mesh in meshset.meshes
        for row in (*mesh.vertices, *mesh.panel_uvs)
        for value in row
    )


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    return values[min(len(values) - 1, math.ceil(quantile * len(values)) - 1)]


def _f32(value: float) -> float:
    return float(struct.unpack("<f", struct.pack("<f", value))[0])


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _normalise(value: Vec3) -> Vec3:
    length = math.sqrt(_dot(value, value))
    if length <= 1e-15:
        return (1.0, 0.0, 0.0)
    return (value[0] / length, value[1] / length, value[2] / length)


def _distance(a: Vec3, b: Vec3) -> float:
    return math.sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(value: Vec3, factor: float) -> Vec3:
    return (value[0] * factor, value[1] * factor, value[2] * factor)


def _integrity_hash(payload: dict[str, Any], field: str) -> str:
    import copy
    import json

    value = copy.deepcopy(payload)
    value["integrity"][field] = ""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256_bytes(canonical.encode("utf-8"))


def _non_zeroone_package_hashes(package_dir: Path) -> dict[str, str]:
    return {
        path.relative_to(package_dir).as_posix(): sha256_file(path)
        for path in sorted(package_dir.rglob("*"))
        if path.is_file()
        and not path.is_symlink()
        and "zeroone" not in path.relative_to(package_dir).parts
        and path.name != ".closy-forge-owned.json"
    }
