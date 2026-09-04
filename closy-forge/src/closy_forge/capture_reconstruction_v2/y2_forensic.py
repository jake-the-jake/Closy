from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .common import canonical_digest

AUTHORITY_ID = "CLOSY-S3-Y2-TRANSPORT-V4-20260903-AUTH1"


def derive_y2_terminal_state(repository: Path) -> dict[str, Any]:
    refs = _git(repository, "for-each-ref", "--format=%(refname)").decode().splitlines()
    forbidden = [ref for ref in refs if AUTHORITY_ID.casefold() in ref.casefold()]
    audit_path = (
        repository
        / "closy-forge/docs/evidence/truth_dependency_authority_v4/y2_protocol_audit.json"
    )
    ledger_path = (
        repository / "closy-forge/docs/evidence/truth_dependency_authority_v4/truth_ledger.json"
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger_y2 = ledger.get("unitY2", {})
    findings = audit.get("findings", [])
    incomplete_markers = (
        audit.get("terminalOutcome") == "preseed_scientific_protocol_invalid"
        and audit.get("scientificProtocolValidForY2") is False
        and audit.get("seedCreated") is False
        and audit.get("scientificAttemptConsumed") is False
        and audit.get("candidateCreated") is False
        and len(findings) >= 4
        and all(bool(row.get("scientificPolicyMissing")) for row in findings)
        and ledger_y2.get("auditDigest") == audit.get("auditDigest")
        and ledger_y2.get("terminalOutcome") == audit.get("terminalOutcome")
    )
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "verifierVersion": "closy.y2_frozen_git_forensic.v1",
        "authorityIdentity": AUTHORITY_ID,
        "terminalOutcome": (
            "preseed_scientific_protocol_invalid"
            if incomplete_markers and not forbidden
            else "integrity_error"
        ),
        "matchingAuthorityRefs": sorted(forbidden),
        "authorityTagExists": False,
        "seedExists": False,
        "scientificAttemptConsumed": False,
        "candidateConsumed": False,
        "topologyStrategyConsumed": False,
        "newAttemptArmed": False,
        "sourceBlobsReopened": [
            "y2_protocol_audit.json",
            "truth_ledger.json",
            "repository_refs",
        ],
    }
    result["forensicDigest"] = canonical_digest(result)
    return result


def _git(repository: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=repository)
