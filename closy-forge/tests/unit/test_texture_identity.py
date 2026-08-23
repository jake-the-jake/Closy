from __future__ import annotations

from closy_forge.appearance import build_texture_identity_report, hash_texture_identity_report
from closy_forge.capture import build_synthetic_capture_record
from closy_forge.fitting import fit_tshirt_parameters_from_visual_observations
from closy_forge.visual_understanding import build_tshirt_visual_observations


def test_texture_identity_report_is_deterministic_and_mobile_safe() -> None:
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    fit = fit_tshirt_parameters_from_visual_observations(visual)
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
    )
    second = build_texture_identity_report(
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        render_materials=materials,
    )

    assert first == second
    assert first["status"] == "pass"
    assert first["sourceTextureAvailable"] is False
    assert first["generatedAtlasAvailable"] is False
    assert first["textureProjectionRun"] is False
    assert first["integrity"]["textureIdentityHash"] == hash_texture_identity_report(first)
    assert len(first["observedMaterialRegions"]) == 2
    for region in first["observedMaterialRegions"]:
        pbr = region["pbr"]
        assert pbr["normalMapAvailable"] is False
        assert pbr["roughnessMapAvailable"] is False
        assert pbr["metalnessMapAvailable"] is False
        assert pbr["aoMapAvailable"] is False
        assert 0.65 <= pbr["roughnessFactor"] <= 1.0
        assert 0.0 <= pbr["metallicFactor"] <= 0.1
