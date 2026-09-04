from __future__ import annotations

import csv
from io import StringIO
from math import isfinite
from pathlib import Path
from typing import Any

from .common import canonical_digest, write_json

HEADER = (
    "coupon_id",
    "specimen_family",
    "length_m",
    "width_m",
    "thickness_m",
    "time_s",
    "force_n",
    "displacement_m",
    "mass_kg",
)
FAMILIES = {
    "warp_extension",
    "weft_extension",
    "bias_shear",
    "cantilever_bend",
    "free_decay",
    "inclined_friction",
    "impact_rebound",
}


class CouponParseError(ValueError):
    pass


def parse_real_coupon_csv(payload: bytes, *, maximum_rows: int = 10000) -> dict[str, Any]:
    if len(payload) > 8 * 1024 * 1024:
        raise CouponParseError("coupon_file_too_large")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CouponParseError("coupon_encoding_invalid") from error
    if "\x00" in text:
        raise CouponParseError("coupon_nul_forbidden")
    reader = csv.DictReader(StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != HEADER:
        raise CouponParseError("coupon_header_or_units_invalid")
    rows: list[dict[str, Any]] = []
    identities: set[str] = set()
    for ordinal, row in enumerate(reader):
        if ordinal >= maximum_rows:
            raise CouponParseError("coupon_row_limit_exceeded")
        identity = str(row["coupon_id"])
        family = str(row["specimen_family"])
        if not identity or identity in identities:
            raise CouponParseError("coupon_identity_invalid")
        if family not in FAMILIES:
            raise CouponParseError("coupon_family_invalid")
        identities.add(identity)
        numeric = {}
        for field in HEADER[2:]:
            try:
                value = float(str(row[field]))
            except (TypeError, ValueError) as error:
                raise CouponParseError("coupon_numeric_invalid") from error
            if not isfinite(value):
                raise CouponParseError("coupon_non_finite")
            numeric[field] = value
        if any(
            numeric[field] <= 0.0
            for field in ("length_m", "width_m", "thickness_m", "time_s", "mass_kg")
        ):
            raise CouponParseError("coupon_positive_quantity_invalid")
        rows.append(
            {
                "couponId": identity,
                "specimenFamily": family,
                "measurementsSI": numeric,
                "sourceOrdinal": ordinal,
            }
        )
    document: dict[str, Any] = {
        "schemaVersion": 2,
        "parserVersion": "closy.real_coupon_si_csv.v2",
        "unitContract": {
            "length": "m",
            "time": "s",
            "force": "N",
            "mass": "kg",
        },
        "realCouponCount": len(rows),
        "rows": rows,
        "calibrationState": "not_run" if not rows else "measurements_ingested_not_calibrated",
    }
    document["documentDigest"] = canonical_digest(document)
    return document


def ingest_real_coupon_file(source: Path, output: Path) -> dict[str, Any]:
    document = parse_real_coupon_csv(source.read_bytes())
    write_json(output, document)
    return document


def empty_real_coupon_report() -> dict[str, Any]:
    header = ",".join(HEADER) + "\n"
    return parse_real_coupon_csv(header.encode("ascii"))
