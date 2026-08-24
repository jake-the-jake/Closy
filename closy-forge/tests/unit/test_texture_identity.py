from __future__ import annotations

from closy_forge.appearance import build_texture_identity_report, hash_texture_identity_report
from closy_forge.capture import build_synthetic_capture_record
from closy_forge.fitting import fit_tshirt_parameters_from_visual_observations
from closy_forge.visual_understanding import (
    build_default_applied_correction_record,
    build_multiview_fusion_record,
    build_tshirt_visual_observations,
)


def test_texture_identity_report_is_deterministic_and_mobile_safe() -> None:
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    correction = build_default_applied_correction_record(visual)
    fusion = build_multiview_fusion_record(capture, visual, correction)
    fit = fit_tshirt_parameters_from_visual_observations(visual, multiview_fusion=fusion)
    materials = {
        "schemaVersion": 1,
        "materials": [
            {
                "id": "material.cotton_jersey_reference_v1",
                "label": "Fixture cotton jersey blue",
                "pbr": {
                    "baseColorFactor": [0.08, 0.26, 0.78, 1.0],
                    "roughnessFactor": 0.86,
                    "metallicFactor": 0.0,
                },
            },
            {
                "id": "material.cotton_rib_reference_v1",
                "label": "Fixture cotton rib collar",
                "pbr": {
                    "baseColorFactor": [0.06, 0.20, 0.62, 1.0],
                    "roughnessFactor": 0.9,
                    "metallicFactor": 0.0,
                },
            },
        ],
    }

    first = build_texture_identity_report(
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        render_materials=materials,
        multiview_fusion=fusion,
    )
    second = build_texture_identity_report(
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        render_materials=materials,
        multiview_fusion=fusion,
    )

    assert first == second
    assert first["status"] == "pass"
    assert first["sourceTextureAvailable"] is True
    assert first["generatedAtlasAvailable"] is True
    assert first["textureProjectionRun"] is True
    assert first["integrity"]["textureIdentityHash"] == hash_texture_identity_report(first)
    assert first["sourceMultiviewFusionId"] == fusion["fusionRecordId"]
    assert first["sourceFusedEvidenceHash"] == fusion["fusedEvidence"]["evidenceHash"]
    assert first["sourceViewProjection"]["visibleProjectionCount"] > 0
    assert first["visibleRegionConfidence"]["meanVisibleConfidence"] >= 0.9
    assert first["logoPrintPreservation"]["visibleSourceOverwriteAllowed"] is False
    assert first["controlledInpainting"]["visibleEvidenceOverwriteAllowed"] is False
    assert first["controlledInpainting"]["overwriteVisibleSourceEvidenceRejectedCount"] > 0
    assert first["policy"]["rawPixelsExported"] is False
    assert set(first["artifactRefs"]) == {
        "conventionalFallbackMaterials",
        "generatedAtlas",
        "pbrMaterialMaps",
        "sourceProjection",
    }
    assert len(first["observedMaterialRegions"]) == 2
    assert any(
        region["textureSource"] == "source_projection_summary"
        for region in first["observedMaterialRegions"]
    )
    assert first["pbrMaterialMaps"]["sourceBackedMapCount"] >= 1
    assert first["pbrMaterialMaps"]["placeholderMapCount"] >= 1
    for region in first["observedMaterialRegions"]:
        pbr = region["pbr"]
        assert pbr["normalMapAvailable"] is False
        assert pbr["roughnessMapAvailable"] is True
        assert pbr["metalnessMapAvailable"] is True
        assert pbr["aoMapAvailable"] is False
        assert 0.65 <= pbr["roughnessFactor"] <= 1.0
        assert 0.0 <= pbr["metallicFactor"] <= 0.1


def test_tshirt_visual_parts_include_privacy_safe_color_evidence() -> None:
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)

    parts = [
        part
        for view in visual["views"]
        for part in view["semanticParts"]
        if part["semanticId"] == "component.tshirt.torso"
    ]

    assert parts
    for part in parts:
        color = part["colorEvidence"]
        assert color["source"] == "decoded_pixel_mean_rgba_summary"
        assert color["sourcePixelsPortable"] is False
        assert color["pixelSampleCount"] > 0
        assert len(color["meanBaseColorFactor"]) == 4
