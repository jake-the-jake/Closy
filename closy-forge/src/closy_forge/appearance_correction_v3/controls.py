from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import replace
from typing import Any

from closy_forge.appearance.bitmap_atlas import BITMAP_PATHS
from closy_forge.appearance_correction_v3.projection import (
    GeometricAtlasBundle,
    SourceViewInput,
    build_geometric_source_atlas,
)
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.inspection.cpu_raster import rasterize_settled_garment
from closy_forge.inspection.source_render_fidelity import _atlas_sampler
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes
from closy_forge.raster import DecodedPng, decode_png_rgba, encode_png_rgba
from closy_forge.visual_understanding.raster_parser import LOGO_RGBA, TORSO_RGBA

_ALT_LOGO_RGBA = (225, 71, 104, 255)


def execute_source_only_controls(
    meshset: MeshSet, source_views: tuple[SourceViewInput, ...]
) -> dict[str, Any]:
    baseline = _run_variant(meshset, source_views, logo_color=LOGO_RGBA)
    variants: dict[str, tuple[tuple[SourceViewInput, ...], tuple[int, int, int, int]]] = {
        "move_logo_left": (_replace_front(source_views, _move_logo(dx=-8, dy=0)), LOGO_RGBA),
        "move_logo_right": (_replace_front(source_views, _move_logo(dx=8, dy=0)), LOGO_RGBA),
        "move_logo_vertically": (
            _replace_front(source_views, _move_logo(dx=0, dy=9)),
            LOGO_RGBA,
        ),
        "change_logo_size": (_replace_front(source_views, _scale_logo(1.35)), LOGO_RGBA),
        "change_logo_color_without_geometry_change": (
            _replace_front(source_views, _recolor_logo(_ALT_LOGO_RGBA)),
            _ALT_LOGO_RGBA,
        ),
        "remove_logo": (_replace_front(source_views, _remove_logo), LOGO_RGBA),
        "swap_front_rear": (_swap_views(source_views), LOGO_RGBA),
        "perturb_camera_within_locked_range": (_perturb_camera(source_views), LOGO_RGBA),
    }
    records = []
    for control_id, (views, logo_color) in variants.items():
        result = _run_variant(meshset, views, logo_color=logo_color)
        record = {
            "controlId": control_id,
            "sourceClosureHash": result["sourceClosureHash"],
            "atlasHash": result["atlasHash"],
            "provenanceHash": result["provenanceHash"],
            "geometryContentHash": result["geometryContentHash"],
            "sourceLogo": result["sourceLogo"],
            "renderedLogo": result["renderedLogo"],
            "atlasLogo": result["atlasLogo"],
            "sourceHashChanged": result["sourceClosureHash"] != baseline["sourceClosureHash"],
            "provenanceHashChanged": result["provenanceHash"] != baseline["provenanceHash"],
            "geometryInvariant": result["geometryContentHash"] == baseline["geometryContentHash"],
            "passed": False,
        }
        record["passed"] = _control_passed(control_id, baseline, result)
        records.append(record)
    moved_atlas_centroids = {
        tuple(_mapping(item.get("atlasLogo")).get("centroid", []))
        for item in records
        if str(item.get("controlId", "")).startswith("move_logo")
    }
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "closy.d0_texture_rerender.source_only_controls.v3",
        "strategyId": "geometric_source_surface_atlas_projection",
        "baseline": baseline,
        "records": records,
        "allControlsPassed": all(bool(item["passed"]) for item in records),
        "noMagicLocationConstant": len(moved_atlas_centroids) == 3,
        "geometryInvariantAcrossControls": all(bool(item["geometryInvariant"]) for item in records),
        "evaluatorOnlyBytesOpened": False,
        "networkUsed": False,
        "integrity": {"controlReportHash": ""},
    }
    report["integrity"]["controlReportHash"] = _hash(report, "controlReportHash")
    return report


