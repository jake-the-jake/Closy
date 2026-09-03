from __future__ import annotations

from pathlib import Path

from closy_forge.d0_v4_engineering.appearance import (
    recover_source_to_uv,
    rerender_from_persisted_atlas,
)
from closy_forge.d0_v4_engineering.corpus import load_partition
from closy_forge.package_io.hashing import sha256_bytes

ROOT = Path(__file__).resolve().parents[2]


def test_source_to_uv_atlas_has_per_texel_lineage_and_safe_pbr_maps() -> None:
    record = load_partition(ROOT, "validation")[0]
    appearance = recover_source_to_uv(record["frontPng"], record["rearPng"])
    manifest = appearance.manifest
    assert manifest["texelCount"] == 256 * 160
    assert manifest["observedTexelCount"] > 0
    assert manifest["generatedControlledFillTexelCount"] > 0
    assert manifest["billboardOrSourcePlaneUsed"] is False
    assert manifest["evaluationTimeReprojectionUsed"] is False
    assert manifest["physicalMaterialAccuracyClaimed"] is False
    assert manifest["perTexelLineage"]["uncompressedBytes"] == 256 * 160 * 5


def test_rerender_uses_persisted_atlas_for_front_rear_and_novel_views() -> None:
    record = load_partition(ROOT, "validation")[1]
    appearance = recover_source_to_uv(record["frontPng"], record["rearPng"])
    background = tuple(record["capture"]["backgroundSrgb"])
    front = rerender_from_persisted_atlas(
        appearance,
        record["frontPng"],
        role="front",
        output_background=background,
    )
    novel = rerender_from_persisted_atlas(
        appearance,
        record["frontPng"],
        role="novel",
        azimuth_degrees=52.0,
        output_background=background,
    )
    assert front
    assert novel
    assert sha256_bytes(front) != sha256_bytes(novel)


def test_source_pixel_and_logo_translation_causally_change_atlas() -> None:
    records = load_partition(ROOT, "validation")
    left = recover_source_to_uv(records[1]["frontPng"], records[1]["rearPng"])
    right = recover_source_to_uv(records[2]["frontPng"], records[2]["rearPng"])
    assert left.manifest["baseColorSha256"] != right.manifest["baseColorSha256"]


def test_low_contrast_logo_survives_panel_uv_recovery() -> None:
    from io import BytesIO

    from PIL import Image

    record = load_partition(ROOT, "validation")[91]
    appearance = recover_source_to_uv(record["frontPng"], record["rearPng"])
    logo = tuple(record["appearance"]["logoColorSrgb"])
    with Image.open(BytesIO(appearance.base_color_png)) as image:
        colours = [pixel[:3] for pixel in image.convert("RGBA").getdata()]
    assert logo in colours
    assert appearance.manifest["atlasVersion"].endswith(".v2")
