from __future__ import annotations

import base64
from collections.abc import Mapping
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .appearance import recover_source_to_uv
from .container_entry import execute_container_request
from .corpus import load_partition
from .model import load_model
from .observation import apply_crop_and_padding, extract_observation

CONTROL_VERSION = "closy.d0_v4.validation_negative_controls.v1"


def run_negative_controls(root: Path, model_path: Path) -> dict[str, Any]:
    model = load_model(model_path)
    records = load_partition(root, "validation")
    complete = next(record for record in records if record.get("rearPng") is not None)
    front_only = next(record for record in records if record.get("rearPng") is None)
    logo_record = next(
        record for record in records if _mapping(record["appearance"])["logoShape"] != "none"
    )
    normal_request = _request(complete)
    normal = execute_container_request(normal_request, model)

    missing_request = dict(normal_request)
    missing_request["frontPngBase64"] = None
    missing = execute_container_request(missing_request, model)

    shuffled_request = dict(normal_request)
    shuffled_request["frontPngBase64"] = _encoded(_shuffle_rows(complete["frontPng"]))
    shuffled = execute_container_request(shuffled_request, model)

    wrong_model = deepcopy(model)
    wrong_model["weights"][0][0] = float(wrong_model["weights"][0][0]) + 0.25
    wrong = execute_container_request(normal_request, wrong_model)

    removed_logo = _replace_logo(logo_record, translate_pixels=0, remove=True)
    translated_logo = _replace_logo(logo_record, translate_pixels=7, remove=False)
    original_appearance = recover_source_to_uv(logo_record["frontPng"], logo_record.get("rearPng"))
    removed_appearance = recover_source_to_uv(removed_logo, logo_record.get("rearPng"))
    translated_appearance = recover_source_to_uv(translated_logo, logo_record.get("rearPng"))

    capture = _mapping(complete["capture"])
    background_values = capture["backgroundSrgb"]
    background = (
        int(background_values[0]),
        int(background_values[1]),
        int(background_values[2]),
    )
    altered_crop, altered_transform = apply_crop_and_padding(
        complete["frontPng"],
        crop_fraction=min(0.12, float(capture["cropFraction"]) + 0.05),
        padding_fraction=float(capture["paddingFraction"]),
        background_rgb=background,
    )
    original_observation = extract_observation(
        complete["frontPng"],
        complete.get("rearPng"),
        metadata=_metadata(complete),
    )
    altered_metadata = _metadata(complete)
    altered_metadata["front"]["observationToOriginalTransform"] = altered_transform
    altered_observation = extract_observation(
        altered_crop,
        complete.get("rearPng"),
        metadata=altered_metadata,
    )

    corrupt_request = dict(normal_request)
    corrupt_request["frontPngBase64"] = _encoded(b"not-a-png")
    corrupt = execute_container_request(corrupt_request, model)

    front_only_result = execute_container_request(_request(front_only), model)
    target_request = dict(normal_request)
    target_request["targetParameters"] = complete["parameters"]
    target_access = execute_container_request(target_request, model)
    evaluator_request = dict(normal_request)
    evaluator_request["evaluator"] = {"thresholdOverride": 1.0}
    evaluator_access = execute_container_request(evaluator_request, model)

    controls = {
        "missingPixels": {
            "pass": _status(missing) == "rejected",
            "status": _status(missing),
        },
        "shuffledPixels": {
            "pass": _prediction_digest(normal) != _prediction_digest(shuffled),
            "normalPredictionDigest": _prediction_digest(normal),
            "shuffledPredictionDigest": _prediction_digest(shuffled),
        },
        "wrongModel": {
            "pass": _status(wrong) == "rejected",
            "status": _status(wrong),
        },
        "removedLogo": {
            "pass": original_appearance.manifest["baseColorSha256"]
            != removed_appearance.manifest["baseColorSha256"],
            "originalAtlasSha256": original_appearance.manifest["baseColorSha256"],
            "removedAtlasSha256": removed_appearance.manifest["baseColorSha256"],
        },
        "translatedLogo": {
            "pass": original_appearance.manifest["baseColorSha256"]
            != translated_appearance.manifest["baseColorSha256"],
            "originalAtlasSha256": original_appearance.manifest["baseColorSha256"],
            "translatedAtlasSha256": translated_appearance.manifest["baseColorSha256"],
        },
        "alteredCrop": {
            "pass": (
                sha256_bytes(complete["frontPng"]) != sha256_bytes(altered_crop)
                and complete["capture"]["frontTransform"] != altered_transform
                and original_observation["featureValues"] != altered_observation["featureValues"]
            ),
            "sourceSha256": sha256_bytes(complete["frontPng"]),
            "alteredSha256": sha256_bytes(altered_crop),
            "alteredTransform": altered_transform,
        },
        "corruptPng": {
            "pass": _status(corrupt) == "rejected",
            "status": _status(corrupt),
        },
        "missingRear": {
            "pass": (
                _status(front_only_result) == "predicted"
                and _prediction(front_only_result).get("observationRoute") == "front_only_bounded"
            ),
            "status": _status(front_only_result),
            "route": _prediction(front_only_result).get("observationRoute"),
        },
        "targetAccess": {
            "pass": _status(target_access) == "rejected",
            "status": _status(target_access),
        },
        "evaluatorAccess": {
            "pass": _status(evaluator_access) == "rejected",
            "status": _status(evaluator_access),
        },
    }
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "controlVersion": CONTROL_VERSION,
        "partition": "validation",
        "publicTestRead": False,
        "controls": controls,
        "allPass": all(bool(_mapping(control).get("pass")) for control in controls.values()),
        "resultDigest": "",
    }
    result["resultDigest"] = _digest(result)
    return result


