from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.phy1_topology_strategy3_diagnosis_v1.protocol import (
    EVIDENCE_ROOT,
    OUTCOME_PATH,
    document_digest,
)

INTEGRITY_ATTESTATION_PATH = EVIDENCE_ROOT / "integrity_attestation.json"
DIAGNOSIS_REPORT_PATH = EVIDENCE_ROOT / "diagnosis_report.json"
EVIDENCE_MANIFEST_PATH = EVIDENCE_ROOT / "evidence_manifest.json"
REPORT_PATH = EVIDENCE_ROOT / "REPORT.md"


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
        if row.get("hashMode", "raw_bytes") == "canonical_lf_text":
            actual_hash = _canonical_lf_sha256(path) if path.is_file() else None
        else:
            actual_hash = sha256_file(path) if path.is_file() else None
        if actual_hash != row.get("sha256"):
            raise ValueError(f"unit_o_preserved_evidence_hash_mismatch:{row.get('path')}")

    committed_outcome = read_json(root / OUTCOME_PATH)
    generated_outcome = generated_documents[OUTCOME_PATH]
    _verify_non_authoritative_regeneration_structure(committed_outcome, generated_outcome)

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


def _verify_non_authoritative_regeneration_structure(
    committed: dict[str, Any], generated: dict[str, Any]
) -> None:
    scalar_fields = (
        "outcomeClass",
        "revisionCount",
        "admittedStrategyClass",
        "candidateCreated",
        "candidateAttemptConsumed",
        "finalStrategyConsumed",
        "unitPEligible",
        "budgetsBefore",
        "budgetsAfter",
    )
    if any(generated.get(field) != committed.get(field) for field in scalar_fields):
        raise ValueError("unit_o_regeneration_structural_state_drift")
    generated_revisions = generated.get("revisions", [])
    committed_revisions = committed.get("revisions", [])
    if not isinstance(generated_revisions, list) or not isinstance(committed_revisions, list):
        raise ValueError("unit_o_regeneration_revision_shape_invalid")
    structural_fields = (
        "revision",
        "strategyClass",
        "fixtureCount",
        "fixturePassCount",
        "firstUnmetPredicate",
        "admitted",
        "candidateCreated",
    )
    if len(generated_revisions) != len(committed_revisions) or any(
        _mapping(actual).get(field) != _mapping(expected).get(field)
        for actual, expected in zip(generated_revisions, committed_revisions, strict=True)
        for field in structural_fields
    ):
        raise ValueError("unit_o_regeneration_revision_structure_drift")


def _mapping(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _canonical_lf_sha256(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return sha256_bytes(content)
