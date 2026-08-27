from __future__ import annotations

from math import ceil
from typing import Any

from .parameters import LayeredAsymmetricParameters

GARMENT_ID = "garment.demo_layered_asymmetric.reference_v1"
GARMENT_CLASS = "layered_asymmetric"
LAYERS = ("inner", "outer")
SIDES = ("front", "back")


def build_layered_asymmetric_pattern(params: LayeredAsymmetricParameters) -> dict[str, Any]:
    """Build a literal two-layer tunic with an asymmetric outer hem."""

    params.validate()
    target = params.target_panel_edge_length_meters
    inner_half = params.half_chest_width_meters + params.body_ease_meters
    outer_half = inner_half + params.outer_layer_ease_meters
    panels = []
    for layer in LAYERS:
        is_outer = layer == "outer"
        for side in SIDES:
            panels.append(
                _panel(
                    layer,
                    side,
                    half=outer_half if is_outer else inner_half,
                    body_length=params.body_length_meters + (0.018 if is_outer else 0.0),
                    shoulder_half=params.shoulder_width_meters / 2 + (0.008 if is_outer else 0.0),
                    neck_half=params.neckline_width_meters / 2 + (0.008 if is_outer else 0.0),
                    armhole_depth=params.armhole_depth_meters + (0.012 if is_outer else 0.0),
                    shoulder_slope=params.shoulder_slope_meters,
                    neck_depth=(
                        params.front_neckline_depth_meters
                        if side == "front"
                        else params.back_neckline_depth_meters
                    ),
                    asymmetry_drop=params.outer_asymmetry_drop_meters if is_outer else 0.0,
                    target=target,
                    seam_allowance=params.hem_allowance_meters,
                )
            )
    return {
        "schemaVersion": 1,
        "patternVersion": "closy.layered_asymmetric.pattern.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "units": "metres",
        "parameters": params.to_json(),
        "layerCount": 2,
        "asymmetric": True,
        "panels": panels,
        "seams": _seams(),
        "openings": _openings(),
        "provenance": {
            "sourceKind": "procedural_fixture",
            "generator": "closy.layered_asymmetric.pattern.d0.v1",
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
    layer: str,
    side: str,
    *,
    half: float,
    body_length: float,
    shoulder_half: float,
    neck_half: float,
    armhole_depth: float,
    shoulder_slope: float,
    neck_depth: float,
    asymmetry_drop: float,
    target: float,
    seam_allowance: float,
) -> dict[str, Any]:
    panel_id = f"panel.layered_asymmetric.{layer}.{side}"
    prefix = f"edge.layered_asymmetric.{layer}"
    armhole_y = body_length - armhole_depth
    shoulder_y = body_length - shoulder_slope
    hem_left_y = -asymmetry_drop
    return {
        "id": panel_id,
        "partId": f"part.layered_asymmetric.{layer}_{side}_torso",
        "semanticRole": f"{layer}_{side}_torso",
        "layerId": f"layer.layered_asymmetric.{layer}",
        "coordinateSystem": "panel-local-metres",
        "grainDirection": [0.0, 1.0],
        "materialRegion": (
            "material.lightweight_woven_reference_v1"
            if layer == "outer"
            else "material.cotton_jersey_reference_v1"
        ),
        "symmetry": f"panel.layered_asymmetric.{layer}.{'back' if side == 'front' else 'front'}",
        "seamAllowance": seam_allowance,
        "tessellation": {"targetEdgeLength": target},
        "confidence": {"source": "authored_deterministic_fixture", "value": 1.0},
        "boundary": [
            _line(f"{prefix}.hem.{side}", (-half, hem_left_y), (half, 0.0), target),
            _line(f"{prefix}.side.right.{side}", (half, 0.0), (half, armhole_y), target),
            _cubic(
                f"{prefix}.armhole.right.{side}",
                [
                    (half, armhole_y),
                    (half, shoulder_y - 0.07),
                    (shoulder_half + 0.015, shoulder_y - 0.04),
                    (shoulder_half, shoulder_y),
                ],
                target,
            ),
            _line(
                f"{prefix}.shoulder.right.{side}",
                (shoulder_half, shoulder_y),
                (neck_half, body_length),
                target,
            ),
            _quad(
                f"{prefix}.neck.{side}",
                [
                    (neck_half, body_length),
                    (0.0, body_length - neck_depth),
                    (-neck_half, body_length),
                ],
                target,
            ),
            _line(
                f"{prefix}.shoulder.left.{side}",
                (-neck_half, body_length),
                (-shoulder_half, shoulder_y),
                target,
            ),
            _cubic(
                f"{prefix}.armhole.left.{side}",
                [
                    (-shoulder_half, shoulder_y),
                    (-shoulder_half - 0.015, shoulder_y - 0.04),
                    (-half, shoulder_y - 0.07),
                    (-half, armhole_y),
                ],
                target,
            ),
            _line(
                f"{prefix}.side.left.{side}",
                (-half, armhole_y),
                (-half, hem_left_y),
                target,
            ),
        ],
    }


def _span(panel: str, edge: str, orientation: str = "forward") -> dict[str, str]:
    return {"panelId": panel, "edgeId": edge, "orientation": orientation}


def _seams() -> list[dict[str, Any]]:
    seams = []
    for layer_index, layer in enumerate(LAYERS):
        front = f"panel.layered_asymmetric.{layer}.front"
        back = f"panel.layered_asymmetric.{layer}.back"
        prefix = f"edge.layered_asymmetric.{layer}"
        for index, (role, side) in enumerate(
            (("shoulder", "left"), ("shoulder", "right"), ("side", "left"), ("side", "right"))
        ):
            seams.append(
                _seam(
                    f"seam.layered_asymmetric.{layer}.{role}.{side}",
                    _span(front, f"{prefix}.{role}.{side}.front"),
                    _span(back, f"{prefix}.{role}.{side}.back", "reverse"),
                    layer_index * 100 + index + 10,
                )
            )
    return seams


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


def _openings() -> list[dict[str, Any]]:
    openings = []
    for layer in LAYERS:
        prefix = f"edge.layered_asymmetric.{layer}"
        for role in ("neck", "hem"):
            openings.append(
                _opening(
                    f"opening.layered_asymmetric.{layer}.{role}",
                    [f"{prefix}.{role}.front", f"{prefix}.{role}.back"],
                )
            )
        for side in ("left", "right"):
            openings.append(
                _opening(
                    f"opening.layered_asymmetric.{layer}.armhole.{side}",
                    [f"{prefix}.armhole.{side}.front", f"{prefix}.armhole.{side}.back"],
                )
            )
    return openings


def _opening(opening_id: str, edges: list[str]) -> dict[str, Any]:
    return {"id": opening_id, "boundaryEdges": edges, "status": "open", "expectedLoopCount": 1}
