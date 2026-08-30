from __future__ import annotations

from copy import deepcopy

import pytest

from closy_forge.pattern_inference.correction_surface_v2 import (
    apply_typed_correction_v2,
    export_typed_correction_v2,
    start_typed_correction_v2,
)
from closy_forge.pattern_inference.typed_program_v2 import (
    CONTINUOUS_AXES,
    GRAMMAR_VERSION,
    PROGRAM_VERSION,
    TOKEN_AXES,
)


def _proposal() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "programVersion": PROGRAM_VERSION,
        "grammarVersion": GRAMMAR_VERSION,
        "programId": "correction.source",
        "tokens": dict(
            zip(
                TOKEN_AXES,
                (
                    "upper",
                    "two_panel",
                    "none",
                    "short",
                    "crew",
                    "shaped",
                    "straight",
                    "none",
                    "base",
                    "jersey",
                ),
                strict=True,
            )
        ),
        "parameters": dict(zip(CONTINUOUS_AXES, (0.5, 0.5, 0.5, 0.5, 0.5), strict=True)),
        "materialRegion": "material.jersey",
    }


def test_typed_correction_creates_a_new_validated_proposal_without_mutating_source() -> None:
    source = _proposal()
    original = deepcopy(source)
    session = start_typed_correction_v2(source, session_id="correction.synthetic.001")
    corrected = apply_typed_correction_v2(
        session,
        expected_proposal_hash=session["currentProposalHash"],
        section="parameters",
        field="length",
        value=0.62,
        reason="synthetic_scripted_compile_fixture_not_human_review",
    )
    record = export_typed_correction_v2(corrected)

    assert source == original
    assert record["sourceProposalUnchanged"] is True
    assert record["proposalVersionCreated"] is True
    assert record["canonicalPackageMutated"] is False
    assert record["humanReviewClaimed"] is False
    assert record["lastValidationIssues"] == []
    assert record["lastCompileAudit"]["topologyValid"] is True
    assert record["edits"][0]["beforeProposalHash"] != record["edits"][0]["afterProposalHash"]


def test_typed_correction_rejects_stale_or_illegal_edits() -> None:
    session = start_typed_correction_v2(_proposal(), session_id="correction.synthetic.002")

    with pytest.raises(ValueError, match="stale_proposal_hash"):
        apply_typed_correction_v2(
            session,
            expected_proposal_hash="0" * 64,
            section="parameters",
            field="length",
            value=0.6,
            reason="stale",
        )
    with pytest.raises(ValueError, match="section_invalid"):
        apply_typed_correction_v2(
            session,
            expected_proposal_hash=session["currentProposalHash"],
            section="canonicalPackage",
            field="length",
            value=0.6,
            reason="forbidden",
        )
