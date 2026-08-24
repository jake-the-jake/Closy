from __future__ import annotations

from closy_forge.capture import build_synthetic_capture_record
from closy_forge.fitting import (
    TSHIRT_FIT_REPORT_VERSION,
    fit_tshirt_parameters_from_visual_observations,
    hash_tshirt_fit_report,
)
from closy_forge.visual_understanding import (
    build_default_applied_correction_record,
    build_multiview_fusion_record,
    build_tshirt_visual_observations,
    hash_fused_evidence,
)


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
    assert first["fittedParameters"]["shoulder_width"] == 0.699417
    assert len(first["alternatives"]) == 2


def test_tshirt_multiview_fit_report_is_image_conditioned_and_hash_linked() -> None:
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    correction = build_default_applied_correction_record(visual)
    fusion = build_multiview_fusion_record(capture, visual, correction)

    first = fit_tshirt_parameters_from_visual_observations(
        visual,
        multiview_fusion=fusion,
    )
    second = fit_tshirt_parameters_from_visual_observations(
        visual,
        multiview_fusion=fusion,
    )

    assert first == second
    assert first["fitterVersion"] == TSHIRT_FIT_REPORT_VERSION
    assert first["fitReportId"] == "fit.image_conditioned_tshirt_multiview_d0_v1"
    assert first["method"] == "deterministic_multiview_image_conditioned_from_fused_raster_evidence"
    assert first["sourceMultiviewFusionId"] == fusion["fusionRecordId"]
    assert first["sourceMultiviewFusionHash"] == fusion["integrity"]["multiviewFusionRecordHash"]
    assert first["sourceFusedEvidenceHash"] == hash_fused_evidence(fusion["fusedEvidence"])
    assert first["integrity"]["fitReportHash"] == hash_tshirt_fit_report(first)
    assert first["evidenceSeparation"]["expectedParametersFromFixtureSource"] is False
    assert len(first["evidenceSeparation"]["observedEvidence"]) == 2
    assert len(first["optimizationTrace"]) >= 4
    assert first["convergence"]["status"] == "converged_d0_synthetic"
    assert first["heldOutEvaluation"]["status"] == "pass"
    assert first["perturbationEvaluation"]["status"] == "pass"
    assert first["settledRenderComparison"]["status"] == "not_run_dependency_pending"
    assert len(first["alternatives"]) == 2
    assert (
        first["losses"]["multiviewSilhouetteMeanIoU"]
        >= first["thresholds"]["minimumMultiviewSilhouetteMeanIoU"]
    )
    assert (
        first["losses"]["confidenceWeightedLoss"]
        <= first["thresholds"]["maximumConfidenceWeightedLoss"]
    )
