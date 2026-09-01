from __future__ import annotations

import math
import struct
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from closy_forge.appearance.bitmap_atlas import (
    ATLAS_SIZE,
    BITMAP_PATHS,
    BitmapAtlasBundle,
    _derived_normal,
    _occlusion_map,
    _roughness_map,
    hash_bitmap_pbr_report,
)
from closy_forge.geometry.mesh_model import MeshSet, Vec2, Vec3, triangle_normal
from closy_forge.inspection.cpu_raster import (
    _apply_frame,
    _edge,
    _frame_offset,
    _project,
    _visible_panels,
)
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.raster import DecodedPng, decode_png_rgba, encode_png_rgba

PROJECTION_VERSION = "closy.appearance.geometric_source_surface_atlas_projection.d0_v3"
PROVENANCE_PATH = "textures/atlas/source_to_texel_provenance.bin.zlib"
PROVENANCE_MANIFEST_PATH = "textures/atlas/source_to_texel_provenance.json"
ACTIVE_MASK_PATH = "textures/atlas/active_semantic_island_mask.png"
_PROVENANCE_STRUCT = struct.Struct("<HHBBHHHHfffffff")
_GENERATED = (42, 96, 210, 255)
_CLASS_CODES = {"observed": 1, "blended": 2, "generated": 3}
_VIEW_CODES = {"front": 1, "back": 2}
SOURCE_BLEND_RADIUS_TEXELS = 6


@dataclass(frozen=True)
class SourceViewInput:
    view_id: str
    source_id: str
    label: str
    expected_sha256: str
    payload: bytes
    image: DecodedPng
    camera: Mapping[str, object]
    garment_pixels: frozenset[int]
    logo_pixels: frozenset[int]


@dataclass(frozen=True)
class ProvenanceRecord:
    atlas_x: int
    atlas_y: int
    view_label: str
    source_x: int
    source_y: int
    panel_id: str
    triangle_index: int
    barycentric: tuple[float, float, float]
    material_uv: tuple[float, float]
    confidence: float
    visibility: float
    occlusion: float
    classification: str


@dataclass(frozen=True)
class GeometricAtlasBundle(BitmapAtlasBundle):
    provenance_records: tuple[ProvenanceRecord, ...]


@dataclass(frozen=True)
class _TriangleProjection:
    view: SourceViewInput
    panel_id: str
    panel_code: int
    triangle_index: int
    global_index: int
    screen: tuple[tuple[float, float, float], ...]
    atlas: tuple[tuple[float, float, float], ...]
    panel_uvs: tuple[Vec2, ...]
    angle_weight: float


@dataclass(frozen=True)
class _AtlasSample:
    color: tuple[int, int, int, int]
    record: ProvenanceRecord
    logo: bool


def build_geometric_source_atlas(
    meshset: MeshSet,
    source_views: tuple[SourceViewInput, ...],
) -> GeometricAtlasBundle:
    """Project source pixels through visible candidate triangles into pattern UV space.

    The operation is camera-dependent only while observing each source view. The emitted atlas
    contains no view selector, and every source-backed texel retains a triangle/UV/pixel record.
    """

    if {view.label for view in source_views} != {"front", "back"}:
        raise ValueError("geometric_atlas_requires_front_and_back")
    panel_ids = sorted({mesh.panel_id for mesh in meshset.meshes})
    panel_codes = {panel_id: index + 1 for index, panel_id in enumerate(panel_ids)}
    samples: list[_AtlasSample | None] = [None] * (ATLAS_SIZE * ATLAS_SIZE)
    active: set[int] = set()
    for view in sorted(source_views, key=lambda item: item.label):
        if sha256_bytes(view.payload) != view.expected_sha256:
            raise ValueError(f"geometric_atlas_source_payload_mismatch:{view.label}")
        _project_view(meshset, view, panel_codes, samples, active)
    _blend_source_backed_holes(samples, active)
    artifacts, report, records = _build_artifacts(source_views, panel_codes, samples, active)
    audit_geometric_source_atlas(artifacts, report, records)
    return GeometricAtlasBundle(
        artifacts=artifacts,
        report=report,
        decoded_atlas=decode_png_rgba(_bytes(artifacts[BITMAP_PATHS["baseColor"]])),
        provenance_records=records,
    )


