from __future__ import annotations

from typing import Any

GARMENT_FAMILY_ONTOLOGY_VERSION = "closy.garment_family_ontology.d0.v1"

GARMENT_FAMILIES: dict[str, dict[str, Any]] = {
    "tshirt": {
        "id": "family.top.tshirt",
        "category": "top",
        "requiredParts": ["torso", "left_short_sleeve", "right_short_sleeve"],
    },
    "sleeveless_top": {
        "id": "family.top.sleeveless",
        "category": "top",
        "requiredParts": ["front_torso", "back_torso"],
        "requiredOpenings": ["neck", "hem", "armhole_left", "armhole_right"],
        "forbiddenParts": ["left_sleeve", "right_sleeve"],
        "forbiddenOpenings": ["left_cuff", "right_cuff"],
    },
}


def garment_family_entry(garment_class: str) -> dict[str, Any]:
    try:
        return {
            "ontologyVersion": GARMENT_FAMILY_ONTOLOGY_VERSION,
            "garmentClass": garment_class,
            **GARMENT_FAMILIES[garment_class],
        }
    except KeyError as exc:
        raise ValueError(f"unknown garment family: {garment_class}") from exc
