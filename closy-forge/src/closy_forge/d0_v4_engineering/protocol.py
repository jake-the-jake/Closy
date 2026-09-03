from __future__ import annotations

import os
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes

PROTOCOL_VERSION = "closy.d0_v4.engineering_protocol.v1"
PROTOCOL_PATH = Path("docs/evidence/d0_v4_engineering/engineering_protocol.json")
LEDGER_PATH = Path("docs/evidence/d0_v4_engineering/engineering_budget_ledger.json")
PUBLIC_TEST_LOCK_PATH = Path("docs/evidence/d0_v4_engineering/public_test_execution.lock")

LIFECYCLE_STATES = (
    "scheduled",
    "container_returned",
    "abstained",
    "candidate_complete",
    "compiler_entered",
    "compile_valid",
    "appearance_evaluated",
    "appearance_pass",
    "all_gate_pass",
)

OBSERVABLE_PARAMETERS = (
    "garment_body_length",
    "half_chest_width",
    "body_ease",
    "shoulder_width",
    "shoulder_slope",
    "neckline_width",
    "front_neckline_depth",
    "back_neckline_depth",
    "armhole_depth",
    "sleeve_length",
    "sleeve_opening_width",
)

REQUIRED_OPENINGS = (
    "opening.cuff.left",
    "opening.cuff.right",
    "opening.hem",
    "opening.neck",
)


def load_engineering_protocol(root: Path) -> dict[str, Any]:
    value = read_json(root / PROTOCOL_PATH)
    if not isinstance(value, dict):
        raise ValueError("d0_v4_engineering_protocol_mapping_required")
    issues = validate_engineering_protocol(value)
    if issues:
        raise ValueError("d0_v4_engineering_protocol_invalid:" + ";".join(issues))
    return value


def load_budget_ledger(root: Path) -> dict[str, Any]:
    value = read_json(root / LEDGER_PATH)
    if not isinstance(value, dict):
        raise ValueError("d0_v4_budget_ledger_mapping_required")
    issues = validate_budget_ledger(value, load_engineering_protocol(root))
    if issues:
        raise ValueError("d0_v4_budget_ledger_invalid:" + ";".join(issues))
    return value


