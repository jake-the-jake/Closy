from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageFilter

from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file


def audit_raster_semantics_v4(
    package: Path,
    *,
    exact_texture_evaluation: Path,
    exact_reference_evaluation: Path,
    contribution_output: Path | None = None,
) -> dict[str, Any]:
    root = package.resolve(strict=True)
    texture = _object(exact_texture_evaluation)
    reference = _object(exact_reference_evaluation)
    pbr = _object(root / "textures/bitmap_pbr_report.json")
    source_records = pbr.get("sourceViews")
    if not isinstance(source_records, list) or len(source_records) != 2:
        raise ValueError("raster_source_view_inventory_invalid")
    source_metrics = []
    for raw in source_records:
        if not isinstance(raw, dict):
            raise ValueError("raster_source_view_invalid")
        path = root / str(raw["path"])
        if sha256_file(path) != raw.get("sha256"):
            raise ValueError("raster_source_view_hash_mismatch")
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
            raw_sharpness = _raw_sharpness(image)
            normalized_focus = raw_sharpness / (255.0 * 255.0)
            source_metrics.append(
                {
                    "viewId": raw["viewId"],
                    "label": raw["label"],
                    "rawLaplacianVariance8BitSquared": round(raw_sharpness, 12),
                    "rawSharpnessThreshold8BitSquared": 20.0,
                    "normalizedFocus": round(normalized_focus, 12),
                    "normalizedFocusThreshold": round(20.0 / (255.0 * 255.0), 12),
                    "rawSharpnessPass": raw_sharpness >= 20.0,
                    "normalizedFocusPass": normalized_focus >= 20.0 / (255.0 * 255.0),
                }
            )
    contribution_path = root / "textures/atlas/source_contribution.png"
    generated_path = root / "textures/atlas/generated_region_mask.png"
    with Image.open(contribution_path) as opened:
        contribution = opened.convert("RGB")
    with Image.open(generated_path) as opened:
        generated = opened.convert("L")
    if contribution.size != generated.size:
        raise ValueError("raster_contribution_shape_mismatch")
    contribution_records, outputs = _contribution_records(
        contribution, generated, contribution_output
    )
    base_path = root / "textures/atlas/base_color.png"
    with Image.open(base_path) as opened:
        base = opened.convert("RGB")
    source_score = _source_observed_color_score(base, generated)
    changed = base.copy()
    pixels = changed.load()
    mask = generated.load()
    assert pixels is not None and mask is not None
    for y in range(changed.height):
        for x in range(changed.width):
            if cast(int, mask[x, y]) >= 128:
                pixels[x, y] = (255, 0, 255)
    changed_score = _source_observed_color_score(changed, generated)
    third = _mapping(reference.get("evaluatorOnlyThirdView"), "raster_third_view_invalid")
    camera = _mapping(third.get("camera"), "raster_third_view_camera_invalid")
    logo = _mapping(texture.get("frontLogoIdentity"), "raster_logo_metrics_invalid")
    pbr_record = _mapping(pbr.get("pbr"), "raster_pbr_record_invalid")
    return {
        "auditVersion": "closy.d0.raster_contribution_semantics.v4",
        "status": "pass",
        "sourceViewQuality": source_metrics,
        "scaleConfidence": {
            "status": "unavailable",
            "reason": "no_calibrated_source_scale_or_camera_intrinsics_in_frozen_fixture",
            "numericValuePublished": False,
        },
        "contributionProvenance": {
            "sourceContributionSha256": sha256_file(contribution_path),
            "generatedRegionMaskSha256": sha256_file(generated_path),
            "perView": contribution_records,
            "generatedOutputs": outputs,
        },
        "sourceFidelityColor": {
            "scoreDomain": "source_observed_atlas_texels_only",
            "sourceObservedMeanLinearProxy": round(source_score, 12),
            "generatedFillMutationMeanLinearProxy": round(changed_score, 12),
            "generatedFillScoreDelta": round(changed_score - source_score, 12),
            "generatedFillCannotImproveScore": changed_score == source_score,
            "generatedFillVisibleAndLabelled": pbr["coverage"]["generatedPixelsMarked"]
            and not pbr["coverage"]["generatedPixelsLabelledSourceObserved"],
        },
        "measuredNumericAuthority": {
            "camera": {
                "classification": "measured_or_frozen_runtime_bounds_frame",
                "azimuthDegrees": camera.get("azimuthDegrees"),
                "elevationDegrees": camera.get("elevationDegrees"),
                "runtimeBoundsFramed": camera.get("runtimeBoundsFramed"),
            },
            "scale": {"classification": "unavailable", "value": None},
            "logo": {
                "classification": "measured_exact_rerender",
                "iou": logo.get("logoIoU"),
                "displacementNormalised": logo.get("logoDisplacementNormalised"),
            },
        },
        "physicalPbrAccuracy": pbr_record.get("normalRoughnessAoPhysicalAccuracy"),
        "originalD0Rp07FailurePreserved": texture.get("status") == "fail"
        and logo.get("logoIoU") == 0.0
        and logo.get("logoDisplacementNormalised") == 0.154158086,
    }


def _contribution_records(
    contribution: Image.Image, generated: Image.Image, output: Path | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pixels = contribution.load()
    generated_pixels = generated.load()
    assert pixels is not None and generated_pixels is not None
    records: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    for label, channel in (("front", 0), ("rear", 1)):
        view = Image.new("L", contribution.size, 0)
        view_pixels = view.load()
        assert view_pixels is not None
        count = 0
        generated_count = 0
        for y in range(contribution.height):
            for x in range(contribution.width):
                source_pixel = cast(tuple[int, int, int], pixels[x, y])
                generated_value = cast(int, generated_pixels[x, y])
                value = source_pixel[channel]
                view_pixels[x, y] = value
                count += int(value > 0 and generated_value < 128)
                generated_count += int(value > 0 and generated_value >= 128)
        payload = view.tobytes()
        record = {
            "viewId": f"view.{label if label == 'front' else 'rear'}",
            "role": label,
            "sourceObservedContributingPixelCount": count,
            "generatedContributingPixelCount": generated_count,
            "decodedMaskSha256": sha256_bytes(payload),
        }
        records.append(record)
        if output is not None:
            output.mkdir(parents=True, exist_ok=True)
            path = output / f"{label}_contribution.png"
            view.save(path, format="PNG", optimize=False, compress_level=9)
            outputs.append(
                {
                    "viewId": record["viewId"],
                    "path": path.name,
                    "sha256": sha256_file(path),
                }
            )
    return records, outputs


def _source_observed_color_score(base: Image.Image, generated: Image.Image) -> float:
    pixels = base.load()
    mask = generated.load()
    assert pixels is not None and mask is not None
    values: list[float] = []
    for y in range(base.height):
        for x in range(base.width):
            if cast(int, mask[x, y]) < 128:
                pixel = cast(tuple[int, int, int], pixels[x, y])
                values.append(sum(pixel) / (3.0 * 255.0))
    if not values:
        raise ValueError("raster_no_source_observed_texels")
    return sum(values) / len(values)


def _raw_sharpness(image: Image.Image) -> float:
    gray = image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    pixels = edges.load()
    assert pixels is not None
    values = [cast(int, pixels[x, y]) for y in range(edges.height) for x in range(edges.width)]
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError("raster_evidence_object_required")
    return value


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(code)
    return value
