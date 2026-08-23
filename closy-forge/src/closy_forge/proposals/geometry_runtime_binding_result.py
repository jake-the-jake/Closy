from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from math import acos, degrees, sqrt
from pathlib import Path
from typing import Any, cast

from closy_forge.binding.binary_format import BindingFile
from closy_forge.binding.builder import build_binding
from closy_forge.geometry.mesh_model import (
    MeshSet,
    Vec3,
    add,
    mesh_bounds,
    normalize,
    sub,
    triangle_normal,
)
from closy_forge.geometry.subdivision import RenderBindingSeed, subdivide_for_render
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)

GEOMETRY_RUNTIME_BINDING_RESULT_VERSION = (
    "closy.geometry_runtime_binding_result.sim_driven_retopology.v1"
)

PROPOSAL_RUNTIME_BINDING_ALGORITHM = "closy.proposal_runtime_retopology_binding.v1"

_MAX_RECONSTRUCTION_ERROR_METERS = 1e-6
_MAX_SEAM_PAIR_DISTANCE_METERS = 0.15
_RMS_SEAM_PAIR_DISTANCE_METERS = 0.05
_WARN_NORMAL_ANGLE_DEGREES = 45.0
_WARN_TANGENT_ANGLE_DEGREES = 25.0


def build_proposal_runtime_render_mesh(
    settled_simulation_mesh: MeshSet,
) -> tuple[MeshSet, list[RenderBindingSeed]]:
    """Retopologize the proposal path onto Closy's simulation-driven render shell.

    This intentionally discards raw provider topology for runtime use. The
    provider/cleanup/repair artifacts remain evidence, while the runtime preview
    keeps stable panel IDs and an exact CLSYBND1 simulation binding.
    """

    return subdivide_for_render(settled_simulation_mesh)


def build_proposal_runtime_binding(
    *,
    settled_simulation_mesh: MeshSet,
    runtime_render_mesh: MeshSet,
    render_binding_seeds: list[RenderBindingSeed],
    target_render_path: str,
) -> tuple[BindingFile, dict[str, object]]:
    binding, manifest = build_binding(
        settled_simulation_mesh,
        runtime_render_mesh,
        render_binding_seeds,
    )
    proposal_manifest = dict(manifest)
    proposal_manifest["targetRenderPath"] = target_render_path
    proposal_manifest["algorithm"] = PROPOSAL_RUNTIME_BINDING_ALGORITHM
    proposal_manifest["generationSettings"] = {
        "normalOffsetMode": "zero",
        "preservePanelBoundaries": True,
        "sourceTopology": "settled_reference_simulation_topology",
        "targetTopology": "proposal_runtime_render_shell",
        "retopologyMode": "canonical_panel_subdivision",
    }
    return binding, proposal_manifest


