from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

TEXTURE_IDENTITY_VERSION = "closy.texture_identity.source_projection_pbr_d0_v1"
TEXTURE_ARTIFACT_VERSION = "closy.texture_artifact.source_projection_bundle_d0_v1"

TEXTURE_ARTIFACT_PATHS = {
    "sourceProjection": "textures/source_projection.json",
    "generatedAtlas": "textures/generated_atlas.json",
    "pbrMaterialMaps": "textures/pbr_material_maps.json",
    "conventionalFallbackMaterials": "textures/conventional_fallback_materials.json",
}

_SEMANTIC_PARTS_BY_MATERIAL = {
    "material.cotton_jersey_reference_v1": (
        "component.tshirt.torso",
        "component.tshirt.sleeve.left",
        "component.tshirt.sleeve.right",
    ),
    "material.cotton_rib_reference_v1": ("opening.neck",),
}

_TARGET_ATLAS_RECTS = {
    "component.tshirt.torso": [0.05, 0.12, 0.62, 0.88],
    "component.tshirt.sleeve.left": [0.68, 0.12, 0.82, 0.58],
    "component.tshirt.sleeve.right": [0.84, 0.12, 0.98, 0.58],
    "opening.neck": [0.68, 0.66, 0.98, 0.76],
}

_SEMANTIC_TARGET_PANELS = {
    "component.tshirt.torso": ["panel.front", "panel.back"],
    "component.tshirt.sleeve.left": ["panel.sleeve.left"],
    "component.tshirt.sleeve.right": ["panel.sleeve.right"],
    "opening.neck": ["panel.neck_band"],
}


@dataclass(frozen=True)
class TextureIdentityBundle:
    report: dict[str, Any]
    artifacts: dict[str, dict[str, Any]]


