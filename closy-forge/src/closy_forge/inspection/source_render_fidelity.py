from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.appearance.bitmap_atlas import BITMAP_PATHS
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.inspection.cpu_raster import rasterize_settled_garment
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, sha256_file
from closy_forge.raster import DecodedPng, decode_png_rgba, encode_png_rgba
from closy_forge.visual_understanding.raster_parser import (
    LEFT_SLEEVE_RGBA,
    LOGO_RGBA,
    RIGHT_SLEEVE_RGBA,
    TORSO_RGBA,
)

SOURCE_RENDER_FIDELITY_VERSION = "closy.source_render_fidelity.decoded_cpu_raster.d0_v1"

_THRESHOLDS = {
    "minimumSilhouetteIoU": 0.30,
    "maximumBoundaryChamferNormalised": 0.095,
    "maximumLandmarkReprojectionNormalised": 0.14,
    "maximumForegroundLinearSrgbMae": 0.24,
    "minimumLogoIoU": 0.02,
    "maximumLogoDisplacementNormalised": 0.14,
    "maximumRenderedSeamDiscontinuityLinear": 0.22,
    "minimumVisibleCoverage": 0.30,
    "maximumGeneratedRegionShare": 0.55,
    "maximumFrontRearSilhouetteDelta": 0.12,
}


def write_source_render_fidelity_artifacts(
    package_dir: Path,
    *,
    visual_observations: Mapping[str, Any],
    settled_mesh: MeshSet,
) -> dict[str, Any]:
    atlas = decode_png_rgba((package_dir / BITMAP_PATHS["baseColor"]).read_bytes())
    contribution = decode_png_rgba((package_dir / BITMAP_PATHS["sourceContribution"]).read_bytes())
    view_records: list[dict[str, Any]] = []
    for view in _views(visual_observations):
        label = str(view.get("label", "front"))
        source_path = f"source/public_fixture/{_safe_label(label)}.png"
        source = decode_png_rgba((package_dir / source_path).read_bytes())
        rendered = rasterize_settled_garment(
            settled_mesh,
            label=label,
            width=source.width,
            height=source.height,
            camera=_mapping(view.get("camera")),
            texture_sampler=_atlas_sampler(atlas, label),
        )
        rendered_contribution = rasterize_settled_garment(
            settled_mesh,
            label=label,
            width=source.width,
            height=source.height,
            camera=_mapping(view.get("camera")),
            texture_sampler=_atlas_sampler(contribution, label),
        )
        render_path = f"reports/fidelity/rendered_{_safe_label(label)}.png"
        contribution_path = f"reports/fidelity/rendered_contribution_{_safe_label(label)}.png"
        _write_bytes(
            package_dir / render_path,
            encode_png_rgba(rendered.width, rendered.height, rendered.rgba),
        )
        _write_bytes(
            package_dir / contribution_path,
            encode_png_rgba(
                rendered_contribution.width,
                rendered_contribution.height,
                rendered_contribution.rgba,
            ),
        )
        metrics = compare_decoded_source_and_render(
            source,
            decode_png_rgba((package_dir / render_path).read_bytes()),
            contribution=decode_png_rgba((package_dir / contribution_path).read_bytes()),
        )
        view_records.append(
            {
                "viewId": str(view.get("viewId", "")),
                "label": label,
                "sourcePath": source_path,
                "sourceSha256": sha256_file(package_dir / source_path),
                "renderPath": render_path,
                "renderSha256": sha256_file(package_dir / render_path),
                "contributionPath": contribution_path,
                "contributionSha256": sha256_file(package_dir / contribution_path),
                "camera": rendered.camera,
                "renderedTriangleCount": rendered.rendered_triangle_count,
                "renderedForegroundPixels": len(rendered.foreground),
                "metrics": metrics,
                "accepted": _metrics_pass(metrics),
            }
        )
    aggregate = _aggregate_metrics(view_records)
    accepted_d0 = all(record["accepted"] for record in view_records) and _aggregate_pass(aggregate)
    controls = _corruption_controls(package_dir, view_records)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "source_render_fidelity.demo_tshirt_d0_v1",
        "stageVersion": SOURCE_RENDER_FIDELITY_VERSION,
        "status": "pass_d0_public_fixture" if accepted_d0 else "fail_d0_public_fixture",
        "garmentId": "garment.demo_tshirt.reference_v1",
        "garmentClass": "tshirt",
        "renderer": {
            "id": "closy_independent_cpu_triangle_raster_v1",
            "dependency": "python_stdlib_only",
            "width": 128,
            "height": 160,
            "projection": "persisted_source_orthographic_camera_metadata",
            "backgroundAlpha": 0,
            "sourceFixtureGeneratorReused": False,
            "metricImplementationUsedForRendering": False,
        },
        "sourceSettledMesh": {
            "path": "simulation/simulation_mesh.glb",
            "contentHash": geometry_content_hash(settled_mesh),
            "fittedParametersPath": "fitting/tshirt_fit.json",
            "baseColorAtlasPath": BITMAP_PATHS["baseColor"],
            "sourceContributionPath": BITMAP_PATHS["sourceContribution"],
        },
        "viewComparisons": view_records,
        "aggregate": aggregate,
        "thresholds": {
            **_THRESHOLDS,
            "classification": "fixture_calibrated_provisional_not_product_derived",
            "calibrationFixture": "project_authored_public_d0_tshirt_pixels_v1",
            "foregroundColorSpace": "linear_srgb_unpremultiplied_foreground_mean",
            "backgroundIncludedInColorMetric": False,
        },
        "thresholdBoundaryCases": _threshold_boundary_cases(),
        "corruptionControls": controls,
        "acceptanceTiers": {
            "acceptedForD0PublicFixture": {
                "status": "pass" if accepted_d0 else "fail",
                "accepted": accepted_d0,
                "run": True,
            },
            "acceptedForPrivateUserCapture": {
                "status": "not_run",
                "accepted": False,
                "run": False,
            },
            "acceptedForProviderGeneratedShell": {
                "status": "not_run",
                "accepted": False,
                "run": False,
            },
            "acceptedForHumanVisualReview": {
                "status": "not_run",
                "accepted": False,
                "run": False,
            },
            "acceptedForCanonicalProduction": {
                "status": "blocked_higher_tiers_absent",
                "accepted": False,
                "run": False,
            },
        },
        "policy": {
            "publicSyntheticFixtureOnly": True,
            "containsUserImagery": False,
            "externalApis": False,
            "humanReviewExecuted": False,
            "providerGeneratedShellExecuted": False,
        },
        "limitations": [
            "fixture_calibrated_thresholds_are_not_product_acceptance_thresholds",
            "cpu_raster_uses_fixed_d0_avatar_projection_not_mobile_gpu_renderer",
            "private_user_provider_and_human_tiers_not_run",
            "canonical_production_acceptance_false",
        ],
        "integrity": {"sourceRenderFidelityHash": ""},
    }
    report["integrity"]["sourceRenderFidelityHash"] = hash_source_render_fidelity_report(report)
    write_canonical_json(
        package_dir / "reports" / "fidelity" / "source_render_fidelity.json", report
    )
    return report


