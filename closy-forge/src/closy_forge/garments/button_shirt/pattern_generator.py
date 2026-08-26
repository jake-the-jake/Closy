from __future__ import annotations

from math import ceil
from typing import Any

from .parameters import ButtonShirtParameters

GARMENT_ID = "garment.demo_button_shirt.reference_v1"
GARMENT_CLASS = "button_shirt"
PREFIX = "button_shirt"
MATERIAL_REGION = "material.lightweight_woven_reference_v1"


def build_button_shirt_pattern(params: ButtonShirtParameters) -> dict[str, Any]:
    params.validate()
    target = params.target_panel_edge_length_meters
    panels = [
        _front_panel("left", params, target),
        _front_panel("right", params, target),
        _back_panel(params, target),
        _sleeve_panel("left", params, target),
        _sleeve_panel("right", params, target),
    ]
    closures = _closures(params)
    return {
        "schemaVersion": 1,
        "patternVersion": "closy.button_shirt.pattern.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "units": "metres",
        "parameters": params.to_json(),
        "panels": panels,
        "seams": _seams(params, target),
        "openings": _openings(),
        "closures": closures,
        "provenance": {
            "sourceKind": "procedural_fixture",
            "generator": "closy.button_shirt.pattern.d0.v1",
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


def _quad(
    edge_id: str,
    points: list[tuple[float, float]],
    target: float,
    *,
    sample_count: int | None = None,
) -> dict[str, Any]:
    return {
        "id": edge_id,
        "curve": {"type": "quadratic_bezier", "points": [list(point) for point in points]},
        "sampleCount": sample_count or _samples(0.20, target, 5),
    }


def _cubic(edge_id: str, points: list[tuple[float, float]], target: float) -> dict[str, Any]:
    return {
        "id": edge_id,
        "curve": {"type": "cubic_bezier", "points": [list(point) for point in points]},
        "sampleCount": _samples(0.24, target, 6),
    }


def _front_panel(side: str, params: ButtonShirtParameters, target: float) -> dict[str, Any]:
    half = params.half_chest_width_meters + params.body_ease_meters
    shoulder_half = params.shoulder_width_meters / 2
    neck_half = params.neckline_width_meters / 2
    length = params.body_length_meters
    armhole_y = length - params.armhole_depth_meters
    shoulder_y = length - params.shoulder_slope_meters
    neck_center_y = length - params.front_neckline_depth_meters
    panel_id = f"panel.{PREFIX}.front.{side}"
    common = {
        "id": panel_id,
        "partId": f"part.{PREFIX}.front_{side}_torso",
        "semanticRole": f"front_{side}_torso",
        "coordinateSystem": "panel-local-metres",
        "grainDirection": [0.0, 1.0],
        "materialRegion": MATERIAL_REGION,
        "symmetry": f"panel.{PREFIX}.front.{'right' if side == 'left' else 'left'}",
        "seamAllowance": params.seam_allowance_meters,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
    }
    if side == "left":
        boundary = [
            _line(f"edge.{PREFIX}.hem.front.left", (-half, 0.0), (0.0, 0.0), target),
            _line(f"edge.{PREFIX}.placket.left", (0.0, 0.0), (0.0, neck_center_y), target),
            _quad(
                f"edge.{PREFIX}.neck.front.left",
                [(0.0, neck_center_y), (-neck_half * 0.46, neck_center_y), (-neck_half, length)],
                target,
            ),
            _line(
                f"edge.{PREFIX}.shoulder.left.front",
                (-neck_half, length),
                (-shoulder_half, shoulder_y),
                target,
            ),
            _cubic(
                f"edge.{PREFIX}.armhole.left.front",
                [
                    (-shoulder_half, shoulder_y),
                    (-shoulder_half - 0.015, shoulder_y - 0.04),
                    (-half, shoulder_y - 0.07),
                    (-half, armhole_y),
                ],
                target,
            ),
            _line(f"edge.{PREFIX}.side.left.front", (-half, armhole_y), (-half, 0.0), target),
        ]
    else:
        boundary = [
            _line(f"edge.{PREFIX}.hem.front.right", (0.0, 0.0), (half, 0.0), target),
            _line(f"edge.{PREFIX}.side.right.front", (half, 0.0), (half, armhole_y), target),
            _cubic(
                f"edge.{PREFIX}.armhole.right.front",
                [
                    (half, armhole_y),
                    (half, shoulder_y - 0.07),
                    (shoulder_half + 0.015, shoulder_y - 0.04),
                    (shoulder_half, shoulder_y),
                ],
                target,
            ),
            _line(
                f"edge.{PREFIX}.shoulder.right.front",
                (shoulder_half, shoulder_y),
                (neck_half, length),
                target,
            ),
            _quad(
                f"edge.{PREFIX}.neck.front.right",
                [(neck_half, length), (neck_half * 0.46, neck_center_y), (0.0, neck_center_y)],
                target,
            ),
            _line(f"edge.{PREFIX}.placket.right", (0.0, neck_center_y), (0.0, 0.0), target),
        ]
    return {**common, "boundary": boundary}


def _back_panel(params: ButtonShirtParameters, target: float) -> dict[str, Any]:
    half = params.half_chest_width_meters + params.body_ease_meters
    shoulder_half = params.shoulder_width_meters / 2
    neck_half = params.neckline_width_meters / 2
    length = params.body_length_meters
    armhole_y = length - params.armhole_depth_meters
    shoulder_y = length - params.shoulder_slope_meters
    return {
        "id": f"panel.{PREFIX}.back",
        "partId": f"part.{PREFIX}.back_torso",
        "semanticRole": "back_torso",
        "coordinateSystem": "panel-local-metres",
        "grainDirection": [0.0, 1.0],
        "materialRegion": MATERIAL_REGION,
        "symmetry": "self_bilateral",
        "seamAllowance": params.seam_allowance_meters,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
        "boundary": [
            _line(f"edge.{PREFIX}.hem.back", (-half, 0.0), (half, 0.0), target),
            _line(f"edge.{PREFIX}.side.right.back", (half, 0.0), (half, armhole_y), target),
            _cubic(
                f"edge.{PREFIX}.armhole.right.back",
                [
                    (half, armhole_y),
                    (half, shoulder_y - 0.07),
                    (shoulder_half + 0.015, shoulder_y - 0.04),
                    (shoulder_half, shoulder_y),
                ],
                target,
            ),
            _line(
                f"edge.{PREFIX}.shoulder.right.back",
                (shoulder_half, shoulder_y),
                (neck_half, length),
                target,
            ),
            _quad(
                f"edge.{PREFIX}.neck.back",
                [
                    (neck_half, length),
                    (0.0, length - params.back_neckline_depth_meters),
                    (-neck_half, length),
                ],
                target,
            ),
            _line(
                f"edge.{PREFIX}.shoulder.left.back",
                (-neck_half, length),
                (-shoulder_half, shoulder_y),
                target,
            ),
            _cubic(
                f"edge.{PREFIX}.armhole.left.back",
                [
                    (-shoulder_half, shoulder_y),
                    (-shoulder_half - 0.015, shoulder_y - 0.04),
                    (-half, shoulder_y - 0.07),
                    (-half, armhole_y),
                ],
                target,
            ),
            _line(f"edge.{PREFIX}.side.left.back", (-half, armhole_y), (-half, 0.0), target),
        ],
    }


def _sleeve_panel(side: str, params: ButtonShirtParameters, target: float) -> dict[str, Any]:
    half_cuff = params.cuff_width_meters / 2
    cap_half = params.armhole_depth_meters * 0.62
    length = params.sleeve_length_meters
    cap_samples = 2 * _samples(0.24, target, 6)
    return {
        "id": f"panel.{PREFIX}.sleeve.{side}",
        "partId": f"part.{PREFIX}.{side}_long_sleeve",
        "semanticRole": f"{side}_long_sleeve",
        "coordinateSystem": "panel-local-metres",
        "grainDirection": [0.0, 1.0],
        "materialRegion": MATERIAL_REGION,
        "symmetry": f"panel.{PREFIX}.sleeve.{'right' if side == 'left' else 'left'}",
        "seamAllowance": params.seam_allowance_meters,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
        "boundary": [
            _line(f"edge.{PREFIX}.cuff.{side}", (-half_cuff, 0.0), (half_cuff, 0.0), target),
            _line(
                f"edge.{PREFIX}.sleeve_underarm.right.{side}",
                (half_cuff, 0.0),
                (cap_half, length),
                target,
            ),
            _quad(
                f"edge.{PREFIX}.sleeve_cap.{side}",
                [
                    (cap_half, length),
                    (0.0, length + params.sleeve_cap_height_meters),
                    (-cap_half, length),
                ],
                target,
                sample_count=cap_samples,
            ),
            _line(
                f"edge.{PREFIX}.sleeve_underarm.left.{side}",
                (-cap_half, length),
                (-half_cuff, 0.0),
                target,
            ),
        ],
    }


def _span(
    panel: str,
    edge: str,
    orientation: str = "forward",
    sample_range: tuple[int, int] | None = None,
    partition_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"panelId": panel, "edgeId": edge, "orientation": orientation}
    if sample_range is not None:
        payload["sampleRange"] = list(sample_range)
    if partition_id is not None:
        payload["partitionId"] = partition_id
    return payload


def _seam(
    seam_id: str, first: dict[str, Any], second: dict[str, Any], order: int, ease: float = 1.0
) -> dict[str, Any]:
    return {
        "id": seam_id,
        "spans": [first, second],
        "stitchType": "lockstitch",
        "easeRatio": ease,
        "attachmentOrder": order,
    }


def _seams(params: ButtonShirtParameters, target: float) -> list[dict[str, Any]]:
    back = f"panel.{PREFIX}.back"
    cap_samples = 2 * _samples(0.24, target, 6)
    cap_half = cap_samples // 2
    seams: list[dict[str, Any]] = []
    for offset, side in enumerate(("left", "right")):
        front = f"panel.{PREFIX}.front.{side}"
        sleeve = f"panel.{PREFIX}.sleeve.{side}"
        cap = f"edge.{PREFIX}.sleeve_cap.{side}"
        front_range = (0, cap_half) if side == "left" else (cap_half, cap_samples)
        back_range = (cap_half, cap_samples) if side == "left" else (0, cap_half)
        seams.extend(
            [
                _seam(
                    f"seam.{PREFIX}.shoulder.{side}",
                    _span(front, f"edge.{PREFIX}.shoulder.{side}.front"),
                    _span(back, f"edge.{PREFIX}.shoulder.{side}.back", "reverse"),
                    10 + offset,
                ),
                _seam(
                    f"seam.{PREFIX}.side.{side}",
                    _span(front, f"edge.{PREFIX}.side.{side}.front"),
                    _span(back, f"edge.{PREFIX}.side.{side}.back", "reverse"),
                    20 + offset,
                ),
                _seam(
                    f"seam.{PREFIX}.armhole.{side}.front",
                    _span(front, f"edge.{PREFIX}.armhole.{side}.front"),
                    _span(
                        sleeve,
                        cap,
                        "reverse" if side == "right" else "forward",
                        front_range,
                        f"sleeve_cap.{side}.front",
                    ),
                    30 + offset * 2,
                    1.08,
                ),
                _seam(
                    f"seam.{PREFIX}.armhole.{side}.back",
                    _span(back, f"edge.{PREFIX}.armhole.{side}.back"),
                    _span(
                        sleeve,
                        cap,
                        "reverse" if side == "left" else "forward",
                        back_range,
                        f"sleeve_cap.{side}.back",
                    ),
                    31 + offset * 2,
                    1.08,
                ),
                _seam(
                    f"seam.{PREFIX}.sleeve_underarm.{side}",
                    _span(sleeve, f"edge.{PREFIX}.sleeve_underarm.left.{side}"),
                    _span(sleeve, f"edge.{PREFIX}.sleeve_underarm.right.{side}", "reverse"),
                    40 + offset,
                ),
            ]
        )
    return seams


def _openings() -> list[dict[str, Any]]:
    return [
        _opening(
            f"opening.{PREFIX}.neck",
            [
                f"edge.{PREFIX}.neck.front.left",
                f"edge.{PREFIX}.neck.front.right",
                f"edge.{PREFIX}.neck.back",
            ],
        ),
        _opening(
            f"opening.{PREFIX}.hem",
            [
                f"edge.{PREFIX}.hem.front.left",
                f"edge.{PREFIX}.hem.front.right",
                f"edge.{PREFIX}.hem.back",
            ],
        ),
        _opening(
            f"opening.{PREFIX}.front_placket",
            [f"edge.{PREFIX}.placket.left", f"edge.{PREFIX}.placket.right"],
        ),
        _opening(f"opening.{PREFIX}.cuff.left", [f"edge.{PREFIX}.cuff.left"]),
        _opening(f"opening.{PREFIX}.cuff.right", [f"edge.{PREFIX}.cuff.right"]),
    ]


def _opening(opening_id: str, edges: list[str]) -> dict[str, Any]:
    return {
        "id": opening_id,
        "boundaryEdges": edges,
        "status": "open",
        "expectedLoopCount": 1,
    }


def _closures(params: ButtonShirtParameters) -> list[dict[str, Any]]:
    bottom = params.bottom_button_clearance_meters
    top = (
        params.body_length_meters
        - params.front_neckline_depth_meters
        - params.top_button_clearance_meters
    )
    spacing = (top - bottom) / (params.button_count - 1)
    records = []
    for index in range(params.button_count):
        distance = round(bottom + spacing * index, 9)
        records.append(
            {
                "id": f"closure.{PREFIX}.button.{index + 1:02d}",
                "type": "button_buttonhole",
                "status": "paired_openable",
                "stationIndex": index,
                "stationCount": params.button_count,
                "distanceFromHemMeters": distance,
                "button": {
                    "panelId": f"panel.{PREFIX}.front.right",
                    "edgeId": f"edge.{PREFIX}.placket.right",
                    "distanceFromHemMeters": distance,
                },
                "buttonhole": {
                    "panelId": f"panel.{PREFIX}.front.left",
                    "edgeId": f"edge.{PREFIX}.placket.left",
                    "distanceFromHemMeters": distance,
                },
                "paired": True,
                "simulationEnabled": False,
            }
        )
    return records
