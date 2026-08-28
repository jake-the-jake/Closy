from __future__ import annotations

from dataclasses import replace

import pytest

import closy_forge.avatar_variation.fit_solver as fit_solver_module
from closy_forge.avatar_variation import (
    DECLARED_RANGES,
    FIT_THRESHOLDS,
    AvatarFitError,
    AvatarMeasurements,
    SyntheticAvatarCase,
    build_collision_samples,
    build_frozen_avatar_suite,
    fit_avatar_patterns,
    measure_collision_samples,
)


def test_frozen_avatar_suite_covers_every_boundary_and_pairwise_interaction() -> None:
    suite = build_frozen_avatar_suite()
    identifiers = [case.case_id for case in suite]

    assert len(suite) == 88
    assert len(identifiers) == len(set(identifiers))
    assert sum(case.coverage_kind == "boundary" for case in suite) == 20
    assert sum(case.coverage_kind == "pairwise" for case in suite) == 65
    assert sum(case.coverage_kind == "posture" for case in suite) == 2
    for field in DECLARED_RANGES:
        assert f"avatar.boundary.{field}.min" in identifiers
        assert f"avatar.boundary.{field}.max" in identifiers
    scalar_fields = tuple(DECLARED_RANGES)
    for left_index, left in enumerate(scalar_fields):
        for right in scalar_fields[left_index + 1 :]:
            assert f"avatar.pairwise.{left}.{right}" in identifiers
        assert f"avatar.pairwise.{left}.forward_8deg" in identifiers
        assert f"avatar.pairwise.{left}.backward_6deg" in identifiers


def test_independent_oracle_recovers_every_declared_supported_measurement() -> None:
    posture_angles = {"upright": 0.0, "forward_8deg": 8.0, "backward_6deg": -6.0}
    for case in build_frozen_avatar_suite():
        measured = measure_collision_samples(build_collision_samples(case.measurements))
        expected = case.measurements
        assert measured.height_m == pytest.approx(expected.height_m, abs=1e-9)
        assert measured.shoulder_width_m == pytest.approx(expected.shoulder_width_m, abs=1e-9)
        assert measured.chest_circumference_m == pytest.approx(
            expected.chest_circumference_m, abs=1e-9
        )
        assert measured.waist_circumference_m == pytest.approx(
            expected.waist_circumference_m, abs=1e-9
        )
        assert measured.hip_circumference_m == pytest.approx(expected.hip_circumference_m, abs=1e-9)
        assert measured.arm_length_m == pytest.approx(expected.arm_length_m, abs=1e-9)
        assert measured.leg_length_m == pytest.approx(expected.leg_length_m, abs=1e-9)
        assert measured.torso_length_m == pytest.approx(expected.torso_length_m, abs=1e-9)
        assert measured.posture_degrees == pytest.approx(posture_angles[expected.posture], abs=1e-9)


def test_every_supported_avatar_fit_passes_predeclared_gates_and_is_deterministic() -> None:
    first = [fit_avatar_patterns(case) for case in build_frozen_avatar_suite()]
    second = [fit_avatar_patterns(case) for case in build_frozen_avatar_suite()]

    assert first == second
    assert len({report.fit_digest for report in first}) == len(first)
    for report in first:
        assert report.status == "accepted_project_authored_synthetic_d0"
        assert report.fit_confidence >= FIT_THRESHOLDS["minimum_fit_confidence"]
        assert min(report.clearance.values()) >= FIT_THRESHOLDS["minimum_radial_clearance_m"]
        assert (
            max(report.opening_placement.values())
            <= FIT_THRESHOLDS["maximum_opening_placement_error_m"]
        )
        assert report.contains_private_data is False
        assert report.contains_stable_identity is False
        assert report.collision_body_linkage == "collision.synthetic_avatar_analytic_v1"
        assert report.provenance == "project_authored_synthetic_no_private_identity"


