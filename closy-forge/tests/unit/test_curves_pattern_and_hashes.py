from __future__ import annotations

from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.geometry.curves import eval_curve, signed_area
from closy_forge.geometry.triangulation import panel_boundary_samples, validate_panel_boundary


def test_quadratic_curve_sampling_is_deterministic() -> None:
    curve = {"type": "quadratic_bezier", "points": [[0.0, 0.0], [0.5, 1.0], [1.0, 0.0]]}
    assert eval_curve(curve, 0.5) == (0.5, 0.5)


def test_tshirt_panels_are_closed_ccw_and_non_self_intersecting() -> None:
    pattern = build_tshirt_pattern(TShirtParameters())
    for panel in pattern["panels"]:
        samples, edge_map = panel_boundary_samples(panel)
        assert signed_area(samples) > 0
        assert edge_map
        assert validate_panel_boundary(panel) == []


def test_parameter_bounds_reject_unsupported_shapes() -> None:
    params = TShirtParameters(garment_body_length=9.0)
    try:
        params.validate()
    except ValueError as exc:
        assert "garment_body_length" in str(exc)
    else:
        raise AssertionError("out-of-bounds parameter was accepted")
