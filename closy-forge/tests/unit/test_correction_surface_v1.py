from __future__ import annotations

import pytest

from closy_forge.pattern_inference.correction_surface_v1 import (
    apply_correction,
    export_correction_record,
    replay_corrections,
    start_correction_surface,
    undo_correction,
)
from closy_forge.pattern_inference.grammar_v2 import default_parameters, program_from_parameters


def _program() -> dict[str, object]:
    return program_from_parameters(
        "sleeveless_top",
        default_parameters("sleeveless_top"),
        program_id="correction.fixture",
        base_seed=1,
    )


def test_correction_surface_replays_hash_chain_and_exports_no_path() -> None:
    source = _program()
    session = start_correction_surface(source, session_id="surface.test")
    session = apply_correction(
        session,
        expected_source_hash=session["sourceProgramHash"],
        field="decision",
        value="defer",
        reason="automated_fixture",
    )
    exported = export_correction_record(session)
    replay = replay_corrections(
        source,
        session["operations"],
        expected_source_hash=session["sourceProgramHash"],
    )
    assert replay["programHash"] == session["currentProgramHash"]
    assert exported["containsRawImagePath"] is False
    assert exported["humanReviewStatus"] == "not_run"
    assert exported["networkUsed"] is False


def test_correction_surface_rejects_stale_source_and_raw_path() -> None:
    session = start_correction_surface(_program(), session_id="surface.stale")
    with pytest.raises(ValueError, match="stale_correction_source_hash"):
        apply_correction(
            session,
            expected_source_hash="0" * 64,
            field="decision",
            value="reject",
            reason="stale",
        )
    with pytest.raises(ValueError, match="raw_path"):
        apply_correction(
            session,
            expected_source_hash=session["sourceProgramHash"],
            field="landmarks",
            value={"rawPath": "C:\\private\\capture.png"},
            reason="path_leak",
        )


def test_correction_surface_undo_restores_previous_hash() -> None:
    source = _program()
    session = start_correction_surface(source, session_id="surface.undo")
    source_hash = session["sourceProgramHash"]
    session = apply_correction(
        session,
        expected_source_hash=source_hash,
        field="decision",
        value="accept",
        reason="automated_fixture",
    )
    undone = undo_correction(session)
    assert undone["currentProgramHash"] == source_hash
    assert undone["operations"] == []
