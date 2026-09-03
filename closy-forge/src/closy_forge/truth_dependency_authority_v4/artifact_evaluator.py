from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file

from .common import canonical_digest, mapping

HEX256 = re.compile(r"^[0-9a-f]{64}$")
CompilerValidator = Callable[[Path, Mapping[str, Any]], Sequence[str]]


def evaluate_artifact_attempts(
    evidence_root: Path,
    protocol: Mapping[str, Any],
    attempts: Sequence[Mapping[str, Any]],
    *,
    compiler_validator: CompilerValidator,
) -> dict[str, Any]:
    """Evaluate contract integrity from reopened files, never producer pass labels.

    This harness establishes transport and contract integrity only. Synthetic fixtures are
    explicitly barred from becoming garment-scientific evidence.
    """
    required = [str(item) for item in protocol.get("requiredObservables", [])]
    thresholds = mapping(protocol.get("maximumAbsoluteErrorByObservable"))
    protocol_reasons: list[str] = []
    if not required or set(required) != set(thresholds):
        protocol_reasons.append("required_observable_vector_or_thresholds_invalid")
    expected_count = int(protocol.get("attemptDenominator", -1))
    if expected_count != len(attempts):
        protocol_reasons.append("attempt_denominator_mismatch")

    rows = [
        _evaluate_row(
            evidence_root,
            row,
            required,
            thresholds,
            compiler_validator=compiler_validator,
        )
        for row in attempts
    ]
    predicate_results = {
        "protocolComplete": not protocol_reasons,
        "rowInventoryComplete": len(rows) == expected_count,
        "allReferencedBytesReopened": all(row["predicates"]["bytesReopened"] for row in rows),
        "allDigestsVerified": all(row["predicates"]["digestsVerified"] for row in rows),
        "allRequiredObservablesPresent": all(
            row["predicates"]["requiredObservablesPresent"] for row in rows
        ),
        "allFrozenThresholdsSatisfied": all(
            row["predicates"]["thresholdsSatisfied"] for row in rows
        ),
        "allLineageBound": all(row["predicates"]["lineageBound"] for row in rows),
        "actualCompilerValidated": all(
            row["predicates"]["actualCompilerValidated"] for row in rows
        ),
        "noSelfDeclaredPassAuthority": all(
            row["predicates"]["selfDeclaredPassIgnored"] for row in rows
        ),
    }
    mandatory = list(predicate_results)
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "resultVersion": "closy.artifact_backed_integrity.v4",
        "evidenceClass": "contract_integrity_harness",
        "scientificCapabilityClaim": False,
        "syntheticMutationMayPromoteScience": False,
        "attemptDenominator": expected_count,
        "attemptsEvaluated": len(rows),
        "requiredObservables": required,
        "rows": rows,
        "protocolReasonCodes": sorted(protocol_reasons),
        "predicateResults": predicate_results,
        "mandatoryPredicates": mandatory,
        "mandatoryIntegrityPass": all(predicate_results[name] for name in mandatory),
        "resultDigest": "",
    }
    result["resultDigest"] = canonical_digest(result, "resultDigest")
    return result


def _evaluate_row(
    root: Path,
    row: Mapping[str, Any],
    required: list[str],
    thresholds: Mapping[str, Any],
    *,
    compiler_validator: CompilerValidator,
) -> dict[str, Any]:
    reasons: dict[str, list[str]] = {
        "bytesReopened": [],
        "digestsVerified": [],
        "requiredObservablesPresent": [],
        "thresholdsSatisfied": [],
        "lineageBound": [],
        "actualCompilerValidated": [],
        "selfDeclaredPassIgnored": [],
    }
    artifacts: dict[str, tuple[Path, dict[str, Any]]] = {}
    for role in ("prediction", "candidate", "compiler", "appearance", "package", "lineage"):
        declared = mapping(row.get(role))
        if not declared:
            reasons["bytesReopened"].append(f"{role}_reference_missing")
            reasons["digestsVerified"].append(f"{role}_digest_missing")
            continue
        path = _safe_path(root, str(declared.get("path", "")))
        digest = str(declared.get("sha256", ""))
        if path is None or not path.is_file():
            reasons["bytesReopened"].append(f"{role}_bytes_missing")
            continue
        if not HEX256.fullmatch(digest) or sha256_file(path) != digest:
            reasons["digestsVerified"].append(f"{role}_digest_invalid")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            reasons["bytesReopened"].append(f"{role}_json_invalid")
            continue
        if not isinstance(value, dict):
            reasons["bytesReopened"].append(f"{role}_mapping_required")
            continue
        artifacts[role] = (path, value)

    candidate = artifacts.get("candidate", (root, {}))[1]
    compiler = artifacts.get("compiler", (root, {}))[1]
    appearance = artifacts.get("appearance", (root, {}))[1]
    package = artifacts.get("package", (root, {}))[1]
    lineage = artifacts.get("lineage", (root, {}))[1]
    prediction = artifacts.get("prediction", (root, {}))[1]
    observables = mapping(compiler.get("observables"))
    if set(observables) != set(required):
        reasons["requiredObservablesPresent"].append("complete_required_observable_vector_missing")
    for name in required:
        value = observables.get(name)
        limit = thresholds.get(name)
        if not isinstance(value, int | float) or not math.isfinite(float(value)):
            reasons["thresholdsSatisfied"].append(f"{name}_nonfinite_or_missing")
        elif not isinstance(limit, int | float) or abs(float(value)) > float(limit):
            reasons["thresholdsSatisfied"].append(f"{name}_threshold_failed")

    ids = {
        str(document.get("attemptId", ""))
        for document in (prediction, candidate, compiler, appearance, package, lineage)
    }
    if ids != {str(row.get("attemptId", ""))}:
        reasons["lineageBound"].append("attempt_identifier_lineage_mismatch")
    candidate_digest = mapping(row.get("candidate")).get("sha256")
    if compiler.get("candidateSha256") != candidate_digest:
        reasons["lineageBound"].append("compiler_candidate_digest_mismatch")
    if appearance.get("candidateSha256") != candidate_digest:
        reasons["lineageBound"].append("appearance_candidate_digest_mismatch")
    if package.get("candidateSha256") != candidate_digest:
        reasons["lineageBound"].append("package_candidate_digest_mismatch")

    candidate_path = artifacts.get("candidate", (root, {}))[0]
    if candidate:
        try:
            reasons["actualCompilerValidated"].extend(compiler_validator(candidate_path, candidate))
        except Exception:
            reasons["actualCompilerValidated"].append("compiler_validator_failed_closed")
    else:
        reasons["actualCompilerValidated"].append("candidate_unavailable_for_compiler")
    if any(document.get("pass") is True for document in (prediction, candidate, compiler)):
        # A producer pass label is accepted as data but never consulted by any predicate.
        pass

    predicates = {name: not values for name, values in reasons.items()}
    return {
        "attemptId": row.get("attemptId"),
        "fixtureKind": row.get("fixtureKind"),
        "scientificEvidenceEligible": row.get("fixtureKind") != "synthetic_mutation",
        "predicates": predicates,
        "reasonCodes": {name: sorted(values) for name, values in reasons.items()},
        "rowIntegrityPass": all(predicates.values()),
    }


def _safe_path(root: Path, value: str) -> Path | None:
    if not value or Path(value).is_absolute():
        return None
    root_resolved = root.resolve()
    candidate = (root_resolved / value).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None
    return candidate
