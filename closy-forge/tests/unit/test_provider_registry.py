from __future__ import annotations

from pathlib import Path

from closy_forge.appearance import build_texture_identity_report
from closy_forge.capture import build_synthetic_capture_record
from closy_forge.fitting import fit_tshirt_parameters_from_visual_observations
from closy_forge.geometry.glb_io import write_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.proposals import (
    build_geometry_provider_registry,
    build_null_geometry_proposal,
    hash_provider_registry,
    inspect_manual_import_candidate,
    provider_registry_quality_report,
)
from closy_forge.visual_understanding import build_tshirt_visual_observations


def test_geometry_provider_registry_is_deterministic_and_d0_safe() -> None:
    capture, visual, fit, texture, proposal = _source_artifacts()

    first = build_geometry_provider_registry(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
        geometry_proposal=proposal,
    )
    second = build_geometry_provider_registry(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
        geometry_proposal=proposal,
    )
    quality = provider_registry_quality_report(first)

    assert first == second
    assert first["selectedProviderId"] == "closy.null_geometry_proposal_provider.v1"
    assert first["scope"]["supportedDomain"] == "avatar_garment_only"
    assert first["scope"]["allowsGenericObjects"] is False
    assert first["d0Capabilities"]["providerRegistryAvailable"] is True
    assert first["d0Capabilities"]["manualLocalImportAdapterDeclared"] is True
    assert first["d0Capabilities"]["manualLocalImportAssetAvailable"] is False
    assert first["d0Capabilities"]["externalProvidersConfigured"] is False
    assert first["manualImportCandidate"]["status"] == "missing_local_asset"
    assert first["integrity"]["providerRegistryHash"] == hash_provider_registry(first)
    assert quality["status"] == "pass"
    assert quality["manualImportFailureReason"] == "manual_glb_asset_not_supplied"


def test_manual_import_candidate_rejects_missing_and_unsafe_paths() -> None:
    missing = inspect_manual_import_candidate(Path("missing.glb"))
    unsafe = inspect_manual_import_candidate(Path("..") / "evil.glb")
    wrong_extension = inspect_manual_import_candidate(Path("candidate.obj"))

    assert missing["acceptedForRawProposal"] is False
    assert missing["failureReason"] == "manual_glb_asset_not_found"
    assert unsafe["acceptedForRawProposal"] is False
    assert unsafe["failureReason"] == "unsafe_path_traversal"
    assert wrong_extension["acceptedForRawProposal"] is False
    assert wrong_extension["failureReason"] == "unsupported_manual_asset_extension"


def test_manual_import_candidate_accepts_valid_local_glb(tmp_path: Path) -> None:
    glb_path = tmp_path / "manual_tshirt_candidate.glb"
    write_glb(glb_path, _tiny_mesh(), "manual_candidate_material", (0.1, 0.2, 0.8, 1.0))

    candidate = inspect_manual_import_candidate(glb_path)

    assert candidate["status"] == "eligible_raw_visual_proposal"
    assert candidate["acceptedForRawProposal"] is True
    assert candidate["acceptedForCanonical"] is False
    assert candidate["asset"]["assetName"] == "manual_tshirt_candidate.glb"
    assert candidate["asset"]["assetHash"] is not None
    assert candidate["audit"]["validGlb20"] is True
    assert candidate["audit"]["triangleEstimate"] == 1


def test_registry_selects_reviewed_manual_candidate(tmp_path: Path) -> None:
    capture, visual, fit, texture, proposal = _source_artifacts()
    glb_path = tmp_path / "manual_tshirt_candidate.glb"
    write_glb(glb_path, _tiny_mesh(), "manual_candidate_material", (0.1, 0.2, 0.8, 1.0))

    registry = build_geometry_provider_registry(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
        geometry_proposal=proposal,
        manual_asset_path=glb_path,
        manual_asset_rights_reviewed=True,
        manual_asset_rights_status="project_authored_fixture_no_third_party_asset",
    )

    assert registry["selectedProviderId"] == "closy.manual_local_glb_import.v1"
    assert registry["d0Capabilities"]["manualLocalImportAssetAvailable"] is True
    assert registry["manualImportCandidate"]["acceptedForRawProposal"] is True
    assert registry["providers"][1]["licence"]["termsReviewed"] is True
    assert registry["integrity"]["providerRegistryHash"] == hash_provider_registry(registry)


def _source_artifacts() -> (
    tuple[
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, object],
    ]
):
    capture = build_synthetic_capture_record(seed=101)
    visual = build_tshirt_visual_observations(capture)
    fit = fit_tshirt_parameters_from_visual_observations(visual)
    texture = build_texture_identity_report(
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        render_materials={"schemaVersion": 1, "materials": []},
    )
    proposal = build_null_geometry_proposal(
        garment_id="garment.demo_tshirt.reference_v1",
        garment_class="tshirt",
        capture_record=capture,
        visual_observations=visual,
        fit_report=fit,
        texture_identity=texture,
    )
    return capture, visual, fit, texture, proposal


def _tiny_mesh() -> MeshSet:
    return MeshSet(
        [
            Mesh(
                name="manual_candidate_triangle",
                panel_id="panel.front",
                vertices=[(0.0, 0.0, 0.0), (0.12, 0.0, 0.0), (0.0, 0.12, 0.0)],
                panel_uvs=[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
                triangles=[(0, 1, 2)],
            )
        ]
    )