def panel_uv_to_atlas(
    panel_id: str, uv: Vec2, *, use_rear: bool, atlas_size: int = ATLAS_SIZE
) -> tuple[float, float]:
    """Mirror the frozen independent renderer's panel-UV sampling contract."""

    if panel_id in {"panel.front", "panel.back"}:
        u = _clamp((uv[0] + 0.35) / 0.70)
        v = _clamp(uv[1] / 0.68)
        local_u = 0.40 + u * 0.40
        atlas_v = (1.0 - v) * 1.02
    elif panel_id == "panel.sleeve.left":
        u = _clamp((uv[0] + 0.1271) / 0.2542)
        v = _clamp(uv[1] / 0.3054)
        local_u = u * 0.38
        atlas_v = 0.06 + (1.0 - v) * 0.45
    elif panel_id == "panel.sleeve.right":
        u = _clamp((uv[0] + 0.1271) / 0.2542)
        v = _clamp(uv[1] / 0.3054)
        local_u = 0.62 + u * 0.38
        atlas_v = 0.06 + (1.0 - v) * 0.45
    else:
        local_u = 0.50
        atlas_v = 0.08
    atlas_u = (0.5 + local_u * 0.5) if use_rear else local_u * 0.5
    return (
        min(atlas_size - 1.0e-6, max(0.0, atlas_u * atlas_size)),
        min(atlas_size - 1.0e-6, max(0.0, atlas_v * atlas_size)),
    )


def audit_geometric_source_atlas(
    artifacts: Mapping[str, bytes | Mapping[str, Any]],
    report: Mapping[str, Any],
    records: tuple[ProvenanceRecord, ...] | None = None,
) -> dict[str, Any]:
    integrity = _mapping(report.get("integrity"))
    if hash_bitmap_pbr_report(report) != integrity.get("bitmapPbrReportHash"):
        raise ValueError("geometric_atlas_report_hash_mismatch")
    maps = _mapping_records(report.get("maps"))
    for map_id, path in {**BITMAP_PATHS, "activeSemanticIslandMask": ACTIVE_MASK_PATH}.items():
        if map_id == "pbrReport":
            continue
        map_record = maps.get(map_id)
        if map_record is None or map_record.get("path") != path:
            raise ValueError(f"geometric_atlas_map_missing:{map_id}")
        payload = _bytes(artifacts[path])
        if map_record.get("sha256") != sha256_bytes(payload):
            raise ValueError(f"geometric_atlas_map_hash_mismatch:{map_id}")
        image = decode_png_rgba(payload)
        if (image.width, image.height) != (ATLAS_SIZE, ATLAS_SIZE):
            raise ValueError(f"geometric_atlas_map_dimensions:{map_id}")
    manifest = _mapping(artifacts[PROVENANCE_MANIFEST_PATH])
    compressed = _bytes(artifacts[PROVENANCE_PATH])
    if sha256_bytes(compressed) != manifest.get("compressedSha256"):
        raise ValueError("geometric_atlas_provenance_hash_mismatch")
    decoded = decode_provenance(compressed, manifest)
    if records is not None and decoded != records:
        raise ValueError("geometric_atlas_provenance_roundtrip_mismatch")
    generated = decode_png_rgba(_bytes(artifacts[BITMAP_PATHS["generatedRegionMask"]]))
    contribution = decode_png_rgba(_bytes(artifacts[BITMAP_PATHS["sourceContribution"]]))
    logo = decode_png_rgba(_bytes(artifacts[BITMAP_PATHS["logoRegionMask"]]))
    for record in decoded:
        offset = (record.atlas_y * ATLAS_SIZE + record.atlas_x) * 4
        source_backed = record.classification in {"observed", "blended"}
        if source_backed == (generated.rgba[offset] >= 128):
            raise ValueError("geometric_atlas_generated_classification_mismatch")
        contribution_code = tuple(contribution.rgba[offset : offset + 3])
        if source_backed and contribution_code not in {
            (255, 0, 0),
            (0, 255, 0),
            (255, 255, 0),
        }:
            raise ValueError("geometric_atlas_source_contribution_missing")
        if logo.rgba[offset] >= 128 and record.classification == "generated":
            raise ValueError("geometric_atlas_logo_overwritten")
    coverage = _mapping(report.get("coverage"))
    if float(coverage.get("generatedControlledFillFraction", 0.0)) <= 0.0:
        raise ValueError("geometric_atlas_generated_fill_empty")
    return {
        "status": "pass",
        "recordCount": len(decoded),
        "sourceObservedFraction": coverage.get("sourceObservedFraction"),
        "generatedControlledFillFraction": coverage.get("generatedControlledFillFraction"),
    }


