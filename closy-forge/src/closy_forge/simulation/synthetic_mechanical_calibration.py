from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from math import exp, isfinite, log, sqrt
from typing import Any, Literal, cast

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.simulation.material_physics import validate_fabric_descriptor

SYNTHETIC_CALIBRATION_VERSION = "closy.synthetic_mechanical_calibration.d0.v2"
SYNTHETIC_COUPON_CORPUS_VERSION = "closy.synthetic_coupon_corpus.project_authored.v1"
SYNTHETIC_CALIBRATION_SOLVER_VERSION = "closy.bounded_coupon_inverse_grid.v1"

_GRID_POINT_COUNT = 2049
_CALIBRATION_SPLIT: tuple[float, ...] = (0.72, 1.08, 1.44)
_HOLDOUT_SPLIT: tuple[float, ...] = (0.90, 1.26)


class SyntheticCalibrationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class _ParameterSpec:
    name: str
    unit: str
    response_unit: str
    fixture_kind: str
    minimum: float
    maximum: float
    search_scale: Literal["linear", "log"]


_PARAMETER_SPECS = (
    _ParameterSpec(
        "thickness",
        "m",
        "m_compressed_thickness",
        "bounded_compression_coupon",
        0.0002,
        0.008,
        "log",
    ),
    _ParameterSpec(
        "arealDensity",
        "kg/m^2",
        "m_gravity_sag",
        "tensioned_gravity_sag_coupon",
        0.03,
        0.8,
        "log",
    ),
    _ParameterSpec(
        "warpStretchStiffness",
        "N/m",
        "ratio_extension",
        "warp_uniaxial_coupon",
        20.0,
        5000.0,
        "log",
    ),
    _ParameterSpec(
        "weftStretchStiffness",
        "N/m",
        "ratio_extension",
        "weft_uniaxial_coupon",
        20.0,
        5000.0,
        "log",
    ),
    _ParameterSpec(
        "shearStiffness",
        "N/m",
        "ratio_shear_displacement",
        "bias_extension_shear_coupon",
        5.0,
        2000.0,
        "log",
    ),
    _ParameterSpec(
        "bendStiffness",
        "N*m",
        "rad_tip_rotation",
        "cantilever_bend_coupon",
        0.00005,
        0.05,
        "log",
    ),
    _ParameterSpec(
        "dampingRatio",
        "ratio",
        "m_residual_amplitude",
        "free_decay_coupon",
        0.0,
        0.95,
        "linear",
    ),
    _ParameterSpec(
        "frictionCoefficient",
        "coefficient",
        "m/s^2_slide_acceleration",
        "inclined_plane_coupon",
        0.0,
        1.5,
        "linear",
    ),
    _ParameterSpec(
        "collisionClearance",
        "m",
        "m_resting_height",
        "floor_clearance_coupon",
        0.0005,
        0.03,
        "log",
    ),
    _ParameterSpec(
        "restitutionCoefficient",
        "coefficient",
        "m_rebound_height",
        "vertical_drop_coupon",
        0.0,
        1.0,
        "linear",
    ),
)


