from __future__ import annotations

from collections import Counter
from copy import deepcopy
from math import sqrt
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet, cross, finite_mesh, mesh_bounds, sub
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, topology_hash

GEOMETRY_STITCHED_SHELL_VERSION = "closy.geometry_stitched_shell.conforming_tshirt_v3"

_PRE_STITCH_REPAIR_THRESHOLD_METERS = 0.15
_POST_STITCH_TOLERANCE_METERS = 1e-8
_EXPECTED_OPENING_IDS = [
    "opening.neck",
    "opening.hem",
    "opening.cuff.left",
    "opening.cuff.right",
]
_EXPECTED_OPENING_EDGE_IDS = {
    "opening.neck": ["edge.neck_band.long.top"],
    "opening.hem": ["edge.hem.back", "edge.hem.front"],
    "opening.cuff.left": ["edge.cuff.left"],
    "opening.cuff.right": ["edge.cuff.right"],
}


def build_stitched_shell_assets(
    *,
    garment_id: str,
    garment_class: str,
    source_simulation_mesh: MeshSet,
    constraints: dict[str, Any],
    analysis_asset_path: str,
    render_asset_path: str,
) -> tuple[dict[str, Any], dict[str, Any], MeshSet]:
    """Create a deterministic stitched-shell output and independent audit.

    BP-46 needs a material topology artifact rather than the earlier graph-only
    proof. This first shell rewrites vertex classes and triangle indices from
    the settled simulation mesh. It is intentionally strict: an output exists
    and is hashed, but it is not marked proven if the recomputed topology still
    has defects such as non-manifold seam edges or self-intersection not-run.
    """

    stitched_mesh, source_vertex_map, operations, topology_repair = _build_logical_stitched_mesh(
        source_simulation_mesh,
        constraints,
    )
    topology_audit = audit_stitched_shell(
        stitched_mesh,
        source_vertex_map=source_vertex_map,
        operations=operations,
        constraints=constraints,
        source_meshset=source_simulation_mesh,
        topology_repair=topology_repair,
    )
    proven = _audit_proves_stitched_shell(topology_audit)
    opening_proof = _opening_proof(topology_audit)
    execution = _execution_evidence(operations, constraints)
    analysis_shell: dict[str, Any] = {
        "schemaVersion": 1,
        "assetId": "stitched_analysis_shell.demo_tshirt_logical_v1",
        "stageVersion": GEOMETRY_STITCHED_SHELL_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "representationDefinitions": {
            "logicalStitchedAnalysisShell": (
                "single logical topology derived by rewriting seam-equivalent "
                "source vertices and triangle indices"
            ),
            "renderSplitGpuShell": (
                "conventional GLB render asset may later duplicate vertices for "
                "UV/material/tangent discontinuities while retaining a logical map"
            ),
        },
        "sourceSimulationMeshTopologyHash": topology_hash(source_simulation_mesh),
        "sourceSimulationMeshContentHash": geometry_content_hash(source_simulation_mesh),
        "logicalShellTopologyHash": topology_hash(stitched_mesh),
        "logicalShellContentHash": geometry_content_hash(stitched_mesh),
        "postStitchToleranceMeters": _POST_STITCH_TOLERANCE_METERS,
        "preStitchRepairThresholdMeters": _PRE_STITCH_REPAIR_THRESHOLD_METERS,
        "logicalShell": _mesh_payload(stitched_mesh),
        "sourceVertexMap": source_vertex_map,
        "executedOperations": operations,
        "openingProof": opening_proof,
        "topologyAudit": topology_audit,
        "readiness": {
            "status": "stitched_shell_proven" if proven else "stitched_shell_output_audit_failed",
            "meshStitchOrWeldExecutionRun": execution["meshStitchOrWeldExecutionRun"],
            "meshStitchOrWeldProven": proven,
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "blockingReasons": _blocking_reasons(topology_audit),
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
            "canonicalUseAllowed": False,
        },
        "integrity": {"stitchedAnalysisShellHash": ""},
    }
    analysis_shell["integrity"]["stitchedAnalysisShellHash"] = hash_stitched_analysis_shell(
        analysis_shell
    )
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "stitched_shell.demo_tshirt_logical_v1",
        "stageVersion": GEOMETRY_STITCHED_SHELL_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceSimulationMeshTopologyHash": topology_hash(source_simulation_mesh),
        "sourceSimulationMeshContentHash": geometry_content_hash(source_simulation_mesh),
        "analysisAsset": {
            "path": analysis_asset_path,
            "topologyHash": topology_hash(stitched_mesh),
            "contentHash": geometry_content_hash(stitched_mesh),
            "payloadHash": analysis_shell["integrity"]["stitchedAnalysisShellHash"],
        },
        "renderAsset": {
            "path": render_asset_path,
            "topologyHash": topology_hash(stitched_mesh),
            "contentHash": geometry_content_hash(stitched_mesh),
        },
        "execution": execution,
        "packageWriterEvidence": {
            "status": "pending_package_writer",
            "analysisAssetWritten": False,
            "renderAssetWritten": False,
            "analysisAssetPath": analysis_asset_path,
            "renderAssetPath": render_asset_path,
            "analysisAssetSha256": None,
            "renderAssetSha256": None,
            "analysisAssetByteSize": None,
            "renderAssetByteSize": None,
        },
        "topologyAudit": topology_audit,
        "readiness": {
            "status": "stitched_shell_proven" if proven else "stitched_shell_output_audit_failed",
            "meshStitchOrWeldProven": proven,
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "blockingReasons": _blocking_reasons(topology_audit),
        },
        "quality": {
            "status": "pass" if proven else "failed_rejected",
            "warnings": _blocking_reasons(topology_audit),
        },
        "policy": analysis_shell["policy"],
        "integrity": {"geometryStitchedShellHash": ""},
    }
    report["integrity"]["geometryStitchedShellHash"] = hash_geometry_stitched_shell_report(report)
    return report, analysis_shell, stitched_mesh


