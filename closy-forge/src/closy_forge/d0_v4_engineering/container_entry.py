from __future__ import annotations

import argparse
import base64
import binascii
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.disjoint_benchmark_v1.compiler import compile_structural_candidate
from closy_forge.package_io.canonical_json import canonical_dumps

from .fitting import _select_compile_valid_hypothesis, fit_source_conditioned, infer_hybrid
from .model import load_model, metadata_only_baseline

CONTAINER_ENTRY_VERSION = "closy.d0_v4.container_entry.v1"
ROUTES = (
    "metadata_control",
    "no_pixel_template_prior",
    "deterministic_pixel_fitting",
    "learned_refined_structured",
)
PIXEL_ROUTES = frozenset({"deterministic_pixel_fitting", "learned_refined_structured"})
_REQUEST_KEYS = frozenset({"requestId", "route", "frontPngBase64", "rearPngBase64", "metadata"})


def execute_container_request(
    request: Mapping[str, Any], model: Mapping[str, Any]
) -> dict[str, Any]:
    unknown = sorted(set(request) - _REQUEST_KEYS)
    if unknown:
        return _response(
            request,
            route=str(request.get("route", "unknown")),
            prediction=_rejection("undeclared_request_fields:" + ",".join(unknown)),
        )
    route = request.get("route")
    if route not in ROUTES:
        return _response(
            request,
            route=str(route),
            prediction=_rejection("route_invalid"),
        )
    metadata = request.get("metadata")
    if not isinstance(metadata, Mapping):
        return _response(
            request,
            route=route,
            prediction=_rejection("metadata_mapping_required"),
        )
    try:
        front = _decode_capture(request.get("frontPngBase64"), required=route in PIXEL_ROUTES)
        rear = _decode_capture(request.get("rearPngBase64"), required=False)
    except ValueError as exc:
        return _response(request, route=route, prediction=_rejection(str(exc)))
    prediction = execute_route(
        route,
        model=model,
        front_png=front,
        rear_png=rear,
        metadata=metadata,
    )
    return _response(request, route=route, prediction=prediction)


def execute_route(
    route: str,
    *,
    model: Mapping[str, Any],
    front_png: bytes | None,
    rear_png: bytes | None,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    if route == "metadata_control":
        return _rejection("metadata_control_has_no_structural_candidate", abstained=True)
    if route == "no_pixel_template_prior":
        parameters = metadata_only_baseline()
        compiled = compile_structural_candidate(parameters)
        return {
            "status": "predicted",
            "parameters": parameters,
            "compile": compiled.report,
            "evidenceClass": "no_pixel_template_prior",
            "targetParametersRead": False,
        }
    if front_png is None:
        return _rejection("front_pixels_required")
    if route == "deterministic_pixel_fitting":
        try:
            fitted = fit_source_conditioned(
                metadata_only_baseline(),
                front_png,
                rear_png,
                metadata=metadata,
            )
            parameters, compiled, selection = _select_compile_valid_hypothesis(
                fitted["parameters"], metadata_only_baseline()
            )
        except (KeyError, OSError, TypeError, ValueError) as exc:
            return _rejection(f"deterministic_fit_rejected:{type(exc).__name__}:{exc}")
        return {
            "status": "predicted",
            "parameters": parameters,
            "fit": {**fitted, "compileSelection": selection},
            "compile": compiled.report,
            "evidenceClass": "deterministic_source_pixel_fitting",
            "targetParametersRead": False,
        }
    if route == "learned_refined_structured":
        return infer_hybrid(model, front_png, rear_png, metadata=metadata)
    return _rejection("route_invalid")


def _response(
    request: Mapping[str, Any], *, route: str, prediction: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "containerEntryVersion": CONTAINER_ENTRY_VERSION,
        "requestId": str(request.get("requestId", "")),
        "route": route,
        "prediction": dict(prediction),
        "targetOrEvaluatorFieldsAccepted": False,
    }


def _decode_capture(value: Any, *, required: bool) -> bytes | None:
    if value is None:
        if required:
            raise ValueError("front_pixels_required")
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("capture_base64_invalid")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("capture_base64_invalid") from exc
    if not decoded:
        raise ValueError("capture_bytes_empty")
    return decoded


def _rejection(reason: str, *, abstained: bool = False) -> dict[str, Any]:
    return {
        "status": "abstained" if abstained else "rejected",
        "reason": reason,
        "parameters": None,
        "targetParametersRead": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    model = load_model(root / arguments.model)
    try:
        raw_request = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(canonical_dumps(_rejection(f"request_json_invalid:{type(exc).__name__}")))
        return 2
    if not isinstance(raw_request, Mapping):
        print(canonical_dumps(_rejection("request_mapping_required")))
        return 2
    response = execute_container_request(raw_request, model)
    print(canonical_dumps(response))
    return 0 if response["prediction"].get("status") in {"predicted", "abstained"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
