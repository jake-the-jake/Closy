from __future__ import annotations

from typing import Any, TypeAlias

from closy_forge.garments.vertical_slice.appearance import (
    AppearanceBundle,
    AppearanceSpec,
    build_appearance_bundle,
)
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.visual_understanding.raster_parser import TORSO_RGBA

LAYERED_ASYMMETRIC_APPEARANCE_VERSION = "closy.layered_asymmetric.decoded_pbr.d0.v1"
WIDTH = 128
HEIGHT = 160
ATLAS_SIZE = 128
FABRIC_RGBA = TORSO_RGBA
LayeredAsymmetricAppearanceBundle: TypeAlias = AppearanceBundle
APPEARANCE_SPEC = AppearanceSpec(
    appearance_version=LAYERED_ASYMMETRIC_APPEARANCE_VERSION,
    garment_class="layered_asymmetric",
    family_token="layered_asymmetric",
    panel_views=(
        ("front", "panel.layered_asymmetric.outer.front"),
        ("back", "panel.layered_asymmetric.outer.back"),
    ),
    capture_record_version="closy.layered_asymmetric.capture_fixture.d0.v1",
    capture_record_id="capture.synthetic_layered_asymmetric_reference_v1",
    texture_identity_id="texture.layered_asymmetric.public_d0_v1",
    texture_report_path="textures/layered_asymmetric_pbr_report.json",
    fidelity_report_version="closy.layered_asymmetric.source_render_fidelity.d0.v1",
    fidelity_report_id="source_render_fidelity.layered_asymmetric.public_d0_v1",
    fidelity_acceptance_key="acceptedForD0LayeredAsymmetricFixture",
    fabric_rgba=FABRIC_RGBA,
)


def build_layered_asymmetric_appearance_bundle(
    *, pattern: dict[str, Any], settled_mesh: MeshSet, seed: int
) -> LayeredAsymmetricAppearanceBundle:
    return build_appearance_bundle(
        spec=APPEARANCE_SPEC,
        pattern=pattern,
        settled_mesh=settled_mesh,
        seed=seed,
    )
