from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from closy_forge.capture.exact_raster_evidence import generate_exact_raster_identity_evidence
from closy_forge.capture.exact_raster_identity import (
    ExactRasterIdentityError,
    build_exact_raster_lineage,
    evaluate_exact_raster_quality,
    load_exact_raster_manifest,
)
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.visual_understanding.raster_parser import RasterVisualParseError
from closy_forge.visual_understanding.tshirt_observations import (
    build_tshirt_visual_observations_from_ingested_rasters,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = PACKAGE_ROOT / "fixtures" / "d0_exact_raster_v2"
MANIFEST_PATH = FIXTURE_ROOT / "fixture_manifest.json"
THRESHOLD_PATH = FIXTURE_ROOT / "quality_thresholds.json"


def test_exact_raster_lineage_reopens_front_rear_and_withholds_evaluator() -> None:
    result = _build()

    assert result["quality"]["overallStatus"] == "pass"
    assert result["quality"]["legacyV1Status"] == "fail"
    assert result["observations"]["fitInputRoles"] == ["front", "rear"]
    assert result["observations"]["aggregate"]["pixelDerivedViewCount"] == 2
    assert result["observations"]["provider"]["settings"][
        "fixtureRendererCalledDuringObservationBuild"
    ] is False
    assert result["observations"]["provider"]["settings"]["sourceFilesReopened"] is True
    assert result["evaluatorOnly"]["decodedAndValidated"] is True
    assert result["evaluatorOnly"]["rgbaBytesPersisted"] is False
    assert result["evaluatorOnly"]["masksOrLandmarksDerived"] is False
    assert result["evaluatorOnly"]["mountedIntoContender"] is False
    assert result["lineage"]["selectedIdentity"] == {
        "garmentId": "garment.demo_tshirt.reference_v1",
        "avatarContractId": "avatar.closy_reference_v1",
    }


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing_view", "ingested_fixture_roles_reordered_or_missing"),
        ("reordered_views", "ingested_fixture_roles_reordered_or_missing"),
        ("wrong_role", "ingested_fixture_roles_reordered_or_missing"),
        ("stale_byte_hash", "ingested_source_byte_hash_stale"),
        ("stale_decoded_hash", "ingested_source_decoded_hash_stale"),
        ("stale_pixel_hash", "ingested_source_pixel_hash_stale"),
        ("bad_dimensions", "ingested_source_dimensions_mismatch"),
        ("unapproved_path", "ingested_source_path_not_allowlisted"),
    ],
)
def test_source_backed_observations_fail_closed_on_identity_breaks(
    mutation: str, expected_code: str
) -> None:
    result = _build()
    manifest = deepcopy(result["manifest"])
    private = deepcopy(result["ingest"].private_record)

    if mutation == "missing_view":
        manifest["fixtures"] = manifest["fixtures"][1:]
    elif mutation == "reordered_views":
        manifest["fixtures"][0], manifest["fixtures"][1] = (
            manifest["fixtures"][1],
            manifest["fixtures"][0],
        )
    elif mutation == "wrong_role":
        manifest["fixtures"][0]["role"] = "side"
    elif mutation == "stale_byte_hash":
        manifest["fixtures"][0]["expectedSha256"] = "0" * 64
    elif mutation == "stale_decoded_hash":
        manifest["fixtures"][0]["expectedDecodedContentHash"] = "0" * 64
    elif mutation == "stale_pixel_hash":
        manifest["fixtures"][0]["decodedPixelHash"] = "0" * 64
    elif mutation == "bad_dimensions":
        manifest["fixtures"][0]["decodedDimensions"]["width"] += 1
    elif mutation == "unapproved_path":
        manifest["fixtures"][0]["relativePath"] = "../outside.png"
    else:  # pragma: no cover - parameter table is exhaustive
        raise AssertionError(mutation)

    with pytest.raises(RasterVisualParseError) as error:
        build_tshirt_visual_observations_from_ingested_rasters(
            manifest=manifest,
            input_root=FIXTURE_ROOT,
            private_record=private,
            normalization_record=result["ingest"].normalization_record,
        )

    assert error.value.code == expected_code


def test_source_backed_observations_reject_swapped_private_view_join() -> None:
    result = _build()
    private = deepcopy(result["ingest"].private_record)
    private["acceptedSources"][0]["viewId"], private["acceptedSources"][1]["viewId"] = (
        private["acceptedSources"][1]["viewId"],
        private["acceptedSources"][0]["viewId"],
    )

    with pytest.raises(RasterVisualParseError) as error:
        build_tshirt_visual_observations_from_ingested_rasters(
            manifest=result["manifest"],
            input_root=FIXTURE_ROOT,
            private_record=private,
            normalization_record=result["ingest"].normalization_record,
        )

    assert error.value.code == "ingested_private_view_join_stale"


