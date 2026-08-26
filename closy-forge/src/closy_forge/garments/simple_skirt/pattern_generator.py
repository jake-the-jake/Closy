from __future__ import annotations

from math import ceil
from typing import Any

from .parameters import SimpleSkirtParameters

GARMENT_ID = "garment.demo_simple_skirt.reference_v1"
GARMENT_CLASS = "simple_skirt"
PREFIX = "simple_skirt"


def build_simple_skirt_pattern(params: SimpleSkirtParameters) -> dict[str, Any]:
    params.validate()
    target = params.target_panel_edge_length_meters
    return {
        "schemaVersion": 1,
        "patternVersion": "closy.simple_skirt.pattern.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "units": "metres",
        "parameters": params.to_json(),
        "panels": [_panel("front", params, target), _panel("back", params, target)],
        "seams": _seams(),
        "openings": _openings(),
        "provenance": {
            "sourceKind": "procedural_fixture",
            "generator": "closy.simple_skirt.pattern.d0.v1",
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


def _cubic(edge_id: str, points: list[tuple[float, float]], target: float) -> dict[str, Any]:
    length_hint = sum(
        ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
        for a, b in zip(points, points[1:], strict=False)
    )
    return {
        "id": edge_id,
        "curve": {"type": "cubic_bezier", "points": [list(point) for point in points]},
        "sampleCount": _samples(length_hint, target, 6),
    }


def _panel(name: str, params: SimpleSkirtParameters, target: float) -> dict[str, Any]:
    waist = params.half_waist_width_meters + params.waist_ease_meters
    hip = params.half_hip_width_meters + params.hip_ease_meters
    hem = hip + params.flare_meters
    length = params.length_meters
    hip_y = length - params.waist_to_hip_meters
    return {
        "id": f"panel.{PREFIX}.{name}",
        "partId": f"part.{PREFIX}.{name}_skirt",
        "semanticRole": f"{name}_skirt",
        "coordinateSystem": "panel-local-metres",
        "grainDirection": [0.0, 1.0],
        "materialRegion": "material.cotton_jersey_reference_v1",
        "symmetry": f"panel.{PREFIX}.{'back' if name == 'front' else 'front'}",
        "seamAllowance": params.seam_allowance_meters,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
        "boundary": [
            _line(f"edge.{PREFIX}.hem.{name}", (-hem, 0.0), (hem, 0.0), target),
            _cubic(
                f"edge.{PREFIX}.side.right.{name}",
                [(hem, 0.0), (hip, hip_y * 0.45), (hip, hip_y), (waist, length)],
                target,
            ),
            _line(
                f"edge.{PREFIX}.waist.{name}",
                (waist, length),
                (-waist, length),
                target,
            ),
            _cubic(
                f"edge.{PREFIX}.side.left.{name}",
                [(-waist, length), (-hip, hip_y), (-hip, hip_y * 0.45), (-hem, 0.0)],
                target,
            ),
        ],
    }


def _span(panel: str, edge: str, orientation: str = "forward") -> dict[str, Any]:
    return {"panelId": panel, "edgeId": edge, "orientation": orientation}


def _seams() -> list[dict[str, Any]]:
    front = f"panel.{PREFIX}.front"
    back = f"panel.{PREFIX}.back"
    return [
        {
            "id": f"seam.{PREFIX}.side.left",
            "spans": [
                _span(front, f"edge.{PREFIX}.side.left.front"),
                _span(back, f"edge.{PREFIX}.side.left.back", "reverse"),
            ],
            "stitchType": "lockstitch",
            "easeRatio": 1.0,
            "attachmentOrder": 10,
        },
        {
            "id": f"seam.{PREFIX}.side.right",
            "spans": [
                _span(front, f"edge.{PREFIX}.side.right.front"),
                _span(back, f"edge.{PREFIX}.side.right.back", "reverse"),
            ],
            "stitchType": "lockstitch",
            "easeRatio": 1.0,
            "attachmentOrder": 11,
        },
    ]


def _openings() -> list[dict[str, Any]]:
    return [
        _opening(
            f"opening.{PREFIX}.waist",
            [f"edge.{PREFIX}.waist.front", f"edge.{PREFIX}.waist.back"],
        ),
        _opening(
            f"opening.{PREFIX}.hem",
            [f"edge.{PREFIX}.hem.front", f"edge.{PREFIX}.hem.back"],
        ),
    ]


def _opening(opening_id: str, edges: list[str]) -> dict[str, Any]:
    return {
        "id": opening_id,
        "boundaryEdges": edges,
        "status": "open",
        "expectedLoopCount": 1,
    }
