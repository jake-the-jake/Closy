from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.visual_understanding.raster_parser import (
    RASTER_PIXEL_PARSER_VERSION,
    build_project_authored_tshirt_pixel_views,
    parse_tshirt_raster_pixel_views,
)

TSHIRT_VISUAL_OBSERVATION_VERSION = "closy.visual_observations.tshirt.raster_d0_v1"
TSHIRT_VISUAL_OBSERVATION_ID = "visual.raster_d0_tshirt_reference_v1"

REQUIRED_TSHIRT_VISUAL_LANDMARKS = (
    "landmark.neck.center",
    "landmark.shoulder.left",
    "landmark.shoulder.right",
    "landmark.armhole.left",
    "landmark.armhole.right",
    "landmark.cuff.left",
    "landmark.cuff.right",
    "landmark.hem.left",
    "landmark.hem.right",
    "landmark.hem.center",
)


def build_tshirt_visual_observations(capture_record: dict[str, Any]) -> dict[str, Any]:
    """Build BP50 D0 visual evidence from decoded project-authored raster pixels.

    This is still a synthetic fixture profile. It is materially stronger than
    the earlier analytic-polygon scaffold because masks, parts, openings and
    landmarks are derived from a deterministic pixel fixture instead of from the
    T-shirt parameter object used by fitting.
    """

    pixel_views = build_project_authored_tshirt_pixel_views(capture_record)
    record = parse_tshirt_raster_pixel_views(
        pixel_views,
        source_record_id=str(capture_record["recordId"]),
        source_record_hash=str(capture_record["immutability"]["sourceRecordHash"]),
    )
    record["visualUnderstandingId"] = TSHIRT_VISUAL_OBSERVATION_ID
    record["stageVersion"] = TSHIRT_VISUAL_OBSERVATION_VERSION
    record["aggregate"]["requiredLandmarks"] = list(REQUIRED_TSHIRT_VISUAL_LANDMARKS)
    record["provider"]["algorithmVersion"] = RASTER_PIXEL_PARSER_VERSION
    cameras = {
        str(view.get("viewId", "")): deepcopy(view.get("camera", {}))
        for view in capture_record.get("views", [])
        if isinstance(view, Mapping)
    }
    for view in record["views"]:
        view["camera"] = {
            **cameras.get(str(view.get("viewId", "")), {}),
            "source": "synthetic_capture_record_camera_metadata",
        }
    record["integrity"]["visualRecordHash"] = hash_visual_observations(record)
    return record


def hash_visual_observations(record: dict[str, Any]) -> str:
    payload = deepcopy(record)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["visualRecordHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