def decode_provenance(
    compressed: bytes, manifest: Mapping[str, Any]
) -> tuple[ProvenanceRecord, ...]:
    if sha256_bytes(compressed) != manifest.get("compressedSha256"):
        raise ValueError("geometric_atlas_provenance_compressed_hash_mismatch")
    try:
        raw = zlib.decompress(compressed)
    except zlib.error as exc:
        raise ValueError("geometric_atlas_provenance_compression_invalid") from exc
    if sha256_bytes(raw) != manifest.get("uncompressedSha256"):
        raise ValueError("geometric_atlas_provenance_uncompressed_hash_mismatch")
    if len(raw) % _PROVENANCE_STRUCT.size:
        raise ValueError("geometric_atlas_provenance_record_alignment")
    panel_ids = {
        int(code): str(panel_id) for panel_id, code in _mapping(manifest.get("panelCodes")).items()
    }
    labels = {value: key for key, value in _VIEW_CODES.items()}
    classes = {value: key for key, value in _CLASS_CODES.items()}
    output = []
    for offset in range(0, len(raw), _PROVENANCE_STRUCT.size):
        values = _PROVENANCE_STRUCT.unpack_from(raw, offset)
        output.append(
            ProvenanceRecord(
                atlas_x=values[0],
                atlas_y=values[1],
                view_label=labels.get(values[2], ""),
                source_x=values[4],
                source_y=values[5],
                panel_id=panel_ids.get(values[6], ""),
                triangle_index=values[7],
                barycentric=(values[8], values[9], values[10]),
                material_uv=(values[11], values[12]),
                confidence=values[13],
                visibility=1.0 if values[2] else 0.0,
                occlusion=values[14],
                classification=classes[values[3]],
            )
        )
    if len(output) != int(manifest.get("recordCount", -1)):
        raise ValueError("geometric_atlas_provenance_record_count_mismatch")
    return tuple(output)


def _project_view(
    meshset: MeshSet,
    view: SourceViewInput,
    panel_codes: Mapping[str, int],
    samples: list[_AtlasSample | None],
    active: set[int],
) -> None:
    visible = [
        mesh
        for mesh in sorted(meshset.meshes, key=lambda item: (item.panel_id, item.name))
        if mesh.panel_id in _visible_panels(view.label)
    ]
    raw_projected = [
        _project(vertex, view.label, view.image.width, view.image.height, view.camera)
        for mesh in visible
        for vertex in mesh.vertices
    ]
    frame = _frame_offset(raw_projected, view.image.width, view.image.height, view.camera)
    projections: list[_TriangleProjection] = []
    global_index = 0
    for mesh in visible:
        projected = tuple(
            _apply_frame(
                _project(vertex, view.label, view.image.width, view.image.height, view.camera),
                frame,
            )
            for vertex in mesh.vertices
        )
        for triangle_index, triangle in enumerate(mesh.triangles):
            uvs = tuple(mesh.panel_uvs[index] for index in triangle)
            projections.append(
                _TriangleProjection(
                    view=view,
                    panel_id=mesh.panel_id,
                    panel_code=panel_codes[mesh.panel_id],
                    triangle_index=triangle_index,
                    global_index=global_index,
                    screen=tuple(projected[index] for index in triangle),
                    atlas=tuple(
                        (*panel_uv_to_atlas(mesh.panel_id, uv, use_rear=view.label == "back"), 0.0)
                        for uv in uvs
                    ),
                    panel_uvs=uvs,
                    angle_weight=_angle_weight(
                        triangle_normal(mesh.vertices, triangle), view.label
                    ),
                )
            )
            global_index += 1
    owner = _source_visibility(projections, view.image.width, view.image.height)
    for projection in projections:
        _raster_projection_to_atlas(projection, owner, samples, active)


