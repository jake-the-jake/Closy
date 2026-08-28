from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .grammar_v2 import FAMILY_SPECS, compile_program, default_parameters, program_from_parameters
from .model_v2 import decode_prediction, deterministic_template_fallback, predict_v2

SESSION_VERSION = "closy.pattern_correction_session.d0.v1"
EDIT_BOUNDS = {
    "lengthScale": (0.90, 1.10),
    "widthScale": (0.93, 1.07),
    "easeNormalized": (-0.84, 0.84),
}


def start_correction_session(
    model: dict[str, Any], observation: dict[str, Any], *, session_id: str, seed: int
) -> dict[str, Any]:
    prediction = predict_v2(model, observation)
    if prediction["status"] == "predicted":
        program, pattern = decode_prediction(
            prediction,
            program_id=f"{session_id}.proposal",
            base_seed=seed,
        )
        proposal_reason = "learned_model_decoded_through_grammar"
        controls = deepcopy(prediction["continuousParameters"])
    else:
        program, pattern, proposal_reason = deterministic_template_fallback(
            model,
            observation,
            program_id=f"{session_id}.proposal",
            base_seed=seed,
        )
        controls = {"lengthScale": 1.0, "widthScale": 1.0, "easeNormalized": 0.0}
    session: dict[str, Any] = {
        "schemaVersion": 1,
        "sessionVersion": SESSION_VERSION,
        "sessionId": session_id,
        "sourceKind": "project_authored_simulated_correction_fixture",
        "humanReviewStatus": "not_run",
        "containsPrivateData": False,
        "proposalReason": proposal_reason,
        "prediction": prediction,
        "editableHighLevelParameters": controls,
        "proposedProgram": program,
        "proposedPatternHash": sha256_bytes(canonical_dumps(pattern).encode("utf-8")),
        "correctionEvents": [],
        "activeProgram": program,
        "activePatternHash": sha256_bytes(canonical_dumps(pattern).encode("utf-8")),
        "deterministicRebuildVerified": False,
        "provenance": {
            "seed": seed,
            "modelHash": model["integrity"]["modelHash"],
            "automatedFixture": True,
            "humanAction": False,
        },
        "integrity": {"sessionHash": ""},
    }
    session["integrity"]["sessionHash"] = _session_hash(session)
    return session


def record_correction(
    session: dict[str, Any],
    *,
    field: str,
    value: float,
    accepted: bool,
    reason_code: str,
) -> dict[str, Any]:
    if field not in EDIT_BOUNDS:
        raise ValueError(f"correction_field_unsupported:{field}")
    minimum, maximum = EDIT_BOUNDS[field]
    if not minimum <= value <= maximum:
        raise ValueError(f"correction_value_out_of_bounds:{field}")
    result = deepcopy(session)
    event = {
        "eventId": f"{result['sessionId']}.event.{len(result['correctionEvents']):03d}",
        "field": field,
        "before": result["editableHighLevelParameters"][field],
        "proposed": value,
        "accepted": accepted,
        "reasonCode": reason_code,
        "source": "simulated_fixture",
        "humanAction": False,
    }
    result["correctionEvents"].append(event)
    if accepted:
        result["editableHighLevelParameters"][field] = value
        family = str(result["activeProgram"]["garmentFamily"])
        parameters = _parameters_from_controls(
            family,
            result["editableHighLevelParameters"],
        )
        program = program_from_parameters(
            family,
            parameters,
            program_id=f"{result['sessionId']}.revision.{len(result['correctionEvents']):03d}",
            base_seed=int(result["provenance"]["seed"]),
            corrections=deepcopy(result["correctionEvents"]),
        )
        first = compile_program(program)
        second = compile_program(program)
        first_hash = sha256_bytes(canonical_dumps(first).encode("utf-8"))
        second_hash = sha256_bytes(canonical_dumps(second).encode("utf-8"))
        result["activeProgram"] = program
        result["activePatternHash"] = first_hash
        result["deterministicRebuildVerified"] = first_hash == second_hash
    result["integrity"]["sessionHash"] = _session_hash(result)
    return result


def validate_correction_session(session: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if session.get("sessionVersion") != SESSION_VERSION:
        issues.append("correction_session_version_invalid")
    if (
        session.get("sourceKind") != "project_authored_simulated_correction_fixture"
        or session.get("humanReviewStatus") != "not_run"
        or session.get("provenance", {}).get("humanAction") is not False
    ):
        issues.append("correction_session_human_evidence_overclaim")
    for event in session.get("correctionEvents", []):
        field = event.get("field")
        if field not in EDIT_BOUNDS or event.get("humanAction") is not False:
            issues.append("correction_event_invalid")
    if session.get("integrity", {}).get("sessionHash") != _session_hash(session):
        issues.append("correction_session_hash_mismatch")
    return sorted(set(issues))


def _parameters_from_controls(family: str, controls: dict[str, float]) -> dict[str, float | int]:
    spec = FAMILY_SPECS[family]
    values = default_parameters(family)
    values[spec.length_field] = round(
        float(values[spec.length_field]) * float(controls["lengthScale"]), 9
    )
    values[spec.width_field] = round(
        float(values[spec.width_field]) * float(controls["widthScale"]), 9
    )
    values[spec.ease_field] = round(
        float(values[spec.ease_field]) + float(controls["easeNormalized"]) * 0.012, 9
    )
    return values


def _session_hash(session: dict[str, Any]) -> str:
    payload = deepcopy(session)
    payload.setdefault("integrity", {})["sessionHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