def _run_variant(
    meshset: MeshSet,
    source_views: tuple[SourceViewInput, ...],
    *,
    logo_color: tuple[int, int, int, int],
) -> dict[str, Any]:
    atlas = build_geometric_source_atlas(meshset, source_views)
    front = next(view for view in source_views if view.label == "front")
    rendered = rasterize_settled_garment(
        meshset,
        label="front",
        width=front.image.width,
        height=front.image.height,
        camera=front.camera,
        texture_sampler=_atlas_sampler(atlas.decoded_atlas, "front"),
    )
    render = DecodedPng(rendered.width, rendered.height, rendered.rgba)
    logo_map = decode_png_rgba(_artifact_bytes(atlas, BITMAP_PATHS["logoRegionMask"]))
    provenance = _artifact_bytes(atlas, "textures/atlas/source_to_texel_provenance.bin.zlib")
    return {
        "sourceClosureHash": sha256_bytes(
            b"".join(
                view.payload + canonical_dumps(dict(view.camera)).encode("utf-8")
                for view in sorted(source_views, key=lambda item: item.label)
            )
        ),
        "atlasHash": sha256_bytes(_artifact_bytes(atlas, BITMAP_PATHS["baseColor"])),
        "provenanceHash": sha256_bytes(provenance),
        "geometryContentHash": geometry_content_hash(meshset),
        "sourceLogo": _mask_summary(front.image, front.logo_pixels),
        "renderedLogo": _color_summary(render, logo_color),
        "atlasLogo": _channel_summary(logo_map),
    }


def _control_passed(
    control_id: str, baseline: Mapping[str, Any], result: Mapping[str, Any]
) -> bool:
    base_source = _mapping(baseline.get("sourceLogo"))
    source = _mapping(result.get("sourceLogo"))
    base_render = _mapping(baseline.get("renderedLogo"))
    rendered = _mapping(result.get("renderedLogo"))
    common = (
        result.get("geometryContentHash") == baseline.get("geometryContentHash")
        and result.get("sourceClosureHash") != baseline.get("sourceClosureHash")
        and result.get("provenanceHash") != baseline.get("provenanceHash")
    )
    if control_id == "move_logo_left":
        return (
            common
            and _axis(source, 0) < _axis(base_source, 0)
            and _axis(rendered, 0) < _axis(base_render, 0)
        )
    if control_id == "move_logo_right":
        return (
            common
            and _axis(source, 0) > _axis(base_source, 0)
            and _axis(rendered, 0) > _axis(base_render, 0)
        )
    if control_id == "move_logo_vertically":
        return (
            common
            and _axis(source, 1) > _axis(base_source, 1)
            and _axis(rendered, 1) > _axis(base_render, 1)
        )
    if control_id == "change_logo_size":
        return (
            common
            and int(source.get("pixelCount", 0)) > int(base_source.get("pixelCount", 0))
            and int(rendered.get("pixelCount", 0)) > int(base_render.get("pixelCount", 0))
        )
    if control_id == "change_logo_color_without_geometry_change":
        return common and int(rendered.get("pixelCount", 0)) > 0
    if control_id == "remove_logo":
        return (
            common
            and int(source.get("pixelCount", -1)) == 0
            and int(rendered.get("pixelCount", -1)) == 0
            and int(_mapping(result.get("atlasLogo")).get("pixelCount", -1)) == 0
        )
    return common


def _replace_front(
    source_views: tuple[SourceViewInput, ...],
    operation: Callable[[SourceViewInput], SourceViewInput],
) -> tuple[SourceViewInput, ...]:
    return tuple(operation(view) if view.label == "front" else view for view in source_views)


def _move_logo(*, dx: int, dy: int) -> Callable[[SourceViewInput], SourceViewInput]:
    def operation(view: SourceViewInput) -> SourceViewInput:
        pixels = _clear_logo(view)
        moved = set()
        for index in view.logo_pixels:
            x, y = index % view.image.width, index // view.image.width
            nx, ny = x + dx, y + dy
            if 0 <= nx < view.image.width and 0 <= ny < view.image.height:
                target = ny * view.image.width + nx
                if target in view.garment_pixels:
                    pixels[target * 4 : target * 4 + 4] = bytes(LOGO_RGBA)
                    moved.add(target)
        return _with_pixels(view, pixels, frozenset(moved))

    return operation


