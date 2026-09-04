from __future__ import annotations

import ast
import json
from copy import deepcopy
from pathlib import Path

import pytest

from closy_forge.capture_reconstruction_v2.appearance import (
    appearance_report,
    evaluate_appearance_controls,
    project_appearance,
)
from closy_forge.capture_reconstruction_v2.camera_estimation import (
    camera_negative_controls,
    estimate_body_pose_from_pixels,
    estimate_camera_from_pixels,
)
from closy_forge.capture_reconstruction_v2.common import canonical_digest
from closy_forge.capture_reconstruction_v2.contestant import infer_pixel_observation
from closy_forge.capture_reconstruction_v2.corpus import (
    _generate_session,
    build_development_seed_authority,
    validate_observable_manifest,
)
from closy_forge.capture_reconstruction_v2.corrections import (
    apply_correction_journal,
    development_correction_fixture,
)
from closy_forge.capture_reconstruction_v2.fitter import fit_structured_garment
from closy_forge.capture_reconstruction_v2.package_artifact import (
    retain_candidate_package,
    validate_retained_package,
)
from closy_forge.capture_reconstruction_v2.producer_cross import render_cross_generator
from closy_forge.capture_reconstruction_v2.producer_in_model import render_in_model
from closy_forge.capture_reconstruction_v2.protocol import CONTROL_NAMES, build_protocol
from closy_forge.capture_reconstruction_v2.video_mjpeg import (
    VideoDecodeError,
    decode_mjpeg_avi,
    encode_mjpeg_avi,
)

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "closy_forge"


def _session(
    *,
    mode: str = "B",
    family: str = "tshirt",
    stratum: str = "in_model",
) -> dict[str, object]:
    return {
        "sessionId": f"test-{mode}-{family}-{stratum}",
        "partition": "development",
        "mode": mode,
        "family": family,
        "stratum": stratum,
        "presentation": "flat",
        "planOrdinal": 0,
        "resolution": [256, 256],
        "weakOrMissingViewIndex": 2 if mode == "C" else None,
        "expectedSourceCount": 3 if mode == "C" else 1,
        "expectedVideoFrames": 24 if mode == "D" else 0,
    }


def _observation(family: str = "tshirt", mode: str = "B", *, nonce: int = 7331):
    rendered = render_in_model(_session(mode=mode, family=family), hidden_nonce=nonce)
    return infer_pixel_observation(
        f"source-{family}", rendered.rgba, rendered.width, rendered.height, frame_index=0
    )


def test_mode_a_flat_and_hung_are_pixel_and_geometry_distinct() -> None:
    flat = _session(mode="A")
    hung = {**flat, "presentation": "hung"}
    left = render_in_model(flat, hidden_nonce=101)
    right = render_in_model(hung, hidden_nonce=101)
    assert left.rgba != right.rgba
    assert left.masks["garment"] != right.masks["garment"]
    assert any(left.masks["scale_target"])
    assert left.camera["scaleMetersPerPixel"] > 0


@pytest.mark.parametrize("renderer", [render_in_model, render_cross_generator])
def test_mode_b_pixels_encode_body_hair_hands_occlusion_and_garment(renderer) -> None:  # type: ignore[no-untyped-def]
    rendered = renderer(_session(mode="B"), hidden_nonce=222)
    assert any(rendered.masks["garment"])
    assert any(rendered.masks["body"])
    assert any(rendered.masks["hair"])
    assert any(rendered.masks["hands"])
    assert rendered.body_pose["leftArmDegrees"] != rendered.body_pose["rightArmDegrees"]


def test_mode_c_views_have_distinct_pixels_intrinsics_extrinsics_and_weak_denominator() -> None:
    session = _session(mode="C")
    views = [
        render_cross_generator(session, hidden_nonce=333, view_index=index) for index in range(3)
    ]
    assert len({row.rgba for row in views}) == 3
    assert len({row.camera["focalPixels"] for row in views}) == 3
    assert len({row.camera["yawDegrees"] for row in views}) == 3
    assert session["weakOrMissingViewIndex"] == 2


@pytest.mark.parametrize("renderer", [render_in_model, render_cross_generator])
def test_mode_d_is_real_riff_mjpeg_with_24_distinct_causal_frames(renderer) -> None:  # type: ignore[no-untyped-def]
    session = _session(mode="D")
    frames = [renderer(session, hidden_nonce=444, frame_index=index) for index in range(24)]
    encoded = encode_mjpeg_avi(256, 256, [row.rgba for row in frames])
    decoded = decode_mjpeg_avi(encoded)
    assert encoded[:4] == b"RIFF"
    assert encoded[8:12] == b"AVI "
    assert len(decoded.frames) == 24
    assert len({row.pixelSha256 for row in decoded.frames}) == 24
    assert len({row.frame_state["posePhase"] for row in frames}) > 12
    assert len({row.frame_state["clothPhase"] for row in frames}) > 12