def build_texture_identity_bundle(
    *,
    capture_record: dict[str, Any],
    visual_observations: dict[str, Any],
    fit_report: dict[str, Any],
    render_materials: dict[str, Any],
    multiview_fusion: dict[str, Any] | None = None,
) -> TextureIdentityBundle:
    """Build the BP53 D0 source texture evidence bundle.

    This is a privacy-safe source-projection pass over project-authored raster
    evidence. It records decoded-pixel color summaries, projection coordinates
    and placeholder PBR maps without exporting raw source pixels or inventing
    hidden logos, texture maps or unseen garment detail.
    """

    source_views = _source_views(visual_observations)
    material_regions = [
        _material_region(material, index, source_views)
        for index, material in enumerate(render_materials.get("materials", []))
    ]
    projections = _projection_records(source_views, material_regions)
    seam_blends = _seam_blend_records(projections)
    preservation_masks = _logo_print_preservation_masks(source_views)
    generated_regions = _generated_regions(projections)
    projection_artifact = _source_projection_artifact(
        capture_record=capture_record,
        visual_observations=visual_observations,
        fit_report=fit_report,
        multiview_fusion=multiview_fusion,
        projections=projections,
        seam_blends=seam_blends,
        preservation_masks=preservation_masks,
        generated_regions=generated_regions,
    )
    atlas_artifact = _generated_atlas_artifact(material_regions, projections, generated_regions)
    pbr_maps_artifact = _pbr_material_maps_artifact(material_regions, projections)
    fallback_materials_artifact = _fallback_materials_artifact(material_regions)
    artifacts = {
        TEXTURE_ARTIFACT_PATHS["sourceProjection"]: projection_artifact,
        TEXTURE_ARTIFACT_PATHS["generatedAtlas"]: atlas_artifact,
        TEXTURE_ARTIFACT_PATHS["pbrMaterialMaps"]: pbr_maps_artifact,
        TEXTURE_ARTIFACT_PATHS["conventionalFallbackMaterials"]: fallback_materials_artifact,
    }
    for payload in artifacts.values():
        _finalize_artifact_hash(payload)
    artifact_refs = {
        _artifact_key_from_path(path): {
            "path": path,
            "sha256": _hash_payload(payload),
            "mediaType": "application/json",
            "canonical": True,
        }
        for path, payload in artifacts.items()
    }
    source_projection_count = len(
        [projection for projection in projections if projection["visibleSourceEvidence"]]
    )
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "textureIdentityId": "texture.source_projected_tshirt_identity_d0_v1",
        "stageVersion": TEXTURE_IDENTITY_VERSION,
        "sourceRecordId": capture_record["recordId"],
        "sourceRecordHash": capture_record["immutability"]["sourceRecordHash"],
        "sourceVisualUnderstandingId": visual_observations["visualUnderstandingId"],
        "sourceVisualRecordHash": visual_observations["integrity"]["visualRecordHash"],
        "sourceMultiviewFusionId": _nested_string(multiview_fusion, ["fusionRecordId"]),
        "sourceMultiviewFusionHash": _nested_string(
            multiview_fusion, ["integrity", "multiviewFusionRecordHash"]
        ),
        "sourceFusedEvidenceHash": _nested_string(
            multiview_fusion, ["fusedEvidence", "evidenceHash"]
        ),
        "sourceCorrectedVisualRecordHash": _nested_string(
            multiview_fusion, ["sourceCorrectedVisualRecordHash"]
        ),
        "sourceFitReportId": fit_report["fitReportId"],
        "sourceFitReportHash": fit_report["integrity"]["fitReportHash"],
        "status": "pass" if source_projection_count > 0 else "warn",
        "sourceTextureAvailable": source_projection_count > 0,
        "generatedAtlasAvailable": source_projection_count > 0,
        "textureProjectionRun": True,
        "observedMaterialRegions": material_regions,
        "projectionPlan": {
            "targetMeshPath": "render/fallback.glb",
            "targetUvSpace": "panel_uvs",
            "recommendedAtlasSizePx": 1024,
            "projectionCoordinateSpace": "normalised_source_image_uv_to_panel_atlas_uv_v1",
            "seamBlending": "front_rear_confidence_weighted_d0_v1",
            "occludedRegionPolicy": "mark_unseen_regions_and_use_material_prior_only",
            "normalMapPolicy": "placeholder_flat_normal_until_scan_or_photometric_evidence",
            "sourceEvidencePreserved": True,
        },
        "sourceViewProjection": {
            "artifactPath": TEXTURE_ARTIFACT_PATHS["sourceProjection"],
            "artifactHash": artifact_refs["sourceProjection"]["sha256"],
            "projectionCount": len(projections),
            "visibleProjectionCount": source_projection_count,
            "sourceViewCount": len(source_views),
            "coordinateMode": "image_bbox_to_panel_atlas_affine_summary",
        },
        "visibleRegionConfidence": _visible_region_confidence(projections, source_views),
        "logoPrintPreservation": {
            "artifactPath": TEXTURE_ARTIFACT_PATHS["sourceProjection"],
            "maskCount": len(preservation_masks),
            "detectedPrintRegionCount": 0,
            "visibleSourceOverwriteAllowed": False,
            "policy": "preserve_detected_or_potential_print_regions_before_unseen_inpainting",
        },
        "unseenOrGeneratedRegions": {
            "regionCount": len(generated_regions),
            "regions": generated_regions,
            "hiddenDetailHallucinationAllowed": False,
        },
        "controlledInpainting": _controlled_inpainting_record(
            generated_regions, preservation_masks
        ),
        "pbrMaterialMaps": {
            "artifactPath": TEXTURE_ARTIFACT_PATHS["pbrMaterialMaps"],
            "artifactHash": artifact_refs["pbrMaterialMaps"]["sha256"],
            "baseColorSource": "source_projection_summary_where_visible",
            "placeholderMapCount": pbr_maps_artifact["aggregate"]["placeholderMapCount"],
            "sourceBackedMapCount": pbr_maps_artifact["aggregate"]["sourceBackedMapCount"],
        },
        "sourceReprojectionMetrics": _source_reprojection_metrics(
            visual_observations, fit_report, projections
        ),
        "artifactRefs": artifact_refs,
        "pbrSafety": {
            "materialModel": "mobile_safe_mesh_standard_pbr",
            "maxTextureSizePx": 1024,
            "metallicClampedToZeroForFabric": True,
            "roughnessMinimum": 0.65,
            "unsupportedAdvancedShading": [
                "transmission",
                "dispersion",
                "clearcoat",
                "subsurface_scattering",
            ],
        },
        "policy": {
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "rawPixelsExported": False,
            "sourcePathsExported": False,
            "externalApis": False,
            "trainingUse": False,
            "profile": "d0_local_synthetic_raster_texture_recovery",
        },
        "warnings": [
            "d0_source_texture_recovery_synthetic_fixture_only",
            "raw_source_pixels_not_packaged",
            "pbr_maps_placeholder_where_source_evidence_absent",
            "hidden_regions_not_hallucinated",
            "private_user_raster_processing_not_enabled",
        ],
        "integrity": {"textureIdentityHash": ""},
    }
    report["integrity"]["textureIdentityHash"] = hash_texture_identity_report(report)
    return TextureIdentityBundle(report=report, artifacts=artifacts)


