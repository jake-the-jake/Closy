from __future__ import annotations

import pytest

from closy_forge.garments.simple_dress.assembly import (
    build_constraints,
    build_simulation_mesh,
)
from closy_forge.garments.simple_dress.fitting import (
    fit_simple_dress,
    hash_simple_dress_fit_report,
)
from closy_forge.garments.simple_dress.parameters import SimpleDressParameters
from closy_forge.garments.simple_dress.pattern_generator import build_simple_dress_pattern
from closy_forge.garments.simple_dress.semantic_graph import (
    build_simple_dress_semantic_graph,
)


def test_simple_dress_pattern_has_literal_bodice_skirt_and_opening_semantics() -> None:
    pattern = build_simple_dress_pattern(SimpleDressParameters())
    semantic = build_simple_dress_semantic_graph(pattern)
    mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)

    assert len(pattern["panels"]) == 4
    assert len(pattern["seams"]) == 8
    assert len(pattern["openings"]) == 4
    assert {panel["semanticRole"] for panel in pattern["panels"]} == {
        "front_bodice",
        "back_bodice",
        "front_skirt",
        "back_skirt",
    }
    assert {opening["id"] for opening in pattern["openings"]} == {
        "opening.simple_dress.neck",
        "opening.simple_dress.hem",
        "opening.simple_dress.armhole.left",
        "opening.simple_dress.armhole.right",
    }
    assert "opening.simple_dress.waist" not in {opening["id"] for opening in pattern["openings"]}
    assert semantic["family"]["garmentClass"] == "simple_dress"
    assert semantic["family"]["category"] == "one_piece"
    assert semantic["family"]["requiredOpenings"] == [
        "neck",
        "armhole_left",
        "armhole_right",
        "hem",
    ]
    assert mesh.vertex_count == 193
    assert mesh.triangle_count == 189
    assert len(constraints["constraints"]) == 62
    assert all(
        edge["status"] == "resolved"
        for opening in constraints["openings"]
        for edge in opening["boundaryEdges"]
    )


def test_simple_dress_bounded_fit_is_hashed_and_not_learned() -> None:
    fitted, report = fit_simple_dress(SimpleDressParameters())

    assert fitted.skirt_length_meters == pytest.approx(0.62)
    assert fitted.half_waist_width_meters == pytest.approx(0.205)
    assert report["candidateCount"] == 25
    assert report["winnerLosses"]["weightedObjective"] == pytest.approx(0.0012)
    assert report["accepted"] is True
    assert report["learnedFitRun"] is False
    assert report["integrity"]["fitReportHash"] == hash_simple_dress_fit_report(report)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bodice_length_meters", 0.2),
        ("half_hip_width_meters", 0.1),
        ("skirt_length_meters", float("nan")),
    ],
)
def test_simple_dress_parameters_reject_unsafe_values(field: str, value: float) -> None:
    values = SimpleDressParameters().to_json()
    values[field] = value
    with pytest.raises(ValueError):
        SimpleDressParameters(**values).validate()
