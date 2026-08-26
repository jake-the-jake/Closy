from __future__ import annotations

from typing import Any, TypeAlias

from closy_forge.garments.vertical_slice.appearance import (
    AppearanceBundle,
    AppearanceSpec,
    build_appearance_bundle,
)
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.visual_understanding.raster_parser import TORSO_RGBA

LongSleevedAppearanceBundle: TypeAlias = AppearanceBundle
APPEARANCE_SPEC = AppearanceSpec(
    appearance_version="closy.long_sleeved_top.decoded_pbr.d0.v1",
    garment_class="long_sleeved_top",
    family_token="long_sleeved_top",
    panel_views=(
        ("front", "panel.long_sleeved_top.front"),
        ("back", "panel.long_sleeved_top.back"),
    ),
    capture_record_version="closy.long_sleeved_top.capture_fixture.d0.v1",
    capture_record_id="capture.synthetic_long_sleeved_top_reference_v1",
    texture_identity_id="texture.long_sleeved_top.public_d0_v1",
    texture_report_path="textures/long_sleeved_pbr_report.json",
    fidelity_report_version="closy.long_sleeved_top.source_render_fidelity.d0.v1",
    fidelity_report_id="source_render_fidelity.long_sleeved_top.public_d0_v1",
    fidelity_acceptance_key="acceptedForD0LongSleevedFixture",
    fabric_rgba=TORSO_RGBA,
)


def build_long_sleeved_appearance_bundle(
    *, pattern: dict[str, Any], settled_mesh: MeshSet, seed: int
) -> LongSleevedAppearanceBundle:
    return build_appearance_bundle(
        spec=APPEARANCE_SPEC,
        pattern=pattern,
        settled_mesh=settled_mesh,
        seed=seed,
    )
