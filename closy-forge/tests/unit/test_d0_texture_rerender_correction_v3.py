from __future__ import annotations

import json
from pathlib import Path

import pytest

from closy_forge.appearance.bitmap_atlas import ATLAS_SIZE, BITMAP_PATHS
from closy_forge.appearance_correction_v3.freeze import load_implementation_freeze
from closy_forge.appearance_correction_v3.known_target import evaluate_known_target_once
from closy_forge.appearance_correction_v3.prediction import (
    generate_source_only_prediction,
    validate_frozen_candidate,
)
from closy_forge.appearance_correction_v3.projection import (
    PROVENANCE_MANIFEST_PATH,
    PROVENANCE_PATH,
    audit_geometric_source_atlas,
    build_geometric_source_atlas,
    decode_provenance,
    panel_uv_to_atlas,
)
from closy_forge.appearance_correction_v3.protocol import load_correction_protocol
from closy_forge.appearance_correction_v3.source_inputs import load_locked_source_inputs
from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.inspection.source_render_fidelity import _atlas_sampler
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.raster import DecodedPng

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_COMMIT = "5a01ed40656c3f2924169f2c3e8f4d702f572cc5"
PARENT_CANDIDATE = ROOT / (
    "docs/evidence/d0_fitting_pbr_fidelity_v2/predictions/candidate_package"
)


@pytest.fixture(scope="module")
def source_inputs():
    return load_locked_source_inputs(ROOT)


@pytest.fixture(scope="module")
def settled_mesh():
    return read_glb_meshset(PARENT_CANDIDATE / "simulation/settled_mesh.glb")


@pytest.fixture(scope="module")
def geometric_atlas(settled_mesh, source_inputs):
    return build_geometric_source_atlas(settled_mesh, source_inputs)


@pytest.fixture(scope="module")
def frozen_prediction(tmp_path_factory):
    output = tmp_path_factory.mktemp("d0-texture-v3") / "predictions"
    summary = generate_source_only_prediction(
        ROOT,
        protocol_commit_sha=PROTOCOL_COMMIT,
        implementation_anchor_sha=PROTOCOL_COMMIT,
        output=output,
    )
    return output, summary


def test_protocol_is_exactly_locked_and_non_promotional() -> None:
    protocol = load_correction_protocol(ROOT)
    assert protocol["strategy"]["maximumAppearanceStrategies"] == 1
    assert protocol["strategy"]["maximumKnownTargetTrials"] == 1
    assert protocol["knownEvaluatorTarget"]["accessStateBeforePredictionFreeze"] == "not_mounted"
    assert protocol["outcomePolicy"]["mayPromoteD0Rp07"] is False
    assert protocol["outcomePolicy"]["mayPromoteResearchPrototype"] is False


def test_implementation_freeze_reopens_every_hashed_file() -> None:
    freeze = load_implementation_freeze(ROOT)
    assert freeze["evaluatorOnlyMounted"] is False
    assert freeze["knownTargetTrialCount"] == 0
    assert freeze["maximumKnownTargetTrials"] == 1
    assert len(freeze["implementationFiles"]) == 11


def test_source_closure_contains_only_exact_front_and_rear(source_inputs) -> None:
    assert {view.label for view in source_inputs} == {"front", "back"}
    assert all(sha256_bytes(view.payload) == view.expected_sha256 for view in source_inputs)
    assert all(view.garment_pixels for view in source_inputs)
    assert next(view for view in source_inputs if view.label == "front").logo_pixels
    assert not next(view for view in source_inputs if view.label == "back").logo_pixels


@pytest.mark.parametrize(
    ("panel_id", "uv", "label"),
    [
        ("panel.front", (0.0, 0.25), "front"),
        ("panel.back", (0.1, 0.4), "back"),
        ("panel.sleeve.left", (0.0, 0.1), "front"),
        ("panel.sleeve.right", (0.04, 0.2), "back"),
    ],
)
def test_panel_uv_contract_matches_independent_renderer(
    panel_id: str, uv: tuple[float, float], label: str
) -> None:
    pixels = bytearray()
    for y in range(ATLAS_SIZE):
        for x in range(ATLAS_SIZE):
            pixels.extend((x, y, 17, 255))
    atlas = DecodedPng(ATLAS_SIZE, ATLAS_SIZE, bytes(pixels))
    expected_x, expected_y = panel_uv_to_atlas(
        panel_id, uv, use_rear=label == "back"
    )
    sampled = _atlas_sampler(atlas, label)(panel_id, uv)
    assert sampled == (int(expected_x), int(expected_y), 17, 255)


def test_geometric_projection_meets_source_only_coverage_and_preserves_logo(
    geometric_atlas,
) -> None:
    coverage = geometric_atlas.report["coverage"]
    assert coverage["denominator"] == "active_semantic_island_texels"
    assert coverage["sourceObservedFraction"] >= 0.50
    assert 0.0 < coverage["generatedControlledFillFraction"] <= 0.55
    assert geometric_atlas.report["logoPreservation"]["preserved"] is True
    assert geometric_atlas.report["policy"]["evaluatorOnlyViewUsed"] is False


