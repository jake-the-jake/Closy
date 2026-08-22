from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

GEOMETRY_CLEANUP_PLAN_VERSION = "closy.geometry_cleanup_plan.recommendation.v1"


def build_geometry_cleanup_plan(
    *,
    garment_id: str,
    garment_class: str,
    raw_geometry_proposal: dict[str, Any],
    raw_topology_report: dict[str, Any],
) -> dict[str, Any]:
    """Convert topology diagnostics into a non-executed cleanup recommendation.

    The plan is a deterministic boundary artifact, not a repair result. It makes
    the next cleanup work explicit while preserving the rule that raw visual
    provider output cannot become canonical until actual cleanup, semantic
    transfer, simulation binding and acceptance validation have all run.
    """

    topology = raw_topology_report["topology"]
    operations = _recommended_operations(topology)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "cleanup_plan.raw_manual_tshirt_visual_geometry_v1",
        "stageVersion": GEOMETRY_CLEANUP_PLAN_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceRawProposalId": raw_geometry_proposal["proposalId"],
        "sourceRawProposalHash": raw_geometry_proposal["integrity"]["geometryProposalHash"],
        "sourceRawTopologyReportId": raw_topology_report["reportId"],
        "sourceRawTopologyReportHash": raw_topology_report["integrity"][
            "rawGeometryTopologyReportHash"
        ],
        "topologySnapshot": {
            "meshCount": topology["meshCount"],
            "componentCount": topology["componentCount"],
            "largestComponentTriangleCount": topology["largestComponentTriangleCount"],
            "boundaryEdgeCount": topology["boundaryEdgeCount"],
            "nonManifoldEdgeCount": topology["nonManifoldEdgeCount"],
            "degenerateTriangleCount": topology["degenerateTriangleCount"],
            "duplicatePositionCount": topology["duplicatePositionCount"],
            "manifoldStatus": topology["manifoldStatus"],
        },
        "recommendedOperations": operations,
        "execution": {
            "cleanupRun": False,
            "repairRun": False,
            "retopologyRun": False,
            "semanticTransferRun": False,
            "simulationBindingRun": False,
            "outputAssetPath": None,
            "outputAssetHash": None,
        },
        "readiness": {
            "status": "blocked_not_executed",
            "estimatedRepairComplexity": _repair_complexity(topology),
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": False,
            "nextExecutableStage": "mesh_cleanup_and_repair_adapter",
            "blockingReasons": [
                "cleanup_plan_not_executed",
                "semantic_panel_transfer_missing",
                "simulation_binding_missing",
                "canonical_acceptance_gate_not_run",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"geometryCleanupPlanHash": ""},
    }
    report["integrity"]["geometryCleanupPlanHash"] = hash_geometry_cleanup_plan(report)
    return report


def hash_geometry_cleanup_plan(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["geometryCleanupPlanHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _recommended_operations(topology: dict[str, Any]) -> list[dict[str, Any]]:
    duplicate_positions = int(topology["duplicatePositionCount"])
    boundary_edges = int(topology["boundaryEdgeCount"])
    non_manifold_edges = int(topology["nonManifoldEdgeCount"])
    degenerate_triangles = int(topology["degenerateTriangleCount"])
    component_count = int(topology["componentCount"])
    triangle_count = int(topology["triangleCount"])
    mesh_count = int(topology["meshCount"])
    return [
        _operation(
            "duplicate_position_weld",
            duplicate_positions > 0,
            duplicate_positions,
            "Expanded or duplicated provider vertices must be welded before repair.",
        ),
        _operation(
            "boundary_loop_classification",
            boundary_edges > 0,
            boundary_edges,
            "Open boundaries must be classified as seams, hems, cuffs or invalid holes.",
        ),
        _operation(
            "component_stitching_or_semantic_panel_transfer",
            component_count > 1 or boundary_edges > 0,
            component_count,
            "Disconnected visual components must be mapped to semantic garment panels.",
        ),
        _operation(
            "non_manifold_edge_repair",
            non_manifold_edges > 0,
            non_manifold_edges,
            "Non-manifold edges must be repaired before clean proposal acceptance.",
        ),
        _operation(
            "degenerate_triangle_removal",
            degenerate_triangles > 0,
            degenerate_triangles,
            "Degenerate triangles must be removed or retriangulated.",
        ),
        _operation(
            "semantic_panel_transfer",
            True,
            mesh_count,
            "Clean geometry must carry stable Closy panel, seam, opening and material IDs.",
        ),
        _operation(
            "simulation_binding_generation",
            True,
            triangle_count,
            "Clean visual geometry must bind to canonical simulation topology before runtime use.",
        ),
        _operation(
            "canonical_acceptance_validation",
            True,
            1,
            "The clean proposal must pass validator gates before canonical/runtime acceptance.",
        ),
    ]


def _operation(
    operation_id: str, required: bool, evidence_count: int, rationale: str
) -> dict[str, Any]:
    return {
        "operationId": operation_id,
        "required": required,
        "executed": False,
        "evidenceCount": evidence_count,
        "rationale": rationale,
    }


def _repair_complexity(topology: dict[str, Any]) -> str:
    if int(topology["nonManifoldEdgeCount"]) > 0 or int(topology["degenerateTriangleCount"]) > 0:
        return "repair_required"
    if int(topology["componentCount"]) > 1 or int(topology["boundaryEdgeCount"]) > 0:
        return "semantic_open_surface_cleanup_required"
    return "low_topology_cleanup_required"
