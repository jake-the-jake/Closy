from __future__ import annotations

from math import ceil, pi
from typing import Any

from .parameters import TShirtParameters


def _samples(length: float, target: float, minimum: int = 3) -> int:
    return max(minimum, int(ceil(length / target)) + 1)


def _line(
    edge_id: str, a: tuple[float, float], b: tuple[float, float], target: float
) -> dict[str, Any]:
    return {
        "id": edge_id,
        "curve": {"type": "line", "points": [list(a), list(b)]},
        "sampleCount": _samples(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5, target),
    }


def _quad(edge_id: str, points: list[tuple[float, float]], target: float) -> dict[str, Any]:
    return {
        "id": edge_id,
        "curve": {"type": "quadratic_bezier", "points": [list(p) for p in points]},
        "sampleCount": _samples(0.20, target, 5),
    }


def _cubic(edge_id: str, points: list[tuple[float, float]], target: float) -> dict[str, Any]:
    return {
        "id": edge_id,
        "curve": {"type": "cubic_bezier", "points": [list(p) for p in points]},
        "sampleCount": _samples(0.24, target, 5),
    }


def build_tshirt_pattern(params: TShirtParameters) -> dict[str, Any]:
    params.validate()
    target = params.target_panel_edge_length
    half = params.half_chest_width + params.body_ease
    body_len = params.garment_body_length
    shoulder_half = params.shoulder_width / 2
    neck_half = params.neckline_width / 2
    armhole_y = body_len - params.armhole_depth
    shoulder_y = body_len - params.shoulder_slope

    front = _torso_panel(
        "front",
        half,
        body_len,
        shoulder_half,
        neck_half,
        armhole_y,
        shoulder_y,
        params.front_neckline_depth,
        target,
    )
    back = _torso_panel(
        "back",
        half,
        body_len,
        shoulder_half,
        neck_half,
        armhole_y,
        shoulder_y,
        params.back_neckline_depth,
        target,
    )
    sleeve_l = _sleeve_panel("left", params, target)
    sleeve_r = _sleeve_panel("right", params, target)
    band_len = (
        pi
        * (params.neckline_width + params.front_neckline_depth + params.back_neckline_depth)
        * params.neckband_length_ease_ratio
    )
    neck_band = {
        "id": "panel.neck_band",
        "semanticRole": "neck_band",
        "coordinateSystem": "panel-local-metres",
        "grainDirection": [1.0, 0.0],
        "materialRegion": "material.cotton_rib_reference_v1",
        "symmetry": None,
        "seamAllowance": params.hem_allowance,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
        "boundary": [
            _line("edge.neck_band.long.bottom", (0.0, 0.0), (band_len, 0.0), target),
            _line(
                "edge.neck_band.short.right",
                (band_len, 0.0),
                (band_len, params.neckband_width),
                target,
            ),
            _line(
                "edge.neck_band.long.top",
                (band_len, params.neckband_width),
                (0.0, params.neckband_width),
                target,
            ),
            _line("edge.neck_band.short.left", (0.0, params.neckband_width), (0.0, 0.0), target),
        ],
    }
    seams = _seams()
    openings = [
        {
            "id": "opening.neck",
            "boundaryEdges": ["edge.neck.front", "edge.neck.back"],
            "status": "open",
        },
        {"id": "opening.cuff.left", "boundaryEdges": ["edge.cuff.left"], "status": "open"},
        {"id": "opening.cuff.right", "boundaryEdges": ["edge.cuff.right"], "status": "open"},
        {
            "id": "opening.hem",
            "boundaryEdges": ["edge.hem.front", "edge.hem.back"],
            "status": "open",
        },
    ]
    return {
        "schemaVersion": 1,
        "garmentClass": "tshirt",
        "parameters": params.to_json(),
        "panels": [front, back, sleeve_l, sleeve_r, neck_band],
        "seams": seams,
        "openings": openings,
        "provenance": {"sourceKind": "procedural_fixture", "generator": "closy.tshirt.pattern.v1"},
    }


def _torso_panel(
    name: str,
    half: float,
    body_len: float,
    shoulder_half: float,
    neck_half: float,
    armhole_y: float,
    shoulder_y: float,
    neck_depth: float,
    target: float,
) -> dict[str, Any]:
    return {
        "id": f"panel.{name}",
        "semanticRole": f"{name}_torso",
        "coordinateSystem": "panel-local-metres",
        "grainDirection": [0.0, 1.0],
        "materialRegion": "material.cotton_jersey_reference_v1",
        "symmetry": "panel.back" if name == "front" else "panel.front",
        "seamAllowance": 0.025,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
        "boundary": [
            _line(f"edge.hem.{name}", (-half, 0.0), (half, 0.0), target),
            _line(f"edge.side.right.{name}", (half, 0.0), (half, armhole_y), target),
            _cubic(
                f"edge.armhole.right.{name}",
                [
                    (half, armhole_y),
                    (half, shoulder_y - 0.04),
                    (shoulder_half, shoulder_y - 0.03),
                    (shoulder_half, shoulder_y),
                ],
                target,
            ),
            _line(
                f"edge.shoulder.right.{name}",
                (shoulder_half, shoulder_y),
                (neck_half, body_len),
                target,
            ),
            _quad(
                f"edge.neck.{name}",
                [(neck_half, body_len), (0.0, body_len - neck_depth), (-neck_half, body_len)],
                target,
            ),
            _line(
                f"edge.shoulder.left.{name}",
                (-neck_half, body_len),
                (-shoulder_half, shoulder_y),
                target,
            ),
            _cubic(
                f"edge.armhole.left.{name}",
                [
                    (-shoulder_half, shoulder_y),
                    (-shoulder_half, shoulder_y - 0.03),
                    (-half, shoulder_y - 0.04),
                    (-half, armhole_y),
                ],
                target,
            ),
            _line(f"edge.side.left.{name}", (-half, armhole_y), (-half, 0.0), target),
        ],
    }


