from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Any, cast

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

FABRIC_DESCRIPTOR_VERSION = "closy.fabric_physics_descriptor.v1"
PRESET_REGISTRY_VERSION = "closy.fabric_preset_registry.d0.v1"
MATERIAL_SELECTION_VERSION = "closy.material_preset_selection.d0.v1"


class FabricDescriptorError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_FIELD_SPECS: dict[str, tuple[str, float, float]] = {
    "thickness": ("m", 0.0002, 0.008),
    "arealDensity": ("kg/m^2", 0.03, 0.8),
    "warpStretchStiffness": ("N/m", 20.0, 5000.0),
    "weftStretchStiffness": ("N/m", 20.0, 5000.0),
    "shearStiffness": ("N/m", 5.0, 2000.0),
    "bendStiffness": ("N*m", 0.00005, 0.05),
    "dampingRatio": ("ratio", 0.0, 0.95),
    "frictionCoefficient": ("coefficient", 0.0, 1.5),
    "collisionClearance": ("m", 0.0005, 0.03),
    "restitutionCoefficient": ("coefficient", 0.0, 1.0),
    "warpOrientation": ("degree", -180.0, 180.0),
}


def _field(value: float, unit: str, minimum: float, maximum: float) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "validRange": [minimum, maximum],
        "confidence": 0.72,
        "evidenceSource": "project_authored_public_fixture_preset",
    }


def _descriptor(
    *,
    preset_id: str,
    label: str,
    family: str,
    thickness: float,
    areal_density: float,
    warp: float,
    weft: float,
    shear: float,
    bend: float,
    damping: float,
    friction: float,
    clearance: float,
    restitution: float,
    orientation: float,
    solver_stretch: float,
    solver_weft: float,
    solver_shear: float,
    solver_bend: float,
) -> dict[str, Any]:
    descriptor: dict[str, Any] = {
        "schemaVersion": 1,
        "descriptorVersion": FABRIC_DESCRIPTOR_VERSION,
        "descriptorId": f"descriptor.{preset_id.removeprefix('material.')}",
        "presetId": preset_id,
        "label": label,
        "fabricFamily": family,
        "status": "bounded_authored_d0_not_calibrated_real_fabric",
        "fields": {
            "thickness": _field(thickness, "m", 0.0002, 0.008),
            "arealDensity": _field(areal_density, "kg/m^2", 0.03, 0.8),
            "warpStretchStiffness": _field(warp, "N/m", 20.0, 5000.0),
            "weftStretchStiffness": _field(weft, "N/m", 20.0, 5000.0),
            "shearStiffness": _field(shear, "N/m", 5.0, 2000.0),
            "bendStiffness": _field(bend, "N*m", 0.00005, 0.05),
            "dampingRatio": _field(damping, "ratio", 0.0, 0.95),
            "frictionCoefficient": _field(friction, "coefficient", 0.0, 1.5),
            "collisionClearance": _field(clearance, "m", 0.0005, 0.03),
            "restitutionCoefficient": _field(restitution, "coefficient", 0.0, 1.0),
            "warpOrientation": _field(orientation, "degree", -180.0, 180.0),
        },
        "anisotropy": {
            "enabled": abs(warp - weft) > 1e-9,
            "orientationConvention": "pattern_uv_positive_v_warp_degrees",
            "warpToWeftStiffnessRatio": _round(warp / weft),
        },
        "solverCoefficients": {
            "stretchStiffness": solver_stretch,
            "weftStretchStiffness": solver_weft,
            "shearStiffness": solver_shear,
            "bendStiffness": solver_bend,
            "dampingRatio": damping,
            "frictionCoefficient": friction,
            "collisionClearanceMeters": clearance,
            "selfCollisionThicknessMeters": thickness,
            "restitutionCoefficient": restitution,
        },
        "provenance": {
            "sourceKind": "authored_deterministic_public_fixture_preset",
            "appearanceInferenceOnly": False,
            "appearanceInferenceDisclosed": True,
            "measuredRealFabric": False,
            "learnedInferenceRun": False,
            "privateUserMaterialEstimationRun": False,
            "externalProviderRun": False,
        },
        "integrity": {"descriptorHash": ""},
    }
    descriptor["integrity"]["descriptorHash"] = hash_fabric_descriptor(descriptor)
    return descriptor


