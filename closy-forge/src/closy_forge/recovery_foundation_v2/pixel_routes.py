from __future__ import annotations

import io
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageDraw

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes

ROUTES = (
    "metadata_category_control",
    "no_pixel_template_prior",
    "pixel_mask_landmark_optimiser",
    "pixel_learned_structured_tshirt",
)
FULL_COMPILE_ROUTES = ROUTES[1:]
PRIMARY_ROUTE = ROUTES[3]
FEATURES = ("body_height", "torso_width", "shoulder_width", "sleeve_extent")
TARGETS = ("garment_body_length", "half_chest_width", "shoulder_width", "sleeve_length")


def decode_pixel_observations(front_png: bytes, rear_png: bytes) -> dict[str, Any]:
    front = _decode_rgba(front_png)
    rear = _decode_rgba(rear_png)
    front_stats = _mask_statistics(front)
    rear_stats = _mask_statistics(rear)
    features = {
        name: math.fsum([float(front_stats[name]), float(rear_stats[name])]) / 2.0
        for name in FEATURES
    }
    return {
        "observationVersion": "closy.d0_v3.pixel_observation.v1",
        "decodedRoles": ["front_png", "rear_png"],
        "sourceHashes": {
            "front": sha256_bytes(front_png),
            "rear": sha256_bytes(rear_png),
        },
        "front": front_stats,
        "rear": rear_stats,
        "features": features,
        "pixelLineageDigest": sha256_bytes(
            canonical_dumps({"front": front_stats, "rear": rear_stats}).encode("utf-8")
        ),
    }


def run_route(
    route: str,
    *,
    front_png: bytes | None,
    rear_png: bytes | None,
    model: Mapping[str, Any] | None = None,
    category: str = "tshirt",
) -> dict[str, Any]:
    if route not in ROUTES:
        raise ValueError(f"d0_v3_route_unknown:{route}")
    if category != "tshirt":
        raise ValueError("d0_v3_category_prior_invalid")
    if route in ROUTES[2:] and (front_png is None or rear_png is None):
        raise ValueError(f"d0_v3_required_pixels_missing:{route}")
    if route == ROUTES[0]:
        parameters = _metadata_prior()
        observation: dict[str, Any] | None = None
    elif route == ROUTES[1]:
        parameters = _template_prior()
        observation = None
    else:
        assert front_png is not None and rear_png is not None
        observation = decode_pixel_observations(front_png, rear_png)
        if route == ROUTES[2]:
            parameters = _mask_prediction(_mapping(observation["features"]))
        else:
            if model is None:
                raise ValueError("d0_v3_fitted_model_missing")
            validate_fitted_model(model)
            parameters = _learned_prediction(_mapping(observation["features"]), model)
    record = {
        "routeId": route,
        "inputRoles": ["tshirt_category"]
        if observation is None
        else ["tshirt_category", "front_png", "rear_png"],
        "pixelsConsumed": observation is not None,
        "pixelObservation": observation,
        "parameters": parameters,
        "pbr": {
            "baseColorSource": "source_pixels" if observation is not None else "bounded_preset",
            "roughnessSource": "bounded_preset_unobserved",
            "metalnessSource": "bounded_preset_unobserved",
            "aoSource": "bounded_preset_unobserved",
            "sourceObservedPhysicalMaterialFraction": 0.0,
        },
    }
    record["predictionDigest"] = sha256_bytes(canonical_dumps(record).encode("utf-8"))
    return record


def fit_public_development_model(sample_count: int = 24) -> dict[str, Any]:
    if sample_count < 8:
        raise ValueError("d0_v3_training_sample_count_too_small")
    observations: list[dict[str, float]] = []
    targets: list[dict[str, float]] = []
    inventory = build_public_training_inventory(sample_count)
    for record in inventory["records"]:
        ordinal = int(record["ordinal"])
        values = {key: float(value) for key, value in _mapping(record["parameters"]).items()}
        front = render_public_tshirt_png(values, rear=False, logo=ordinal % 2 == 0)
        rear = render_public_tshirt_png(values, rear=True, logo=False)
        observation = decode_pixel_observations(front, rear)
        observations.append(
            {key: float(value) for key, value in _mapping(observation["features"]).items()}
        )
        targets.append(values)
    feature_for_target = dict(zip(TARGETS, FEATURES, strict=True))
    weights: dict[str, dict[str, float | str]] = {}
    for target, feature in feature_for_target.items():
        x_values = [row[feature] for row in observations]
        y_values = [row[target] for row in targets]
        slope, intercept = _least_squares(x_values, y_values)
        weights[target] = {"feature": feature, "slope": slope, "intercept": intercept}
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "modelVersion": "closy.d0_v3.public_pixel_fitted_tshirt.v1",
        "trainingClass": "public_fixed_pre_v3_development_only",
        "sampleCount": sample_count,
        "trainingOrCalibrationOnV3": False,
        "features": list(FEATURES),
        "targets": list(TARGETS),
        "weights": weights,
        "trainingInventoryDigest": inventory["inventoryDigest"],
        "modelDigest": "",
    }
    document["modelDigest"] = _document_digest(document, "modelDigest")
    return document


