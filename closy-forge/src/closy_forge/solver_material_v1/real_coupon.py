from __future__ import annotations

import csv
import json
from io import StringIO
from math import isfinite
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = (
    "record_id",
    "partition_key",
    "protocol_version",
    "raw_or_processed",
    "specimen_length_m",
    "specimen_width_m",
    "specimen_thickness_m",
    "orientation",
    "warp_direction_degrees",
    "weft_direction_degrees",
    "force_n",
    "displacement_m",
    "time_s",
    "stress_pa",
    "strain_ratio",
    "areal_density_kg_m2",
    "bending_protocol",
    "bending_observable_si",
    "damping_amplitude_m",
    "friction_method",
    "temperature_c",
    "relative_humidity_ratio",
    "equipment_id",
    "calibration_id",
    "repetition_id",
    "measurement_uncertainty_si",
    "sample_status",
    "censor_reason",
    "provenance_uri",
    "license_id",
    "consent_id",
    "retention_class",
    "deletion_class",
)
NUMERIC_COLUMNS = {
    "specimen_length_m",
    "specimen_width_m",
    "specimen_thickness_m",
    "warp_direction_degrees",
    "weft_direction_degrees",
    "force_n",
    "displacement_m",
    "time_s",
    "stress_pa",
    "strain_ratio",
    "areal_density_kg_m2",
    "bending_observable_si",
    "damping_amplitude_m",
    "temperature_c",
    "relative_humidity_ratio",
    "measurement_uncertainty_si",
}


class CouponValidationError(ValueError):
    pass


def parse_csv_bytes(payload: bytes) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CouponValidationError("coupon_csv_utf8_invalid") from error
    reader = csv.DictReader(StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != REQUIRED_COLUMNS:
        raise CouponValidationError("coupon_csv_header_invalid")
    return _validate_records([dict(row) for row in reader])


def parse_json_bytes(payload: bytes) -> list[dict[str, Any]]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CouponValidationError("coupon_json_decode_invalid") from error
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "records"}:
        raise CouponValidationError("coupon_json_root_invalid")
    if value["schemaVersion"] != 1 or not isinstance(value["records"], list):
        raise CouponValidationError("coupon_json_schema_invalid")
    return _validate_records(value["records"])


def import_coupon(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    records = (
        parse_csv_bytes(path.read_bytes())
        if suffix == ".csv"
        else parse_json_bytes(path.read_bytes())
    )
    return {
        "schemaVersion": 1,
        "sourceFormat": suffix.removeprefix("."),
        "recordCount": len(records),
        "realMeasurementsInvented": False,
        "records": records,
    }


def _validate_records(records: list[Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in records:
        if not isinstance(value, dict) or set(value) != set(REQUIRED_COLUMNS):
            raise CouponValidationError("coupon_record_fields_invalid")
        record = {str(key): item for key, item in value.items()}
        record_id = str(record["record_id"])
        if not record_id or record_id in seen:
            raise CouponValidationError("coupon_record_id_invalid")
        seen.add(record_id)
        if record["sample_status"] not in {"valid", "missing", "censored", "invalid"}:
            raise CouponValidationError("coupon_sample_status_invalid")
        if record["raw_or_processed"] not in {"raw", "processed"}:
            raise CouponValidationError("coupon_processing_class_invalid")
        for field in NUMERIC_COLUMNS:
            raw = record[field]
            if raw in (None, "") and record["sample_status"] in {"missing", "censored"}:
                continue
            try:
                number = float(raw)
            except (TypeError, ValueError) as error:
                raise CouponValidationError(f"coupon_numeric_invalid:{field}") from error
            if not isfinite(number):
                raise CouponValidationError(f"coupon_numeric_non_finite:{field}")
            record[field] = number
        if (
            record["relative_humidity_ratio"] not in (None, "")
            and not 0.0 <= float(record["relative_humidity_ratio"]) <= 1.0
        ):
            raise CouponValidationError("coupon_humidity_range_invalid")
        if any(
            Path(str(record[field])).is_absolute()
            for field in ("provenance_uri", "equipment_id", "calibration_id")
        ):
            raise CouponValidationError("coupon_absolute_local_path_forbidden")
        output.append(record)
    return output
