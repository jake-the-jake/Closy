from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.geometry.mesh_model import MeshSet, finite_mesh, mesh_bounds
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, topology_hash

GEOMETRY_VISUAL_SHELL_REVIEW_VERSION = (
    "closy.geometry_visual_shell_review.runtime_proxy_and_shell_proof_v1"
)

_VISUAL_FIDELITY_THRESHOLD = 0.8


def build_geometry_visual_shell_review_report(
    *,
    garment_id: str,
    garment_class: str,
    runtime_binding_result_report: dict[str, Any],
    semantic_transfer_report: dict[str, Any],
    material_uv_transfer_report: dict[str, Any],
    runtime_render_mesh: MeshSet,
) -> dict[str, Any]:
    """Run deterministic preview-fidelity and shell-proof checks.

    This is a review artifact, not a rendered screenshot acceptance artifact.
    It proves that Closy reviewed the runtime-bound preview, material transfer
    and shell state, while keeping clean/canonical acceptance blocked until a
    rendered visual-fidelity comparison and real single-shell stitch/weld pass.
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
    rendered_pixel_comparison_run = False
    accepted_for_visual_fidelity = (
        rendered_pixel_comparison_run
        and geometry_proxy_score >= _VISUAL_FIDELITY_THRESHOLD
        and mesh_finite
    )

    shell_metrics = _shell_metrics(runtime_render_mesh)
    single_shell_weld_proven = (
        retopology["vertexWeldedSingleShell"] is True
        and shell_metrics["semanticPanelShellCount"] == 1
    )
    blocking_reasons = []
    if not accepted_for_visual_fidelity:
        blocking_reasons.append("visual_fidelity_review_not_accepted")
    if not rendered_pixel_comparison_run:
        blocking_reasons.append("rendered_visual_fidelity_review_missing")
    if not single_shell_weld_proven:
        blocking_reasons.append("single_shell_weld_not_proven")
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
        "visualFidelity": {
            "status": "pass" if accepted_for_visual_fidelity else "fail",
            "reviewKind": "deterministic_runtime_geometry_proxy",
            "visualFidelityReviewRun": True,
            "renderedPixelComparisonRun": rendered_pixel_comparison_run,
            "renderedReferenceAvailable": False,
            "geometryProxyScore": geometry_proxy_score,
            "acceptedForVisualFidelity": accepted_for_visual_fidelity,
            "threshold": _VISUAL_FIDELITY_THRESHOLD,
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
                "no_rendered_pixel_comparison",
                "no_human_visual_review",
                "proxy_score_cannot_accept_clean_geometry",
            ],
        },
        "shellProof": {
            "status": "pass" if single_shell_weld_proven else "fail",
            "singleShellWeldProofRun": True,
            "singleShellWeldProven": single_shell_weld_proven,
            "vertexWeldedSingleShell": retopology["vertexWeldedSingleShell"],
            "semanticPanelShellCount": shell_metrics["semanticPanelShellCount"],
            "meshCount": shell_metrics["meshCount"],
            "boundaryEdgeCount": shell_metrics["boundaryEdgeCount"],
            "seamConstraintCount": seam_constraint_count,
            "evidence": shell_metrics["meshShells"],
        },
        "aggregate": {
            "visualFidelityReviewRun": True,
            "renderedPixelComparisonRun": rendered_pixel_comparison_run,
            "visualFidelityScore": geometry_proxy_score,
            "acceptedForVisualFidelity": accepted_for_visual_fidelity,
            "singleShellWeldProofRun": True,
            "singleShellWeldProven": single_shell_weld_proven,
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
            "visualFidelityReviewRun": True,
            "deterministicPreviewProxyReviewRun": True,
            "renderedPixelComparisonRun": rendered_pixel_comparison_run,
            "singleShellWeldProofRun": True,
        },
        "readiness": {
            "status": "visual_shell_review_completed_clean_rejected",
            "acceptedForVisualFidelity": accepted_for_visual_fidelity,
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": runtime_readiness["acceptedForRuntimeRender"],
            "singleShellWeldProven": single_shell_weld_proven,
            "nextExecutableStage": "rendered_visual_fidelity_and_single_shell_weld_execution",
            "blockingReasons": sorted(set(blocking_reasons)),
        },
        "quality": {
            "status": "reviewed_clean_rejected",
            "acceptedForVisualFidelity": accepted_for_visual_fidelity,
            "acceptedForCleanProposal": False,
            "warnings": [
                "rendered_visual_fidelity_review_missing",
                "single_shell_weld_not_proven",
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


def _shell_metrics(meshset: MeshSet) -> dict[str, Any]:
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
    return {
        "meshCount": len(meshset.meshes),
        "semanticPanelShellCount": len({mesh.panel_id for mesh in meshset.meshes}),
        "boundaryEdgeCount": boundary_edge_count,
        "meshShells": mesh_shells,
    }


def _rounded_bounds(bounds: dict[str, list[float]]) -> dict[str, list[float]]:
    return {key: [_round(value) for value in values] for key, values in bounds.items()}


def _round(value: float) -> float:
    return round(float(value), 9)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return _round(float(numerator) / float(denominator))
