from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from closy_forge.manual_provider_c3_v1.states import MOTION_STATES

from .contracts import LayerSpec


@dataclass(frozen=True)
class OutfitCase:
    case_id: str
    layers: tuple[LayerSpec, ...]
    order: tuple[tuple[str, str, float, float, bool], ...]
    intent: str


STATES = tuple(MOTION_STATES[i] for i in (0, 3, 6, 7))


def cases(root: Path) -> tuple[OutfitCase, ...]:
    def layer(name: str, family: str, variant: str = "nominal", **kwargs: object) -> LayerSpec:
        return LayerSpec(name, root / family / variant, **kwargs)  # type: ignore[arg-type]

    def ordered(case_id: str, layers: tuple[LayerSpec, ...], intent: str) -> OutfitCase:
        pairs = tuple(
            (a.layer_id, b.layer_id, 0.0, 2.5, True)
            for i, a in enumerate(layers)
            for b in layers[i + 1 :]
        )
        return OutfitCase(case_id, layers, pairs, intent)

    return (
        ordered(
            "outfit01",
            (layer("top", "tshirt", "variation1"), layer("bottom", "simple_trousers")),
            "shorter_tshirt_with_trousers_clean_contact_reference",
        ),
        ordered(
            "outfit02",
            (layer("top", "sleeveless_top"), layer("bottom", "simple_skirt")),
            "sleeveless_with_skirt_regional_waist",
        ),
        ordered(
            "outfit03",
            (
                layer("inner", "long_sleeved_top"),
                layer("outer", "jacket_outerwear", density_kg_m2=0.32, thickness_m=0.003),
            ),
            "long_sleeve_under_jacket_sleeve_contact",
        ),
        ordered(
            "outfit04",
            (layer("inner", "button_shirt"), layer("outer", "jacket_outerwear")),
            "split_front_closure_preserved",
        ),
        ordered(
            "outfit05",
            (layer("inner", "simple_dress"), layer("outer", "jacket_outerwear")),
            "dress_and_outerwear",
        ),
        ordered(
            "outfit06",
            (
                layer("inner", "layered_asymmetric", panel_prefix="panel.layered_asymmetric.inner"),
                layer("outer", "layered_asymmetric", panel_prefix="panel.layered_asymmetric.outer"),
            ),
            "actual_internal_semantic_layers",
        ),
        ordered(
            "outfit07",
            (
                layer("base", "tshirt", density_kg_m2=0.12),
                layer("middle", "button_shirt", density_kg_m2=0.2),
                layer("outer", "jacket_outerwear", density_kg_m2=0.4, thickness_m=0.004),
            ),
            "three_layer_mixed_material_projection",
        ),
        OutfitCase(
            "outfit08",
            (layer("top", "button_shirt"), layer("bottom", "simple_trousers")),
            (("top", "bottom", 0.75, 1.15, True), ("top", "bottom", 1.15, 2.5, False)),
            "local_waist_tuck_not_blanket_contact_exemption",
        ),
        ordered(
            "outfit09",
            (
                layer("inner", "sleeveless_top"),
                layer("outer", "sleeveless_top", "variation1", translation=(0, 0, -0.025)),
            ),
            "deliberate_intersection_different_tessellation_recovery_target",
        ),
        ordered(
            "outfit10",
            (
                layer("top", "sleeveless_top", "variation2", body_clearance_m=0.012),
                layer("bottom", "simple_skirt", "variation1", body_clearance_m=0.012),
            ),
            "supported_parameters_reference_body_clearance_stress",
        ),
    )
