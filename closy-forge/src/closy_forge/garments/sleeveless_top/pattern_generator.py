from __future__ import annotations

from math import ceil
from typing import Any

from .parameters import SleevelessTopParameters

GARMENT_ID = "garment.demo_sleeveless_top.reference_v1"
GARMENT_CLASS = "sleeveless_top"


def build_sleeveless_top_pattern(params: SleevelessTopParameters) -> dict[str, Any]:
    params.validate()
    target = params.target_panel_edge_length_meters
    half = params.half_chest_width_meters + params.body_ease_meters
    shoulder_half = params.shoulder_width_meters / 2
    neck_half = params.neckline_width_meters / 2
    armhole_y = params.body_length_meters - params.armhole_depth_meters
    shoulder_y = params.body_length_meters - params.shoulder_slope_meters
    panels = [
        _panel(
            "front",
            half=half,
            body_length=params.body_length_meters,
            shoulder_half=shoulder_half,
            neck_half=neck_half,
            armhole_y=armhole_y,
            shoulder_y=shoulder_y,
            neck_depth=params.front_neckline_depth_meters,
            target=target,
            seam_allowance=params.hem_allowance_meters,
        ),
        _panel(
            "back",
            half=half,
            body_length=params.body_length_meters,
            shoulder_half=shoulder_half,
            neck_half=neck_half,
            armhole_y=armhole_y,
            shoulder_y=shoulder_y,
            neck_depth=params.back_neckline_depth_meters,
            target=target,
            seam_allowance=params.hem_allowance_meters,
        ),
    ]
    return {
        "schemaVersion": 1,
        "patternVersion": "closy.sleeveless_top.pattern.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "units": "metres",
        "parameters": params.to_json(),
        "panels": panels,
        "seams": _seams(),
        "openings": _openings(),
        "provenance": {
            "sourceKind": "procedural_fixture",
            "generator": "closy.sleeveless_top.pattern.d0.v1",
            "containsUserData": False,
        },
    }


def _samples(length: float, target: float, minimum: int = 3) -> int:
    return max(minimum, int(ceil(length / target)) + 1)


def _line(
    edge_id: str, a: tuple[float, float], b: tuple[float, float], target: float
) -> dict[str, Any]:
    length = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
    return {
        "id": edge_id,
        "curve": {"type": "line", "points": [list(a), list(b)]},
        "sampleCount": _samples(length, target),
    }


def _quad(edge_id: str, points: list[tuple[float, float]], target: float) -> dict[str, Any]:
    return {
        "id": edge_id,
        "curve": {"type": "quadratic_bezier", "points": [list(point) for point in points]},
        "sampleCount": _samples(0.20, target, 5),
    }


def _cubic(edge_id: str, points: list[tuple[float, float]], target: float) -> dict[str, Any]:
    return {
        "id": edge_id,
        "curve": {"type": "cubic_bezier", "points": [list(point) for point in points]},
        "sampleCount": _samples(0.24, target, 6),
    }