def test_video_decoder_rejects_corruption_and_resource_limit() -> None:
    frames = [
        render_in_model(_session(mode="D"), hidden_nonce=555, frame_index=i) for i in range(24)
    ]
    encoded = encode_mjpeg_avi(256, 256, [row.rgba for row in frames])
    corrupted = bytearray(encoded)
    corrupted[4:8] = (1).to_bytes(4, "little")
    with pytest.raises(VideoDecodeError, match="riff_length_invalid"):
        decode_mjpeg_avi(bytes(corrupted))
    with pytest.raises(VideoDecodeError, match="byte_limit_exceeded"):
        decode_mjpeg_avi(b"0" * (2 * 1024 * 1024 + 1))


def test_mode_e_keeps_hidden_hypotheses_out_of_public_manifest() -> None:
    protocol = build_protocol()
    session = next(
        row
        for row in protocol["sessionPlan"]
        if row["partition"] == "development" and row["mode"] == "E"
    )
    seed = build_development_seed_authority(protocol)[session["sessionId"]]
    public, truth, _sources = _generate_session(
        session, protocol, frozen_source_commit="a" * 40, hidden_seed=seed
    )
    assert len(truth["targetHypotheses"]) == 3
    assert {"seed", "producerIdentity", "stratum", "observations"}.isdisjoint(public)
    assert public["truthWithheld"] is True


def test_observable_manifest_rejects_hidden_fields_traversal_and_unlisted_files(
    tmp_path: Path,
) -> None:
    protocol = build_protocol()
    session = next(row for row in protocol["sessionPlan"] if row["partition"] == "development")
    seed = build_development_seed_authority(protocol)[session["sessionId"]]
    public, _truth, sources = _generate_session(
        session, protocol, frozen_source_commit="a" * 40, hidden_seed=seed
    )
    public["truthCommitment"] = "a" * 64
    for suffix, payload in sources:
        source = next(row for row in public["sources"] if row["codec"].casefold() == suffix)
        (tmp_path / source["contentAddressedName"]).write_bytes(payload)
    manifest = {
        "sessionCount": 1,
        "uniqueSourceFileCount": len(sources),
        "sessions": [public],
    }
    manifest["observableManifestDigest"] = canonical_digest(manifest)
    assert validate_observable_manifest(tmp_path, manifest) == []

    leaked = deepcopy(manifest)
    leaked["sessions"][0]["seed"] = "secret"
    leaked["observableManifestDigest"] = canonical_digest(leaked, "observableManifestDigest")
    assert "observable_forbidden_session_field" in validate_observable_manifest(tmp_path, leaked)

    invalid_commitment = deepcopy(manifest)
    invalid_commitment["sessions"][0]["truthCommitment"] = "not-a-digest"
    invalid_commitment["observableManifestDigest"] = canonical_digest(
        invalid_commitment, "observableManifestDigest"
    )
    assert "observable_truth_commitment_format_invalid" in validate_observable_manifest(
        tmp_path, invalid_commitment
    )

    traversing = deepcopy(manifest)
    traversing["sessions"][0]["sources"][0]["contentAddressedName"] = "../outside.png"
    traversing["observableManifestDigest"] = canonical_digest(
        traversing, "observableManifestDigest"
    )
    assert "observable_source_name_or_digest_format_invalid" in validate_observable_manifest(
        tmp_path, traversing
    )

    (tmp_path / "unlisted.bin").write_bytes(b"unexpected")
    assert "observable_source_inventory_mismatch" in validate_observable_manifest(
        tmp_path, manifest
    )


def test_correction_fixture_executes_all_nine_operations_and_replays_exactly() -> None:
    initial, operations = development_correction_fixture()
    report = apply_correction_journal(initial, operations)
    assert [row["kind"] for row in report["operations"]] == [row["kind"] for row in operations]
    assert report["operationCount"] == 9
    assert report["initialDigest"] != report["finalDigest"]
    assert report["replayDigest"] == report["finalDigest"]
    assert report["undoDigest"] == report["initialDigest"]
    assert report["redoDigest"] == report["finalDigest"]
    assert report["replayDeterministic"] is True
    assert report["allDownstreamInvalidated"] is True


def test_correction_noop_and_unknown_operations_fail_closed() -> None:
    initial, operations = development_correction_fixture()
    no_op = deepcopy(operations[0])
    no_op["value"] = initial["captureRole"]
    with pytest.raises(ValueError, match="no_op_forbidden"):
        apply_correction_journal(initial, [no_op])
    with pytest.raises(ValueError, match="operation_unknown"):
        apply_correction_journal(initial, [{"kind": "oracle_fix", "value": True}])


