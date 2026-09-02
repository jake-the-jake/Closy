from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from closy_forge.d0_v4_engineering.observation import (
    FEATURE_NAMES,
    ObservationRejected,
    apply_crop_and_padding,
    extract_observation,
    load_observation_contract,
    observation_contract,
)

ROOT = Path(__file__).resolve().parents[2]


def test_contract_is_checked_in_and_training_inference_shared() -> None:
    checked_in = load_observation_contract(ROOT)
    assert checked_in == observation_contract()
    assert checked_in["alphaConvention"] == "alpha_is_advisory_not_foreground_authority"
    assert len(checked_in["featureNames"]) == 40


def test_opaque_rgb_foreground_does_not_repeat_v3_alpha_failure() -> None:
    png = _fixture_png(background=(208, 200, 238), garment=(40, 92, 160))
    observation = extract_observation(png, png, metadata={"front": {}, "rear": {}})
    assert observation["views"]["front"]["alphaFullyOpaque"] is True
    assert observation["views"]["front"]["foregroundPixelCount"] > 1000
    assert observation["featureNames"] == list(FEATURE_NAMES)
    assert observation["pixelDerived"] is True


def test_crop_changes_pixels_dimensions_and_transform() -> None:
    original = _fixture_png(background=(220, 218, 210), garment=(72, 104, 142))
    cropped, transform = apply_crop_and_padding(
        original,
        crop_fraction=0.05,
        padding_fraction=0.0,
        background_rgb=(220, 218, 210),
    )
    assert cropped != original
    assert transform["pixelsChanged"] is True
    assert transform["dimensionsChanged"] is True
    assert transform["sourceSize"] == [128, 160]
    assert transform["outputSize"] != transform["sourceSize"]
    observation = extract_observation(
        cropped,
        None,
        metadata={"front": {"observationToOriginalTransform": transform}},
    )
    assert observation["route"] == "front_only_bounded"
    assert observation["views"]["rear"]["status"] == "missing"
    assert observation["views"]["front"]["observationToOriginalTransform"] == transform


def test_random_backgrounds_and_pixel_mutation_change_features() -> None:
    first = _fixture_png(background=(232, 226, 215), garment=(47, 96, 180))
    second = _fixture_png(background=(176, 210, 202), garment=(47, 96, 180), sleeve=28)
    left = extract_observation(first, first, metadata={"front": {}, "rear": {}})
    right = extract_observation(second, second, metadata={"front": {}, "rear": {}})
    assert left["featureValues"] != right["featureValues"]
    assert left["views"]["front"]["backgroundRgb"] != right["views"]["front"]["backgroundRgb"]


def test_corrupt_or_background_only_png_fails_closed() -> None:
    with pytest.raises(ObservationRejected, match="corrupt_png"):
        extract_observation(b"not-a-png", None, metadata={"front": {}})
    image = Image.new("RGBA", (128, 160), (210, 210, 210, 255))
    with pytest.raises(ObservationRejected, match="foreground_not_found"):
        extract_observation(_encode(image), None, metadata={"front": {}})


def _fixture_png(
    *,
    background: tuple[int, int, int],
    garment: tuple[int, int, int],
    sleeve: int = 22,
) -> bytes:
    image = Image.new("RGBA", (128, 160), (*background, 255))
    draw = ImageDraw.Draw(image)
    draw.polygon(
        [
            (42, 30),
            (25 - sleeve // 4, 40),
            (18, 63),
            (38, 66),
            (39, 126),
            (89, 126),
            (90, 66),
            (110, 63),
            (103 + sleeve // 4, 40),
            (86, 30),
        ],
        fill=(*garment, 255),
    )
    draw.ellipse((55, 24, 73, 43), fill=(*background, 255))
    return _encode(image)


def _encode(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
