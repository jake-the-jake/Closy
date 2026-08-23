from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

TEXTURE_IDENTITY_VERSION = "closy.texture_identity.synthetic_pbr_v1"


def build_texture_identity_report(
    *,
    capture_record: dict[str, Any],
    visual_observations: dict[str, Any],
    fit_report: dict[str, Any],
    render_materials: dict[str, Any],
) -> dict[str, Any]:
    materials = render_materials.get("materials", [])
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "textureIdentityId": "texture.synthetic_tshirt_identity_v1",
        "stageVersion": TEXTURE_IDENTITY_VERSION,
        "sourceRecordId": capture_record["recordId"],
        "sourceRecordHash": capture_record["immutability"]["sourceRecordHash"],
        "sourceVisualUnderstandingId": visual_observations["visualUnderstandingId"],
        "sourceVisualRecordHash": visual_observations["integrity"]["visualRecordHash"],
        "sourceFitReportId": fit_report["fitReportId"],
        "sourceFitReportHash": fit_report["integrity"]["fitReportHash"],
        "status": "pass",
        "sourceTextureAvailable": False,
        "generatedAtlasAvailable": False,
        "textureProjectionRun": False,
        "observedMaterialRegions": [
            _material_region(material, index) for index, material in enumerate(materials)
        ],
        "projectionPlan": {
            "targetMeshPath": "render/fallback.glb",
            "targetUvSpace": "panel_uvs",
            "recommendedAtlasSizePx": 1024,
            "seamBlending": "not_started_no_source_pixels",
            "occludedRegionPolicy": "retain_authored_material_until_source_evidence_exists",
            "normalMapPolicy": "not_generated_without_source_or_scan",
        },
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
        "warnings": [
            "source_texture_projection_not_run",
            "synthetic_material_identity_not_observed_from_photos",
        ],
        "integrity": {"textureIdentityHash": ""},
    }
    report["integrity"]["textureIdentityHash"] = hash_texture_identity_report(report)
    return report


def hash_texture_identity_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["textureIdentityHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _material_region(material: dict[str, Any], index: int) -> dict[str, Any]:
    pbr = material.get("pbr", {})
    base_color = pbr.get("baseColorFactor", [0.08, 0.26, 0.78, 1.0])
    roughness = float(pbr.get("roughnessFactor", 0.86))
    metallic = float(pbr.get("metallicFactor", 0.0))
    return {
        "regionId": f"texture.region.{index:02d}",
        "materialId": str(material.get("id", f"material.unknown.{index:02d}")),
        "label": str(material.get("label", "Unnamed material")),
        "evidenceKind": "authored_fixture_pbr_not_photo_recovered",
        "evidenceViews": ["view.front", "view.back"],
        "coverageConfidence": 0.72,
        "pbr": {
            "baseColorFactor": [float(value) for value in base_color],
            "roughnessFactor": max(0.65, min(1.0, roughness)),
            "metallicFactor": max(0.0, min(0.1, metallic)),
            "normalMapAvailable": False,
            "roughnessMapAvailable": False,
            "metalnessMapAvailable": False,
            "aoMapAvailable": False,
        },
        "textureSource": "authored_color_only_until_source_projection",
    }
