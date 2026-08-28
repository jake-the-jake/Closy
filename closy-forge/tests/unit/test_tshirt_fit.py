from __future__ import annotations

from copy import deepcopy

import pytest

from closy_forge.capture import build_synthetic_capture_record
from closy_forge.fitting import (
    TSHIRT_FIT_REPORT_VERSION,
    fit_tshirt_parameters_from_visual_observations,
    hash_tshirt_fit_report,
)
from closy_forge.fitting.d0_optimizer import evaluate_candidate, validate_d0_fit_evidence
from closy_forge.garments.tshirt.parameters import TShirtParameters
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
    assert first["method"] == "bounded_iterative_decoded_raster_fit_with_full_solver_verification"
    assert first["sourceMultiviewFusionId"] == fusion["fusionRecordId"]
    assert first["sourceMultiviewFusionHash"] == fusion["integrity"]["multiviewFusionRecordHash"]
    assert first["sourceFusedEvidenceHash"] == hash_fused_evidence(fusion["fusedEvidence"])
    assert first["integrity"]["fitReportHash"] == hash_tshirt_fit_report(first)
    assert first["evidenceSeparation"]["expectedParametersFromFixtureSource"] is False
    assert len(first["evidenceSeparation"]["observedEvidence"]) == 2
    assert len(first["optimizationTrace"]) >= 4
    assert first["status"] == "fail"
    assert first["accepted"] is False
    assert first["convergence"]["status"] == "bounded_without_acceptance"
    assert first["convergence"]["absoluteImprovement"] > 0.0
    assert first["convergence"]["noOpCandidateAccepted"] is False
    assert first["heldOutEvaluation"]["status"] == "pass"
    assert first["perturbationEvaluation"]["status"] == "pass"
    assert first["settledRenderComparison"]["status"] == "fail"
    assert first["settledRenderComparison"]["fullSolverRun"] is True
    assert first["settledRenderComparison"]["renderedCandidateEvaluated"] is True
    assert len(first["alternatives"]) >= 2
    assert all(control["status"] == "pass_rejected" for control in first["corruptionControls"])
    assert (
        first["losses"]["multiviewSilhouetteMeanIoU"]
        >= first["thresholds"]["minimumMultiviewSilhouetteMeanIoU"]
    )
    assert (
        first["losses"]["confidenceWeightedLoss"]
        <= first["thresholds"]["maximumConfidenceWeightedLoss"]
    )


def test_tshirt_fit_rejects_corrupt_decoded_mask_and_camera_evidence() -> None:
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    fusion = build_multiview_fusion_record(
        capture,
        visual,
        build_default_applied_correction_record(visual),
    )
    corrupt_mask = deepcopy(visual)
    target = next(
        mask
        for mask in corrupt_mask["views"][0]["masks"]
        if mask["semanticId"] == "component.tshirt"
    )
    target["rle"]["runs"] = [[target["rle"]["width"] * target["rle"]["height"], 1]]
    with pytest.raises(ValueError, match="d0_fit_corrupt_mask_rle"):
        evaluate_candidate(corrupt_mask, fusion, TShirtParameters(), TShirtParameters())

    corrupt_camera = deepcopy(visual)
    corrupt_camera["views"][0]["camera"]["azimuthDegrees"] = 90.0
    with pytest.raises(ValueError, match="d0_fit_camera_evidence_invalid"):
        validate_d0_fit_evidence(corrupt_camera, fusion)
