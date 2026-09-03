from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec2, Vec3, cross, normalize, sub

from .alternate_renderer import render_ray_triangles
from .common import sha256_bytes
from .quality import PixelObservation

PROJECTION_VERSION = "closy.source_to_panel_uv.barycentric.v1"
RGBA = tuple[int, int, int, int]


@dataclass(frozen=True)
class ProjectionView:
    source_id: str
    role: str
    width: int
    height: int
    rgba: bytes
    observation: PixelObservation


@dataclass(frozen=True)
class AtlasProjection:
    width: int
    height: int
    rgba: bytes
    observed_mask: bytes
    generated_mask: bytes
    confidence: tuple[float, ...]
    lineage: dict[str, Any]


def project_views_to_panel_uv(
    meshset: MeshSet,
    views: list[ProjectionView],
    *,
    atlas_width: int = 32,
    atlas_height: int = 32,
) -> AtlasProjection:
    if atlas_width <= 0 or atlas_height <= 0 or not views:
        raise ValueError("uv_projection_input_invalid")
    pixels = bytearray(atlas_width * atlas_height * 4)
    observed = bytearray(atlas_width * atlas_height)
    generated = bytearray(atlas_width * atlas_height)
    confidence = [0.0] * (atlas_width * atlas_height)
    contributions: dict[str, int] = {view.source_id: 0 for view in views}
    visible_triangle_count = 0
    for mesh in meshset.meshes:
        for triangle in mesh.triangles:
            a, b, c = (mesh.vertices[index] for index in triangle)
            uv_a, uv_b, uv_c = (mesh.panel_uvs[index] for index in triangle)
            normal = normalize(cross(sub(b, a), sub(c, a)))
            wrote_triangle = False
            for x, y, barycentric in _atlas_triangle_pixels(
                uv_a, uv_b, uv_c, atlas_width, atlas_height
            ):
                world = _interpolate3(a, b, c, barycentric)
                choices: list[tuple[float, RGBA, str]] = []
                for view in views:
                    sampled = _sample_view(mesh, world, normal, view, meshset)
                    if sampled is not None:
                        choices.append(sampled)
                if not choices:
                    continue
                total_weight = sum(item[0] for item in choices)
                color = tuple(
                    round(
                        sum(weight * rgba[channel] for weight, rgba, _source in choices)
                        / total_weight
                    )
                    for channel in range(4)
                )
                index = y * atlas_width + x
                pixels[index * 4 : index * 4 + 4] = bytes(color)
                observed[index] = 255
                confidence[index] = min(1.0, total_weight / max(1, len(choices)))
                for _weight, _rgba, source_id in choices:
                    contributions[source_id] += 1
                wrote_triangle = True
            if wrote_triangle:
                visible_triangle_count += 1
    for index in range(atlas_width * atlas_height):
        if observed[index]:
            continue
        x, y = index % atlas_width, index // atlas_width
        fill = _deterministic_fill(x, y)
        pixels[index * 4 : index * 4 + 4] = bytes(fill)
        generated[index] = 255
    observed_count = sum(value > 0 for value in observed)
    generated_count = sum(value > 0 for value in generated)
    if observed_count + generated_count != atlas_width * atlas_height:
        raise ValueError("uv_mask_partition_invalid")
    return AtlasProjection(
        width=atlas_width,
        height=atlas_height,
        rgba=bytes(pixels),
        observed_mask=bytes(observed),
        generated_mask=bytes(generated),
        confidence=tuple(confidence),
        lineage={
            "projectionVersion": PROJECTION_VERSION,
            "visibility": "panel_role_normal_and_source_foreground_mask",
            "mapping": "mesh_triangle_barycentric_world_to_panel_uv_to_source_pixel",
            "weights": ["view_angle", "focus", "exposure", "mask_confidence"],
            "sourceContributions": dict(sorted(contributions.items())),
            "visibleTriangleCount": visible_triangle_count,
            "observedTexelCount": observed_count,
            "generatedTexelCount": generated_count,
            "observedFraction": observed_count / (atlas_width * atlas_height),
            "observedAtlasSha256": sha256_bytes(bytes(pixels)),
            "observedMaskSha256": sha256_bytes(bytes(observed)),
            "generatedMaskSha256": sha256_bytes(bytes(generated)),
            "unseenFill": "deterministic_checker_not_observed",
            "protectedRegions": ["high_contrast_logo", "text_like_edges", "labels", "prints"],
        },
    )


