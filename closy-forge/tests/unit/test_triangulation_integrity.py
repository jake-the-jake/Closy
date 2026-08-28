from __future__ import annotations

import pytest

from closy_forge.garments.assembly import build_seam_constraints
from closy_forge.garments.simple_trousers.parameters import SimpleTrousersParameters
from closy_forge.garments.simple_trousers.pattern_generator import build_simple_trousers_pattern
from closy_forge.geometry.curves import signed_area
from closy_forge.geometry.triangulation import (
    panel_boundary_samples,
    triangulate_panel,
    triangulate_simple_polygon,
)

POLYGONS = [
    [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0)],
    [
        (0.0, 0.0),
        (3.0, 0.0),
        (3.0, 3.0),
        (1.8, 3.0),
        (1.8, 0.4),
        (1.2, 0.4),
        (1.2, 3.0),
        (0.0, 3.0),
    ],
    [(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (2.01, 2.0), (2.0, 0.02), (1.99, 2.0), (0.0, 2.0)],
]


@pytest.mark.parametrize("points", POLYGONS)
@pytest.mark.parametrize("scale", [1e-3, 1.0, 1e3])
def test_ear_clipping_covers_convex_concave_and_narrow_notch_polygons(
    points: list[tuple[float, float]], scale: float
) -> None:
    scaled = [(x * scale, y * scale) for x, y in points]
    triangles = triangulate_simple_polygon(scaled)
    assert len(triangles) == len(scaled) - 2
    assert _triangle_area(scaled, triangles) == pytest.approx(abs(signed_area(scaled)), rel=1e-10)
    triangle_edges = {tuple(sorted(edge)) for triangle in triangles for edge in _edges(triangle)}
    assert {
        tuple(sorted((index, (index + 1) % len(scaled)))) for index in range(len(scaled))
    } <= triangle_edges
    assert triangles == triangulate_simple_polygon(scaled)


def test_winding_reversal_preserves_geometric_triangulation_area() -> None:
    points = POLYGONS[1]
    forward = triangulate_simple_polygon(points)
    reversed_points = list(reversed(points))
    backward = triangulate_simple_polygon(reversed_points)
    assert _triangle_area(points, forward) == pytest.approx(
        _triangle_area(reversed_points, backward)
    )


@pytest.mark.parametrize(
    ("points", "error"),
    [
        ([(0.0, 0.0), (1.0, 0.0), (1.0, 0.0), (0.0, 1.0)], "repeated"),
        ([(0.0, 0.0), (2.0, 2.0), (0.0, 2.0), (2.0, 0.0)], "self_intersects"),
    ],
)
def test_invalid_polygons_fail_closed(points: list[tuple[float, float]], error: str) -> None:
    with pytest.raises(ValueError, match=error):
        triangulate_simple_polygon(points)


def test_trousers_panels_preserve_every_boundary_and_cover_polygon() -> None:
    pattern = build_simple_trousers_pattern(SimpleTrousersParameters())
    for panel in pattern["panels"]:
        points, edge_map = panel_boundary_samples(panel)
        mesh, rendered_edge_map = triangulate_panel(
            panel, "lower.front" if ".front." in panel["id"] else "lower.back"
        )
        assert rendered_edge_map == edge_map
        assert len(mesh.vertices) == len(points)
        assert len(mesh.triangles) == len(points) - 2
        assert _triangle_area(points, mesh.triangles) == pytest.approx(
            abs(signed_area(points)), rel=1e-10
        )
        triangle_edges = {
            tuple(sorted(edge)) for triangle in mesh.triangles for edge in _edges(triangle)
        }
        for indices in edge_map.values():
            assert indices[0] != indices[-1]
            assert all(
                tuple(sorted(pair)) in triangle_edges
                for pair in zip(indices, indices[1:], strict=False)
            )


def test_full_span_seam_mapping_preserves_both_endpoints_without_truncation() -> None:
    pattern = {
        "panels": [
            {
                "id": "panel.a",
                "boundary": [
                    {
                        "id": "edge.a",
                        "curve": {
                            "type": "polyline",
                            "points": [[0.0, 0.0], [0.5, 0.0], [1.0, 0.0]],
                        },
                        "sampleCount": 3,
                    }
                ],
            },
            {
                "id": "panel.b",
                "boundary": [
                    {
                        "id": "edge.b",
                        "curve": {
                            "type": "polyline",
                            "points": [
                                [0.0, 0.0],
                                [0.25, 0.0],
                                [0.5, 0.0],
                                [0.75, 0.0],
                                [1.0, 0.0],
                            ],
                        },
                        "sampleCount": 5,
                    }
                ],
            },
        ],
        "seams": [
            {
                "id": "seam.test",
                "spans": [
                    {"panelId": "panel.a", "edgeId": "edge.a", "orientation": "forward"},
                    {"panelId": "panel.b", "edgeId": "edge.b", "orientation": "forward"},
                ],
                "stitchType": "lockstitch",
                "easeRatio": 1.1,
            }
        ],
        "openings": [],
    }
    constraints = build_seam_constraints(
        pattern,
        {"panel.a": {"edge.a": [0, 1, 2]}, "panel.b": {"edge.b": [0, 1, 2, 3, 4]}},
    )
    records = constraints["constraints"]
    assert constraints["constraintModel"] == "full_span_seam_mapping_v2"
    assert len(records) == 5
    assert [record["spanA"]["vertexIndex"] for record in records] == [0, 0, 1, 1, 2]
    assert [record["spanB"]["vertexIndex"] for record in records] == [0, 1, 2, 3, 4]
    assert records[0]["mapping"]["parameter"] == 0.0
    assert records[-1]["mapping"]["parameter"] == 1.0
    assert records[1]["spanA"]["nextVertexIndex"] == 1
    assert records[1]["spanA"]["interpolationWeight"] == 0.5
    assert all(record["restEaseRatio"] == 1.1 for record in records)


def _triangle_area(
    points: list[tuple[float, float]], triangles: list[tuple[int, int, int]]
) -> float:
    return sum(
        abs(
            (points[b][0] - points[a][0]) * (points[c][1] - points[a][1])
            - (points[b][1] - points[a][1]) * (points[c][0] - points[a][0])
        )
        * 0.5
        for a, b, c in triangles
    )


def _edges(triangle: tuple[int, int, int]) -> tuple[tuple[int, int], ...]:
    a, b, c = triangle
    return ((a, b), (b, c), (c, a))
