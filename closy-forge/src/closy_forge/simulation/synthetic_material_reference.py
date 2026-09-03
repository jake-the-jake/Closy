from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .material_physics import PRESET_REGISTRY_VERSION, validate_fabric_descriptor
from .synthetic_mechanical_calibration import (
    SYNTHETIC_CALIBRATION_VERSION,
    SyntheticCalibrationError,
    run_synthetic_mechanical_calibration,
    validate_synthetic_mechanical_calibration,
)

REFERENCE_VERSION = "closy.synthetic_material_reference.v1"


def build_synthetic_material_reference(
    registry: dict[str, Any], selected_descriptor: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any]:
    validate_synthetic_mechanical_calibration(report, registry)
    validate_fabric_descriptor(selected_descriptor)
    selected_id = selected_descriptor["presetId"]
    selected_report = next(row for row in report["presets"] if row["presetId"] == selected_id)
    selected_mapping = [
        {
            "parameter": row["parameter"],
            "unit": row["unit"],
            "fixtureKind": row["fixtureKind"],
            "estimatedValue": row["estimatedValue"],
            "normalizedParameterError": row["normalizedParameterError"],
            "holdoutNormalizedRmse": row["holdoutNormalizedRmse"],
            "identifiableWithinGridResolution": row["identifiableWithinGridResolution"],
        }
        for row in selected_report["parameters"]
    ]
    return {
        "schemaVersion": 1,
        "referenceVersion": REFERENCE_VERSION,
        "registryVersion": registry["registryVersion"],
        "registryDigest": _hash(registry),
        "calibrationVersion": report["calibrationVersion"],
        "calibrationReportDigest": report["integrity"]["reportHash"],
        "selectedPresetId": selected_id,
        "selectedDescriptor": selected_descriptor,
        "selectedDescriptorDigest": _hash(selected_descriptor),
        "selectedSolverMapping": selected_mapping,
        "selectedSolverMappingDigest": _hash(selected_mapping),
        "evidenceTier": "analytic_same_forward_model_inverse_harness",
        "measuredRealFabric": False,
        "provenancePreserved": True,
    }


def validate_or_migrate_synthetic_material_evidence(
    value: dict[str, Any], registry: dict[str, Any]
) -> dict[str, Any]:
    if value.get("referenceVersion") == REFERENCE_VERSION:
        _validate_reference(value, registry)
        return value
    if value.get("calibrationVersion") == SYNTHETIC_CALIBRATION_VERSION:
        validate_synthetic_mechanical_calibration(value, registry)
        selected = registry["presets"][0]
        return build_synthetic_material_reference(registry, selected, value)
    raise SyntheticCalibrationError("synthetic_material_evidence_version_invalid")


def _validate_reference(value: Mapping[str, Any], registry: dict[str, Any]) -> None:
    if value.get("registryVersion") != PRESET_REGISTRY_VERSION:
        raise SyntheticCalibrationError("synthetic_material_reference_registry_version_invalid")
    if value.get("registryDigest") != _hash(registry):
        raise SyntheticCalibrationError("synthetic_material_reference_registry_digest_invalid")
    descriptor = value.get("selectedDescriptor")
    if not isinstance(descriptor, dict):
        raise SyntheticCalibrationError("synthetic_material_reference_descriptor_missing")
    try:
        validate_fabric_descriptor(descriptor)
    except Exception as error:
        raise SyntheticCalibrationError(
            "synthetic_material_reference_descriptor_invalid"
        ) from error
    if value.get("selectedDescriptorDigest") != _hash(descriptor):
        raise SyntheticCalibrationError("synthetic_material_reference_descriptor_digest_invalid")
    expected = run_synthetic_mechanical_calibration(registry)
    rebuilt = build_synthetic_material_reference(registry, descriptor, expected)
    for field in (
        "calibrationVersion",
        "calibrationReportDigest",
        "selectedPresetId",
        "selectedSolverMapping",
        "selectedSolverMappingDigest",
        "evidenceTier",
        "measuredRealFabric",
        "provenancePreserved",
    ):
        if value.get(field) != rebuilt[field]:
            raise SyntheticCalibrationError("synthetic_material_reference_content_invalid")


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