def build_public_training_inventory(sample_count: int = 24) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for ordinal in range(sample_count):
        values = {
            "garment_body_length": 0.52 + 0.008 * (ordinal % 8),
            "half_chest_width": 0.235 + 0.006 * ((ordinal * 3) % 8),
            "shoulder_width": 0.62 + 0.012 * ((ordinal * 5) % 8),
            "sleeve_length": 0.18 + 0.009 * ((ordinal * 7) % 8),
        }
        front = render_public_tshirt_png(values, rear=False, logo=ordinal % 2 == 0)
        rear = render_public_tshirt_png(values, rear=True, logo=False)
        records.append(
            {
                "ordinal": ordinal,
                "identityClass": "public_pre_v3_development_ineligible",
                "parameters": values,
                "frontPngSha256": sha256_bytes(front),
                "rearPngSha256": sha256_bytes(rear),
            }
        )
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "inventoryVersion": "closy.d0_v3.public_pixel_training_inventory.v1",
        "sampleCount": sample_count,
        "qualificationEligible": False,
        "renderer": "render_public_tshirt_png",
        "extractor": "decode_pixel_observations",
        "records": records,
        "inventoryDigest": "",
    }
    document["inventoryDigest"] = _document_digest(document, "inventoryDigest")
    return document


def validate_fitted_model(model: Mapping[str, Any]) -> None:
    if model.get("trainingClass") != "public_fixed_pre_v3_development_only":
        raise ValueError("d0_v3_model_training_class_invalid")
    if model.get("trainingOrCalibrationOnV3") is not False:
        raise ValueError("d0_v3_model_v3_leakage")
    if model.get("sampleCount") != 24:
        raise ValueError("d0_v3_model_sample_denominator_invalid")
    if tuple(model.get("features", ())) != FEATURES or tuple(model.get("targets", ())) != TARGETS:
        raise ValueError("d0_v3_model_contract_invalid")
    if _document_digest(model, "modelDigest") != model.get("modelDigest"):
        raise ValueError("d0_v3_model_digest_invalid")


def load_fitted_model(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, Mapping):
        raise ValueError("d0_v3_model_mapping_required")
    model = dict(value)
    validate_fitted_model(model)
    return model


def render_public_tshirt_png(parameters: Mapping[str, float], *, rear: bool, logo: bool) -> bytes:
    size = 128
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    body_height = int(float(parameters["garment_body_length"]) * 112)
    torso_half = int(float(parameters["half_chest_width"]) * 96)
    shoulder_half = int(float(parameters["shoulder_width"]) * 52)
    sleeve = int(float(parameters["sleeve_length"]) * 90)
    center = 64
    top = 22
    bottom = min(119, top + body_height)
    colour = (70, 112, 148, 255) if not rear else (65, 104, 138, 255)
    polygon = [
        (center - shoulder_half, top + 8),
        (center - shoulder_half - sleeve, top + 18),
        (center - shoulder_half - sleeve + 4, top + 31),
        (center - torso_half, top + 28),
        (center - torso_half, bottom),
        (center + torso_half, bottom),
        (center + torso_half, top + 28),
        (center + shoulder_half + sleeve - 4, top + 31),
        (center + shoulder_half + sleeve, top + 18),
        (center + shoulder_half, top + 8),
    ]
    draw.polygon(polygon, fill=colour)
    draw.ellipse((center - 9, top + 2, center + 9, top + 16), fill=(0, 0, 0, 0))
    if logo and not rear:
        draw.rectangle((center - 6, top + 30, center + 6, top + 40), fill=(228, 218, 185, 255))
    output = io.BytesIO()
    image.save(output, format="PNG", compress_level=9)
    return output.getvalue()


def apply_crop_and_occlusion(png: bytes, *, crop_pixels: int, occlusion_width: int) -> bytes:
    image = _decode_rgba(png)
    if crop_pixels < 0 or crop_pixels >= image.width // 4:
        raise ValueError("d0_v3_crop_invalid")
    if crop_pixels:
        image = image.crop(
            (
                crop_pixels,
                crop_pixels,
                image.width - crop_pixels,
                image.height - crop_pixels,
            )
        )
    if occlusion_width:
        draw = ImageDraw.Draw(image)
        center = image.width // 2
        draw.rectangle(
            (
                center - occlusion_width // 2,
                image.height // 2,
                center + occlusion_width // 2,
                image.height,
            ),
            fill=(0, 0, 0, 0),
        )
    output = io.BytesIO()
    image.save(output, format="PNG", compress_level=9)
    return output.getvalue()


