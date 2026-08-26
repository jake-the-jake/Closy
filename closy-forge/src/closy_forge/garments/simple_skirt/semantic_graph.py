from __future__ import annotations

from typing import Any

from closy_forge.garments.families import garment_family_entry

from .pattern_generator import GARMENT_CLASS, GARMENT_ID, PREFIX


def build_simple_skirt_semantic_graph(pattern: dict[str, Any]) -> dict[str, Any]:
    panels = [str(panel["id"]) for panel in pattern["panels"]]
    seams = [str(seam["id"]) for seam in pattern["seams"]]
    openings = [str(opening["id"]) for opening in pattern["openings"]]
    return {
        "schemaVersion": 1,
        "semanticVersion": "closy.simple_skirt.semantic_graph.d0.v1",
        "garmentId": GARMENT_ID,
        "garmentClass": GARMENT_CLASS,
        "family": garment_family_entry(GARMENT_CLASS),
        "source": {"kind": "procedural_fixture", "confidence": 1.0},
        "components": [
            {
                "id": f"component.{PREFIX}.body",
                "panels": panels,
                "parts": [f"part.{PREFIX}.front_skirt", f"part.{PREFIX}.back_skirt"],
                "bodyRegions": ["region.waist", "region.hips", "region.upper_legs"],
                "layerClass": "outerwear_lower",
                "collisionOrder": 20,
            }
        ],
        "panelMapping": {
            str(panel["id"]): str(panel["semanticRole"]) for panel in pattern["panels"]
        },
        "openings": pattern["openings"],
        "seams": pattern["seams"],
        "symmetry": [{"a": f"panel.{PREFIX}.front", "b": f"panel.{PREFIX}.back"}],
        "requiredIds": {
            "components": [f"component.{PREFIX}.body"],
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