@pytest.mark.parametrize(
    ("field", "output_group", "output_field"),
    [
        ("height_m", "top_parameters", "bodyLengthMeters"),
        ("shoulder_width_m", "top_parameters", "shoulderHalfWidthMeters"),
        ("chest_circumference_m", "top_parameters", "halfChestWidthMeters"),
        ("waist_circumference_m", "trouser_parameters", "halfWaistWidthMeters"),
        ("hip_circumference_m", "trouser_parameters", "halfHipWidthMeters"),
        ("arm_length_m", "top_parameters", "sleeveLengthMeters"),
        ("leg_length_m", "trouser_parameters", "outseamLengthMeters"),
        ("torso_length_m", "top_parameters", "bodyLengthMeters"),
        ("shape_chest_depth", "top_parameters", "frontDepthAllowanceMeters"),
        ("shape_hip_depth", "trouser_parameters", "seatDepthAllowanceMeters"),
    ],
)
def test_measurement_to_pattern_updates_are_monotonic_where_expected(
    field: str, output_group: str, output_field: str
) -> None:
    minimum, maximum = DECLARED_RANGES[field]
    baseline = AvatarMeasurements()
    low = SyntheticAvatarCase(
        f"monotonic.{field}.low",
        replace(baseline, **{field: minimum}),
        "boundary",
        (field,),
    )
    high = SyntheticAvatarCase(
        f"monotonic.{field}.high",
        replace(baseline, **{field: maximum}),
        "boundary",
        (field,),
    )
    low_report = fit_avatar_patterns(low)
    high_report = fit_avatar_patterns(high)

    low_group = getattr(low_report, output_group)
    high_group = getattr(high_report, output_group)
    assert high_group[output_field] > low_group[output_field]


def test_posture_updates_front_balance_without_changing_collision_authority() -> None:
    baseline = AvatarMeasurements()
    backward = fit_avatar_patterns(
        SyntheticAvatarCase(
            "posture.backward", replace(baseline, posture="backward_6deg"), "posture", ("posture",)
        )
    )
    forward = fit_avatar_patterns(
        SyntheticAvatarCase(
            "posture.forward", replace(baseline, posture="forward_8deg"), "posture", ("posture",)
        )
    )

    assert backward.top_parameters["frontBalanceAdjustmentMeters"] < 0.0
    assert forward.top_parameters["frontBalanceAdjustmentMeters"] > 0.0
    assert backward.measurement_authority == forward.measurement_authority


def test_unsupported_extreme_and_proportion_fail_closed() -> None:
    unsupported = SyntheticAvatarCase(
        "unsupported.height",
        replace(AvatarMeasurements(), height_m=1.2),
        "boundary",
        ("height_m",),
    )
    with pytest.raises(AvatarFitError, match="unsupported_avatar_extreme:height_m"):
        fit_avatar_patterns(unsupported)

    proportion = SyntheticAvatarCase(
        "unsupported.vertical",
        replace(AvatarMeasurements(), height_m=1.62, leg_length_m=1.10, torso_length_m=0.68),
        "pairwise",
        ("height_m", "leg_length_m", "torso_length_m"),
    )
    with pytest.raises(AvatarFitError, match="unsupported_avatar_proportion:vertical_sum"):
        fit_avatar_patterns(proportion)


def test_corrupting_collision_geometry_only_is_detected_by_independent_oracle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_frozen_avatar_suite()[0]
    samples = build_collision_samples(case.measurements)
    landmarks = samples["landmarks"]
    landmarks["shoulderR"] = (0.9, landmarks["shoulderR"][1], landmarks["shoulderR"][2])
    monkeypatch.setattr(fit_solver_module, "build_collision_samples", lambda _: samples)

    with pytest.raises(AvatarFitError, match="independent_measurement_mismatch:shoulder_width_m"):
        fit_avatar_patterns(case)


def test_portable_fit_reports_have_no_identity_or_private_source_fields() -> None:
    report = fit_avatar_patterns(build_frozen_avatar_suite()[0])
    keys = {key.lower() for key in report.__dict__}

    assert "name" not in keys
    assert "email" not in keys
    assert "rawsourcesha256" not in keys
    assert "useridentity" not in keys
    assert report.contains_private_data is False
    assert report.contains_stable_identity is False