def build_geometry_runtime_binding_result_report(
    *,
    garment_id: str,
    garment_class: str,
    repair_result_report: dict[str, Any],
    semantic_transfer_report: dict[str, Any],
    binding_candidate_report: dict[str, Any],
    binding_validation_report: dict[str, Any],
    repair_asset_path: Path,
    output_render_asset_path: Path,
    output_render_package_path: str,
    output_binding_path: Path,
    output_binding_package_path: str,
    output_binding_manifest: dict[str, object],
    output_binding_manifest_package_path: str,
    output_render_mesh: MeshSet,
    settled_simulation_mesh: MeshSet,
    settled_simulation_mesh_path: str,
    constraints: dict[str, Any],
) -> dict[str, Any]:
    """Report a proposal-specific runtime binding without clean/canonical acceptance."""

    binding_record_count = _manifest_int(output_binding_manifest, "recordCount")
    max_reconstruction_error = _manifest_float(
        output_binding_manifest, "maximumReconstructionError"
    )
    rms_reconstruction_error = _manifest_float(output_binding_manifest, "rmsReconstructionError")
    seam_metrics = _seam_metrics(settled_simulation_mesh, constraints)
    checks = _checks(output_binding_manifest, seam_metrics)
    failed_or_warn_checks = [
        check for check in checks if check["status"] in {"fail", "warn", "not_run"}
    ]
    accepted_for_runtime = not any(check["status"] == "fail" for check in checks)
    executed_operations = _executed_operations(output_binding_manifest, seam_metrics)
    deferred_operations = [
        {
            "operationId": "clean_proposal_acceptance_gate",
            "required": True,
            "executed": False,
            "evidenceCount": 1,
            "reason": "clean_canonical_acceptance_requires_visual_quality_and_policy_review",
        }
    ]

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "runtime_binding_result.cleanup_preview_tshirt_visual_geometry_v1",
        "stageVersion": GEOMETRY_RUNTIME_BINDING_RESULT_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceGeometryRepairResultId": repair_result_report["reportId"],
        "sourceGeometryRepairResultHash": repair_result_report["integrity"][
            "geometryRepairResultHash"
        ],
        "sourceGeometrySemanticTransferId": semantic_transfer_report["reportId"],
        "sourceGeometrySemanticTransferHash": semantic_transfer_report["integrity"][
            "geometrySemanticTransferHash"
        ],
        "sourceGeometryBindingCandidateId": binding_candidate_report["reportId"],
        "sourceGeometryBindingCandidateHash": binding_candidate_report["integrity"][
            "geometryBindingCandidateHash"
        ],
        "sourceGeometryBindingValidationId": binding_validation_report["reportId"],
        "sourceGeometryBindingValidationHash": binding_validation_report["integrity"][
            "geometryBindingValidationHash"
        ],
        "inputRepairAsset": {
            "path": repair_result_report["outputAsset"]["path"],
            "sourceAssetHash": sha256_file(repair_asset_path),
            "byteSize": repair_asset_path.stat().st_size,
            "canonicalUseAllowed": False,
            "purpose": repair_result_report["outputAsset"]["purpose"],
        },
        "targetSettledSimulation": {
            "path": settled_simulation_mesh_path,
            "topologyHash": topology_hash(settled_simulation_mesh),
            "contentHash": geometry_content_hash(settled_simulation_mesh),
            "meshCount": len(settled_simulation_mesh.meshes),
            "vertexCount": settled_simulation_mesh.vertex_count,
            "triangleCount": settled_simulation_mesh.triangle_count,
            "bounds": mesh_bounds(settled_simulation_mesh),
            "state": "settled_reference_simulation_topology",
        },
        "outputRenderAsset": {
            "path": output_render_package_path,
            "sourceAssetHash": sha256_file(output_render_asset_path),
            "byteSize": output_render_asset_path.stat().st_size,
            "canonicalUseAllowed": False,
            "runtimePreviewUseAllowed": accepted_for_runtime,
            "purpose": "non_canonical_runtime_retopology_preview",
        },
        "outputBinding": {
            "path": output_binding_package_path,
            "sourceAssetHash": sha256_file(output_binding_path),
            "byteSize": output_binding_path.stat().st_size,
            "format": output_binding_manifest["format"],
            "recordCount": binding_record_count,
            "runtimeUseAllowed": accepted_for_runtime,
            "accepted": accepted_for_runtime,
        },
        "outputBindingManifest": {
            "path": output_binding_manifest_package_path,
            "format": output_binding_manifest["format"],
            "algorithm": output_binding_manifest["algorithm"],
            "recordCount": binding_record_count,
            "sourceSimulationPath": output_binding_manifest["sourceSimulationPath"],
            "targetRenderPath": output_binding_manifest["targetRenderPath"],
            "simulationTopologyHash": output_binding_manifest["simulationTopologyHash"],
            "renderTopologyHash": output_binding_manifest["renderTopologyHash"],
            "maximumReconstructionError": max_reconstruction_error,
            "rmsReconstructionError": rms_reconstruction_error,
        },
        "outputRenderMesh": {
            "topologyHash": topology_hash(output_render_mesh),
            "contentHash": geometry_content_hash(output_render_mesh),
            "meshCount": len(output_render_mesh.meshes),
            "vertexCount": output_render_mesh.vertex_count,
            "triangleCount": output_render_mesh.triangle_count,
            "bounds": mesh_bounds(output_render_mesh),
            "source": "settled_simulation_subdivision",
        },
        "retopology": {
            "mode": "canonical_panel_subdivision",
            "sourcePartialRepairStatus": repair_result_report["readiness"]["status"],
            "sourcePartialRepairDeferredOperationCount": repair_result_report["aggregate"][
                "deferredOperationCount"
            ],
            "providerTopologyRetainedForRuntime": False,
            "stablePanelIdsPreserved": True,
            "panelBoundaryVerticesPreserved": True,
            "semanticStitchGraphGenerated": True,
            "vertexWeldedSingleShell": False,
            "reasonNoSingleShellWeld": (
                "D0 runtime path preserves panel boundaries and seam constraints until "
                "cloth-safe single-shell stitching is proven."
            ),
        },
        "seamContinuity": seam_metrics,
        "checks": checks,
        "executedOperations": executed_operations,
        "deferredOperations": deferred_operations,
        "aggregate": {
            "executedOperationCount": len(executed_operations),
            "deferredOperationCount": len(deferred_operations),
            "runtimeBindingRecordCount": binding_record_count,
            "runtimeRenderVertexCount": output_render_mesh.vertex_count,
            "runtimeRenderTriangleCount": output_render_mesh.triangle_count,
            "runtimeBindingAccepted": accepted_for_runtime,
            "failedOrWarnCheckCount": len(failed_or_warn_checks),
            "maxReconstructionError": _round(max_reconstruction_error),
            "rmsReconstructionError": _round(rms_reconstruction_error),
            "maxSeamPairDistanceMeters": seam_metrics["maxSeamPairDistanceMeters"],
            "rmsSeamPairDistanceMeters": seam_metrics["rmsSeamPairDistanceMeters"],
            "maxNormalAngleDegrees": seam_metrics["maxNormalAngleDegrees"],
            "maxTangentAngleDegrees": seam_metrics["maxTangentAngleDegrees"],
        },
        "execution": {
            "runtimeBindingResultGenerated": True,
            "deformationReprojectionRun": True,
            "repairRun": True,
            "retopologyRun": True,
            "seamSplitRun": True,
            "componentStitchingRun": True,
            "normalContinuityValidationRun": True,
            "tangentContinuityValidationRun": True,
            "runtimeBindingWritten": True,
            "runtimeBindingAccepted": accepted_for_runtime,
            "cleanProposalRun": False,
        },
        "readiness": {
            "status": "runtime_binding_ready_clean_acceptance_pending"
            if accepted_for_runtime
            else "runtime_binding_generated_but_rejected",
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForSimulation": accepted_for_runtime,
            "acceptedForRuntimeRender": accepted_for_runtime,
            "nextExecutableStage": "clean_geometry_acceptance_gate",
            "blockingReasons": _blocking_reasons(checks),
        },
        "quality": {
            "status": "runtime_binding_pass_clean_rejected"
            if accepted_for_runtime
            else "runtime_binding_failed_rejected",
            "acceptedForCleanProposal": False,
            "acceptedForRuntimeRender": accepted_for_runtime,
            "warnings": [
                warning
                for warning in [
                    "provider_topology_replaced_by_canonical_runtime_retopology",
                    "panel_boundaries_preserved_not_single_shell_welded",
                    "normal_continuity_warn"
                    if seam_metrics["normalContinuityStatus"] == "warn"
                    else None,
                    "tangent_continuity_warn"
                    if seam_metrics["tangentContinuityStatus"] == "warn"
                    else None,
                    "clean_geometry_acceptance_not_run",
                ]
                if warning is not None
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"geometryRuntimeBindingResultHash": ""},
    }
    report["integrity"]["geometryRuntimeBindingResultHash"] = hash_geometry_runtime_binding_result(
        report
    )
    return report