@pytest.mark.parametrize(
    ("control", "failed_check"),
    [
        ("blank", "front_foreground_coverage"),
        ("blurred", "front_focus"),
        ("clipped", "front_clipping"),
        ("duplicate", "view_diversity"),
        ("wrong_role", "view_roles"),
        ("occluded", "front_occlusion"),
    ],
)
def test_exact_quality_rejects_predeclared_capture_controls(
    control: str, failed_check: str
) -> None:
    result = _build()
    manifest = deepcopy(result["manifest"])
    ingest = deepcopy(result["ingest"])
    observations = deepcopy(result["observations"])
    front_stats = ingest.private_record["acceptedSources"][0]["pixelStats"]

    if control == "blank":
        front_stats["foregroundCoverage"] = 0.0
    elif control == "blurred":
        front_stats["sharpnessScore"] = 0.0
    elif control == "clipped":
        front_stats["combinedClipFraction"] = 1.0
    elif control == "duplicate":
        ingest.private_record["acceptedSources"][1]["decodedContentSha256"] = (
            ingest.private_record["acceptedSources"][0]["decodedContentSha256"]
        )
    elif control == "wrong_role":
        manifest["fixtures"][0]["role"] = "side"
    elif control == "occluded":
        front_view = observations["views"][0]
        occlusion = next(
            mask
            for mask in front_view["masks"]
            if mask["semanticId"] == "component.occlusion_uncertainty"
        )
        occlusion["pixelCountFraction"] = 0.9
    else:  # pragma: no cover - parameter table is exhaustive
        raise AssertionError(control)

    quality = evaluate_exact_raster_quality(
        manifest=manifest,
        ingest=ingest,
        observations=observations,
        thresholds=result["thresholds"],
    )

    assert quality["overallStatus"] == "fail"
    assert failed_check in quality["failedChecks"]


def test_frozen_manifest_rejects_unsafe_policy_and_identity(tmp_path: Path) -> None:
    manifest = _json(MANIFEST_PATH)
    manifest["policy"]["allowNetwork"] = True
    unsafe = tmp_path / "unsafe.json"
    write_canonical_json(unsafe, manifest)

    with pytest.raises(ExactRasterIdentityError) as error:
        load_exact_raster_manifest(unsafe)

    assert str(error.value) == "exact_manifest_policy_unsafe"


def test_evidence_generation_is_deterministic_and_keeps_portable_scope_clean(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "closy-forge"
    fixture_target = package_root / "fixtures" / "d0_exact_raster_v2"
    fixture_target.mkdir(parents=True)
    for source in FIXTURE_ROOT.rglob("*"):
        if source.is_file():
            destination = fixture_target / source.relative_to(FIXTURE_ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())

    first = generate_exact_raster_identity_evidence(
        package_root=package_root, source_lock_sha="38dfb56" + "0" * 33
    )
    first_manifest = first["manifest"].read_bytes()
    second = generate_exact_raster_identity_evidence(
        package_root=package_root, source_lock_sha="38dfb56" + "0" * 33
    )

    assert second["manifest"].read_bytes() == first_manifest
    portable_values = [
        read_json(path) for path in sorted((second["root"] / "portable").glob("*.json"))
    ]
    portable_keys = set().union(*(_all_keys(value) for value in portable_values))
    portable_text = "".join(canonical_dumps(value) for value in portable_values)
    assert "sourceByteSha256" not in portable_keys
    assert "decodedContentSha256" not in portable_keys
    assert str(FIXTURE_ROOT) not in portable_text
    assert (second["root"] / "qualification" / "visual_overlay_front.svg").is_file()


def _build() -> dict[str, Any]:
    return build_exact_raster_lineage(
        manifest_path=MANIFEST_PATH,
        input_root=FIXTURE_ROOT,
        threshold_path=THRESHOLD_PATH,
    )


def _json(path: Path) -> dict[str, Any]:
    value = read_json(path)
    assert isinstance(value, dict)
    return value


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = {str(key) for key in value}
        for child in value.values():
            keys.update(_all_keys(child))
        return keys
    if isinstance(value, list):
        return {child_key for child in value for child_key in _all_keys(child)}
    return set()