def build_pixel_causal_controls(model: Mapping[str, Any]) -> dict[str, Any]:
    parameters = {
        "garment_body_length": 0.58,
        "half_chest_width": 0.26,
        "shoulder_width": 0.68,
        "sleeve_length": 0.22,
    }
    front = render_public_tshirt_png(parameters, rear=False, logo=True)
    rear = render_public_tshirt_png(parameters, rear=True, logo=False)
    changed = apply_crop_and_occlusion(front, crop_pixels=3, occlusion_width=9)
    baseline = run_route(PRIMARY_ROUTE, front_png=front, rear_png=rear, model=model)
    changed_result = run_route(PRIMARY_ROUTE, front_png=changed, rear_png=rear, model=model)
    negative_model = dict(model)
    negative_weights = {
        target: {"feature": feature, "slope": 0.0, "intercept": 0.0}
        for target, feature in zip(TARGETS, FEATURES, strict=True)
    }
    negative_model["weights"] = negative_weights
    negative_model["modelDigest"] = _document_digest(negative_model, "modelDigest")
    negative = run_route(PRIMARY_ROUTE, front_png=front, rear_png=rear, model=negative_model)
    mask = run_route(ROUTES[2], front_png=front, rear_png=rear)
    return {
        "schemaVersion": 1,
        "fixtureClass": "public_contaminated_development_non_qualifying",
        "missingPixelsRejected": _raises_missing_pixels(model),
        "pixelMutationChangesObservation": (
            _mapping(baseline["pixelObservation"])["pixelLineageDigest"]
            != _mapping(changed_result["pixelObservation"])["pixelLineageDigest"]
        ),
        "cropAndOcclusionChangeBytes": sha256_bytes(front) != sha256_bytes(changed),
        "negativeModelChangesPrediction": (
            baseline["predictionDigest"] != negative["predictionDigest"]
        ),
        "learnedAndMaskRoutesDistinct": baseline["predictionDigest"] != mask["predictionDigest"],
        "metadataControlConsumesPixels": False,
        "sourceObservedPbrFraction": 0.0,
    }


def _raises_missing_pixels(model: Mapping[str, Any]) -> bool:
    try:
        run_route(PRIMARY_ROUTE, front_png=None, rear_png=None, model=model)
    except ValueError:
        return True
    return False


def _decode_rgba(data: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            if source.format != "PNG":
                raise ValueError("d0_v3_png_required")
            return cast(Image.Image, source.convert("RGBA"))
    except (OSError, ValueError) as error:
        raise ValueError("d0_v3_png_decode_failed") from error


def _mask_statistics(image: Image.Image) -> dict[str, float | int]:
    alpha = image.getchannel("A")
    bounds = alpha.getbbox()
    if bounds is None:
        raise ValueError("d0_v3_pixel_mask_empty")
    left, top, right, bottom = bounds
    width = float(image.width)
    height = float(image.height)
    row_widths: list[int] = []
    pixels = alpha.load()
    assert pixels is not None
    foreground = 0
    for y in range(image.height):
        occupied = [x for x in range(image.width) if cast(int, pixels[x, y]) > 0]
        foreground += len(occupied)
        if occupied:
            row_widths.append(occupied[-1] - occupied[0] + 1)
    torso_rows = row_widths[len(row_widths) // 2 :]
    torso_width = float(sorted(torso_rows)[len(torso_rows) // 2]) / width
    shoulder_width = float(max(row_widths)) / width
    return {
        "imageWidth": image.width,
        "imageHeight": image.height,
        "foregroundPixels": foreground,
        "foregroundFraction": foreground / float(image.width * image.height),
        "body_height": (bottom - top) / height,
        "torso_width": torso_width,
        "shoulder_width": shoulder_width,
        "sleeve_extent": max(0.0, shoulder_width - torso_width),
    }


def _mask_prediction(features: Mapping[str, Any]) -> dict[str, float]:
    return {
        "garment_body_length": float(features["body_height"]) * 1.05,
        "half_chest_width": float(features["torso_width"]) * 0.52,
        "shoulder_width": float(features["shoulder_width"]) * 0.92,
        "sleeve_length": float(features["sleeve_extent"]) * 0.62,
    }


def _learned_prediction(features: Mapping[str, Any], model: Mapping[str, Any]) -> dict[str, float]:
    weights = _mapping(model["weights"])
    result: dict[str, float] = {}
    for target in TARGETS:
        row = _mapping(weights[target])
        value = float(row["intercept"]) + float(row["slope"]) * float(features[str(row["feature"])])
        result[target] = value
    return result


def _metadata_prior() -> dict[str, float]:
    return dict(zip(TARGETS, (0.62, 0.285, 0.70, 0.255), strict=True))


def _template_prior() -> dict[str, float]:
    return dict(zip(TARGETS, (0.60, 0.27, 0.67, 0.23), strict=True))


def _least_squares(x_values: Sequence[float], y_values: Sequence[float]) -> tuple[float, float]:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        raise ValueError("d0_v3_fit_shape_invalid")
    x_mean = math.fsum(x_values) / len(x_values)
    y_mean = math.fsum(y_values) / len(y_values)
    numerator = math.fsum(
        (x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values, strict=True)
    )
    denominator = math.fsum((x - x_mean) ** 2 for x in x_values)
    if denominator <= 0.0:
        raise ValueError("d0_v3_fit_singular")
    slope = numerator / denominator
    return slope, y_mean - slope * x_mean


def _document_digest(document: Mapping[str, Any], field: str) -> str:
    payload = dict(document)
    payload[field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
