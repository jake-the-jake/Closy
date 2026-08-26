from __future__ import annotations

from math import ceil
from typing import Any

from .parameters import SimpleDressParameters

GARMENT_ID = "garment.demo_simple_dress.reference_v1"
GARMENT_CLASS = "simple_dress"
PREFIX = "simple_dress"


def build_simple_dress_pattern(params: SimpleDressParameters) -> dict[str, Any]:
    params.validate()
    target = params.target_panel_edge_length_meters
    panels = []
    for face in ("front", "back"):
        panels.append(_bodice(face, params, target))
        panels.append(_skirt(face, params, target))
    return {
        "schemaVersion": 1,
        "patternVersion": "closy.simple_dress.pattern.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "units": "metres",
        "parameters": params.to_json(),
        "panels": panels,
        "seams": _seams(),
        "openings": _openings(),
        "provenance": {
            "sourceKind": "procedural_fixture",
            "generator": "closy.simple_dress.pattern.d0.v1",
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


def _curve(
    edge_id: str, curve_type: str, points: list[tuple[float, float]], target: float
) -> dict[str, Any]:
    length_hint = sum(
        ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
        for a, b in zip(points, points[1:], strict=False)
    )
    return {
        "id": edge_id,
        "curve": {"type": curve_type, "points": [list(point) for point in points]},
        "sampleCount": _samples(length_hint, target, 5 if curve_type == "quadratic_bezier" else 6),
    }


def _bodice(face: str, params: SimpleDressParameters, target: float) -> dict[str, Any]:
    chest = params.half_chest_width_meters + params.body_ease_meters
    waist = params.half_waist_width_meters + params.waist_ease_meters
    shoulder = params.shoulder_width_meters / 2
    neck = params.neckline_width_meters / 2
    length = params.bodice_length_meters
    armhole_y = length - params.armhole_depth_meters
    shoulder_y = length - params.shoulder_slope_meters
    neck_depth = (
        params.front_neckline_depth_meters if face == "front" else params.back_neckline_depth_meters
    )
    base = f"{PREFIX}.{face}.bodice"
    return {
        "id": f"panel.{base}",
        "partId": f"part.{base}",
        "semanticRole": f"{face}_bodice",
        "coordinateSystem": "panel-local-metres",
        "grainDirection": [0.0, 1.0],
        "materialRegion": "material.cotton_jersey_reference_v1",
        "symmetry": f"panel.{PREFIX}.{'back' if face == 'front' else 'front'}.bodice",
        "seamAllowance": params.seam_allowance_meters,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
        "boundary": [
            _line(f"edge.{base}.waist", (-waist, 0.0), (waist, 0.0), target),
            _line(f"edge.{base}.side.right", (waist, 0.0), (chest, armhole_y), target),
            _curve(
                f"edge.{base}.armhole.right",
                "cubic_bezier",
                [
                    (chest, armhole_y),
                    (chest, shoulder_y - 0.07),
                    (shoulder + 0.015, shoulder_y - 0.04),
                    (shoulder, shoulder_y),
                ],
                target,
            ),
            _line(f"edge.{base}.shoulder.right", (shoulder, shoulder_y), (neck, length), target),
            _curve(
                f"edge.{base}.neck",
                "quadratic_bezier",
                [(neck, length), (0.0, length - neck_depth), (-neck, length)],
                target,
            ),
            _line(f"edge.{base}.shoulder.left", (-neck, length), (-shoulder, shoulder_y), target),
            _curve(
                f"edge.{base}.armhole.left",
                "cubic_bezier",
                [
                    (-shoulder, shoulder_y),
                    (-shoulder - 0.015, shoulder_y - 0.04),
                    (-chest, shoulder_y - 0.07),
                    (-chest, armhole_y),
                ],
                target,
            ),
            _line(f"edge.{base}.side.left", (-chest, armhole_y), (-waist, 0.0), target),
        ],
    }


def _skirt(face: str, params: SimpleDressParameters, target: float) -> dict[str, Any]:
    waist = params.half_waist_width_meters + params.waist_ease_meters
    hip = params.half_hip_width_meters + params.hip_ease_meters
    hem = hip + params.skirt_flare_meters
    length = params.skirt_length_meters
    base = f"{PREFIX}.{face}.skirt"
    return {
        "id": f"panel.{base}",
        "partId": f"part.{base}",
        "semanticRole": f"{face}_skirt",
        "coordinateSystem": "panel-local-metres",
        "grainDirection": [0.0, 1.0],
        "materialRegion": "material.cotton_jersey_reference_v1",
        "symmetry": f"panel.{PREFIX}.{'back' if face == 'front' else 'front'}.skirt",
        "seamAllowance": params.seam_allowance_meters,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
        "boundary": [
            _line(f"edge.{base}.hem", (-hem, 0.0), (hem, 0.0), target),
            _curve(
                f"edge.{base}.side.right",
                "cubic_bezier",
                [(hem, 0.0), (hip, length * 0.42), (hip, length * 0.72), (waist, length)],
                target,
            ),
            _line(f"edge.{base}.waist", (waist, length), (-waist, length), target),
            _curve(
                f"edge.{base}.side.left",
                "cubic_bezier",
                [(-waist, length), (-hip, length * 0.72), (-hip, length * 0.42), (-hem, 0.0)],
                target,
            ),
        ],
    }


def _span(panel: str, edge: str, orientation: str = "forward") -> dict[str, str]:
    return {"panelId": panel, "edgeId": edge, "orientation": orientation}


def _seam(
    seam_id: str, first: dict[str, str], second: dict[str, str], order: int
) -> dict[str, Any]:
    return {
        "id": seam_id,
        "spans": [first, second],
        "stitchType": "lockstitch",
        "easeRatio": 1.0,
        "attachmentOrder": order,
    }


def _seams() -> list[dict[str, Any]]:
    seams: list[dict[str, Any]] = []
    order = 10
    for region in ("shoulder", "side"):
        for side in ("left", "right"):
            seams.append(
                _seam(
                    f"seam.{PREFIX}.bodice.{region}.{side}",
                    _span(
                        f"panel.{PREFIX}.front.bodice",
                        f"edge.{PREFIX}.front.bodice.{region}.{side}",
                    ),
                    _span(
                        f"panel.{PREFIX}.back.bodice",
                        f"edge.{PREFIX}.back.bodice.{region}.{side}",
                        "reverse",
                    ),
                    order,
                )
            )
            order += 1
    for face in ("front", "back"):
        seams.append(
            _seam(
                f"seam.{PREFIX}.waist.{face}",
                _span(f"panel.{PREFIX}.{face}.bodice", f"edge.{PREFIX}.{face}.bodice.waist"),
                _span(
                    f"panel.{PREFIX}.{face}.skirt", f"edge.{PREFIX}.{face}.skirt.waist", "reverse"
                ),
                order,
            )
        )
        order += 1
    for side in ("left", "right"):
        seams.append(
            _seam(
                f"seam.{PREFIX}.skirt.side.{side}",
                _span(f"panel.{PREFIX}.front.skirt", f"edge.{PREFIX}.front.skirt.side.{side}"),
                _span(
                    f"panel.{PREFIX}.back.skirt", f"edge.{PREFIX}.back.skirt.side.{side}", "reverse"
                ),
                order,
            )
        )
        order += 1
    return seams


def _openings() -> list[dict[str, Any]]:
    return [
        _opening(
            f"opening.{PREFIX}.neck",
            [f"edge.{PREFIX}.{face}.bodice.neck" for face in ("front", "back")],
        ),
        _opening(
            f"opening.{PREFIX}.hem",
            [f"edge.{PREFIX}.{face}.skirt.hem" for face in ("front", "back")],
        ),
        *[
            _opening(
                f"opening.{PREFIX}.armhole.{side}",
                [f"edge.{PREFIX}.{face}.bodice.armhole.{side}" for face in ("front", "back")],
            )
            for side in ("left", "right")
        ],
    ]


def _opening(opening_id: str, edges: list[str]) -> dict[str, Any]:
    return {"id": opening_id, "boundaryEdges": edges, "status": "open", "expectedLoopCount": 1}
