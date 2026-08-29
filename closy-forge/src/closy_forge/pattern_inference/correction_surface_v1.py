from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .grammar_v2 import compile_program, validate_program

CORRECTION_VERSION = "closy.forge_local_structured_correction.v1"
ALLOWED_FIELDS = {
    "garmentFamily",
    "maskCorrection",
    "landmarks",
    "panelDimensions",
    "openingPresence",
    "openingType",
    "seamPairing",
    "fitEase",
    "decision",
}


def start_correction_surface(program: dict[str, Any], *, session_id: str) -> dict[str, Any]:
    issues = validate_program(program)
    if issues:
        raise ValueError("correction_source_program_invalid:" + ";".join(issues))
    source_hash = _hash(program)
    return {
        "schemaVersion": 1,
        "correctionVersion": CORRECTION_VERSION,
        "sessionId": session_id,
        "sourceProgramHash": source_hash,
        "sourceProgram": deepcopy(program),
        "currentProgramHash": source_hash,
        "currentProgram": deepcopy(program),
        "operations": [],
        "undoneOperations": [],
        "networkEnabled": False,
        "portableRawImagePathPresent": False,
        "humanReviewStatus": "not_run",
    }


def apply_correction(
    session: dict[str, Any],
    *,
    expected_source_hash: str,
    field: str,
    value: Any,
    reason: str,
) -> dict[str, Any]:
    _validate_session(session)
    if expected_source_hash != session["sourceProgramHash"]:
        raise ValueError("stale_correction_source_hash")
    if field not in ALLOWED_FIELDS:
        raise ValueError("correction_field_not_allowed")
    if _contains_path(value):
        raise ValueError("portable_correction_must_not_contain_raw_path")
    updated = deepcopy(session)
    before_hash = str(updated["currentProgramHash"])
    program = deepcopy(updated["currentProgram"])
    _apply_program_edit(program, field, value)
    issues = validate_program(program)
    if issues:
        raise ValueError("correction_program_invalid:" + ";".join(issues))
    compile_program(program)
    after_hash = _hash(program)
    operation = {
        "index": len(updated["operations"]),
        "field": field,
        "value": deepcopy(value),
        "reason": reason,
        "beforeHash": before_hash,
        "afterHash": after_hash,
    }
    updated["operations"].append(operation)
    updated["undoneOperations"] = []
    updated["currentProgram"] = program
    updated["currentProgramHash"] = after_hash
    return updated


def undo_correction(session: dict[str, Any]) -> dict[str, Any]:
    _validate_session(session)
    if not session["operations"]:
        return deepcopy(session)
    updated = deepcopy(session)
    removed = updated["operations"].pop()
    updated["undoneOperations"].append(removed)
    replayed = replay_corrections(
        _source_program(session),
        updated["operations"],
        expected_source_hash=str(session["sourceProgramHash"]),
    )
    updated["currentProgram"] = replayed["program"]
    updated["currentProgramHash"] = replayed["programHash"]
    return updated


def replay_corrections(
    source_program: dict[str, Any],
    operations: list[dict[str, Any]],
    *,
    expected_source_hash: str,
) -> dict[str, Any]:
    if _hash(source_program) != expected_source_hash:
        raise ValueError("stale_correction_source_hash")
    program = deepcopy(source_program)
    previous_hash = expected_source_hash
    for index, operation in enumerate(operations):
        if int(operation.get("index", -1)) != index:
            raise ValueError("correction_operation_order_invalid")
        if operation.get("beforeHash") != previous_hash:
            raise ValueError("correction_operation_hash_chain_invalid")
        _apply_program_edit(program, str(operation["field"]), operation.get("value"))
        issues = validate_program(program)
        if issues:
            raise ValueError("correction_replay_program_invalid:" + ";".join(issues))
        compile_program(program)
        previous_hash = _hash(program)
        if operation.get("afterHash") != previous_hash:
            raise ValueError("correction_operation_result_hash_invalid")
    return {
        "program": program,
        "programHash": previous_hash,
        "operationCount": len(operations),
        "deterministic": True,
    }


def export_correction_record(session: dict[str, Any]) -> dict[str, Any]:
    _validate_session(session)
    return {
        "schemaVersion": 1,
        "correctionVersion": CORRECTION_VERSION,
        "sessionId": session["sessionId"],
        "sourceProgramHash": session["sourceProgramHash"],
        "resultProgramHash": session["currentProgramHash"],
        "operations": deepcopy(session["operations"]),
        "decision": next(
            (
                operation["value"]
                for operation in reversed(session["operations"])
                if operation["field"] == "decision"
            ),
            "defer",
        ),
        "networkUsed": False,
        "containsRawImagePath": False,
        "humanReviewStatus": "not_run",
        "automatedStateSerializationTested": True,
    }


def _apply_program_edit(program: dict[str, Any], field: str, value: Any) -> None:
    if field == "fitEase":
        if not isinstance(value, dict) or not value:
            raise ValueError("fit_ease_edit_invalid")
        for name, number in value.items():
            if name not in program["parameters"] or not isinstance(number, int | float):
                raise ValueError("fit_ease_parameter_invalid")
            program["parameters"][name] = number
            for measurement in program["measurements"]:
                if measurement["semanticId"] == name:
                    measurement["value"] = number
    elif field == "decision":
        if value not in {"accept", "defer", "reject"}:
            raise ValueError("correction_decision_invalid")
    elif field == "garmentFamily":
        if value != program["garmentFamily"]:
            raise ValueError("family_change_requires_new_proposal")
    else:
        # Non-program visual corrections remain provenance-only until a typed
        # compiler edit is registered; they never silently mutate geometry.
        if value is None:
            raise ValueError("correction_value_missing")


def _validate_session(session: dict[str, Any]) -> None:
    if session.get("correctionVersion") != CORRECTION_VERSION:
        raise ValueError("correction_session_version_invalid")
    if session.get("networkEnabled") is not False:
        raise ValueError("correction_network_must_be_disabled")
    if session.get("humanReviewStatus") != "not_run":
        raise ValueError("automated_surface_cannot_claim_human_review")


def _source_program(session: dict[str, Any]) -> dict[str, Any]:
    current = deepcopy(session["currentProgram"])
    operations = list(reversed(session["operations"]))
    if not operations:
        return cast(dict[str, Any], current)
    # All current executable edits are scalar parameter replacements. Recover
    # the source from the first operation's before-value by replaying from the
    # source snapshot persisted in each session.
    source = session.get("sourceProgram")
    if not isinstance(source, dict):
        raise ValueError("correction_source_snapshot_missing")
    return cast(dict[str, Any], deepcopy(source))


def _contains_path(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            "path" in str(key).lower() or _contains_path(child) for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_path(child) for child in value)
    if isinstance(value, str):
        return ":\\" in value or value.startswith(("/", "file://"))
    return False


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
