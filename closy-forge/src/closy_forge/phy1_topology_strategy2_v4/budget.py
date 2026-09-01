from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

PARENT_HEAD = "07b28f804274cdf6f79347150a85fcc3ff9f4684"
CLASSIFIER_VERSION = "closy.phy1.topology_strategy2.budget_classifier.v1"


def build_budget_classifier() -> dict[str, Any]:
    categories = [
        _category("topology_or_dof_representation", True, "changes connectivity or shared DOFs"),
        _category("seam_constitutive_or_enforcement_model", False, "changes seam equations"),
        _category("solver_formulation", False, "changes integration or XPBD equations"),
        _category("support_model", False, "changes supports, pins, targets, or release"),
        _category("collision_model", False, "changes contact law, filtering, or cadence"),
        _category("evaluator_only_correction", False, "changes scoring without physics"),
        _category(
            "harness_or_reporting_defect",
            False,
            "candidate-independent defect may be repaired only before strategy lock",
        ),
    ]
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "classifierVersion": CLASSIFIER_VERSION,
        "parentHead": PARENT_HEAD,
        "appendOnly": True,
        "categories": categories,
        "budget": {
            "topologyStrategiesMaximum": 3,
            "topologyStrategiesConsumedBeforeUnitI": 1,
            "topologyStrategiesAvailableBeforeUnitI": 2,
            "unitICandidateExecutionsMaximum": 1,
            "preCandidateImplementationRevisionsMaximum": 2,
            "topologyStrategy3Reserved": True,
            "seamModelsMaximum": 2,
            "seamModelsConsumedBeforeUnitI": 2,
            "seamModelsRemaining": 0,
        },
        "consumptionRules": {
            "candidateAttemptConsumedWhen": (
                "selected_full_candidate_is_opened_and_any_solver_step_advances"
            ),
            "crashTimeoutSerializationOrUnpublishedAfterStepConsumes": True,
            "candidateIndependentMicrofixtureConsumesCandidateAttempt": False,
            "strategySpecificMicrofixtureFailureEndsUnit": True,
            "postCandidateRetryAllowed": False,
            "infrastructureRetryRequiresProofNoSolverStepAdvanced": True,
        },
        "forbiddenChanges": [
            "additional_support_duration_or_pins",
            "disabled_or_filtered_collisions",
            "deleted_difficult_geometry",
            "threshold_weakening",
            "new_seam_or_support_equation",
            "second_topology_strategy_in_this_unit",
        ],
        "integrity": {"classifierDigest": ""},
    }
    document["integrity"]["classifierDigest"] = _digest(document)
    return document


def validate_budget_classifier(document: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if document.get("classifierVersion") != CLASSIFIER_VERSION:
        issues.append("classifier_version_mismatch")
    if document.get("parentHead") != PARENT_HEAD:
        issues.append("parent_head_mismatch")
    if document.get("integrity", {}).get("classifierDigest") != _digest(document):
        issues.append("classifier_digest_mismatch")
    categories = {row.get("categoryId"): row for row in document.get("categories", [])}
    expected = {
        "topology_or_dof_representation",
        "seam_constitutive_or_enforcement_model",
        "solver_formulation",
        "support_model",
        "collision_model",
        "evaluator_only_correction",
        "harness_or_reporting_defect",
    }
    if set(categories) != expected:
        issues.append("classifier_category_inventory_mismatch")
    if categories.get("topology_or_dof_representation", {}).get("authorizedInUnitI") is not True:
        issues.append("topology_category_not_authorized")
    if any(
        row.get("authorizedInUnitI") is True
        for key, row in categories.items()
        if key != "topology_or_dof_representation"
    ):
        issues.append("non_topology_category_authorized")
    budget = document.get("budget", {})
    if budget.get("topologyStrategiesAvailableBeforeUnitI") != 2:
        issues.append("available_topology_budget_mismatch")
    if budget.get("topologyStrategy3Reserved") is not True:
        issues.append("topology_strategy3_not_reserved")
    if budget.get("seamModelsRemaining") != 0:
        issues.append("seam_budget_reopened")
    return issues


def classify_change(document: dict[str, Any], category_id: str) -> dict[str, Any]:
    issues = validate_budget_classifier(document)
    if issues:
        raise ValueError("invalid_budget_classifier:" + ",".join(issues))
    for row in document["categories"]:
        if row["categoryId"] == category_id:
            return dict(row)
    raise KeyError(category_id)


def _category(category_id: str, authorized: bool, boundary: str) -> dict[str, Any]:
    return {"categoryId": category_id, "authorizedInUnitI": authorized, "boundary": boundary}


def _digest(document: dict[str, Any]) -> str:
    payload = deepcopy(document)
    payload.setdefault("integrity", {})["classifierDigest"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
