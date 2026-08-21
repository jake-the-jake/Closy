from __future__ import annotations

from typing import Any

from closy_forge.contracts.semantic import (
    REQUIRED_COMPONENTS,
    REQUIRED_OPENINGS,
    REQUIRED_PANELS,
    REQUIRED_SEAMS,
)


def build_semantic_graph(pattern: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "garmentId": "garment.demo_tshirt.reference_v1",
        "garmentClass": "tshirt",
        "source": {"kind": "procedural_fixture", "confidence": 1.0},
        "components": [
            {
                "id": "component.torso",
                "panels": ["panel.front", "panel.back"],
                "bodyRegions": ["region.torso"],
                "layerClass": "midlayer",
                "collisionOrder": 10,
            },
            {
                "id": "component.sleeve.left",
                "panels": ["panel.sleeve.left"],
                "bodyRegions": ["region.upper_arm.left"],
                "layerClass": "midlayer",
                "collisionOrder": 10,
            },
            {
                "id": "component.sleeve.right",
                "panels": ["panel.sleeve.right"],
                "bodyRegions": ["region.upper_arm.right"],
                "layerClass": "midlayer",
                "collisionOrder": 10,
            },
            {
                "id": "component.neck_band",
                "panels": ["panel.neck_band"],
                "bodyRegions": ["region.torso"],
                "layerClass": "trim",
                "collisionOrder": 11,
            },
        ],
        "partHierarchy": {"garment": REQUIRED_COMPONENTS},
        "panelMapping": {panel["id"]: panel["semanticRole"] for panel in pattern["panels"]},
        "openings": pattern["openings"],
        "seams": [
            {"id": seam["id"], "spans": seam["spans"], "stitchType": seam["stitchType"]}
            for seam in pattern["seams"]
        ],
        "symmetry": [
            {"a": "panel.sleeve.left", "b": "panel.sleeve.right"},
            {"a": "component.sleeve.left", "b": "component.sleeve.right"},
        ],
        "requiredIds": {
            "components": REQUIRED_COMPONENTS,
            "panels": REQUIRED_PANELS,
            "openings": REQUIRED_OPENINGS,
            "seams": REQUIRED_SEAMS,
        },
        "materialRegions": [
            "material.cotton_jersey_reference_v1",
            "material.cotton_rib_reference_v1",
        ],
        "provenance": {
            "sourceKind": "procedural_fixture",
            "aiInferred": False,
            "userCorrected": False,
        },
    }