def _sleeve_panel(side: str, params: TShirtParameters, target: float) -> dict[str, Any]:
    half_open = params.sleeve_opening_width / 2
    cap_half = params.armhole_depth * 0.62
    length = params.sleeve_length
    return {
        "id": f"panel.sleeve.{side}",
        "semanticRole": f"{side}_sleeve",
        "coordinateSystem": "panel-local-metres",
        "grainDirection": [0.0, 1.0],
        "materialRegion": "material.cotton_jersey_reference_v1",
        "symmetry": "panel.sleeve.right" if side == "left" else "panel.sleeve.left",
        "seamAllowance": params.hem_allowance,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
        "boundary": [
            _line(f"edge.cuff.{side}", (-half_open, 0.0), (half_open, 0.0), target),
            _line(
                f"edge.sleeve_underarm.right.{side}", (half_open, 0.0), (cap_half, length), target
            ),
            _quad(
                f"edge.sleeve_cap.{side}",
                [(cap_half, length), (0.0, length + params.sleeve_cap_height), (-cap_half, length)],
                target,
            ),
            _line(
                f"edge.sleeve_underarm.left.{side}", (-cap_half, length), (-half_open, 0.0), target
            ),
        ],
    }


def _span(panel: str, edge: str, orientation: str = "forward") -> dict[str, str]:
    return {"panelId": panel, "edgeId": edge, "orientation": orientation}


def _seams() -> list[dict[str, Any]]:
    return [
        {
            "id": "seam.shoulder.left",
            "spans": [
                _span("panel.front", "edge.shoulder.left.front"),
                _span("panel.back", "edge.shoulder.left.back", "reverse"),
            ],
            "stitchType": "lockstitch",
            "easeRatio": 1.0,
            "attachmentOrder": 10,
        },
        {
            "id": "seam.shoulder.right",
            "spans": [
                _span("panel.front", "edge.shoulder.right.front"),
                _span("panel.back", "edge.shoulder.right.back", "reverse"),
            ],
            "stitchType": "lockstitch",
            "easeRatio": 1.0,
            "attachmentOrder": 11,
        },
        {
            "id": "seam.side.left",
            "spans": [
                _span("panel.front", "edge.side.left.front"),
                _span("panel.back", "edge.side.left.back", "reverse"),
            ],
            "stitchType": "lockstitch",
            "easeRatio": 1.0,
            "attachmentOrder": 20,
        },
        {
            "id": "seam.side.right",
            "spans": [
                _span("panel.front", "edge.side.right.front"),
                _span("panel.back", "edge.side.right.back", "reverse"),
            ],
            "stitchType": "lockstitch",
            "easeRatio": 1.0,
            "attachmentOrder": 21,
        },
        {
            "id": "seam.armhole.left.front",
            "spans": [
                _span("panel.front", "edge.armhole.left.front"),
                _span("panel.sleeve.left", "edge.sleeve_cap.left"),
            ],
            "stitchType": "lockstitch",
            "easeRatio": 1.08,
            "attachmentOrder": 30,
        },
        {
            "id": "seam.armhole.left.back",
            "spans": [
                _span("panel.back", "edge.armhole.left.back"),
                _span("panel.sleeve.left", "edge.sleeve_cap.left", "reverse"),
            ],
            "stitchType": "lockstitch",
            "easeRatio": 1.08,
            "attachmentOrder": 31,
        },
        {
            "id": "seam.armhole.right.front",
            "spans": [
                _span("panel.front", "edge.armhole.right.front"),
                _span("panel.sleeve.right", "edge.sleeve_cap.right", "reverse"),
            ],
            "stitchType": "lockstitch",
            "easeRatio": 1.08,
            "attachmentOrder": 32,
        },
        {
            "id": "seam.armhole.right.back",
            "spans": [
                _span("panel.back", "edge.armhole.right.back"),
                _span("panel.sleeve.right", "edge.sleeve_cap.right"),
            ],
            "stitchType": "lockstitch",
            "easeRatio": 1.08,
            "attachmentOrder": 33,
        },
        {
            "id": "seam.sleeve_underarm.left",
            "spans": [
                _span("panel.sleeve.left", "edge.sleeve_underarm.left.left"),
                _span("panel.sleeve.left", "edge.sleeve_underarm.right.left", "reverse"),
            ],
            "stitchType": "lockstitch",
            "easeRatio": 1.0,
            "attachmentOrder": 40,
        },
        {
            "id": "seam.sleeve_underarm.right",
            "spans": [
                _span("panel.sleeve.right", "edge.sleeve_underarm.left.right"),
                _span("panel.sleeve.right", "edge.sleeve_underarm.right.right", "reverse"),
            ],
            "stitchType": "lockstitch",
            "easeRatio": 1.0,
            "attachmentOrder": 41,
        },
        {
            "id": "seam.neck_band.closure",
            "spans": [
                _span("panel.neck_band", "edge.neck_band.short.left"),
                _span("panel.neck_band", "edge.neck_band.short.right", "reverse"),
            ],
            "stitchType": "lockstitch",
            "easeRatio": 1.0,
            "attachmentOrder": 50,
        },
        {
            "id": "seam.neck_band.attachment",
            "spans": [
                _span("panel.front", "edge.neck.front"),
                _span("panel.back", "edge.neck.back"),
                _span("panel.neck_band", "edge.neck_band.long.bottom"),
            ],
            "stitchType": "rib_attachment",
            "easeRatio": 0.92,
            "attachmentOrder": 51,
        },
    ]