def build_material_preset_registry() -> dict[str, Any]:
    presets = [
        _descriptor(
            preset_id="material.lightweight_knit_d0_v1",
            label="Lightweight knit D0",
            family="lightweight_knit",
            thickness=0.0008,
            areal_density=0.115,
            warp=320.0,
            weft=260.0,
            shear=70.0,
            bend=0.0007,
            damping=0.12,
            friction=0.32,
            clearance=0.0045,
            restitution=0.03,
            orientation=0.0,
            solver_stretch=0.30,
            solver_weft=0.25,
            solver_shear=0.18,
            solver_bend=0.045,
        ),
        _descriptor(
            preset_id="material.cotton_jersey_d0_v1",
            label="Cotton jersey D0",
            family="cotton_jersey",
            thickness=0.0016,
            areal_density=0.16,
            warp=550.0,
            weft=420.0,
            shear=120.0,
            bend=0.0018,
            damping=0.18,
            friction=0.42,
            clearance=0.006,
            restitution=0.02,
            orientation=0.0,
            solver_stretch=0.42,
            solver_weft=0.42,
            solver_shear=0.42,
            solver_bend=0.08,
        ),
        _descriptor(
            preset_id="material.heavy_jersey_d0_v1",
            label="Heavy jersey D0",
            family="heavy_jersey",
            thickness=0.0022,
            areal_density=0.24,
            warp=780.0,
            weft=620.0,
            shear=180.0,
            bend=0.0035,
            damping=0.24,
            friction=0.50,
            clearance=0.0075,
            restitution=0.015,
            orientation=0.0,
            solver_stretch=0.55,
            solver_weft=0.48,
            solver_shear=0.40,
            solver_bend=0.13,
        ),
        _descriptor(
            preset_id="material.lightweight_woven_d0_v1",
            label="Lightweight woven D0",
            family="lightweight_woven",
            thickness=0.0009,
            areal_density=0.135,
            warp=1150.0,
            weft=980.0,
            shear=360.0,
            bend=0.0013,
            damping=0.14,
            friction=0.38,
            clearance=0.0052,
            restitution=0.025,
            orientation=0.0,
            solver_stretch=0.68,
            solver_weft=0.61,
            solver_shear=0.58,
            solver_bend=0.065,
        ),
    ]
    registry: dict[str, Any] = {
        "schemaVersion": 1,
        "registryVersion": PRESET_REGISTRY_VERSION,
        "registryId": "material_registry.tops_public_d0_v1",
        "status": "bounded_authored_presets_not_real_fabric_measurements",
        "presets": presets,
        "policy": {
            "garmentBoundary": ["tshirt", "sleeveless_top"],
            "learnedClassifierRun": False,
            "calibratedRealFabricInferenceRun": False,
            "privateUserMaterialEstimationRun": False,
        },
        "integrity": {"registryHash": ""},
    }
    registry["integrity"]["registryHash"] = _hash_without_integrity(registry)
    return registry


