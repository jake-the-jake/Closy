from __future__ import annotations

import pytest

from closy_forge.garments.simple_skirt.assembly import (
    build_constraints,
    build_simulation_mesh,
)
from closy_forge.garments.simple_skirt.fitting import (
    fit_simple_skirt,
    hash_simple_skirt_fit_report,
)
from closy_forge.garments.simple_skirt.parameters import SimpleSkirtParameters
from closy_forge.garments.simple_skirt.pattern_generator import build_simple_skirt_pattern
from closy_forge.garments.simple_skirt.semantic_graph import build_simple_skirt_semantic_graph


def test_simple_skirt_pattern_has_literal_waist_hem_and_side_seams() -> None:
    pattern = build_simple_skirt_pattern(SimpleSkirtParameters())
    semantic = build_simple_skirt_semantic_graph(pattern)
    mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)

    assert len(pattern["panels"]) == 2
    assert len(pattern["seams"]) == 2
    assert {panel["semanticRole"] for panel in pattern["panels"]} == {
        "front_skirt",
        "back_skirt",
    }
    assert {opening["id"] for opening in pattern["openings"]} == {
        "opening.simple_skirt.waist",
        "opening.simple_skirt.hem",
    }
    assert semantic["family"]["garmentClass"] == "simple_skirt"
    assert semantic["family"]["category"] == "bottom"
    assert semantic["family"]["requiredOpenings"] == ["waist", "hem"]
    assert mesh.vertex_count == 104
    assert mesh.triangle_count == 100
    assert len(constraints["constraints"]) == 28
    assert all(
        edge["status"] == "resolved"
        for opening in constraints["openings"]
        for edge in opening["boundaryEdges"]
    )


def test_simple_skirt_bounded_fit_is_hashed_and_not_learned() -> None:
    fitted, report = fit_simple_skirt(SimpleSkirtParameters())

    assert fitted.length_meters == pytest.approx(0.56)
    assert fitted.half_waist_width_meters == pytest.approx(0.205)
    assert report["candidateCount"] == 25
    assert report["winnerLosses"]["weightedObjective"] == pytest.approx(0.00122)
    assert report["accepted"] is True
    assert report["learnedFitRun"] is False
    assert report["integrity"]["fitReportHash"] == hash_simple_skirt_fit_report(report)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("length_meters", 0.2),
        ("half_hip_width_meters", 0.1),
        ("flare_meters", float("nan")),
    ],
)
def test_simple_skirt_parameters_reject_unsafe_values(field: str, value: float) -> None:
    values = SimpleSkirtParameters().to_json()
    values[field] = value
    with pytest.raises(ValueError):
        SimpleSkirtParameters(**values).validate()