def _source_visibility(
    projections: list[_TriangleProjection], width: int, height: int
) -> list[int]:
    depth = [math.inf] * (width * height)
    owner = [-1] * (width * height)
    for projection in projections:
        points = projection.screen
        area = _edge(points[0], points[1], points[2][0], points[2][1])
        if abs(area) <= 1.0e-9:
            continue
        min_x, max_x, min_y, max_y = _bounds(points, width, height)
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                bary = _barycentric(points, x + 0.5, y + 0.5, area)
                if min(bary) < -1.0e-8:
                    continue
                z = sum(bary[index] * points[index][2] for index in range(3))
                pixel = y * width + x
                if z < depth[pixel]:
                    depth[pixel] = z
                    owner[pixel] = projection.global_index
    return owner


def _raster_projection_to_atlas(
    projection: _TriangleProjection,
    owner: list[int],
    samples: list[_AtlasSample | None],
    active: set[int],
) -> None:
    points = projection.atlas
    area = _edge(points[0], points[1], points[2][0], points[2][1])
    if abs(area) <= 1.0e-9:
        return
    min_x, max_x, min_y, max_y = _bounds(points, ATLAS_SIZE, ATLAS_SIZE)
    image = projection.view.image
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            bary = _barycentric(points, x + 0.5, y + 0.5, area)
            if min(bary) < -1.0e-8:
                continue
            atlas_index = y * ATLAS_SIZE + x
            active.add(atlas_index)
            sx = sum(bary[index] * projection.screen[index][0] for index in range(3))
            sy = sum(bary[index] * projection.screen[index][1] for index in range(3))
            source_x = int(math.floor(sx))
            source_y = int(math.floor(sy))
            if not (0 <= source_x < image.width and 0 <= source_y < image.height):
                continue
            source_index = source_y * image.width + source_x
            if owner[source_index] != projection.global_index:
                continue
            if source_index not in projection.view.garment_pixels:
                continue
            offset = source_index * 4
            color = (
                image.rgba[offset],
                image.rgba[offset + 1],
                image.rgba[offset + 2],
                image.rgba[offset + 3],
            )
            logo = source_index in projection.view.logo_pixels
            classification = (
                "observed"
                if logo or (abs(sx - (source_x + 0.5)) <= 0.2 and abs(sy - (source_y + 0.5)) <= 0.2)
                else "blended"
            )
            uv = (
                sum(bary[index] * projection.panel_uvs[index][0] for index in range(3)),
                sum(bary[index] * projection.panel_uvs[index][1] for index in range(3)),
            )
            focus = _focus_weight(image, source_x, source_y)
            confidence = _clamp(0.55 + projection.angle_weight * 0.35 + focus * 0.10)
            record = ProvenanceRecord(
                atlas_x=x,
                atlas_y=y,
                view_label=projection.view.label,
                source_x=source_x,
                source_y=source_y,
                panel_id=projection.panel_id,
                triangle_index=projection.triangle_index,
                barycentric=(_f32(bary[0]), _f32(bary[1]), _f32(bary[2])),
                material_uv=(_f32(uv[0]), _f32(uv[1])),
                confidence=_f32(confidence),
                visibility=1.0,
                occlusion=0.0,
                classification=classification,
            )
            candidate = _AtlasSample(color=color, record=record, logo=logo)
            current = samples[atlas_index]
            if current is None or _sample_rank(candidate) > _sample_rank(current):
                samples[atlas_index] = candidate