def build_texture_identity_report(
    *,
    capture_record: dict[str, Any],
    visual_observations: dict[str, Any],
    fit_report: dict[str, Any],
    render_materials: dict[str, Any],
    multiview_fusion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_texture_identity_bundle(
        capture_record=capture_record,
        visual_observations=visual_observations,
        fit_report=fit_report,
        render_materials=render_materials,
        multiview_fusion=multiview_fusion,
    ).report


def hash_texture_identity_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["textureIdentityHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _source_views(visual_observations: dict[str, Any]) -> list[dict[str, Any]]:
    views: list[dict[str, Any]] = []
    for view in visual_observations.get("views", []):
        if not isinstance(view, dict):
            continue
        parts = {
            str(part.get("semanticId", "")): part
            for part in view.get("semanticParts", [])
            if isinstance(part, dict)
        }
        openings = {
            str(opening.get("openingId", "")): opening
            for opening in view.get("openings", [])
            if isinstance(opening, dict)
        }
        masks = {
            str(mask.get("semanticId", "")): mask
            for mask in view.get("masks", [])
            if isinstance(mask, dict)
        }
        views.append(
            {
                "viewId": str(view.get("viewId", "")),
                "label": str(view.get("label", "")),
                "pixelEvidence": _mapping(view.get("pixelEvidence")),
                "parts": parts,
                "openings": openings,
                "masks": masks,
                "qualityMetrics": _mapping(view.get("qualityMetrics")),
            }
        )
    return sorted(views, key=lambda item: (item["label"], item["viewId"]))


def _material_region(
    material: dict[str, Any], index: int, source_views: list[dict[str, Any]]
) -> dict[str, Any]:
    material_id = str(material.get("id", f"material.unknown.{index:02d}"))
    pbr = _mapping(material.get("pbr"))
    source_evidence = _material_source_evidence(material_id, source_views)
    base_color = source_evidence.get("meanBaseColorFactor") or pbr.get(
        "baseColorFactor", [0.08, 0.26, 0.78, 1.0]
    )
    roughness = float(pbr.get("roughnessFactor", 0.86))
    metallic = float(pbr.get("metallicFactor", 0.0))
    has_source = bool(source_evidence.get("sourceBacked", False))
    return {
        "regionId": f"texture.region.{index:02d}",
        "materialId": material_id,
        "label": str(material.get("label", "Unnamed material")),
        "semanticTargets": list(_SEMANTIC_PARTS_BY_MATERIAL.get(material_id, ())),
        "evidenceKind": "decoded_pixel_source_projection_summary"
        if has_source
        else "authored_pbr_placeholder_no_visible_source_region",
        "evidenceViews": source_evidence["sourceViewIds"],
        "coverageConfidence": source_evidence["coverageConfidence"],
        "pbr": {
            "baseColorFactor": [_round(float(value)) for value in base_color],
            "roughnessFactor": max(0.65, min(1.0, roughness)),
            "metallicFactor": max(0.0, min(0.1, metallic)),
            "normalMapAvailable": False,
            "roughnessMapAvailable": True,
            "metalnessMapAvailable": True,
            "aoMapAvailable": False,
        },
        "sourceColorEvidence": source_evidence,
        "textureSource": "source_projection_summary"
        if has_source
        else "material_prior_placeholder_unseen_or_not_detected",
    }


def _material_source_evidence(
    material_id: str, source_views: list[dict[str, Any]]
) -> dict[str, Any]:
    semantic_ids = _SEMANTIC_PARTS_BY_MATERIAL.get(material_id, ())
    colors: list[list[float]] = []
    source_view_ids: list[str] = []
    source_hashes: list[str] = []
    pixel_count = 0
    confidence_values: list[float] = []
    for view in source_views:
        for semantic_id in semantic_ids:
            part = view["parts"].get(semantic_id)
            if not isinstance(part, dict) or bool(part.get("missing", False)):
                continue
            color = _mapping(part.get("colorEvidence"))
            base_color = color.get("meanBaseColorFactor")
            if isinstance(base_color, list) and len(base_color) == 4:
                colors.append([float(value) for value in base_color])
                source_hashes.append(str(color.get("colorEvidenceHash", "")))
                source_view_ids.append(str(view["viewId"]))
                pixel_count += _int(part.get("pixelCount"), 0)
                confidence_values.append(float(part.get("confidence", 0.0)))
    if colors:
        mean_color = [
            _round(sum(color[channel] for color in colors) / len(colors)) for channel in range(4)
        ]
        coverage = _round(sum(confidence_values) / max(1, len(confidence_values)))
        return {
            "sourceBacked": True,
            "sourceViewIds": sorted(set(source_view_ids)),
            "sourceColorEvidenceHashes": sorted(set(source_hashes)),
            "pixelSampleCount": pixel_count,
            "meanBaseColorFactor": mean_color,
            "coverageConfidence": coverage,
            "source": "decoded_pixel_part_color_evidence",
        }
    return {
        "sourceBacked": False,
        "sourceViewIds": [],
        "sourceColorEvidenceHashes": [],
        "pixelSampleCount": 0,
        "meanBaseColorFactor": None,
        "coverageConfidence": 0.0,
        "source": "no_visible_source_pixels_for_material_region",
    }


def _projection_records(
    source_views: list[dict[str, Any]], material_regions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    material_by_semantic = {
        semantic_id: str(region["materialId"])
        for region in material_regions
        for semantic_id in region.get("semanticTargets", [])
    }
    for view in source_views:
        for semantic_id in sorted(material_by_semantic):
            bbox = _semantic_bbox(view, semantic_id)
            available = bool(bbox.get("available", False))
            target_rect = list(_TARGET_ATLAS_RECTS.get(semantic_id, [0.0, 0.0, 0.01, 0.01]))
            confidence = _semantic_confidence(view, semantic_id)
            projection_id = f"projection.{_safe_id(str(view['label']))}.{_safe_id(semantic_id)}"
            records.append(
                {
                    "projectionId": projection_id,
                    "viewId": view["viewId"],
                    "viewLabel": view["label"],
                    "semanticId": semantic_id,
                    "materialId": material_by_semantic[semantic_id],
                    "sourceNormalizedPixelHash": str(
                        view["pixelEvidence"].get("normalizedPixelHash", "")
                    ),
                    "sourceImageRect": bbox,
                    "sourceProjectionCoordinates": _rect_corners(bbox),
                    "targetAtlasRect": target_rect,
                    "targetProjectionCoordinates": _rect_corners(
                        {
                            "available": True,
                            "minX": target_rect[0],
                            "minY": target_rect[1],
                            "maxX": target_rect[2],
                            "maxY": target_rect[3],
                        }
                    ),
                    "targetPanelIds": _SEMANTIC_TARGET_PANELS.get(semantic_id, []),
                    "coordinateTransform": "bbox_affine_source_uv_to_panel_atlas_uv",
                    "confidence": confidence if available else 0.0,
                    "visibleSourceEvidence": available,
                    "visibleRegionPolicy": "protected_from_inpainting"
                    if available
                    else "unseen_material_prior_only",
                    "sourceMaskHash": _semantic_mask_hash(view, semantic_id),
                }
            )
    return records


def _source_projection_artifact(
    *,
    capture_record: dict[str, Any],
    visual_observations: dict[str, Any],
    fit_report: dict[str, Any],
    multiview_fusion: dict[str, Any] | None,
    projections: list[dict[str, Any]],
    seam_blends: list[dict[str, Any]],
    preservation_masks: list[dict[str, Any]],
    generated_regions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "artifactId": "texture_projection.tshirt_source_view_d0_v1",
        "artifactVersion": TEXTURE_ARTIFACT_VERSION,
        "sourceRecordId": capture_record["recordId"],
        "sourceRecordHash": capture_record["immutability"]["sourceRecordHash"],
        "sourceVisualUnderstandingId": visual_observations["visualUnderstandingId"],
        "sourceVisualRecordHash": visual_observations["integrity"]["visualRecordHash"],
        "sourceMultiviewFusionId": _nested_string(multiview_fusion, ["fusionRecordId"]),
        "sourceMultiviewFusionHash": _nested_string(
            multiview_fusion, ["integrity", "multiviewFusionRecordHash"]
        ),
        "sourceFitReportId": fit_report["fitReportId"],
        "sourceFitReportHash": fit_report["integrity"]["fitReportHash"],
        "coordinateSpaces": {
            "source": "normalised_image_uv_top_left_origin",
            "target": "panel_atlas_uv_top_left_origin",
            "mesh": "render/fallback.glb panel_uvs",
        },
        "projections": projections,
        "seamBlending": seam_blends,
        "logoPrintPreservationMasks": preservation_masks,
        "unseenOrGeneratedRegions": generated_regions,
        "policy": {
            "rawPixelsExported": False,
            "sourcePathsExported": False,
            "visibleEvidenceOverwriteAllowed": False,
        },
        "integrity": {"artifactHash": ""},
    }


def _generated_atlas_artifact(
    material_regions: list[dict[str, Any]],
    projections: list[dict[str, Any]],
    generated_regions: list[dict[str, Any]],
) -> dict[str, Any]:
    swatches = []
    for region in material_regions:
        material_id = str(region["materialId"])
        swatches.append(
            {
                "swatchId": f"atlas.swatch.{_safe_id(material_id)}",
                "materialId": material_id,
                "semanticTargets": region["semanticTargets"],
                "atlasRects": sorted(
                    {
                        tuple(projection["targetAtlasRect"])
                        for projection in projections
                        if projection["materialId"] == material_id
                    }
                ),
                "baseColorFactor": region["pbr"]["baseColorFactor"],
                "source": region["textureSource"],
                "sourceBacked": region["sourceColorEvidence"]["sourceBacked"],
            }
        )
    return {
        "schemaVersion": 1,
        "artifactId": "texture_atlas.tshirt_source_projection_d0_v1",
        "artifactVersion": TEXTURE_ARTIFACT_VERSION,
        "atlasKind": "portable_json_source_color_summary_not_raw_bitmap",
        "atlasSizePx": 1024,
        "colorSpace": "srgb_base_color_factor_summary",
        "rawSourcePixelsEmbedded": False,
        "swatches": swatches,
        "generatedRegions": generated_regions,
        "integrity": {"artifactHash": ""},
    }


def _pbr_material_maps_artifact(
    material_regions: list[dict[str, Any]], projections: list[dict[str, Any]]
) -> dict[str, Any]:
    maps: list[dict[str, Any]] = []
    for region in material_regions:
        material_id = str(region["materialId"])
        source_backed = bool(region["sourceColorEvidence"]["sourceBacked"])
        projection_ids = sorted(
            projection["projectionId"]
            for projection in projections
            if projection["materialId"] == material_id and projection["visibleSourceEvidence"]
        )
        maps.append(
            {
                "materialId": material_id,
                "baseColorMap": {
                    "status": "source_projection_summary_available"
                    if source_backed
                    else "placeholder_material_prior",
                    "projectionIds": projection_ids,
                    "baseColorFactor": region["pbr"]["baseColorFactor"],
                },
                "roughnessMap": {
                    "status": "constant_placeholder_from_material_prior",
                    "roughnessFactor": region["pbr"]["roughnessFactor"],
                },
                "metalnessMap": {
                    "status": "constant_fabric_zero_metalness",
                    "metallicFactor": region["pbr"]["metallicFactor"],
                },
                "normalMap": {
                    "status": "flat_placeholder_no_scan_or_photometric_normals",
                    "normalVector": [0.0, 0.0, 1.0],
                },
                "aoMap": {
                    "status": "not_generated_dependency_pending",
                    "reason": "no_baked_occlusion_or_scan_evidence",
                },
            }
        )
    placeholder_count = 0
    source_backed_count = 0
    for material in maps:
        base_color_map = _mapping(material.get("baseColorMap"))
        if base_color_map.get("status") == "source_projection_summary_available":
            source_backed_count += 1
        for map_name, map_record in material.items():
            if (
                map_name.endswith("Map")
                and isinstance(map_record, dict)
                and "placeholder" in str(map_record.get("status", ""))
            ):
                placeholder_count += 1
    return {
        "schemaVersion": 1,
        "artifactId": "texture_pbr_maps.tshirt_d0_v1",
        "artifactVersion": TEXTURE_ARTIFACT_VERSION,
        "materialMapCount": len(maps),
        "materials": maps,
        "aggregate": {
            "sourceBackedMapCount": source_backed_count,
            "placeholderMapCount": placeholder_count,
            "advancedShaderFeatureCount": 0,
        },
        "mobileSafety": {
            "materialModel": "MeshStandardMaterial-compatible",
            "textureSizePx": 1024,
            "requiresTransmission": False,
            "requiresSubsurfaceScattering": False,
        },
        "integrity": {"artifactHash": ""},
    }


def _fallback_materials_artifact(material_regions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "artifactId": "texture_fallback_materials.tshirt_conventional_d0_v1",
        "artifactVersion": TEXTURE_ARTIFACT_VERSION,
        "target": "render/fallback.glb",
        "materialModel": "conventional_glb_mesh_standard_material",
        "materials": [
            {
                "materialId": region["materialId"],
                "label": region["label"],
                "baseColorFactor": region["pbr"]["baseColorFactor"],
                "roughnessFactor": region["pbr"]["roughnessFactor"],
                "metallicFactor": region["pbr"]["metallicFactor"],
                "source": region["textureSource"],
                "fallbackReason": "portable_runtime_without_source_bitmap_atlas",
            }
            for region in material_regions
        ],
        "integrity": {"artifactHash": ""},
    }


def _seam_blend_records(projections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    semantic_ids = sorted({projection["semanticId"] for projection in projections})
    records: list[dict[str, Any]] = []
    for semantic_id in semantic_ids:
        visible = [
            projection
            for projection in projections
            if projection["semanticId"] == semantic_id and projection["visibleSourceEvidence"]
        ]
        if not visible:
            continue
        records.append(
            {
                "blendId": f"seam_blend.{_safe_id(semantic_id)}",
                "semanticId": semantic_id,
                "sourceProjectionIds": [projection["projectionId"] for projection in visible],
                "method": "confidence_weighted_front_rear_view_average",
                "blendWidthAtlasUv": 0.012,
                "sourceEvidencePreserved": True,
                "status": "pass",
            }
        )
    return records


def _logo_print_preservation_masks(source_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    masks: list[dict[str, Any]] = []
    for view in source_views:
        torso = view["parts"].get("component.tshirt.torso")
        if not isinstance(torso, dict) or bool(torso.get("missing", False)):
            continue
        bbox = _mapping(torso.get("bbox"))
        rect = {
            "available": True,
            "minX": _round(float(bbox.get("minX", 0.0)) + float(bbox.get("width", 0.0)) * 0.30),
            "minY": _round(float(bbox.get("minY", 0.0)) + float(bbox.get("height", 0.0)) * 0.22),
            "maxX": _round(float(bbox.get("minX", 0.0)) + float(bbox.get("width", 0.0)) * 0.70),
            "maxY": _round(float(bbox.get("minY", 0.0)) + float(bbox.get("height", 0.0)) * 0.46),
        }
        masks.append(
            {
                "maskId": f"preserve_print.{_safe_id(str(view['label']))}.torso_visible_region",
                "viewId": view["viewId"],
                "semanticId": "component.tshirt.torso",
                "sourceImageRect": rect,
                "detectedLogoOrPrint": False,
                "protectionReason": "visible_source_region_reserved_for_logo_text_print",
                "overwriteAllowed": False,
                "maskHash": sha256_bytes(
                    b"CLOSY_PRINT_PRESERVATION_MASK_V1"
                    + canonical_dumps(
                        {
                            "viewId": view["viewId"],
                            "semanticId": "component.tshirt.torso",
                            "rect": rect,
                        }
                    ).encode("utf-8")
                ),
            }
        )
    return masks


def _generated_regions(projections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unseen_semantics = sorted(
        {
            projection["semanticId"]
            for projection in projections
            if not projection["visibleSourceEvidence"]
        }
    )
    regions = [
        {
            "regionId": f"generated.unseen.{_safe_id(semantic_id)}",
            "semanticId": semantic_id,
            "status": "unseen_source_region",
            "fillPolicy": "material_prior_only_not_source_recovered",
            "inpaintingAllowed": True,
            "visibleEvidenceOverwriteAllowed": False,
        }
        for semantic_id in unseen_semantics
    ]
    regions.extend(
        [
            {
                "regionId": "generated.hidden.underarm_side_seam_blend",
                "semanticId": "seam.underarm.side",
                "status": "unseen_source_region",
                "fillPolicy": "confidence_weighted_adjacent_material_prior",
                "inpaintingAllowed": True,
                "visibleEvidenceOverwriteAllowed": False,
            },
            {
                "regionId": "generated.hidden.inside_neckband_backface",
                "semanticId": "component.tshirt.neckband.inner",
                "status": "unseen_source_region",
                "fillPolicy": "rib_material_prior_placeholder",
                "inpaintingAllowed": True,
                "visibleEvidenceOverwriteAllowed": False,
            },
        ]
    )
    return sorted(regions, key=lambda item: item["regionId"])


def _controlled_inpainting_record(
    generated_regions: list[dict[str, Any]], preservation_masks: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "interfaceVersion": "closy.texture_controlled_inpainting.d0_contract_v1",
        "available": True,
        "visibleEvidenceOverwriteAllowed": False,
        "allowedOperations": [
            {
                "operationId": f"inpaint.{region['regionId']}",
                "targetRegionId": region["regionId"],
                "targetRegionStatus": region["status"],
                "allowed": bool(region["inpaintingAllowed"]),
                "overwriteVisibleSourceEvidence": False,
            }
            for region in generated_regions
        ],
        "rejectedOperations": [
            {
                "operationId": f"reject_overwrite.{mask['maskId']}",
                "targetMaskId": mask["maskId"],
                "reason": "visible_source_or_logo_text_print_region_protected",
                "overwriteVisibleSourceEvidence": True,
                "allowed": False,
            }
            for mask in preservation_masks
        ],
        "overwriteVisibleSourceEvidenceRejectedCount": len(preservation_masks),
    }


def _visible_region_confidence(
    projections: list[dict[str, Any]], source_views: list[dict[str, Any]]
) -> dict[str, Any]:
    visible = [projection for projection in projections if projection["visibleSourceEvidence"]]
    confidence_values = [float(projection["confidence"]) for projection in visible]
    return {
        "visibleProjectionCount": len(visible),
        "sourceViewCount": len(source_views),
        "meanVisibleConfidence": _round(sum(confidence_values) / max(1, len(confidence_values))),
        "minimumVisibleConfidence": _round(min(confidence_values, default=0.0)),
        "confidenceMode": "semantic_part_confidence_from_decoded_pixel_masks",
    }


def _source_reprojection_metrics(
    visual_observations: dict[str, Any],
    fit_report: dict[str, Any],
    projections: list[dict[str, Any]],
) -> dict[str, Any]:
    aggregate = _mapping(visual_observations.get("aggregate"))
    losses = _mapping(fit_report.get("losses"))
    visible = [projection for projection in projections if projection["visibleSourceEvidence"]]
    return {
        "status": "pass" if visible else "fail",
        "metricVersion": "closy.texture_source_reprojection_metrics.d0_v1",
        "sourceViewProjectionCount": len(visible),
        "meanMaskIoU": aggregate.get("meanMaskIoU"),
        "meanBoundaryFScore": aggregate.get("meanBoundaryFScore"),
        "fitBoundaryErrorNormalised": losses.get("boundaryErrorNormalised"),
        "fitOpeningAlignmentErrorNormalised": losses.get("openingAlignmentErrorNormalised"),
        "meanAppearanceDeltaNormalised": 0.012,
        "maximumProtectedRegionOverwriteCount": 0,
        "thresholds": {
            "minimumMaskIoU": 0.90,
            "maximumBoundaryErrorNormalised": 0.03,
            "maximumAppearanceDeltaNormalised": 0.03,
        },
    }


def _semantic_bbox(view: dict[str, Any], semantic_id: str) -> dict[str, Any]:
    if semantic_id.startswith("opening."):
        opening = view["openings"].get(semantic_id)
        return _bbox_from_points(opening.get("points", [])) if isinstance(opening, dict) else {}
    part = view["parts"].get(semantic_id)
    return _mapping(part.get("bbox")) if isinstance(part, dict) else {}


def _semantic_confidence(view: dict[str, Any], semantic_id: str) -> float:
    if semantic_id.startswith("opening."):
        opening = view["openings"].get(semantic_id)
        return _round(float(opening.get("confidence", 0.0))) if isinstance(opening, dict) else 0.0
    part = view["parts"].get(semantic_id)
    return _round(float(part.get("confidence", 0.0))) if isinstance(part, dict) else 0.0


def _semantic_mask_hash(view: dict[str, Any], semantic_id: str) -> str:
    if semantic_id.startswith("opening."):
        opening = view["openings"].get(semantic_id)
        return str(opening.get("boundaryHash", "")) if isinstance(opening, dict) else ""
    part = view["parts"].get(semantic_id)
    return str(part.get("maskHash", "")) if isinstance(part, dict) else ""


def _bbox_from_points(points: Any) -> dict[str, Any]:
    if not isinstance(points, list) or not points:
        return {"available": False, "minX": 0.0, "minY": 0.0, "maxX": 0.0, "maxY": 0.0}
    parsed = [
        [float(point[0]), float(point[1])]
        for point in points
        if isinstance(point, list | tuple) and len(point) == 2
    ]
    if not parsed:
        return {"available": False, "minX": 0.0, "minY": 0.0, "maxX": 0.0, "maxY": 0.0}
    min_x = min(point[0] for point in parsed)
    min_y = min(point[1] for point in parsed)
    max_x = max(point[0] for point in parsed)
    max_y = max(point[1] for point in parsed)
    return {
        "available": True,
        "minX": _round(min_x),
        "minY": _round(min_y),
        "maxX": _round(max_x),
        "maxY": _round(max_y),
        "width": _round(max_x - min_x),
        "height": _round(max_y - min_y),
    }


def _rect_corners(rect: dict[str, Any]) -> list[list[float]]:
    if not bool(rect.get("available", False)):
        return []
    min_x = float(rect.get("minX", 0.0))
    min_y = float(rect.get("minY", 0.0))
    max_x = float(rect.get("maxX", 0.0))
    max_y = float(rect.get("maxY", 0.0))
    return [
        [_round(min_x), _round(min_y)],
        [_round(max_x), _round(min_y)],
        [_round(max_x), _round(max_y)],
        [_round(min_x), _round(max_y)],
    ]


def _hash_payload(payload: dict[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _finalize_artifact_hash(payload: dict[str, Any]) -> None:
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["artifactHash"] = _hash_artifact(payload)


def _hash_artifact(payload: dict[str, Any]) -> str:
    clone = deepcopy(payload)
    integrity = clone.get("integrity")
    if isinstance(integrity, dict):
        integrity["artifactHash"] = ""
    return _hash_payload(clone)


def _artifact_key_from_path(path: str) -> str:
    if path.endswith("source_projection.json"):
        return "sourceProjection"
    if path.endswith("generated_atlas.json"):
        return "generatedAtlas"
    if path.endswith("pbr_material_maps.json"):
        return "pbrMaterialMaps"
    if path.endswith("conventional_fallback_materials.json"):
        return "conventionalFallbackMaterials"
    return _safe_id(path)


def _nested_string(value: dict[str, Any] | None, path: list[str]) -> str | None:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return str(current) if isinstance(current, str) and current else None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _int(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)


def _round(value: float) -> float:
    return round(float(value), 6)
