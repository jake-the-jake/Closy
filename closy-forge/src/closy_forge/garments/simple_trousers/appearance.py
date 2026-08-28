from __future__ import annotations

from typing import Any, TypeAlias

from closy_forge.garments.vertical_slice.appearance import (
    AppearanceBundle,
    AppearanceSpec,
    build_appearance_bundle,
)
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.inspection.independent_targets import IndependentTargetEvidence
from closy_forge.visual_understanding.raster_parser import TORSO_RGBA

SimpleTrousersAppearanceBundle: TypeAlias = AppearanceBundle
APPEARANCE_SPEC = AppearanceSpec(
    appearance_version="closy.simple_trousers.decoded_pbr.d0.v1",
    garment_class="simple_trousers",
    family_token="simple_trousers",
    panel_views=(
        (
            "front",
            (
                "panel.simple_trousers.front.left",
                "panel.simple_trousers.front.right",
            ),
        ),
        (
            "back",
            (
                "panel.simple_trousers.back.left",
                "panel.simple_trousers.back.right",
            ),
        ),
    ),
    capture_record_version="closy.simple_trousers.capture_fixture.d0.v1",
    capture_record_id="capture.synthetic_simple_trousers_reference_v1",
    texture_identity_id="texture.simple_trousers.public_d0_v1",
    texture_report_path="textures/simple_trousers_pbr_report.json",
    fidelity_report_version="closy.simple_trousers.source_render_fidelity.d0.v1",
    fidelity_report_id="source_render_fidelity.simple_trousers.public_d0_v1",
    fidelity_acceptance_key="acceptedForD0SimpleTrousersFixture",
    fabric_rgba=TORSO_RGBA,
)


def build_simple_trousers_appearance_bundle(
    *,
    pattern: dict[str, Any],
    settled_mesh: MeshSet,
    seed: int,
    independent_target: IndependentTargetEvidence | None = None,
) -> SimpleTrousersAppearanceBundle:
    return build_appearance_bundle(
        spec=APPEARANCE_SPEC,
        pattern=pattern,
        settled_mesh=settled_mesh,
        seed=seed,
        independent_target=independent_target,
    )
