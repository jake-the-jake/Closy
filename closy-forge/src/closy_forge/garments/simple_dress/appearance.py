from __future__ import annotations

from typing import Any, TypeAlias

from closy_forge.garments.vertical_slice.appearance import (
    AppearanceBundle,
    AppearanceSpec,
    build_appearance_bundle,
)
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.visual_understanding.raster_parser import TORSO_RGBA

SimpleDressAppearanceBundle: TypeAlias = AppearanceBundle
APPEARANCE_SPEC = AppearanceSpec(
    appearance_version="closy.simple_dress.decoded_pbr.d0.v1",
    garment_class="simple_dress",
    family_token="simple_dress",
    panel_views=(
        (
            "front",
            (
                "panel.simple_dress.front.bodice",
                "panel.simple_dress.front.skirt",
            ),
        ),
        (
            "back",
            (
                "panel.simple_dress.back.bodice",
                "panel.simple_dress.back.skirt",
            ),
        ),
    ),
    capture_record_version="closy.simple_dress.capture_fixture.d0.v1",
    capture_record_id="capture.synthetic_simple_dress_reference_v1",
    texture_identity_id="texture.simple_dress.public_d0_v1",
    texture_report_path="textures/simple_dress_pbr_report.json",
    fidelity_report_version="closy.simple_dress.source_render_fidelity.d0.v1",
    fidelity_report_id="source_render_fidelity.simple_dress.public_d0_v1",
    fidelity_acceptance_key="acceptedForD0SimpleDressFixture",
    fabric_rgba=TORSO_RGBA,
    panel_y_offsets=(
        ("panel.simple_dress.front.bodice", 1.02),
        ("panel.simple_dress.front.skirt", 0.40),
        ("panel.simple_dress.back.bodice", 1.02),
        ("panel.simple_dress.back.skirt", 0.40),
    ),
)


def build_simple_dress_appearance_bundle(
    *, pattern: dict[str, Any], settled_mesh: MeshSet, seed: int
) -> SimpleDressAppearanceBundle:
    return build_appearance_bundle(
        spec=APPEARANCE_SPEC,
        pattern=pattern,
        settled_mesh=settled_mesh,
        seed=seed,
    )
