from __future__ import annotations

from closy_forge.appearance import build_texture_identity_report
from closy_forge.capture import build_synthetic_capture_record
from closy_forge.fitting import fit_tshirt_parameters_from_visual_observations
from closy_forge.proposals import (
    build_null_geometry_proposal,
    geometry_proposal_quality_report,
    hash_geometry_proposal,
)
from closy_forge.visual_understanding import build_tshirt_visual_observations


def test_null_geometry_proposal_is_deterministic_and_rejected() -> None:
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    fit = fit_tshirt_parameters_from_visual_observations(visual)
    texture = build_texture_identity_report(
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        render_materials={"schemaVersion": 1, "materials": []},
    )

    first = build_null_geometry_proposal(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
    )
    second = build_null_geometry_proposal(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
    )
    quality = geometry_proposal_quality_report(first)

    assert first == second
    assert first["rawProposal"]["available"] is False
    assert first["cleanProposal"]["available"] is False
    assert first["quality"]["status"] == "rejected"
    assert first["quality"]["acceptedForCanonical"] is False
    assert first["request"]["supportedDomain"] == "avatar_garment_only"
    assert first["integrity"]["geometryProposalHash"] == hash_geometry_proposal(first)
    assert quality["status"] == "rejected"
    assert quality["failureReason"] == "null_provider_no_geometry_generated"
