from __future__ import annotations

import pytest

from closy_forge.garments.jacket_outerwear.assembly import (
    build_constraints,
    build_simulation_mesh,
)
from closy_forge.garments.jacket_outerwear.fitting import (
    fit_jacket_outerwear,
    hash_jacket_outerwear_fit_report,
)
from closy_forge.garments.jacket_outerwear.parameters import JacketOuterwearParameters
from closy_forge.garments.jacket_outerwear.pattern_generator import (
    build_jacket_outerwear_pattern,
)
from closy_forge.garments.jacket_outerwear.semantic_graph import (
    build_jacket_outerwear_semantic_graph,
)


def test_jacket_outerwear_has_split_front_facings_and_outer_layer_semantics() -> None:
    pattern = build_jacket_outerwear_pattern(JacketOuterwearParameters())
    semantic = build_jacket_outerwear_semantic_graph(pattern)
    mesh, edge_maps = build_simulation_mesh(pattern)
    constraints = build_constraints(pattern, edge_maps)

    assert len(pattern["panels"]) == 7
    assert len(pattern["seams"]) == 12
    assert {panel["semanticRole"] for panel in pattern["panels"]} == {
        "front_left_torso",
        "front_right_torso",
        "back_torso",
        "left_long_sleeve",
        "right_long_sleeve",
        "front_left_facing",
        "front_right_facing",
    }
    assert {opening["id"] for opening in pattern["openings"]} == {
        "opening.jacket_outerwear.neck",
        "opening.jacket_outerwear.hem",
        "opening.jacket_outerwear.front",
        "opening.jacket_outerwear.cuff.left",
        "opening.jacket_outerwear.cuff.right",
    }
    assert semantic["family"]["garmentClass"] == "jacket_outerwear"
    assert semantic["family"]["requiredOpenings"] == [
        "neck",
        "hem",
        "front",
        "left_cuff",
        "right_cuff",
    ]
    components = {item["id"]: item for item in semantic["components"]}
    assert components["component.jacket_outerwear.torso"]["collisionOrder"] == 30
    assert components["component.jacket_outerwear.sleeve.left"]["collisionOrder"] == 31
    assert components["component.jacket_outerwear.facing.left"]["collisionOrder"] == 29
    assert mesh.vertex_count == 324
    assert mesh.triangle_count == 310
    assert len(constraints["constraints"]) == 124
    assert not any(
        "facing.inner" in str(span["edgeId"]) for seam in pattern["seams"] for span in seam["spans"]
    )
    assert all(
        edge["status"] == "resolved"
        for opening in constraints["openings"]
        for edge in opening["boundaryEdges"]
    )


def test_jacket_outerwear_bounded_fit_is_hashed_and_not_learned() -> None:
    fitted, report = fit_jacket_outerwear(JacketOuterwearParameters())

    assert fitted.body_length_meters == pytest.approx(0.72)
    assert fitted.sleeve_length_meters == pytest.approx(0.60)
    assert report["candidateCount"] == 25
    assert report["winnerLosses"]["weightedObjective"] == pytest.approx(0.00156)
    assert report["accepted"] is True
    assert report["learnedFitRun"] is False
    assert report["integrity"]["fitReportHash"] == hash_jacket_outerwear_fit_report(report)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sleeve_length_meters", 0.2),
        ("cuff_width_meters", 0.3),
        ("facing_width_meters", 0.2),
        ("body_length_meters", float("nan")),
    ],
)
def test_jacket_outerwear_parameters_reject_unsafe_values(field: str, value: float) -> None:
    values = JacketOuterwearParameters().to_json()
    values[field] = value
    with pytest.raises(ValueError):
        JacketOuterwearParameters(**values).validate()
