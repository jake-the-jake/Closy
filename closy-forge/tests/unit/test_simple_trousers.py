from __future__ import annotations

import pytest

from closy_forge.garments.simple_trousers.assembly import (
    build_constraints,
    build_simulation_mesh,
)
from closy_forge.garments.simple_trousers.fitting import (
    fit_simple_trousers,
    hash_simple_trousers_fit_report,
)
from closy_forge.garments.simple_trousers.parameters import SimpleTrousersParameters
from closy_forge.garments.simple_trousers.pattern_generator import build_simple_trousers_pattern
from closy_forge.garments.simple_trousers.semantic_graph import (
    build_simple_trousers_semantic_graph,
)


def test_simple_trousers_pattern_has_literal_leg_rise_and_opening_semantics() -> None:
    pattern = build_simple_trousers_pattern(SimpleTrousersParameters())
    semantic = build_simple_trousers_semantic_graph(pattern)
    mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)

    assert len(pattern["panels"]) == 4
    assert len(pattern["seams"]) == 6
    assert len(pattern["openings"]) == 3
    assert {panel["semanticRole"] for panel in pattern["panels"]} == {
        "front_left_leg",
        "front_right_leg",
        "back_left_leg",
        "back_right_leg",
    }
    assert {opening["id"] for opening in pattern["openings"]} == {
        "opening.simple_trousers.waist",
        "opening.simple_trousers.cuff.left",
        "opening.simple_trousers.cuff.right",
    }
    assert semantic["family"]["garmentClass"] == "simple_trousers"
    assert semantic["family"]["category"] == "bottom"
    assert semantic["family"]["requiredOpenings"] == ["waist", "left_cuff", "right_cuff"]
    assert mesh.vertex_count == 186
    assert mesh.triangle_count == 182
    assert len(constraints["constraints"]) == 75
    assert all(
        edge["status"] == "resolved"
        for opening in constraints["openings"]
        for edge in opening["boundaryEdges"]
    )


def test_simple_trousers_bounded_fit_is_hashed_and_not_learned() -> None:
    fitted, report = fit_simple_trousers(SimpleTrousersParameters())

    assert fitted.outseam_length_meters == pytest.approx(0.98)
    assert fitted.half_waist_width_meters == pytest.approx(0.195)
    assert report["candidateCount"] == 25
    assert report["winnerLosses"]["weightedObjective"] == pytest.approx(0.00138)
    assert report["accepted"] is True
    assert report["learnedFitRun"] is False
    assert report["integrity"]["fitReportHash"] == hash_simple_trousers_fit_report(report)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("outseam_length_meters", 0.4),
        ("half_hip_width_meters", 0.1),
        ("leg_cuff_width_meters", float("nan")),
    ],
)
def test_simple_trousers_parameters_reject_unsafe_values(field: str, value: float) -> None:
    values = SimpleTrousersParameters().to_json()
    values[field] = value
    with pytest.raises(ValueError):
        SimpleTrousersParameters(**values).validate()
