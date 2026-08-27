from __future__ import annotations

from typing import Any, TypeAlias

from closy_forge.garments.vertical_slice.appearance import (
    AppearanceBundle,
    AppearanceSpec,
    build_appearance_bundle,
)
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.visual_understanding.raster_parser import TORSO_RGBA

JacketOuterwearAppearanceBundle: TypeAlias = AppearanceBundle
APPEARANCE_SPEC = AppearanceSpec(
    appearance_version="closy.jacket_outerwear.decoded_pbr.d0.v1",
    garment_class="jacket_outerwear",
    family_token="jacket_outerwear",
    panel_views=(
        (
            "front",
            ("panel.jacket_outerwear.front.left", "panel.jacket_outerwear.front.right"),
        ),
        ("back", "panel.jacket_outerwear.back"),
    ),
    capture_record_version="closy.jacket_outerwear.capture_fixture.d0.v1",
    capture_record_id="capture.synthetic_jacket_outerwear_reference_v1",
    texture_identity_id="texture.jacket_outerwear.public_d0_v1",
    texture_report_path="textures/jacket_outerwear_pbr_report.json",
    fidelity_report_version="closy.jacket_outerwear.source_render_fidelity.d0.v1",
    fidelity_report_id="source_render_fidelity.jacket_outerwear.public_d0_v1",
    fidelity_acceptance_key="acceptedForD0JacketOuterwearFixture",
    fabric_rgba=TORSO_RGBA,
    material_id="material.heavy_jersey_reference_v1",
)


def build_jacket_outerwear_appearance_bundle(
    *, pattern: dict[str, Any], settled_mesh: MeshSet, seed: int
) -> JacketOuterwearAppearanceBundle:
    return build_appearance_bundle(
        spec=APPEARANCE_SPEC,
        pattern=pattern,
        settled_mesh=settled_mesh,
        seed=seed,
    )
