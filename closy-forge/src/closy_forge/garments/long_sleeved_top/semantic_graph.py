from __future__ import annotations

from typing import Any

from closy_forge.garments.families import garment_family_entry

from .pattern_generator import GARMENT_CLASS, GARMENT_ID, PREFIX


def build_long_sleeved_top_semantic_graph(pattern: dict[str, Any]) -> dict[str, Any]:
    panels = [str(panel["id"]) for panel in pattern["panels"]]
    seams = [str(seam["id"]) for seam in pattern["seams"]]
    openings = [str(opening["id"]) for opening in pattern["openings"]]
    return {
        "schemaVersion": 1,
        "semanticVersion": "closy.long_sleeved_top.semantic_graph.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "family": garment_family_entry(GARMENT_CLASS),
        "source": {"kind": "procedural_fixture", "confidence": 1.0},
        "components": [
            {
                "id": f"component.{PREFIX}.torso",
                "panels": [f"panel.{PREFIX}.front", f"panel.{PREFIX}.back"],
                "parts": [f"part.{PREFIX}.front_torso", f"part.{PREFIX}.back_torso"],
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
        "symmetry": [
            {"a": f"panel.{PREFIX}.front", "b": f"panel.{PREFIX}.back"},
            {
                "a": f"panel.{PREFIX}.sleeve.left",
                "b": f"panel.{PREFIX}.sleeve.right",
            },
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
        },
        "materialRegions": ["material.cotton_jersey_reference_v1"],
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
