from __future__ import annotations

import re
from pathlib import Path

_WINDOWS_ABSOLUTE = re.compile(r"(?i)(?:^|[\s\"'`=:(])(?:[a-z]:[\\/]|\\\\[^\\\s]+[\\/])")
_POSIX_HOME = re.compile(r"(?:^|[\s\"'`=:(])/(?:home|Users|root)/[^\s\"'`/]+/")
_URI_CREDENTIALS = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@")
_COMMON_TOKEN = re.compile(
    r"(?i)(?:\bgh[pousr]_[A-Za-z0-9_]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|"
    r"\bsk-[A-Za-z0-9_-]{20,}|(?:api|access|auth)[_-]?token\s*[:=]\s*[\"']?"
    r"[A-Za-z0-9._-]{16,})"
)
_PRIVATE_CAPTURE_ID = re.compile(r"(?i)\b(?:private[-_ ]?(?:capture|registry))[-_:][A-Za-z0-9._-]+")
_UNEXPECTED_SOURCE = re.compile(
    r"(?i)\b(?:customer|participant|subject)[-_ ]?(?:name|email|id)\s*[:=]"
)


def scan_evidence_text(text: str) -> tuple[str, ...]:
    checks = {
        "windows_absolute_path": _WINDOWS_ABSOLUTE,
        "posix_home_path": _POSIX_HOME,
        "uri_credentials": _URI_CREDENTIALS,
        "common_token": _COMMON_TOKEN,
        "private_capture_identifier": _PRIVATE_CAPTURE_ID,
        "unexpected_source_identity": _UNEXPECTED_SOURCE,
    }
    return tuple(name for name, pattern in checks.items() if pattern.search(text))


def scan_evidence_files(paths: list[Path]) -> dict[str, tuple[str, ...]]:
    issues: dict[str, tuple[str, ...]] = {}
    for path in paths:
        found = scan_evidence_text(path.read_text(encoding="utf-8"))
        if found:
            issues[path.as_posix()] = found
    return issues
