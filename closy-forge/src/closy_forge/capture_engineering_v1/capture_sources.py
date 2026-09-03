from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.capture.raster_sources import decode_raster_fixture_pixels

from .camera_observation import estimate_camera, reprojection_diagnostics
from .common import sha256_bytes
from .privacy import assert_portable_record, portable_source_record
from .quality import PixelObservation, observe_pixels, quality_acceptance
from .video_avi import DecodedVideo, decode_uncompressed_avi


@dataclass(frozen=True)
class DecodedCaptureSource:
    private_record: dict[str, Any]
    portable_record: dict[str, Any]
    observation: PixelObservation
    camera: dict[str, Any]
    quality: dict[str, Any]


def decode_capture_source(
    path: Path,
    *,
    source_id: str,
    declared_mime: str,
    view_role: str,
    evidence_tier: str,
    known_scale_marker_meters: float | None,
    capture_thresholds: Mapping[str, object],
) -> DecodedCaptureSource:
    decoded = decode_raster_fixture_pixels(path, declared_mime=declared_mime)
    observation = observe_pixels(decoded.width, decoded.height, decoded.rgba)
    quality = quality_acceptance(observation, capture_thresholds)
    camera = estimate_camera(
        observation,
        declared_view_role=view_role,
        known_scale_marker_meters=known_scale_marker_meters,
    )
    private = {
        "sourceId": source_id,
        "absolutePath": str(path.resolve()),
        "mime": decoded.mime,
        "decodedWidth": decoded.width,
        "decodedHeight": decoded.height,
        "sourceByteSha256": sha256_bytes(path.read_bytes()),
        "decodedContentSha256": decoded.decoded_content_sha256,
        "pixelSha256": decoded.pixel_hash,
        "viewRole": view_role,
        "evidenceTier": evidence_tier,
        "orientationNormalization": "decoded_exif_transpose_then_rgba8",
        "colorspaceNormalization": "srgb_rgba8",
        "exifRetained": False,
    }
    portable = portable_source_record(private)
    assert_portable_record(portable)
    return DecodedCaptureSource(
        private_record=private,
        portable_record=portable,
        observation=observation,
        camera={**camera, "reprojection": reprojection_diagnostics(observation, camera)},
        quality=quality,
    )


def decode_video_source(
    data: bytes,
    *,
    source_id: str,
    capture_thresholds: Mapping[str, object],
    cancelled: object | None = None,
) -> dict[str, Any]:
    callback = cancelled if callable(cancelled) else None
    video = decode_uncompressed_avi(data, cancelled=callback)
    frame_rows = _video_frame_rows(video, capture_thresholds)
    selected = select_video_frames(frame_rows, maximum_selected=8)
    return {
        "sourceId": source_id,
        "container": video.container,
        "codec": video.codec,
        "decoderVersion": video.decoder_version,
        "decoderLicense": video.decoder_license,
        "sourceFrameCount": len(video.frames),
        "sourceByteSha256": video.source_byte_sha256,
        "timestamps": [
            {
                "numerator": frame.timestamp_numerator,
                "denominator": frame.timestamp_denominator,
            }
            for frame in video.frames
        ],
        "frameRows": frame_rows,
        "selectedFrameIndices": [row["frameIndex"] for row in selected],
        "duplicateFrameCount": len(frame_rows) - len({row["pixelSha256"] for row in frame_rows}),
        "selectionVersion": "closy.video_frame_selection.coverage_focus.v1",
        "rawFramesPersisted": False,
    }


