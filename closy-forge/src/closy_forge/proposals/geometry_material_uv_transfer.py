from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, topology_hash

GEOMETRY_MATERIAL_UV_TRANSFER_VERSION = (
    "closy.geometry_material_uv_transfer.source_projection_runtime_preview_v1"
)


def build_geometry_material_uv_transfer_report(
    *,
    garment_id: str,
    garment_class: str,
    runtime_binding_result_report: dict[str, Any],
    semantic_transfer_report: dict[str, Any],
    texture_identity_report: dict[str, Any],
    render_materials: dict[str, Any],
    runtime_render_mesh: MeshSet,
) -> dict[str, Any]:
    """Record UV/material evidence carried onto the runtime render shell.

    D0 now has privacy-safe source-view projection summaries, generated atlas
    metadata and PBR placeholders. This report proves those texture/material
    metadata paths are transferred while leaving clean single-shell acceptance
    and production visual fidelity to later gates.
    """

    material_regions = _material_regions(texture_identity_report)
    render_material_by_id = {
        str(material.get("id")): material
        for material in render_materials.get("materials", [])
        if isinstance(material, dict) and material.get("id") is not None
    }
    region_by_material_id = {
        str(region["materialId"]): region
        for region in material_regions
        if region.get("materialId") is not None
    }
    assignments = _panel_material_assignments(runtime_render_mesh, region_by_material_id)
    runtime_material_ids = sorted({str(item["materialId"]) for item in assignments})
    missing_material_ids = sorted(
        material_id
        for material_id in runtime_material_ids
        if material_id not in render_material_by_id or material_id not in region_by_material_id
    )
    uv_summary = _uv_summary(runtime_render_mesh)
    uv_transfer_accepted = uv_summary["missingUvCount"] == 0 and uv_summary["nonFiniteUvCount"] == 0
    material_transfer_accepted = len(assignments) > 0 and not missing_material_ids
    accepted_for_material_preview = uv_transfer_accepted and material_transfer_accepted
    blocking_reasons = []
    if not uv_transfer_accepted:
        blocking_reasons.append("uv_transfer_incomplete")
    if not material_transfer_accepted:
        blocking_reasons.append("material_transfer_incomplete")
    blocking_reasons.extend(
        [
            "visual_fidelity_review_not_run",
            "single_shell_weld_not_proven",
            "provider_output_not_canonical_garment_truth",
        ]
    )

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "material_uv_transfer.runtime_bound_tshirt_visual_geometry_v1",
        "stageVersion": GEOMETRY_MATERIAL_UV_TRANSFER_VERSION,
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
        "sourceTextureIdentityId": texture_identity_report["textureIdentityId"],
        "sourceTextureIdentityHash": texture_identity_report["integrity"]["textureIdentityHash"],
        "sourceRenderMaterialsHash": _hash_json(render_materials),
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
            "materialRepresentation": "source_projected_pbr_regions_with_panel_uv_metadata"
            if texture_identity_report["textureProjectionRun"]
            else "authored_fixture_pbr_regions_with_panel_uv_metadata",
            "sourceTextureProjectionAvailable": texture_identity_report["sourceTextureAvailable"],
            "sourceTextureProjectionRun": texture_identity_report["textureProjectionRun"],
            "generatedAtlasAvailable": texture_identity_report["generatedAtlasAvailable"],
            "generatedAtlasArtifactPath": texture_identity_report.get("artifactRefs", {})
            .get("generatedAtlas", {})
            .get("path"),
            "canonicalUseAllowed": False,
        },
        "uvTransfer": {
            "status": "pass" if uv_transfer_accepted else "fail",
            "coordinateSpace": "panel_uvs",
            "panelCoordinatesRetained": True,
            "meshCount": len(runtime_render_mesh.meshes),
            "vertexCount": runtime_render_mesh.vertex_count,
            "triangleCount": runtime_render_mesh.triangle_count,
            "verticesWithPanelUvs": uv_summary["verticesWithPanelUvs"],
            "missingUvCount": uv_summary["missingUvCount"],
            "nonFiniteUvCount": uv_summary["nonFiniteUvCount"],
            "uvBounds": uv_summary["uvBounds"],
            "semanticPanelCoverage": _ratio(
                semantic_transfer_report["aggregate"]["transferredPanelCount"],
                semantic_transfer_report["aggregate"]["expectedPanelCount"],
            ),
        },
        "materialTransfer": {
            "status": "pass" if material_transfer_accepted else "fail",
            "renderMaterialCount": len(render_material_by_id),
            "textureMaterialRegionCount": len(material_regions),
            "runtimeMaterialIdCount": len(runtime_material_ids),
            "runtimeMaterialIds": runtime_material_ids,
            "missingMaterialIds": missing_material_ids,
            "panelMaterialAssignmentCount": len(assignments),
            "panelMaterialAssignments": assignments,
        },
        "pbrTransfer": {
            "status": "pass" if material_transfer_accepted else "fail",
            "materialModel": texture_identity_report["pbrSafety"]["materialModel"],
            "maxTextureSizePx": texture_identity_report["pbrSafety"]["maxTextureSizePx"],
            "sourceTextureProjectionRun": texture_identity_report["textureProjectionRun"],
            "generatedAtlasTransferRun": texture_identity_report["generatedAtlasAvailable"],
            "transferredMaterials": _transferred_materials(
                runtime_material_ids,
                render_material_by_id,
                region_by_material_id,
                assignments,
            ),
            "unsupportedAdvancedShading": texture_identity_report["pbrSafety"][
                "unsupportedAdvancedShading"
            ],
        },
        "aggregate": {
            "uvTransferAccepted": uv_transfer_accepted,
            "materialTransferAccepted": material_transfer_accepted,
            "acceptedForMaterialPreview": accepted_for_material_preview,
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForRuntimeRender": runtime_binding_result_report["readiness"][
                "acceptedForRuntimeRender"
            ],
            "meshCount": len(runtime_render_mesh.meshes),
            "vertexCount": runtime_render_mesh.vertex_count,
            "triangleCount": runtime_render_mesh.triangle_count,
            "missingUvCount": uv_summary["missingUvCount"],
            "missingMaterialCount": len(missing_material_ids),
            "transferredMaterialCount": len(runtime_material_ids) - len(missing_material_ids),
        },
        "execution": {
            "materialUvTransferReportGenerated": True,
            "runtimeBindingEvidenceReviewed": True,
            "semanticTransferEvidenceReviewed": True,
            "textureIdentityEvidenceReviewed": True,
            "renderMaterialEvidenceReviewed": True,
            "uvTransferRun": True,
            "materialTransferRun": True,
            "sourceTextureProjectionRun": texture_identity_report["textureProjectionRun"],
            "generatedAtlasTransferRun": texture_identity_report["generatedAtlasAvailable"],
            "visualFidelityReviewRun": False,
            "singleShellWeldProofRun": False,
        },
        "readiness": {
            "status": "material_uv_transfer_completed_fidelity_weld_pending"
            if accepted_for_material_preview
            else "material_uv_transfer_incomplete",
            "acceptedForMaterialPreview": accepted_for_material_preview,
            "acceptedForCleanProposal": False,
            "acceptedForCanonical": False,
            "acceptedForSimulation": False,
            "acceptedForRuntimeRender": runtime_binding_result_report["readiness"][
                "acceptedForRuntimeRender"
            ],
            "nextExecutableStage": "visual_fidelity_review_and_single_shell_stitch_weld_proof",
            "blockingReasons": sorted(set(blocking_reasons)),
        },
        "quality": {
            "status": "pass_runtime_material_preview_clean_rejected"
            if accepted_for_material_preview
            else "rejected",
            "acceptedForMaterialPreview": accepted_for_material_preview,
            "acceptedForCleanProposal": False,
            "warnings": [
                "authored_pbr_materials_not_source_photo_projected",
                "d0_source_texture_projection_synthetic_fixture_only",
                "raw_source_pixels_not_packaged",
                "pbr_maps_placeholder_where_source_evidence_absent",
                "visual_fidelity_review_not_run",
                "single_shell_weld_not_proven",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"geometryMaterialUvTransferHash": ""},
    }
    report["integrity"]["geometryMaterialUvTransferHash"] = hash_geometry_material_uv_transfer(
        report
    )
    return report


