from __future__ import annotations

import importlib
import math
from dataclasses import dataclass
from typing import Any


class FamilyInputError(ValueError):
    """Typed rejection before numerical compilation."""


@dataclass(frozen=True)
class FamilySpec:
    name: str
    parameter_class: str
    pattern_function: str
    semantic_function: str
    variations: tuple[dict[str, float | int], dict[str, float | int]]

    def module(self, name: str) -> Any:
        return importlib.import_module(f"closy_forge.garments.{self.name}.{name}")

    def parameters(self, changes: dict[str, float | int] | None = None) -> Any:
        try:
            value = getattr(self.module("parameters"), self.parameter_class)(**(changes or {}))
            if any(isinstance(v, bool) or not math.isfinite(v) for v in value.to_json().values()):
                raise ValueError("nonfinite_or_boolean_parameter")
            value.validate()
            return value
        except (TypeError, ValueError) as error:
            raise FamilyInputError(f"invalid_parameters:{self.name}:{error}") from error


# Ordinary development cases declared before evaluation; ranges remain owned by V1 schemas.
FAMILIES = (
    FamilySpec(
        "tshirt",
        "TShirtParameters",
        "build_tshirt_pattern",
        "build_semantic_graph",
        (
            {"garment_body_length": 0.62, "half_chest_width": 0.33},
            {"garment_body_length": 0.77, "sleeve_length": 0.30},
        ),
    ),
    FamilySpec(
        "sleeveless_top",
        "SleevelessTopParameters",
        "build_sleeveless_top_pattern",
        "build_sleeveless_top_semantic_graph",
        ({"body_length_meters": 0.60}, {"armhole_depth_meters": 0.24}),
    ),
    FamilySpec(
        "long_sleeved_top",
        "LongSleevedTopParameters",
        "build_long_sleeved_top_pattern",
        "build_long_sleeved_top_semantic_graph",
        (
            {"sleeve_length_meters": 0.64, "shoulder_width_meters": 0.64},
            {"sleeve_length_meters": 0.48, "cuff_width_meters": 0.13},
        ),
    ),
    FamilySpec(
        "simple_skirt",
        "SimpleSkirtParameters",
        "build_simple_skirt_pattern",
        "build_simple_skirt_semantic_graph",
        ({"length_meters": 0.60}, {"flare_meters": 0.12}),
    ),
    FamilySpec(
        "simple_trousers",
        "SimpleTrousersParameters",
        "build_simple_trousers_pattern",
        "build_simple_trousers_semantic_graph",
        (
            {"leg_gap_half_width_meters": 0.055, "leg_cuff_width_meters": 0.16},
            {"outseam_length_meters": 1.04, "leg_gap_half_width_meters": 0.025},
        ),
    ),
    FamilySpec(
        "simple_dress",
        "SimpleDressParameters",
        "build_simple_dress_pattern",
        "build_simple_dress_semantic_graph",
        ({"skirt_length_meters": 0.64}, {"body_ease_meters": 0.055}),
    ),
    FamilySpec(
        "button_shirt",
        "ButtonShirtParameters",
        "build_button_shirt_pattern",
        "build_button_shirt_semantic_graph",
        (
            {"placket_width_meters": 0.035, "button_count": 5},
            {"sleeve_length_meters": 0.64, "top_button_clearance_meters": 0.10},
        ),
    ),
    FamilySpec(
        "jacket_outerwear",
        "JacketOuterwearParameters",
        "build_jacket_outerwear_pattern",
        "build_jacket_outerwear_semantic_graph",
        (
            {"facing_width_meters": 0.065, "sleeve_length_meters": 0.65},
            {"facing_width_meters": 0.04, "cuff_width_meters": 0.14},
        ),
    ),
    FamilySpec(
        "layered_asymmetric",
        "LayeredAsymmetricParameters",
        "build_layered_asymmetric_pattern",
        "build_layered_asymmetric_semantic_graph",
        (
            {"body_length_meters": 0.68, "outer_asymmetry_drop_meters": 0.14},
            {"half_chest_width_meters": 0.30, "outer_layer_ease_meters": 0.04},
        ),
    ),
)


def family_spec(family: str) -> FamilySpec:
    for spec in FAMILIES:
        if spec.name == family:
            return spec
    raise FamilyInputError(f"unsupported_family:{family}")
