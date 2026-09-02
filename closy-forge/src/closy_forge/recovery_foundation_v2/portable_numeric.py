from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any, Literal

Decision = Literal["pass", "fail"]


def encode_metric(
    metric_id: str,
    terms: Sequence[float],
    *,
    unit: str,
    integer_scale_per_unit: int,
    threshold: float,
    comparator: Literal["maximum", "minimum"],
) -> dict[str, Any]:
    if not terms or integer_scale_per_unit <= 0:
        raise ValueError("portable_metric_contract_invalid")
    if not all(math.isfinite(value) for value in (*terms, threshold)):
        raise ValueError("portable_metric_nonfinite")
    raw = [value.hex() for value in terms]
    with localcontext() as context:
        context.prec = 80
        scale = Decimal(integer_scale_per_unit)
        quantized = [
            int((Decimal.from_float(value) * scale).to_integral_value(rounding=ROUND_HALF_EVEN))
            for value in terms
        ]
        aggregate_integer = sum(quantized)
        aggregate = Decimal(aggregate_integer) / (scale * Decimal(len(quantized)))
        threshold_integer = int(
            (Decimal.from_float(threshold) * scale).to_integral_value(rounding=ROUND_HALF_EVEN)
        )
    maximum_error = Decimal(len(terms)) / (Decimal(2) * Decimal(integer_scale_per_unit))
    threshold_quantized = Decimal(threshold_integer) / Decimal(integer_scale_per_unit)
    ambiguity_distance = abs(aggregate - threshold_quantized)
    if ambiguity_distance <= maximum_error:
        decision: Decision = "fail"
        ambiguity = True
    elif comparator == "maximum":
        decision = "pass" if aggregate <= threshold_quantized else "fail"
        ambiguity = False
    else:
        decision = "pass" if aggregate >= threshold_quantized else "fail"
        ambiguity = False
    return {
        "metricId": metric_id,
        "unit": unit,
        "rawTermsBinary64Hex": raw,
        "rawTermOrder": list(range(len(raw))),
        "portablePolicy": {
            "method": "per_term_decimal_from_binary64_then_fixed_point_mean",
            "integerScalePerUnit": integer_scale_per_unit,
            "roundingMode": "ROUND_HALF_EVEN",
            "decimalPrecision": 80,
            "maximumAggregationError": str(maximum_error),
        },
        "portableTermsInteger": quantized,
        "portableAggregateInteger": aggregate_integer,
        "portableMean": str(aggregate),
        "thresholdBinary64Hex": threshold.hex(),
        "thresholdQuantized": str(threshold_quantized),
        "comparator": comparator,
        "ambiguityBandEntered": ambiguity,
        "decision": decision,
    }


def derive_from_raw(document: Mapping[str, Any]) -> dict[str, Any]:
    policy = _mapping(document.get("portablePolicy"))
    raw = document.get("rawTermsBinary64Hex")
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError("portable_metric_raw_terms_invalid")
    terms = [float.fromhex(item) for item in raw]
    threshold_hex = document.get("thresholdBinary64Hex")
    if not isinstance(threshold_hex, str):
        raise ValueError("portable_metric_threshold_invalid")
    comparator = document.get("comparator")
    if comparator not in {"maximum", "minimum"}:
        raise ValueError("portable_metric_comparator_invalid")
    scale = policy.get("integerScalePerUnit")
    if not isinstance(scale, int) or isinstance(scale, bool):
        raise ValueError("portable_metric_scale_invalid")
    return encode_metric(
        str(document.get("metricId", "")),
        terms,
        unit=str(document.get("unit", "")),
        integer_scale_per_unit=scale,
        threshold=float.fromhex(threshold_hex),
        comparator=comparator,
    )


def validate_metric(document: Mapping[str, Any]) -> list[str]:
    try:
        regenerated = derive_from_raw(document)
    except ValueError as error:
        return [str(error)]
    fields = (
        "rawTermOrder",
        "portableTermsInteger",
        "portableAggregateInteger",
        "portableMean",
        "thresholdQuantized",
        "ambiguityBandEntered",
        "decision",
    )
    return [
        f"portable_metric_derivation_mismatch:{field}"
        for field in fields
        if regenerated[field] != document.get(field)
    ]


def boundary_fixtures() -> list[dict[str, Any]]:
    threshold = 0.01
    scale = 1_000_000_000
    return [
        encode_metric(
            f"boundary_{label}",
            [value],
            unit="meters",
            integer_scale_per_unit=scale,
            threshold=threshold,
            comparator="maximum",
        )
        for label, value in (
            ("below", threshold - 2e-9),
            ("at", threshold),
            ("above", threshold + 2e-9),
        )
    ]


def canonical_geometry_coordinate(value: float) -> dict[str, Any]:
    if not math.isfinite(value):
        raise ValueError("canonical_geometry_nonfinite")
    scale = 1_000_000_000
    with localcontext() as context:
        context.prec = 80
        integer = int(
            (Decimal.from_float(value) * Decimal(scale)).to_integral_value(
                rounding=ROUND_HALF_EVEN
            )
        )
    return {
        "integerNanometers": integer,
        "meters": format(Decimal(integer) / Decimal(scale), "f"),
        "maximumGeometricErrorMeters": "0.0000000005",
        "roundingMode": "ROUND_HALF_EVEN",
    }


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