def hash_geometry_material_uv_transfer(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["geometryMaterialUvTransferHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _panel_material_assignments(
    meshset: MeshSet, region_by_material_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "meshName": mesh.name,
            "panelId": mesh.panel_id,
            "materialId": mesh.material_id,
            "materialRegionId": region_by_material_id.get(mesh.material_id, {}).get("regionId"),
            "vertexCount": len(mesh.vertices),
            "triangleCount": len(mesh.triangles),
            "uvCount": len(mesh.panel_uvs),
            "transferStatus": "panel_material_metadata_transferred"
            if mesh.material_id in region_by_material_id
            and len(mesh.panel_uvs) == len(mesh.vertices)
            else "panel_material_metadata_incomplete",
        }
        for mesh in sorted(meshset.meshes, key=lambda item: (item.panel_id, item.name))
    ]


def _transferred_materials(
    runtime_material_ids: list[str],
    render_material_by_id: dict[str, dict[str, Any]],
    region_by_material_id: dict[str, dict[str, Any]],
    assignments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    panels_by_material: dict[str, list[str]] = {}
    for assignment in assignments:
        panels_by_material.setdefault(str(assignment["materialId"]), []).append(
            str(assignment["panelId"])
        )
    transferred: list[dict[str, Any]] = []
    for material_id in runtime_material_ids:
        render_material = render_material_by_id.get(material_id, {})
        region = region_by_material_id.get(material_id, {})
        transferred.append(
            {
                "materialId": material_id,
                "label": str(render_material.get("label", region.get("label", material_id))),
                "regionId": region.get("regionId"),
                "evidenceKind": region.get("evidenceKind"),
                "textureSource": region.get("textureSource"),
                "usedByPanelIds": sorted(set(panels_by_material.get(material_id, []))),
                "pbr": region.get("pbr", render_material.get("pbr", {})),
            }
        )
    return transferred


def _uv_summary(meshset: MeshSet) -> dict[str, Any]:
    vertices_with_panel_uvs = 0
    missing_uv_count = 0
    nonfinite_uv_count = 0
    u_values: list[float] = []
    v_values: list[float] = []
    for mesh in meshset.meshes:
        if len(mesh.panel_uvs) != len(mesh.vertices):
            missing_uv_count += abs(len(mesh.vertices) - len(mesh.panel_uvs))
        for uv in mesh.panel_uvs:
            if _finite_pair(uv):
                vertices_with_panel_uvs += 1
                u_values.append(float(uv[0]))
                v_values.append(float(uv[1]))
            else:
                nonfinite_uv_count += 1
    uv_bounds = {
        "min": [round(min(u_values, default=0.0), 9), round(min(v_values, default=0.0), 9)],
        "max": [round(max(u_values, default=0.0), 9), round(max(v_values, default=0.0), 9)],
    }
    uv_bounds["size"] = [
        round(uv_bounds["max"][0] - uv_bounds["min"][0], 9),
        round(uv_bounds["max"][1] - uv_bounds["min"][1], 9),
    ]
    return {
        "verticesWithPanelUvs": vertices_with_panel_uvs,
        "missingUvCount": missing_uv_count,
        "nonFiniteUvCount": nonfinite_uv_count,
        "uvBounds": uv_bounds,
    }


def _material_regions(texture_identity_report: dict[str, Any]) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for index, region in enumerate(texture_identity_report.get("observedMaterialRegions", [])):
        if isinstance(region, dict):
            regions.append(region)
        else:
            regions.append(
                {
                    "regionId": f"texture.region.{index:02d}",
                    "materialId": str(region),
                    "label": str(region),
                    "evidenceKind": "legacy_region_label",
                    "pbr": {},
                    "textureSource": "unknown",
                }
            )
    return regions


def _finite_pair(value: Any) -> bool:
    try:
        return (
            len(value) == 2
            and float(value[0]) == float(value[0])
            and float(value[1]) == float(value[1])
            and abs(float(value[0])) < 1e6
            and abs(float(value[1])) < 1e6
        )
    except Exception:
        return False


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 9)


def _hash_json(payload: dict[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