def _scale_logo(scale: float) -> Callable[[SourceViewInput], SourceViewInput]:
    def operation(view: SourceViewInput) -> SourceViewInput:
        pixels = _clear_logo(view)
        xs = [index % view.image.width for index in view.logo_pixels]
        ys = [index // view.image.width for index in view.logo_pixels]
        center_x = sum(xs) / len(xs)
        center_y = sum(ys) / len(ys)
        scaled = set()
        for index in view.logo_pixels:
            x, y = index % view.image.width, index // view.image.width
            nx = round(center_x + (x - center_x) * scale)
            ny = round(center_y + (y - center_y) * scale)
            for ox in (0, 1):
                for oy in (0, 1):
                    target = (ny + oy) * view.image.width + nx + ox
                    if target in view.garment_pixels:
                        pixels[target * 4 : target * 4 + 4] = bytes(LOGO_RGBA)
                        scaled.add(target)
        return _with_pixels(view, pixels, frozenset(scaled))

    return operation


def _recolor_logo(color: tuple[int, int, int, int]) -> Callable[[SourceViewInput], SourceViewInput]:
    def operation(view: SourceViewInput) -> SourceViewInput:
        pixels = bytearray(view.image.rgba)
        for index in view.logo_pixels:
            pixels[index * 4 : index * 4 + 4] = bytes(color)
        return _with_pixels(view, pixels, view.logo_pixels)

    return operation


def _remove_logo(view: SourceViewInput) -> SourceViewInput:
    return _with_pixels(view, _clear_logo(view), frozenset())


def _clear_logo(view: SourceViewInput) -> bytearray:
    pixels = bytearray(view.image.rgba)
    for index in view.logo_pixels:
        pixels[index * 4 : index * 4 + 4] = bytes(TORSO_RGBA)
    return pixels


def _with_pixels(
    view: SourceViewInput, pixels: bytearray, logo_pixels: frozenset[int]
) -> SourceViewInput:
    payload = encode_png_rgba(view.image.width, view.image.height, bytes(pixels))
    return replace(
        view,
        expected_sha256=sha256_bytes(payload),
        payload=payload,
        image=decode_png_rgba(payload),
        logo_pixels=logo_pixels,
    )


def _swap_views(source_views: tuple[SourceViewInput, ...]) -> tuple[SourceViewInput, ...]:
    front = next(view for view in source_views if view.label == "front")
    back = next(view for view in source_views if view.label == "back")
    return (
        replace(
            front,
            expected_sha256=sha256_bytes(back.payload),
            payload=back.payload,
            image=back.image,
            garment_pixels=back.garment_pixels,
            logo_pixels=back.logo_pixels,
        ),
        replace(
            back,
            expected_sha256=sha256_bytes(front.payload),
            payload=front.payload,
            image=front.image,
            garment_pixels=front.garment_pixels,
            logo_pixels=front.logo_pixels,
        ),
    )


def _perturb_camera(
    source_views: tuple[SourceViewInput, ...],
) -> tuple[SourceViewInput, ...]:
    output = []
    for view in source_views:
        camera = deepcopy(dict(view.camera))
        camera["azimuthDegrees"] = _number(camera.get("azimuthDegrees")) + 1.5
        camera["elevationDegrees"] = _number(camera.get("elevationDegrees")) + 0.5
        camera["principalPointNormalized"] = [0.507, 0.496]
        output.append(
            replace(
                view,
                camera=camera,
            )
        )
    return tuple(output)


def _mask_summary(image: DecodedPng, indices: frozenset[int]) -> dict[str, Any]:
    return _indices_summary(indices, image.width)


def _color_summary(image: DecodedPng, color: tuple[int, int, int, int]) -> dict[str, Any]:
    return _indices_summary(
        frozenset(
            index
            for index in range(image.width * image.height)
            if tuple(image.rgba[index * 4 : index * 4 + 4]) == color
        ),
        image.width,
    )


def _channel_summary(image: DecodedPng) -> dict[str, Any]:
    return _indices_summary(
        frozenset(
            index for index in range(image.width * image.height) if image.rgba[index * 4] >= 128
        ),
        image.width,
    )


def _indices_summary(indices: frozenset[int], width: int) -> dict[str, Any]:
    if not indices:
        return {"pixelCount": 0, "centroid": None}
    return {
        "pixelCount": len(indices),
        "centroid": [
            round(sum(index % width for index in indices) / len(indices), 6),
            round(sum(index // width for index in indices) / len(indices), 6),
        ],
    }


def _axis(summary: Mapping[str, Any], axis: int) -> float:
    centroid = summary.get("centroid")
    if not isinstance(centroid, list) or len(centroid) != 2:
        return -1.0
    return float(centroid[axis])


def _number(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _artifact_bytes(atlas: GeometricAtlasBundle, path: str) -> bytes:
    value = atlas.artifacts[path]
    if not isinstance(value, bytes):
        raise ValueError("d0_appearance_control_expected_bytes")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _hash(document: Mapping[str, Any], key: str) -> str:
    payload = deepcopy(dict(document))
    payload["integrity"] = dict(_mapping(document.get("integrity")))
    payload["integrity"][key] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