def validate_engineering_protocol(protocol: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if protocol.get("protocolVersion") != PROTOCOL_VERSION:
        issues.append("protocol_version_invalid")
    budgets = _mapping(protocol.get("budgets"))
    expected_budgets = {
        "maximumObservationContractRevisions": 3,
        "maximumCompleteModelTrainingTrials": 12,
        "maximumPublicTestExecutions": 1,
    }
    if any(budgets.get(key) != value for key, value in expected_budgets.items()):
        issues.append("engineering_budget_invalid")
    partitions = _mapping(protocol.get("partitions"))
    if partitions.get("trainingIdentityCount") != 512:
        issues.append("training_count_invalid")
    if partitions.get("validationIdentityCount") != 128:
        issues.append("validation_count_invalid")
    if partitions.get("publicTestIdentityCount") != 128:
        issues.append("public_test_count_invalid")
    if partitions.get("qualificationIdentityCount") != 0:
        issues.append("qualification_identity_present")
    lifecycle = protocol.get("lifecycleStates")
    if lifecycle != list(LIFECYCLE_STATES):
        issues.append("lifecycle_states_invalid")
    if protocol.get("observableParameters") != list(OBSERVABLE_PARAMETERS):
        issues.append("observable_parameter_axis_invalid")
    thresholds = _mapping(protocol.get("readinessThresholds"))
    required_thresholds: dict[str, float | int] = {
        "maximumForegroundSrgbMae": 0.10,
        "maximumMedianMacroNormalizedObservableError": 0.085,
        "maximumWorstNormalizedObservableError": 0.22,
        "maximumBoundaryProxyError": 0.20,
        "maximumLandmarkProxyError": 0.14,
        "maximumReferenceRmsVertexErrorMeters": 0.08,
        "minimumLogoIoUWhenApplicable": 0.05,
        "maximumLogoDisplacementNormalized": 0.14,
        "maximumLogoFalsePositiveFraction": 0.002,
        "minimumMeanEvaluatorViewSilhouetteIoU": 0.35,
        "minimumEvaluationCoverageRate": 0.95,
        "minimumRelativeParameterImprovement": 0.15,
        "minimumSilhouetteIoUImprovement": 0.03,
        "minimumPrimaryCanonicalCompileSuccess": 126,
        "primaryCanonicalCompileDenominator": 128,
        "requiredPanelCount": 5,
        "bootstrapResamples": 10000,
        "bootstrapConfidence": 0.95,
    }
    if any(thresholds.get(key) != value for key, value in required_thresholds.items()):
        issues.append("readiness_threshold_invalid")
    if thresholds.get("requiredOpenings") != list(REQUIRED_OPENINGS):
        issues.append("required_opening_axis_invalid")
    if thresholds.get("bootstrapLowerBoundsStrictlyPositive") is not True:
        issues.append("bootstrap_policy_invalid")
    if thresholds.get("failedRowPenalty") != {
        "macroNormalizedError": 1.0,
        "silhouetteIoU": 0.0,
    }:
        issues.append("failed_row_penalty_invalid")
    if protocol.get("publicTestMayGuideDevelopment") is not False:
        issues.append("public_test_selection_leak")
    if protocol.get("v3OutcomePreserved") != "completed_benchmark_failed_absolute_gates":
        issues.append("v3_outcome_not_preserved")
    if protocol.get("lostOpaqueV2Disjointness") != "unverified":
        issues.append("lost_v2_relation_overclaimed")
    if protocol.get("protocolDigest") != protocol_digest(protocol):
        issues.append("protocol_digest_invalid")
    return sorted(set(issues))


def validate_budget_ledger(ledger: Mapping[str, Any], protocol: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    events = ledger.get("events")
    if not isinstance(events, list) or not events:
        return ["budget_events_missing"]
    if [event.get("ordinal") for event in events if isinstance(event, Mapping)] != list(
        range(len(events))
    ):
        issues.append("budget_event_order_invalid")
    kinds = [str(event.get("event")) for event in events if isinstance(event, Mapping)]
    revision_count = kinds.count("observation_contract_revision_completed")
    trial_count = kinds.count("model_training_trial_completed")
    public_count = kinds.count("public_test_execution_started")
    public_terminal_count = sum(
        kind in {"public_test_execution_completed", "public_test_execution_failed"}
        for kind in kinds
    )
    budgets = _mapping(protocol.get("budgets"))
    if revision_count > int(budgets.get("maximumObservationContractRevisions", -1)):
        issues.append("observation_revision_budget_exceeded")
    if trial_count > int(budgets.get("maximumCompleteModelTrainingTrials", -1)):
        issues.append("model_training_trial_budget_exceeded")
    if public_count > int(budgets.get("maximumPublicTestExecutions", -1)):
        issues.append("public_test_execution_budget_exceeded")
    if public_terminal_count > public_count:
        issues.append("public_test_terminal_without_start")
    if public_count and kinds.index("public_test_execution_started") == len(kinds) - 1:
        pass
    elif public_count:
        start = kinds.index("public_test_execution_started")
        terminals = [
            index
            for index, kind in enumerate(kinds)
            if kind in {"public_test_execution_completed", "public_test_execution_failed"}
        ]
        if any(index <= start for index in terminals):
            issues.append("public_test_terminal_order_invalid")
    if ledger.get("observationContractRevisionsConsumed") != revision_count:
        issues.append("observation_revision_count_mismatch")
    if ledger.get("modelTrainingTrialsConsumed") != trial_count:
        issues.append("model_trial_count_mismatch")
    if ledger.get("publicTestExecutionsConsumed") != public_count:
        issues.append("public_test_count_mismatch")
    if ledger.get("ledgerDigest") != ledger_digest(ledger):
        issues.append("budget_ledger_digest_invalid")
    return sorted(set(issues))


def append_budget_event(root: Path, event: Mapping[str, Any]) -> dict[str, Any]:
    ledger = load_budget_ledger(root)
    updated = deepcopy(ledger)
    events = list(updated["events"])
    appended = dict(event)
    appended["ordinal"] = len(events)
    events.append(appended)
    updated["events"] = events
    kinds = [str(item["event"]) for item in events]
    updated["observationContractRevisionsConsumed"] = kinds.count(
        "observation_contract_revision_completed"
    )
    updated["modelTrainingTrialsConsumed"] = kinds.count("model_training_trial_completed")
    updated["publicTestExecutionsConsumed"] = kinds.count("public_test_execution_started")
    updated["ledgerDigest"] = ledger_digest(updated)
    issues = validate_budget_ledger(updated, load_engineering_protocol(root))
    if issues:
        raise ValueError("d0_v4_budget_event_invalid:" + ";".join(issues))
    _atomic_write(root / LEDGER_PATH, canonical_dumps(updated).encode("utf-8"))
    return updated


def claim_public_test_execution(
    root: Path, *, source_head: str, model_sha256: str
) -> dict[str, Any]:
    ledger = load_budget_ledger(root)
    if int(ledger["publicTestExecutionsConsumed"]) != 0:
        raise ValueError("d0_v4_public_test_execution_already_consumed")
    lock_path = root / PUBLIC_TEST_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = {
        "lockVersion": "closy.d0_v4.public_test_execution_claim.v1",
        "sourceHead": source_head,
        "modelSha256": model_sha256,
        "consumptionPolicy": "claim_precedes_first_public_test_read_and_survives_partial_failure",
    }
    descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, canonical_dumps(lock).encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return append_budget_event(
        root,
        {
            "event": "public_test_execution_started",
            "sourceHead": source_head,
            "modelSha256": model_sha256,
            "publicTestRead": False,
            "executionConsumedBeforeRead": True,
        },
    )


def complete_public_test_execution(
    root: Path, *, result_digest: str | None, readiness_pass: bool, failed_reason: str | None = None
) -> dict[str, Any]:
    ledger = load_budget_ledger(root)
    kinds = [str(item["event"]) for item in ledger["events"]]
    if kinds.count("public_test_execution_started") != 1:
        raise ValueError("d0_v4_public_test_completion_without_single_claim")
    if any(
        kind in {"public_test_execution_completed", "public_test_execution_failed"}
        for kind in kinds
    ):
        raise ValueError("d0_v4_public_test_terminal_already_recorded")
    safe_failed_reason = None
    if failed_reason is not None:
        safe_failed_reason = " ".join(str(failed_reason).split())[:240]
    return append_budget_event(
        root,
        {
            "event": (
                "public_test_execution_failed"
                if safe_failed_reason is not None
                else "public_test_execution_completed"
            ),
            "resultDigest": result_digest,
            "readinessPass": readiness_pass,
            "failedReason": safe_failed_reason,
            "publicTestRead": True,
        },
    )


def protocol_digest(protocol: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(protocol))
    payload["protocolDigest"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def ledger_digest(ledger: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(ledger))
    payload["ledgerDigest"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