def run_synthetic_mechanical_calibration(registry: dict[str, Any]) -> dict[str, Any]:
    """Recover authored descriptor fields from synthetic coupon observations.

    The forward fixtures are project-authored numerical instruments. They are useful for
    deterministic inverse-calibration engineering, but they are not measurements of fabric.
    """

    registry_hash = _validate_registry(registry)
    preset_reports: list[dict[str, Any]] = []
    all_observation_hashes: list[str] = []
    for descriptor_value in registry["presets"]:
        descriptor = cast(dict[str, Any], descriptor_value)
        observations = build_synthetic_coupon_observations(descriptor)
        all_observation_hashes.extend(
            str(observation["observationHash"]) for observation in observations
        )
        preset_reports.append(_calibrate_preset(descriptor, observations))

    parameter_records = [
        parameter
        for preset in preset_reports
        for parameter in cast(list[dict[str, Any]], preset["parameters"])
    ]
    holdout_errors = [float(record["holdoutNormalizedRmse"]) for record in parameter_records]
    baseline_errors = [
        float(record["baselineHoldoutNormalizedRmse"]) for record in parameter_records
    ]
    parameter_errors = [float(record["normalizedParameterError"]) for record in parameter_records]
    accepted = (
        len(preset_reports) == 4
        and len(parameter_records) == 40
        and all(bool(record["finite"]) for record in parameter_records)
        and all(bool(record["identifiableWithinGridResolution"]) for record in parameter_records)
        and all(bool(record["improvesMidpointBaseline"]) for record in parameter_records)
        and max(parameter_errors, default=1.0) <= 0.0025
        and _mean(holdout_errors) <= 0.006
        and max(holdout_errors, default=1.0) <= 0.025
        and _mean(holdout_errors) < _mean(baseline_errors) * 0.25
    )
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "calibrationVersion": SYNTHETIC_CALIBRATION_VERSION,
        "calibrationId": "material_calibration.project_authored_synthetic_coupons_v2",
        "solverVersion": SYNTHETIC_CALIBRATION_SOLVER_VERSION,
        "sourceRegistryHash": registry_hash,
        "corpus": {
            "corpusVersion": SYNTHETIC_COUPON_CORPUS_VERSION,
            "sourceKind": "deterministic_project_authored_synthetic_mechanical_tests",
            "presetCount": len(preset_reports),
            "parameterCountPerPreset": len(_PARAMETER_SPECS),
            "calibratedDescriptorFields": [spec.name for spec in _PARAMETER_SPECS],
            "uncalibratedDescriptorFields": ["warpOrientation"],
            "observationCount": len(all_observation_hashes),
            "calibrationObservationCount": len(preset_reports)
            * len(_PARAMETER_SPECS)
            * len(_CALIBRATION_SPLIT),
            "holdoutObservationCount": len(preset_reports)
            * len(_PARAMETER_SPECS)
            * len(_HOLDOUT_SPLIT),
            "observationSetHash": sha256_bytes(
                canonical_dumps(sorted(all_observation_hashes)).encode("utf-8")
            ),
            "calibrationStimuli": list(_CALIBRATION_SPLIT),
            "unseenHoldoutStimuli": list(_HOLDOUT_SPLIT),
        },
        "presets": preset_reports,
        "aggregate": {
            "presetCount": len(preset_reports),
            "parameterRecordCount": len(parameter_records),
            "finiteParameterRecordCount": sum(
                bool(record["finite"]) for record in parameter_records
            ),
            "identifiableParameterRecordCount": sum(
                bool(record["identifiableWithinGridResolution"]) for record in parameter_records
            ),
            "meanNormalizedParameterError": _round(_mean(parameter_errors)),
            "worstNormalizedParameterError": _round(max(parameter_errors, default=1.0)),
            "meanHoldoutNormalizedRmse": _round(_mean(holdout_errors)),
            "p95HoldoutNormalizedRmse": _round(_percentile(holdout_errors, 0.95)),
            "worstHoldoutNormalizedRmse": _round(max(holdout_errors, default=1.0)),
            "midpointBaselineMeanHoldoutNormalizedRmse": _round(_mean(baseline_errors)),
            "calibratedToBaselineErrorRatio": _round(
                _mean(holdout_errors) / max(_mean(baseline_errors), 1e-15)
            ),
        },
        "readiness": {
            "actualSyntheticMechanicalTestsRun": True,
            "allFourAuthoredPresetsEvaluated": len(preset_reports) == 4,
            "unseenSyntheticHoldoutEvaluated": len(all_observation_hashes) == 200,
            "calibratedModelOutperformsMidpointBaseline": _mean(holdout_errors)
            < _mean(baseline_errors) * 0.25,
            "acceptedForProjectAuthoredSyntheticCalibration": accepted,
            "acceptedAsMeasuredRealFabric": False,
            "acceptedForLearnedMaterialInference": False,
            "acceptedForPrivateUserMaterialEstimation": False,
            "acceptedForProductionGpuMotion": False,
        },
        "truth": {
            "projectAuthoredSyntheticObservations": True,
            "realFabricMeasurementRun": False,
            "learnedInferenceRun": False,
            "privateUserMaterialEstimationRun": False,
            "productionGpuRun": False,
            "statisticalConfidenceIntervalClaimed": False,
            "intervalKind": "deterministic_grid_resolution_interval_not_statistical_confidence",
        },
        "unsupportedEvidence": [
            "real_fabric_physical_accuracy",
            "appearance_to_material_inference",
            "private_user_material_estimation",
            "production_gpu_cloth",
            "mobile_device_performance",
        ],
        "integrity": {"reportHash": ""},
    }
    report["integrity"]["reportHash"] = hash_synthetic_mechanical_calibration(report)
    return report


