from __future__ import annotations

from copy import deepcopy

import pytest

from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.binding.builder import build_binding
from closy_forge.garments.tshirt.assembly import build_constraints, build_simulation_mesh
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.simulation.material_calibration import run_material_calibration
from closy_forge.simulation.material_motion_suite import build_material_motion_suite
from closy_forge.simulation.material_physics import (
    FABRIC_DESCRIPTOR_VERSION,
    FabricDescriptorError,
    build_material_preset_registry,
    hash_fabric_descriptor,
    select_material_preset,
    validate_fabric_descriptor,
)
from closy_forge.validation.validator import validate_package
from tests.helpers import build_demo, clone_package, issue_codes, read_json, write_json


def test_fabric_descriptor_contract_and_four_bounded_presets() -> None:
    registry = build_material_preset_registry()

    assert registry["registryVersion"] == "closy.fabric_preset_registry.d0.v1"
    assert [preset["presetId"] for preset in registry["presets"]] == [
        "material.lightweight_knit_d0_v1",
        "material.cotton_jersey_d0_v1",
        "material.heavy_jersey_d0_v1",
        "material.lightweight_woven_d0_v1",
    ]
    for descriptor in registry["presets"]:
        assert descriptor["descriptorVersion"] == FABRIC_DESCRIPTOR_VERSION
        validate_fabric_descriptor(descriptor)
        assert descriptor["provenance"]["measuredRealFabric"] is False
        assert descriptor["provenance"]["learnedInferenceRun"] is False


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda value: value.update({"schemaVersion": 99}), "unknown_schema_version"),
        (
            lambda value: value["fields"]["thickness"].update({"unit": "millimetre"}),
            "invalid_unit",
        ),
        (
            lambda value: value["fields"]["arealDensity"].update({"value": -1.0}),
            "value_out_of_range",
        ),
        (
            lambda value: value["fields"]["dampingRatio"].update({"value": float("nan")}),
            "non_finite_value",
        ),
        (
            lambda value: value["fields"]["frictionCoefficient"].update({"validRange": [1.0, 0.0]}),
            "contradictory_range",
        ),
        (
            lambda value: value["provenance"].update(
                {"appearanceInferenceOnly": True, "appearanceInferenceDisclosed": False}
            ),
            "undisclosed_appearance_only_inference",
        ),
    ],
)
def test_fabric_descriptor_rejects_invalid_or_undisclosed_values(mutation, code: str) -> None:
    descriptor = deepcopy(build_material_preset_registry()["presets"][1])
    mutation(descriptor)

    with pytest.raises(FabricDescriptorError, match=code):
        validate_fabric_descriptor(descriptor)


def test_selector_exposes_scores_alternatives_low_confidence_and_override() -> None:
    registry = build_material_preset_registry()
    inputs = {
        "schemaVersion": 1,
        "inputId": "material_selection.public_tshirt_d0_v1",
        "observations": {
            "massClass": "medium",
            "stretchClass": "moderate",
            "drapeClass": "soft",
            "surfaceClass": "jersey_knit",
        },
        "provenance": {
            "source": "project_authored_public_fixture_visual_cues",
            "physicalMeasurement": False,
            "learnedClassifierRun": False,
        },
    }

    selected = select_material_preset(inputs, registry)
    repeat = select_material_preset(inputs, registry)
    assert selected == repeat
    assert selected["selection"]["selectedPresetId"] == "material.cotton_jersey_d0_v1"
    assert len(selected["scores"]) == 4
    assert len(selected["alternatives"]) == 3
    assert selected["selection"]["calibratedPhysicalMeasurement"] is False

    ambiguous = deepcopy(inputs)
    ambiguous["observations"] = {}
    assert select_material_preset(ambiguous, registry)["selection"]["confidenceState"] == "low"

    overridden = select_material_preset(
        inputs,
        registry,
        override={
            "overrideId": "override.material.heavy_jersey.test_v1",
            "presetId": "material.heavy_jersey_d0_v1",
            "actor": "fixture_test",
            "reason": "exercise_explicit_override_contract",
        },
    )
    assert overridden["selection"]["selectedPresetId"] == "material.heavy_jersey_d0_v1"
    assert overridden["selection"]["selectionMode"] == "explicit_override"
    assert overridden["override"]["applied"] is True


