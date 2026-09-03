from __future__ import annotations

import base64
from pathlib import Path

from closy_forge.d0_v4_engineering.container_entry import (
    ROUTES,
    execute_container_request,
)
from closy_forge.d0_v4_engineering.corpus import load_partition
from closy_forge.d0_v4_engineering.model import MODEL_ROOT, load_model

ROOT = Path(__file__).resolve().parents[2]


def _request(record: dict[str, object], route: str) -> dict[str, object]:
    capture = record["capture"]
    assert isinstance(capture, dict)
    front = record["frontPng"]
    assert isinstance(front, bytes)
    rear = record.get("rearPng")
    return {
        "requestId": f"unit-{route}",
        "route": route,
        "frontPngBase64": base64.b64encode(front).decode("ascii"),
        "rearPngBase64": (
            base64.b64encode(rear).decode("ascii") if isinstance(rear, bytes) else None
        ),
        "metadata": {
            "front": {
                "camera": capture["frontCamera"],
                "observationToOriginalTransform": capture["frontTransform"],
            },
            "rear": {
                "camera": capture["rearCamera"],
                "observationToOriginalTransform": capture["rearTransform"],
            },
        },
    }


def test_every_preregistered_route_uses_one_strict_entry_contract() -> None:
    model = load_model(ROOT / MODEL_ROOT / "trial-006.json")
    record = load_partition(ROOT, "validation")[0]
    statuses = {}
    for route in ROUTES:
        response = execute_container_request(_request(record, route), model)
        statuses[route] = response["prediction"]["status"]
        assert response["route"] == route
        assert response["targetOrEvaluatorFieldsAccepted"] is False
    assert statuses == {
        "metadata_control": "abstained",
        "no_pixel_template_prior": "predicted",
        "deterministic_pixel_fitting": "predicted",
        "learned_refined_structured": "predicted",
    }


def test_entry_rejects_target_evaluator_fields_and_missing_pixels() -> None:
    model = load_model(ROOT / MODEL_ROOT / "trial-006.json")
    record = load_partition(ROOT, "validation")[0]
    leaked = _request(record, "learned_refined_structured")
    leaked["targetParameters"] = record["parameters"]
    response = execute_container_request(leaked, model)
    assert response["prediction"]["status"] == "rejected"
    assert response["prediction"]["reason"].startswith("undeclared_request_fields:")

    missing = _request(record, "learned_refined_structured")
    missing["frontPngBase64"] = None
    response = execute_container_request(missing, model)
    assert response["prediction"] == {
        "status": "rejected",
        "reason": "front_pixels_required",
        "parameters": None,
        "targetParametersRead": False,
    }


def test_entry_rejects_corrupt_capture_without_compiler_defaults() -> None:
    model = load_model(ROOT / MODEL_ROOT / "trial-006.json")
    record = load_partition(ROOT, "validation")[0]
    request = _request(record, "learned_refined_structured")
    request["frontPngBase64"] = base64.b64encode(b"not-png").decode("ascii")
    response = execute_container_request(request, model)
    assert response["prediction"]["status"] == "rejected"
    assert response["prediction"]["parameters"] is None