def validate_fabric_descriptor(descriptor: dict[str, Any]) -> None:
    if descriptor.get("schemaVersion") != 1 or descriptor.get("descriptorVersion") != (
        FABRIC_DESCRIPTOR_VERSION
    ):
        raise FabricDescriptorError("unknown_schema_version")
    fields = descriptor.get("fields")
    if not isinstance(fields, dict):
        raise FabricDescriptorError("missing_required_fields")
    for name, (unit, global_minimum, global_maximum) in _FIELD_SPECS.items():
        field = fields.get(name)
        if not isinstance(field, dict):
            raise FabricDescriptorError(f"missing_required_field:{name}")
        if field.get("unit") != unit:
            raise FabricDescriptorError(f"invalid_unit:{name}")
        valid_range = field.get("validRange")
        if not isinstance(valid_range, list) or len(valid_range) != 2:
            raise FabricDescriptorError(f"missing_valid_range:{name}")
        minimum, maximum = valid_range
        if not _finite_number(minimum) or not _finite_number(maximum):
            raise FabricDescriptorError(f"non_finite_range:{name}")
        minimum_value = float(cast(int | float, minimum))
        maximum_value = float(cast(int | float, maximum))
        if minimum_value > maximum_value:
            raise FabricDescriptorError(f"contradictory_range:{name}")
        value = field.get("value")
        if not _finite_number(value):
            raise FabricDescriptorError(f"non_finite_value:{name}")
        field_value = float(cast(int | float, value))
        if not global_minimum <= field_value <= global_maximum:
            raise FabricDescriptorError(f"value_out_of_range:{name}")
        if not minimum_value <= field_value <= maximum_value:
            raise FabricDescriptorError(f"value_outside_declared_range:{name}")
        confidence = field.get("confidence")
        if not _finite_number(confidence):
            raise FabricDescriptorError(f"invalid_confidence:{name}")
        confidence_value = float(cast(int | float, confidence))
        if not 0.0 <= confidence_value <= 1.0:
            raise FabricDescriptorError(f"invalid_confidence:{name}")
        if not field.get("evidenceSource"):
            raise FabricDescriptorError(f"missing_evidence_source:{name}")
    provenance = descriptor.get("provenance", {})
    if (
        provenance.get("appearanceInferenceOnly") is True
        and provenance.get("appearanceInferenceDisclosed") is not True
    ):
        raise FabricDescriptorError("undisclosed_appearance_only_inference")
    solver = descriptor.get("solverCoefficients")
    if not isinstance(solver, dict) or not all(_finite_number(value) for value in solver.values()):
        raise FabricDescriptorError("invalid_solver_coefficients")
    expected_hash = hash_fabric_descriptor(descriptor)
    if descriptor.get("integrity", {}).get("descriptorHash") != expected_hash:
        raise FabricDescriptorError("descriptor_hash_mismatch")


def select_material_preset(
    inputs: dict[str, Any],
    registry: dict[str, Any],
    *,
    override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    presets = list(registry.get("presets", []))
    if len(presets) != 4:
        raise FabricDescriptorError("invalid_preset_registry")
    for preset in presets:
        validate_fabric_descriptor(preset)
    observations = inputs.get("observations", {})
    profiles = {
        "material.lightweight_knit_d0_v1": {
            "massClass": "light",
            "stretchClass": "high",
            "drapeClass": "very_soft",
            "surfaceClass": "fine_knit",
        },
        "material.cotton_jersey_d0_v1": {
            "massClass": "medium",
            "stretchClass": "moderate",
            "drapeClass": "soft",
            "surfaceClass": "jersey_knit",
        },
        "material.heavy_jersey_d0_v1": {
            "massClass": "heavy",
            "stretchClass": "moderate",
            "drapeClass": "structured_soft",
            "surfaceClass": "jersey_knit",
        },
        "material.lightweight_woven_d0_v1": {
            "massClass": "light",
            "stretchClass": "low",
            "drapeClass": "structured",
            "surfaceClass": "woven",
        },
    }
    scores: list[dict[str, Any]] = []
    observed_keys = sorted(key for key in profiles[next(iter(profiles))] if key in observations)
    for preset in presets:
        preset_id = str(preset["presetId"])
        matches = [key for key in observed_keys if observations[key] == profiles[preset_id][key]]
        score = len(matches) / max(1, len(observed_keys))
        scores.append(
            {
                "presetId": preset_id,
                "score": _round(score),
                "matchedCues": matches,
                "mismatchedCues": [key for key in observed_keys if key not in matches],
                "reason": "deterministic_equal_weight_categorical_cue_match",
            }
        )
    scores.sort(key=lambda item: (-float(item["score"]), str(item["presetId"])))
    selected_id = str(scores[0]["presetId"])
    selection_mode = "deterministic_fixture_cue_score"
    override_record: dict[str, Any] = {"applied": False}
    if override is not None:
        requested = str(override.get("presetId", ""))
        if requested not in {str(preset["presetId"]) for preset in presets}:
            raise FabricDescriptorError("unknown_override_preset")
        if not all(override.get(key) for key in ("overrideId", "actor", "reason")):
            raise FabricDescriptorError("incomplete_override_record")
        selected_id = requested
        selection_mode = "explicit_override"
        override_record = {**deepcopy(override), "applied": True}
    winning_score = next(float(item["score"]) for item in scores if item["presetId"] == selected_id)
    runner_up = max(
        (float(item["score"]) for item in scores if item["presetId"] != selected_id),
        default=0.0,
    )
    confidence = "low" if len(observed_keys) < 2 or winning_score - runner_up < 0.25 else "high"
    selected_descriptor = next(
        deepcopy(preset) for preset in presets if preset["presetId"] == selected_id
    )
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "selectionVersion": MATERIAL_SELECTION_VERSION,
        "selectionId": str(inputs.get("selectionId", "material_selection.tshirt_public_d0_v1")),
        "input": deepcopy(inputs),
        "sourceRegistryHash": registry["integrity"]["registryHash"],
        "scores": scores,
        "alternatives": [item for item in scores if item["presetId"] != selected_id],
        "selection": {
            "selectedPresetId": selected_id,
            "selectionMode": selection_mode,
            "confidenceState": confidence,
            "score": _round(winning_score),
            "scoreMargin": _round(winning_score - runner_up),
            "calibratedPhysicalMeasurement": False,
            "learnedClassifierRun": False,
        },
        "override": override_record,
        "selectedDescriptor": selected_descriptor,
        "truth": {
            "presetSelectionCompleteForPublicFixture": True,
            "calibratedRealFabricInferenceRun": False,
            "privateUserMaterialEstimationRun": False,
        },
        "integrity": {"selectionHash": ""},
    }
    report["integrity"]["selectionHash"] = _hash_without_integrity(report)
    return report


