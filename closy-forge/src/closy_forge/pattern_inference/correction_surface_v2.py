from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .typed_program_v2 import compile_typed_program_v2, validate_typed_program_v2

CORRECTION_VERSION = "closy.typed_program_correction_surface.forge_local.v2"


def start_typed_correction_v2(proposal: dict[str, Any], *, session_id: str) -> dict[str, Any]:
    source = deepcopy(proposal)
    source_hash = _hash(source)
    return {
        "schemaVersion": 1,
        "correctionVersion": CORRECTION_VERSION,
        "sessionId": session_id,
        "sourceProposal": source,
        "sourceProposalHash": source_hash,
        "currentProposal": deepcopy(source),
        "currentProposalHash": source_hash,
        "edits": [],
        "provenance": {
            "actor": "synthetic_script",
            "actualHumanInteraction": False,
            "productUi": False,
            "developerToolOnly": True,
        },
        "canonicalPackageMutated": False,
    }


def apply_typed_correction_v2(
    session: dict[str, Any],
    *,
    expected_proposal_hash: str,
    section: str,
    field: str,
    value: Any,
    reason: str,
) -> dict[str, Any]:
    if section not in {"tokens", "parameters"}:
        raise ValueError("typed_correction_section_invalid")
    if expected_proposal_hash != session.get("currentProposalHash"):
        raise ValueError("typed_correction_stale_proposal_hash")
    result = deepcopy(session)
    before = deepcopy(result["currentProposal"])
    if field not in before.get(section, {}):
        raise ValueError("typed_correction_field_invalid")
    after = deepcopy(before)
    after[section][field] = value
    issues = validate_typed_program_v2(after)
    compile_audit: dict[str, Any] | None = None
    if not issues:
        compilation = compile_typed_program_v2(after)
        compile_audit = {
            "topologyValid": compilation["audit"]["topologyValid"],
            "panelCount": compilation["audit"]["panelCount"],
            "topologyHash": compilation["audit"]["topologyHash"],
            "contentHash": compilation["audit"]["contentHash"],
        }
    after_hash = _hash(after)
    result["edits"].append(
        {
            "section": section,
            "field": field,
            "beforeValue": before[section][field],
            "afterValue": value,
            "reason": reason,
            "beforeProposalHash": result["currentProposalHash"],
            "afterProposalHash": after_hash,
            "validationIssues": issues,
            "compileAudit": compile_audit,
            "actualHumanInteraction": False,
        }
    )
    result["currentProposal"] = after
    result["currentProposalHash"] = after_hash
    result["lastValidationIssues"] = issues
    result["lastCompileAudit"] = compile_audit
    return result


def export_typed_correction_v2(session: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(session)
    result["sourceProposalUnchanged"] = (
        _hash(result["sourceProposal"]) == result["sourceProposalHash"]
    )
    result["proposalVersionCreated"] = result["currentProposalHash"] != result["sourceProposalHash"]
    result["canonicalPackageMutated"] = False
    result["humanReviewClaimed"] = False
    result["recordHash"] = ""
    result["recordHash"] = _hash(result)
    return result


def _hash(value: dict[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
