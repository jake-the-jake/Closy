from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

from .common import load_mapping, mapping, records

BUDGET_MAXIMA = {"seam_model": 2, "topology_strategy": 3, "canonical_candidate": 1}
LEDGER_PATH = Path(
    "docs/evidence/final_strategy3_v2/physical_budget_event_ledger_after_unit_u.json"
)


def validate_production_budget_ledger(forge_root: Path, document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    events = records(document.get("events"))
    try:
        derived = derive_verified_budget_state(forge_root, events)
    except ValueError as error:
        issues.append(str(error))
        derived = {}
    legacy_derived = {key: derived.get(key) for key in ("consumed", "remaining", "headEventHash")}
    if legacy_derived != mapping(document.get("derived")):
        issues.append("budget_derived_state_invalid")
    if document.get("maxima") != BUDGET_MAXIMA:
        issues.append("budget_maxima_invalid")
    if document.get("candidateAttemptConsumed") is not False:
        issues.append("candidate_attempt_consumption_invalid")
    if document.get("untouchedConfirmationAttemptConsumed") is not False:
        issues.append("confirmation_attempt_consumption_invalid")
    return sorted(set(issues))


def derive_verified_budget_state(
    forge_root: Path, events: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    consumed = {category: 0 for category in BUDGET_MAXIMA}
    previous_hash = ""
    seen_ids: set[str] = set()
    seen_sources: list[tuple[str, str]] = []
    for expected_ordinal, source_row in enumerate(events, start=1):
        row = dict(source_row)
        if row.get("ordinal") != expected_ordinal:
            raise ValueError("budget_event_order_invalid")
        event_id = str(row.get("eventId", ""))
        if not event_id or event_id in seen_ids:
            raise ValueError("budget_event_id_duplicate_or_missing")
        seen_ids.add(event_id)
        category = str(row.get("category", ""))
        if category not in BUDGET_MAXIMA:
            raise ValueError("budget_event_category_invalid")
        if row.get("consumed") is not True:
            raise ValueError("budget_event_must_be_consuming")
        if row.get("previousEventHash") != previous_hash:
            raise ValueError("budget_event_chain_invalid")
        if row.get("eventHash") != _event_digest(row):
            raise ValueError("budget_event_hash_invalid")
        source_path = _safe_source_path(str(row.get("sourcePath", "")))
        source_digest = str(row.get("sourceDigest", ""))
        if not source_digest or sha256_file(forge_root / source_path) != source_digest:
            raise ValueError("budget_event_source_digest_invalid")
        seen_sources.append((source_path, source_digest))
        consumed[category] += 1
        previous_hash = str(row["eventHash"])
    remaining = {
        category: maximum - consumed[category] for category, maximum in BUDGET_MAXIMA.items()
    }
    if any(value < 0 for value in remaining.values()):
        raise ValueError("budget_overconsumed")
    source_inventory_digest = sha256_bytes(
        canonical_dumps(
            [
                {"ordinal": index, "sourcePath": path, "sourceDigest": digest}
                for index, (path, digest) in enumerate(seen_sources, start=1)
            ]
        ).encode("utf-8")
    )
    return {
        "consumed": consumed,
        "remaining": remaining,
        "headEventHash": previous_hash,
        "sourceInventoryDigest": source_inventory_digest,
    }


def build_verified_budget_report(forge_root: Path) -> dict[str, Any]:
    source = load_mapping(forge_root / LEDGER_PATH)
    events = records(source.get("events"))
    derived = derive_verified_budget_state(forge_root, events)
    return {
        "schemaVersion": 1,
        "reportVersion": "closy.physical_budget_verified_successor.v1",
        "sourceLedgerPath": LEDGER_PATH.as_posix(),
        "sourceLedgerDigest": sha256_file(forge_root / LEDGER_PATH),
        "eventCount": len(events),
        "derived": derived,
        "strategy3Reserved": True,
        "strategy3Consumed": True,
        "strategy3ScientificAdmissionExecuted": False,
        "untouchedStrategy3ConfirmationAttemptConsumed": False,
        "canonicalCandidateAttemptsRemaining": derived["remaining"]["canonical_candidate"],
        "validationIssues": validate_production_budget_ledger(forge_root, source),
    }


def budget_mutation_report(forge_root: Path) -> dict[str, bool]:
    source = load_mapping(forge_root / LEDGER_PATH)
    baseline = records(source.get("events"))
    mutations: dict[str, list[dict[str, Any]]] = {}
    mutations["deletion"] = deepcopy(baseline[:-1])
    mutated = deepcopy(baseline)
    mutated[0]["sourceDigest"] = "0" * 64
    mutations["source_mutation"] = mutated
    duplicated = deepcopy(baseline)
    duplicated.insert(1, deepcopy(duplicated[0]))
    mutations["duplication"] = duplicated
    mutations["reorder"] = list(reversed(deepcopy(baseline)))
    report: dict[str, bool] = {}
    for name, rows in mutations.items():
        mutated_document = deepcopy(source)
        mutated_document["events"] = rows
        report[name] = bool(validate_production_budget_ledger(forge_root, mutated_document))
    return report


def _safe_source_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("budget_event_source_path_invalid")
    return path.as_posix()


def _event_digest(row: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(row))
    payload["eventHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
