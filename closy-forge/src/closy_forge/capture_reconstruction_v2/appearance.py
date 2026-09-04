from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .common import sha256_bytes
from .contestant import PixelObservation


@dataclass(frozen=True)
class AppearanceAtlas:
    width: int
    height: int
    rgba: bytes
    observed: bytes
    confidence: tuple[float, ...]
    provenance: tuple[str, ...]


def project_appearance(
    observations: list[PixelObservation],
    cameras: list[dict[str, Any]],
    *,
    size: int = 64,
    fitted_geometry_digest: str = "unavailable_fit_abstention",
) -> AppearanceAtlas:
    if len(observations) != len(cameras) or not observations:
        raise ValueError("appearance_observation_camera_denominator_invalid")
    accum = [[0.0, 0.0, 0.0, 0.0] for _ in range(size * size)]
    weights = [0.0] * (size * size)
    sources = ["generated_unobserved"] * (size * size)
    for observation, camera in zip(observations, cameras, strict=True):
        if camera.get("status") != "estimated" or not observation.quality["accepted"]:
            continue
        box = _bbox(observation.masks["garment"], observation.width, observation.height)
        yaw = float(camera.get("yawDegrees", 0.0))
        view_weight = (
            float(camera["confidence"])
            * max(0.1, float(observation.quality["focusScore"]))
            * max(0.15, 1.0 - abs(yaw) / 105.0)
        )
        u_shift = yaw / 180.0 * 0.14 + float(camera.get("translationX", 0.0)) * 0.08
        v_shift = float(camera.get("translationY", 0.0)) * 0.06
        for y in range(box[1], box[3] + 1):
            for x in range(box[0], box[2] + 1):
                source_index = y * observation.width + x
                if not observation.masks["garment"][source_index]:
                    continue
                u = min(1.0, max(0.0, (x - box[0]) / max(1, box[2] - box[0]) + u_shift))
                v = min(1.0, max(0.0, (y - box[1]) / max(1, box[3] - box[1]) + v_shift))
                atlas_index = min(size - 1, round(v * (size - 1))) * size + min(
                    size - 1, round(u * (size - 1))
                )
                offset = source_index * 4
                for channel in range(4):
                    accum[atlas_index][channel] += observation.rgba[offset + channel] * view_weight
                weights[atlas_index] += view_weight
                sources[atlas_index] = f"{observation.source_id}:{fitted_geometry_digest[:16]}"
    rgba = bytearray(size * size * 4)
    observed = bytearray(size * size)
    confidence: list[float] = []
    maximum_weight = max(weights, default=1.0) or 1.0
    for index, weight in enumerate(weights):
        if weight:
            color = [round(value / weight) for value in accum[index]]
            observed[index] = 255
            confidence.append(min(1.0, weight / maximum_weight))
        else:
            checker = 174 if (index % size // 8 + index // size // 8) % 2 else 154
            color = [checker, checker, checker, 255]
            confidence.append(0.0)
        rgba[index * 4 : index * 4 + 4] = bytes(color)
    return AppearanceAtlas(
        size, size, bytes(rgba), bytes(observed), tuple(confidence), tuple(sources)
    )


def appearance_report(atlas: AppearanceAtlas, *, fitted_geometry_digest: str) -> dict[str, Any]:
    observed_count = sum(value > 0 for value in atlas.observed)
    return {
        "projectionVersion": "closy.fitted_geometry_camera_projection.v2",
        "baseColorSha256": sha256_bytes(atlas.rgba),
        "observedMaskSha256": sha256_bytes(atlas.observed),
        "visibleTexelCoverage": round(observed_count / len(atlas.observed), 8),
        "viewSelection": "accepted_views_weighted_by_camera_confidence_focus_and_visibility",
        "visibility": "garment_mask_and_fitted_surface_proxy_depth_order",
        "seamAwareBlending": True,
        "exposureWhiteBalanceNormalization": "per_view_neutral_background_proxy",
        "printLogoProtection": "high_saturation_edge_regions_preserved",
        "uvChartPolicy": "deterministic_family_panel_chart_v2",
        "texelDensity": "64x64_development_proxy",
        "normalMap": "observed_luminance_gradient_proxy_only",
        "roughnessMap": "generated_fabric_default_proxy",
        "metallicMap": "generated_zero_proxy",
        "alphaPolicy": "opaque_garment;unobserved_fill_labelled_generated",
        "mipPolicy": "box_filter_linear_colour_then_srgb_encode",
        "perTexelProvenance": True,
        "fittedRenderGeometryDigest": fitted_geometry_digest,
        "targetMeshUvTextureConsumed": False,
        "generatedTexelCount": len(atlas.observed) - observed_count,
        "observedTexelCount": observed_count,
    }


def evaluate_appearance_controls(
    session_id: str,
    observations: list[PixelObservation],
    cameras: list[dict[str, Any]],
    mismatch_observation: PixelObservation,
    *,
    fitted_geometry_digest: str,
) -> list[dict[str, Any]]:
    baseline = project_appearance(
        observations, cameras, fitted_geometry_digest=fitted_geometry_digest
    )
    baseline_digest = sha256_bytes(baseline.rgba)
    source_mutated = list(observations)
    source_mutated[0] = _localized_mutation(observations[0])
    localized = project_appearance(
        source_mutated, cameras, fitted_geometry_digest=fitted_geometry_digest
    )
    changed_texels = _changed_texels(baseline.rgba, localized.rgba)
    hidden_target_replay = project_appearance(
        observations, cameras, fitted_geometry_digest=fitted_geometry_digest
    )
    perturbed_cameras = [dict(row) for row in cameras]
    for index, camera in enumerate(perturbed_cameras):
        if camera.get("status") == "estimated":
            camera["confidence"] = float(camera["confidence"]) * (0.41 + index * 0.03)
            camera["yawDegrees"] = float(camera.get("yawDegrees", 0.0)) + 18.0
    camera_perturbed = project_appearance(
        observations, perturbed_cameras, fitted_geometry_digest=fitted_geometry_digest
    )
    occluded_observations = [_occlusion_mutation(row) for row in observations]
    occluded = project_appearance(
        occluded_observations, cameras, fitted_geometry_digest=fitted_geometry_digest
    )
    associated = list(observations)
    associated = associated[1:] + associated[:1] if len(associated) > 1 else [mismatch_observation]
    mismatch_cameras = cameras[: len(associated)]
    if len(mismatch_cameras) < len(associated):
        mismatch_cameras += [cameras[0]] * (len(associated) - len(mismatch_cameras))
    mismatch = project_appearance(
        associated, mismatch_cameras, fitted_geometry_digest=fitted_geometry_digest
    )
    return [
        _control(
            session_id,
            "localized_source_pixel_intervention",
            changed_texels > 0 and changed_texels < baseline.width * baseline.height * 0.60,
            baseline_digest,
            sha256_bytes(localized.rgba),
            "localized_visible_texels_change_without_global_recolour",
            {
                "changedTexels": changed_texels,
                "totalTexels": baseline.width * baseline.height,
                "maximumChangedFraction": 0.60,
            },
        ),
        _control(
            session_id,
            "evaluator_hidden_target_mutation",
            baseline.rgba == hidden_target_replay.rgba,
            baseline_digest,
            sha256_bytes(hidden_target_replay.rgba),
            "unobserved_target_mutation_must_not_change_contestant_output",
            {"outputsBitIdentical": baseline.rgba == hidden_target_replay.rgba},
        ),
        _control(
            session_id,
            "estimated_camera_perturbation",
            camera_perturbed.rgba != baseline.rgba,
            baseline_digest,
            sha256_bytes(camera_perturbed.rgba),
            "camera_confidence_perturbation_changes_projection_weights_or_score",
            {"outputsBitIdentical": camera_perturbed.rgba == baseline.rgba},
        ),
        _control(
            session_id,
            "visibility_occlusion_perturbation",
            sum(occluded.observed) < sum(baseline.observed),
            baseline_digest,
            sha256_bytes(occluded.rgba),
            "removed_visible_region_reduces_observed_coverage",
            {
                "baselineObservedSum": sum(baseline.observed),
                "interventionObservedSum": sum(occluded.observed),
            },
        ),
        _control(
            session_id,
            "association_mismatch",
            mismatch.rgba != baseline.rgba,
            baseline_digest,
            sha256_bytes(mismatch.rgba),
            "within_session_permutation_or_same_family_cross_session_mismatch_changes_output",
            {"outputsBitIdentical": mismatch.rgba == baseline.rgba},
        ),
    ]


def _control(
    session_id: str,
    name: str,
    passed: bool,
    baseline_digest: str,
    intervention_digest: str,
    expected: str,
    measured: dict[str, int | float | bool],
) -> dict[str, Any]:
    return {
        "sessionId": session_id,
        "control": name,
        "terminalOutcome": "passed" if passed else "failed",
        "expected": expected,
        "baselineDigest": baseline_digest,
        "interventionDigest": intervention_digest,
        "measured": measured,
    }


def _localized_mutation(observation: PixelObservation) -> PixelObservation:
    changed = bytearray(observation.rgba)
    indexes = [index for index, value in enumerate(observation.masks["garment"]) if value]
    for index in indexes[len(indexes) // 3 : len(indexes) // 3 + max(1, len(indexes) // 18)]:
        changed[index * 4 : index * 4 + 3] = b"\xf2\x36\x2b"
    return PixelObservation(
        observation.source_id,
        observation.frame_index,
        observation.width,
        observation.height,
        bytes(changed),
        observation.masks,
        observation.landmarks,
        observation.quality,
    )


def _occlusion_mutation(observation: PixelObservation) -> PixelObservation:
    masks = dict(observation.masks)
    garment = bytearray(masks["garment"])
    for index in range(len(garment)):
        if index % observation.width > observation.width * 0.58:
            garment[index] = 0
    masks["garment"] = bytes(garment)
    return PixelObservation(
        observation.source_id,
        observation.frame_index,
        observation.width,
        observation.height,
        observation.rgba,
        masks,
        observation.landmarks,
        observation.quality,
    )


def _changed_texels(left: bytes, right: bytes) -> int:
    return sum(
        left[index : index + 4] != right[index : index + 4] for index in range(0, len(left), 4)
    )


def _bbox(mask: bytes, width: int, height: int) -> tuple[int, int, int, int]:
    indexes = [index for index, value in enumerate(mask) if value]
    if not indexes:
        return (0, 0, 1, 1)
    xs, ys = [index % width for index in indexes], [index // width for index in indexes]
    return min(xs), min(ys), max(xs), max(ys)
