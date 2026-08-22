from __future__ import annotations

from closy_forge.capture import build_synthetic_capture_record
from closy_forge.fitting import (
    fit_tshirt_parameters_from_visual_observations,
    hash_tshirt_fit_report,
)
from closy_forge.visual_understanding import build_tshirt_visual_observations


def test_tshirt_fit_report_is_deterministic_and_bounded() -> None:
    visual = build_tshirt_visual_observations(build_synthetic_capture_record(seed=101))
    first = fit_tshirt_parameters_from_visual_observations(visual)
    second = fit_tshirt_parameters_from_visual_observations(visual)

    assert first == second
    assert first["status"] == "pass"
    assert first["accepted"] is True
    assert first["integrity"]["fitReportHash"] == hash_tshirt_fit_report(first)
    assert (
        first["losses"]["landmarkRmsNormalised"]
        <= first["thresholds"]["maximumLandmarkRmsNormalised"]
    )
    assert first["fittedParameters"]["garment_body_length"] == 0.68
    assert first["fittedParameters"]["shoulder_width"] == 0.7
    assert len(first["alternatives"]) == 2
