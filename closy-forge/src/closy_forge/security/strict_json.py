from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

MAX_JSON_BYTES = 1_048_576
MAX_JSON_DEPTH = 32
MAX_JSON_ITEMS = 20_000


class StrictJsonError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def load_strict_json_object(
    path: Path,
    *,
    maximum_bytes: int = MAX_JSON_BYTES,
    maximum_depth: int = MAX_JSON_DEPTH,
    maximum_items: int = MAX_JSON_ITEMS,
    expected_fields: Iterable[str] | None = None,
) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise StrictJsonError("json_unreadable") from error
    if len(raw) > maximum_bytes:
        raise StrictJsonError("json_too_large")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise StrictJsonError("json_invalid_unicode") from error
    return loads_strict_json_object(
        text,
        maximum_bytes=maximum_bytes,
        maximum_depth=maximum_depth,
        maximum_items=maximum_items,
        expected_fields=expected_fields,
    )


def loads_strict_json_object(
    text: str,
    *,
    maximum_bytes: int = MAX_JSON_BYTES,
    maximum_depth: int = MAX_JSON_DEPTH,
    maximum_items: int = MAX_JSON_ITEMS,
    expected_fields: Iterable[str] | None = None,
) -> dict[str, Any]:
    if len(text.encode("utf-8")) > maximum_bytes:
        raise StrictJsonError("json_too_large")
    try:
        value = json.loads(
            text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_nonfinite
        )
    except json.JSONDecodeError as error:
        raise StrictJsonError("json_invalid") from error
    if not isinstance(value, dict):
        raise StrictJsonError("json_root_not_object")
    _validate_shape(value, maximum_depth=maximum_depth, maximum_items=maximum_items)
    if expected_fields is not None and set(value) != set(expected_fields):
        raise StrictJsonError("json_unexpected_fields")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError("json_duplicate_key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise StrictJsonError(f"json_nonfinite_number:{value}")


def _validate_shape(value: Any, *, maximum_depth: int, maximum_items: int) -> None:
    pending: list[tuple[Any, int]] = [(value, 1)]
    item_count = 0
    while pending:
        current, depth = pending.pop()
        if depth > maximum_depth:
            raise StrictJsonError("json_depth_exceeded")
        item_count += 1
        if item_count > maximum_items:
            raise StrictJsonError("json_item_count_exceeded")
        if isinstance(current, dict):
            for key, child in current.items():
                _reject_surrogates(key)
                pending.append((child, depth + 1))
        elif isinstance(current, list):
            pending.extend((child, depth + 1) for child in current)
        elif isinstance(current, str):
            _reject_surrogates(current)


def _reject_surrogates(value: str) -> None:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise StrictJsonError("json_invalid_unicode")
