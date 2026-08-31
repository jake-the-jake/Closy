from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.package_io.paths import validate_package_relpath

MATRIX_V3_EVALUATOR_VERSION = "closy.d0_research_matrix.predicate_evaluator.v3"
ATTEMPT_REGISTRY_VERSION = "closy.d0_research_matrix.attempt_registry.v3"
AttemptState = Literal[
    "never_attempted",
    "attempted_pass",
    "attempted_fail",
    "attempted_integrity_error",
    "dependency_blocked",
]
ResultStatus = Literal["pass", "fail", "not_run"]

_ATTEMPT_STATES = {
    "never_attempted",
    "attempted_pass",
    "attempted_fail",
    "attempted_integrity_error",
    "dependency_blocked",
}


class MatrixV3Error(ValueError):
    pass


def canonical_artifact_sha256(path: Path) -> str:
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    if b"\r" in normalized:
        raise MatrixV3Error("evidence_artifact_noncanonical_newline")
    return sha256_bytes(normalized)


def document_hash(value: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(dict(value)).encode())


def append_attempt(
    registry: dict[str, Any],
    *,
    attempt_id: str,
    lineage_id: str,
    row_id: str,
    scope: str,
    candidate_identity_hash: str,
    attempt_state: AttemptState,
    reason_code: str,
    evidence_ids: list[str],
    dependency_blocker: str | None = None,
    invalidates_attempt_id: str | None = None,
) -> dict[str, Any]:
    """Append an immutable hash-linked attempt record.

    The registry is intentionally append-only. Invalidating an attempt adds a
    tombstone record; callers never delete or replace the original history.
    """

    records = registry.setdefault("records", [])
    if not isinstance(records, list):
        raise MatrixV3Error("attempt_registry_records_invalid")
    sequence = len(records) + 1
    predecessor_hash = "0" * 64 if not records else str(records[-1]["recordHash"])
    lineage_records = [
        record
        for record in records
        if isinstance(record, dict) and record.get("lineageId") == lineage_id
    ]
    prior_status = "none" if not lineage_records else str(lineage_records[-1]["attemptState"])
    record: dict[str, Any] = {
        "sequence": sequence,
        "attemptId": attempt_id,
        "lineageId": lineage_id,
        "rowId": row_id,
        "scope": scope,
        "candidateIdentityHash": candidate_identity_hash,
        "attemptState": attempt_state,
        "priorStatus": prior_status,
        "currentStatus": attempt_state,
        "reasonCode": reason_code,
        "requiredEvidenceIds": list(evidence_ids),
        "dependencyBlocker": dependency_blocker,
        "invalidatesAttemptId": invalidates_attempt_id,
        "predecessorHash": predecessor_hash,
        "recordHash": "",
    }
    record["recordHash"] = document_hash({**record, "recordHash": ""})
    records.append(record)
    registry["headHash"] = record["recordHash"]
    registry["recordCount"] = len(records)
    return record