def build_synthetic_coupon_observations(descriptor: dict[str, Any]) -> list[dict[str, Any]]:
    validate_fabric_descriptor(descriptor)
    preset_id = str(descriptor["presetId"])
    observations: list[dict[str, Any]] = []
    for spec in _PARAMETER_SPECS:
        true_value = float(descriptor["fields"][spec.name]["value"])
        for split, stimuli in (
            ("calibration", _CALIBRATION_SPLIT),
            ("holdout", _HOLDOUT_SPLIT),
        ):
            for index, stimulus in enumerate(stimuli):
                observation_id = f"coupon.{preset_id}.{spec.name}.{split}.{index:02d}"
                ideal = _response(spec, true_value, stimulus)
                measured = ideal * _measurement_factor(observation_id)
                observation: dict[str, Any] = {
                    "observationId": observation_id,
                    "fixtureKind": spec.fixture_kind,
                    "parameter": spec.name,
                    "split": split,
                    "stimulus": _round(stimulus),
                    "stimulusUnit": "normalized_fixture_control",
                    "measuredResponse": _round(measured),
                    "responseUnit": spec.response_unit,
                    "sourceKind": "project_authored_synthetic_numerical_fixture",
                    "realFabricMeasurement": False,
                    "observationHash": "",
                }
                observation["observationHash"] = _hash_with_blank(observation, "observationHash")
                observations.append(observation)
    return observations


def validate_synthetic_mechanical_calibration(
    report: dict[str, Any], registry: dict[str, Any]
) -> None:
    if report.get("schemaVersion") != 1 or report.get("calibrationVersion") != (
        SYNTHETIC_CALIBRATION_VERSION
    ):
        raise SyntheticCalibrationError("unknown_schema_version")
    integrity = report.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("reportHash") != (
        hash_synthetic_mechanical_calibration(report)
    ):
        raise SyntheticCalibrationError("report_hash_mismatch")
    expected = run_synthetic_mechanical_calibration(registry)
    if report != expected:
        raise SyntheticCalibrationError("synthetic_calibration_content_mismatch")
    readiness = report["readiness"]
    if readiness.get("acceptedForProjectAuthoredSyntheticCalibration") is not True:
        raise SyntheticCalibrationError("synthetic_calibration_not_accepted")
    for unsupported_key in (
        "acceptedAsMeasuredRealFabric",
        "acceptedForLearnedMaterialInference",
        "acceptedForPrivateUserMaterialEstimation",
        "acceptedForProductionGpuMotion",
    ):
        if readiness.get(unsupported_key) is not False:
            raise SyntheticCalibrationError("unsupported_evidence_tier_promoted")


def hash_synthetic_mechanical_calibration(report: dict[str, Any]) -> str:
    return _hash_nested_blank(report, "integrity", "reportHash")


