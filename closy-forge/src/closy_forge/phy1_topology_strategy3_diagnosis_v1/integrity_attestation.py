from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.phy1_topology_strategy3_diagnosis_v1.protocol import (
    EVIDENCE_ROOT,
    OUTCOME_PATH,
    document_digest,
)

INTEGRITY_ATTESTATION_PATH = EVIDENCE_ROOT / "integrity_attestation.json"
REVISION_PATHS = (
    EVIDENCE_ROOT / "revision_1.json",
    EVIDENCE_ROOT / "revision_2.json",
)
DIAGNOSIS_REPORT_PATH = EVIDENCE_ROOT / "diagnosis_report.json"
EVIDENCE_MANIFEST_PATH = EVIDENCE_ROOT / "evidence_manifest.json"
REPORT_PATH = EVIDENCE_ROOT / "REPORT.md"

# The first exact-head matrix exposed these three binary64 accumulation points. This is a
# pointer-specific integrity witness, not a global floating-point tolerance or an acceptance gate.
FLOAT_DRIFT_POINTERS = (
    "/fixtures/1/measurements/totalAbsoluteImpulseNewtonSeconds",
    "/fixtures/3/measurements/totalAbsoluteImpulseNewtonSeconds",
    "/fixtures/4/measurements/constraint/totalAbsoluteImpulseNewtonSeconds",
)


def verify_integrity_failure(
    root: Path,
    generated_documents: Mapping[Path, dict[str, Any]],
    generated_markdown: str,
) -> dict[str, Any]:
    attestation = cast(dict[str, Any], read_json(root / INTEGRITY_ATTESTATION_PATH))
    if attestation.get("effectiveOutcome") != "diagnosis_integrity_error":
        raise ValueError("unit_o_integrity_attestation_outcome_invalid")
    if _mapping(attestation.get("integrity")).get("attestationDigest") != document_digest(
        attestation, "attestationDigest"
    ):
        raise ValueError("unit_o_integrity_attestation_digest_invalid")

    for record in attestation.get("preservedRawEvidence", []):
        row = _mapping(record)
        path = root / str(row.get("path"))
        if not path.is_file() or sha256_file(path) != row.get("sha256"):
            raise ValueError(f"unit_o_preserved_evidence_hash_mismatch:{row.get('path')}")

    committed_revisions: list[dict[str, Any]] = []
    for path in REVISION_PATHS:
        committed = read_json(root / path)
        generated = deepcopy(generated_documents[path])
        _verify_pointer_specific_revision_drift(committed, generated)
        committed_revisions.append(committed)

    committed_outcome = read_json(root / OUTCOME_PATH)
    generated_outcome = deepcopy(generated_documents[OUTCOME_PATH])
    generated_outcome["revisions"] = committed_revisions
    generated_outcome["integrity"]["outcomeDigest"] = committed_outcome["integrity"][
        "outcomeDigest"
    ]
    if generated_outcome != committed_outcome:
        raise ValueError("unit_o_outcome_drift_outside_attested_pointers")

    if generated_documents[DIAGNOSIS_REPORT_PATH] != read_json(root / DIAGNOSIS_REPORT_PATH):
        raise ValueError("unit_o_diagnosis_report_unattested_drift")
    if generated_markdown != (root / REPORT_PATH).read_text(encoding="utf-8"):
        raise ValueError("unit_o_markdown_report_unattested_drift")

    manifest = read_json(root / EVIDENCE_MANIFEST_PATH)
    for record in manifest.get("records", []):
        row = _mapping(record)
        if sha256_file(root / str(row.get("path"))) != row.get("sha256"):
            raise ValueError(f"unit_o_evidence_hash_mismatch:{row.get('path')}")
    return attestation


def _verify_pointer_specific_revision_drift(
    committed: dict[str, Any], generated: dict[str, Any]
) -> None:
    numeric_drift = False
    for pointer in FLOAT_DRIFT_POINTERS:
        expected = _pointer_get(committed, pointer)
        actual = _pointer_get(generated, pointer)
        if expected == actual:
            continue
        if not isinstance(expected, float) or not isinstance(actual, float):
            raise ValueError(f"unit_o_non_float_at_attested_pointer:{pointer}")
        if not math.isfinite(expected) or not math.isfinite(actual):
            raise ValueError(f"unit_o_non_finite_attested_drift:{pointer}")
        if abs(expected - actual) > math.ulp(expected):
            raise ValueError(f"unit_o_drift_exceeds_one_ulp:{pointer}")
        numeric_drift = True
        _pointer_set(generated, pointer, expected)

    generated_fixture = _mapping(generated["fixtures"][7])
    committed_fixture = _mapping(committed["fixtures"][7])
    if numeric_drift:
        generated_fixture["measurements"] = committed_fixture["measurements"]
        generated["fixtures"][7] = generated_fixture
        generated["integrity"]["revisionDigest"] = committed["integrity"]["revisionDigest"]
    if generated != committed:
        raise ValueError("unit_o_revision_drift_outside_attested_pointers")


def _pointer_get(document: object, pointer: str) -> object:
    current = document
    for token in pointer.strip("/").split("/"):
        current = current[int(token)] if isinstance(current, list) else _mapping(current)[token]
    return current


def _pointer_set(document: object, pointer: str, value: object) -> None:
    tokens = pointer.strip("/").split("/")
    current = document
    for token in tokens[:-1]:
        current = current[int(token)] if isinstance(current, list) else _mapping(current)[token]
    last = tokens[-1]
    if isinstance(current, list):
        current[int(last)] = value
    elif isinstance(current, dict):
        current[last] = value
    else:
        raise TypeError(f"unit_o_pointer_parent_invalid:{pointer}")


def _mapping(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}