def validate_attempt_registry(registry: Mapping[str, Any]) -> None:
    if registry.get("registryVersion") != ATTEMPT_REGISTRY_VERSION:
        raise MatrixV3Error("attempt_registry_version_invalid")
    records = registry.get("records")
    if not isinstance(records, list) or not records:
        raise MatrixV3Error("attempt_registry_records_invalid")
    expected_predecessor = "0" * 64
    ids: set[str] = set()
    invalidated: set[str] = set()
    lineage_last: dict[str, str] = {}
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, dict):
            raise MatrixV3Error("attempt_registry_record_invalid")
        record = raw
        attempt_id = record.get("attemptId")
        lineage_id = record.get("lineageId")
        state = record.get("attemptState")
        if (
            record.get("sequence") != index
            or not isinstance(attempt_id, str)
            or attempt_id in ids
            or not isinstance(lineage_id, str)
            or state not in _ATTEMPT_STATES
            or record.get("predecessorHash") != expected_predecessor
            or record.get("currentStatus") != state
        ):
            raise MatrixV3Error("attempt_registry_record_invalid")
        expected_prior = lineage_last.get(lineage_id, "none")
        if record.get("priorStatus") != expected_prior:
            raise MatrixV3Error("attempt_registry_prior_status_invalid")
        blocker = record.get("dependencyBlocker")
        if state == "dependency_blocked" and not isinstance(blocker, str):
            raise MatrixV3Error("attempt_registry_dependency_blocker_missing")
        invalidates = record.get("invalidatesAttemptId")
        if invalidates is not None:
            if (
                not isinstance(invalidates, str)
                or invalidates not in ids
                or invalidates in invalidated
            ):
                raise MatrixV3Error("attempt_registry_tombstone_invalid")
            invalidated.add(invalidates)
        expected_hash = document_hash({**record, "recordHash": ""})
        if record.get("recordHash") != expected_hash:
            raise MatrixV3Error("attempt_registry_hash_chain_invalid")
        ids.add(attempt_id)
        expected_predecessor = expected_hash
        lineage_last[lineage_id] = str(state)
    if registry.get("headHash") != expected_predecessor:
        raise MatrixV3Error("attempt_registry_head_invalid")
    if registry.get("recordCount") != len(records):
        raise MatrixV3Error("attempt_registry_count_invalid")


def evaluate_research_matrix_v3(
    root: Path,
    *,
    profile: Mapping[str, Any],
    bindings: Mapping[str, Mapping[str, Any]],
    attempt_registry: Mapping[str, Any],
    selected_context: Mapping[str, Any],
    evidence_source_anchor_sha: str,
    externally_attested_head_sha: str,
) -> dict[str, Any]:
    _validate_profile(profile)
    validate_attempt_registry(attempt_registry)
    _validate_context(selected_context)
    if not _commit(evidence_source_anchor_sha) or not _commit(externally_attested_head_sha):
        raise MatrixV3Error("matrix_commit_authority_invalid")
    context_hash = document_hash(selected_context)
    records = attempt_registry["records"]
    rows = [
        _evaluate_row(root, definition, bindings, records, context_hash)
        for definition in profile["rows"]
    ]
    core = [row for row in rows if row["summaryClass"] == "core"]
    supplemental = [row for row in rows if row["summaryClass"] == "supplemental"]
    first_unmet = next(
        (
            row
            for row in core
            if row["requiredForResearchPrototype"] and row["resultStatus"] != "pass"
        ),
        None,
    )
    matrix: dict[str, Any] = {
        "schemaVersion": 3,
        "matrixVersion": "closy.final_d0_research_prototype_matrix.v3",
        "evaluatorVersion": MATRIX_V3_EVALUATOR_VERSION,
        "thresholdRegistryId": profile["registryId"],
        "thresholdRegistryHash": document_hash(profile),
        "scope": "exact_fixture_candidate",
        "selectedCandidateContext": dict(selected_context),
        "selectedCandidateContextHash": context_hash,
        "authority": {
            "evidenceSourceAnchorSha": evidence_source_anchor_sha,
            "externallyAttestedPublishedHeadSha": externally_attested_head_sha,
            "recursiveSelfReferenceAvoided": True,
        },
        "attemptRegistryHeadHash": attempt_registry["headHash"],
        "rows": rows,
        "summaries": {
            "core": _summary(core),
            "supplemental": _summary(supplemental),
        },
        "researchPrototypeStatus": "pass" if first_unmet is None else "partial",
        "firstUnmetRequiredPredicate": None
        if first_unmet is None
        else {
            "rowId": first_unmet["rowId"],
            "scope": first_unmet["scope"],
            "predicateId": first_unmet["firstUnmetPredicate"],
            "reasonCode": first_unmet["reasonCodes"][0],
        },
        "independentSupplementalStatus": _supplemental_status(supplemental),
        "scopedAuthorities": deepcopy(profile["scopedAuthorities"]),
        "claims": {
            "globalResearchPrototypePassed": first_unmet is None,
            "runtimeV1RemainsSelected": True,
            "physicalCandidateReran": False,
            "alphaReady": False,
            "humanEvidence": False,
            "privateUserEvidence": False,
            "deviceEvidence": False,
            "physicalClothEvidence": False,
        },
        "integrity": {"matrixHash": ""},
    }
    matrix["integrity"]["matrixHash"] = document_hash({**matrix, "integrity": {"matrixHash": ""}})
    return matrix