def _blend_source_backed_holes(samples: list[_AtlasSample | None], active: set[int]) -> None:
    for distance in range(1, SOURCE_BLEND_RADIUS_TEXELS + 1):
        updates: dict[int, _AtlasSample] = {}
        for index in sorted(active):
            if samples[index] is not None:
                continue
            x, y = index % ATLAS_SIZE, index // ATLAS_SIZE
            neighbours = [
                samples[ny * ATLAS_SIZE + nx]
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                if 0 <= nx < ATLAS_SIZE and 0 <= ny < ATLAS_SIZE
            ]
            backed = [item for item in neighbours if item is not None and not item.logo]
            if not backed:
                continue
            source = max(backed, key=_sample_rank)
            color_values = tuple(
                round(sum(item.color[channel] for item in backed) / len(backed))
                for channel in range(4)
            )
            color = (color_values[0], color_values[1], color_values[2], color_values[3])
            record = source.record
            updates[index] = _AtlasSample(
                color=color,
                logo=False,
                record=ProvenanceRecord(
                    atlas_x=x,
                    atlas_y=y,
                    view_label=record.view_label,
                    source_x=record.source_x,
                    source_y=record.source_y,
                    panel_id=record.panel_id,
                    triangle_index=record.triangle_index,
                    barycentric=record.barycentric,
                    material_uv=record.material_uv,
                    confidence=_f32(record.confidence * (0.88**distance)),
                    visibility=record.visibility,
                    occlusion=record.occlusion,
                    classification="blended",
                ),
            )
        for index, sample in updates.items():
            samples[index] = sample