def select_video_frames(
    frame_rows: Sequence[Mapping[str, Any]], *, maximum_selected: int
) -> list[dict[str, Any]]:
    if maximum_selected <= 0:
        raise ValueError("maximum_selected_frames_invalid")
    unique: dict[str, dict[str, Any]] = {}
    for row in frame_rows:
        digest = str(row.get("pixelSha256", ""))
        if digest and digest not in unique:
            unique[digest] = dict(row)
    candidates = list(unique.values())
    selected: list[dict[str, Any]] = []
    while candidates and len(selected) < maximum_selected:

        def score(row: Mapping[str, Any]) -> tuple[float, int]:
            focus = float(row.get("focusScore", 0.0))
            centroid = row.get("foregroundCentroidNormalized", [0.5, 0.5])
            diversity = 1.0
            if selected and isinstance(centroid, Sequence):
                diversity = min(
                    abs(float(centroid[0]) - float(item["foregroundCentroidNormalized"][0]))
                    + abs(float(centroid[1]) - float(item["foregroundCentroidNormalized"][1]))
                    for item in selected
                )
            return (focus * 0.65 + diversity * 0.35, -int(row.get("frameIndex", 0)))

        chosen = max(candidates, key=score)
        selected.append(chosen)
        candidates.remove(chosen)
    return sorted(selected, key=lambda row: int(row["frameIndex"]))


def single_image_uncertainty(view_role: str) -> dict[str, Any]:
    visible = view_role if view_role in {"front", "rear", "side"} else "ambiguous"
    alternatives = [
        {
            "hypothesisId": "single.front_symmetric_back",
            "hiddenSurface": "rear",
            "construction": "symmetric_panel_prior",
            "confidence": 0.42,
        },
        {
            "hypothesisId": "single.front_distinct_back",
            "hiddenSurface": "rear",
            "construction": "bounded_distinct_panel",
            "confidence": 0.28,
        },
    ]
    return {
        "declaredView": visible,
        "viewAmbiguity": ["front", "rear", "side"] if visible == "ambiguous" else [visible],
        "hiddenSurfaceHypotheses": alternatives,
        "confidenceClass": "low",
        "maximumAlternatives": 2,
        "canonicalClaimAllowed": False,
        "physicalMaterialClaimAllowed": False,
        "editableCorrections": ["view_role", "mask", "landmarks", "scale_marker"],
        "inferenceReasons": {
            "hiddenSurface": "not_observed_in_single_image",
            "construction": "family_bounded_prior_only",
            "scale": "known_marker_or_low_confidence_garment_prior",
        },
    }


def worn_capture_qc(observation: PixelObservation) -> dict[str, Any]:
    left, top, right, bottom = observation.foreground_bbox
    width = max(1, right - left + 1)
    height = max(1, bottom - top + 1)
    edge_overlap = sum(
        index % observation.width in {left, right}
        for index in observation.foreground
        if top <= index // observation.width <= bottom
    ) / max(1, len(observation.foreground))
    return {
        "maskRoles": ["body", "garment", "background"],
        "bodyMaskAvailable": True,
        "garmentMaskAvailable": True,
        "occlusionFraction": round(min(1.0, edge_overlap * width / height), 8),
        "handArmOverlapStatus": "bounded_synthetic_proxy",
        "poseObservation": "pixel_landmark_proxy",
        "garmentEaseUncertainty": [0.01, 0.06],
        "garmentShapeUncertainty": "bounded_family_template",
        "bodyReconstructionClaimed": False,
    }


def _video_frame_rows(
    video: DecodedVideo, capture_thresholds: Mapping[str, object]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for frame in video.frames:
        observation = observe_pixels(frame.width, frame.height, frame.rgba)
        quality = quality_acceptance(observation, capture_thresholds)
        rows.append(
            {
                "frameIndex": frame.index,
                "timestamp": {
                    "numerator": frame.timestamp_numerator,
                    "denominator": frame.timestamp_denominator,
                },
                "pixelSha256": frame.pixel_sha256,
                "focusScore": round(observation.focus_score, 8),
                "foregroundCoverage": round(observation.foreground_coverage, 8),
                "foregroundCentroidNormalized": [
                    round(value, 8) for value in observation.foreground_centroid
                ],
                "qualityStatus": quality["status"],
            }
        )
    return rows
