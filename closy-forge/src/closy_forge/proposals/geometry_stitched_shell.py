from __future__ import annotations

from collections import Counter
from copy import deepcopy
from math import sqrt
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet, cross, finite_mesh, mesh_bounds, sub
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, topology_hash

GEOMETRY_STITCHED_SHELL_VERSION = "closy.geometry_stitched_shell.logical_asset_v2"

_PRE_STITCH_REPAIR_THRESHOLD_METERS = 0.15
_POST_STITCH_TOLERANCE_METERS = 1e-8
_EXPECTED_OPENING_IDS = [
    "opening.neck",
    "opening.hem",
    "opening.cuff.left",
    "opening.cuff.right",
]


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

    stitched_mesh, source_vertex_map, operations = _build_logical_stitched_mesh(
        source_simulation_mesh,
        constraints,
    )
    topology_audit = audit_stitched_shell(
        stitched_mesh,
        source_vertex_map=source_vertex_map,
        operations=operations,
        constraints=constraints,
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
) -> dict[str, Any]:
    mesh = meshset.meshes[0]
    edge_counts = _edge_counts(mesh.triangles)
    boundary_edges = [edge for edge, count in edge_counts.items() if count == 1]
    non_manifold_edges = [edge for edge, count in edge_counts.items() if count > 2]
    duplicate_faces = _duplicate_face_count(mesh.triangles)
    degenerate_triangles = _degenerate_triangle_count(mesh)
    boundary_components = _boundary_components(boundary_edges)
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
    provenance_coverage = _provenance_coverage(source_vertex_map, mesh)
    binding_coverage = _binding_coverage(mesh)
    displacement_metrics = _source_displacement_metrics(source_vertex_map, meshset)
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
        "simpleBoundaryCycleCount": len(simple_boundary_cycles),
        "boundaryBranchVertexCount": len(boundary_branch_vertices),
        "boundaryBranchVertexIds": boundary_branch_vertices,
        "expectedOpeningCount": len(_EXPECTED_OPENING_IDS),
        "unexpectedBoundaryLoopCount": max(
            0,
            len(simple_boundary_cycles) - len(_EXPECTED_OPENING_IDS),
        ),
        "missingExpectedOpeningCount": len(_EXPECTED_OPENING_IDS),
        "provenOpeningCount": 0,
        "nonManifoldEdgeCount": len(non_manifold_edges),
        "nonManifoldVertexCount": _non_manifold_vertex_count(non_manifold_edges),
        "duplicateFaceCount": duplicate_faces,
        "degenerateTriangleCount": degenerate_triangles,
        "tJunctionCheckStatus": "not_run",
        "inconsistentWindingCheckStatus": "not_run",
        "normalInversionCheckStatus": "not_run",
        "selfIntersectionCheckStatus": "not_run",
        "hiddenInternalComponentCheckStatus": "not_run",
        "seamSpanCoverage": seam_coverage,
        "uvMaterialPanelProvenanceCoverage": provenance_coverage["coverageRatio"],
        "uvMaterialPanelProvenance": provenance_coverage,
        "bindingCoverage": binding_coverage["coverageRatio"],
        "bindingEvidence": binding_coverage,
        "bindingReconstructionStatus": "not_run",
        "bindingReconstructionErrorMeters": None,
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
) -> tuple[MeshSet, list[dict[str, Any]], list[dict[str, Any]]]:
    offsets: list[int] = []
    total_vertices = 0
    for mesh in source_mesh.meshes:
        offsets.append(total_vertices)
        total_vertices += len(mesh.vertices)
    union = _UnionFind(total_vertices)
    operations: list[dict[str, Any]] = []
    for constraint in sorted(
        constraints.get("constraints", []),
        key=lambda item: str(item.get("id", "")) if isinstance(item, dict) else "",
    ):
        if not isinstance(constraint, dict):
            continue
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
                "operationId": str(constraint.get("id", f"constraint.{len(operations):03d}")),
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
    for mesh_index, mesh in enumerate(source_mesh.meshes):
        offset = offsets[mesh_index]
        for tri in mesh.triangles:
            remapped = (
                remap[offset + tri[0]],
                remap[offset + tri[1]],
                remap[offset + tri[2]],
            )
            if len(set(remapped)) == 3:
                logical_triangles.append(remapped)
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
    return stitched_mesh, source_vertex_map, operations


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
        and audit["nonManifoldEdgeCount"] == 0
        and audit["nonManifoldVertexCount"] == 0
        and audit["duplicateFaceCount"] == 0
        and audit["degenerateTriangleCount"] == 0
        and audit["unexpectedBoundaryLoopCount"] == 0
        and audit["boundaryLoopCount"] == len(_EXPECTED_OPENING_IDS)
        and audit["simpleBoundaryCycleCount"] == len(_EXPECTED_OPENING_IDS)
        and audit["boundaryBranchVertexCount"] == 0
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
    if audit["nonManifoldEdgeCount"] > 0:
        reasons.append("stitched_shell_non_manifold_edges")
    if audit["nonManifoldVertexCount"] > 0:
        reasons.append("stitched_shell_non_manifold_vertices")
    if audit["duplicateFaceCount"] > 0:
        reasons.append("stitched_shell_duplicate_faces")
    if audit["degenerateTriangleCount"] > 0:
        reasons.append("stitched_shell_degenerate_triangles")
    if audit["unexpectedBoundaryLoopCount"] > 0 or audit["boundaryLoopCount"] != len(
        _EXPECTED_OPENING_IDS
    ):
        reasons.append("stitched_shell_opening_loop_mismatch")
    if audit["missingExpectedOpeningCount"] > 0:
        reasons.append("stitched_shell_opening_semantics_missing")
    if audit["boundaryBranchVertexCount"] > 0:
        reasons.append("stitched_shell_branched_boundary_graph")
    for field, code in [
        ("tJunctionCheckStatus", "t_junction_audit_not_run"),
        ("inconsistentWindingCheckStatus", "winding_audit_not_run"),
        ("normalInversionCheckStatus", "normal_inversion_audit_not_run"),
        ("hiddenInternalComponentCheckStatus", "hidden_internal_component_audit_not_run"),
    ]:
        if audit[field] == "not_run":
            reasons.append(code)
    if audit["selfIntersectionCheckStatus"] == "not_run":
        reasons.append("self_intersection_not_run")
    if audit["uvMaterialPanelProvenanceCoverage"] < 1.0:
        reasons.append("uv_material_panel_provenance_incomplete")
    if audit["bindingCoverage"] < 1.0:
        reasons.append("binding_coverage_incomplete")
    if audit["bindingReconstructionStatus"] != "pass":
        reasons.append("binding_reconstruction_not_run")
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
    # Semantic opening assignment requires a simple boundary cycle and an explicit
    # loop-to-opening map. BP-46 currently exposes the missing proof instead of
    # deriving opening IDs from fixture expectations.
    proven_opening_ids: list[str] = []
    missing_ids = [
        opening_id for opening_id in _EXPECTED_OPENING_IDS if opening_id not in proven_opening_ids
    ]
    return {
        "expectedOpeningIds": _EXPECTED_OPENING_IDS,
        "expectedOpeningCount": len(_EXPECTED_OPENING_IDS),
        "topologicalBoundaryComponentCount": topology_audit["boundaryLoopCount"],
        "simpleBoundaryCycleCount": topology_audit["simpleBoundaryCycleCount"],
        "boundaryBranchVertexCount": topology_audit["boundaryBranchVertexCount"],
        "provenOpeningIds": proven_opening_ids,
        "provenOpeningCount": len(proven_opening_ids),
        "missingExpectedOpeningIds": missing_ids,
        "missingExpectedOpeningCount": len(missing_ids),
        "unexpectedBoundaryLoopCount": topology_audit["unexpectedBoundaryLoopCount"],
        "status": "pass"
        if not missing_ids and topology_audit["unexpectedBoundaryLoopCount"] == 0
        else "fail",
        "limitations": [
            (
                "semantic loop-to-opening assignment is not implemented yet; "
                "BP-47 inspection overlays may visualize these rejected boundaries"
            ),
        ],
    }


