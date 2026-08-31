from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.package_io.paths import validate_package_relpath

MATRIX_EVALUATOR_VERSION = "closy.d0_research_matrix.predicate_evaluator.v2"
MatrixStatus = Literal["pass", "fail", "not_run"]


class MatrixEvaluationError(ValueError):
    pass


def evaluate_research_matrix(
    root: Path,
    *,
    registry: dict[str, Any],
    evidence_bindings: dict[str, dict[str, Any]],
    selected_identity: dict[str, str],
    source_anchor_sha: str,
) -> dict[str, Any]:
    """Evaluate every matrix row from opened evidence rather than stored verdicts."""

    _validate_registry(registry)
    _validate_identity(selected_identity)
    if len(source_anchor_sha) != 40:
        raise MatrixEvaluationError("matrix_source_anchor_invalid")

    rows = [
        _evaluate_row(root, definition, evidence_bindings, selected_identity)
        for definition in registry["rows"]
    ]
    counts = {
        status: sum(row["status"] == status for row in rows)
        for status in ("pass", "fail", "not_run")
    }
    required_rows = [row for row in rows if row["requiredForResearchPrototype"]]
    first_unmet = next((row for row in required_rows if row["status"] != "pass"), None)
    matrix: dict[str, Any] = {
        "schemaVersion": 2,
        "matrixVersion": "closy.final_d0_research_prototype_matrix.v2",
        "evaluatorVersion": MATRIX_EVALUATOR_VERSION,
        "thresholdRegistryId": registry["registryId"],
        "thresholdRegistryHash": _document_hash(registry),
        "sourceAnchorSha": source_anchor_sha,
        "selectedIdentity": dict(sorted(selected_identity.items())),
        "traceability": registry["traceability"],
        "rowCount": len(rows),
        "rows": rows,
        "statusCounts": counts,
        "researchPrototypeStatus": "pass" if first_unmet is None else "partial",
        "firstUnmetRequirement": (
            None
            if first_unmet is None
            else {
                "rowId": first_unmet["rowId"],
                "reasonCode": first_unmet["reasonCode"],
            }
        ),
        "claims": {
            "globalResearchPrototypePassed": first_unmet is None,
            "alphaReady": False,
            "humanEvidence": False,
            "privateUserEvidence": False,
            "deviceEvidence": False,
            "physicalClothEvidence": False,
        },
        "integrity": {"matrixHash": ""},
    }
    matrix["integrity"]["matrixHash"] = _document_hash(matrix, omitted_key="matrixHash")
    return matrix


def _evaluate_row(
    root: Path,
    definition: dict[str, Any],
    evidence_bindings: dict[str, dict[str, Any]],
    selected_identity: dict[str, str],
) -> dict[str, Any]:
    evidence_ids = list(definition["requiredEvidenceIds"])
    missing = [evidence_id for evidence_id in evidence_ids if evidence_id not in evidence_bindings]
    if missing:
        return _row_result(
            definition,
            "not_run",
            f"required_evidence_not_supplied:{missing[0]}",
            [],
        )

    opened: list[dict[str, Any]] = []
    try:
        for evidence_id in evidence_ids:
            opened.append(
                _open_and_evaluate(
                    root,
                    evidence_id,
                    evidence_bindings[evidence_id],
                    selected_identity,
                )
            )
    except MatrixEvaluationError as error:
        return _row_result(definition, "fail", str(error), opened)
    return _row_result(definition, "pass", "all_predicates_passed", opened)


def _open_and_evaluate(
    root: Path,
    evidence_id: str,
    binding: dict[str, Any],
    selected_identity: dict[str, str],
) -> dict[str, Any]:
    relative = binding.get("path")
    if not isinstance(relative, str):
        raise MatrixEvaluationError(f"evidence_path_invalid:{evidence_id}")
    try:
        validate_package_relpath(relative)
    except ValueError as error:
        raise MatrixEvaluationError(f"evidence_path_invalid:{evidence_id}") from error
    path = root / relative
    if not path.is_file():
        raise MatrixEvaluationError(f"evidence_artifact_missing:{evidence_id}")
    actual_hash = sha256_file(path)
    expected_hash = binding.get("sha256")
    if not isinstance(expected_hash, str) or actual_hash != expected_hash:
        raise MatrixEvaluationError(f"evidence_artifact_hash_mismatch:{evidence_id}")
    value = read_json(path)
    if not isinstance(value, dict):
        raise MatrixEvaluationError(f"evidence_object_required:{evidence_id}")
    predicates = binding.get("predicates")
    if not isinstance(predicates, list) or not predicates:
        raise MatrixEvaluationError(f"evidence_predicates_missing:{evidence_id}")
    results = [
        _evaluate_predicate(evidence_id, value, predicate, selected_identity)
        for predicate in predicates
    ]
    return {
        "evidenceId": evidence_id,
        "path": relative,
        "sha256": actual_hash,
        "payloadHash": _document_hash(value),
        "predicateResults": results,
    }