def hash_geometry_runtime_binding_result(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["geometryRuntimeBindingResultHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _executed_operations(
    output_binding_manifest: dict[str, object], seam_metrics: dict[str, Any]
) -> list[dict[str, Any]]:
    binding_record_count = _manifest_int(output_binding_manifest, "recordCount")
    return [
        {
            "operationId": "deformation_offset_reprojection",
            "executed": True,
            "sourceStage": "geometry_repair_result",
            "evidenceCount": seam_metrics["seamConstraintCount"],
        },
        {
            "operationId": "seam_boundary_split",
            "executed": True,
            "output": "canonical_panel_boundaries_preserved_for_runtime_binding",
            "evidenceCount": seam_metrics["seamConstraintCount"],
        },
        {
            "operationId": "component_stitching_or_shell_unification",
            "executed": True,
            "output": "semantic_stitch_graph_from_simulation_constraints",
            "evidenceCount": seam_metrics["seamConstraintCount"],
        },
        {
            "operationId": "canonical_panel_retopology",
            "executed": True,
            "output": "simulation_driven_runtime_render_topology",
            "evidenceCount": binding_record_count,
        },
        {
            "operationId": "normal_continuity_validation",
            "executed": True,
            "status": seam_metrics["normalContinuityStatus"],
            "evidenceCount": seam_metrics["seamConstraintCount"],
        },
        {
            "operationId": "tangent_continuity_validation",
            "executed": True,
            "status": seam_metrics["tangentContinuityStatus"],
            "evidenceCount": seam_metrics["tangentPairCount"],
        },
        {
            "operationId": "runtime_binding_generation",
            "executed": True,
            "output": "proposal_sim_to_render_CLSYBND1_binding",
            "evidenceCount": binding_record_count,
        },
    ]


def _checks(
    output_binding_manifest: dict[str, object], seam_metrics: dict[str, Any]
) -> list[dict[str, Any]]:
    binding_record_count = _manifest_int(output_binding_manifest, "recordCount")
    max_reconstruction = _manifest_float(output_binding_manifest, "maximumReconstructionError")
    rms_reconstruction = _manifest_float(output_binding_manifest, "rmsReconstructionError")
    return [
        {
            "checkId": "runtime_binding_file",
            "status": "pass" if binding_record_count > 0 else "fail",
            "measured": binding_record_count,
            "threshold": 1,
        },
        {
            "checkId": "binding_reconstruction",
            "status": "pass"
            if max_reconstruction <= _MAX_RECONSTRUCTION_ERROR_METERS
            and rms_reconstruction <= _MAX_RECONSTRUCTION_ERROR_METERS
            else "fail",
            "measured": {"max": _round(max_reconstruction), "rms": _round(rms_reconstruction)},
            "threshold": _MAX_RECONSTRUCTION_ERROR_METERS,
        },
        {
            "checkId": "seam_boundary_continuity",
            "status": seam_metrics["seamContinuityStatus"],
            "measured": {
                "max": seam_metrics["maxSeamPairDistanceMeters"],
                "rms": seam_metrics["rmsSeamPairDistanceMeters"],
            },
            "threshold": {
                "max": _MAX_SEAM_PAIR_DISTANCE_METERS,
                "rms": _RMS_SEAM_PAIR_DISTANCE_METERS,
            },
        },
        {
            "checkId": "normal_continuity",
            "status": seam_metrics["normalContinuityStatus"],
            "measured": seam_metrics["maxNormalAngleDegrees"],
            "warnThreshold": _WARN_NORMAL_ANGLE_DEGREES,
        },
        {
            "checkId": "tangent_continuity",
            "status": seam_metrics["tangentContinuityStatus"],
            "measured": seam_metrics["maxTangentAngleDegrees"],
            "warnThreshold": _WARN_TANGENT_ANGLE_DEGREES,
        },
        {
            "checkId": "clean_acceptance_gate",
            "status": "not_run",
            "reason": "clean visual quality and policy acceptance intentionally remains separate",
        },
    ]


def _blocking_reasons(checks: list[dict[str, Any]]) -> list[str]:
    reasons = {
        "clean_acceptance_gate_not_run",
        "provider_output_not_canonical_garment_truth",
    }
    for check in checks:
        status = check["status"]
        if status in {"fail", "warn", "not_run"}:
            reasons.add(f"{check['checkId']}_{status}")
    return sorted(reasons)


def _seam_metrics(meshset: MeshSet, constraints: dict[str, Any]) -> dict[str, Any]:
    normal_by_vertex = _vertex_normals(meshset)
    seam_distances: list[float] = []
    normal_angles: list[float] = []
    constraints_by_seam: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for constraint in constraints.get("constraints", []):
        if not isinstance(constraint, dict):
            continue
        constraints_by_seam[str(constraint.get("seamId", ""))].append(constraint)
        a = constraint["spanA"]
        b = constraint["spanB"]
        a_key = (int(a["meshIndex"]), int(a["vertexIndex"]))
        b_key = (int(b["meshIndex"]), int(b["vertexIndex"]))
        seam_distances.append(_distance3(_vertex_at(meshset, a_key), _vertex_at(meshset, b_key)))
        normal_angles.append(_angle_degrees(normal_by_vertex[a_key], normal_by_vertex[b_key]))

    tangent_angles = _tangent_angles(meshset, constraints_by_seam)
    max_seam = _round(max(seam_distances, default=0.0))
    rms_seam = _round(_rms(seam_distances))
    max_normal = _round(max(normal_angles, default=0.0))
    max_tangent = _round(max(tangent_angles, default=0.0))
    return {
        "seamConstraintCount": len(seam_distances),
        "seamIdCount": len([seam_id for seam_id in constraints_by_seam if seam_id]),
        "tangentPairCount": len(tangent_angles),
        "maxSeamPairDistanceMeters": max_seam,
        "rmsSeamPairDistanceMeters": rms_seam,
        "maxNormalAngleDegrees": max_normal,
        "rmsNormalAngleDegrees": _round(_rms(normal_angles)),
        "maxTangentAngleDegrees": max_tangent,
        "rmsTangentAngleDegrees": _round(_rms(tangent_angles)),
        "seamContinuityStatus": "pass"
        if max_seam <= _MAX_SEAM_PAIR_DISTANCE_METERS and rms_seam <= _RMS_SEAM_PAIR_DISTANCE_METERS
        else "fail",
        "normalContinuityStatus": "pass" if max_normal <= _WARN_NORMAL_ANGLE_DEGREES else "warn",
        "tangentContinuityStatus": "pass" if max_tangent <= _WARN_TANGENT_ANGLE_DEGREES else "warn",
        "thresholds": {
            "maxSeamPairDistanceMeters": _MAX_SEAM_PAIR_DISTANCE_METERS,
            "rmsSeamPairDistanceMeters": _RMS_SEAM_PAIR_DISTANCE_METERS,
            "warnNormalAngleDegrees": _WARN_NORMAL_ANGLE_DEGREES,
            "warnTangentAngleDegrees": _WARN_TANGENT_ANGLE_DEGREES,
        },
    }


def _vertex_normals(meshset: MeshSet) -> dict[tuple[int, int], Vec3]:
    normals: dict[tuple[int, int], Vec3] = {}
    for mesh_index, mesh in enumerate(meshset.meshes):
        accumulated: list[Vec3] = [(0.0, 0.0, 0.0) for _ in mesh.vertices]
        for tri in mesh.triangles:
            normal = triangle_normal(mesh.vertices, tri)
            for vertex_index in tri:
                accumulated[vertex_index] = add(accumulated[vertex_index], normal)
        for vertex_index, normal in enumerate(accumulated):
            normals[(mesh_index, vertex_index)] = normalize(normal)
    return normals


def _tangent_angles(
    meshset: MeshSet, constraints_by_seam: dict[str, list[dict[str, Any]]]
) -> list[float]:
    angles: list[float] = []
    for seam_constraints in constraints_by_seam.values():
        ordered = sorted(seam_constraints, key=lambda item: str(item["id"]))
        for previous, current in zip(ordered, ordered[1:], strict=False):
            prev_a = previous["spanA"]
            curr_a = current["spanA"]
            prev_b = previous["spanB"]
            curr_b = current["spanB"]
            a0 = _vertex_at(meshset, (int(prev_a["meshIndex"]), int(prev_a["vertexIndex"])))
            a1 = _vertex_at(meshset, (int(curr_a["meshIndex"]), int(curr_a["vertexIndex"])))
            b0 = _vertex_at(meshset, (int(prev_b["meshIndex"]), int(prev_b["vertexIndex"])))
            b1 = _vertex_at(meshset, (int(curr_b["meshIndex"]), int(curr_b["vertexIndex"])))
            tangent_a = normalize(sub(a1, a0))
            tangent_b = normalize(sub(b1, b0))
            angles.append(_angle_degrees(tangent_a, tangent_b))
    return angles


def _vertex_at(meshset: MeshSet, key: tuple[int, int]) -> Vec3:
    mesh_index, vertex_index = key
    return meshset.meshes[mesh_index].vertices[vertex_index]


def _angle_degrees(a: Vec3, b: Vec3) -> float:
    dot = max(-1.0, min(1.0, abs(sum(a[index] * b[index] for index in range(3)))))
    return degrees(acos(dot))


def _distance3(a: Vec3, b: Vec3) -> float:
    return sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def _rms(values: list[float]) -> float:
    if not values:
        return 0.0
    return sqrt(sum(value * value for value in values) / len(values))


def _round(value: float) -> float:
    return round(float(value), 9)


def _manifest_int(manifest: dict[str, object], key: str) -> int:
    return cast(int, manifest[key])


def _manifest_float(manifest: dict[str, object], key: str) -> float:
    return cast(float, manifest[key])
