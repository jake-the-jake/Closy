from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .blueprint_parser import build_requirement_inventory
from .common import canonical_digest

STATUS_ORDER = (
    "complete",
    "partial",
    "not_started",
    "discovery_pending",
    "dependency_blocked",
    "not_run",
    "failed",
    "superseded",
)


def build_pr62_baseline_inventory(text: str, source_blob_oid: str) -> dict[str, Any]:
    source = build_requirement_inventory(text, source_blob_oid=source_blob_oid)
    overrides = _status_overrides(source, include_capture_v2=False)
    inventory = build_requirement_inventory(
        text, source_blob_oid=source_blob_oid, status_overrides=overrides
    )
    return _decorate_inventory(inventory, "reconstructed_pr62_starting_head")


def build_pr63_inventory(
    text: str, source_blob_oid: str, *, result_digest: str | None
) -> dict[str, Any]:
    source = build_requirement_inventory(text, source_blob_oid=source_blob_oid)
    overrides = _status_overrides(source, include_capture_v2=True, result_digest=result_digest)
    inventory = build_requirement_inventory(
        text, source_blob_oid=source_blob_oid, status_overrides=overrides
    )
    return _decorate_inventory(inventory, "capture_reconstruction_v2_current")


def build_inventory_transition(
    parent: Mapping[str, Any], child: Mapping[str, Any], transition_commit: str
) -> dict[str, Any]:
    parent_rows = {str(row["id"]): row for row in parent["requirements"]}
    child_rows = {str(row["id"]): row for row in child["requirements"]}
    if set(parent_rows) != set(child_rows):
        raise ValueError("blueprint_transition_requirement_set_changed")
    rows = []
    for requirement_id in sorted(parent_rows):
        old = parent_rows[requirement_id]
        new = child_rows[requirement_id]
        rows.append(
            {
                "requirementId": requirement_id,
                "oldState": old["status"],
                "newState": new["status"],
                "transitionCommit": transition_commit,
                "evidenceAnchors": new["evidenceAnchors"],
                "reason": new["reason"],
                "stateChanged": old["status"] != new["status"],
            }
        )
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "transitionVersion": "closy.blueprint_inventory_transition.v2",
        "parentInventoryDigest": parent["inventoryDigest"],
        "childInventoryDigest": child["inventoryDigest"],
        "transitionCommit": transition_commit,
        "rowCount": len(rows),
        "rows": rows,
    }
    result["transitionDigest"] = canonical_digest(result)
    return result


def validate_decorated_inventory(repository: Path, inventory: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    requirements = inventory.get("requirements", [])
    if not isinstance(requirements, list):
        return ["blueprint_decorated_requirements_missing"]
    expected_counts = Counter(str(row.get("status")) for row in requirements)
    published_counts = inventory.get("statusCounts", {})
    if published_counts != {status: expected_counts.get(status, 0) for status in STATUS_ORDER}:
        failures.append("blueprint_status_counts_inconsistent")
    phase_rows: defaultdict[str, list[str]] = defaultdict(list)
    for row in requirements:
        phase_rows[str(row.get("phase"))].append(str(row.get("status")))
        for anchor in row.get("evidenceAnchors", []):
            value = str(anchor)
            member = PurePosixPath(value)
            if (
                not value
                or member.is_absolute()
                or ".." in member.parts
                or "\\" in value
                or not (repository / value).is_file()
            ):
                failures.append("blueprint_evidence_anchor_missing_or_unsafe")
    summaries = {phase: _reduce_phase(states) for phase, states in sorted(phase_rows.items())}
    if inventory.get("phaseSummaries") != summaries:
        failures.append("blueprint_phase_summary_inconsistent")
    if inventory.get("inventoryDigest") != canonical_digest(inventory, "inventoryDigest"):
        failures.append("blueprint_inventory_digest_invalid")
    return sorted(set(failures))


def _status_overrides(
    inventory: Mapping[str, Any],
    *,
    include_capture_v2: bool,
    result_digest: str | None = None,
) -> dict[str, dict[str, Any]]:
    overrides: dict[str, dict[str, Any]] = {}
    for row in inventory["requirements"]:
        phase = str(row["phase"])
        external = row["externalInputDependency"]
        if external is not None:
            overrides[str(row["id"])] = {
                "status": "dependency_blocked",
                "evidenceAnchors": [
                    "closy-forge/docs/evidence/capture_reconstruction_v2/truth_reconciliation.json"
                ],
                "reason": str(external),
            }
        elif phase in {"2", "3", "4"}:
            anchors = [
                "closy-forge/docs/evidence/capture_reconstruction_v2/truth_reconciliation.json"
            ]
            if include_capture_v2:
                anchors.append(
                    "closy-forge/docs/evidence/capture_reconstruction_v2/canonical_result_envelope.json"
                    if result_digest
                    else "closy-forge/fixtures/capture_reconstruction_v2/protocol.json"
                )
            overrides[str(row["id"])] = {
                "status": "partial",
                "evidenceAnchors": anchors,
                "reason": (
                    "source_guarded_synthetic_v2_engineering_not_real_private_phase_completion"
                    if include_capture_v2
                    else "pr61_synthetic_engineering_partial_after_erratum"
                ),
            }
        elif phase == "7":
            overrides[str(row["id"])] = {
                "status": "partial",
                "evidenceAnchors": [
                    "closy-forge/docs/evidence/phase7_solver_material_v1/retrospective_result.json"
                ],
                "reason": "pr62_toy_chain_failed_and_real_physical_material_evidence_missing",
            }
    return overrides


def _decorate_inventory(inventory: dict[str, Any], label: str) -> dict[str, Any]:
    status_counts = Counter(str(row["status"]) for row in inventory["requirements"])
    phase_rows: defaultdict[str, list[str]] = defaultdict(list)
    for row in inventory["requirements"]:
        phase_rows[str(row["phase"])].append(str(row["status"]))
    summaries = {phase: _reduce_phase(statuses) for phase, statuses in sorted(phase_rows.items())}
    inventory["inventoryLabel"] = label
    inventory["statusCounts"] = {status: status_counts.get(status, 0) for status in STATUS_ORDER}
    inventory["phaseSummaries"] = summaries
    inventory["summaryReductionVersion"] = "closy.phase_status_reduction.v2"
    inventory["inventoryDigest"] = canonical_digest(inventory)
    return inventory


def _reduce_phase(statuses: list[str]) -> str:
    if statuses and all(status == "complete" for status in statuses):
        return "complete"
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status in {"partial", "superseded"} for status in statuses):
        return "partial"
    if statuses and all(status == "dependency_blocked" for status in statuses):
        return "dependency_blocked"
    if any(status == "discovery_pending" for status in statuses):
        return "discovery_pending"
    return "not_started"
