from __future__ import annotations

import pytest

from closy_forge.garments.long_sleeved_top.assembly import (
    build_constraints,
    build_simulation_mesh,
)
from closy_forge.garments.long_sleeved_top.fitting import (
    fit_long_sleeved_top,
    hash_long_sleeved_fit_report,
)
from closy_forge.garments.long_sleeved_top.parameters import LongSleevedTopParameters
from closy_forge.garments.long_sleeved_top.pattern_generator import (
    build_long_sleeved_top_pattern,
)
from closy_forge.garments.long_sleeved_top.semantic_graph import (
    build_long_sleeved_top_semantic_graph,
)


def test_long_sleeved_pattern_has_literal_sleeve_cuff_and_seam_semantics() -> None:
    pattern = build_long_sleeved_top_pattern(LongSleevedTopParameters())
    semantic = build_long_sleeved_top_semantic_graph(pattern)
    mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)

    assert len(pattern["panels"]) == 4
    assert len(pattern["seams"]) == 10
    assert {panel["semanticRole"] for panel in pattern["panels"]} == {
        "front_torso",
        "back_torso",
        "left_long_sleeve",
        "right_long_sleeve",
    }
    assert {opening["id"] for opening in pattern["openings"]} == {
        "opening.long_sleeved_top.neck",
        "opening.long_sleeved_top.hem",
        "opening.long_sleeved_top.cuff.left",
        "opening.long_sleeved_top.cuff.right",
    }
    assert semantic["family"]["garmentClass"] == "long_sleeved_top"
    assert semantic["family"]["requiredOpenings"] == [
        "neck",
        "hem",
        "left_cuff",
        "right_cuff",
    ]
    assert mesh.vertex_count == 208
    assert mesh.triangle_count == 200
    assert len(constraints["constraints"]) == 90
    assert all(
        edge["status"] == "resolved"
        for opening in constraints["openings"]
        for edge in opening["boundaryEdges"]
    )


def test_long_sleeved_bounded_fit_is_hashed_and_not_learned() -> None:
    fitted, report = fit_long_sleeved_top(LongSleevedTopParameters())

    assert fitted.body_length_meters == pytest.approx(0.66)
    assert fitted.sleeve_length_meters == pytest.approx(0.56)
    assert report["candidateCount"] == 25
    assert report["winnerLosses"]["weightedObjective"] == pytest.approx(0.00187)
    assert report["accepted"] is True
    assert report["learnedFitRun"] is False
    assert report["integrity"]["fitReportHash"] == hash_long_sleeved_fit_report(report)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sleeve_length_meters", 0.2),
        ("cuff_width_meters", 0.3),
        ("body_length_meters", float("nan")),
    ],
)
def test_long_sleeved_parameters_reject_unsafe_values(field: str, value: float) -> None:
    values = LongSleevedTopParameters().to_json()
    values[field] = value
    with pytest.raises(ValueError):
        LongSleevedTopParameters(**values).validate()
