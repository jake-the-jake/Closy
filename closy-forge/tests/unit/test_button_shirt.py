from __future__ import annotations

import pytest

from closy_forge.garments.button_shirt.assembly import (
    build_constraints,
    build_simulation_mesh,
)
from closy_forge.garments.button_shirt.fitting import (
    fit_button_shirt,
    hash_button_shirt_fit_report,
)
from closy_forge.garments.button_shirt.parameters import ButtonShirtParameters
from closy_forge.garments.button_shirt.pattern_generator import build_button_shirt_pattern
from closy_forge.garments.button_shirt.semantic_graph import build_button_shirt_semantic_graph


def test_button_shirt_has_literal_split_front_openings_and_closure_pairs() -> None:
    pattern = build_button_shirt_pattern(ButtonShirtParameters())
    semantic = build_button_shirt_semantic_graph(pattern)
    mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)

    assert len(pattern["panels"]) == 5
    assert len(pattern["seams"]) == 10
    assert len(pattern["openings"]) == 5
    assert len(pattern["closures"]) == 6
    assert {panel["semanticRole"] for panel in pattern["panels"]} == {
        "front_left_torso",
        "front_right_torso",
        "back_torso",
        "left_long_sleeve",
        "right_long_sleeve",
    }
    assert {opening["id"] for opening in pattern["openings"]} == {
        "opening.button_shirt.neck",
        "opening.button_shirt.hem",
        "opening.button_shirt.front_placket",
        "opening.button_shirt.cuff.left",
        "opening.button_shirt.cuff.right",
    }
    assert all(closure["paired"] for closure in pattern["closures"])
    assert all(closure["simulationEnabled"] is False for closure in pattern["closures"])
    assert [closure["stationIndex"] for closure in pattern["closures"]] == list(range(6))
    assert len({closure["distanceFromHemMeters"] for closure in pattern["closures"]}) == 6
    assert semantic["family"]["requiredClosures"] == ["button_buttonhole"]
    assert mesh.vertex_count == 256
    assert mesh.triangle_count == 251
    assert len(constraints["constraints"]) == 81
    assert len(constraints["closures"]) == 6
    assert all(
        edge["status"] == "resolved"
        for opening in constraints["openings"]
        for edge in opening["boundaryEdges"]
    )


def test_button_shirt_bounded_fit_is_hashed_and_not_learned() -> None:
    fitted, report = fit_button_shirt(ButtonShirtParameters())

    assert fitted.body_length_meters == pytest.approx(0.68)
    assert fitted.sleeve_length_meters == pytest.approx(0.58)
    assert report["candidateCount"] == 25
    assert report["winnerLosses"]["weightedObjective"] == pytest.approx(0.00156)
    assert report["accepted"] is True
    assert report["learnedFitRun"] is False
    assert report["integrity"]["fitReportHash"] == hash_button_shirt_fit_report(report)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("button_count", 2),
        ("button_count", 5.5),
        ("placket_width_meters", 0.2),
        ("body_length_meters", float("nan")),
    ],
)
def test_button_shirt_parameters_reject_unsafe_values(field: str, value: float) -> None:
    values = ButtonShirtParameters().to_json()
    values[field] = value
    with pytest.raises(ValueError):
        ButtonShirtParameters(**values).validate()
