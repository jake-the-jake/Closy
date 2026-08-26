from __future__ import annotations

from typing import Any, TypeAlias

from closy_forge.garments.vertical_slice.appearance import (
    AppearanceBundle,
    AppearanceSpec,
    build_appearance_bundle,
)
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.visual_understanding.raster_parser import TORSO_RGBA

ButtonShirtAppearanceBundle: TypeAlias = AppearanceBundle
APPEARANCE_SPEC = AppearanceSpec(
    appearance_version="closy.button_shirt.decoded_pbr.d0.v1",
    garment_class="button_shirt",
    family_token="button_shirt",
    panel_views=(
        (
            "front",
            ("panel.button_shirt.front.left", "panel.button_shirt.front.right"),
        ),
        ("back", "panel.button_shirt.back"),
    ),
    capture_record_version="closy.button_shirt.capture_fixture.d0.v1",
    capture_record_id="capture.synthetic_button_shirt_reference_v1",
    texture_identity_id="texture.button_shirt.public_d0_v1",
    texture_report_path="textures/button_shirt_pbr_report.json",
    fidelity_report_version="closy.button_shirt.source_render_fidelity.d0.v1",
    fidelity_report_id="source_render_fidelity.button_shirt.public_d0_v1",
    fidelity_acceptance_key="acceptedForD0ButtonShirtFixture",
    fabric_rgba=TORSO_RGBA,
    material_id="material.lightweight_woven_reference_v1",
)


def build_button_shirt_appearance_bundle(
    *, pattern: dict[str, Any], settled_mesh: MeshSet, seed: int
) -> ButtonShirtAppearanceBundle:
    return build_appearance_bundle(
        spec=APPEARANCE_SPEC,
        pattern=pattern,
        settled_mesh=settled_mesh,
        seed=seed,
    )
