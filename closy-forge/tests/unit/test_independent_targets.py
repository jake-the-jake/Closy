from __future__ import annotations

from closy_forge.inspection.independent_targets import (
    build_layered_asymmetric_target,
    build_simple_trousers_target,
)
from closy_forge.package_io.hashing import sha256_bytes


def test_hard_family_targets_are_deterministic_and_sealed() -> None:
    for builder in (build_simple_trousers_target, build_layered_asymmetric_target):
        first = builder(101)
        second = builder(101)

        assert first == second
        assert len(first.program_hash) == 64
        assert first.capture_measurements
        assert all(view.width == 128 and view.height == 160 for view in first.views.values())
        assert all(
            any(view.rgba[offset + 3] for offset in range(0, len(view.rgba), 4))
            for view in first.views.values()
        )


def test_target_program_identity_changes_without_exposing_parameters() -> None:
    first = build_simple_trousers_target(101)
    second = build_simple_trousers_target(102)

    assert first.program_hash != second.program_hash
    assert first.capture_measurements != second.capture_measurements
    assert {label: sha256_bytes(view.rgba) for label, view in first.views.items()} != {
        label: sha256_bytes(view.rgba) for label, view in second.views.items()
    }
    assert not hasattr(first, "target_parameters")


def test_layered_target_exposes_inner_layer_in_required_views() -> None:
    target = build_layered_asymmetric_target(101)

    assert set(target.views) == {
        "front",
        "back",
        "left_three_quarter",
        "right_three_quarter",
    }
    for view in target.views.values():
        colors = {tuple(view.rgba[offset : offset + 4]) for offset in range(0, len(view.rgba), 4)}
        assert (42, 96, 210, 255) in colors
        assert (60, 124, 232, 255) in colors