def _panel(
    name: str,
    *,
    half: float,
    body_length: float,
    shoulder_half: float,
    neck_half: float,
    armhole_y: float,
    shoulder_y: float,
    neck_depth: float,
    target: float,
    seam_allowance: float,
) -> dict[str, Any]:
    return {
        "id": f"panel.sleeveless_top.{name}",
        "partId": f"part.sleeveless_top.{name}_torso",
        "semanticRole": f"{name}_torso",
        "coordinateSystem": "panel-local-metres",
        "grainDirection": [0.0, 1.0],
        "materialRegion": "material.cotton_jersey_reference_v1",
        "symmetry": (
            "panel.sleeveless_top.back" if name == "front" else "panel.sleeveless_top.front"
        ),
        "seamAllowance": seam_allowance,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
        "boundary": [
            _line(f"edge.sleeveless_top.hem.{name}", (-half, 0.0), (half, 0.0), target),
            _line(
                f"edge.sleeveless_top.side.right.{name}",
                (half, 0.0),
                (half, armhole_y),
                target,
            ),
            _cubic(
                f"edge.sleeveless_top.armhole.right.{name}",
                [
                    (half, armhole_y),
                    (half, shoulder_y - 0.07),
                    (shoulder_half + 0.015, shoulder_y - 0.04),
                    (shoulder_half, shoulder_y),
                ],
                target,
            ),
            _line(
                f"edge.sleeveless_top.shoulder.right.{name}",
                (shoulder_half, shoulder_y),
                (neck_half, body_length),
                target,
            ),
            _quad(
                f"edge.sleeveless_top.neck.{name}",
                [
                    (neck_half, body_length),
                    (0.0, body_length - neck_depth),
                    (-neck_half, body_length),
                ],
                target,
            ),
            _line(
                f"edge.sleeveless_top.shoulder.left.{name}",
                (-neck_half, body_length),
                (-shoulder_half, shoulder_y),
                target,
            ),
            _cubic(
                f"edge.sleeveless_top.armhole.left.{name}",
                [
                    (-shoulder_half, shoulder_y),
                    (-shoulder_half - 0.015, shoulder_y - 0.04),
                    (-half, shoulder_y - 0.07),
                    (-half, armhole_y),
                ],
                target,
            ),
            _line(
                f"edge.sleeveless_top.side.left.{name}",
                (-half, armhole_y),
                (-half, 0.0),
                target,
            ),
        ],
    }


def _span(panel: str, edge: str, orientation: str = "forward") -> dict[str, str]:
    return {"panelId": panel, "edgeId": edge, "orientation": orientation}


def _seams() -> list[dict[str, Any]]:
    front = "panel.sleeveless_top.front"
    back = "panel.sleeveless_top.back"
    return [
        _seam(
            "seam.sleeveless_top.shoulder.left",
            _span(front, "edge.sleeveless_top.shoulder.left.front"),
            _span(back, "edge.sleeveless_top.shoulder.left.back", "reverse"),
            10,
        ),
        _seam(
            "seam.sleeveless_top.shoulder.right",
            _span(front, "edge.sleeveless_top.shoulder.right.front"),
            _span(back, "edge.sleeveless_top.shoulder.right.back", "reverse"),
            11,
        ),
        _seam(
            "seam.sleeveless_top.side.left",
            _span(front, "edge.sleeveless_top.side.left.front"),
            _span(back, "edge.sleeveless_top.side.left.back", "reverse"),
            20,
        ),
        _seam(
            "seam.sleeveless_top.side.right",
            _span(front, "edge.sleeveless_top.side.right.front"),
            _span(back, "edge.sleeveless_top.side.right.back", "reverse"),
            21,
        ),
    ]


def _seam(
    seam_id: str,
    first: dict[str, str],
    second: dict[str, str],
    order: int,
) -> dict[str, Any]:
    return {
        "id": seam_id,
        "spans": [first, second],
        "stitchType": "lockstitch",
        "easeRatio": 1.0,
        "attachmentOrder": order,
    }


def _openings() -> list[dict[str, Any]]:
    return [
        _opening(
            "opening.sleeveless_top.neck",
            ["edge.sleeveless_top.neck.front", "edge.sleeveless_top.neck.back"],
        ),
        _opening(
            "opening.sleeveless_top.hem",
            ["edge.sleeveless_top.hem.front", "edge.sleeveless_top.hem.back"],
        ),
        _opening(
            "opening.sleeveless_top.armhole.left",
            [
                "edge.sleeveless_top.armhole.left.front",
                "edge.sleeveless_top.armhole.left.back",
            ],
        ),
        _opening(
            "opening.sleeveless_top.armhole.right",
            [
                "edge.sleeveless_top.armhole.right.front",
                "edge.sleeveless_top.armhole.right.back",
            ],
        ),
    ]


def _opening(opening_id: str, edges: list[str]) -> dict[str, Any]:
    return {
        "id": opening_id,
        "boundaryEdges": edges,
        "status": "open",
        "expectedLoopCount": 1,
    }
