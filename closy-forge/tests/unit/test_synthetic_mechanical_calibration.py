from __future__ import annotations

from copy import deepcopy

import pytest

from closy_forge.simulation.material_physics import build_material_preset_registry
from closy_forge.simulation.synthetic_mechanical_calibration import (
    SYNTHETIC_CALIBRATION_VERSION,
    SyntheticCalibrationError,
    build_synthetic_coupon_observations,
    hash_synthetic_mechanical_calibration,
    run_synthetic_mechanical_calibration,
    validate_synthetic_mechanical_calibration,
)
from closy_forge.validation.validator import validate_package
from tests.helpers import build_demo, clone_package, issue_codes, read_json, write_json


def test_inverse_calibration_runs_four_presets_with_unseen_holdouts() -> None:
    registry = build_material_preset_registry()
    report = run_synthetic_mechanical_calibration(registry)

    assert report == run_synthetic_mechanical_calibration(registry)
    assert report["calibrationVersion"] == SYNTHETIC_CALIBRATION_VERSION
    assert report["corpus"]["presetCount"] == 4
    assert report["corpus"]["observationCount"] == 200
    assert report["corpus"]["calibrationObservationCount"] == 120
    assert report["corpus"]["holdoutObservationCount"] == 80
    assert report["corpus"]["uncalibratedDescriptorFields"] == ["warpOrientation"]
    assert report["aggregate"]["parameterRecordCount"] == 40
    assert report["aggregate"]["finiteParameterRecordCount"] == 40
    assert report["aggregate"]["identifiableParameterRecordCount"] == 40
    assert report["aggregate"]["worstNormalizedParameterError"] <= 0.0025
    assert report["aggregate"]["worstHoldoutNormalizedRmse"] <= 0.025
    assert report["aggregate"]["calibratedToBaselineErrorRatio"] < 0.25
    assert report["readiness"]["acceptedForProjectAuthoredSyntheticCalibration"] is True
    assert report["readiness"]["acceptedAsMeasuredRealFabric"] is False
    assert report["truth"]["statisticalConfidenceIntervalClaimed"] is False
    validate_synthetic_mechanical_calibration(report, registry)


def test_coupon_observations_are_split_and_do_not_embed_parameter_truth() -> None:
    descriptor = build_material_preset_registry()["presets"][1]
    observations = build_synthetic_coupon_observations(descriptor)

    assert len(observations) == 50
    assert sum(row["split"] == "calibration" for row in observations) == 30
    assert sum(row["split"] == "holdout" for row in observations) == 20
    assert len({row["observationId"] for row in observations}) == 50
    assert len({row["observationHash"] for row in observations}) == 50
    assert all("authoredSyntheticTruth" not in row for row in observations)
    assert all(row["realFabricMeasurement"] is False for row in observations)


def test_inverse_estimates_follow_descriptor_values_not_preset_identity() -> None:
    registry = build_material_preset_registry()
    report = run_synthetic_mechanical_calibration(registry)
    estimates_by_preset = {
        preset["presetId"]: {
            parameter["parameter"]: parameter["estimatedValue"]
            for parameter in preset["parameters"]
        }
        for preset in report["presets"]
    }

    warp_estimates = {
        estimates["warpStretchStiffness"] for estimates in estimates_by_preset.values()
    }
    density_estimates = {estimates["arealDensity"] for estimates in estimates_by_preset.values()}
    assert len(warp_estimates) == 4
    assert len(density_estimates) == 4
    for descriptor in registry["presets"]:
        estimates = estimates_by_preset[descriptor["presetId"]]
        for parameter in report["presets"][0]["parameters"]:
            name = parameter["parameter"]
            field = descriptor["fields"][name]
            global_range = field["validRange"][1] - field["validRange"][0]
            assert abs(estimates[name] - field["value"]) / global_range <= 0.0025


def test_semantic_mutation_fails_even_when_outer_hash_is_recomputed() -> None:
    registry = build_material_preset_registry()
    report = run_synthetic_mechanical_calibration(registry)
    mutated = deepcopy(report)
    mutated["presets"][0]["parameters"][0]["estimatedValue"] *= 1.5
    mutated["integrity"]["reportHash"] = hash_synthetic_mechanical_calibration(mutated)

    with pytest.raises(SyntheticCalibrationError, match="synthetic_calibration_content_mismatch"):
        validate_synthetic_mechanical_calibration(mutated, registry)


def test_unsupported_real_fabric_promotion_fails_closed() -> None:
    registry = build_material_preset_registry()
    report = run_synthetic_mechanical_calibration(registry)
    report["readiness"]["acceptedAsMeasuredRealFabric"] = True
    report["integrity"]["reportHash"] = hash_synthetic_mechanical_calibration(report)

    with pytest.raises(SyntheticCalibrationError):
        validate_synthetic_mechanical_calibration(report, registry)


def test_package_synthetic_calibration_corruption_fails_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = clone_package(
        build_demo(tmp_path), tmp_path / "bad_synthetic_calibration.closygarment"
    )
    path = package / "reports" / "synthetic_mechanical_calibration.json"
    report = read_json(path)
    report["presets"][0]["parameters"][0]["holdoutNormalizedRmse"] = 0.5
    report["integrity"]["reportHash"] = hash_synthetic_mechanical_calibration(report)
    write_json(path, report)

    codes = issue_codes(validate_package(package))

    assert "file_hash_mismatch" in codes
    assert "synthetic_mechanical_calibration_invalid" in codes
