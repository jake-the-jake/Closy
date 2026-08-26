from __future__ import annotations

from typing import Any, TypeAlias

from closy_forge.garments.vertical_slice.appearance import (
    AppearanceBundle,
    AppearanceSpec,
    build_appearance_bundle,
)
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.visual_understanding.raster_parser import TORSO_RGBA

SimpleSkirtAppearanceBundle: TypeAlias = AppearanceBundle
APPEARANCE_SPEC = AppearanceSpec(
    appearance_version="closy.simple_skirt.decoded_pbr.d0.v1",
    garment_class="simple_skirt",
    family_token="simple_skirt",
    panel_views=(
        ("front", "panel.simple_skirt.front"),
        ("back", "panel.simple_skirt.back"),
    ),
    capture_record_version="closy.simple_skirt.capture_fixture.d0.v1",
    capture_record_id="capture.synthetic_simple_skirt_reference_v1",
    texture_identity_id="texture.simple_skirt.public_d0_v1",
    texture_report_path="textures/simple_skirt_pbr_report.json",
    fidelity_report_version="closy.simple_skirt.source_render_fidelity.d0.v1",
    fidelity_report_id="source_render_fidelity.simple_skirt.public_d0_v1",
    fidelity_acceptance_key="acceptedForD0SimpleSkirtFixture",
    fabric_rgba=TORSO_RGBA,
)


def build_simple_skirt_appearance_bundle(
    *, pattern: dict[str, Any], settled_mesh: MeshSet, seed: int
) -> SimpleSkirtAppearanceBundle:
    return build_appearance_bundle(
        spec=APPEARANCE_SPEC,
        pattern=pattern,
        settled_mesh=settled_mesh,
        seed=seed,
    )
