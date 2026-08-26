from __future__ import annotations

from math import ceil
from typing import Any

from .parameters import LongSleevedTopParameters

GARMENT_ID = "garment.demo_long_sleeved_top.reference_v1"
GARMENT_CLASS = "long_sleeved_top"
PREFIX = "long_sleeved_top"


def build_long_sleeved_top_pattern(params: LongSleevedTopParameters) -> dict[str, Any]:
    params.validate()
    target = params.target_panel_edge_length_meters
    panels = [
        _torso_panel("front", params, target, params.front_neckline_depth_meters),
        _torso_panel("back", params, target, params.back_neckline_depth_meters),
        _sleeve_panel("left", params, target),
        _sleeve_panel("right", params, target),
    ]
    return {
        "schemaVersion": 1,
        "patternVersion": "closy.long_sleeved_top.pattern.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "units": "metres",
        "parameters": params.to_json(),
        "panels": panels,
        "seams": _seams(params, target),
        "openings": _openings(),
        "provenance": {
            "sourceKind": "procedural_fixture",
            "generator": "closy.long_sleeved_top.pattern.d0.v1",
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


def _torso_panel(
    name: str,
    params: LongSleevedTopParameters,
    target: float,
    neck_depth: float,
) -> dict[str, Any]:
    half = params.half_chest_width_meters + params.body_ease_meters
    shoulder_half = params.shoulder_width_meters / 2
    neck_half = params.neckline_width_meters / 2
    armhole_y = params.body_length_meters - params.armhole_depth_meters
    shoulder_y = params.body_length_meters - params.shoulder_slope_meters
    panel_id = f"panel.{PREFIX}.{name}"
    return {
        "id": panel_id,
        "partId": f"part.{PREFIX}.{name}_torso",
        "semanticRole": f"{name}_torso",
        "coordinateSystem": "panel-local-metres",
        "grainDirection": [0.0, 1.0],
        "materialRegion": "material.cotton_jersey_reference_v1",
        "symmetry": f"panel.{PREFIX}.{'back' if name == 'front' else 'front'}",
        "seamAllowance": params.hem_allowance_meters,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
        "boundary": [
            _line(f"edge.{PREFIX}.hem.{name}", (-half, 0.0), (half, 0.0), target),
            _line(
                f"edge.{PREFIX}.side.right.{name}",
                (half, 0.0),
                (half, armhole_y),
                target,
            ),
            _cubic(
                f"edge.{PREFIX}.armhole.right.{name}",
                [
                    (half, armhole_y),
                    (half, shoulder_y - 0.07),
                    (shoulder_half + 0.015, shoulder_y - 0.04),
                    (shoulder_half, shoulder_y),
                ],
                target,
            ),
            _line(
                f"edge.{PREFIX}.shoulder.right.{name}",
                (shoulder_half, shoulder_y),
                (neck_half, params.body_length_meters),
                target,
            ),
            _quad(
                f"edge.{PREFIX}.neck.{name}",
                [
                    (neck_half, params.body_length_meters),
                    (0.0, params.body_length_meters - neck_depth),
                    (-neck_half, params.body_length_meters),
                ],
                target,
            ),
            _line(
                f"edge.{PREFIX}.shoulder.left.{name}",
                (-neck_half, params.body_length_meters),
                (-shoulder_half, shoulder_y),
                target,
            ),
            _cubic(
                f"edge.{PREFIX}.armhole.left.{name}",
                [
                    (-shoulder_half, shoulder_y),
                    (-shoulder_half - 0.015, shoulder_y - 0.04),
                    (-half, shoulder_y - 0.07),
                    (-half, armhole_y),
                ],
                target,
            ),
            _line(
                f"edge.{PREFIX}.side.left.{name}",
                (-half, armhole_y),
                (-half, 0.0),
                target,
            ),
        ],
    }


def _sleeve_panel(side: str, params: LongSleevedTopParameters, target: float) -> dict[str, Any]:
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
        "materialRegion": "material.cotton_jersey_reference_v1",
        "symmetry": f"panel.{PREFIX}.sleeve.{'right' if side == 'left' else 'left'}",
        "seamAllowance": params.hem_allowance_meters,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
        "boundary": [
            _line(
                f"edge.{PREFIX}.cuff.{side}",
                (-half_cuff, 0.0),
                (half_cuff, 0.0),
                target,
            ),
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


def _seams(params: LongSleevedTopParameters, target: float) -> list[dict[str, Any]]:
    front = f"panel.{PREFIX}.front"
    back = f"panel.{PREFIX}.back"
    cap_samples = 2 * _samples(0.24, target, 6)
    cap_half = cap_samples // 2
    seams = [
        _seam(
            f"seam.{PREFIX}.shoulder.left",
            _span(front, f"edge.{PREFIX}.shoulder.left.front"),
            _span(back, f"edge.{PREFIX}.shoulder.left.back", "reverse"),
            10,
        ),
        _seam(
            f"seam.{PREFIX}.shoulder.right",
            _span(front, f"edge.{PREFIX}.shoulder.right.front"),
            _span(back, f"edge.{PREFIX}.shoulder.right.back", "reverse"),
            11,
        ),
        _seam(
            f"seam.{PREFIX}.side.left",
            _span(front, f"edge.{PREFIX}.side.left.front"),
            _span(back, f"edge.{PREFIX}.side.left.back", "reverse"),
            20,
        ),
        _seam(
            f"seam.{PREFIX}.side.right",
            _span(front, f"edge.{PREFIX}.side.right.front"),
            _span(back, f"edge.{PREFIX}.side.right.back", "reverse"),
            21,
        ),
    ]
    order = 30
    for side in ("left", "right"):
        sleeve = f"panel.{PREFIX}.sleeve.{side}"
        cap = f"edge.{PREFIX}.sleeve_cap.{side}"
        front_range = (0, cap_half) if side == "left" else (cap_half, cap_samples)
        back_range = (cap_half, cap_samples) if side == "left" else (0, cap_half)
        seams.extend(
            [
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
                    order,
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
                    order + 1,
                    1.08,
                ),
                _seam(
                    f"seam.{PREFIX}.sleeve_underarm.{side}",
                    _span(sleeve, f"edge.{PREFIX}.sleeve_underarm.left.{side}"),
                    _span(
                        sleeve,
                        f"edge.{PREFIX}.sleeve_underarm.right.{side}",
                        "reverse",
                    ),
                    order + 10,
                ),
            ]
        )
        order += 2
    return seams


def _openings() -> list[dict[str, Any]]:
    return [
        _opening(
            f"opening.{PREFIX}.neck",
            [f"edge.{PREFIX}.neck.front", f"edge.{PREFIX}.neck.back"],
        ),
        _opening(
            f"opening.{PREFIX}.hem",
            [f"edge.{PREFIX}.hem.front", f"edge.{PREFIX}.hem.back"],
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
