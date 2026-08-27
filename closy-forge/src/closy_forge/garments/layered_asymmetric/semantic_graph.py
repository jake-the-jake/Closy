from __future__ import annotations

from typing import Any

from closy_forge.garments.families import garment_family_entry

from .parameters import LayeredAsymmetricParameters
from .pattern_generator import GARMENT_CLASS, GARMENT_ID


def build_layered_asymmetric_semantic_graph(pattern: dict[str, Any]) -> dict[str, Any]:
    params = LayeredAsymmetricParameters(**pattern["parameters"])
    panels = [str(panel["id"]) for panel in pattern["panels"]]
    seams = [str(seam["id"]) for seam in pattern["seams"]]
    openings = [str(opening["id"]) for opening in pattern["openings"]]
    inner_panels = [panel for panel in panels if ".inner." in panel]
    outer_panels = [panel for panel in panels if ".outer." in panel]
    return {
        "schemaVersion": 1,
        "semanticVersion": "closy.layered_asymmetric.semantic_graph.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "family": garment_family_entry(GARMENT_CLASS),
        "source": {"kind": "procedural_fixture", "confidence": 1.0},
        "layering": {
            "layerCount": 2,
            "orderedLayerIds": [
                "layer.layered_asymmetric.inner",
                "layer.layered_asymmetric.outer",
            ],
            "interLayerCollisionEnabled": False,
            "interLayerCollisionStatus": "declared_order_not_yet_consumed_by_reference_solver",
            "minimumClearanceMeters": params.layer_clearance_meters,
        },
        "components": [
            {
                "id": "component.layered_asymmetric.base_layer",
                "layerId": "layer.layered_asymmetric.inner",
                "panels": inner_panels,
                "parts": [
                    "part.layered_asymmetric.inner_front_torso",
                    "part.layered_asymmetric.inner_back_torso",
                ],
                "bodyRegions": ["region.torso"],
                "layerClass": "base_layer",
                "collisionOrder": 10,
                "materialRegion": "material.cotton_jersey_reference_v1",
            },
            {
                "id": "component.layered_asymmetric.outer_asymmetric_layer",
                "layerId": "layer.layered_asymmetric.outer",
                "panels": outer_panels,
                "parts": [
                    "part.layered_asymmetric.outer_front_torso",
                    "part.layered_asymmetric.outer_back_torso",
                ],
                "bodyRegions": ["region.torso"],
                "layerClass": "outerwear",
                "collisionOrder": 20,
                "materialRegion": "material.lightweight_woven_reference_v1",
            },
        ],
        "panelMapping": {
            str(panel["id"]): str(panel["semanticRole"]) for panel in pattern["panels"]
        },
        "openings": pattern["openings"],
        "seams": pattern["seams"],
        "symmetry": [
            {
                "a": f"panel.layered_asymmetric.{layer}.front",
                "b": f"panel.layered_asymmetric.{layer}.back",
            }
            for layer in ("inner", "outer")
        ],
        "requiredIds": {
            "components": [
                "component.layered_asymmetric.base_layer",
                "component.layered_asymmetric.outer_asymmetric_layer",
            ],
            "panels": panels,
            "openings": openings,
            "seams": seams,
        },
        "materialRegions": [
            "material.cotton_jersey_reference_v1",
            "material.lightweight_woven_reference_v1",
        ],
        "provenance": {
            "sourceKind": "procedural_fixture",
            "aiInferred": False,
            "userCorrected": False,
        },
    }
