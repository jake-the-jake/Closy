from __future__ import annotations

from math import ceil
from typing import Any

from .parameters import SimpleTrousersParameters

GARMENT_ID = "garment.demo_simple_trousers.reference_v1"
GARMENT_CLASS = "simple_trousers"
PREFIX = "simple_trousers"


def build_simple_trousers_pattern(params: SimpleTrousersParameters) -> dict[str, Any]:
    params.validate()
    target = params.target_panel_edge_length_meters
    panels = [
        _panel(face, side, params, target)
        for face in ("front", "back")
        for side in ("left", "right")
    ]
    return {
        "schemaVersion": 1,
        "patternVersion": "closy.simple_trousers.pattern.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "units": "metres",
        "parameters": params.to_json(),
        "panels": panels,
        "seams": _seams(),
        "openings": _openings(),
        "provenance": {
            "sourceKind": "procedural_fixture",
            "generator": "closy.simple_trousers.pattern.d0.v1",
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


def _panel(
    face: str,
    side: str,
    params: SimpleTrousersParameters,
    target: float,
) -> dict[str, Any]:
    sign = -1.0 if side == "left" else 1.0
    waist = params.half_waist_width_meters + params.waist_ease_meters
    hip = params.half_hip_width_meters + params.hip_ease_meters
    length = params.outseam_length_meters
    rise_y = length - params.rise_depth_meters
    extension = (
        params.front_rise_extension_meters if face == "front" else params.back_rise_extension_meters
    )
    inner_cuff_x = sign * params.leg_gap_half_width_meters
    outer_cuff_x = sign * (params.leg_gap_half_width_meters + params.leg_cuff_width_meters)
    outer_waist_x = sign * waist
    outer_hip_x = sign * hip
    crotch_x = sign * extension
    prefix = f"{PREFIX}.{face}.{side}"
    if side == "right":
        boundary = [
            _line(f"edge.{prefix}.cuff", (inner_cuff_x, 0.0), (outer_cuff_x, 0.0), target),
            _cubic(
                f"edge.{prefix}.outseam",
                [
                    (outer_cuff_x, 0.0),
                    (outer_hip_x * 0.78, rise_y * 0.45),
                    (outer_hip_x, rise_y),
                    (outer_waist_x, length),
                ],
                target,
            ),
            _line(f"edge.{prefix}.waist", (outer_waist_x, length), (0.0, length), target),
            _cubic(
                f"edge.{prefix}.rise",
                [
                    (0.0, length),
                    (0.0, length - 0.10),
                    (crotch_x, rise_y + 0.08),
                    (crotch_x, rise_y),
                ],
                target,
            ),
            _cubic(
                f"edge.{prefix}.inseam",
                [
                    (crotch_x, rise_y),
                    (inner_cuff_x * 1.7, rise_y * 0.62),
                    (inner_cuff_x, rise_y * 0.25),
                    (inner_cuff_x, 0.0),
                ],
                target,
            ),
        ]
    else:
        boundary = [
            _line(f"edge.{prefix}.cuff", (outer_cuff_x, 0.0), (inner_cuff_x, 0.0), target),
            _cubic(
                f"edge.{prefix}.inseam",
                [
                    (inner_cuff_x, 0.0),
                    (inner_cuff_x, rise_y * 0.25),
                    (crotch_x, rise_y * 0.62),
                    (crotch_x, rise_y),
                ],
                target,
            ),
            _cubic(
                f"edge.{prefix}.rise",
                [
                    (crotch_x, rise_y),
                    (crotch_x, rise_y + 0.08),
                    (0.0, length - 0.10),
                    (0.0, length),
                ],
                target,
            ),
            _line(f"edge.{prefix}.waist", (0.0, length), (outer_waist_x, length), target),
            _cubic(
                f"edge.{prefix}.outseam",
                [
                    (outer_waist_x, length),
                    (outer_hip_x, rise_y),
                    (outer_hip_x * 0.78, rise_y * 0.45),
                    (outer_cuff_x, 0.0),
                ],
                target,
            ),
        ]
    return {
        "id": f"panel.{prefix}",
        "partId": f"part.{prefix}.leg",
        "semanticRole": f"{face}_{side}_leg",
        "coordinateSystem": "panel-local-metres",
        "grainDirection": [0.0, 1.0],
        "materialRegion": "material.cotton_jersey_reference_v1",
        "symmetry": f"panel.{PREFIX}.{face}.{'right' if side == 'left' else 'left'}",
        "seamAllowance": params.seam_allowance_meters,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
        "boundary": boundary,
    }


def _span(face: str, side: str, edge: str, orientation: str = "forward") -> dict[str, Any]:
    prefix = f"{PREFIX}.{face}.{side}"
    return {
        "panelId": f"panel.{prefix}",
        "edgeId": f"edge.{prefix}.{edge}",
        "orientation": orientation,
    }


def _seams() -> list[dict[str, Any]]:
    seams: list[dict[str, Any]] = []
    order = 10
    for side in ("left", "right"):
        for edge in ("outseam", "inseam"):
            seams.append(
                {
                    "id": f"seam.{PREFIX}.{side}.{edge}",
                    "spans": [
                        _span("front", side, edge),
                        _span("back", side, edge, "reverse"),
                    ],
                    "stitchType": "lockstitch",
                    "easeRatio": 1.0,
                    "attachmentOrder": order,
                }
            )
            order += 1
    for face in ("front", "back"):
        seams.append(
            {
                "id": f"seam.{PREFIX}.{face}.rise",
                "spans": [
                    _span(face, "left", "rise"),
                    _span(face, "right", "rise", "reverse"),
                ],
                "stitchType": "lockstitch",
                "easeRatio": 1.0,
                "attachmentOrder": order,
            }
        )
        order += 1
    return seams


def _openings() -> list[dict[str, Any]]:
    return [
        _opening(
            f"opening.{PREFIX}.waist",
            [
                f"edge.{PREFIX}.{face}.{side}.waist"
                for face in ("front", "back")
                for side in ("left", "right")
            ],
        ),
        *[
            _opening(
                f"opening.{PREFIX}.cuff.{side}",
                [f"edge.{PREFIX}.{face}.{side}.cuff" for face in ("front", "back")],
            )
            for side in ("left", "right")
        ],
    ]


def _opening(opening_id: str, edges: list[str]) -> dict[str, Any]:
    return {
        "id": opening_id,
        "boundaryEdges": edges,
        "status": "open",
        "expectedLoopCount": 1,
    }