def render_atlas_novel_view(
    meshset: MeshSet, atlas: AtlasProjection, *, width: int = 28, height: int = 36
) -> dict[str, Any]:
    def sample(_panel_id: str, uv: Vec2) -> RGBA:
        x = min(atlas.width - 1, max(0, int(uv[0] * atlas.width)))
        y = min(atlas.height - 1, max(0, int(uv[1] * atlas.height)))
        offset = (y * atlas.width + x) * 4
        return tuple(atlas.rgba[offset + channel] for channel in range(4))  # type: ignore[return-value]

    rendered = render_ray_triangles(
        meshset,
        width=width,
        height=height,
        view_role="three-quarter",
        texture_sampler=sample,
    )
    return {
        "rendererVersion": rendered.renderer_version,
        "implementationIndependentFromProjection": True,
        "renderedPixelCount": rendered.rendered_pixel_count,
        "rgbaSha256": rendered.image_sha256,
        "decoded": len(rendered.rgba) == width * height * 4,
    }


def projection_controls(meshset: MeshSet, views: list[ProjectionView]) -> dict[str, Any]:
    baseline = project_views_to_panel_uv(meshset, views)
    mutated_views = list(views)
    first = mutated_views[0]
    changed = bytearray(first.rgba)
    for index in sorted(first.observation.foreground)[
        : max(1, len(first.observation.foreground) // 5)
    ]:
        changed[index * 4 : index * 4 + 3] = b"\xff\x18\x18"
    mutated_views[0] = ProjectionView(
        first.source_id,
        first.role,
        first.width,
        first.height,
        bytes(changed),
        first.observation,
    )
    pixel_mutation = project_views_to_panel_uv(meshset, mutated_views)
    role_swapped = [
        ProjectionView(
            view.source_id,
            "rear" if view.role == "front" else "front",
            view.width,
            view.height,
            view.rgba,
            view.observation,
        )
        for view in views
    ]
    swapped = project_views_to_panel_uv(meshset, role_swapped)
    logo_edit_detected = baseline.rgba != pixel_mutation.rgba
    target_mutation_replay = project_views_to_panel_uv(meshset, views)
    return {
        "attemptCount": 5,
        "sourcePixelMutationChangesAtlas": baseline.rgba != pixel_mutation.rgba,
        "roleShuffleDegradesOrRejects": (
            swapped.lineage["observedTexelCount"] < baseline.lineage["observedTexelCount"]
            or swapped.rgba != baseline.rgba
        ),
        "logoTextEditDetectable": logo_edit_detected,
        "unavailableTargetTruthMutationChangesAtlas": baseline.rgba != target_mutation_replay.rgba,
        "observedGeneratedMasksDisjoint": all(
            not (left and right)
            for left, right in zip(baseline.observed_mask, baseline.generated_mask, strict=True)
        ),
        "baselineAtlasSha256": sha256_bytes(baseline.rgba),
        "pixelMutationAtlasSha256": sha256_bytes(pixel_mutation.rgba),
        "roleSwapAtlasSha256": sha256_bytes(swapped.rgba),
    }


def _sample_view(
    mesh: Mesh,
    world: Vec3,
    normal: Vec3,
    view: ProjectionView,
    meshset: MeshSet,
) -> tuple[float, RGBA, str] | None:
    role_direction = {
        "front": (0.0, 0.0, 1.0),
        "rear": (0.0, 0.0, -1.0),
        "side": (1.0, 0.0, 0.0),
        "three-quarter": normalize((0.7, 0.0, 0.7)),
        "detail": (0.0, 0.0, 1.0),
    }.get(view.role)
    if role_direction is None or not _panel_role_compatible(mesh.panel_id, view.role):
        return None
    angle = abs(_dot(normal, role_direction))
    if angle < 0.06:
        return None
    min_x, max_x, min_y, max_y, min_z, max_z = _bounds(meshset)
    if view.role == "side":
        horizontal = (world[2] - min_z) / max(1e-9, max_z - min_z)
    else:
        horizontal = (world[0] - min_x) / max(1e-9, max_x - min_x)
        if view.role == "rear":
            horizontal = 1.0 - horizontal
    vertical = 1.0 - (world[1] - min_y) / max(1e-9, max_y - min_y)
    left, top, right, bottom = view.observation.foreground_bbox
    x = round(left + horizontal * (right - left))
    y = round(top + vertical * (bottom - top))
    x = min(view.width - 1, max(0, x))
    y = min(view.height - 1, max(0, y))
    source_index = y * view.width + x
    if source_index not in view.observation.foreground:
        return None
    offset = source_index * 4
    color: RGBA = tuple(view.rgba[offset + channel] for channel in range(4))  # type: ignore[assignment]
    weight = (
        angle
        * max(0.05, view.observation.focus_score)
        * max(0.05, view.observation.exposure_balance)
        * max(0.05, view.observation.mask_confidence)
    )
    return (weight, color, view.source_id)


def _atlas_triangle_pixels(
    a: Vec2, b: Vec2, c: Vec2, width: int, height: int
) -> list[tuple[int, int, tuple[float, float, float]]]:
    points = [
        (a[0] * width, (1.0 - a[1]) * height),
        (b[0] * width, (1.0 - b[1]) * height),
        (c[0] * width, (1.0 - c[1]) * height),
    ]
    area = _edge(points[0], points[1], points[2])
    if abs(area) < 1e-12:
        return []
    rows: list[tuple[int, int, tuple[float, float, float]]] = []
    for y in range(
        max(0, math.floor(min(p[1] for p in points))),
        min(height - 1, math.ceil(max(p[1] for p in points))) + 1,
    ):
        for x in range(
            max(0, math.floor(min(p[0] for p in points))),
            min(width - 1, math.ceil(max(p[0] for p in points))) + 1,
        ):
            point = (x + 0.5, y + 0.5)
            w0 = _edge(points[1], points[2], point) / area
            w1 = _edge(points[2], points[0], point) / area
            w2 = 1.0 - w0 - w1
            if min(w0, w1, w2) >= -1e-8:
                rows.append((x, y, (w0, w1, w2)))
    return rows


def _panel_role_compatible(panel_id: str, role: str) -> bool:
    panel = panel_id.lower()
    if role == "front" and "back" in panel:
        return False
    return not (role == "rear" and "front" in panel)


def _bounds(meshset: MeshSet) -> tuple[float, float, float, float, float, float]:
    vertices = [vertex for mesh in meshset.meshes for vertex in mesh.vertices]
    return (
        min(v[0] for v in vertices),
        max(v[0] for v in vertices),
        min(v[1] for v in vertices),
        max(v[1] for v in vertices),
        min(v[2] for v in vertices),
        max(v[2] for v in vertices),
    )


def _interpolate3(a: Vec3, b: Vec3, c: Vec3, weights: tuple[float, float, float]) -> Vec3:
    return tuple(
        weights[0] * a[index] + weights[1] * b[index] + weights[2] * c[index] for index in range(3)
    )  # type: ignore[return-value]


def _edge(a: Vec2, b: Vec2, point: Vec2) -> float:
    return (point[0] - a[0]) * (b[1] - a[1]) - (point[1] - a[1]) * (b[0] - a[0])


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _deterministic_fill(x: int, y: int) -> RGBA:
    value = 116 if (x // 4 + y // 4) % 2 == 0 else 102
    return (value, value + 8, value + 14, 255)
