from __future__ import annotations

from typing import Any


def strip_truth_for_estimator(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose observation and public load metadata without authored tuple descriptors."""

    return [
        {
            "family": coupon["family"],
            "load": coupon["load"],
            "observable": coupon["observable"],
            "normalizationFloor": 0.0001,
        }
        for coupon in row["coupons"]
    ]