def test_provenance_roundtrip_retains_pixel_triangle_uv_and_classification(
    geometric_atlas,
) -> None:
    compressed = geometric_atlas.artifacts[PROVENANCE_PATH]
    manifest = geometric_atlas.artifacts[PROVENANCE_MANIFEST_PATH]
    assert isinstance(compressed, bytes)
    assert isinstance(manifest, dict)
    decoded = decode_provenance(compressed, manifest)
    assert decoded == geometric_atlas.provenance_records
    observed = next(record for record in decoded if record.classification == "observed")
    assert observed.view_label in {"front", "back"}
    assert observed.source_x != 65535
    assert observed.panel_id
    assert abs(sum(observed.barycentric) - 1.0) < 1.0e-5
    assert all(value == value for value in observed.material_uv)


def test_provenance_corruption_fails_closed(geometric_atlas) -> None:
    compressed = geometric_atlas.artifacts[PROVENANCE_PATH]
    manifest = geometric_atlas.artifacts[PROVENANCE_MANIFEST_PATH]
    assert isinstance(compressed, bytes)
    assert isinstance(manifest, dict)
    corrupted = bytearray(compressed)
    corrupted[len(corrupted) // 2] ^= 0x01
    with pytest.raises(ValueError):
        decode_provenance(bytes(corrupted), manifest)


def test_map_hash_corruption_fails_closed(geometric_atlas) -> None:
    artifacts = dict(geometric_atlas.artifacts)
    base = artifacts[BITMAP_PATHS["baseColor"]]
    assert isinstance(base, bytes)
    artifacts[BITMAP_PATHS["baseColor"]] = base[:-1] + bytes((base[-1] ^ 1,))
    with pytest.raises(ValueError, match="geometric_atlas_map_hash_mismatch"):
        audit_geometric_source_atlas(artifacts, geometric_atlas.report)


def test_source_controls_are_causal_and_geometry_invariant(frozen_prediction) -> None:
    output, _summary = frozen_prediction
    controls = _read(output / "source_only_controls.json")
    assert controls["allControlsPassed"] is True
    assert controls["noMagicLocationConstant"] is True
    assert controls["geometryInvariantAcrossControls"] is True
    assert controls["evaluatorOnlyBytesOpened"] is False
    assert [record["controlId"] for record in controls["records"]] == [
        "move_logo_left",
        "move_logo_right",
        "move_logo_vertically",
        "change_logo_size",
        "change_logo_color_without_geometry_change",
        "remove_logo",
        "swap_front_rear",
        "perturb_camera_within_locked_range",
    ]
    assert all(record["passed"] for record in controls["records"])
    assert all(record["sourceHashChanged"] for record in controls["records"])
    assert all(record["provenanceHashChanged"] for record in controls["records"])


def test_prediction_is_frozen_before_evaluator_and_package_valid(frozen_prediction) -> None:
    output, summary = frozen_prediction
    freeze = _read(output / "prediction_freeze.json")
    assert freeze["state"] == "frozen_before_known_target_mount"
    assert freeze["knownTargetTrialCount"] == 0
    assert freeze["evaluatorOnlyPixelsMounted"] is False
    assert freeze["evaluatorOnlyDerivedEvidenceMounted"] is False
    assert freeze["evaluatorOnlyTarget3dMounted"] is False
    assert summary["sourceOnlyRerenderPredicatesPassed"] is True
    assert summary["d0Rp07Status"] == "fail_preserved_pending_unit_g"
    assert validate_frozen_candidate(output / "candidate_package")["status"] == "pass"


def test_new_package_invalidates_appearance_but_preserves_geometry_bytes(
    frozen_prediction,
) -> None:
    output, _summary = frozen_prediction
    invalidation = _read(output / "identity_invalidation.json")
    assert invalidation["allRetainedGeometryPhysicsByteIdentical"] is True
    assert invalidation["matrixV3StatusChanged"] is False
    assert invalidation["d0Rp07Promoted"] is False
    assert set(invalidation["invalidated"]) >= {
        "atlas",
        "material_maps",
        "candidate_package",
        "runtime_package",
        "matrix_evidence_binding",
        "downstream_cache",
        "reports",
    }


def test_candidate_byte_corruption_is_rejected(frozen_prediction) -> None:
    output, _summary = frozen_prediction
    candidate = output / "candidate_package"
    manifest_path = candidate / "candidate_manifest.json"
    manifest = _read(manifest_path)
    original = manifest_path.read_text(encoding="utf-8")
    try:
        manifest["packageDigest"] = "0" * 64
        manifest_path.write_text(canonical_dumps(manifest), encoding="utf-8")
        result = validate_frozen_candidate(candidate)
        assert result["status"] == "fail"
        assert "candidate_package_digest_mismatch" in result["issues"]
    finally:
        manifest_path.write_text(original, encoding="utf-8")


def test_known_target_cannot_replay_into_existing_output(frozen_prediction, tmp_path) -> None:
    prediction, _summary = frozen_prediction
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    with pytest.raises(ValueError, match="trial_already_exists"):
        evaluate_known_target_once(
            ROOT,
            prediction_commit_sha=PROTOCOL_COMMIT,
            evaluator_anchor_sha=PROTOCOL_COMMIT,
            predictions=prediction,
            output=occupied,
        )


def test_original_failure_is_immutable_and_still_failed() -> None:
    failure = _read(
        ROOT
        / "docs/evidence/d0_fitting_pbr_fidelity_v2/evaluation"
        / "exact_texture_rerender_evaluation.json"
    )
    assert failure["status"] == "fail"
    assert failure["frontLogoIdentity"] == {
        "status": "fail",
        "logoIoU": 0.0,
        "logoDisplacementNormalised": 0.154158086,
    }


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value