def descriptor_field_value(descriptor: dict[str, Any], field_name: str) -> float:
    return float(descriptor["fields"][field_name]["value"])


def solver_material_payload(descriptor: dict[str, Any]) -> dict[str, Any]:
    validate_fabric_descriptor(descriptor)
    coefficients = descriptor["solverCoefficients"]
    warp_solver_stiffness = float(coefficients["stretchStiffness"])
    return {
        **deepcopy(descriptor),
        "surfaceDensityKgM2": descriptor_field_value(descriptor, "arealDensity"),
        "stretchStiffnessNPerM": descriptor_field_value(descriptor, "warpStretchStiffness"),
        "bendStiffnessNm": descriptor_field_value(descriptor, "bendStiffness"),
        "dampingRatio": float(coefficients["dampingRatio"]),
        "frictionCoefficient": float(coefficients["frictionCoefficient"]),
        "thicknessMeters": descriptor_field_value(descriptor, "thickness"),
        "stretchStiffness": float(coefficients["stretchStiffness"]),
        "warpStretchStiffness": warp_solver_stiffness,
        "weftStretchStiffness": float(coefficients["weftStretchStiffness"]),
        "shearStiffness": float(coefficients["shearStiffness"]),
        "bendStiffness": float(coefficients["bendStiffness"]),
        "collisionClearanceMeters": float(coefficients["collisionClearanceMeters"]),
        "selfCollisionThicknessMeters": float(coefficients["selfCollisionThicknessMeters"]),
        "restitutionCoefficient": float(coefficients["restitutionCoefficient"]),
        "clothSettleRun": True,
        "selfCollisionRun": True,
        "selfCollisionProfile": "d0_reference_vertex_triangle",
        "settleBackend": "deterministic_cpu_reference_xpbd",
    }


def hash_fabric_descriptor(descriptor: dict[str, Any]) -> str:
    payload = deepcopy(descriptor)
    payload.setdefault("integrity", {})["descriptorHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _hash_without_integrity(value: dict[str, Any]) -> str:
    payload = deepcopy(value)
    for key in payload.get("integrity", {}):
        payload["integrity"][key] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _finite_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and isfinite(float(value))


def _round(value: float) -> float:
    return round(float(value), 9)