def _calibrate_preset(
    descriptor: dict[str, Any], observations: list[dict[str, Any]]
) -> dict[str, Any]:
    parameter_reports: list[dict[str, Any]] = []
    for spec in _PARAMETER_SPECS:
        parameter_observations = [
            observation for observation in observations if observation["parameter"] == spec.name
        ]
        calibration = [
            observation
            for observation in parameter_observations
            if observation["split"] == "calibration"
        ]
        holdout = [
            observation
            for observation in parameter_observations
            if observation["split"] == "holdout"
        ]
        if len(calibration) != 3 or len(holdout) != 2:
            raise SyntheticCalibrationError(f"invalid_observation_denominator:{spec.name}")
        estimate, lower, upper, calibration_loss = _fit_parameter(spec, calibration)
        true_value = float(descriptor["fields"][spec.name]["value"])
        baseline = _midpoint(spec)
        holdout_error = _normalized_rmse(spec, estimate, holdout)
        baseline_error = _normalized_rmse(spec, baseline, holdout)
        normalized_parameter_error = abs(estimate - true_value) / (spec.maximum - spec.minimum)
        record: dict[str, Any] = {
            "parameter": spec.name,
            "unit": spec.unit,
            "fixtureKind": spec.fixture_kind,
            "searchScale": spec.search_scale,
            "searchBounds": [_round(spec.minimum), _round(spec.maximum)],
            "candidateCount": _GRID_POINT_COUNT,
            "authoredSyntheticTruth": _round(true_value),
            "estimatedValue": _round(estimate),
            "gridResolutionInterval": [_round(lower), _round(upper)],
            "intervalKind": "deterministic_grid_resolution_not_statistical_confidence",
            "midpointBaselineValue": _round(baseline),
            "calibrationObservationHashes": [
                str(observation["observationHash"]) for observation in calibration
            ],
            "holdoutObservationHashes": [
                str(observation["observationHash"]) for observation in holdout
            ],
            "calibrationObjective": _round(calibration_loss),
            "normalizedParameterError": _round(normalized_parameter_error),
            "holdoutNormalizedRmse": _round(holdout_error),
            "baselineHoldoutNormalizedRmse": _round(baseline_error),
            "improvesMidpointBaseline": holdout_error < baseline_error,
            "identifiableWithinGridResolution": (upper - lower) / (spec.maximum - spec.minimum)
            <= 0.002,
            "finite": all(
                isfinite(value)
                for value in (
                    estimate,
                    lower,
                    upper,
                    calibration_loss,
                    holdout_error,
                    baseline_error,
                )
            ),
            "observations": parameter_observations,
            "recordHash": "",
        }
        record["recordHash"] = _hash_with_blank(record, "recordHash")
        parameter_reports.append(record)
    report: dict[str, Any] = {
        "presetId": descriptor["presetId"],
        "descriptorHash": descriptor["integrity"]["descriptorHash"],
        "parameterCount": len(parameter_reports),
        "parameters": parameter_reports,
        "allFinite": all(record["finite"] for record in parameter_reports),
        "allImproveMidpointBaseline": all(
            record["improvesMidpointBaseline"] for record in parameter_reports
        ),
        "recordHash": "",
    }
    report["recordHash"] = _hash_with_blank(report, "recordHash")
    return report


def _fit_parameter(
    spec: _ParameterSpec, observations: list[dict[str, Any]]
) -> tuple[float, float, float, float]:
    grid = _grid(spec)
    ranked = sorted(
        (
            _objective(spec, candidate, observations),
            candidate,
            index,
        )
        for index, candidate in enumerate(grid)
    )
    loss, estimate, index = ranked[0]
    lower = grid[max(index - 1, 0)]
    upper = grid[min(index + 1, len(grid) - 1)]
    return estimate, lower, upper, loss


