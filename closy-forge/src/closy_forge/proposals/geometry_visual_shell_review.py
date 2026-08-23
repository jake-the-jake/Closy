from __future__ import annotations

from copy import deepcopy
from math import sqrt
from typing import Any

from closy_forge.geometry.mesh_model import MeshSet, finite_mesh, mesh_bounds
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, topology_hash

GEOMETRY_VISUAL_SHELL_REVIEW_VERSION = (
    "closy.geometry_visual_shell_review.truthful_representation_and_connectability_v3"
)

_VISUAL_FIDELITY_THRESHOLD = 0.8
_SILHOUETTE_IOU_THRESHOLD = 0.94
_SILHOUETTE_RASTER_SIZE = 64
_STITCH_DISTANCE_THRESHOLD_METERS = 0.15


def build_geometry_visual_shell_review_report(
    *,
    garment_id: str,
    garment_class: str,
    runtime_binding_result_report: dict[str, Any],
    semantic_transfer_report: dict[str, Any],
    material_uv_transfer_report: dict[str, Any],
    runtime_render_mesh: MeshSet,
    reference_simulation_mesh: MeshSet | None = None,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run deterministic representation and shell-connectability checks.

    This remains a CI-safe geometry artifact rather than a GPU screenshot. The
    rendered pass rasterizes deterministic orthographic silhouettes from the
    runtime render mesh and canonical settled simulation mesh, then compares
    pixels by IoU. That is representation-preservation evidence, not source
    image or provider appearance fidelity. The shell pass proves the stitch
    graph can connect panel components under bounded seam distances; it does
    not execute a vertex/index weld and must not be treated as welded topology.
    """

    semantic = semantic_transfer_report["aggregate"]
    runtime = runtime_binding_result_report["aggregate"]
    runtime_readiness = runtime_binding_result_report["readiness"]
    material = material_uv_transfer_report["aggregate"]
    retopology = runtime_binding_result_report["retopology"]
    seam_continuity = runtime_binding_result_report["seamContinuity"]
    seam_status = str(seam_continuity.get("seamContinuityStatus", "pass"))
    normal_status = str(seam_continuity.get("normalContinuityStatus", "warn"))
    tangent_status = str(seam_continuity.get("tangentContinuityStatus", "warn"))
    seam_constraint_count = int(seam_continuity.get("seamConstraintCount", 0))

    mesh_finite = finite_mesh(runtime_render_mesh)
    bounds = _rounded_bounds(mesh_bounds(runtime_render_mesh))
    semantic_panel_coverage = _ratio(
        semantic["transferredPanelCount"],
        semantic["expectedPanelCount"],
    )
    boundary_completeness = float(semantic["classificationCompleteness"])
    material_score = (
        1.0
        if material["acceptedForMaterialPreview"]
        and material["missingUvCount"] == 0
        and material["missingMaterialCount"] == 0
        else 0.0
    )
    runtime_binding_accepted = bool(
        runtime.get("runtimeBindingAccepted", runtime_readiness["acceptedForRuntimeRender"])
    )
    binding_score = 1.0 if runtime_binding_accepted else 0.0
    seam_distance_score = 1.0 if seam_status == "pass" else 0.65
    normal_score = 1.0 if normal_status == "pass" else 0.75
    tangent_score = 1.0 if tangent_status == "pass" else 0.75
    geometry_proxy_score = _round(
        (binding_score * 0.22)
        + (semantic_panel_coverage * 0.18)
        + (boundary_completeness * 0.16)
        + (material_score * 0.20)
        + (seam_distance_score * 0.12)
        + (normal_score * 0.06)
        + (tangent_score * 0.06)
    )
    rendered_pixel_comparison = _rendered_silhouette_comparison(
        runtime_render_mesh,
        reference_simulation_mesh,
    )
    rendered_pixel_comparison_run = rendered_pixel_comparison["renderedPixelComparisonRun"]
    rendered_silhouette_score = float(rendered_pixel_comparison["meanIou"])
    rendered_silhouette_minimum_iou = float(rendered_pixel_comparison["minimumIou"])
    representation_silhouette_score = _round(
        (geometry_proxy_score * 0.45) + (rendered_silhouette_score * 0.55)
    )
    representation_silhouette_accepted = (
        rendered_pixel_comparison_run
        and representation_silhouette_score >= _VISUAL_FIDELITY_THRESHOLD
        and rendered_silhouette_minimum_iou >= _SILHOUETTE_IOU_THRESHOLD
        and mesh_finite
    )

    shell_metrics = _shell_metrics(
        runtime_render_mesh,
        stitch_source_mesh=reference_simulation_mesh,
        constraints=constraints,
    )
    stitch_graph_connectable = (
        shell_metrics["stitchGraphConnectivityCheckRun"] is True
        and shell_metrics["postStitchShellCount"] == 1
        and shell_metrics["rejectedStitchPairCount"] == 0
        and shell_metrics["acceptedStitchPairCount"] > 0
    )
    mesh_stitch_or_weld_execution_run = False
    mesh_stitch_or_weld_proven = False
    source_image_visual_comparison_run = False
    source_image_visual_fidelity_accepted = False
    provider_appearance_comparison_run = False
    provider_appearance_accepted = False
    human_visual_review_run = False
    human_visual_review_result = "not_run"

    blocking_reasons = []
    if not representation_silhouette_accepted:
        blocking_reasons.append("representation_silhouette_not_accepted")
    if not rendered_pixel_comparison_run:
        blocking_reasons.append("representation_silhouette_comparison_not_run")
    if not source_image_visual_comparison_run:
        blocking_reasons.append("source_image_visual_comparison_not_run")
    if not source_image_visual_fidelity_accepted:
        blocking_reasons.append("source_image_visual_fidelity_not_accepted")
    if not provider_appearance_comparison_run:
        blocking_reasons.append("provider_appearance_comparison_not_run")
    if not provider_appearance_accepted:
        blocking_reasons.append("provider_appearance_not_accepted")
    if not human_visual_review_run:
        blocking_reasons.append("human_visual_review_not_run")
    if not stitch_graph_connectable:
        blocking_reasons.append("stitch_graph_not_connectable")
    if not mesh_stitch_or_weld_execution_run:
        blocking_reasons.append("mesh_stitch_or_weld_not_executed")
    if not mesh_stitch_or_weld_proven:
        blocking_reasons.append("mesh_stitch_or_weld_not_proven")
    blocking_reasons.append("provider_output_not_canonical_garment_truth")

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "visual_shell_review.runtime_bound_tshirt_visual_geometry_v1",
        "stageVersion": GEOMETRY_VISUAL_SHELL_REVIEW_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceGeometryRuntimeBindingResultId": runtime_binding_result_report["reportId"],
        "sourceGeometryRuntimeBindingResultHash": runtime_binding_result_report["integrity"][
            "geometryRuntimeBindingResultHash"
        ],
        "sourceGeometrySemanticTransferId": semantic_transfer_report["reportId"],
        "sourceGeometrySemanticTransferHash": semantic_transfer_report["integrity"][
            "geometrySemanticTransferHash"
        ],
        "sourceGeometryMaterialUvTransferId": material_uv_transfer_report["reportId"],
        "sourceGeometryMaterialUvTransferHash": material_uv_transfer_report["integrity"][
            "geometryMaterialUvTransferHash"
        ],
        "sourceRuntimeRenderMeshTopologyHash": topology_hash(runtime_render_mesh),
        "sourceRuntimeRenderMeshContentHash": geometry_content_hash(runtime_render_mesh),
        "candidate": {
            "runtimeRenderAssetPath": runtime_binding_result_report["outputRenderAsset"]["path"],
            "runtimeRenderAssetHash": runtime_binding_result_report["outputRenderAsset"][
                "sourceAssetHash"
            ],
            "runtimePreviewUseAllowed": runtime_binding_result_report["outputRenderAsset"][
                "runtimePreviewUseAllowed"
            ],
            "acceptedForRuntimeRender": runtime_readiness["acceptedForRuntimeRender"],
            "canonicalUseAllowed": False,
            "reviewedRepresentation": "runtime_bound_panel_subdivision_preview",
            "bounds": bounds,
        },
        "representationEvidence": {
            "status": "pass" if representation_silhouette_accepted else "fail",
            "reviewKind": "deterministic_runtime_representation_consistency",
            "representationSilhouetteComparisonRun": rendered_pixel_comparison_run,
            "representationSilhouetteAccepted": representation_silhouette_accepted,
            "representationSilhouetteScore": representation_silhouette_score,
            "representationSilhouetteMinimumIou": rendered_silhouette_minimum_iou,
            "renderedReferenceAvailable": rendered_pixel_comparison["renderedReferenceAvailable"],
            "renderedPixelComparison": rendered_pixel_comparison,
            "threshold": _VISUAL_FIDELITY_THRESHOLD,
            "minimumViewIouThreshold": _SILHOUETTE_IOU_THRESHOLD,
            "limitations": [
                "compares_runtime_preview_to_canonical_settled_simulation_mesh",
                "not_source_photo_visual_fidelity",
                "not_independent_provider_appearance_fidelity",
                "not_texture_logo_or_material_detail_fidelity",
            ],
        },
        "appearanceEvidence": {
            "status": "not_run",
            "sourceImageVisualComparisonRun": source_image_visual_comparison_run,
            "sourceImageVisualFidelityAccepted": source_image_visual_fidelity_accepted,
            "providerAppearanceComparisonRun": provider_appearance_comparison_run,
            "providerAppearanceAccepted": provider_appearance_accepted,
            "humanVisualReviewRun": human_visual_review_run,
            "humanVisualReviewResult": human_visual_review_result,
            "independentReferenceAvailable": False,
            "comparisonTier": "not_run",
            "limitations": [
                "no_source_photo_pixel_comparison",
                "no_independent_provider_target_comparison",
                "no_human_visual_review",
            ],
        },
        "visualFidelity": {
            "status": "not_run",
            "reviewKind": "independent_source_or_provider_visual_fidelity",
            "visualFidelityReviewRun": False,
            "renderedPixelComparisonRun": rendered_pixel_comparison_run,
            "renderedReferenceAvailable": rendered_pixel_comparison["renderedReferenceAvailable"],
            "geometryProxyScore": geometry_proxy_score,
            "renderedSilhouetteScore": rendered_silhouette_score,
            "renderedSilhouetteMinimumIou": rendered_silhouette_minimum_iou,
            "renderedPixelComparison": rendered_pixel_comparison,
            "visualFidelityScore": 0.0,
            "acceptedForVisualFidelity": False,
            "representationSilhouetteAccepted": representation_silhouette_accepted,
            "sourceImageVisualComparisonRun": source_image_visual_comparison_run,
            "sourceImageVisualFidelityAccepted": source_image_visual_fidelity_accepted,
            "providerAppearanceComparisonRun": provider_appearance_comparison_run,
            "providerAppearanceAccepted": provider_appearance_accepted,
            "humanVisualReviewRun": human_visual_review_run,
            "humanVisualReviewResult": human_visual_review_result,
            "threshold": _VISUAL_FIDELITY_THRESHOLD,
            "minimumViewIouThreshold": _SILHOUETTE_IOU_THRESHOLD,
            "factors": {
                "runtimeBindingAccepted": runtime_binding_accepted,
                "semanticPanelCoverage": semantic_panel_coverage,
                "boundaryClassificationCompleteness": boundary_completeness,
                "materialTransferAccepted": material["acceptedForMaterialPreview"],
                "meshFinite": mesh_finite,
                "normalContinuityStatus": normal_status,
                "tangentContinuityStatus": tangent_status,
            },
            "limitations": [
                "no_human_visual_review",
                "no_source_photo_pixel_comparison",
                "no_independent_provider_appearance_comparison",
                "silhouette_comparison_only_not_texture_fidelity",
            ],
        },
        "shellProof": {
            "status": "not_run",
            "stitchGraphConnectivityCheckRun": shell_metrics["stitchGraphConnectivityCheckRun"],
            "stitchGraphConnectable": stitch_graph_connectable,
            "meshStitchOrWeldExecutionRun": mesh_stitch_or_weld_execution_run,
            "meshStitchOrWeldProven": mesh_stitch_or_weld_proven,
            "meshStitchOrWeldOutputAssetPath": None,
            "meshStitchOrWeldOutputTopologyHash": None,
            "meshStitchOrWeldOutputContentHash": None,
            "meshStitchOrWeldAudit": None,
            "singleShellWeldProofRun": False,
            "singleShellWeldProven": False,
            "vertexWeldedSingleShell": retopology["vertexWeldedSingleShell"],
            "singleShellWeldExecutionRun": False,
            "proofMesh": shell_metrics["proofMesh"],
            "semanticPanelShellCount": shell_metrics["semanticPanelShellCount"],
            "initialShellCount": shell_metrics["initialShellCount"],
            "postStitchShellCount": shell_metrics["postStitchShellCount"],
            "acceptedStitchPairCount": shell_metrics["acceptedStitchPairCount"],
            "rejectedStitchPairCount": shell_metrics["rejectedStitchPairCount"],
            "stitchDistanceThresholdMeters": _STITCH_DISTANCE_THRESHOLD_METERS,
            "meshCount": shell_metrics["meshCount"],
            "boundaryEdgeCount": shell_metrics["boundaryEdgeCount"],
            "seamConstraintCount": seam_constraint_count,
            "evidence": shell_metrics["meshShells"],
        },
        "aggregate": {
            "visualFidelityReviewRun": False,
            "renderedPixelComparisonRun": rendered_pixel_comparison_run,
            "representationSilhouetteComparisonRun": rendered_pixel_comparison_run,
            "representationSilhouetteAccepted": representation_silhouette_accepted,
            "representationSilhouetteScore": representation_silhouette_score,
            "visualFidelityScore": 0.0,
            "acceptedForVisualFidelity": False,
            "sourceImageVisualComparisonRun": source_image_visual_comparison_run,
            "sourceImageVisualFidelityAccepted": source_image_visual_fidelity_accepted,
            "providerAppearanceComparisonRun": provider_appearance_comparison_run,
            "providerAppearanceAccepted": provider_appearance_accepted,
            "humanVisualReviewRun": human_visual_review_run,
            "humanVisualReviewResult": human_visual_review_result,
            "stitchGraphConnectivityCheckRun": shell_metrics["stitchGraphConnectivityCheckRun"],
            "stitchGraphConnectable": stitch_graph_connectable,
            "singleShellWeldProofRun": False,
            "singleShellWeldProven": False,
            "meshStitchOrWeldExecutionRun": mesh_stitch_or_weld_execution_run,
            "meshStitchOrWeldProven": mesh_stitch_or_weld_proven,
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForRuntimeRender": runtime_readiness["acceptedForRuntimeRender"],
            "meshCount": len(runtime_render_mesh.meshes),
            "vertexCount": runtime_render_mesh.vertex_count,
            "triangleCount": runtime_render_mesh.triangle_count,
            "boundaryEdgeCount": shell_metrics["boundaryEdgeCount"],
        },
        "execution": {
            "geometryVisualShellReviewGenerated": True,
            "runtimeBindingEvidenceReviewed": True,
            "semanticTransferEvidenceReviewed": True,
            "materialUvTransferEvidenceReviewed": True,
            "visualFidelityReviewRun": False,
            "deterministicPreviewProxyReviewRun": True,
            "renderedPixelComparisonRun": rendered_pixel_comparison_run,
            "representationSilhouetteComparisonRun": rendered_pixel_comparison_run,
            "sourceImageVisualComparisonRun": source_image_visual_comparison_run,
            "providerAppearanceComparisonRun": provider_appearance_comparison_run,
            "humanVisualReviewRun": human_visual_review_run,
            "stitchGraphConnectivityCheckRun": shell_metrics["stitchGraphConnectivityCheckRun"],
            "singleShellWeldProofRun": False,
            "singleShellWeldExecutionRun": False,
            "meshStitchOrWeldExecutionRun": mesh_stitch_or_weld_execution_run,
        },
        "readiness": {
            "status": "visual_shell_review_completed_clean_rejected",
            "acceptedForVisualFidelity": False,
            "representationSilhouetteAccepted": representation_silhouette_accepted,
            "sourceImageVisualFidelityAccepted": source_image_visual_fidelity_accepted,
            "providerAppearanceAccepted": provider_appearance_accepted,
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": runtime_readiness["acceptedForRuntimeRender"],
            "stitchGraphConnectable": stitch_graph_connectable,
            "singleShellWeldProven": False,
            "meshStitchOrWeldProven": mesh_stitch_or_weld_proven,
            "nextExecutableStage": "canonical_acceptance_quality_gate"
            if (
                source_image_visual_fidelity_accepted
                and provider_appearance_accepted
                and mesh_stitch_or_weld_proven
            )
            else "source_or_provider_visual_fidelity_and_mesh_stitch_weld_execution",
            "blockingReasons": sorted(set(blocking_reasons)),
        },
        "quality": {
            "status": "reviewed_clean_rejected",
            "acceptedForVisualFidelity": False,
            "representationSilhouetteAccepted": representation_silhouette_accepted,
            "stitchGraphConnectable": stitch_graph_connectable,
            "acceptedForCleanProposal": False,
            "warnings": [
                None
                if rendered_pixel_comparison_run
                else "representation_silhouette_comparison_not_run",
                None
                if representation_silhouette_accepted
                else "representation_silhouette_not_accepted",
                "source_image_visual_comparison_not_run",
                "provider_appearance_comparison_not_run",
                "human_visual_review_not_run",
                None if stitch_graph_connectable else "stitch_graph_not_connectable",
                "mesh_stitch_or_weld_not_executed",
                "mesh_stitch_or_weld_not_proven",
                "normal_continuity_warn" if normal_status == "warn" else None,
                "tangent_continuity_warn" if tangent_status == "warn" else None,
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"geometryVisualShellReviewHash": ""},
    }
    report["quality"]["warnings"] = [
        str(warning) for warning in report["quality"]["warnings"] if warning is not None
    ]
    report["integrity"]["geometryVisualShellReviewHash"] = hash_geometry_visual_shell_review(report)
    return report


def hash_geometry_visual_shell_review(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["geometryVisualShellReviewHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _shell_metrics(
    meshset: MeshSet,
    *,
    stitch_source_mesh: MeshSet | None,
    constraints: dict[str, Any] | None,
) -> dict[str, Any]:
    mesh_shells: list[dict[str, Any]] = []
    boundary_edge_count = 0
    for mesh in sorted(meshset.meshes, key=lambda item: (item.panel_id, item.name)):
        edge_counts: dict[tuple[int, int], int] = {}
        for tri in mesh.triangles:
            for a, b in [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]:
                edge = (a, b) if a <= b else (b, a)
                edge_counts[edge] = edge_counts.get(edge, 0) + 1
        mesh_boundary_edges = sum(1 for count in edge_counts.values() if count == 1)
        boundary_edge_count += mesh_boundary_edges
        mesh_shells.append(
            {
                "meshName": mesh.name,
                "panelId": mesh.panel_id,
                "vertexCount": len(mesh.vertices),
                "triangleCount": len(mesh.triangles),
                "boundaryEdgeCount": mesh_boundary_edges,
                "materialId": mesh.material_id,
            }
        )
    proof_mesh = stitch_source_mesh if stitch_source_mesh is not None else meshset
    initial_shell_count, post_stitch_shell_count, stitch_metrics = _stitch_graph_shell_counts(
        proof_mesh,
        constraints,
    )
    return {
        "meshCount": len(meshset.meshes),
        "proofMesh": "settled_simulation_stitch_graph"
        if stitch_source_mesh is not None
        else "runtime_render_mesh_topology_only",
        "semanticPanelShellCount": post_stitch_shell_count,
        "initialShellCount": initial_shell_count,
        "postStitchShellCount": post_stitch_shell_count,
        "stitchGraphConnectivityCheckRun": constraints is not None
        and stitch_source_mesh is not None,
        "acceptedStitchPairCount": stitch_metrics["acceptedStitchPairCount"],
        "rejectedStitchPairCount": stitch_metrics["rejectedStitchPairCount"],
        "maxAcceptedStitchDistanceMeters": stitch_metrics["maxAcceptedStitchDistanceMeters"],
        "maxRejectedStitchDistanceMeters": stitch_metrics["maxRejectedStitchDistanceMeters"],
        "boundaryEdgeCount": boundary_edge_count,
        "meshShells": mesh_shells,
    }


def _stitch_graph_shell_counts(
    meshset: MeshSet,
    constraints: dict[str, Any] | None,
) -> tuple[int, int, dict[str, Any]]:
    offsets: list[int] = []
    total_vertices = 0
    for mesh in meshset.meshes:
        offsets.append(total_vertices)
        total_vertices += len(mesh.vertices)
    union = _UnionFind(total_vertices)
    for mesh_index, mesh in enumerate(meshset.meshes):
        offset = offsets[mesh_index]
        for tri in mesh.triangles:
            union.union(offset + tri[0], offset + tri[1])
            union.union(offset + tri[1], offset + tri[2])
            union.union(offset + tri[2], offset + tri[0])
    initial_shell_count = union.component_count()
    accepted_distances: list[float] = []
    rejected_distances: list[float] = []
    if constraints is not None:
        for constraint in constraints.get("constraints", []):
            if not isinstance(constraint, dict):
                continue
            span_a = constraint.get("spanA")
            span_b = constraint.get("spanB")
            if not isinstance(span_a, dict) or not isinstance(span_b, dict):
                continue
            a_key = (int(span_a["meshIndex"]), int(span_a["vertexIndex"]))
            b_key = (int(span_b["meshIndex"]), int(span_b["vertexIndex"]))
            distance = _distance3(_vertex_at(meshset, a_key), _vertex_at(meshset, b_key))
            if distance <= _STITCH_DISTANCE_THRESHOLD_METERS:
                union.union(offsets[a_key[0]] + a_key[1], offsets[b_key[0]] + b_key[1])
                accepted_distances.append(distance)
            else:
                rejected_distances.append(distance)
    metrics = {
        "acceptedStitchPairCount": len(accepted_distances),
        "rejectedStitchPairCount": len(rejected_distances),
        "maxAcceptedStitchDistanceMeters": _round(max(accepted_distances, default=0.0)),
        "maxRejectedStitchDistanceMeters": _round(max(rejected_distances, default=0.0)),
    }
    return initial_shell_count, union.component_count(), metrics


def _rendered_silhouette_comparison(
    candidate: MeshSet,
    reference: MeshSet | None,
) -> dict[str, Any]:
    if reference is None:
        return {
            "renderedPixelComparisonRun": False,
            "renderedReferenceAvailable": False,
            "rasterSize": _SILHOUETTE_RASTER_SIZE,
            "meanIou": 0.0,
            "minimumIou": 0.0,
            "views": [],
        }
    views: list[dict[str, Any]] = []
    for view_name, axis_a, axis_b in [
        ("front_xy", 0, 1),
        ("side_zy", 2, 1),
        ("top_xz", 0, 2),
    ]:
        candidate_mask = _silhouette_mask(candidate, reference, axis_a, axis_b)
        reference_mask = _silhouette_mask(reference, candidate, axis_a, axis_b)
        intersection = len(candidate_mask & reference_mask)
        union_count = len(candidate_mask | reference_mask)
        iou = 1.0 if union_count == 0 else intersection / union_count
        views.append(
            {
                "view": view_name,
                "candidatePixelCount": len(candidate_mask),
                "referencePixelCount": len(reference_mask),
                "intersectionPixelCount": intersection,
                "unionPixelCount": union_count,
                "iou": _round(iou),
            }
        )
    ious = [float(view["iou"]) for view in views]
    return {
        "renderedPixelComparisonRun": True,
        "renderedReferenceAvailable": True,
        "rasterSize": _SILHOUETTE_RASTER_SIZE,
        "meanIou": _round(sum(ious) / len(ious)),
        "minimumIou": _round(min(ious)),
        "views": views,
    }


def _silhouette_mask(primary: MeshSet, secondary: MeshSet, axis_a: int, axis_b: int) -> set[int]:
    bounds = _combined_axis_bounds(primary, secondary, axis_a, axis_b)
    mask: set[int] = set()
    for mesh in primary.meshes:
        for tri in mesh.triangles:
            points = [
                _project_vertex(mesh.vertices[index], bounds, axis_a, axis_b) for index in tri
            ]
            mask.update(_rasterize_triangle(points))
    return mask


def _combined_axis_bounds(
    primary: MeshSet,
    secondary: MeshSet,
    axis_a: int,
    axis_b: int,
) -> dict[str, float]:
    values_a = [
        vertex[axis_a]
        for meshset in [primary, secondary]
        for mesh in meshset.meshes
        for vertex in mesh.vertices
    ]
    values_b = [
        vertex[axis_b]
        for meshset in [primary, secondary]
        for mesh in meshset.meshes
        for vertex in mesh.vertices
    ]
    min_a = min(values_a, default=-0.5)
    max_a = max(values_a, default=0.5)
    min_b = min(values_b, default=-0.5)
    max_b = max(values_b, default=0.5)
    span_a = max(max_a - min_a, 1e-9)
    span_b = max(max_b - min_b, 1e-9)
    pad_a = span_a * 0.08
    pad_b = span_b * 0.08
    return {
        "minA": min_a - pad_a,
        "maxA": max_a + pad_a,
        "minB": min_b - pad_b,
        "maxB": max_b + pad_b,
    }


def _project_vertex(
    vertex: tuple[float, float, float],
    bounds: dict[str, float],
    axis_a: int,
    axis_b: int,
) -> tuple[float, float]:
    span_a = bounds["maxA"] - bounds["minA"]
    span_b = bounds["maxB"] - bounds["minB"]
    x = ((vertex[axis_a] - bounds["minA"]) / span_a) * (_SILHOUETTE_RASTER_SIZE - 1)
    y = ((vertex[axis_b] - bounds["minB"]) / span_b) * (_SILHOUETTE_RASTER_SIZE - 1)
    return (x, y)


def _rasterize_triangle(points: list[tuple[float, float]]) -> set[int]:
    min_x = max(0, int(min(point[0] for point in points)))
    max_x = min(_SILHOUETTE_RASTER_SIZE - 1, int(max(point[0] for point in points)) + 1)
    min_y = max(0, int(min(point[1] for point in points)))
    max_y = min(_SILHOUETTE_RASTER_SIZE - 1, int(max(point[1] for point in points)) + 1)
    covered: set[int] = set()
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            if _point_in_triangle((x + 0.5, y + 0.5), points):
                covered.add((y * _SILHOUETTE_RASTER_SIZE) + x)
    return covered


def _point_in_triangle(point: tuple[float, float], tri: list[tuple[float, float]]) -> bool:
    px, py = point
    (ax, ay), (bx, by), (cx, cy) = tri
    denominator = ((by - cy) * (ax - cx)) + ((cx - bx) * (ay - cy))
    if abs(denominator) <= 1e-12:
        return False
    u = (((by - cy) * (px - cx)) + ((cx - bx) * (py - cy))) / denominator
    v = (((cy - ay) * (px - cx)) + ((ax - cx) * (py - cy))) / denominator
    w = 1.0 - u - v
    return u >= -1e-9 and v >= -1e-9 and w >= -1e-9


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


def _vertex_at(meshset: MeshSet, key: tuple[int, int]) -> tuple[float, float, float]:
    mesh_index, vertex_index = key
    return meshset.meshes[mesh_index].vertices[vertex_index]


def _distance3(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def _rounded_bounds(bounds: dict[str, list[float]]) -> dict[str, list[float]]:
    return {key: [_round(value) for value in values] for key, values in bounds.items()}


def _round(value: float) -> float:
    return round(float(value), 9)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return _round(float(numerator) / float(denominator))
