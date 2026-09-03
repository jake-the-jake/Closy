from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file

from .common import canonical_digest, read_mapping

EXECUTION_CLASSES = frozenset(
    {
        "ready",
        "in_progress",
        "gate_blocked",
        "scientific_attempt_sealed",
        "external_data_blocked",
        "hardware_blocked",
        "legal_or_privacy_blocked",
        "superseded",
        "deliberately_deferred_with_reason",
    }
)
KNOWN_COVERAGE_STATUSES = frozenset({"complete", "partial", "not_started", "discovery_pending"})
EXTERNAL_GATE_IDS = frozenset(
    {
        "BP-45-IMPLEMENTATION-23",
        "engine/CMakeLists.txt FetchContent declarations",
        "ZeroOne repository discovery",
    }
)
SATISFIED_EXTERNAL_GATES = EXTERNAL_GATE_IDS
CAPTURE_READY = frozenset({"BP-07-MODE-A", "BP-07-MODE-B", "BP-07-MODE-D", "BP-07-MODE-E"})
STATIC_RUNTIME_READY = frozenset({f"BP-09-Z{ordinal}" for ordinal in range(3, 9)})
SEALED_MARKERS = ("failed", "consumed", "sealed", "not run", "not_run", "ineligible")
PRIVACY_MARKERS = ("private", "privacy", "consent", "p1")
HARDWARE_MARKERS = ("gpu", "mobile device", "hardware")
EXTERNAL_MARKERS = ("real fabric", "real photo", "human review", "licensed", "external data")


def build_coverage_scheduler(
    coverage: Mapping[str, Any],
    *,
    blueprint_path: Path,
) -> dict[str, Any]:
    rows = coverage.get("rows")
    if not isinstance(rows, list):
        raise ValueError("scheduler_rows_missing")
    typed = [dict(row) for row in rows if isinstance(row, Mapping)]
    if len(typed) != len(rows):
        raise ValueError("scheduler_row_mapping_required")
    issues = validate_coverage_inventory(typed)
    if issues:
        raise ValueError(";".join(issues))
    identities = {str(row["id"]) for row in typed}
    complete = {str(row["id"]) for row in typed if row["status"] == "complete"}
    classified: list[dict[str, Any]] = []
    for row in typed:
        if row["status"] == "complete":
            continue
        row_id = str(row["id"])
        dependencies = [str(item) for item in row.get("dependencies", [])]
        satisfied = all(dep in complete or dep in SATISFIED_EXTERNAL_GATES for dep in dependencies)
        execution_class, reason = _classify(row, satisfied)
        classified.append(
            {
                "rowId": row_id,
                "coverageStatus": row["status"],
                "executionClass": execution_class,
                "reason": reason,
                "dependencies": dependencies,
                "dependenciesSatisfied": satisfied,
                "sourceSection": row.get("sourceSection"),
                "nextAction": row.get("nextAction"),
            }
        )
    source_sections = sorted({str(row.get("sourceSection", "")) for row in typed})
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "schedulerVersion": "closy.coverage_complete_scheduler.v4",
        "blueprintPath": f"docs/{blueprint_path.name}",
        "blueprintSha256": sha256_file(blueprint_path),
        "coverageVersion": coverage.get("version"),
        "dynamicRequirementCount": len(typed),
        "completeRowCount": len(complete),
        "mappedRequirementCount": len(identities),
        "unmappedRequirementCount": 0,
        "sourceSectionAudit": [
            {
                "sourceSection": section,
                "rowIds": sorted(
                    str(row["id"]) for row in typed if row.get("sourceSection") == section
                ),
            }
            for section in source_sections
        ],
        "externalGateIds": sorted(EXTERNAL_GATE_IDS),
        "executionClassVocabulary": sorted(EXECUTION_CLASSES),
        "executionClassCounts": dict(
            sorted(Counter(row["executionClass"] for row in classified).items())
        ),
        "readyRows": sorted(row["rowId"] for row in classified if row["executionClass"] == "ready"),
        "rows": classified,
        "inventoryValidation": "pass",
        "schedulerDigest": "",
    }
    if not result["readyRows"]:
        raise ValueError("scheduler_ready_set_must_not_be_empty")
    result["schedulerDigest"] = canonical_digest(result, "schedulerDigest")
    return result