def _seam_span_coverage(
    operations: list[dict[str, Any]], constraints: dict[str, Any]
) -> dict[str, Any]:
    input_constraints = constraints.get("constraints", [])
    required_ids = [
        str(constraint.get("id", f"constraint.{index:03d}"))
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


def _binding_coverage(mesh: Mesh) -> dict[str, Any]:
    required_vertices = len(mesh.vertices)
    return {
        "bindingStatus": "not_run",
        "requiredRenderVertexCount": required_vertices,
        "boundRenderVertexCount": 0,
        "coverageRatio": 0.0,
        "missingRenderVertexIds": [
            f"logicalVertex.{index:06d}" for index in range(required_vertices)
        ],
        "bindingRecordCount": 0,
        "bindingFormat": None,
        "bindingAssetPath": None,
        "reconstructionStatus": "not_run",
        "maxReconstructionErrorMeters": None,
        "rmsReconstructionErrorMeters": None,
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


def _boundary_components(boundary_edges: list[tuple[int, int]]) -> list[dict[str, Any]]:
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
            if edge[0] in component_vertices or edge[1] in component_vertices
        ]
        degree_violations = sorted(
            vertex for vertex in component_vertices if len(adjacency.get(vertex, set())) != 2
        )
        components.append(
            {
                "componentIndex": len(components),
                "vertexCount": len(component_vertices),
                "edgeCount": len(component_edges),
                "isSimpleCycle": len(degree_violations) == 0
                and len(component_edges) == len(component_vertices),
                "degreeViolationVertexIds": [
                    f"logicalVertex.{vertex:06d}" for vertex in degree_violations
                ],
            }
        )
    return components


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


def _non_manifold_vertex_count(non_manifold_edges: list[tuple[int, int]]) -> int:
    vertices: set[int] = set()
    for left, right in non_manifold_edges:
        vertices.add(left)
        vertices.add(right)
    return len(vertices)


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