def hash_source_render_fidelity_report(report: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(report))
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["sourceRenderFidelityHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def validate_persisted_source_render_fidelity(
    package_dir: Path, report: Mapping[str, Any]
) -> dict[str, Any]:
    if hash_source_render_fidelity_report(report) != _mapping(report.get("integrity")).get(
        "sourceRenderFidelityHash"
    ):
        raise ValueError("source_render_fidelity_hash_mismatch")
    recomputed_records = []
    threshold_results: list[bool] = []
    for record in report.get("viewComparisons", []):
        if not isinstance(record, Mapping):
            raise ValueError("source_render_view_record_invalid")
        source_path = str(record.get("sourcePath", ""))
        render_path = str(record.get("renderPath", ""))
        contribution_path = str(record.get("contributionPath", ""))
        if sha256_file(package_dir / source_path) != record.get("sourceSha256"):
            raise ValueError("source_render_source_hash_mismatch")
        if sha256_file(package_dir / render_path) != record.get("renderSha256"):
            raise ValueError("source_render_output_hash_mismatch")
        if sha256_file(package_dir / contribution_path) != record.get("contributionSha256"):
            raise ValueError("source_render_contribution_hash_mismatch")
        source = decode_png_rgba((package_dir / source_path).read_bytes())
        rendered = decode_png_rgba((package_dir / render_path).read_bytes())
        contribution = decode_png_rgba((package_dir / contribution_path).read_bytes())
        metrics = compare_decoded_source_and_render(source, rendered, contribution=contribution)
        if canonical_dumps(metrics) != canonical_dumps(record.get("metrics", {})):
            raise ValueError("source_render_metrics_recompute_mismatch")
        threshold_passed = _metrics_pass(metrics)
        if record.get("accepted") is not threshold_passed:
            raise ValueError("source_render_view_acceptance_mismatch")
        threshold_results.append(threshold_passed)
        recomputed_records.append(
            {"label": record.get("label"), "metrics": metrics, "accepted": threshold_passed}
        )
    if not recomputed_records:
        raise ValueError("source_render_comparisons_missing")
    tiers = _mapping(report.get("acceptanceTiers"))
    public = _mapping(tiers.get("acceptedForD0PublicFixture"))
    canonical = _mapping(tiers.get("acceptedForCanonicalProduction"))
    recomputed_aggregate = _aggregate_metrics(recomputed_records)
    if canonical_dumps(recomputed_aggregate) != canonical_dumps(report.get("aggregate", {})):
        raise ValueError("source_render_aggregate_recompute_mismatch")
    expected_public_acceptance = all(threshold_results) and _aggregate_pass(recomputed_aggregate)
    expected_public_status = "pass" if expected_public_acceptance else "fail"
    expected_report_status = (
        "pass_d0_public_fixture" if expected_public_acceptance else "fail_d0_public_fixture"
    )
    if (
        public.get("run") is not True
        or public.get("accepted") is not expected_public_acceptance
        or public.get("status") != expected_public_status
        or report.get("status") != expected_report_status
        or canonical.get("accepted") is not False
    ):
        raise ValueError("source_render_acceptance_tiers_invalid")
    for tier in [
        "acceptedForPrivateUserCapture",
        "acceptedForProviderGeneratedShell",
        "acceptedForHumanVisualReview",
    ]:
        state = _mapping(tiers.get(tier))
        if state.get("status") != "not_run" or state.get("accepted") is not False:
            raise ValueError("source_render_not_run_tier_deleted_or_promoted")
    controls = report.get("corruptionControls", [])
    controls_are_valid = (
        isinstance(controls, list)
        and bool(controls)
        and all(isinstance(control, Mapping) for control in controls)
    )
    canonical_controls_pass = controls_are_valid and all(
        control.get("detected") is True for control in controls if isinstance(control, Mapping)
    )
    if not controls_are_valid or (expected_public_acceptance and not canonical_controls_pass):
        raise ValueError("source_render_corruption_control_failed")
    return {
        "status": "pass",
        "recomputedViewCount": len(recomputed_records),
        "acceptedForD0PublicFixture": expected_public_acceptance,
    }


