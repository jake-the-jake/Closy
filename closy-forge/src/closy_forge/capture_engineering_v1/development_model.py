from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .common import canonical_digest
from .quality import PixelObservation

MODEL_VERSION = "closy.capture_pixel_linear_development_model.v1"
FEATURE_NAMES = ("bias", "bboxWidth", "bboxHeight", "bboxAspect", "foregroundCoverage")


def pixel_features(observation: PixelObservation) -> list[float]:
    left, top, right, bottom = observation.foreground_bbox
    width = (right - left + 1) / observation.width
    height = (bottom - top + 1) / observation.height
    return [1.0, width, height, width / max(1e-9, height), observation.foreground_coverage]


def train_linear_model(
    rows: Sequence[tuple[str, PixelObservation, Mapping[str, float]]],
    *,
    target_fields: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    by_family: dict[str, list[tuple[PixelObservation, Mapping[str, float]]]] = {}
    for family, observation, target in rows:
        by_family.setdefault(family, []).append((observation, target))
    families: dict[str, Any] = {}
    for family, fields in sorted(target_fields.items()):
        family_rows = by_family.get(family, [])
        if len(family_rows) < len(FEATURE_NAMES):
            raise ValueError(f"insufficient_training_rows:{family}")
        matrix = [pixel_features(observation) for observation, _target in family_rows]
        families[family] = {
            "rowCount": len(family_rows),
            "fields": {
                field: _ridge_regression(
                    matrix,
                    [float(target[field]) for _observation, target in family_rows],
                    ridge=1e-6,
                )
                for field in fields
            },
        }
    model: dict[str, Any] = {
        "schemaVersion": 1,
        "modelVersion": MODEL_VERSION,
        "trainingEvidence": "project_authored_development_only",
        "validationRowsConsumed": False,
        "featureNames": list(FEATURE_NAMES),
        "families": families,
        "weightsPersisted": True,
        "modelDigest": "",
    }
    model["modelDigest"] = canonical_digest(model, "modelDigest")
    return model


def predict_linear_model(
    model: Mapping[str, Any], family: str, observation: PixelObservation
) -> dict[str, float]:
    if model.get("modelVersion") != MODEL_VERSION:
        raise ValueError("pixel_model_version_invalid")
    families = model.get("families")
    if not isinstance(families, Mapping) or family not in families:
        raise ValueError("pixel_model_family_missing")
    family_model = families[family]
    if not isinstance(family_model, Mapping):
        raise ValueError("pixel_model_family_invalid")
    fields = family_model.get("fields")
    if not isinstance(fields, Mapping):
        raise ValueError("pixel_model_fields_invalid")
    features = pixel_features(observation)
    result: dict[str, float] = {}
    for field, weights in fields.items():
        if not isinstance(weights, Sequence) or isinstance(weights, str | bytes):
            raise ValueError("pixel_model_weights_invalid")
        if len(weights) != len(features):
            raise ValueError("pixel_model_weight_count_invalid")
        result[str(field)] = sum(
            float(weight) * feature for weight, feature in zip(weights, features, strict=True)
        )
    return result


def _ridge_regression(matrix: list[list[float]], targets: list[float], ridge: float) -> list[float]:
    width = len(matrix[0])
    normal = [[0.0] * (width + 1) for _ in range(width)]
    for matrix_row, target in zip(matrix, targets, strict=True):
        for left in range(width):
            for right in range(width):
                normal[left][right] += matrix_row[left] * matrix_row[right]
            normal[left][-1] += matrix_row[left] * target
    for index in range(width):
        normal[index][index] += ridge
    for pivot in range(width):
        selected = max(range(pivot, width), key=lambda row: abs(normal[row][pivot]))
        normal[pivot], normal[selected] = normal[selected], normal[pivot]
        divisor = normal[pivot][pivot]
        if abs(divisor) < 1e-12:
            raise ValueError("pixel_model_singular")
        normal[pivot] = [value / divisor for value in normal[pivot]]
        for elimination_row in range(width):
            if elimination_row == pivot:
                continue
            factor = normal[elimination_row][pivot]
            normal[elimination_row] = [
                value - factor * source
                for value, source in zip(normal[elimination_row], normal[pivot], strict=True)
            ]
    return [round(normal[index][-1], 12) for index in range(width)]