def _build_artifacts(
    source_views: tuple[SourceViewInput, ...],
    panel_codes: Mapping[str, int],
    samples: list[_AtlasSample | None],
    active: set[int],
) -> tuple[dict[str, bytes | dict[str, Any]], dict[str, Any], tuple[ProvenanceRecord, ...]]:
    base = bytearray(_GENERATED * (ATLAS_SIZE * ATLAS_SIZE))
    confidence = bytearray((32, 32, 32, 255) * (ATLAS_SIZE * ATLAS_SIZE))
    generated = bytearray((255, 255, 255, 255) * (ATLAS_SIZE * ATLAS_SIZE))
    contribution = bytearray((0, 0, 255, 255) * (ATLAS_SIZE * ATLAS_SIZE))
    logo = bytearray((0, 0, 0, 255) * (ATLAS_SIZE * ATLAS_SIZE))
    active_mask = bytearray((0, 0, 0, 255) * (ATLAS_SIZE * ATLAS_SIZE))
    records: list[ProvenanceRecord] = []
    generated_active = 0
    for index in sorted(active):
        offset = index * 4
        active_mask[offset : offset + 4] = bytes((255, 255, 255, 255))
        sample = samples[index]
        if sample is None:
            generated_active += 1
            records.append(
                ProvenanceRecord(
                    atlas_x=index % ATLAS_SIZE,
                    atlas_y=index // ATLAS_SIZE,
                    view_label="",
                    source_x=65535,
                    source_y=65535,
                    panel_id="",
                    triangle_index=65535,
                    barycentric=(0.0, 0.0, 0.0),
                    material_uv=(0.0, 0.0),
                    confidence=0.0,
                    visibility=0.0,
                    occlusion=1.0,
                    classification="generated",
                )
            )
            continue
        record = sample.record
        records.append(record)
        base[offset : offset + 4] = bytes(sample.color)
        confidence_value = round(record.confidence * 255)
        confidence[offset : offset + 4] = bytes(
            (confidence_value, confidence_value, confidence_value, 255)
        )
        generated[offset : offset + 4] = bytes((0, 0, 0, 255))
        if record.classification == "blended":
            source_code = (255, 255, 0, 255)
        elif record.view_label == "front":
            source_code = (255, 0, 0, 255)
        else:
            source_code = (0, 255, 0, 255)
        contribution[offset : offset + 4] = bytes(source_code)
        if sample.logo:
            logo[offset : offset + 4] = bytes((255, 255, 255, 255))
    record_tuple = tuple(records)
    provenance_raw = _encode_provenance(record_tuple, panel_codes)
    provenance_compressed = zlib.compress(provenance_raw, level=9)
    maps = {
        "baseColor": bytes(base),
        "normal": _derived_normal(bytes(base)),
        "roughness": _roughness_map(bytes(base), bytes(logo)),
        "occlusion": _occlusion_map(bytes(generated)),
        "viewConfidence": bytes(confidence),
        "generatedRegionMask": bytes(generated),
        "sourceContribution": bytes(contribution),
        "logoRegionMask": bytes(logo),
        "activeSemanticIslandMask": bytes(active_mask),
    }
    artifacts: dict[str, bytes | dict[str, Any]] = {}
    source_records = []
    for view in sorted(source_views, key=lambda item: item.label):
        path = f"source/public_fixture/{view.label}.png"
        artifacts[path] = view.payload
        source_records.append(
            {
                "viewId": view.view_id,
                "sourceId": view.source_id,
                "label": view.label,
                "path": path,
                "sha256": sha256_bytes(view.payload),
                "width": view.image.width,
                "height": view.image.height,
                "camera": dict(view.camera),
                "sourceMode": "opened_frozen_source_bytes",
            }
        )
    map_paths = {
        **{key: value for key, value in BITMAP_PATHS.items() if key != "pbrReport"},
        "activeSemanticIslandMask": ACTIVE_MASK_PATH,
    }
    map_records = []
    for key, path in map_paths.items():
        payload = encode_png_rgba(ATLAS_SIZE, ATLAS_SIZE, maps[key])
        artifacts[path] = payload
        map_records.append(
            {
                "mapId": key,
                "path": path,
                "sha256": sha256_bytes(payload),
                "width": ATLAS_SIZE,
                "height": ATLAS_SIZE,
                "colorSpace": "srgb" if key == "baseColor" else "linear_data",
                "mediaType": "image/png",
            }
        )
    source_backed = len(active) - generated_active
    source_fraction = source_backed / len(active) if active else 0.0
    generated_fraction = generated_active / len(active) if active else 1.0
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "recordVersion": "closy.source_to_texel_provenance.binary.v1",
        "recordStruct": _PROVENANCE_STRUCT.format,
        "recordSizeBytes": _PROVENANCE_STRUCT.size,
        "recordCount": len(record_tuple),
        "panelCodes": dict(panel_codes),
        "viewCodes": _VIEW_CODES,
        "classCodes": _CLASS_CODES,
        "uncompressedSha256": sha256_bytes(provenance_raw),
        "compressedSha256": sha256_bytes(provenance_compressed),
        "generatedSentinel": 65535,
    }
    artifacts[PROVENANCE_PATH] = provenance_compressed
    artifacts[PROVENANCE_MANIFEST_PATH] = manifest
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "texture_bitmap_pbr.exact_tshirt_known_target_regression_v3",
        "stageVersion": PROJECTION_VERSION,
        "status": "pass",
        "atlas": {
            "width": ATLAS_SIZE,
            "height": ATLAS_SIZE,
            "layout": "front_left_half_rear_right_half_panel_uv_v2",
            "cameraIndependent": True,
            "viewConditionedTextureSelection": False,
            "projection": "decoded_pixel_to_visible_triangle_to_barycentric_material_uv",
            "seamBlend": {
                "mode": "bounded_active_island_source_backed_hole_blend",
                "maximumRadiusTexels": SOURCE_BLEND_RADIUS_TEXELS,
                "observedLogoOverwriteAllowed": False,
            },
        },
        "sourceViews": source_records,
        "maps": map_records,
        "provenance": {
            "path": PROVENANCE_PATH,
            "manifestPath": PROVENANCE_MANIFEST_PATH,
            "compressedSha256": sha256_bytes(provenance_compressed),
            "recordCount": len(record_tuple),
            "cameraIndependentFinalAtlas": True,
        },
        "coverage": {
            "denominator": "active_semantic_island_texels",
            "activeSemanticIslandTexels": len(active),
            "sourceObservedTexels": source_backed,
            "generatedControlledFillTexels": generated_active,
            "sourceObservedFraction": round(source_fraction, 9),
            "generatedControlledFillFraction": round(generated_fraction, 9),
            "generatedPixelsMarked": True,
            "generatedPixelsLabelledSourceObserved": False,
        },
        "logoPreservation": {
            "sourceView": "front",
            "atlasPixelCount": sum(1 for sample in samples if sample is not None and sample.logo),
            "preserved": any(sample is not None and sample.logo for sample in samples),
            "generatedOverwriteAllowed": False,
        },
        "pbr": {
            "baseColorAvailable": True,
            "normalAvailable": True,
            "roughnessAvailable": True,
            "occlusionAvailable": True,
            "normalRoughnessAoPhysicalAccuracy": "not_measured",
            "estimateClassification": "uncalibrated_d0_estimates",
            "metallicFactor": 0.0,
            "minimumRoughnessFactor": round(196 / 255, 9),
            "appearancePhysicsSeparated": True,
        },
        "controlledFill": {
            "method": "deterministic_bounded_blue_fabric_prior_v1",
            "nonEmpty": generated_active > 0,
            "observedPixelsWin": True,
            "excludedFromSourceFidelity": True,
        },
        "policy": {
            "publicSyntheticFixturePixelsPackaged": True,
            "privateUserPixelsPackaged": False,
            "externalApis": False,
            "trainingUse": False,
            "evaluatorOnlyViewUsed": False,
            "targetSpecificConstants": False,
        },
        "integrity": {"bitmapPbrReportHash": ""},
    }
    report["integrity"]["bitmapPbrReportHash"] = hash_bitmap_pbr_report(report)
    artifacts[BITMAP_PATHS["pbrReport"]] = report
    return artifacts, report, record_tuple