def _evaluate_row(
    root: Path,
    definition: Mapping[str, Any],
    bindings: Mapping[str, Mapping[str, Any]],
    attempts: list[dict[str, Any]],
    context_hash: str,
) -> dict[str, Any]:
    row_id = str(definition["rowId"])
    scope = str(definition["scope"])
    lineage = [
        attempt
        for attempt in attempts
        if attempt["rowId"] == row_id
        and attempt["scope"] == scope
        and attempt["candidateIdentityHash"] == context_hash
    ]
    if not lineage:
        raise MatrixV3Error(f"matrix_attempt_lineage_missing:{row_id}:{scope}")
    latest = lineage[-1]
    state = str(latest["attemptState"])
    required_ids = list(definition["requiredEvidenceIds"])
    opened: list[dict[str, Any]] = []
    integrity_errors: list[str] = []
    predicate_failures: list[str] = []
    if state != "never_attempted":
        for evidence_id in required_ids:
            binding = bindings.get(evidence_id)
            if binding is None:
                integrity_errors.append(f"required_evidence_binding_missing:{evidence_id}")
                opened.append(_missing_binding_record(evidence_id))
                continue
            record = _open_evidence(root, evidence_id, binding, context_hash)
            opened.append(record)
            integrity_errors.extend(record["integrityErrors"])
            predicate_failures.extend(
                result["reasonCode"]
                for result in record["predicateResults"]
                if result["passed"] is False
            )
    result, reasons = _map_result(state, latest, integrity_errors, predicate_failures)
    first_predicate = next(
        (
            result_record["predicateId"]
            for artifact in opened
            for result_record in artifact["predicateResults"]
            if result_record["passed"] is False
        ),
        None,
    )
    return {
        "rowId": row_id,
        "scope": scope,
        "requirement": definition["requirement"],
        "decisionGroup": definition["decisionGroup"],
        "summaryClass": definition["summaryClass"],
        "requiredForResearchPrototype": definition["requiredForResearchPrototype"],
        "thresholdRegistryRef": definition["thresholdRegistryRef"],
        "selectedCandidateContextHash": context_hash,
        "requiredEvidenceIds": required_ids,
        "attemptId": latest["attemptId"],
        "attemptState": state,
        "attemptHistory": [
            {
                "sequence": item["sequence"],
                "attemptId": item["attemptId"],
                "priorStatus": item["priorStatus"],
                "currentStatus": item["currentStatus"],
                "reasonCode": item["reasonCode"],
                "recordHash": item["recordHash"],
            }
            for item in lineage
        ],
        "currentDependencyBlocker": latest["dependencyBlocker"],
        "openedArtifactInventory": opened,
        "resultStatus": result,
        "reasonCodes": reasons,
        "firstUnmetPredicate": first_predicate,
    }


