from __future__ import annotations

from typing import Any

from closy_forge.garments.families import garment_family_entry

from .pattern_generator import GARMENT_CLASS, GARMENT_ID


def build_sleeveless_top_semantic_graph(pattern: dict[str, Any]) -> dict[str, Any]:
    panels = [str(panel["id"]) for panel in pattern["panels"]]
    seams = [str(seam["id"]) for seam in pattern["seams"]]
    openings = [str(opening["id"]) for opening in pattern["openings"]]
    return {
        "schemaVersion": 1,
        "semanticVersion": "closy.sleeveless_top.semantic_graph.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "family": garment_family_entry(GARMENT_CLASS),
        "source": {"kind": "procedural_fixture", "confidence": 1.0},
        "components": [
            {
                "id": "component.sleeveless_top.torso",
                "panels": panels,
                "parts": [
                    "part.sleeveless_top.front_torso",
                    "part.sleeveless_top.back_torso",
                ],
                "bodyRegions": ["region.torso"],
                "layerClass": "midlayer",
                "collisionOrder": 10,
            }
        ],
        "panelMapping": {
            str(panel["id"]): str(panel["semanticRole"]) for panel in pattern["panels"]
        },
        "openings": pattern["openings"],
        "seams": pattern["seams"],
        "symmetry": [{"a": "panel.sleeveless_top.front", "b": "panel.sleeveless_top.back"}],
        "requiredIds": {
            "components": ["component.sleeveless_top.torso"],
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