def _encode_provenance(
    records: tuple[ProvenanceRecord, ...], panel_codes: Mapping[str, int]
) -> bytes:
    output = bytearray()
    for record in records:
        output.extend(
            _PROVENANCE_STRUCT.pack(
                record.atlas_x,
                record.atlas_y,
                _VIEW_CODES.get(record.view_label, 0),
                _CLASS_CODES[record.classification],
                record.source_x,
                record.source_y,
                panel_codes.get(record.panel_id, 0),
                record.triangle_index,
                *record.barycentric,
                *record.material_uv,
                record.confidence,
                record.occlusion,
            )
        )
    return bytes(output)


def _angle_weight(normal: Vec3, label: str) -> float:
    direction = (0.0, 0.0, -1.0) if label == "back" else (0.0, 0.0, 1.0)
    return abs(sum(normal[index] * direction[index] for index in range(3)))


def _focus_weight(image: DecodedPng, x: int, y: int) -> float:
    if not (0 < x < image.width - 1 and 0 < y < image.height - 1):
        return 0.5
    center = _luminance(image, x, y)
    neighbours = (
        _luminance(image, x - 1, y),
        _luminance(image, x + 1, y),
        _luminance(image, x, y - 1),
        _luminance(image, x, y + 1),
    )
    laplacian = abs(4.0 * center - sum(neighbours))
    return _clamp(0.5 + laplacian * 2.0)


def _luminance(image: DecodedPng, x: int, y: int) -> float:
    offset = (y * image.width + x) * 4
    return (
        image.rgba[offset] * 0.2126
        + image.rgba[offset + 1] * 0.7152
        + image.rgba[offset + 2] * 0.0722
    ) / 255.0


def _sample_rank(sample: _AtlasSample) -> tuple[int, float, int, int]:
    record = sample.record
    return (
        1 if sample.logo else 0,
        record.confidence,
        -_VIEW_CODES.get(record.view_label, 0),
        -record.triangle_index,
    )


def _bounds(
    points: tuple[tuple[float, float, float], ...], width: int, height: int
) -> tuple[int, int, int, int]:
    return (
        max(0, int(math.floor(min(point[0] for point in points)))),
        min(width - 1, int(math.ceil(max(point[0] for point in points)))),
        max(0, int(math.floor(min(point[1] for point in points)))),
        min(height - 1, int(math.ceil(max(point[1] for point in points)))),
    )


def _barycentric(
    points: tuple[tuple[float, float, float], ...], x: float, y: float, area: float
) -> tuple[float, float, float]:
    w0 = _edge(points[1], points[2], x, y) / area
    w1 = _edge(points[2], points[0], x, y) / area
    return (w0, w1, 1.0 - w0 - w1)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _f32(value: float) -> float:
    return float(struct.unpack("<f", struct.pack("<f", value))[0])


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_records(value: object) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        return {}
    return {str(item.get("mapId", "")): item for item in value if isinstance(item, Mapping)}


def _bytes(value: bytes | Mapping[str, Any]) -> bytes:
    if not isinstance(value, bytes):
        raise ValueError("geometric_atlas_expected_bytes")
    return value