def _open_evidence(
    root: Path,
    evidence_id: str,
    binding: Mapping[str, Any],
    context_hash: str,
) -> dict[str, Any]:
    errors: list[str] = []
    relative = binding.get("path")
    classification = binding.get("classification")
    record: dict[str, Any] = {
        "evidenceId": evidence_id,
        "classification": classification,
        "path": relative,
        "openAttempted": True,
        "exists": False,
        "declaredArtifactSha256": binding.get("sha256"),
        "recomputedArtifactSha256": None,
        "recomputedPayloadHash": None,
        "selectedCandidateContextHash": context_hash,
        "predicateResults": [],
        "integrityErrors": errors,
    }
    if classification not in {"public_fixture", "portable_exported_authority"}:
        errors.append(f"portable_evidence_classification_invalid:{evidence_id}")
    if not isinstance(relative, str):
        errors.append(f"evidence_path_invalid:{evidence_id}")
        return record
    try:
        validate_package_relpath(relative)
    except ValueError:
        errors.append(f"evidence_path_invalid:{evidence_id}")
        return record
    path = root / relative
    if not path.is_file():
        errors.append(f"evidence_artifact_missing:{evidence_id}")
        return record
    record["exists"] = True
    actual_hash = canonical_artifact_sha256(path)
    record["recomputedArtifactSha256"] = actual_hash
    if binding.get("sha256") != actual_hash:
        errors.append(f"evidence_artifact_hash_mismatch:{evidence_id}")
    try:
        value = read_json(path)
    except (OSError, ValueError):
        errors.append(f"evidence_json_invalid:{evidence_id}")
        return record
    if not isinstance(value, dict):
        errors.append(f"evidence_object_required:{evidence_id}")
        return record
    record["recomputedPayloadHash"] = document_hash(value)
    predicates = binding.get("predicates")
    if not isinstance(predicates, list) or not predicates:
        errors.append(f"evidence_predicates_missing:{evidence_id}")
        return record
    record["predicateResults"] = [
        _evaluate_predicate(evidence_id, value, predicate, context_hash) for predicate in predicates
    ]
    return record


def _evaluate_predicate(
    evidence_id: str,
    value: Mapping[str, Any],
    raw_predicate: Any,
    context_hash: str,
) -> dict[str, Any]:
    if not isinstance(raw_predicate, dict):
        return _predicate_error("invalid", None, None, "evidence_predicate_invalid")
    predicate = raw_predicate
    predicate_id = str(predicate.get("predicateId", "invalid"))
    pointer = predicate.get("pointer")
    operation = predicate.get("operation")
    expected = predicate.get("expected")
    if not isinstance(pointer, str) or not isinstance(operation, str):
        return _predicate_error(predicate_id, None, expected, "evidence_predicate_invalid")
    try:
        observed = _resolve_pointer(value, pointer)
        if operation == "equals":
            passed = observed == expected
        elif operation == "not_equals":
            passed = observed != expected
        elif operation == "less_or_equal":
            passed = _number(observed) <= _number(expected)
        elif operation == "greater_or_equal":
            passed = _number(observed) >= _number(expected)
        elif operation == "sha256":
            passed = _is_sha256(observed)
        elif operation == "context_hash_equals":
            expected = context_hash
            passed = observed == context_hash
        elif operation == "identity_equals":
            identity_pointer = predicate.get("identityPointer")
            if not isinstance(identity_pointer, str):
                raise MatrixV3Error("identity_predicate_pointer_invalid")
            expected = _resolve_pointer(value, identity_pointer)
            passed = observed == expected
        elif operation == "contains":
            passed = isinstance(observed, list | str) and expected in observed
        else:
            raise MatrixV3Error(f"evidence_predicate_operation_unknown:{operation}")
    except (MatrixV3Error, TypeError, ValueError) as error:
        return _predicate_error(predicate_id, None, expected, str(error))
    reason = (
        "predicate_passed" if passed else f"evidence_predicate_failed:{evidence_id}:{predicate_id}"
    )
    return {
        "predicateId": predicate_id,
        "pointer": pointer,
        "operation": operation,
        "expected": expected,
        "observed": observed,
        "passed": passed,
        "reasonCode": reason,
    }


def _predicate_error(
    predicate_id: str, observed: Any, expected: Any, reason: str
) -> dict[str, Any]:
    return {
        "predicateId": predicate_id,
        "pointer": None,
        "operation": "invalid",
        "expected": expected,
        "observed": observed,
        "passed": False,
        "reasonCode": reason,
    }


