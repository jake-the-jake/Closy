from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from math import sqrt
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import BindingFile
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.geometry.frame_attributes import meshset_frame_metrics
from closy_forge.geometry.glb_io import audit_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3, mesh_bounds
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)

FRAME_POSE_SUITE_VERSION = "closy.render_frame_pose_suite.persisted_tangents_and_pose_v1"

_POSE_IDS = [
    "rest_identity",
    "breath_chest_expand",
    "left_sleeve_lift",
    "torso_twist_preview",
]
_BINDING_TOLERANCE_METERS = 1e-6
_FRAME_LENGTH_TOLERANCE = 1e-6
_FRAME_ORTHOGONAL_TOLERANCE = 1e-6
_POSE_ROTATION_TRIG = {
    0.16: (0.987227283376, 0.159318206614),
    0.07: (0.997551000253, 0.069942847338),
    0.035: (0.999387562523, 0.034992854604),
}


def build_render_frame_pose_suite_report(
    *,
    garment_id: str,
    garment_class: str,
    render_asset_path: Path,
    render_asset_package_path: str,
    simulation_mesh_manifest_path: Path,
    render_mesh_manifest_path: Path,
    binding_asset_path: Path,
    binding_manifest_path: Path,
    simulation_mesh: MeshSet,
    render_mesh: MeshSet,
    binding: BindingFile,
    binding_manifest: dict[str, Any],
) -> dict[str, Any]:
    glb_audit = audit_glb(render_asset_path)
    frame_metrics = meshset_frame_metrics(render_mesh)
    frame_persistence = _frame_persistence(glb_audit, frame_metrics, render_mesh)
    pose_results = [
        _pose_result(pose_id, simulation_mesh, render_mesh, binding) for pose_id in _POSE_IDS
    ]
    pose_suite_pass = all(
        result["bindingReconstructionStatus"] == "pass"
        and result["frameStatus"] == "pass"
        and result["deformedBoundsStatus"] == "pass"
        for result in pose_results
    )
    frame_persistence_pass = (
        frame_persistence["glbTangentsPersisted"] is True
        and frame_persistence["tangentAccessorType"] == "VEC4"
        and frame_persistence["tangentVectorCount"] == frame_persistence["glbPositionVectorCount"]
        and frame_persistence["normalVectorCount"] == frame_persistence["glbPositionVectorCount"]
        and frame_persistence["frameStatus"] == "pass"
    )
    accepted_for_runtime_frame_preview = frame_persistence_pass and pose_suite_pass
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "render_frame_pose_suite.demo_tshirt_bp48_v1",
        "stageVersion": FRAME_POSE_SUITE_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceAssets": {
            "renderAsset": {
                "path": render_asset_package_path,
                "sha256": sha256_file(render_asset_path),
                "byteSize": render_asset_path.stat().st_size,
            },
            "simulationMeshManifest": {
                "path": "simulation/mesh_manifest.json",
                "sha256": sha256_file(simulation_mesh_manifest_path),
            },
            "renderMeshManifest": {
                "path": "render/mesh_manifest.json",
                "sha256": sha256_file(render_mesh_manifest_path),
            },
            "binding": {
                "path": "binding/sim_to_render.bin",
                "sha256": sha256_file(binding_asset_path),
                "byteSize": binding_asset_path.stat().st_size,
            },
            "bindingManifest": {
                "path": "binding/binding_manifest.json",
                "sha256": sha256_file(binding_manifest_path),
            },
        },
        "sourceHashes": {
            "renderTopologyHash": topology_hash(render_mesh),
            "renderContentHash": geometry_content_hash(render_mesh),
            "simulationTopologyHash": topology_hash(simulation_mesh),
            "simulationContentHash": geometry_content_hash(simulation_mesh),
            "bindingSimulationTopologyHash": binding.simulation_topology_hash,
            "bindingRenderTopologyHash": binding.render_topology_hash,
            "bindingManifestRenderTopologyHash": str(binding_manifest["renderTopologyHash"]),
            "bindingManifestSimulationTopologyHash": str(
                binding_manifest["simulationTopologyHash"]
            ),
        },
        "framePersistence": frame_persistence,
        "poseSuite": {
            "poseCount": len(pose_results),
            "poseIds": _POSE_IDS,
            "bindingToleranceMeters": _BINDING_TOLERANCE_METERS,
            "frameLengthTolerance": _FRAME_LENGTH_TOLERANCE,
            "frameOrthogonalTolerance": _FRAME_ORTHOGONAL_TOLERANCE,
            "poses": pose_results,
        },
        "aggregate": {
            "framePersistenceRun": True,
            "glbTangentsPersisted": frame_persistence["glbTangentsPersisted"],
            "normalAccessorPersisted": frame_persistence["normalAccessorPersisted"],
            "poseSuiteRun": True,
            "poseSuitePass": pose_suite_pass,
            "acceptedForRuntimeFramePreview": accepted_for_runtime_frame_preview,
            "maxPoseBindingErrorMeters": _round(
                max(float(result["maxBindingErrorMeters"]) for result in pose_results)
            ),
            "maxPoseRmsBindingErrorMeters": _round(
                max(float(result["rmsBindingErrorMeters"]) for result in pose_results)
            ),
            "maxPoseNormalLengthError": _round(
                max(
                    float(result["frameMetrics"]["maxNormalLengthError"]) for result in pose_results
                )
            ),
            "maxPoseTangentLengthError": _round(
                max(
                    float(result["frameMetrics"]["maxTangentLengthError"])
                    for result in pose_results
                )
            ),
            "maxPoseNormalTangentDot": _round(
                max(float(result["frameMetrics"]["maxNormalTangentDot"]) for result in pose_results)
            ),
        },
        "execution": {
            "framePersistenceReportGenerated": True,
            "renderGlbDecoded": True,
            "normalAccessorAuditRun": True,
            "tangentAccessorAuditRun": True,
            "poseSuiteRun": True,
            "bindingReconstructionPoseSuiteRun": True,
            "runtimePreviewFrameAcceptanceRun": True,
        },
        "readiness": {
            "status": "render_frame_pose_suite_pass_clean_rejected"
            if accepted_for_runtime_frame_preview
            else "render_frame_pose_suite_failed",
            "framePersistenceRun": True,
            "glbTangentsPersisted": frame_persistence["glbTangentsPersisted"],
            "poseSuiteRun": True,
            "poseSuitePass": pose_suite_pass,
            "acceptedForRuntimeFramePreview": accepted_for_runtime_frame_preview,
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "blockingReasons": [
                "clean_acceptance_requires_topology_source_fidelity_and_motion_suite_extension",
                "source_image_visual_comparison_not_run",
                "self_collision_not_run",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "limitations": [
            "pose_suite_uses_deterministic_affine_garment_panel_transforms",
            "not_full_avatar_skeletal_animation",
            "not_cloth_simulation_motion",
            "does_not_unlock_clean_or_canonical_acceptance",
        ],
        "integrity": {"renderFramePoseSuiteHash": ""},
    }
    report["integrity"]["renderFramePoseSuiteHash"] = hash_render_frame_pose_suite_report(report)
    return report


def hash_render_frame_pose_suite_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["renderFramePoseSuiteHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def apply_pose_to_meshset(meshset: MeshSet, pose_id: str) -> MeshSet:
    transform = _pose_transform(pose_id)
    return MeshSet(
        [
            Mesh(
                name=mesh.name,
                panel_id=mesh.panel_id,
                vertices=[transform(mesh.panel_id, vertex) for vertex in mesh.vertices],
                panel_uvs=mesh.panel_uvs,
                triangles=mesh.triangles,
                material_id=mesh.material_id,
            )
            for mesh in meshset.meshes
        ]
    )


def _frame_persistence(
    glb_audit: dict[str, Any], frame_metrics: dict[str, Any], render_mesh: MeshSet
) -> dict[str, Any]:
    semantic_counts = glb_audit.get("semanticAttributeCounts", {})
    semantic_accessor_counts = glb_audit.get("semanticAccessorCounts", {})
    semantic_accessor_types = glb_audit.get("semanticAccessorTypes", {})
    tangent_types = semantic_accessor_types.get("TANGENT", [])
    normal_types = semantic_accessor_types.get("NORMAL", [])
    frame_status = (
        "pass"
        if frame_metrics["finiteNormalCount"] == frame_metrics["normalVectorCount"]
        and frame_metrics["finiteTangentCount"] == frame_metrics["tangentVectorCount"]
        and frame_metrics["unitNormalCount"] == frame_metrics["normalVectorCount"]
        and frame_metrics["unitTangentCount"] == frame_metrics["tangentVectorCount"]
        and frame_metrics["orthogonalNormalTangentCount"] == frame_metrics["normalVectorCount"]
        else "fail"
    )
    return {
        "glbTangentsPersisted": bool(glb_audit.get("hasVec4Tangents", False)),
        "normalAccessorPersisted": semantic_counts.get("NORMAL", 0) == glb_audit["primitiveCount"],
        "tangentAccessorSemantic": "TANGENT",
        "normalAccessorSemantic": "NORMAL",
        "tangentAccessorType": tangent_types[0] if len(tangent_types) == 1 else "missing_or_mixed",
        "normalAccessorType": normal_types[0] if len(normal_types) == 1 else "missing_or_mixed",
        "primitiveCount": glb_audit["primitiveCount"],
        "renderVertexCount": render_mesh.vertex_count,
        "glbPositionVectorCount": int(semantic_accessor_counts.get("POSITION", 0)),
        "normalVectorCount": int(semantic_accessor_counts.get("NORMAL", 0)),
        "tangentVectorCount": int(semantic_accessor_counts.get("TANGENT", 0)),
        "computedFrameMetrics": frame_metrics,
        "frameStatus": frame_status,
    }


def _pose_result(
    pose_id: str,
    simulation_mesh: MeshSet,
    render_mesh: MeshSet,
    binding: BindingFile,
) -> dict[str, Any]:
    posed_sim = apply_pose_to_meshset(simulation_mesh, pose_id)
    posed_render = apply_pose_to_meshset(render_mesh, pose_id)
    reconstructed = reconstruct_vertices(posed_sim, binding)
    target = [vertex for mesh in posed_render.meshes for vertex in mesh.vertices]
    max_error, rms_error = _point_cloud_error(target, reconstructed)
    frame_metrics = meshset_frame_metrics(posed_render)
    frame_status = (
        "pass"
        if frame_metrics["finiteNormalCount"] == frame_metrics["normalVectorCount"]
        and frame_metrics["finiteTangentCount"] == frame_metrics["tangentVectorCount"]
        and frame_metrics["unitNormalCount"] == frame_metrics["normalVectorCount"]
        and frame_metrics["unitTangentCount"] == frame_metrics["tangentVectorCount"]
        and frame_metrics["orthogonalNormalTangentCount"] == frame_metrics["normalVectorCount"]
        else "fail"
    )
    bounds = mesh_bounds(posed_render)
    bounds_status = "pass" if all(value > 0.0 for value in bounds["size"]) else "fail"
    return {
        "poseId": pose_id,
        "poseKind": _pose_kind(pose_id),
        "simulationTopologyHash": topology_hash(posed_sim),
        "renderTopologyHash": topology_hash(posed_render),
        "deformedRenderContentHash": geometry_content_hash(posed_render),
        "deformedBounds": {
            key: [_round(value) for value in values] for key, values in bounds.items()
        },
        "deformedBoundsStatus": bounds_status,
        "bindingReconstructionStatus": "pass"
        if max_error <= _BINDING_TOLERANCE_METERS and rms_error <= _BINDING_TOLERANCE_METERS
        else "fail",
        "maxBindingErrorMeters": _round(max_error),
        "rmsBindingErrorMeters": _round(rms_error),
        "frameStatus": frame_status,
        "frameMetrics": frame_metrics,
    }


def _pose_transform(pose_id: str) -> Callable[[str, Vec3], Vec3]:
    def transform(panel_id: str, vertex: Vec3) -> Vec3:
        x, y, z = vertex
        if pose_id == "rest_identity":
            return vertex
        if pose_id == "breath_chest_expand":
            factor = (
                1.018 if panel_id in {"panel.front", "panel.back", "panel.neck_band"} else 1.008
            )
            return _quantize_vec3((x * factor, y, z * factor))
        if pose_id == "left_sleeve_lift" and panel_id == "panel.sleeve.left":
            return _rotate_z(vertex, pivot=(-0.42, 1.18, 0.0), radians=0.16)
        if pose_id == "torso_twist_preview":
            radians = (
                0.07 if panel_id in {"panel.front", "panel.back", "panel.neck_band"} else 0.035
            )
            return _rotate_y(vertex, pivot=(0.0, 1.02, 0.0), radians=radians)
        return vertex

    return transform


def _pose_kind(pose_id: str) -> str:
    return {
        "rest_identity": "baseline_identity",
        "breath_chest_expand": "bounded_torso_scale_preview",
        "left_sleeve_lift": "bounded_sleeve_rotation_preview",
        "torso_twist_preview": "bounded_upper_body_rotation_preview",
    }[pose_id]


def _rotate_z(vertex: Vec3, *, pivot: Vec3, radians: float) -> Vec3:
    x, y, z = vertex
    px, py, pz = pivot
    dx, dy = x - px, y - py
    c, s = _POSE_ROTATION_TRIG[radians]
    return _quantize_vec3((px + (dx * c) - (dy * s), py + (dx * s) + (dy * c), pz + (z - pz)))


def _rotate_y(vertex: Vec3, *, pivot: Vec3, radians: float) -> Vec3:
    x, y, z = vertex
    px, py, pz = pivot
    dx, dz = x - px, z - pz
    c, s = _POSE_ROTATION_TRIG[radians]
    return _quantize_vec3((px + (dx * c) + (dz * s), y, pz - (dx * s) + (dz * c)))


def _point_cloud_error(left: list[Vec3], right: list[Vec3]) -> tuple[float, float]:
    if len(left) != len(right):
        raise ValueError("pose_binding_record_count_mismatch")
    max_error = 0.0
    squared_sum = 0.0
    for a, b in zip(left, right, strict=True):
        distance = sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))
        max_error = max(max_error, distance)
        squared_sum += distance * distance
    return max_error, sqrt(squared_sum / max(1, len(left)))


def _round(value: float) -> float:
    return round(float(value), 9)


def _quantize_vec3(value: Vec3) -> Vec3:
    return (_round(value[0]), _round(value[1]), _round(value[2]))
