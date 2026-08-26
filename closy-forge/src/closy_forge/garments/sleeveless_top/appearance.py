from __future__ import annotations

from typing import Any, TypeAlias

from closy_forge.garments.vertical_slice.appearance import (
    AppearanceBundle,
    AppearanceSpec,
    build_appearance_bundle,
)
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.visual_understanding.raster_parser import TORSO_RGBA

SLEEVELESS_APPEARANCE_VERSION = "closy.sleeveless_top.decoded_pbr.d0.v1"
WIDTH = 128
HEIGHT = 160
ATLAS_SIZE = 128
FABRIC_RGBA = TORSO_RGBA
SleevelessAppearanceBundle: TypeAlias = AppearanceBundle
APPEARANCE_SPEC = AppearanceSpec(
    appearance_version=SLEEVELESS_APPEARANCE_VERSION,
    garment_class="sleeveless_top",
    family_token="sleeveless_top",
    panel_views=(
        ("front", "panel.sleeveless_top.front"),
        ("back", "panel.sleeveless_top.back"),
    ),
    capture_record_version="closy.sleeveless_top.capture_fixture.d0.v1",
    capture_record_id="capture.synthetic_sleeveless_top_reference_v1",
    texture_identity_id="texture.sleeveless_top.public_d0_v1",
    texture_report_path="textures/sleeveless_pbr_report.json",
    fidelity_report_version="closy.sleeveless_top.source_render_fidelity.d0.v1",
    fidelity_report_id="source_render_fidelity.sleeveless_top.public_d0_v1",
    fidelity_acceptance_key="acceptedForD0SleevelessFixture",
    fabric_rgba=FABRIC_RGBA,
)


def build_sleeveless_appearance_bundle(
    *, pattern: dict[str, Any], settled_mesh: MeshSet, seed: int
) -> SleevelessAppearanceBundle:
    return build_appearance_bundle(
        spec=APPEARANCE_SPEC,
        pattern=pattern,
        settled_mesh=settled_mesh,
        seed=seed,
    )
