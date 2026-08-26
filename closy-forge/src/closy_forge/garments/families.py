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
    "long_sleeved_top": {
        "id": "family.top.long_sleeved",
        "category": "top",
        "requiredParts": [
            "front_torso",
            "back_torso",
            "left_long_sleeve",
            "right_long_sleeve",
        ],
        "requiredOpenings": ["neck", "hem", "left_cuff", "right_cuff"],
        "forbiddenOpenings": ["armhole_left", "armhole_right"],
    },
    "simple_skirt": {
        "id": "family.bottom.simple_skirt",
        "category": "bottom",
        "requiredParts": ["front_skirt", "back_skirt"],
        "requiredOpenings": ["waist", "hem"],
        "forbiddenParts": ["torso", "sleeve", "trouser_leg"],
        "forbiddenOpenings": ["neck", "armhole_left", "armhole_right", "cuff"],
    },
    "simple_trousers": {
        "id": "family.bottom.simple_trousers",
        "category": "bottom",
        "requiredParts": [
            "front_left_leg",
            "front_right_leg",
            "back_left_leg",
            "back_right_leg",
        ],
        "requiredOpenings": ["waist", "left_cuff", "right_cuff"],
        "forbiddenParts": ["torso", "sleeve", "skirt"],
        "forbiddenOpenings": ["neck", "armhole_left", "armhole_right", "hem"],
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