def test_camera_and_body_pose_are_pixel_derived_with_negative_controls() -> None:
    observations = [_observation(mode="D", nonce=900 + index) for index in range(3)]
    camera = estimate_camera_from_pixels(observations[0])
    pose = estimate_body_pose_from_pixels(observations[0], "D")
    assert camera["status"] == "estimated"
    assert camera["producerCameraConsumed"] is False
    assert camera["radialDistortionPolicy"] == (
        "not_estimated_protocol_raster_has_no_radial_distortion"
    )
    garment_indexes = [
        index for index, value in enumerate(observations[0].masks["garment"]) if value
    ]
    garment_centroid_x = sum(index % observations[0].width for index in garment_indexes) / len(
        garment_indexes
    )
    assert camera["principalX"] != round(garment_centroid_x, 8)
    assert pose["status"] == "estimated"
    assert pose["hiddenBodyMetadataConsumed"] is False
    controls = camera_negative_controls(camera, observations)
    assert controls["wrongFocalLengthDegrades"] is True
    assert controls["wrongScaleDegrades"] is True
    assert controls["shuffledRoleCannotOverridePixels"] is True


@pytest.mark.parametrize("family", ["tshirt", "sleeveless_top", "simple_skirt"])
def test_all_observation_fitter_builds_structured_retained_family_packages(
    family: str, tmp_path: Path
) -> None:
    observations = [_observation(family, nonce=1200 + index) for index in range(2)]
    fit = fit_structured_garment(family, "B", observations)
    assert fit["inputDenominators"]["attemptedObservations"] == 2
    assert fit["candidateCount"] == 12
    assert fit["candidateBudget"]["maximumFitCandidatesPerSession"] == 12
    assert fit["stoppingReason"] == "predeclared_candidate_budget_exhausted_then_stable_tie_break"
    assert len(fit["rejectedCandidates"]) == 11
    assert set(fit["objectiveTrace"][0]["objectiveTerms"]) >= {
        "pixelDerivedMultiviewSilhouette",
        "visibleLandmarks",
        "renderedShape",
        "topologyOpenings",
        "scale",
        "seamCompatibility",
        "patternPrior",
        "bodyClearance",
        "temporalConsistency",
        "printAlignment",
        "materialSettledShape",
    }
    package = fit["package"]
    assert package["pattern"]["panels"]
    assert package["pattern"]["seams"]
    assert all(mesh["vertices"] for mesh in package["simulationMesh"]["meshes"])
    assert all(mesh["vertices"] for mesh in package["renderMesh"]["meshes"])
    assert package["simulationToRenderBinding"]["records"]
    assert package["solver"]["iterations"] > 0
    manifest = retain_candidate_package(
        tmp_path, f"session-{family}", fit, {"baseColorSha256": "a" * 64}
    )
    package_root = tmp_path / f"session-{family}"
    assert manifest["intrinsicPackageValid"] is True
    assert validate_retained_package(package_root) == []
    assert (package_root / "simulation" / "settle_receipt.json").is_file()

    package_manifest_path = package_root / "manifest.json"
    changed = json.loads(package_manifest_path.read_text(encoding="utf-8"))
    changed["inventory"][0]["path"] = "../outside.json"
    changed["canonicalPackageDigest"] = canonical_digest(changed["inventory"])
    changed["manifestDigest"] = canonical_digest(changed, "manifestDigest")
    package_manifest_path.write_text(json.dumps(changed), encoding="utf-8")
    assert validate_retained_package(package_root) == ["capture_package_inventory_path_unsafe"]


def test_appearance_uses_fitted_geometry_cameras_and_exactly_five_causal_controls() -> None:
    left = _observation("tshirt", nonce=1401)
    right = _observation("tshirt", nonce=1402)
    observations = [left, right]
    cameras = [estimate_camera_from_pixels(row) for row in observations]
    atlas = project_appearance(observations, cameras, fitted_geometry_digest="f" * 64)
    report = appearance_report(atlas, fitted_geometry_digest="f" * 64)
    controls = evaluate_appearance_controls(
        "appearance-session",
        observations,
        cameras,
        _observation("tshirt", nonce=1999),
        fitted_geometry_digest="f" * 64,
    )
    assert report["targetMeshUvTextureConsumed"] is False
    assert report["fittedRenderGeometryDigest"] == "f" * 64
    assert report["perTexelProvenance"] is True
    assert len(controls) == 5
    assert {row["control"] for row in controls} == set(CONTROL_NAMES)
    assert all(row["terminalOutcome"] in {"passed", "failed"} for row in controls)
    hidden = next(row for row in controls if row["control"] == "evaluator_hidden_target_mutation")
    assert hidden["terminalOutcome"] == "passed"
    assert hidden["baselineDigest"] == hidden["interventionDigest"]


def test_contestant_projection_modules_have_no_source_generator_or_truth_import_path() -> None:
    prohibited = {
        "closy_forge.capture_reconstruction_v2.corpus",
        "closy_forge.capture_reconstruction_v2.producer_in_model",
        "closy_forge.capture_reconstruction_v2.producer_cross",
        "closy_forge.capture_reconstruction_v2.evaluator_renderer",
    }
    for name in ("contestant.py", "camera_estimation.py", "fitter.py", "appearance.py"):
        tree = ast.parse((SOURCE_ROOT / "capture_reconstruction_v2" / name).read_text())
        imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        absolute = {
            (
                f"closy_forge.capture_reconstruction_v2.{node.module}"
                if node.level
                else str(node.module)
            )
            for node in imports
            if node.module is not None
        }
        assert prohibited.isdisjoint(absolute)