def compare_decoded_source_and_render(
    source: DecodedPng,
    rendered: DecodedPng,
    *,
    contribution: DecodedPng | None = None,
) -> dict[str, Any]:
    if (source.width, source.height) != (rendered.width, rendered.height):
        raise ValueError("source_render_dimensions_mismatch")
    source_mask = _source_foreground(source)
    render_mask = _alpha_foreground(rendered)
    if not source_mask or not render_mask:
        return _failed_blank_metrics(len(source_mask), len(render_mask))
    width, height = source.width, source.height
    source_boundary = _boundary(source_mask, width, height)
    render_boundary = _boundary(render_mask, width, height)
    source_landmarks = _mask_landmarks(source_mask, width, height)
    render_landmarks = _mask_landmarks(render_mask, width, height)
    landmark_error = _mean(
        math.hypot(
            source_landmarks[key][0] - render_landmarks[key][0],
            source_landmarks[key][1] - render_landmarks[key][1],
        )
        for key in source_landmarks
    )
    source_logo = _color_mask(source, LOGO_RGBA)
    render_logo = _color_mask(rendered, LOGO_RGBA)
    logo_union = source_logo | render_logo
    logo_iou = len(source_logo & render_logo) / len(logo_union) if logo_union else 1.0
    logo_displacement = (
        _centroid_distance(source_logo, render_logo, width, height)
        if source_logo or render_logo
        else 0.0
    )
    source_mean = _mean_linear_rgb(source, source_mask)
    render_mean = _mean_linear_rgb(rendered, render_mask)
    color_mae = _mean(abs(source_mean[index] - render_mean[index]) for index in range(3))
    generated_share = _generated_share(contribution, render_mask) if contribution else 1.0
    return {
        "silhouetteIoU": _round(_iou(source_mask, render_mask)),
        "boundaryChamferNormalised": _round(
            _chamfer(source_boundary, render_boundary, width, height)
        ),
        "landmarkReprojectionNormalised": _round(landmark_error),
        "foregroundLinearSrgbMae": _round(color_mae),
        "logoIoU": _round(logo_iou),
        "logoDisplacementNormalised": _round(logo_displacement),
        "logoMetricApplicable": bool(source_logo),
        "renderedSeamDiscontinuityLinear": _round(_rendered_discontinuity(rendered, render_mask)),
        "visibleCoverage": _round(len(source_mask & render_mask) / len(source_mask)),
        "generatedRegionShare": _round(generated_share),
        "sourceForegroundPixels": len(source_mask),
        "renderForegroundPixels": len(render_mask),
        "blankOrTransparent": False,
        "backgroundIncludedInColorMetric": False,
        "foregroundColorSpace": "linear_srgb",
    }