def _evaluate_predicate(
    evidence_id: str,
    value: dict[str, Any],
    predicate: Any,
    selected_identity: dict[str, str],
) -> dict[str, Any]:
    if not isinstance(predicate, dict):
        raise MatrixEvaluationError(f"evidence_predicate_invalid:{evidence_id}")
    pointer = predicate.get("pointer")
    operation = predicate.get("operation")
    if not isinstance(pointer, str) or not isinstance(operation, str):
        raise MatrixEvaluationError(f"evidence_predicate_invalid:{evidence_id}")
    observed = _resolve_pointer(value, pointer)
    expected = predicate.get("expected")
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
    elif operation == "identity_equals":
        identity_key = predicate.get("identityKey")
        if not isinstance(identity_key, str) or identity_key not in selected_identity:
            raise MatrixEvaluationError(f"identity_join_invalid:{evidence_id}:{pointer}")
        expected = selected_identity[identity_key]
        passed = observed == expected
    else:
        raise MatrixEvaluationError(f"evidence_predicate_operation_unknown:{operation}")
    if not passed:
        raise MatrixEvaluationError(
            f"evidence_predicate_failed:{evidence_id}:{predicate.get('predicateId', pointer)}"
        )
    return {
        "predicateId": str(predicate.get("predicateId", pointer)),
        "operation": operation,
        "passed": True,
    }


def _row_result(
    definition: dict[str, Any],
    status: MatrixStatus,
    reason_code: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "rowId": definition["rowId"],
        "requirement": definition["requirement"],
        "thresholdRef": definition["thresholdRef"],
        "evaluatorVersion": MATRIX_EVALUATOR_VERSION,
        "requiredEvidenceIds": list(definition["requiredEvidenceIds"]),
        "decisionGroup": definition["decisionGroup"],
        "requiredForResearchPrototype": definition["requiredForResearchPrototype"],
        "status": status,
        "reasonCode": reason_code,
        "openedEvidence": evidence,
    }


def _validate_registry(registry: dict[str, Any]) -> None:
    if registry.get("schemaVersion") != 1 or not isinstance(registry.get("registryId"), str):
        raise MatrixEvaluationError("matrix_registry_invalid")
    rows = registry.get("rows")
    traceability = registry.get("traceability")
    if not isinstance(rows, list) or not rows or not isinstance(traceability, list):
        raise MatrixEvaluationError("matrix_registry_invalid")
    row_ids = [row.get("rowId") for row in rows if isinstance(row, dict)]
    if len(row_ids) != len(rows) or len(row_ids) != len(set(row_ids)):
        raise MatrixEvaluationError("matrix_registry_row_inventory_invalid")
    required = {
        "rowId",
        "requirement",
        "thresholdRef",
        "requiredEvidenceIds",
        "decisionGroup",
        "requiredForResearchPrototype",
    }
    if any(set(row) != required for row in rows):
        raise MatrixEvaluationError("matrix_registry_row_shape_invalid")
    known = set(row_ids)
    traced: set[str] = set()
    for clause in traceability:
        if not isinstance(clause, dict) or not isinstance(clause.get("requiredRowIds"), list):
            raise MatrixEvaluationError("matrix_registry_traceability_invalid")
        clause_rows = set(clause["requiredRowIds"])
        if not clause_rows or not clause_rows <= known:
            raise MatrixEvaluationError("matrix_registry_traceability_invalid")
        traced.update(clause_rows)
    required_rows = {row["rowId"] for row in rows if row["requiredForResearchPrototype"]}
    if traced != required_rows:
        raise MatrixEvaluationError("matrix_registry_traceability_incomplete")


def _validate_identity(identity: dict[str, str]) -> None:
    required = {"avatarContractHash", "garmentId", "packageDigest"}
    if set(identity) != required:
        raise MatrixEvaluationError("matrix_selected_identity_invalid")
    if not identity["garmentId"].startswith("garment."):
        raise MatrixEvaluationError("matrix_selected_identity_invalid")
    for key in ("avatarContractHash", "packageDigest"):
        if not _is_sha256(identity[key]):
            raise MatrixEvaluationError(f"matrix_selected_identity_invalid:{key}")


def _resolve_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise MatrixEvaluationError("evidence_pointer_invalid")
    current = value
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise MatrixEvaluationError(f"evidence_pointer_missing:{pointer}")
    return current


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise MatrixEvaluationError("evidence_numeric_predicate_type_invalid")
    return float(value)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _document_hash(value: dict[str, Any], omitted_key: str | None = None) -> str:
    payload = value
    if omitted_key is not None:
        payload = {
            **value,
            "integrity": {**value.get("integrity", {}), omitted_key: ""},
        }
    return sha256_bytes(canonical_dumps(payload).encode())