def _request(record: Mapping[str, Any]) -> dict[str, Any]:
    rear = record.get("rearPng")
    return {
        "requestId": str(record["identityHash"]),
        "route": "learned_refined_structured",
        "frontPngBase64": _encoded(record["frontPng"]),
        "rearPngBase64": _encoded(rear) if isinstance(rear, bytes) else None,
        "metadata": _metadata(record),
    }


def _metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    capture = _mapping(record["capture"])
    return {
        "front": {
            "camera": capture["frontCamera"],
            "observationToOriginalTransform": capture["frontTransform"],
        },
        "rear": {
            "camera": capture["rearCamera"],
            "observationToOriginalTransform": capture["rearTransform"],
        },
    }


def _shuffle_rows(png: bytes) -> bytes:
    with Image.open(BytesIO(png)) as image:
        rgba = image.convert("RGBA")
        rows = [rgba.crop((0, y, rgba.width, y + 1)) for y in range(rgba.height)]
        output_image = Image.new("RGBA", rgba.size)
        for destination, source in enumerate(reversed(rows)):
            output_image.paste(source, (0, destination))
    output = BytesIO()
    output_image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _replace_logo(record: Mapping[str, Any], *, translate_pixels: int, remove: bool) -> bytes:
    appearance = _mapping(record["appearance"])
    logo = tuple(int(value) for value in appearance["logoColorSrgb"])
    base = tuple(int(value) for value in appearance["baseColorSrgb"])
    with Image.open(BytesIO(record["frontPng"])) as image:
        rgba = image.convert("RGBA")
        pixels = list(rgba.getdata())
        logo_indices = [
            index
            for index, pixel in enumerate(pixels)
            if max(abs(pixel[channel] - logo[channel]) for channel in range(3)) <= 4
        ]
        for index in logo_indices:
            pixels[index] = (*base, 255)
        if not remove:
            for index in logo_indices:
                x = index % rgba.width
                y = index // rgba.width
                shifted_x = min(rgba.width - 1, x + translate_pixels)
                pixels[y * rgba.width + shifted_x] = (*logo, 255)
        rgba.putdata(pixels)
        output = BytesIO()
        rgba.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _status(response: Mapping[str, Any]) -> str:
    return str(_prediction(response).get("status"))


def _prediction(response: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping(response.get("prediction"))


def _prediction_digest(response: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(_prediction(response)).encode("utf-8"))


def _encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _digest(result: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(result))
    payload["resultDigest"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