def _corruption_controls(
    package_dir: Path, view_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    front = next(record for record in view_records if record["label"] == "front")
    source = decode_png_rgba((package_dir / front["sourcePath"]).read_bytes())
    rendered = decode_png_rgba((package_dir / front["renderPath"]).read_bytes())
    contribution = decode_png_rgba((package_dir / front["contributionPath"]).read_bytes())
    baseline = compare_decoded_source_and_render(source, rendered, contribution=contribution)
    controls = []
    for control_id, corrupted in [
        ("one_pixel_mask_shift", _shift_image(rendered, 1, 0)),
        ("multi_pixel_mask_shift", _shift_image(rendered, 8, 0)),
        ("foreground_colour_cast", _color_cast(rendered, (38, -18, 24))),
        ("logo_translation", _translate_logo(rendered, 12)),
        ("texture_swap", _swap_blue_and_logo(rendered)),
        ("camera_perturbation_proxy", _shift_image(rendered, 14, 3)),
        ("blank_render", _blank(rendered)),
        ("wrong_alpha", _wrong_alpha(rendered)),
        ("seam_break", _seam_break(rendered)),
    ]:
        metrics = compare_decoded_source_and_render(source, corrupted, contribution=contribution)
        changed = canonical_dumps(metrics) != canonical_dumps(baseline)
        rejected = not _metrics_pass(metrics)
        pixel_hash_changed = sha256_bytes(corrupted.rgba) != sha256_bytes(rendered.rgba)
        detected = changed and pixel_hash_changed
        controls.append(
            {
                "controlId": control_id,
                "detected": detected,
                "overallRejected": rejected,
                "baselineSilhouetteIoU": baseline["silhouetteIoU"],
                "corruptSilhouetteIoU": metrics["silhouetteIoU"],
                "corruptBoundaryChamferNormalised": metrics["boundaryChamferNormalised"],
                "corruptForegroundLinearSrgbMae": metrics["foregroundLinearSrgbMae"],
                "corruptLogoIoU": metrics["logoIoU"],
                "pixelHashChanged": pixel_hash_changed,
            }
        )
    return controls


def _aggregate_metrics(view_records: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = [record["metrics"] for record in view_records]
    front = next(record for record in view_records if record["label"] == "front")
    rear = next(record for record in view_records if record["label"] == "back")
    return {
        "viewCount": len(metrics),
        "meanSilhouetteIoU": _round(_mean(item["silhouetteIoU"] for item in metrics)),
        "maximumBoundaryChamferNormalised": _round(
            max(float(item["boundaryChamferNormalised"]) for item in metrics)
        ),
        "meanForegroundLinearSrgbMae": _round(
            _mean(item["foregroundLinearSrgbMae"] for item in metrics)
        ),
        "frontRearSilhouetteDelta": _round(
            abs(float(front["metrics"]["silhouetteIoU"]) - float(rear["metrics"]["silhouetteIoU"]))
        ),
        "allViewsNonBlank": all(not item["blankOrTransparent"] for item in metrics),
    }


def _metrics_pass(metrics: Mapping[str, Any]) -> bool:
    logo_passes = not bool(metrics.get("logoMetricApplicable")) or (
        float(metrics.get("logoIoU", 0.0)) >= _THRESHOLDS["minimumLogoIoU"]
        and float(metrics.get("logoDisplacementNormalised", 1.0))
        <= _THRESHOLDS["maximumLogoDisplacementNormalised"]
    )
    return (
        not bool(metrics.get("blankOrTransparent", True))
        and float(metrics.get("silhouetteIoU", 0.0)) >= _THRESHOLDS["minimumSilhouetteIoU"]
        and float(metrics.get("boundaryChamferNormalised", 1.0))
        <= _THRESHOLDS["maximumBoundaryChamferNormalised"]
        and float(metrics.get("landmarkReprojectionNormalised", 1.0))
        <= _THRESHOLDS["maximumLandmarkReprojectionNormalised"]
        and float(metrics.get("foregroundLinearSrgbMae", 1.0))
        <= _THRESHOLDS["maximumForegroundLinearSrgbMae"]
        and logo_passes
        and float(metrics.get("renderedSeamDiscontinuityLinear", 1.0))
        <= _THRESHOLDS["maximumRenderedSeamDiscontinuityLinear"]
        and float(metrics.get("visibleCoverage", 0.0)) >= _THRESHOLDS["minimumVisibleCoverage"]
        and float(metrics.get("generatedRegionShare", 1.0))
        <= _THRESHOLDS["maximumGeneratedRegionShare"]
    )


def _aggregate_pass(aggregate: Mapping[str, Any]) -> bool:
    return (
        bool(aggregate.get("allViewsNonBlank"))
        and float(aggregate.get("frontRearSilhouetteDelta", 1.0))
        <= _THRESHOLDS["maximumFrontRearSilhouetteDelta"]
    )


def _threshold_boundary_cases() -> list[dict[str, Any]]:
    epsilon = 0.000001
    return [
        {
            "metric": "silhouetteIoU",
            "threshold": _THRESHOLDS["minimumSilhouetteIoU"],
            "justPassing": _round(_THRESHOLDS["minimumSilhouetteIoU"] + epsilon),
            "justFailing": _round(_THRESHOLDS["minimumSilhouetteIoU"] - epsilon),
            "passingAccepted": True,
            "failingAccepted": False,
        },
        {
            "metric": "foregroundLinearSrgbMae",
            "threshold": _THRESHOLDS["maximumForegroundLinearSrgbMae"],
            "justPassing": _round(_THRESHOLDS["maximumForegroundLinearSrgbMae"] - epsilon),
            "justFailing": _round(_THRESHOLDS["maximumForegroundLinearSrgbMae"] + epsilon),
            "passingAccepted": True,
            "failingAccepted": False,
        },
    ]


def _atlas_sampler(atlas: DecodedPng, label: str) -> Any:
    def sample(panel_id: str, uv: tuple[float, float]) -> tuple[int, int, int, int]:
        use_rear = label == "back" or panel_id == "panel.back"
        if panel_id in {"panel.front", "panel.back"}:
            u = max(0.0, min(1.0, (uv[0] + 0.35) / 0.70))
            v = max(0.0, min(1.0, uv[1] / 0.68))
            # The settled D0 shell's visible torso lobe is sheared relative to
            # pattern space. This bounded unwrap maps that lobe to the decoded
            # source-backed torso region; it never paints pixels after raster.
            local_u = 0.40 + u * 0.40
            atlas_v = (1.0 - v) * 1.02
        elif panel_id == "panel.sleeve.left":
            u = max(0.0, min(1.0, (uv[0] + 0.1271) / 0.2542))
            v = max(0.0, min(1.0, uv[1] / 0.3054))
            local_u = u * 0.38
            atlas_v = 0.06 + (1.0 - v) * 0.45
        elif panel_id == "panel.sleeve.right":
            u = max(0.0, min(1.0, (uv[0] + 0.1271) / 0.2542))
            v = max(0.0, min(1.0, uv[1] / 0.3054))
            local_u = 0.62 + u * 0.38
            atlas_v = 0.06 + (1.0 - v) * 0.45
        else:
            local_u = 0.50
            atlas_v = 0.08
        atlas_u = (0.5 + local_u * 0.5) if use_rear else (local_u * 0.5)
        x = min(atlas.width - 1, max(0, int(atlas_u * atlas.width)))
        y = min(atlas.height - 1, max(0, int(atlas_v * atlas.height)))
        offset = (y * atlas.width + x) * 4
        return tuple(atlas.rgba[offset : offset + 4])  # type: ignore[return-value]

    return sample


def _source_foreground(image: DecodedPng) -> set[int]:
    colors = {TORSO_RGBA, LEFT_SLEEVE_RGBA, RIGHT_SLEEVE_RGBA, LOGO_RGBA}
    return {
        offset // 4
        for offset in range(0, len(image.rgba), 4)
        if tuple(image.rgba[offset : offset + 4]) in colors
    }


def _alpha_foreground(image: DecodedPng) -> set[int]:
    return {offset // 4 for offset in range(0, len(image.rgba), 4) if image.rgba[offset + 3] >= 128}


def _color_mask(image: DecodedPng, color: tuple[int, int, int, int]) -> set[int]:
    return {
        offset // 4
        for offset in range(0, len(image.rgba), 4)
        if tuple(image.rgba[offset : offset + 4]) == color
    }


def _mean_linear_rgb(image: DecodedPng, mask: set[int]) -> tuple[float, float, float]:
    values = [
        tuple(_srgb_to_linear(image.rgba[index * 4 + channel] / 255.0) for channel in range(3))
        for index in mask
    ]
    return (
        _mean(item[0] for item in values),
        _mean(item[1] for item in values),
        _mean(item[2] for item in values),
    )


def _srgb_to_linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _mask_landmarks(mask: set[int], width: int, height: int) -> dict[str, tuple[float, float]]:
    xs = [index % width for index in mask]
    ys = [index // width for index in mask]
    min_x, max_x = min(xs) / width, max(xs) / width
    min_y, max_y = min(ys) / height, max(ys) / height
    return {
        "top": ((min_x + max_x) / 2, min_y),
        "left": (min_x, (min_y + max_y) / 2),
        "right": (max_x, (min_y + max_y) / 2),
        "bottom": ((min_x + max_x) / 2, max_y),
        "center": ((min_x + max_x) / 2, (min_y + max_y) / 2),
    }


def _centroid_distance(left: set[int], right: set[int], width: int, height: int) -> float:
    if not left or not right:
        return 1.0
    left_center = (
        _mean(index % width for index in left) / width,
        _mean(index // width for index in left) / height,
    )
    right_center = (
        _mean(index % width for index in right) / width,
        _mean(index // width for index in right) / height,
    )
    return math.hypot(left_center[0] - right_center[0], left_center[1] - right_center[1])


def _rendered_discontinuity(image: DecodedPng, mask: set[int]) -> float:
    differences = []
    for index in mask:
        x = index % image.width
        if x + 1 >= image.width or index + 1 not in mask:
            continue
        left = index * 4
        right = (index + 1) * 4
        differences.append(
            _mean(
                abs(
                    _srgb_to_linear(image.rgba[left + channel] / 255.0)
                    - _srgb_to_linear(image.rgba[right + channel] / 255.0)
                )
                for channel in range(3)
            )
        )
    if not differences:
        return 1.0
    ordered = sorted(differences)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]


def _generated_share(contribution: DecodedPng, render_mask: set[int]) -> float:
    generated = 0
    observed = 0
    for index in render_mask:
        offset = index * 4
        color = tuple(contribution.rgba[offset : offset + 3])
        if color == (0, 0, 255):
            generated += 1
        else:
            observed += 1
    return generated / max(1, generated + observed)


def _failed_blank_metrics(source_count: int, render_count: int) -> dict[str, Any]:
    return {
        "silhouetteIoU": 0.0,
        "boundaryChamferNormalised": 1.0,
        "landmarkReprojectionNormalised": 1.0,
        "foregroundLinearSrgbMae": 1.0,
        "logoIoU": 0.0,
        "logoDisplacementNormalised": 1.0,
        "renderedSeamDiscontinuityLinear": 1.0,
        "visibleCoverage": 0.0,
        "generatedRegionShare": 1.0,
        "sourceForegroundPixels": source_count,
        "renderForegroundPixels": render_count,
        "blankOrTransparent": True,
        "backgroundIncludedInColorMetric": False,
        "foregroundColorSpace": "linear_srgb",
    }


def _shift_image(image: DecodedPng, dx: int, dy: int) -> DecodedPng:
    output = bytearray((246, 244, 239, 0) * image.width * image.height)
    for y in range(image.height):
        for x in range(image.width):
            nx, ny = x + dx, y + dy
            if 0 <= nx < image.width and 0 <= ny < image.height:
                source = (y * image.width + x) * 4
                target = (ny * image.width + nx) * 4
                output[target : target + 4] = image.rgba[source : source + 4]
    return DecodedPng(image.width, image.height, bytes(output))


def _color_cast(image: DecodedPng, delta: tuple[int, int, int]) -> DecodedPng:
    output = bytearray(image.rgba)
    for offset in range(0, len(output), 4):
        if output[offset + 3] < 128:
            continue
        for channel in range(3):
            output[offset + channel] = max(0, min(255, output[offset + channel] + delta[channel]))
    return DecodedPng(image.width, image.height, bytes(output))


def _translate_logo(image: DecodedPng, dx: int) -> DecodedPng:
    output = bytearray(image.rgba)
    logo = _color_mask(image, LOGO_RGBA)
    for index in logo:
        output[index * 4 : index * 4 + 4] = bytes(TORSO_RGBA)
    for index in logo:
        x, y = index % image.width, index // image.width
        nx = x + dx
        if 0 <= nx < image.width:
            target = (y * image.width + nx) * 4
            output[target : target + 4] = bytes(LOGO_RGBA)
    return DecodedPng(image.width, image.height, bytes(output))


def _swap_blue_and_logo(image: DecodedPng) -> DecodedPng:
    output = bytearray(image.rgba)
    for offset in range(0, len(output), 4):
        if output[offset + 3] >= 128:
            output[offset : offset + 4] = bytes((118, 48, 168, 255))
    return DecodedPng(image.width, image.height, bytes(output))


def _blank(image: DecodedPng) -> DecodedPng:
    return DecodedPng(
        image.width, image.height, bytes((246, 244, 239, 0)) * image.width * image.height
    )


def _wrong_alpha(image: DecodedPng) -> DecodedPng:
    output = bytearray(image.rgba)
    for offset in range(3, len(output), 4):
        output[offset] = 0
    return DecodedPng(image.width, image.height, bytes(output))


def _seam_break(image: DecodedPng) -> DecodedPng:
    output = bytearray(image.rgba)
    for y in range(image.height):
        for x in range(image.width // 2 - 4, image.width):
            offset = (y * image.width + x) * 4
            if output[offset + 3] >= 128:
                output[offset : offset + 4] = bytes((246, 244, 239, 0))
    return DecodedPng(image.width, image.height, bytes(output))


def _boundary(mask: set[int], width: int, height: int) -> set[int]:
    result = set()
    for index in mask:
        x, y = index % width, index // width
        neighbours = [
            index - 1 if x > 0 else -1,
            index + 1 if x + 1 < width else -1,
            index - width if y > 0 else -1,
            index + width if y + 1 < height else -1,
        ]
        if any(neighbour not in mask for neighbour in neighbours):
            result.add(index)
    return result


def _chamfer(left: set[int], right: set[int], width: int, height: int) -> float:
    if not left or not right:
        return 1.0
    diagonal = math.hypot(width, height)

    def directed(source: set[int], target: set[int]) -> float:
        source_sample = sorted(source)[:: max(1, len(source) // 96)]
        target_points = [(item % width, item // width) for item in sorted(target)]
        return (
            _mean(
                math.sqrt(
                    min(
                        ((item % width) - tx) ** 2 + ((item // width) - ty) ** 2
                        for tx, ty in target_points
                    )
                )
                for item in source_sample
            )
            / diagonal
        )

    return (directed(left, right) + directed(right, left)) / 2


def _iou(left: set[int], right: set[int]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _views(visual: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [view for view in visual.get("views", []) if isinstance(view, Mapping)]


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _safe_label(label: str) -> str:
    return "".join(char if char.isalnum() or char in "_-" else "_" for char in label)


def _mean(values: Any) -> float:
    items = list(values)
    return sum(float(value) for value in items) / max(1, len(items))


def _round(value: float) -> float:
    return round(float(value), 9)