def _map_result(
    state: str,
    attempt: Mapping[str, Any],
    integrity_errors: list[str],
    predicate_failures: list[str],
) -> tuple[ResultStatus, list[str]]:
    if state == "never_attempted":
        return "not_run", [str(attempt["reasonCode"])]
    if integrity_errors:
        return "fail", integrity_errors + predicate_failures
    if state == "attempted_integrity_error":
        return "fail", [str(attempt["reasonCode"])] + predicate_failures
    if state == "attempted_fail":
        return "fail", [str(attempt["reasonCode"])] + predicate_failures
    if state == "dependency_blocked":
        prior = str(attempt["priorStatus"])
        if prior in {"attempted_fail", "attempted_integrity_error", "dependency_blocked"}:
            return "fail", [str(attempt["reasonCode"]), str(attempt["dependencyBlocker"])]
        return "not_run", [str(attempt["reasonCode"]), str(attempt["dependencyBlocker"])]
    if predicate_failures:
        return "fail", ["attempted_pass_current_predicate_invalid"] + predicate_failures
    return "pass", ["all_current_predicates_and_identities_valid"]


def _missing_binding_record(evidence_id: str) -> dict[str, Any]:
    return {
        "evidenceId": evidence_id,
        "classification": None,
        "path": None,
        "openAttempted": True,
        "exists": False,
        "declaredArtifactSha256": None,
        "recomputedArtifactSha256": None,
        "recomputedPayloadHash": None,
        "selectedCandidateContextHash": None,
        "predicateResults": [],
        "integrityErrors": [f"required_evidence_binding_missing:{evidence_id}"],
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        status: sum(row["resultStatus"] == status for row in rows)
        for status in ("pass", "fail", "not_run")
    }
    return {"rowCount": len(rows), "statusCounts": counts, "rowIds": [row["rowId"] for row in rows]}


def _supplemental_status(rows: list[dict[str, Any]]) -> str:
    if any(row["resultStatus"] == "fail" for row in rows):
        return "partial_with_failures"
    if any(row["resultStatus"] == "not_run" for row in rows):
        return "partial_not_run"
    return "pass"


def _validate_profile(profile: Mapping[str, Any]) -> None:
    rows = profile.get("rows")
    if (
        profile.get("schemaVersion") != 3
        or not isinstance(profile.get("registryId"), str)
        or not isinstance(rows, list)
        or not rows
        or not isinstance(profile.get("scopedAuthorities"), list)
    ):
        raise MatrixV3Error("matrix_v3_profile_invalid")
    required = {
        "rowId",
        "scope",
        "requirement",
        "decisionGroup",
        "summaryClass",
        "requiredForResearchPrototype",
        "thresholdRegistryRef",
        "requiredEvidenceIds",
    }
    keys: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != required:
            raise MatrixV3Error("matrix_v3_profile_row_invalid")
        key = (str(row["rowId"]), str(row["scope"]))
        if key in keys or row["summaryClass"] not in {"core", "supplemental"}:
            raise MatrixV3Error("matrix_v3_profile_row_invalid")
        keys.add(key)


def _validate_context(context: Mapping[str, Any]) -> None:
    required = {
        "candidateId",
        "packageDigest",
        "avatarContractHash",
        "garmentId",
        "patternHash",
        "simulationTopologyHash",
        "renderTopologyHash",
        "bindingHash",
    }
    if set(context) != required or not str(context.get("garmentId", "")).startswith("garment."):
        raise MatrixV3Error("matrix_selected_context_invalid")
    for key in required - {"candidateId", "garmentId"}:
        if not _is_sha256(context[key]):
            raise MatrixV3Error(f"matrix_selected_context_invalid:{key}")


def _resolve_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise MatrixV3Error("evidence_pointer_invalid")
    current = value
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise MatrixV3Error(f"evidence_pointer_missing:{pointer}")
    return current


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise MatrixV3Error("evidence_numeric_predicate_type_invalid")
    return float(value)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _commit(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)
