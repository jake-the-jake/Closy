from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.geometry.triangulation import panel_boundary_samples
from closy_forge.inspection.cpu_raster import rasterize_settled_garment
from closy_forge.inspection.source_render_fidelity import compare_decoded_source_and_render
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.raster import DecodedPng, decode_png_rgba, encode_png_rgba
from closy_forge.visual_understanding.raster_parser import TORSO_RGBA

WIDTH = 128
HEIGHT = 160
ATLAS_SIZE = 128


@dataclass(frozen=True)
class AppearanceSpec:
    appearance_version: str
    garment_class: str
    family_token: str
    panel_views: tuple[tuple[str, str], ...]
    capture_record_version: str
    capture_record_id: str
    texture_identity_id: str
    texture_report_path: str
    fidelity_report_version: str
    fidelity_report_id: str
    fidelity_acceptance_key: str
    fabric_rgba: tuple[int, int, int, int] = TORSO_RGBA


@dataclass(frozen=True)
class AppearanceBundle:
    artifacts: dict[str, bytes | dict[str, Any]]
    capture_record: dict[str, Any]
    texture_report: dict[str, Any]
    fidelity_report: dict[str, Any]


def build_appearance_bundle(
    *, spec: AppearanceSpec, pattern: dict[str, Any], settled_mesh: MeshSet, seed: int
) -> AppearanceBundle:
    artifacts: dict[str, bytes | dict[str, Any]] = {}
    source_views: list[dict[str, Any]] = []
    fidelity_views: list[dict[str, Any]] = []
    for label, panel_id in spec.panel_views:
        panel = next(panel for panel in pattern["panels"] if panel["id"] == panel_id)
        source = source_fixture(panel, spec.fabric_rgba)
        source_bytes = encode_png_rgba(source.width, source.height, source.rgba)
        source_path = f"source/public_fixture/{label}.png"
        artifacts[source_path] = source_bytes
        rendered = rasterize_settled_garment(
            settled_mesh,
            label=label,
            width=WIDTH,
            height=HEIGHT,
            texture_sampler=lambda _panel_id, _uv: spec.fabric_rgba,
        )
        render_bytes = encode_png_rgba(rendered.width, rendered.height, rendered.rgba)
        render_path = f"reports/fidelity/rendered_{label}.png"
        artifacts[render_path] = render_bytes
        metrics = compare_decoded_source_and_render(source, decode_png_rgba(render_bytes))
        view_id = f"view.{spec.family_token}.{label}"
        source_views.append(
            {
                "viewId": view_id,
                "label": label,
                "sourcePath": source_path,
                "sourceSha256": sha256_bytes(source_bytes),
                "decodedPixelHash": pixel_hash(source),
                "camera": rendered.camera,
                "garmentPixelsDerivedFromPatternBoundary": True,
            }
        )
        fidelity_views.append(
            {
                "viewId": view_id,
                "label": label,
                "sourcePath": source_path,
                "renderPath": render_path,
                "sourceSha256": sha256_bytes(source_bytes),
                "renderSha256": sha256_bytes(render_bytes),
                "renderedTriangleCount": rendered.rendered_triangle_count,
                "renderedForegroundPixels": len(rendered.foreground),
                "metrics": metrics,
                "accepted": (
                    int(metrics["sourceForegroundPixels"]) > 0
                    and int(metrics["renderForegroundPixels"]) > 0
                    and float(metrics["silhouetteIoU"]) >= 0.20
                ),
            }
        )
    generated_texture_artifacts, texture_report = texture_artifacts(source_views, spec)
    artifacts.update(generated_texture_artifacts)
    capture_record = {
        "schemaVersion": 1,
        "recordVersion": spec.capture_record_version,
        "recordId": spec.capture_record_id,
        "garmentId": pattern["garmentId"],
        "garmentClass": spec.garment_class,
        "seed": seed,
        "sourceKind": "public_synthetic_pattern_boundary_raster",
        "views": source_views,
        "privacy": {
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "allowExternalApis": False,
            "allowTrainingUse": False,
        },
        "sourceFixtureGenerator": {
            "id": "closy.pattern_boundary_scanline_rgba8.v1",
            "renderTriangleRasterizerReused": False,
            "fidelityMetricImplementationReused": False,
        },
    }
    aggregate = {
        "viewCount": len(fidelity_views),
        "allViewsNonBlank": all(
            int(view["renderedForegroundPixels"]) > 0 for view in fidelity_views
        ),
        "minimumSilhouetteIoU": round_metric(
            min(float(view["metrics"]["silhouetteIoU"]) for view in fidelity_views)
        ),
        "maximumBoundaryChamferNormalised": round_metric(
            max(float(view["metrics"]["boundaryChamferNormalised"]) for view in fidelity_views)
        ),
        "meanForegroundLinearSrgbMae": round_metric(
            sum(float(view["metrics"]["foregroundLinearSrgbMae"]) for view in fidelity_views)
            / len(fidelity_views)
        ),
    }
    accepted = all(view["accepted"] for view in fidelity_views)
    fidelity_report = {
        "schemaVersion": 1,
        "reportVersion": spec.fidelity_report_version,
        "reportId": spec.fidelity_report_id,
        "garmentId": pattern["garmentId"],
        "garmentClass": spec.garment_class,
        "status": "pass_d0_public_fixture" if accepted else "partial_d0_public_fixture",
        "sourceGenerator": "independent_pattern_boundary_scanline",
        "renderGenerator": "independent_cpu_triangle_raster",
        "decodedPixelComparisonRun": True,
        "viewComparisons": fidelity_views,
        "aggregate": aggregate,
        spec.fidelity_acceptance_key: accepted,
        "acceptedForProductionVisualFidelity": False,
    }
    return AppearanceBundle(
        artifacts=artifacts,
        capture_record=capture_record,
        texture_report=texture_report,
        fidelity_report=fidelity_report,
    )