def _objective(spec: _ParameterSpec, candidate: float, observations: list[dict[str, Any]]) -> float:
    errors = []
    for observation in observations:
        measured = float(observation["measuredResponse"])
        predicted = _response(spec, candidate, float(observation["stimulus"]))
        scale = max(abs(measured), 1e-12)
        errors.append(((predicted - measured) / scale) ** 2)
    return _mean(errors)


def _normalized_rmse(
    spec: _ParameterSpec, candidate: float, observations: list[dict[str, Any]]
) -> float:
    return sqrt(_objective(spec, candidate, observations))


def _response(spec: _ParameterSpec, value: float, stimulus: float) -> float:
    if spec.name == "thickness":
        return value * (1.0 - 0.24 * stimulus)
    if spec.name == "arealDensity":
        return value * 9.81 * 0.012 * stimulus
    if spec.name in {"warpStretchStiffness", "weftStretchStiffness"}:
        return 18.0 * stimulus / max(value, 1e-12)
    if spec.name == "shearStiffness":
        return 4.0 * stimulus / max(value, 1e-12)
    if spec.name == "bendStiffness":
        return 0.00028 * stimulus / max(value, 1e-12)
    if spec.name == "dampingRatio":
        return 0.08 * exp(-value * 4.0 * stimulus)
    if spec.name == "frictionCoefficient":
        return 0.08 * max(1.9 + 0.35 * stimulus - value, 0.0)
    if spec.name == "collisionClearance":
        return value + 0.0002 * stimulus
    if spec.name == "restitutionCoefficient":
        return 0.24 * stimulus * value * value
    raise SyntheticCalibrationError(f"unsupported_parameter:{spec.name}")


def _grid(spec: _ParameterSpec) -> list[float]:
    if spec.search_scale == "linear":
        step = (spec.maximum - spec.minimum) / (_GRID_POINT_COUNT - 1)
        return [spec.minimum + index * step for index in range(_GRID_POINT_COUNT)]
    log_minimum = log(spec.minimum)
    log_step = (log(spec.maximum) - log_minimum) / (_GRID_POINT_COUNT - 1)
    return [exp(log_minimum + index * log_step) for index in range(_GRID_POINT_COUNT)]


def _midpoint(spec: _ParameterSpec) -> float:
    if spec.search_scale == "log":
        return sqrt(spec.minimum * spec.maximum)
    return (spec.minimum + spec.maximum) * 0.5


def _measurement_factor(observation_id: str) -> float:
    digest = sha256(observation_id.encode("utf-8")).digest()
    signed = int.from_bytes(digest[:2], "big") / 65535.0 * 2.0 - 1.0
    return 1.0 + signed * 0.0015


def _validate_registry(registry: dict[str, Any]) -> str:
    presets = registry.get("presets")
    if not isinstance(presets, list) or len(presets) != 4:
        raise SyntheticCalibrationError("invalid_four_preset_registry")
    for descriptor in presets:
        if not isinstance(descriptor, dict):
            raise SyntheticCalibrationError("invalid_descriptor")
        validate_fabric_descriptor(descriptor)
    integrity = registry.get("integrity")
    if not isinstance(integrity, dict):
        raise SyntheticCalibrationError("missing_registry_integrity")
    registry_hash = integrity.get("registryHash")
    if not isinstance(registry_hash, str) or len(registry_hash) != 64:
        raise SyntheticCalibrationError("invalid_registry_hash")
    payload = deepcopy(registry)
    payload["integrity"]["registryHash"] = ""
    if registry_hash != sha256_bytes(canonical_dumps(payload).encode("utf-8")):
        raise SyntheticCalibrationError("registry_hash_mismatch")
    return registry_hash


def _hash_with_blank(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    payload[field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _hash_nested_blank(value: dict[str, Any], parent: str, field: str) -> str:
    payload = dict(value)
    nested = dict(cast(dict[str, Any], payload[parent]))
    nested[field] = ""
    payload[parent] = nested
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * quantile)]


def _round(value: float) -> float:
    return round(float(value), 12)
