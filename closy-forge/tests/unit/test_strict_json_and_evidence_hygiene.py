from __future__ import annotations

from pathlib import Path

import pytest

from closy_forge.security.evidence_hygiene import scan_evidence_text
from closy_forge.security.strict_json import StrictJsonError, load_strict_json_object


@pytest.mark.parametrize(
    ("payload", "code"),
    (
        (b'{"a":1,"a":2}', "json_duplicate_key"),
        (b'{"value":NaN}', "json_nonfinite_number"),
        (b'{"value":Infinity}', "json_nonfinite_number"),
        (b'{"value":"\\ud800"}', "json_invalid_unicode"),
    ),
)
def test_strict_json_rejects_ambiguous_values(tmp_path: Path, payload: bytes, code: str) -> None:
    path = tmp_path / "record.json"
    path.write_bytes(payload)

    with pytest.raises(StrictJsonError, match=code):
        load_strict_json_object(path)


def test_strict_json_enforces_bytes_depth_items_and_closed_fields(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    path.write_text('{"outer":{"inner":1},"extra":2}', encoding="utf-8")

    with pytest.raises(StrictJsonError, match="json_too_large"):
        load_strict_json_object(path, maximum_bytes=2)
    with pytest.raises(StrictJsonError, match="json_depth_exceeded"):
        load_strict_json_object(path, maximum_depth=2)
    with pytest.raises(StrictJsonError, match="json_item_count_exceeded"):
        load_strict_json_object(path, maximum_items=2)
    with pytest.raises(StrictJsonError, match="json_unexpected_fields"):
        load_strict_json_object(path, expected_fields={"outer"})


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        (r'command="C:\\Users\\person\\work\\tool.exe"', "windows_absolute_path"),
        ("source=/home/person/private/image.png", "posix_home_path"),
        ("https://user:password@example.invalid/a", "uri_credentials"),
        ("token=ghp_012345678901234567890123456789", "common_token"),
        ("private-capture:registry-subject-9", "private_capture_identifier"),
        ("participant_email=person@example.invalid", "unexpected_source_identity"),
    ),
)
def test_evidence_hygiene_detects_sensitive_context(text: str, expected: str) -> None:
    assert expected in scan_evidence_text(text)


def test_evidence_hygiene_accepts_repository_relative_fixture_records() -> None:
    safe = (
        "closy-forge/docs/evidence/report.json ",
        "fixture://project-authored/tshirt ",
        "python scripts/generate_report.py --output <managed-output>",
    )

    assert scan_evidence_text("".join(safe)) == ()