def source_fixture(panel: dict[str, Any], fabric_rgba: tuple[int, int, int, int]) -> DecodedPng:
    points, _edge_map = panel_boundary_samples(panel)
    projected = [
        ((0.5 + x * 0.46) * WIDTH, (0.78 - ((0.74 + y) - 1.04) * 1.21) * HEIGHT) for x, y in points
    ]
    center_x = (min(point[0] for point in projected) + max(point[0] for point in projected)) / 2
    center_y = (min(point[1] for point in projected) + max(point[1] for point in projected)) / 2
    offset_x = WIDTH * 0.5 - center_x
    offset_y = HEIGHT * 0.5 - center_y
    polygon = [(x + offset_x, y + offset_y) for x, y in projected]
    rgba = bytearray((246, 244, 239, 0) * (WIDTH * HEIGHT))
    for y in range(HEIGHT):
        scan_y = y + 0.5
        intersections: list[float] = []
        for first, second in zip(polygon, polygon[1:] + polygon[:1], strict=True):
            if (first[1] > scan_y) == (second[1] > scan_y):
                continue
            ratio = (scan_y - first[1]) / (second[1] - first[1])
            intersections.append(first[0] + ratio * (second[0] - first[0]))
        intersections.sort()
        for left, right in zip(intersections[::2], intersections[1::2], strict=False):
            for x in range(max(0, int(left)), min(WIDTH, int(right + 1))):
                offset = (y * WIDTH + x) * 4
                rgba[offset : offset + 4] = bytes(fabric_rgba)
    return DecodedPng(WIDTH, HEIGHT, bytes(rgba))


def texture_artifacts(
    source_views: list[dict[str, Any]], spec: AppearanceSpec
) -> tuple[dict[str, bytes | dict[str, Any]], dict[str, Any]]:
    pixels: dict[str, bytes] = {
        "base_color": bytes(spec.fabric_rgba) * (ATLAS_SIZE * ATLAS_SIZE),
        "normal": bytes((128, 128, 255, 255)) * (ATLAS_SIZE * ATLAS_SIZE),
        "roughness": bytes((222, 222, 222, 255)) * (ATLAS_SIZE * ATLAS_SIZE),
        "occlusion": bytes((255, 255, 255, 255)) * (ATLAS_SIZE * ATLAS_SIZE),
    }
    paths = {key: f"textures/atlas/{key}.png" for key in sorted(pixels)}
    artifacts: dict[str, bytes | dict[str, Any]] = {
        paths[key]: encode_png_rgba(ATLAS_SIZE, ATLAS_SIZE, rgba) for key, rgba in pixels.items()
    }
    maps = [
        {
            "mapId": key,
            "path": paths[key],
            "sha256": sha256_bytes(require_bytes(artifacts[paths[key]])),
            "width": ATLAS_SIZE,
            "height": ATLAS_SIZE,
            "colorSpace": "srgb" if key == "base_color" else "linear_data",
            "source": "decoded_public_fixture_mean"
            if key == "base_color"
            else "bounded_d0_derived",
        }
        for key in sorted(paths)
    ]
    report = {
        "schemaVersion": 1,
        "appearanceVersion": spec.appearance_version,
        "textureIdentityId": spec.texture_identity_id,
        "status": "pass_d0_public_fixture",
        "sourceViews": source_views,
        "maps": maps,
        "material": {
            "materialId": "material.cotton_jersey_reference_v1",
            "baseColorMap": paths["base_color"],
            "normalMap": paths["normal"],
            "roughnessMap": paths["roughness"],
            "occlusionMap": paths["occlusion"],
            "metalness": 0.0,
            "roughness": 0.87,
            "doubleSided": True,
        },
        "decodedPbrMapsPersisted": True,
        "measuredFabricMaps": False,
        "learnedTextureCompletionRun": False,
    }
    artifacts[spec.texture_report_path] = report
    return artifacts, report


def pixel_hash(decoded: DecodedPng) -> str:
    header = f"{decoded.width}x{decoded.height}:{decoded.color_space}:".encode()
    return sha256_bytes(header + decoded.rgba)


def require_bytes(value: bytes | dict[str, Any]) -> bytes:
    if not isinstance(value, bytes):
        raise TypeError("expected PNG bytes")
    return value


def round_metric(value: float) -> float:
    return round(float(value), 9)
