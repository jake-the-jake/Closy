from __future__ import annotations

from typing import Any

from closy_forge.garments.families import garment_family_entry

from .pattern_generator import GARMENT_CLASS, GARMENT_ID, MATERIAL_REGION, PREFIX


def build_button_shirt_semantic_graph(pattern: dict[str, Any]) -> dict[str, Any]:
    panels = [str(panel["id"]) for panel in pattern["panels"]]
    seams = [str(seam["id"]) for seam in pattern["seams"]]
    openings = [str(opening["id"]) for opening in pattern["openings"]]
    closures = [str(closure["id"]) for closure in pattern["closures"]]
    return {
        "schemaVersion": 1,
        "semanticVersion": "closy.button_shirt.semantic_graph.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "family": garment_family_entry(GARMENT_CLASS),
        "source": {"kind": "procedural_fixture", "confidence": 1.0},
        "components": [
            {
                "id": f"component.{PREFIX}.torso",
                "panels": [
                    f"panel.{PREFIX}.front.left",
                    f"panel.{PREFIX}.front.right",
                    f"panel.{PREFIX}.back",
                ],
                "parts": [
                    f"part.{PREFIX}.front_left_torso",
                    f"part.{PREFIX}.front_right_torso",
                    f"part.{PREFIX}.back_torso",
                ],
                "bodyRegions": ["region.torso"],
                "layerClass": "midlayer",
                "collisionOrder": 10,
            },
            _sleeve_component("left"),
            _sleeve_component("right"),
        ],
        "panelMapping": {
            str(panel["id"]): str(panel["semanticRole"]) for panel in pattern["panels"]
        },
        "openings": pattern["openings"],
        "seams": pattern["seams"],
        "closures": pattern["closures"],
        "symmetry": [
            {"a": f"panel.{PREFIX}.front.left", "b": f"panel.{PREFIX}.front.right"},
            {"a": f"panel.{PREFIX}.sleeve.left", "b": f"panel.{PREFIX}.sleeve.right"},
        ],
        "requiredIds": {
            "components": [
                f"component.{PREFIX}.torso",
                f"component.{PREFIX}.sleeve.left",
                f"component.{PREFIX}.sleeve.right",
            ],
            "panels": panels,
            "openings": openings,
            "seams": seams,
            "closures": closures,
        },
        "materialRegions": [MATERIAL_REGION],
        "provenance": {
            "sourceKind": "procedural_fixture",
            "aiInferred": False,
            "userCorrected": False,
        },
    }


def _sleeve_component(side: str) -> dict[str, Any]:
    return {
        "id": f"component.{PREFIX}.sleeve.{side}",
        "panels": [f"panel.{PREFIX}.sleeve.{side}"],
        "parts": [f"part.{PREFIX}.{side}_long_sleeve"],
        "bodyRegions": [f"region.arm.{side}"],
        "layerClass": "midlayer",
        "collisionOrder": 11,
    }