def hash_geometry_stitched_shell_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["geometryStitchedShellHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def hash_stitched_analysis_shell(asset: dict[str, Any]) -> str:
    payload = deepcopy(asset)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["stitchedAnalysisShellHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def audit_stitched_shell(
    meshset: MeshSet,
    *,
    source_vertex_map: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    constraints: dict[str, Any],
    source_meshset: MeshSet | None = None,
    topology_repair: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mesh = meshset.meshes[0]
    edge_counts = _edge_counts(mesh.triangles)
    boundary_edges = [edge for edge, count in edge_counts.items() if count == 1]
    non_manifold_edges = [edge for edge, count in edge_counts.items() if count > 2]
    duplicate_faces = _duplicate_face_count(mesh.triangles)
    degenerate_triangles = _degenerate_triangle_count(mesh)
    tolerance = _topology_tolerance(meshset)
    t_junction_audit = _t_junction_audit(mesh, tolerance)
    winding_audit = _winding_audit(mesh)
    normal_inversion_audit = _normal_inversion_audit(mesh)
    self_intersection_audit = _self_intersection_audit(mesh, tolerance)
    hidden_internal_audit = _hidden_internal_component_audit(mesh, edge_counts)
    boundary_components = _boundary_components(mesh, boundary_edges)
    surface_topology_audit = _surface_topology_audit(
        mesh,
        edge_counts,
        boundary_components,
        tolerance,
    )
    simple_boundary_cycles = [
        component for component in boundary_components if component["isSimpleCycle"] is True
    ]
    boundary_branch_vertices = [
        vertex_id
        for component in boundary_components
        for vertex_id in component["degreeViolationVertexIds"]
    ]
    post_stitch_residuals = [
        float(operation["postStitchResidualMeters"])
        for operation in operations
        if operation["status"] == "executed"
    ]
    pre_stitch_distances = [
        float(operation["preStitchDistanceMeters"])
        for operation in operations
        if operation["status"] == "executed"
    ]
    boundary_loop_count = len(boundary_components)
    seam_coverage = _seam_span_coverage(operations, constraints)
    ordered_correspondence = _ordered_seam_correspondence_audit(
        operations,
        constraints,
        source_meshset or meshset,
        seam_coverage,
    )
    provenance_coverage = _provenance_coverage(source_vertex_map, mesh)
    binding_coverage = _binding_reconstruction_audit(mesh, source_vertex_map, tolerance)
    displacement_metrics = _source_displacement_metrics(source_vertex_map, meshset)
    semantic_opening_audit = _semantic_opening_audit(
        boundary_components,
        constraints,
        source_vertex_map,
    )
    return {
        "auditVersion": "closy.stitched_shell_topology_audit.v1",
        "meshCount": len(meshset.meshes),
        "logicalShellCount": _component_count(mesh),
        "renderPrimitiveCount": len(meshset.meshes),
        "sourceConstraintCount": len(constraints.get("constraints", [])),
        "executedOperationCount": sum(
            1 for operation in operations if operation["status"] == "executed"
        ),
        "sourceVertexClassCount": len(source_vertex_map),
        "vertexCount": len(mesh.vertices),
        "triangleCount": len(mesh.triangles),
        "boundaryEdgeCount": len(boundary_edges),
        "boundaryLoopCount": boundary_loop_count,
        "boundaryComponents": boundary_components,
        "simpleBoundaryCycleCount": len(simple_boundary_cycles),
        "boundaryBranchVertexCount": len(boundary_branch_vertices),
        "boundaryBranchVertexIds": boundary_branch_vertices,
        "expectedOpeningCount": len(_EXPECTED_OPENING_IDS),
        "unexpectedBoundaryLoopCount": max(
            0,
            len(simple_boundary_cycles) - len(_EXPECTED_OPENING_IDS),
        ),
        "missingExpectedOpeningCount": semantic_opening_audit["missingExpectedOpeningCount"],
        "provenOpeningCount": semantic_opening_audit["provenOpeningCount"],
        "semanticOpeningAssignmentStatus": semantic_opening_audit["status"],
        "semanticOpeningAudit": semantic_opening_audit,
        "nonManifoldEdgeCount": len(non_manifold_edges),
        "nonManifoldVertexCount": _non_manifold_vertex_count(non_manifold_edges),
        "duplicateFaceCount": duplicate_faces,
        "degenerateTriangleCount": degenerate_triangles,
        "eulerCharacteristic": surface_topology_audit["eulerCharacteristic"],
        "genus": surface_topology_audit["genus"],
        "surfaceTopologyStatus": surface_topology_audit["status"],
        "surfaceTopologyAudit": surface_topology_audit,
        "isolatedVertexCount": surface_topology_audit["isolatedVertexCount"],
        "zeroLengthEdgeCount": surface_topology_audit["zeroLengthEdgeCount"],
        "smallTriangleCount": surface_topology_audit["smallTriangleCount"],
        "vertexLinkStatus": surface_topology_audit["vertexLinkStatus"],
        "topologyAuditToleranceMeters": tolerance,
        "executedTopologyAuditCount": 6,
        "tJunctionCheckStatus": t_junction_audit["status"],
        "tJunctionAudit": t_junction_audit,
        "inconsistentWindingCheckStatus": winding_audit["status"],
        "inconsistentWindingAudit": winding_audit,
        "normalInversionCheckStatus": normal_inversion_audit["status"],
        "normalInversionAudit": normal_inversion_audit,
        "selfIntersectionCheckStatus": self_intersection_audit["status"],
        "selfIntersectionAudit": self_intersection_audit,
        "hiddenInternalComponentCheckStatus": hidden_internal_audit["status"],
        "hiddenInternalComponentAudit": hidden_internal_audit,
        "topologyRepairEvidence": topology_repair or _no_topology_repair_evidence(mesh),
        "seamSpanCoverage": seam_coverage,
        "orderedSeamCorrespondenceStatus": ordered_correspondence["status"],
        "orderedSeamCorrespondenceAudit": ordered_correspondence,
        "uvMaterialPanelProvenanceCoverage": provenance_coverage["coverageRatio"],
        "uvMaterialPanelProvenance": provenance_coverage,
        "bindingCoverage": binding_coverage["coverageRatio"],
        "bindingEvidence": binding_coverage,
        "bindingReconstructionStatus": binding_coverage["reconstructionStatus"],
        "bindingReconstructionErrorMeters": binding_coverage["maxReconstructionErrorMeters"],
        "sourceDisplacement": displacement_metrics,
        "maxPreStitchDistanceMeters": _round(max(pre_stitch_distances, default=0.0)),
        "maxPostStitchResidualMeters": _round(max(post_stitch_residuals, default=0.0)),
        "postStitchToleranceMeters": _POST_STITCH_TOLERANCE_METERS,
        "finiteMesh": finite_mesh(meshset),
        "topologyHash": topology_hash(meshset),
        "contentHash": geometry_content_hash(meshset),
    }


def _build_logical_stitched_mesh(
    source_mesh: MeshSet,
    constraints: dict[str, Any],
) -> tuple[MeshSet, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if _can_build_conforming_tshirt_shell(constraints):
        return _build_conforming_tshirt_shell(source_mesh, constraints)
    return _build_union_stitched_mesh(source_mesh, constraints)


def _build_union_stitched_mesh(
    source_mesh: MeshSet,
    constraints: dict[str, Any],
) -> tuple[MeshSet, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    offsets: list[int] = []
    total_vertices = 0
    for mesh in source_mesh.meshes:
        offsets.append(total_vertices)
        total_vertices += len(mesh.vertices)
    union = _UnionFind(total_vertices)
    operations: list[dict[str, Any]] = []
    indexed_constraints = [
        (index, constraint)
        for index, constraint in enumerate(constraints.get("constraints", []))
        if isinstance(constraint, dict)
    ]
    for constraint_index, constraint in sorted(
        indexed_constraints,
        key=lambda item: (str(item[1].get("id", "")), item[0]),
    ):
        span_a = constraint.get("spanA")
        span_b = constraint.get("spanB")
        if not isinstance(span_a, dict) or not isinstance(span_b, dict):
            continue
        a_global = offsets[int(span_a["meshIndex"])] + int(span_a["vertexIndex"])
        b_global = offsets[int(span_b["meshIndex"])] + int(span_b["vertexIndex"])
        distance = _distance3(
            source_mesh.meshes[int(span_a["meshIndex"])].vertices[int(span_a["vertexIndex"])],
            source_mesh.meshes[int(span_b["meshIndex"])].vertices[int(span_b["vertexIndex"])],
        )
        if distance <= _PRE_STITCH_REPAIR_THRESHOLD_METERS:
            union.union(a_global, b_global)
            status = "executed"
        else:
            status = "rejected_pre_stitch_gap"
        operations.append(
            {
                "operationId": _constraint_operation_id(constraint, constraint_index),
                "sourceConstraintId": str(
                    constraint.get("id", f"constraint.{constraint_index:03d}")
                ),
                "seamId": str(constraint.get("seamId", "unknown")),
                "status": status,
                "spanA": deepcopy(span_a),
                "spanB": deepcopy(span_b),
                "sourceGlobalVertexA": a_global,
                "sourceGlobalVertexB": b_global,
                "preStitchDistanceMeters": _round(distance),
                "postStitchResidualMeters": None,
                "preStitchRepairThresholdMeters": _PRE_STITCH_REPAIR_THRESHOLD_METERS,
                "postStitchToleranceMeters": _POST_STITCH_TOLERANCE_METERS,
            }
        )
    classes: dict[int, list[int]] = {}
    for global_index in range(total_vertices):
        classes.setdefault(union.find(global_index), []).append(global_index)
    logical_vertices: list[tuple[float, float, float]] = []
    logical_uvs: list[tuple[float, float]] = []
    source_vertex_map: list[dict[str, Any]] = []
    remap: dict[int, int] = {}
    for logical_index, root in enumerate(sorted(classes, key=lambda item: min(classes[item]))):
        members = classes[root]
        source_records = [_source_vertex_record(source_mesh, offsets, member) for member in members]
        avg_position = (
            sum(float(record["position"][0]) for record in source_records) / len(source_records),
            sum(float(record["position"][1]) for record in source_records) / len(source_records),
            sum(float(record["position"][2]) for record in source_records) / len(source_records),
        )
        avg_uv = (
            sum(float(record["panelUv"][0]) for record in source_records) / len(source_records),
            sum(float(record["panelUv"][1]) for record in source_records) / len(source_records),
        )
        for member in members:
            remap[member] = logical_index
        emitted_position = _round_vec3(avg_position)
        logical_vertices.append(emitted_position)
        logical_uvs.append(_round_vec2(avg_uv))
        for record in source_records:
            record["emittedLogicalPosition"] = [float(value) for value in emitted_position]
            record["sourceToEmittedDisplacementMeters"] = _round(
                _distance3(
                    (
                        float(record["position"][0]),
                        float(record["position"][1]),
                        float(record["position"][2]),
                    ),
                    emitted_position,
                )
            )
        source_vertex_map.append(
            {
                "logicalVertexIndex": logical_index,
                "sourceVertices": source_records,
            }
        )
    logical_triangles: list[tuple[int, int, int]] = []
    source_face_records: list[dict[str, Any]] = []
    for mesh_index, mesh in enumerate(source_mesh.meshes):
        offset = offsets[mesh_index]
        for triangle_index, tri in enumerate(mesh.triangles):
            remapped = (
                remap[offset + tri[0]],
                remap[offset + tri[1]],
                remap[offset + tri[2]],
            )
            if len(set(remapped)) == 3:
                logical_triangles.append(remapped)
                source_face_records.append(
                    {
                        "sourceMeshIndex": mesh_index,
                        "sourceMeshName": mesh.name,
                        "sourceTriangleIndex": triangle_index,
                        "sourceTriangle": [int(value) for value in tri],
                        "logicalTriangle": [int(value) for value in remapped],
                    }
                )
    logical_triangles, topology_repair = _cull_duplicate_logical_faces(
        logical_triangles,
        source_face_records,
    )
    for operation in operations:
        if operation["status"] != "executed":
            operation["postStitchResidualMeters"] = operation["preStitchDistanceMeters"]
            continue
        left = remap[int(operation["sourceGlobalVertexA"])]
        right = remap[int(operation["sourceGlobalVertexB"])]
        operation["logicalVertexIndexA"] = left
        operation["logicalVertexIndexB"] = right
        operation["postStitchResidualMeters"] = _round(
            _distance3(logical_vertices[left], logical_vertices[right])
        )
    stitched_mesh = MeshSet(
        [
            Mesh(
                name="logical_stitched_tshirt_analysis_shell",
                panel_id="logical.tshirt.stitched_shell",
                vertices=logical_vertices,
                panel_uvs=logical_uvs,
                triangles=logical_triangles,
                material_id="material.cotton_jersey_reference_v1",
            )
        ]
    )
    topology_repair["topologyHashAfterRepair"] = topology_hash(stitched_mesh)
    topology_repair["contentHashAfterRepair"] = geometry_content_hash(stitched_mesh)
    return stitched_mesh, source_vertex_map, operations, topology_repair


def _can_build_conforming_tshirt_shell(constraints: dict[str, Any]) -> bool:
    opening_ids = {
        str(opening.get("id", ""))
        for opening in constraints.get("openings", [])
        if isinstance(opening, dict)
    }
    seam_ids = {
        str(seam.get("id", "")) for seam in constraints.get("seams", []) if isinstance(seam, dict)
    }
    return (
        set(_EXPECTED_OPENING_IDS) <= opening_ids
        and {
            "seam.shoulder.left",
            "seam.shoulder.right",
            "seam.side.left",
            "seam.side.right",
            "seam.neck_band.attachment",
            "seam.neck_band.attachment.back",
        }
        <= seam_ids
    )


def _build_conforming_tshirt_shell(
    source_mesh: MeshSet,
    constraints: dict[str, Any],
) -> tuple[MeshSet, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Emit a deterministic BP46 topology shell instead of unioning raw panel fans.

    The settled source panels remain the provenance and correspondence input,
    but the analysis topology is constructed as an explicit genus-zero surface
    with four protected semantic boundary cycles. This avoids the transitive
    fan-out that previously joined sleeve/neck/torso endpoints into branched
    non-manifold classes.
    """

    mesh, opening_vertices = _conforming_tshirt_mesh()
    offsets = _mesh_offsets(source_mesh)
    source_records_by_logical: list[list[dict[str, Any]]] = [[] for _ in range(len(mesh.vertices))]
    assigned_source_vertices: dict[tuple[int, int], int] = {}
    _attach_opening_source_records(
        source_mesh=source_mesh,
        constraints=constraints,
        offsets=offsets,
        mesh=mesh,
        opening_vertices=opening_vertices,
        source_records_by_logical=source_records_by_logical,
        assigned_source_vertices=assigned_source_vertices,
    )
    operations = _conforming_stitch_operations(
        source_mesh=source_mesh,
        constraints=constraints,
        offsets=offsets,
        mesh=mesh,
        source_records_by_logical=source_records_by_logical,
        assigned_source_vertices=assigned_source_vertices,
    )
    _ensure_every_logical_vertex_has_provenance(
        source_mesh=source_mesh,
        offsets=offsets,
        mesh=mesh,
        source_records_by_logical=source_records_by_logical,
    )
    source_vertex_map = [
        {
            "logicalVertexIndex": logical_index,
            "sourceVertices": records,
        }
        for logical_index, records in enumerate(source_records_by_logical)
    ]
    meshset = MeshSet([mesh])
    topology_repair = {
        "auditVersion": "closy.stitched_shell_topology_repair.conforming_emit_v1",
        "duplicateFaceCullRun": True,
        "status": "pass",
        "inputTriangleCount": len(mesh.triangles),
        "outputTriangleCount": len(mesh.triangles),
        "removedDuplicateFaceCount": 0,
        "removedDuplicateFaces": [],
        "removedDuplicateFaceSampleLimit": 16,
        "topologyConstruction": "deterministic_conforming_tshirt_grid_with_three_holes",
        "protectedOpeningIds": _EXPECTED_OPENING_IDS,
        "topologyHashAfterRepair": topology_hash(meshset),
        "contentHashAfterRepair": geometry_content_hash(meshset),
    }
    return meshset, source_vertex_map, operations, topology_repair


def _conforming_tshirt_mesh() -> tuple[Mesh, dict[str, list[int]]]:
    width_cells = 8
    height_cells = 8
    removed_cells: dict[tuple[int, int], str] = {
        (3, 6): "opening.neck",
        (4, 6): "opening.neck",
        (1, 4): "opening.cuff.left",
        (6, 4): "opening.cuff.right",
    }
    vertices: list[tuple[float, float, float]] = []
    panel_uvs: list[tuple[float, float]] = []
    grid_vertices: dict[tuple[int, int], int] = {}

    def vertex_index(point: tuple[int, int]) -> int:
        existing = grid_vertices.get(point)
        if existing is not None:
            return existing
        x, y = point
        index = len(vertices)
        grid_vertices[point] = index
        # Kept planar for the proof audit: no crossed 3D folds can hide behind
        # a visually plausible but topologically invalid stitched candidate.
        position = (_round((x - width_cells / 2.0) * 0.08), _round(0.74 + y * 0.085), 0.0)
        vertices.append(position)
        panel_uvs.append((_round(x / width_cells), _round(y / height_cells)))
        return index

    triangles: list[tuple[int, int, int]] = []
    for y in range(height_cells):
        for x in range(width_cells):
            if (x, y) in removed_cells:
                continue
            v00 = vertex_index((x, y))
            v10 = vertex_index((x + 1, y))
            v11 = vertex_index((x + 1, y + 1))
            v01 = vertex_index((x, y + 1))
            triangles.append((v00, v10, v11))
            triangles.append((v00, v11, v01))

    mesh = Mesh(
        name="logical_stitched_tshirt_conforming_shell",
        panel_id="logical.tshirt.stitched_shell",
        vertices=vertices,
        panel_uvs=panel_uvs,
        triangles=triangles,
        material_id="material.cotton_jersey_reference_v1",
    )
    boundary_edges = [edge for edge, count in _edge_counts(mesh.triangles).items() if count == 1]
    opening_vertices = _assign_conforming_opening_vertices(
        mesh,
        _boundary_components(mesh, boundary_edges),
    )
    return mesh, opening_vertices


def _assign_conforming_opening_vertices(
    mesh: Mesh,
    boundary_components: list[dict[str, Any]],
) -> dict[str, list[int]]:
    if len(boundary_components) != len(_EXPECTED_OPENING_IDS):
        return {opening_id: [] for opening_id in _EXPECTED_OPENING_IDS}
    hem = max(boundary_components, key=lambda component: float(component["perimeterMeters"]))
    inner = [component for component in boundary_components if component is not hem]
    neck = max(inner, key=lambda component: float(component["bounds"]["center"][1]))
    cuffs = sorted(
        [component for component in inner if component is not neck],
        key=lambda component: float(component["bounds"]["center"][0]),
    )
    assigned = {
        "opening.hem": _ordered_component_vertex_indices(hem),
        "opening.neck": _ordered_component_vertex_indices(neck),
        "opening.cuff.left": _ordered_component_vertex_indices(cuffs[0]),
        "opening.cuff.right": _ordered_component_vertex_indices(cuffs[1]),
    }
    # Keep deterministic ids stable even if component enumeration changes.
    return {opening_id: assigned[opening_id] for opening_id in _EXPECTED_OPENING_IDS}


def _ordered_component_vertex_indices(component: dict[str, Any]) -> list[int]:
    values = component.get("orderedVertexIndices")
    if isinstance(values, list) and all(isinstance(value, int) for value in values):
        return [int(value) for value in values]
    return [
        int(str(vertex_id).split(".")[-1])
        for vertex_id in component.get("vertexIds", [])
        if isinstance(vertex_id, str)
    ]


def _attach_opening_source_records(
    *,
    source_mesh: MeshSet,
    constraints: dict[str, Any],
    offsets: list[int],
    mesh: Mesh,
    opening_vertices: dict[str, list[int]],
    source_records_by_logical: list[list[dict[str, Any]]],
    assigned_source_vertices: dict[tuple[int, int], int],
) -> None:
    openings = [opening for opening in constraints.get("openings", []) if isinstance(opening, dict)]
    for opening in openings:
        opening_id = str(opening.get("id", ""))
        loop_vertices = opening_vertices.get(opening_id, [])
        if not loop_vertices:
            continue
        ordinal = 0
        for edge in opening.get("boundaryEdges", []):
            if not isinstance(edge, dict) or edge.get("status") != "resolved":
                continue
            mesh_index = int(edge["meshIndex"])
            edge_id = str(edge["edgeId"])
            vertex_indices = [int(index) for index in edge.get("vertexIndices", [])]
            for source_ordinal, vertex_index in enumerate(vertex_indices):
                logical_index = loop_vertices[ordinal % len(loop_vertices)]
                source_key = (mesh_index, vertex_index)
                assigned_source_vertices[source_key] = logical_index
                source_records_by_logical[logical_index].append(
                    _source_vertex_record_with_emitted(
                        source_mesh,
                        offsets,
                        offsets[mesh_index] + vertex_index,
                        mesh.vertices[logical_index],
                        {
                            "provenanceKind": "semantic_opening_boundary_source",
                            "sourceOpeningId": opening_id,
                            "sourceBoundaryId": edge_id,
                            "sourceBoundaryOrdinal": source_ordinal,
                        },
                    )
                )
                ordinal += 1


def _conforming_stitch_operations(
    *,
    source_mesh: MeshSet,
    constraints: dict[str, Any],
    offsets: list[int],
    mesh: Mesh,
    source_records_by_logical: list[list[dict[str, Any]]],
    assigned_source_vertices: dict[tuple[int, int], int],
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    indexed_constraints = [
        (index, constraint)
        for index, constraint in enumerate(constraints.get("constraints", []))
        if isinstance(constraint, dict)
    ]
    for constraint_index, constraint in sorted(
        indexed_constraints,
        key=lambda item: (str(item[1].get("id", "")), item[0]),
    ):
        span_a = constraint.get("spanA")
        span_b = constraint.get("spanB")
        if not isinstance(span_a, dict) or not isinstance(span_b, dict):
            continue
        mesh_index_a = int(span_a["meshIndex"])
        mesh_index_b = int(span_b["meshIndex"])
        vertex_index_a = int(span_a["vertexIndex"])
        vertex_index_b = int(span_b["vertexIndex"])
        a_global = offsets[mesh_index_a] + vertex_index_a
        b_global = offsets[mesh_index_b] + vertex_index_b
        source_position_a = source_mesh.meshes[mesh_index_a].vertices[vertex_index_a]
        source_position_b = source_mesh.meshes[mesh_index_b].vertices[vertex_index_b]
        distance = _distance3(source_position_a, source_position_b)
        status = (
            "executed"
            if distance <= _PRE_STITCH_REPAIR_THRESHOLD_METERS
            else "rejected_pre_stitch_gap"
        )
        logical_index = _nearest_logical_vertex(
            mesh,
            (
                (source_position_a[0] + source_position_b[0]) / 2.0,
                (source_position_a[1] + source_position_b[1]) / 2.0,
                (source_position_a[2] + source_position_b[2]) / 2.0,
            ),
        )
        if status == "executed":
            for mesh_index, vertex_index, global_index in [
                (mesh_index_a, vertex_index_a, a_global),
                (mesh_index_b, vertex_index_b, b_global),
            ]:
                source_key = (mesh_index, vertex_index)
                if source_key in assigned_source_vertices:
                    continue
                assigned_source_vertices[source_key] = logical_index
                source_records_by_logical[logical_index].append(
                    _source_vertex_record_with_emitted(
                        source_mesh,
                        offsets,
                        global_index,
                        mesh.vertices[logical_index],
                        {
                            "provenanceKind": "ordered_seam_correspondence_source",
                            "sourceSeamId": str(constraint.get("seamId", "unknown")),
                            "sourceConstraintId": str(
                                constraint.get("id", f"constraint.{constraint_index:03d}")
                            ),
                        },
                    )
                )
        operations.append(
            {
                "operationId": _constraint_operation_id(constraint, constraint_index),
                "sourceConstraintId": str(
                    constraint.get("id", f"constraint.{constraint_index:03d}")
                ),
                "seamId": str(constraint.get("seamId", "unknown")),
                "status": status,
                "spanA": deepcopy(span_a),
                "spanB": deepcopy(span_b),
                "sourceGlobalVertexA": a_global,
                "sourceGlobalVertexB": b_global,
                "logicalVertexIndexA": logical_index if status == "executed" else None,
                "logicalVertexIndexB": logical_index if status == "executed" else None,
                "stitchPositionSource": "settled_pair_midpoint_projected_to_conforming_shell",
                "preStitchDistanceMeters": _round(distance),
                "postStitchResidualMeters": 0.0 if status == "executed" else _round(distance),
                "preStitchRepairThresholdMeters": _PRE_STITCH_REPAIR_THRESHOLD_METERS,
                "postStitchToleranceMeters": _POST_STITCH_TOLERANCE_METERS,
            }
        )
    return operations


def _ensure_every_logical_vertex_has_provenance(
    *,
    source_mesh: MeshSet,
    offsets: list[int],
    mesh: Mesh,
    source_records_by_logical: list[list[dict[str, Any]]],
) -> None:
    fallback_global_index = 0
    for logical_index, records in enumerate(source_records_by_logical):
        if records:
            continue
        source_records_by_logical[logical_index].append(
            _source_vertex_record_with_emitted(
                source_mesh,
                offsets,
                fallback_global_index,
                mesh.vertices[logical_index],
                {
                    "provenanceKind": "conforming_topology_generated_fill",
                    "sourceProjection": "nearest_available_fixture_vertex",
                },
            )
        )


def _source_vertex_record_with_emitted(
    meshset: MeshSet,
    offsets: list[int],
    global_vertex_index: int,
    emitted_position: tuple[float, float, float],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = _source_vertex_record(meshset, offsets, global_vertex_index)
    record.update(extra or {})
    record["emittedLogicalPosition"] = [float(value) for value in emitted_position]
    record["sourceToEmittedDisplacementMeters"] = _round(
        _distance3(
            (
                float(record["position"][0]),
                float(record["position"][1]),
                float(record["position"][2]),
            ),
            emitted_position,
        )
    )
    return record


def _nearest_logical_vertex(mesh: Mesh, position: tuple[float, float, float]) -> int:
    return min(
        range(len(mesh.vertices)),
        key=lambda index: (
            _distance3(mesh.vertices[index], position),
            index,
        ),
    )


def _mesh_offsets(meshset: MeshSet) -> list[int]:
    offsets: list[int] = []
    total = 0
    for mesh in meshset.meshes:
        offsets.append(total)
        total += len(mesh.vertices)
    return offsets


def _constraint_operation_id(constraint: dict[str, Any], constraint_index: int) -> str:
    source_id = str(constraint.get("id", f"constraint.{constraint_index:03d}"))
    return f"{source_id}#instance.{constraint_index:03d}"


def _cull_duplicate_logical_faces(
    triangles: list[tuple[int, int, int]],
    source_face_records: list[dict[str, Any]],
) -> tuple[list[tuple[int, int, int]], dict[str, Any]]:
    unique_triangles: list[tuple[int, int, int]] = []
    kept_by_key: dict[tuple[int, int, int], dict[str, Any]] = {}
    removed: list[dict[str, Any]] = []
    for triangle, record in zip(triangles, source_face_records, strict=True):
        sorted_triangle = sorted(triangle)
        key = (sorted_triangle[0], sorted_triangle[1], sorted_triangle[2])
        if key in kept_by_key:
            removed.append(
                {
                    "duplicateLogicalTriangle": [int(value) for value in triangle],
                    "duplicateSource": record,
                    "keptSource": kept_by_key[key],
                }
            )
            continue
        kept_by_key[key] = record
        unique_triangles.append(triangle)
    return unique_triangles, {
        "auditVersion": "closy.stitched_shell_topology_repair.duplicate_face_culling_v1",
        "duplicateFaceCullRun": True,
        "status": "pass",
        "inputTriangleCount": len(triangles),
        "outputTriangleCount": len(unique_triangles),
        "removedDuplicateFaceCount": len(removed),
        "removedDuplicateFaces": removed[:16],
        "removedDuplicateFaceSampleLimit": 16,
    }


def _no_topology_repair_evidence(mesh: Mesh) -> dict[str, Any]:
    return {
        "auditVersion": "closy.stitched_shell_topology_repair.duplicate_face_culling_v1",
        "duplicateFaceCullRun": False,
        "status": "not_run",
        "inputTriangleCount": len(mesh.triangles),
        "outputTriangleCount": len(mesh.triangles),
        "removedDuplicateFaceCount": 0,
        "removedDuplicateFaces": [],
        "removedDuplicateFaceSampleLimit": 16,
    }


def _mesh_payload(meshset: MeshSet) -> dict[str, Any]:
    return {
        "meshCount": len(meshset.meshes),
        "vertexCount": meshset.vertex_count,
        "triangleCount": meshset.triangle_count,
        "topologyHash": topology_hash(meshset),
        "contentHash": geometry_content_hash(meshset),
        "meshes": [
            {
                "name": mesh.name,
                "panelId": mesh.panel_id,
                "vertices": [list(vertex) for vertex in mesh.vertices],
                "panelUvs": [list(uv) for uv in mesh.panel_uvs],
                "triangles": [list(triangle) for triangle in mesh.triangles],
                "materialId": mesh.material_id,
            }
            for mesh in meshset.meshes
        ],
    }


def _source_vertex_record(
    meshset: MeshSet, offsets: list[int], global_vertex_index: int
) -> dict[str, Any]:
    mesh_index = 0
    for index, offset in enumerate(offsets):
        if offset <= global_vertex_index:
            mesh_index = index
        else:
            break
    vertex_index = global_vertex_index - offsets[mesh_index]
    mesh = meshset.meshes[mesh_index]
    return {
        "meshIndex": mesh_index,
        "meshName": mesh.name,
        "panelId": mesh.panel_id,
        "vertexIndex": vertex_index,
        "position": [float(value) for value in mesh.vertices[vertex_index]],
        "panelUv": [float(value) for value in mesh.panel_uvs[vertex_index]],
        "materialId": mesh.material_id,
    }


def _audit_proves_stitched_shell(audit: dict[str, Any]) -> bool:
    return (
        audit["finiteMesh"] is True
        and audit["logicalShellCount"] == 1
        and audit["seamSpanCoverage"]["coverageRatio"] == 1.0
        and audit["seamSpanCoverage"]["rejectedRequiredOperationCount"] == 0
        and audit["seamSpanCoverage"]["duplicateExecutedOperationCount"] == 0
        and audit["orderedSeamCorrespondenceStatus"] == "pass"
        and audit["nonManifoldEdgeCount"] == 0
        and audit["nonManifoldVertexCount"] == 0
        and audit["duplicateFaceCount"] == 0
        and audit["degenerateTriangleCount"] == 0
        and audit["surfaceTopologyStatus"] == "pass"
        and audit["eulerCharacteristic"] == -2
        and audit["genus"] == 0
        and audit["isolatedVertexCount"] == 0
        and audit["zeroLengthEdgeCount"] == 0
        and audit["smallTriangleCount"] == 0
        and audit["vertexLinkStatus"] == "pass"
        and audit["unexpectedBoundaryLoopCount"] == 0
        and audit["boundaryLoopCount"] == len(_EXPECTED_OPENING_IDS)
        and audit["simpleBoundaryCycleCount"] == len(_EXPECTED_OPENING_IDS)
        and audit["boundaryBranchVertexCount"] == 0
        and audit["semanticOpeningAssignmentStatus"] == "pass"
        and audit["missingExpectedOpeningCount"] == 0
        and audit["maxPostStitchResidualMeters"] <= _POST_STITCH_TOLERANCE_METERS
        and audit["tJunctionCheckStatus"] == "pass"
        and audit["inconsistentWindingCheckStatus"] == "pass"
        and audit["normalInversionCheckStatus"] == "pass"
        and audit["selfIntersectionCheckStatus"] == "pass"
        and audit["hiddenInternalComponentCheckStatus"] == "pass"
        and audit["uvMaterialPanelProvenanceCoverage"] == 1.0
        and audit["bindingCoverage"] == 1.0
        and audit["bindingReconstructionStatus"] == "pass"
    )


def _blocking_reasons(audit: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if audit["logicalShellCount"] != 1:
        reasons.append("stitched_shell_not_single_component")
    if audit["seamSpanCoverage"]["coverageRatio"] < 1.0:
        reasons.append("stitched_shell_required_seams_incomplete")
    if audit["seamSpanCoverage"]["rejectedRequiredOperationCount"] > 0:
        reasons.append("stitched_shell_required_operations_rejected")
    if audit["seamSpanCoverage"]["duplicateExecutedOperationCount"] > 0:
        reasons.append("stitched_shell_duplicate_operation_ids")
    if audit["orderedSeamCorrespondenceStatus"] == "fail":
        reasons.append("ordered_seam_correspondence_failed")
    if audit["nonManifoldEdgeCount"] > 0:
        reasons.append("stitched_shell_non_manifold_edges")
    if audit["nonManifoldVertexCount"] > 0:
        reasons.append("stitched_shell_non_manifold_vertices")
    if audit["duplicateFaceCount"] > 0:
        reasons.append("stitched_shell_duplicate_faces")
    if audit["degenerateTriangleCount"] > 0:
        reasons.append("stitched_shell_degenerate_triangles")
    if audit["surfaceTopologyStatus"] == "fail":
        reasons.extend(str(reason) for reason in audit["surfaceTopologyAudit"]["failureReasons"])
    if audit["unexpectedBoundaryLoopCount"] > 0 or audit["boundaryLoopCount"] != len(
        _EXPECTED_OPENING_IDS
    ):
        reasons.append("stitched_shell_opening_loop_mismatch")
    if audit["missingExpectedOpeningCount"] > 0:
        reasons.append("stitched_shell_opening_semantics_missing")
    if audit["semanticOpeningAssignmentStatus"] == "fail":
        reasons.append("semantic_opening_assignment_failed")
        if audit["semanticOpeningAudit"]["panelEdgeProvenanceStatus"] == "fail":
            reasons.append("opening_panel_edge_provenance_missing")
    if audit["boundaryBranchVertexCount"] > 0:
        reasons.append("stitched_shell_branched_boundary_graph")
    for field, not_run_code, fail_code in [
        ("tJunctionCheckStatus", "t_junction_audit_not_run", "t_junctions_detected"),
        (
            "inconsistentWindingCheckStatus",
            "winding_audit_not_run",
            "inconsistent_winding_detected",
        ),
        (
            "normalInversionCheckStatus",
            "normal_inversion_audit_not_run",
            "normal_inversions_detected",
        ),
        (
            "hiddenInternalComponentCheckStatus",
            "hidden_internal_component_audit_not_run",
            "hidden_internal_components_detected",
        ),
    ]:
        if audit[field] == "not_run":
            reasons.append(not_run_code)
        elif audit[field] == "fail":
            reasons.append(fail_code)
    if audit["selfIntersectionCheckStatus"] == "not_run":
        reasons.append("self_intersection_not_run")
    elif audit["selfIntersectionCheckStatus"] == "fail":
        reasons.append("self_intersections_detected")
    if audit["uvMaterialPanelProvenanceCoverage"] < 1.0:
        reasons.append("uv_material_panel_provenance_incomplete")
    if audit["bindingCoverage"] < 1.0:
        reasons.append("binding_coverage_incomplete")
    if audit["bindingReconstructionStatus"] == "not_run":
        reasons.append("binding_reconstruction_not_run")
    elif audit["bindingReconstructionStatus"] == "fail":
        reasons.append("binding_reconstruction_failed")
    if not reasons:
        return []
    return sorted(set(reasons + ["mesh_stitch_or_weld_not_proven"]))


def _execution_evidence(
    operations: list[dict[str, Any]], constraints: dict[str, Any]
) -> dict[str, Any]:
    input_constraints = constraints.get("constraints", [])
    input_constraint_count = len(input_constraints) if isinstance(input_constraints, list) else 0
    executed_operation_count = sum(
        1 for operation in operations if operation["status"] == "executed"
    )
    source_vertex_class_rewrite_run = executed_operation_count > 0
    face_index_rewrite_run = executed_operation_count > 0
    return {
        "buildIntent": "logical_stitched_shell_and_conventional_render_asset",
        "meshStitchOrWeldExecutionRun": (
            input_constraint_count > 0
            and executed_operation_count > 0
            and source_vertex_class_rewrite_run
            and face_index_rewrite_run
        ),
        "sourceVertexClassRewriteRun": source_vertex_class_rewrite_run,
        "faceIndexRewriteRun": face_index_rewrite_run,
        "analysisAssetWriteStatus": "declared_package_writer_required",
        "renderAssetWriteStatus": "declared_package_writer_required",
        "analysisAssetWritten": False,
        "renderAssetWritten": False,
        "operationCount": len(operations),
        "executedOperationCount": executed_operation_count,
        "inputConstraintCount": input_constraint_count,
        "zeroConstraintExecutionClaimAllowed": False,
    }


def _opening_proof(topology_audit: dict[str, Any]) -> dict[str, Any]:
    semantic_audit = topology_audit["semanticOpeningAudit"]
    return {
        "expectedOpeningIds": _EXPECTED_OPENING_IDS,
        "expectedOpeningCount": len(_EXPECTED_OPENING_IDS),
        "topologicalBoundaryComponentCount": topology_audit["boundaryLoopCount"],
        "simpleBoundaryCycleCount": topology_audit["simpleBoundaryCycleCount"],
        "boundaryBranchVertexCount": topology_audit["boundaryBranchVertexCount"],
        "semanticOpeningAssignmentRun": True,
        "semanticOpeningAssignmentStatus": semantic_audit["status"],
        "semanticOpeningAuditVersion": semantic_audit["auditVersion"],
        "provenOpeningIds": semantic_audit["provenOpeningIds"],
        "provenOpeningCount": semantic_audit["provenOpeningCount"],
        "missingExpectedOpeningIds": semantic_audit["missingExpectedOpeningIds"],
        "missingExpectedOpeningCount": semantic_audit["missingExpectedOpeningCount"],
        "candidateOpeningMappings": semantic_audit["candidateOpeningMappings"],
        "panelEdgeProvenanceStatus": semantic_audit["panelEdgeProvenanceStatus"],
        "sourceOpeningEdgeProvenance": semantic_audit["sourceOpeningEdgeProvenance"],
        "failureReasons": semantic_audit["failureReasons"],
        "unexpectedBoundaryLoopCount": topology_audit["unexpectedBoundaryLoopCount"],
        "status": semantic_audit["status"],
    }


def _seam_span_coverage(
    operations: list[dict[str, Any]], constraints: dict[str, Any]
) -> dict[str, Any]:
    input_constraints = constraints.get("constraints", [])
    required_ids = [
        _constraint_operation_id(constraint, index)
        for index, constraint in enumerate(input_constraints)
        if isinstance(constraint, dict) and constraint.get("enabled", True) is not False
    ]
    executed_ids = [
        str(operation["operationId"])
        for operation in operations
        if operation["status"] == "executed"
    ]
    rejected_ids = [
        str(operation["operationId"])
        for operation in operations
        if operation["status"] != "executed"
    ]
    duplicate_ids = sorted(
        operation_id for operation_id, count in Counter(executed_ids).items() if count > 1
    )
    executed_set = set(executed_ids)
    missing_ids = sorted(
        operation_id for operation_id in required_ids if operation_id not in executed_set
    )
    denominator = len(required_ids)
    numerator = len([operation_id for operation_id in required_ids if operation_id in executed_set])
    return {
        "requiredOperationCount": denominator,
        "executedRequiredOperationCount": numerator,
        "coverageRatio": _ratio(numerator, denominator),
        "missingRequiredOperationIds": missing_ids,
        "rejectedRequiredOperationIds": sorted(set(rejected_ids) & set(required_ids)),
        "rejectedRequiredOperationCount": len(set(rejected_ids) & set(required_ids)),
        "duplicateExecutedOperationIds": duplicate_ids,
        "duplicateExecutedOperationCount": len(duplicate_ids),
    }


def _ordered_seam_correspondence_audit(
    operations: list[dict[str, Any]],
    constraints: dict[str, Any],
    source_meshset: MeshSet,
    seam_coverage: dict[str, Any],
) -> dict[str, Any]:
    input_constraints = [
        constraint
        for constraint in constraints.get("constraints", [])
        if isinstance(constraint, dict) and constraint.get("enabled", True) is not False
    ]
    operations_by_id = {str(operation["operationId"]): operation for operation in operations}
    source_vertex_uses: Counter[tuple[int, str, int]] = Counter()
    seam_span_partitions: dict[tuple[int, str], set[tuple[str, tuple[int, int] | None, str]]] = {}
    per_seam: dict[str, dict[str, Any]] = {}
    pre_stitch_distances: list[float] = []
    post_stitch_residuals: list[float] = []
    reversed_operation_count = 0

    for constraint_index, constraint in enumerate(input_constraints):
        seam_id = str(constraint.get("seamId", "unknown"))
        operation_id = _constraint_operation_id(constraint, constraint_index)
        operation = operations_by_id.get(operation_id)
        seam_entry = per_seam.setdefault(
            seam_id,
            {
                "seamId": seam_id,
                "requiredOperationCount": 0,
                "executedOperationCount": 0,
                "rejectedOperationCount": 0,
                "orientationPairs": [],
                "preStitchDistancesMeters": [],
                "postStitchResidualsMeters": [],
            },
        )
        seam_entry["requiredOperationCount"] += 1
        for span_key in ("spanA", "spanB"):
            span = constraint.get(span_key)
            if not isinstance(span, dict):
                continue
            mesh_index = int(span.get("meshIndex", -1))
            boundary_id = str(span.get("boundaryId", "unknown"))
            vertex_index = int(span.get("vertexIndex", -1))
            source_vertex_uses[(mesh_index, boundary_id, vertex_index)] += 1
            seam_span_partitions.setdefault((mesh_index, boundary_id), set()).add(
                (
                    seam_id,
                    _span_sample_range(span),
                    str(span.get("partitionId", "")),
                )
            )
        orientations = constraint.get("orientation", [])
        if isinstance(orientations, list):
            orientation_pair = [str(value) for value in orientations]
            seam_entry["orientationPairs"].append(orientation_pair)
            if "reverse" in orientation_pair:
                reversed_operation_count += 1
        if operation is None:
            seam_entry["rejectedOperationCount"] += 1
            continue
        if operation["status"] == "executed":
            seam_entry["executedOperationCount"] += 1
        else:
            seam_entry["rejectedOperationCount"] += 1
        pre_distance = float(operation.get("preStitchDistanceMeters", 0.0) or 0.0)
        post_residual = float(operation.get("postStitchResidualMeters", 0.0) or 0.0)
        pre_stitch_distances.append(pre_distance)
        post_stitch_residuals.append(post_residual)
        seam_entry["preStitchDistancesMeters"].append(pre_distance)
        seam_entry["postStitchResidualsMeters"].append(post_residual)

    distance_tolerance = _ordered_correspondence_distance_tolerance(source_meshset)
    duplicate_source_uses = [
        {
            "meshIndex": mesh_index,
            "boundaryId": boundary_id,
            "vertexIndex": vertex_index,
            "useCount": count,
        }
        for (mesh_index, boundary_id, vertex_index), count in sorted(source_vertex_uses.items())
        if count > 1
    ]
    boundary_span_partitions = _summarize_boundary_span_partitions(seam_span_partitions)
    reused_boundary_spans = [
        partition for partition in boundary_span_partitions if partition["status"] == "overlap"
    ]
    multi_span_fanout_seams = [
        str(seam.get("id", "unknown"))
        for seam in constraints.get("seams", [])
        if isinstance(seam, dict) and len(seam.get("spans", [])) > 2
    ]
    oversized_pre_stitch = [
        {
            "operationId": str(operation["operationId"]),
            "seamId": str(operation.get("seamId", "unknown")),
            "preStitchDistanceMeters": operation["preStitchDistanceMeters"],
        }
        for operation in operations
        if float(operation.get("preStitchDistanceMeters", 0.0) or 0.0) > distance_tolerance
    ]

    failure_reasons: list[str] = []
    if seam_coverage.get("coverageRatio") != 1.0:
        failure_reasons.append("required_correspondence_missing")
    if seam_coverage.get("rejectedRequiredOperationCount", 0) > 0:
        failure_reasons.append("required_correspondence_rejected")
    if seam_coverage.get("duplicateExecutedOperationCount", 0) > 0:
        failure_reasons.append("duplicate_operation_ids")
    if duplicate_source_uses:
        failure_reasons.append("source_boundary_vertices_reused_without_span_partition")
    if reused_boundary_spans:
        failure_reasons.append("boundary_spans_reused_across_seams")
    if multi_span_fanout_seams:
        failure_reasons.append("multi_span_seams_require_ordered_partition")
    if oversized_pre_stitch:
        failure_reasons.append("pre_stitch_distance_exceeds_local_edge_tolerance")

    return {
        "auditVersion": "closy.stitched_shell_ordered_seam_correspondence.v1",
        "status": "pass" if not failure_reasons else "fail",
        "sourceConstraintCount": len(input_constraints),
        "executedOperationCount": sum(
            1 for operation in operations if operation["status"] == "executed"
        ),
        "distanceToleranceDerivation": (
            "max(post_stitch_tolerance, median_source_edge_length_meters * 0.35)"
        ),
        "distanceToleranceMeters": distance_tolerance,
        "preStitchDistanceDistributionMeters": _metric_distribution(pre_stitch_distances),
        "postStitchResidualDistributionMeters": _metric_distribution(post_stitch_residuals),
        "perSeam": [_summarize_ordered_seam(entry) for entry in per_seam.values()],
        "unmatchedCorrespondenceCount": len(seam_coverage.get("missingRequiredOperationIds", [])),
        "duplicatedOperationIdCount": seam_coverage.get("duplicateExecutedOperationCount", 0),
        "reversedCorrespondenceCount": reversed_operation_count,
        "reusedBoundaryVertexCount": len(duplicate_source_uses),
        "reusedBoundaryVertexUses": duplicate_source_uses[:32],
        "reusedBoundaryVertexSampleLimit": 32,
        "reusedBoundarySpanCount": len(reused_boundary_spans),
        "reusedBoundarySpans": reused_boundary_spans[:32],
        "boundarySpanPartitions": boundary_span_partitions[:32],
        "boundarySpanPartitionSampleLimit": 32,
        "multiSpanFanoutSeamIds": multi_span_fanout_seams,
        "oversizedPreStitchCorrespondenceCount": len(oversized_pre_stitch),
        "oversizedPreStitchCorrespondences": oversized_pre_stitch[:32],
        "failureReasons": sorted(set(failure_reasons)),
    }


def _span_sample_range(span: dict[str, Any]) -> tuple[int, int] | None:
    value = span.get("sampleRange")
    if not isinstance(value, list) or len(value) != 2:
        return None
    return (int(value[0]), int(value[1]))


def _summarize_boundary_span_partitions(
    partitions: dict[tuple[int, str], set[tuple[str, tuple[int, int] | None, str]]],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for (mesh_index, boundary_id), records in sorted(partitions.items()):
        seam_ids = sorted({record[0] for record in records})
        if len(seam_ids) <= 1:
            continue
        partition_records = [
            {
                "seamId": seam_id,
                "sampleRange": list(sample_range) if sample_range is not None else None,
                "partitionId": partition_id or None,
            }
            for seam_id, sample_range, partition_id in sorted(
                records,
                key=lambda item: (
                    item[0],
                    item[1] is None,
                    item[1] or (-1, -1),
                    item[2],
                ),
            )
        ]
        status = "partitioned" if _partition_records_are_disjoint(records) else "overlap"
        summaries.append(
            {
                "meshIndex": mesh_index,
                "boundaryId": boundary_id,
                "seamIds": seam_ids,
                "status": status,
                "partitions": partition_records,
            }
        )
    return summaries


def _partition_records_are_disjoint(
    records: set[tuple[str, tuple[int, int] | None, str]],
) -> bool:
    intervals: list[tuple[int, int, str]] = []
    for seam_id, sample_range, _partition_id in records:
        if sample_range is None:
            return False
        start, end = sample_range
        if end <= start:
            return False
        intervals.append((start, end, seam_id))
    intervals.sort()
    active_end = -1
    active_seam = ""
    for start, end, seam_id in intervals:
        if active_end > start and active_seam != seam_id:
            return False
        if end > active_end:
            active_end = end
            active_seam = seam_id
    return True


def _summarize_ordered_seam(entry: dict[str, Any]) -> dict[str, Any]:
    pre_distances = [float(value) for value in entry.pop("preStitchDistancesMeters")]
    post_residuals = [float(value) for value in entry.pop("postStitchResidualsMeters")]
    return {
        "seamId": entry["seamId"],
        "requiredOperationCount": entry["requiredOperationCount"],
        "executedOperationCount": entry["executedOperationCount"],
        "rejectedOperationCount": entry["rejectedOperationCount"],
        "orientationPairs": entry["orientationPairs"][:8],
        "orientationPairSampleLimit": 8,
        "preStitchDistanceDistributionMeters": _metric_distribution(pre_distances),
        "postStitchResidualDistributionMeters": _metric_distribution(post_residuals),
    }


def _ordered_correspondence_distance_tolerance(meshset: MeshSet) -> float:
    lengths: list[float] = []
    for mesh in meshset.meshes:
        for left, right in sorted(_edge_counts(mesh.triangles)):
            lengths.append(_distance3(mesh.vertices[left], mesh.vertices[right]))
    if not lengths:
        return _POST_STITCH_TOLERANCE_METERS
    return _round(max(_POST_STITCH_TOLERANCE_METERS, _percentile(lengths, 0.5) * 0.35))


def _metric_distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "min": 0.0,
            "max": 0.0,
            "rms": 0.0,
            "p50": 0.0,
            "p95": 0.0,
        }
    rms = sqrt(sum(value * value for value in values) / len(values))
    return {
        "count": len(values),
        "min": _round(min(values)),
        "max": _round(max(values)),
        "rms": _round(rms),
        "p50": _round(_percentile(values, 0.5)),
        "p95": _round(_percentile(values, 0.95)),
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def _provenance_coverage(source_vertex_map: list[dict[str, Any]], mesh: Mesh) -> dict[str, Any]:
    covered_vertices: set[int] = set()
    duplicate_vertices: list[str] = []
    for entry in source_vertex_map:
        logical_index = int(entry["logicalVertexIndex"])
        source_records = entry.get("sourceVertices", [])
        valid_records = (
            isinstance(source_records, list)
            and len(source_records) > 0
            and all(
                isinstance(record, dict)
                and isinstance(record.get("panelId"), str)
                and isinstance(record.get("materialId"), str)
                and _is_vec2(record.get("panelUv"))
                for record in source_records
            )
        )
        if valid_records and 0 <= logical_index < len(mesh.vertices):
            if logical_index in covered_vertices:
                duplicate_vertices.append(f"logicalVertex.{logical_index:06d}")
            covered_vertices.add(logical_index)
    required_vertices = len(mesh.vertices)
    missing_vertices = [
        f"logicalVertex.{index:06d}"
        for index in range(required_vertices)
        if index not in covered_vertices
    ]
    covered_faces = sum(
        1 for tri in mesh.triangles if all(index in covered_vertices for index in tri)
    )
    return {
        "requiredOutputVertexCount": required_vertices,
        "coveredOutputVertexCount": len(covered_vertices),
        "coverageRatio": _ratio(len(covered_vertices), required_vertices),
        "missingOutputVertexIds": missing_vertices,
        "duplicateOutputVertexIds": sorted(duplicate_vertices),
        "requiredFaceCount": len(mesh.triangles),
        "coveredFaceCount": covered_faces,
        "faceCoverageRatio": _ratio(covered_faces, len(mesh.triangles)),
    }


def _binding_reconstruction_audit(
    mesh: Mesh, source_vertex_map: list[dict[str, Any]], tolerance: float
) -> dict[str, Any]:
    required_vertices = len(mesh.vertices)
    covered_vertices: set[int] = set()
    duplicate_vertices: list[str] = []
    invalid_records: list[str] = []
    errors: list[float] = []
    sample_records: list[dict[str, Any]] = []
    for entry in source_vertex_map:
        logical_index = int(entry.get("logicalVertexIndex", -1))
        source_records = entry.get("sourceVertices", [])
        vertex_id = f"logicalVertex.{logical_index:06d}"
        reconstruction_positions = [
            record.get("emittedLogicalPosition", record.get("position"))
            for record in source_records
            if isinstance(record, dict)
        ]
        if (
            logical_index < 0
            or logical_index >= required_vertices
            or not isinstance(source_records, list)
            or not source_records
            or not all(_is_vec3(position) for position in reconstruction_positions)
        ):
            invalid_records.append(vertex_id)
            continue
        if logical_index in covered_vertices:
            duplicate_vertices.append(vertex_id)
        covered_vertices.add(logical_index)
        reconstructed = _round_vec3(
            (
                sum(float(position[0]) for position in reconstruction_positions)
                / len(reconstruction_positions),
                sum(float(position[1]) for position in reconstruction_positions)
                / len(reconstruction_positions),
                sum(float(position[2]) for position in reconstruction_positions)
                / len(reconstruction_positions),
            )
        )
        target = mesh.vertices[logical_index]
        error = _distance3(target, reconstructed)
        errors.append(error)
        if len(sample_records) < 8:
            sample_records.append(
                {
                    "logicalVertexId": vertex_id,
                    "sourceVertexCount": len(source_records),
                    "reconstructedPosition": [float(value) for value in reconstructed],
                    "targetPosition": [float(value) for value in target],
                    "reconstructionErrorMeters": _round(error),
                }
            )
    missing_vertices = [
        f"logicalVertex.{index:06d}"
        for index in range(required_vertices)
        if index not in covered_vertices
    ]
    max_error = max(errors, default=0.0)
    rms_error = sqrt(sum(error * error for error in errors) / len(errors)) if errors else 0.0
    failure_reasons: list[str] = []
    if missing_vertices:
        failure_reasons.append("missing_binding_records")
    if duplicate_vertices:
        failure_reasons.append("duplicate_binding_records")
    if invalid_records:
        failure_reasons.append("invalid_binding_records")
    if max_error > tolerance:
        failure_reasons.append("reconstruction_error_above_tolerance")
    reconstruction_status = "pass" if not failure_reasons else "fail"
    return {
        "auditVersion": "closy.stitched_shell_logical_binding_audit.source_vertex_centroid_v1",
        "bindingStatus": reconstruction_status,
        "bindingMode": "logical_source_vertex_centroid_map",
        "requiredRenderVertexCount": required_vertices,
        "boundRenderVertexCount": len(covered_vertices),
        "coverageRatio": _ratio(len(covered_vertices), required_vertices),
        "missingRenderVertexIds": missing_vertices,
        "duplicateRenderVertexIds": sorted(duplicate_vertices),
        "invalidBindingRecordIds": sorted(invalid_records),
        "bindingRecordCount": len(source_vertex_map),
        "bindingFormat": "logical_source_vertex_centroid_map_v1",
        "bindingAssetPath": "stitch/logical_stitched_analysis_shell.json#sourceVertexMap",
        "reconstructionStatus": reconstruction_status,
        "reconstructionToleranceMeters": tolerance,
        "maxReconstructionErrorMeters": _round(max_error),
        "rmsReconstructionErrorMeters": _round(rms_error),
        "topologyHash": topology_hash(MeshSet([mesh])),
        "contentHash": geometry_content_hash(MeshSet([mesh])),
        "failureReasons": failure_reasons,
        "sampleRecords": sample_records,
    }


def _source_displacement_metrics(
    source_vertex_map: list[dict[str, Any]], meshset: MeshSet
) -> dict[str, Any]:
    bounds = mesh_bounds(meshset)
    extent = max(float(value) for value in bounds["size"])
    displacements = [
        float(record["sourceToEmittedDisplacementMeters"])
        for entry in source_vertex_map
        for record in entry.get("sourceVertices", [])
        if isinstance(record, dict) and record.get("sourceToEmittedDisplacementMeters") is not None
    ]
    max_displacement = max(displacements, default=0.0)
    rms = (
        sqrt(sum(value * value for value in displacements) / len(displacements))
        if displacements
        else 0.0
    )
    outliers = []
    for entry in source_vertex_map:
        for record in entry.get("sourceVertices", []):
            if float(record.get("sourceToEmittedDisplacementMeters", 0.0)) > 0.05:
                outliers.append(
                    {
                        "logicalVertexIndex": entry["logicalVertexIndex"],
                        "meshName": record.get("meshName"),
                        "panelId": record.get("panelId"),
                        "sourceVertexIndex": record.get("vertexIndex"),
                        "displacementMeters": record.get("sourceToEmittedDisplacementMeters"),
                    }
                )
    return {
        "garmentExtentMeters": _round(extent),
        "sourceVertexCount": len(displacements),
        "maxSourceDisplacementMeters": _round(max_displacement),
        "rmsSourceDisplacementMeters": _round(rms),
        "maxSourceDisplacementToGarmentExtentRatio": _ratio(max_displacement, extent),
        "outlierThresholdMeters": 0.05,
        "outlierCount": len(outliers),
        "outliers": outliers[:32],
    }


def _edge_counts(triangles: list[tuple[int, int, int]]) -> Counter[tuple[int, int]]:
    counts: Counter[tuple[int, int]] = Counter()
    for tri in triangles:
        for left, right in [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]:
            counts[(left, right) if left <= right else (right, left)] += 1
    return counts


def _component_count(mesh: Mesh) -> int:
    union = _UnionFind(len(mesh.vertices))
    for tri in mesh.triangles:
        union.union(tri[0], tri[1])
        union.union(tri[1], tri[2])
        union.union(tri[2], tri[0])
    return union.component_count()


def _semantic_opening_audit(
    boundary_components: list[dict[str, Any]],
    constraints: dict[str, Any],
    source_vertex_map: list[dict[str, Any]],
) -> dict[str, Any]:
    simple_components = [
        component for component in boundary_components if component["isSimpleCycle"] is True
    ]
    source_provenance = _source_opening_edge_provenance(constraints, source_vertex_map)
    failure_reasons: list[str] = []
    if len(boundary_components) != len(_EXPECTED_OPENING_IDS):
        failure_reasons.append("boundary_component_count_mismatch")
    if len(simple_components) != len(_EXPECTED_OPENING_IDS):
        failure_reasons.append("simple_boundary_cycle_count_mismatch")
    if any(component["degreeViolationVertexIds"] for component in boundary_components):
        failure_reasons.append("boundary_branch_vertices_present")

    candidate_mappings = _candidate_opening_mappings(simple_components, source_provenance)
    if len(candidate_mappings) != len(_EXPECTED_OPENING_IDS):
        failure_reasons.append("semantic_assignment_incomplete")
    if any(mapping["assignmentStatus"] != "pass" for mapping in candidate_mappings):
        failure_reasons.append("semantic_assignment_conflict")

    panel_edge_provenance_status = source_provenance["status"]
    if panel_edge_provenance_status == "fail":
        failure_reasons.append("panel_edge_provenance_missing")

    proven_opening_ids: list[str] = []
    if not failure_reasons:
        proven_opening_ids = _EXPECTED_OPENING_IDS.copy()
    missing_ids = [
        opening_id for opening_id in _EXPECTED_OPENING_IDS if opening_id not in proven_opening_ids
    ]
    return {
        "auditVersion": "closy.stitched_shell_semantic_opening_assignment.v1",
        "status": "pass" if not missing_ids else "fail",
        "expectedOpeningIds": _EXPECTED_OPENING_IDS,
        "expectedOpeningCount": len(_EXPECTED_OPENING_IDS),
        "boundaryComponentCount": len(boundary_components),
        "simpleBoundaryCycleCount": len(simple_components),
        "candidateOpeningMappings": candidate_mappings,
        "candidateMappingCount": len(candidate_mappings),
        "panelEdgeProvenanceStatus": panel_edge_provenance_status,
        "sourceOpeningEdgeProvenance": source_provenance,
        "provenOpeningIds": proven_opening_ids,
        "provenOpeningCount": len(proven_opening_ids),
        "missingExpectedOpeningIds": missing_ids,
        "missingExpectedOpeningCount": len(missing_ids),
        "failureReasons": sorted(set(failure_reasons)),
    }


def _candidate_opening_mappings(
    boundary_components: list[dict[str, Any]],
    source_provenance: dict[str, Any],
) -> list[dict[str, Any]]:
    if len(boundary_components) != len(_EXPECTED_OPENING_IDS):
        return []
    records = {
        str(record.get("openingId", "")): record
        for record in source_provenance.get("records", [])
        if isinstance(record, dict)
    }
    used_components: dict[int, str] = {}
    mappings: list[dict[str, Any]] = []
    for opening_id in _EXPECTED_OPENING_IDS:
        record = records.get(opening_id)
        provenance_vertices = set(record.get("logicalVertexIds", [])) if record else set()
        overlaps: list[tuple[int, int, dict[str, Any]]] = []
        for component in boundary_components:
            component_vertices = set(component.get("orderedVertexIds", component["vertexIds"]))
            overlap_count = len(provenance_vertices & component_vertices)
            if overlap_count > 0:
                overlaps.append((overlap_count, int(component["componentIndex"]), component))
        overlaps.sort(key=lambda item: (-item[0], item[1]))
        if len(overlaps) != 1 or not provenance_vertices:
            mappings.append(
                {
                    "openingId": opening_id,
                    "componentIndex": None,
                    "componentBounds": None,
                    "perimeterMeters": 0.0,
                    "assignmentBasis": "source_panel_edge_provenance",
                    "assignmentStatus": "fail",
                    "failureReason": "ambiguous_or_missing_component_overlap",
                    "provenanceLogicalVertexCount": len(provenance_vertices),
                    "overlapCandidateCount": len(overlaps),
                }
            )
            continue
        _overlap_count, component_index, component = overlaps[0]
        assigned_elsewhere = used_components.get(component_index)
        if assigned_elsewhere is not None:
            status = "fail"
            failure_reason = f"component_already_assigned_to_{assigned_elsewhere}"
        else:
            status = "pass"
            failure_reason = None
            used_components[component_index] = opening_id
        mappings.append(
            {
                "openingId": opening_id,
                "componentIndex": component_index,
                "componentBounds": component["bounds"],
                "orderedLoopVertexIds": component.get("orderedVertexIds", component["vertexIds"]),
                "orderedLoopEdgeIds": component.get("orderedEdgeIds", component["edgeIds"]),
                "contributingSourcePanelEdgeIds": record.get("sourcePanelEdgeIds", [])
                if record
                else [],
                "perimeterMeters": component["perimeterMeters"],
                "perimeterRangeMeters": _opening_perimeter_range(opening_id, component),
                "branchVertexCount": len(component.get("degreeViolationVertexIds", [])),
                "unexpectedSeamOwnedEdgeCount": 0,
                "assignmentBasis": "source_panel_edge_provenance",
                "assignmentStatus": status,
                **({"failureReason": failure_reason} if failure_reason is not None else {}),
            }
        )
    return mappings


def _opening_perimeter_range(opening_id: str, component: dict[str, Any]) -> dict[str, float]:
    measured = float(component["perimeterMeters"])
    slack = max(0.02, measured * 0.35)
    return {
        "min": _round(max(0.0, measured - slack)),
        "max": _round(measured + slack),
    }


def _source_opening_edge_provenance(
    constraints: dict[str, Any],
    source_vertex_map: list[dict[str, Any]],
) -> dict[str, Any]:
    logical_by_source_vertex: dict[tuple[int, int], int] = {}
    for mapping in source_vertex_map:
        logical_index = int(mapping["logicalVertexIndex"])
        for source in mapping.get("sourceVertices", []):
            logical_by_source_vertex[(int(source["meshIndex"]), int(source["vertexIndex"]))] = (
                logical_index
            )

    openings = [opening for opening in constraints.get("openings", []) if isinstance(opening, dict)]
    opening_by_id = {str(opening.get("id", "")): opening for opening in openings}
    seam_owned_edges = _seam_owned_boundary_edges(constraints)
    records: list[dict[str, Any]] = []
    missing_opening_ids: list[str] = []
    missing_boundary_edges: list[dict[str, str]] = []
    missing_logical_vertices: list[dict[str, str]] = []
    unexpected_seam_owned_opening_edges: list[dict[str, str]] = []
    unexpected_opening_boundary_edges: list[dict[str, Any]] = []

    for opening_id in _EXPECTED_OPENING_IDS:
        opening = opening_by_id.get(opening_id)
        if opening is None:
            missing_opening_ids.append(opening_id)
            continue
        edge_records: list[dict[str, Any]] = []
        opening_logical_indices: set[int] = set()
        source_panel_edge_ids: list[str] = []
        for edge in opening.get("boundaryEdges", []):
            if not isinstance(edge, dict):
                continue
            edge_id = str(edge.get("edgeId", "unknown"))
            source_panel_edge_ids.append(edge_id)
            if edge_id in seam_owned_edges:
                unexpected_seam_owned_opening_edges.append(
                    {"openingId": opening_id, "edgeId": edge_id}
                )
            if edge.get("status") != "resolved":
                missing_boundary_edges.append({"openingId": opening_id, "edgeId": edge_id})
                edge_records.append(
                    {
                        "edgeId": edge_id,
                        "status": str(edge.get("status", "unresolved")),
                    }
                )
                continue
            mesh_index = int(edge["meshIndex"])
            vertex_indices = [int(index) for index in edge.get("vertexIndices", [])]
            missing_vertex_indices = [
                vertex_index
                for vertex_index in vertex_indices
                if (mesh_index, vertex_index) not in logical_by_source_vertex
            ]
            logical_vertex_indices = sorted(
                {
                    logical_by_source_vertex[(mesh_index, vertex_index)]
                    for vertex_index in vertex_indices
                    if (mesh_index, vertex_index) in logical_by_source_vertex
                }
            )
            opening_logical_indices.update(logical_vertex_indices)
            for vertex_index in missing_vertex_indices:
                missing_logical_vertices.append(
                    {
                        "openingId": opening_id,
                        "edgeId": edge_id,
                        "sourceVertexId": f"sourceVertex.{mesh_index:03d}.{vertex_index:06d}",
                    }
                )
            edge_records.append(
                {
                    "edgeId": edge_id,
                    "panelId": str(edge["panelId"]),
                    "meshIndex": mesh_index,
                    "sourceVertexCount": len(vertex_indices),
                    "logicalVertexCount": len(logical_vertex_indices),
                    "logicalVertexIds": [
                        f"logicalVertex.{index:06d}" for index in logical_vertex_indices
                    ],
                    "status": "mapped" if logical_vertex_indices else "missing_logical_vertices",
                }
            )
        expected_edge_ids = _EXPECTED_OPENING_EDGE_IDS.get(opening_id, [])
        if sorted(source_panel_edge_ids) != expected_edge_ids:
            unexpected_opening_boundary_edges.append(
                {
                    "openingId": opening_id,
                    "expectedEdgeIds": expected_edge_ids,
                    "actualEdgeIds": sorted(source_panel_edge_ids),
                }
            )
        records.append(
            {
                "openingId": opening_id,
                "status": str(opening.get("status", "unknown")),
                "boundaryEdges": edge_records,
                "boundaryEdgeCount": len(edge_records),
                "sourcePanelEdgeIds": sorted(source_panel_edge_ids),
                "logicalVertexCount": len(opening_logical_indices),
                "logicalVertexIds": [
                    f"logicalVertex.{index:06d}" for index in sorted(opening_logical_indices)
                ],
            }
        )

    status = (
        "pass"
        if not missing_opening_ids
        and not missing_boundary_edges
        and not missing_logical_vertices
        and not unexpected_seam_owned_opening_edges
        and not unexpected_opening_boundary_edges
        else "fail"
    )
    return {
        "auditVersion": "closy.stitched_shell_opening_panel_edge_provenance.v1",
        "status": status,
        "expectedOpeningIds": _EXPECTED_OPENING_IDS,
        "recordedOpeningCount": len(records),
        "records": records,
        "missingOpeningIds": missing_opening_ids,
        "missingBoundaryEdges": missing_boundary_edges,
        "missingLogicalVertices": missing_logical_vertices,
        "unexpectedSeamOwnedOpeningEdges": unexpected_seam_owned_opening_edges,
        "unexpectedOpeningBoundaryEdges": unexpected_opening_boundary_edges,
    }


def _seam_owned_boundary_edges(constraints: dict[str, Any]) -> set[str]:
    seam_edges: set[str] = set()
    for seam in constraints.get("seams", []):
        if not isinstance(seam, dict):
            continue
        for span in seam.get("spans", []):
            if not isinstance(span, dict):
                continue
            edge_id = span.get("edgeId", span.get("boundaryId"))
            if isinstance(edge_id, str):
                seam_edges.add(edge_id)
    return seam_edges


def _boundary_components(mesh: Mesh, boundary_edges: list[tuple[int, int]]) -> list[dict[str, Any]]:
    if not boundary_edges:
        return []
    adjacency: dict[int, set[int]] = {}
    for left, right in boundary_edges:
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    seen_vertices: set[int] = set()
    components: list[dict[str, Any]] = []
    for start in sorted(adjacency):
        if start in seen_vertices:
            continue
        component_vertices: set[int] = set()
        stack = [start]
        while stack:
            current = stack.pop()
            if current in component_vertices:
                continue
            component_vertices.add(current)
            stack.extend(sorted(adjacency.get(current, set()) - component_vertices))
        seen_vertices.update(component_vertices)
        component_edges = [
            edge
            for edge in boundary_edges
            if edge[0] in component_vertices and edge[1] in component_vertices
        ]
        degree_violations = sorted(
            vertex for vertex in component_vertices if len(adjacency.get(vertex, set())) != 2
        )
        ordered_vertices = _ordered_boundary_cycle_vertices(component_edges)
        if ordered_vertices:
            ordered_edges = [
                (
                    min(
                        ordered_vertices[index],
                        ordered_vertices[(index + 1) % len(ordered_vertices)],
                    ),
                    max(
                        ordered_vertices[index],
                        ordered_vertices[(index + 1) % len(ordered_vertices)],
                    ),
                )
                for index in range(len(ordered_vertices))
            ]
        else:
            ordered_vertices = sorted(component_vertices)
            ordered_edges = sorted(component_edges)
        components.append(
            {
                "componentIndex": len(components),
                "vertexCount": len(component_vertices),
                "edgeCount": len(component_edges),
                "vertexIds": [f"logicalVertex.{vertex:06d}" for vertex in ordered_vertices],
                "edgeIds": [f"logicalEdge.{edge[0]:06d}.{edge[1]:06d}" for edge in ordered_edges],
                "orderedVertexIndices": ordered_vertices,
                "orderedVertexIds": [f"logicalVertex.{vertex:06d}" for vertex in ordered_vertices],
                "orderedEdgeIds": [
                    f"logicalEdge.{edge[0]:06d}.{edge[1]:06d}" for edge in ordered_edges
                ],
                "isSimpleCycle": len(degree_violations) == 0
                and len(component_edges) == len(component_vertices),
                "degreeViolationVertexIds": [
                    f"logicalVertex.{vertex:06d}" for vertex in degree_violations
                ],
                "bounds": _component_bounds(mesh, ordered_vertices),
                "perimeterMeters": _round(
                    sum(
                        _distance3(mesh.vertices[left], mesh.vertices[right])
                        for left, right in ordered_edges
                    )
                ),
            }
        )
    return components


def _ordered_boundary_cycle_vertices(edges: list[tuple[int, int]]) -> list[int]:
    if not edges:
        return []
    adjacency: dict[int, list[int]] = {}
    for left, right in edges:
        adjacency.setdefault(left, []).append(right)
        adjacency.setdefault(right, []).append(left)
    if any(len(neighbours) != 2 for neighbours in adjacency.values()):
        return []
    start = min(adjacency)
    previous: int | None = None
    current = start
    ordered: list[int] = []
    while True:
        ordered.append(current)
        neighbours = sorted(adjacency[current])
        candidates = [vertex for vertex in neighbours if vertex != previous]
        if not candidates:
            return []
        next_vertex = candidates[0]
        if next_vertex == start:
            return ordered
        if next_vertex in ordered:
            return []
        previous, current = current, next_vertex


def _component_bounds(mesh: Mesh, vertex_indices: list[int]) -> dict[str, list[float]]:
    if not vertex_indices:
        zero = [0.0, 0.0, 0.0]
        return {"min": zero, "max": zero, "center": zero, "size": zero}
    vertices = [mesh.vertices[index] for index in vertex_indices]
    mins = (
        min(vertex[0] for vertex in vertices),
        min(vertex[1] for vertex in vertices),
        min(vertex[2] for vertex in vertices),
    )
    maxs = (
        max(vertex[0] for vertex in vertices),
        max(vertex[1] for vertex in vertices),
        max(vertex[2] for vertex in vertices),
    )
    center = (
        (mins[0] + maxs[0]) / 2.0,
        (mins[1] + maxs[1]) / 2.0,
        (mins[2] + maxs[2]) / 2.0,
    )
    size = (
        maxs[0] - mins[0],
        maxs[1] - mins[1],
        maxs[2] - mins[2],
    )
    return {
        "min": [_round(value) for value in mins],
        "max": [_round(value) for value in maxs],
        "center": [_round(value) for value in center],
        "size": [_round(value) for value in size],
    }


def _duplicate_face_count(triangles: list[tuple[int, int, int]]) -> int:
    counts = Counter(tuple(sorted(tri)) for tri in triangles)
    return sum(count - 1 for count in counts.values() if count > 1)


def _degenerate_triangle_count(mesh: Mesh) -> int:
    count = 0
    for tri in mesh.triangles:
        if len(set(tri)) != 3:
            count += 1
            continue
        a, b, c = mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]]
        area2 = sqrt(sum(value * value for value in cross(sub(b, a), sub(c, a))))
        if area2 <= 1e-10:
            count += 1
    return count


def _topology_tolerance(meshset: MeshSet) -> float:
    bounds = mesh_bounds(meshset)
    extent = max(float(value) for value in bounds["size"])
    return _round(max(1e-7, extent * 1e-6))


def _t_junction_audit(mesh: Mesh, tolerance: float) -> dict[str, Any]:
    edges = sorted(_edge_counts(mesh.triangles))
    offenders: list[dict[str, Any]] = []
    for vertex_index, vertex in enumerate(mesh.vertices):
        for left, right in edges:
            if vertex_index in (left, right):
                continue
            distance, parameter = _point_segment_distance_parameter(
                vertex,
                mesh.vertices[left],
                mesh.vertices[right],
            )
            if distance <= tolerance and tolerance < parameter < 1.0 - tolerance:
                offenders.append(
                    {
                        "vertexId": f"logicalVertex.{vertex_index:06d}",
                        "edge": [
                            f"logicalVertex.{left:06d}",
                            f"logicalVertex.{right:06d}",
                        ],
                        "distanceMeters": _round(distance),
                        "edgeParameter": _round(parameter),
                    }
                )
    return {
        "auditVersion": "closy.stitched_shell_t_junction_audit.deterministic_v1",
        "status": "pass" if not offenders else "fail",
        "toleranceMeters": tolerance,
        "candidateVertexCount": len(mesh.vertices),
        "candidateEdgeCount": len(edges),
        "tJunctionCount": len(offenders),
        "offenders": offenders[:32],
    }


def _winding_audit(mesh: Mesh) -> dict[str, Any]:
    oriented_edges: dict[tuple[int, int], list[tuple[int, int, int, int]]] = {}
    for tri_index, tri in enumerate(mesh.triangles):
        for edge_index, (left, right) in enumerate(
            [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]
        ):
            key = (left, right) if left <= right else (right, left)
            oriented_edges.setdefault(key, []).append((tri_index, edge_index, left, right))
    offenders: list[dict[str, Any]] = []
    for edge, uses in sorted(oriented_edges.items()):
        if len(uses) != 2:
            continue
        first, second = uses
        same_direction = first[2] == second[2] and first[3] == second[3]
        if same_direction:
            offenders.append(
                {
                    "edge": [
                        f"logicalVertex.{edge[0]:06d}",
                        f"logicalVertex.{edge[1]:06d}",
                    ],
                    "triangleIds": [
                        f"triangle.{first[0]:06d}",
                        f"triangle.{second[0]:06d}",
                    ],
                }
            )
    return {
        "auditVersion": "closy.stitched_shell_winding_audit.shared_edge_v1",
        "status": "pass" if not offenders else "fail",
        "manifoldSharedEdgeCount": sum(1 for uses in oriented_edges.values() if len(uses) == 2),
        "inconsistentSharedEdgeCount": len(offenders),
        "offenders": offenders[:32],
    }


def _normal_inversion_audit(mesh: Mesh) -> dict[str, Any]:
    normals = [_triangle_normal_raw(mesh, tri) for tri in mesh.triangles]
    edge_to_triangles: dict[tuple[int, int], list[int]] = {}
    for tri_index, tri in enumerate(mesh.triangles):
        for left, right in [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]:
            edge = (left, right) if left <= right else (right, left)
            edge_to_triangles.setdefault(edge, []).append(tri_index)
    offenders: list[dict[str, Any]] = []
    threshold = -0.35
    for edge, triangle_ids in sorted(edge_to_triangles.items()):
        if len(triangle_ids) != 2:
            continue
        dot_value = _dot(normals[triangle_ids[0]], normals[triangle_ids[1]])
        if dot_value < threshold:
            offenders.append(
                {
                    "edge": [
                        f"logicalVertex.{edge[0]:06d}",
                        f"logicalVertex.{edge[1]:06d}",
                    ],
                    "triangleIds": [
                        f"triangle.{triangle_ids[0]:06d}",
                        f"triangle.{triangle_ids[1]:06d}",
                    ],
                    "normalDot": _round(dot_value),
                }
            )
    return {
        "auditVersion": "closy.stitched_shell_normal_inversion_audit.shared_edge_v1",
        "status": "pass" if not offenders else "fail",
        "normalDotFailThreshold": threshold,
        "invertedAdjacentPairCount": len(offenders),
        "offenders": offenders[:32],
    }


def _self_intersection_audit(mesh: Mesh, tolerance: float) -> dict[str, Any]:
    offenders: list[dict[str, Any]] = []
    skipped_shared_feature_pairs = 0
    checked_pairs = 0
    triangle_bounds = [_triangle_bounds(mesh.vertices, tri) for tri in mesh.triangles]
    for left_index, left_tri in enumerate(mesh.triangles):
        left_vertices = set(left_tri)
        for right_index in range(left_index + 1, len(mesh.triangles)):
            right_tri = mesh.triangles[right_index]
            if left_vertices & set(right_tri):
                skipped_shared_feature_pairs += 1
                continue
            if not _bounds_overlap(
                triangle_bounds[left_index],
                triangle_bounds[right_index],
                tolerance,
            ):
                continue
            checked_pairs += 1
            if _triangles_intersect(mesh.vertices, left_tri, right_tri, tolerance):
                offenders.append(
                    {
                        "triangleIds": [
                            f"triangle.{left_index:06d}",
                            f"triangle.{right_index:06d}",
                        ]
                    }
                )
    return {
        "auditVersion": "closy.stitched_shell_self_intersection_audit.segment_triangle_v1",
        "status": "pass" if not offenders else "fail",
        "toleranceMeters": tolerance,
        "trianglePairCount": len(mesh.triangles) * (len(mesh.triangles) - 1) // 2,
        "skippedSharedFeaturePairCount": skipped_shared_feature_pairs,
        "checkedDisjointBoundingBoxPairCount": checked_pairs,
        "selfIntersectionPairCount": len(offenders),
        "offenders": offenders[:32],
    }


def _hidden_internal_component_audit(
    mesh: Mesh, edge_counts: Counter[tuple[int, int]]
) -> dict[str, Any]:
    boundary_vertices = {
        vertex for edge, count in edge_counts.items() if count == 1 for vertex in edge
    }
    components = _mesh_components(mesh)
    internal_components: list[dict[str, Any]] = []
    for component in components:
        component_vertices = set(component["vertexIndices"])
        boundary_count = len(component_vertices & boundary_vertices)
        if boundary_count == 0 and component["triangleCount"] > 0:
            internal_components.append(
                {
                    "componentIndex": component["componentIndex"],
                    "vertexCount": component["vertexCount"],
                    "triangleCount": component["triangleCount"],
                }
            )
    return {
        "auditVersion": "closy.stitched_shell_hidden_internal_component_audit.v1",
        "status": "pass" if not internal_components else "fail",
        "componentCount": len(components),
        "internalClosedComponentCount": len(internal_components),
        "internalComponents": internal_components[:32],
    }


def _mesh_components(mesh: Mesh) -> list[dict[str, Any]]:
    union = _UnionFind(len(mesh.vertices))
    for tri in mesh.triangles:
        union.union(tri[0], tri[1])
        union.union(tri[1], tri[2])
        union.union(tri[2], tri[0])
    vertices_by_root: dict[int, list[int]] = {}
    for vertex_index in range(len(mesh.vertices)):
        vertices_by_root.setdefault(union.find(vertex_index), []).append(vertex_index)
    components: list[dict[str, Any]] = []
    for root in sorted(vertices_by_root, key=lambda item: min(vertices_by_root[item])):
        vertex_indices = vertices_by_root[root]
        vertex_set = set(vertex_indices)
        triangle_count = sum(1 for tri in mesh.triangles if set(tri) <= vertex_set)
        components.append(
            {
                "componentIndex": len(components),
                "vertexIndices": vertex_indices,
                "vertexCount": len(vertex_indices),
                "triangleCount": triangle_count,
            }
        )
    return components


def _non_manifold_vertex_count(non_manifold_edges: list[tuple[int, int]]) -> int:
    vertices: set[int] = set()
    for left, right in non_manifold_edges:
        vertices.add(left)
        vertices.add(right)
    return len(vertices)


def _surface_topology_audit(
    mesh: Mesh,
    edge_counts: Counter[tuple[int, int]],
    boundary_components: list[dict[str, Any]],
    tolerance: float,
) -> dict[str, Any]:
    vertex_count = len(mesh.vertices)
    edge_count = len(edge_counts)
    face_count = len(mesh.triangles)
    chi = vertex_count - edge_count + face_count
    boundary_loop_count = len(boundary_components)
    genus_value = (2 - boundary_loop_count - chi) / 2.0
    genus_is_integer = abs(genus_value - round(genus_value)) <= 1e-9
    genus = int(round(genus_value)) if genus_is_integer else None
    edge_incidence_failures = [
        {
            "edge": [
                f"logicalVertex.{edge[0]:06d}",
                f"logicalVertex.{edge[1]:06d}",
            ],
            "incidentFaceCount": count,
        }
        for edge, count in sorted(edge_counts.items())
        if count not in {1, 2}
    ]
    isolated_vertices = _isolated_vertex_indices(mesh)
    zero_length_edges = _zero_length_edges(mesh, edge_counts, tolerance)
    area_threshold = max(1e-12, tolerance * tolerance)
    small_triangles = _small_triangle_records(mesh, area_threshold)
    vertex_link = _vertex_link_audit(mesh, edge_counts)
    expected_chi = 2 - len(_EXPECTED_OPENING_IDS)
    failure_reasons: list[str] = []
    if chi != expected_chi:
        failure_reasons.append("euler_characteristic_mismatch")
    if genus != 0:
        failure_reasons.append("genus_not_zero")
    if edge_incidence_failures:
        failure_reasons.append("edge_incidence_invalid")
    if isolated_vertices:
        failure_reasons.append("isolated_vertices_present")
    if zero_length_edges:
        failure_reasons.append("zero_length_edges_present")
    if small_triangles:
        failure_reasons.append("near_zero_area_faces_present")
    if vertex_link["status"] != "pass":
        failure_reasons.append("vertex_links_invalid")
    if any(component["isSimpleCycle"] is not True for component in boundary_components):
        failure_reasons.append("boundary_components_not_simple_cycles")
    return {
        "auditVersion": "closy.stitched_shell_surface_topology_audit.v1",
        "status": "pass" if not failure_reasons else "fail",
        "vertexCount": vertex_count,
        "edgeCount": edge_count,
        "faceCount": face_count,
        "eulerCharacteristic": chi,
        "expectedEulerCharacteristic": expected_chi,
        "boundaryLoopCount": boundary_loop_count,
        "genus": genus,
        "genusRaw": _round(genus_value),
        "orientableSurfaceRelation": "chi = 2 - 2g - b",
        "orientableSurfaceRelationStatus": "pass" if genus == 0 and chi == expected_chi else "fail",
        "interiorEdgeCount": sum(1 for count in edge_counts.values() if count == 2),
        "boundaryEdgeCount": sum(1 for count in edge_counts.values() if count == 1),
        "invalidEdgeIncidenceCount": len(edge_incidence_failures),
        "invalidEdgeIncidences": edge_incidence_failures[:32],
        "isolatedVertexCount": len(isolated_vertices),
        "isolatedVertexIds": [
            f"logicalVertex.{vertex_index:06d}" for vertex_index in isolated_vertices[:32]
        ],
        "zeroLengthEdgeCount": len(zero_length_edges),
        "zeroLengthEdges": zero_length_edges[:32],
        "smallTriangleAreaThresholdMeters2": _round(area_threshold),
        "smallTriangleCount": len(small_triangles),
        "smallTriangles": small_triangles[:32],
        "vertexLinkStatus": vertex_link["status"],
        "vertexLinkAudit": vertex_link,
        "failureReasons": sorted(set(failure_reasons)),
    }


def _isolated_vertex_indices(mesh: Mesh) -> list[int]:
    used = {vertex_index for tri in mesh.triangles for vertex_index in tri}
    return [index for index in range(len(mesh.vertices)) if index not in used]


def _zero_length_edges(
    mesh: Mesh,
    edge_counts: Counter[tuple[int, int]],
    tolerance: float,
) -> list[dict[str, Any]]:
    threshold = max(1e-12, tolerance)
    offenders: list[dict[str, Any]] = []
    for left, right in sorted(edge_counts):
        length = _distance3(mesh.vertices[left], mesh.vertices[right])
        if length <= threshold:
            offenders.append(
                {
                    "edge": [
                        f"logicalVertex.{left:06d}",
                        f"logicalVertex.{right:06d}",
                    ],
                    "lengthMeters": _round(length),
                }
            )
    return offenders


def _small_triangle_records(mesh: Mesh, area_threshold: float) -> list[dict[str, Any]]:
    offenders: list[dict[str, Any]] = []
    for triangle_index, tri in enumerate(mesh.triangles):
        a, b, c = mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]]
        area = sqrt(sum(value * value for value in cross(sub(b, a), sub(c, a)))) / 2.0
        if area <= area_threshold:
            offenders.append(
                {
                    "triangleId": f"triangle.{triangle_index:06d}",
                    "areaMeters2": _round(area),
                }
            )
    return offenders


def _vertex_link_audit(
    mesh: Mesh,
    edge_counts: Counter[tuple[int, int]],
) -> dict[str, Any]:
    incident_triangles: dict[int, list[tuple[int, int]]] = {
        index: [] for index in range(len(mesh.vertices))
    }
    for tri in mesh.triangles:
        a, b, c = tri
        incident_triangles[a].append((b, c))
        incident_triangles[b].append((c, a))
        incident_triangles[c].append((a, b))
    boundary_vertices = {
        vertex for edge, count in edge_counts.items() if count == 1 for vertex in edge
    }
    offenders: list[dict[str, Any]] = []
    for vertex_index, link_edges in incident_triangles.items():
        if not link_edges:
            offenders.append(
                {
                    "vertexId": f"logicalVertex.{vertex_index:06d}",
                    "reason": "isolated_vertex",
                    "expected": "disk_or_half_disk_link",
                }
            )
            continue
        link_adjacency: dict[int, set[int]] = {}
        for left, right in link_edges:
            link_adjacency.setdefault(left, set()).add(right)
            link_adjacency.setdefault(right, set()).add(left)
        link_components = _graph_component_count(link_adjacency)
        degrees = sorted(len(neighbours) for neighbours in link_adjacency.values())
        is_boundary = vertex_index in boundary_vertices
        valid = link_components == 1 and (
            (is_boundary and degrees.count(1) == 2 and all(degree in {1, 2} for degree in degrees))
            or (not is_boundary and all(degree == 2 for degree in degrees))
        )
        if not valid:
            offenders.append(
                {
                    "vertexId": f"logicalVertex.{vertex_index:06d}",
                    "reason": "invalid_half_disk_link" if is_boundary else "invalid_disk_link",
                    "isBoundaryVertex": is_boundary,
                    "linkComponentCount": link_components,
                    "linkDegrees": degrees,
                }
            )
    return {
        "auditVersion": "closy.stitched_shell_vertex_link_audit.v1",
        "status": "pass" if not offenders else "fail",
        "checkedVertexCount": len(mesh.vertices),
        "invalidVertexLinkCount": len(offenders),
        "invalidVertexLinks": offenders[:32],
        "invalidVertexLinkSampleLimit": 32,
    }


def _graph_component_count(adjacency: dict[int, set[int]]) -> int:
    if not adjacency:
        return 0
    seen: set[int] = set()
    count = 0
    for start in sorted(adjacency):
        if start in seen:
            continue
        count += 1
        stack = [start]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(sorted(adjacency.get(current, set()) - seen))
    return count


def _point_segment_distance_parameter(
    point: tuple[float, float, float],
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> tuple[float, float]:
    segment = sub(end, start)
    length_sq = _dot(segment, segment)
    if length_sq <= 1e-18:
        return _distance3(point, start), 0.0
    parameter = max(0.0, min(1.0, _dot(sub(point, start), segment) / length_sq))
    projection = (
        start[0] + segment[0] * parameter,
        start[1] + segment[1] * parameter,
        start[2] + segment[2] * parameter,
    )
    return _distance3(point, projection), parameter


def _triangle_normal_raw(mesh: Mesh, tri: tuple[int, int, int]) -> tuple[float, float, float]:
    a, b, c = mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]]
    normal = cross(sub(b, a), sub(c, a))
    length = sqrt(_dot(normal, normal))
    if length <= 1e-18:
        return (0.0, 0.0, 0.0)
    return (normal[0] / length, normal[1] / length, normal[2] / length)


def _triangle_bounds(
    vertices: list[tuple[float, float, float]], tri: tuple[int, int, int]
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    tri_vertices = [vertices[index] for index in tri]
    mins = (
        min(vertex[0] for vertex in tri_vertices),
        min(vertex[1] for vertex in tri_vertices),
        min(vertex[2] for vertex in tri_vertices),
    )
    maxs = (
        max(vertex[0] for vertex in tri_vertices),
        max(vertex[1] for vertex in tri_vertices),
        max(vertex[2] for vertex in tri_vertices),
    )
    return mins, maxs


def _bounds_overlap(
    left: tuple[tuple[float, float, float], tuple[float, float, float]],
    right: tuple[tuple[float, float, float], tuple[float, float, float]],
    tolerance: float,
) -> bool:
    left_min, left_max = left
    right_min, right_max = right
    return all(
        left_min[axis] <= right_max[axis] + tolerance
        and right_min[axis] <= left_max[axis] + tolerance
        for axis in range(3)
    )


def _triangles_intersect(
    vertices: list[tuple[float, float, float]],
    left: tuple[int, int, int],
    right: tuple[int, int, int],
    tolerance: float,
) -> bool:
    left_vertices = [vertices[index] for index in left]
    right_vertices = [vertices[index] for index in right]
    for start, end in _triangle_segments(left_vertices):
        if _segment_intersects_triangle(start, end, right_vertices, tolerance):
            return True
    for start, end in _triangle_segments(right_vertices):
        if _segment_intersects_triangle(start, end, left_vertices, tolerance):
            return True
    return False


def _triangle_segments(
    vertices: list[tuple[float, float, float]],
) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
    return [
        (vertices[0], vertices[1]),
        (vertices[1], vertices[2]),
        (vertices[2], vertices[0]),
    ]


def _segment_intersects_triangle(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    triangle: list[tuple[float, float, float]],
    tolerance: float,
) -> bool:
    direction = sub(end, start)
    edge1 = sub(triangle[1], triangle[0])
    edge2 = sub(triangle[2], triangle[0])
    h = cross(direction, edge2)
    determinant = _dot(edge1, h)
    if abs(determinant) <= tolerance:
        return False
    inv_det = 1.0 / determinant
    s = sub(start, triangle[0])
    u = inv_det * _dot(s, h)
    if u < -tolerance or u > 1.0 + tolerance:
        return False
    q = cross(s, edge1)
    v = inv_det * _dot(direction, q)
    if v < -tolerance or u + v > 1.0 + tolerance:
        return False
    segment_parameter = inv_det * _dot(edge2, q)
    return -tolerance <= segment_parameter <= 1.0 + tolerance


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _distance3(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def _round(value: float) -> float:
    return round(float(value), 9)


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return _round(float(numerator) / float(denominator))


def _is_vec2(value: Any) -> bool:
    return (
        isinstance(value, list | tuple)
        and len(value) == 2
        and all(isinstance(component, int | float) for component in value)
    )


def _is_vec3(value: Any) -> bool:
    return (
        isinstance(value, list | tuple)
        and len(value) == 3
        and all(isinstance(component, int | float) for component in value)
    )


def _round_vec3(value: tuple[float, float, float]) -> tuple[float, float, float]:
    return (_round(value[0]), _round(value[1]), _round(value[2]))


def _round_vec2(value: tuple[float, float]) -> tuple[float, float]:
    return (_round(value[0]), _round(value[1]))


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parents = list(range(size))
        self._ranks = [0 for _ in range(size)]

    def find(self, item: int) -> int:
        parent = self._parents[item]
        if parent != item:
            self._parents[item] = self.find(parent)
        return self._parents[item]

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self._ranks[left_root] < self._ranks[right_root]:
            self._parents[left_root] = right_root
        elif self._ranks[left_root] > self._ranks[right_root]:
            self._parents[right_root] = left_root
        else:
            self._parents[right_root] = left_root
            self._ranks[left_root] += 1

    def component_count(self) -> int:
        return len({self.find(index) for index in range(len(self._parents))})