def test_calibration_fixtures_measure_expected_parameter_response() -> None:
    registry = build_material_preset_registry()
    report = run_material_calibration(registry["presets"][1])

    assert report["calibrationVersion"] == "closy.material_calibration.d0.v1"
    assert [fixture["fixtureId"] for fixture in report["fixtures"]] == [
        "calibration.stretch_patch_v1",
        "calibration.shear_patch_v1",
        "calibration.bend_cantilever_v1",
        "calibration.damped_oscillator_v1",
        "calibration.gravity_sag_chain_v1",
        "calibration.floor_collision_v1",
    ]
    assert all(fixture["orderingObserved"] for fixture in report["fixtures"])
    assert all(fixture["withinTolerance"] for fixture in report["fixtures"])
    assert len({fixture["resultHash"] for fixture in report["fixtures"]}) == 6
    assert report["readiness"]["acceptedForD0CalibrationFixtures"] is True
    assert report["readiness"]["acceptedAsMeasuredRealFabric"] is False


def test_dynamic_material_suite_runs_solver_and_authoritative_binding() -> None:
    pattern = build_tshirt_pattern(TShirtParameters())
    rest_mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)
    render_mesh, seeds = subdivide_for_render(rest_mesh)
    binding, _manifest = build_binding(rest_mesh, render_mesh, seeds)
    avatar = avatar_contract(build_reference_avatar_mesh(), build_collision_mesh())
    registry = build_material_preset_registry()

    report, states = build_material_motion_suite(
        rest_mesh=rest_mesh,
        constraints=constraints,
        avatar_contract=avatar,
        preset_registry=registry,
        binding=binding,
    )

    assert report["suiteVersion"] == "closy.material_motion_suite.d0.v1"
    assert len(report["presets"]) == 4
    assert set(states) == {preset["presetId"] for preset in registry["presets"]}
    assert all(record["execution"]["actualSolverRun"] for record in report["presets"])
    assert all(record["binding"]["authoritativeDenseBindingRun"] for record in report["presets"])
    assert all(
        record["binding"]["reconstructedVertexCount"] == render_mesh.vertex_count
        for record in report["presets"]
    )
    assert all(record["metrics"]["nonFinitePositionCount"] == 0 for record in report["presets"])
    assert all(
        record["metrics"]["invertedOrDegenerateTriangleCount"] == 0 for record in report["presets"]
    )
    assert report["readiness"]["executedForD0FixedAvatarTshirt"] is True
    assert report["readiness"]["acceptedForD0FixedAvatarTshirt"] is False
    assert report["readiness"]["acceptedForProductionGpuMotion"] is False


def test_package_material_descriptor_corruption_fails_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = clone_package(build_demo(tmp_path), tmp_path / "bad_material_descriptor.closygarment")
    path = package / "simulation" / "material_presets.json"
    registry = read_json(path)
    descriptor = registry["presets"][0]
    descriptor["fields"]["thickness"]["unit"] = "millimetre"
    descriptor["integrity"]["descriptorHash"] = hash_fabric_descriptor(descriptor)
    write_json(path, registry)

    codes = issue_codes(validate_package(package))

    assert "file_hash_mismatch" in codes
    assert "fabric_descriptor_invalid" in codes


def test_package_material_motion_claim_corruption_fails_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = clone_package(build_demo(tmp_path), tmp_path / "bad_material_motion.closygarment")
    path = package / "reports" / "material_motion_suite.json"
    report = read_json(path)
    report["presets"][0]["metrics"]["invertedOrDegenerateTriangleCount"] = 1
    write_json(path, report)

    codes = issue_codes(validate_package(package))

    assert "file_hash_mismatch" in codes
    assert "material_motion_suite_invalid" in codes