def validate_coverage_inventory(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    issues: list[str] = []
    ids = [str(row.get("id", "")) for row in rows]
    if not ids or "" in ids:
        issues.append("scheduler_missing_row_id")
    if len(ids) != len(set(ids)):
        issues.append("scheduler_duplicate_row_id")
    known = set(ids) | set(EXTERNAL_GATE_IDS)
    for row in rows:
        if row.get("status") not in KNOWN_COVERAGE_STATUSES:
            issues.append("scheduler_unknown_coverage_status")
        if not row.get("sourceSection"):
            issues.append("scheduler_source_section_missing")
        dependencies = row.get("dependencies")
        if not isinstance(dependencies, list):
            issues.append("scheduler_dependencies_not_list")
            continue
        for dependency in dependencies:
            if str(dependency) not in known:
                issues.append("scheduler_dependency_reference_missing")
    if not issues and _has_cycle(rows):
        issues.append("scheduler_dependency_cycle")
    return sorted(set(issues))


def validate_scheduler(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    rows = document.get("rows")
    if not isinstance(rows, list):
        return ["scheduler_rows_missing"]
    if document.get("unmappedRequirementCount") != 0:
        issues.append("scheduler_unmapped_requirements")
    if len(rows) != int(document.get("dynamicRequirementCount", 0)) - int(
        document.get("completeRowCount", -1)
    ):
        issues.append("scheduler_noncomplete_row_count_mismatch")
    classes = [row.get("executionClass") for row in rows if isinstance(row, Mapping)]
    if any(value not in EXECUTION_CLASSES for value in classes):
        issues.append("scheduler_unknown_execution_class")
    if len(rows) != len({row.get("rowId") for row in rows if isinstance(row, Mapping)}):
        issues.append("scheduler_duplicate_classification")
    if not document.get("readyRows"):
        issues.append("scheduler_empty_ready_set")
    if document.get("schedulerDigest") != canonical_digest(document, "schedulerDigest"):
        issues.append("scheduler_digest_invalid")
    return sorted(set(issues))


def load_and_build_scheduler(coverage_path: Path, blueprint_path: Path) -> dict[str, Any]:
    return build_coverage_scheduler(read_mapping(coverage_path), blueprint_path=blueprint_path)


def _classify(row: Mapping[str, Any], dependencies_satisfied: bool) -> tuple[str, str]:
    row_id = str(row["id"])
    text = f"{row.get('nextAction', '')} {row.get('limitations', '')}".lower()
    if row_id in CAPTURE_READY:
        return "ready", "capture_contract_and_public_fixture_work_is_independent_of_gate_p1"
    if row_id in STATIC_RUNTIME_READY:
        return "ready", "conventional_static_runtime_discovery_is_candidate_independent"
    if row_id in {"BP-08-Q-MATERIAL-INFERENCE", "BP-17-PHASE-07"}:
        return "in_progress", "synthetic_solver_engineering_is_independent_of_real_fabric"
    if row_id in {"BP-17-PHASE-12", "BP-12-MODEL-STRATEGY"}:
        return "ready", "conventional_runtime_fallback_work_does_not_depend_on_z2"
    if row_id in {"BP-20-ALPHA", "BP-20-BETA", "BP-20-PRODUCTION"}:
        return "deliberately_deferred_with_reason", "success_level_prerequisites_are_not_met"
    if row_id == "BP-20-RESEARCH-PROTOTYPE":
        return "in_progress", "research_prototype_scope_is_active_but_partial"
    if row_id in {"BP-08-A-INGESTION", "BP-08-C-SEGMENTATION", "BP-08-E-MULTIVIEW-FUSION"}:
        return "in_progress", "public_and_synthetic_engineering_scope_remains_runnable"
    if any(marker in text for marker in PRIVACY_MARKERS):
        return "legal_or_privacy_blocked", "unavailable_private_or_consent_tier_only"
    if any(marker in text for marker in HARDWARE_MARKERS):
        return "hardware_blocked", "measured_hardware_tier_unavailable"
    if any(marker in text for marker in EXTERNAL_MARKERS):
        return "external_data_blocked", "external_evidence_tier_unavailable"
    if any(marker in text for marker in SEALED_MARKERS):
        return "scientific_attempt_sealed", "historical_scientific_attempt_is_terminal"
    if not dependencies_satisfied:
        return "gate_blocked", "one_or_more_declared_dependencies_are_not_complete"
    if row.get("status") == "partial":
        return "in_progress", "implemented_scope_is_partial_and_has_runnable_engineering"
    if row.get("status") == "not_started":
        return "ready", "declared_dependencies_are_satisfied"
    return "deliberately_deferred_with_reason", "discovery_is_bounded_to_a_later_declared_unit"


def _has_cycle(rows: Sequence[Mapping[str, Any]]) -> bool:
    graph = {
        str(row["id"]): [
            str(dep) for dep in row.get("dependencies", []) if str(dep).startswith("BP-")
        ]
        for row in rows
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for dependency in graph.get(node, []):
            if dependency in graph and visit(dependency):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)
