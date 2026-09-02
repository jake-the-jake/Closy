from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, Literal

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

STARTING_HEAD = "8dd7a547debf038e9e27c48cf8e42009ae69ac3a"
STARTING_BASE = "e062a30ba295ed27334622916ddb449fd76e2166"
MAIN_HEAD = "859d4ee9a8a3386e95ec8c29043aa9ecc246769a"
RESULTS = frozenset({"pass", "fail", "not_run"})
ATTEMPT_STATES = frozenset(
    {
        "not_attempted",
        "completed",
        "attempted_integrity_error",
        "dependency_blocked",
    }
)
EvidenceResult = Literal["pass", "fail", "not_run"]
BudgetCategory = Literal["seam_model", "topology_strategy", "canonical_candidate"]

ACTIVE_TAIL = (
    (46, "ba54b17a0aef7518d9acac30c6b7ec6564a38d87", "bc4927fe6d36667b5b236d844b4eff511ef6f987"),
    (47, "bc4927fe6d36667b5b236d844b4eff511ef6f987", "e25da69d29eb1b68885b911c7354df085f4a22c0"),
    (48, "e25da69d29eb1b68885b911c7354df085f4a22c0", "69f17e0bc0d01472eec3aaf244c158181f74febf"),
    (49, "69f17e0bc0d01472eec3aaf244c158181f74febf", "a72f45955abbe65ce14b7142668447d0477db71c"),
    (50, "a72f45955abbe65ce14b7142668447d0477db71c", "552867e96d53e9d4c728f90d12e0c1c9a344ba0d"),
    (51, "552867e96d53e9d4c728f90d12e0c1c9a344ba0d", "e062a30ba295ed27334622916ddb449fd76e2166"),
    (52, STARTING_BASE, STARTING_HEAD),
)

PUBLICATION_ANCHORS = {
    "46": {
        "scientificSourceSha": "9bfe08ce9111f8437825206695e6faf441442ad3",
        "scientificResultSha": "069707bbd0bfc95eabbc5a3b3045e349d4c0b121",
        "publicationHeadSha": "bc4927fe6d36667b5b236d844b4eff511ef6f987",
    },
    "47": {
        "scientificSourceSha": "0ab88467c4c290a0cccb6410c6d744d49067f4c3",
        "scientificResultSha": "3541507808946ae1248fba110b7732599db3fdbc",
        "publicationHeadSha": "e25da69d29eb1b68885b911c7354df085f4a22c0",
    },
}

BUDGET_MAXIMA: dict[BudgetCategory, int] = {
    "seam_model": 2,
    "topology_strategy": 3,
    "canonical_candidate": 1,
}


def canonical_digest(document: Mapping[str, Any], field: str = "canonicalDigest") -> str:
    payload = deepcopy(dict(document))
    payload[field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def build_starting_manifest() -> dict[str, Any]:
    tail = [
        {
            "pullRequest": number,
            "baseSha": base,
            "headSha": head,
            "mergeBaseSha": base,
            "open": True,
            "draft": True,
            "mergeable": True,
            "unmerged": True,
        }
        for number, base, head in ACTIVE_TAIL
    ]
    document: dict[str, Any] = {
        "schemaVersion": 2,
        "manifestVersion": "closy.evidence_authority_recovery.starting_manifest.v2",
        "repository": "jake-the-jake/Closy",
        "mainHeadSha": MAIN_HEAD,
        "unitSBaseSha": STARTING_HEAD,
        "activeTail": tail,
        "publicationAnchors": PUBLICATION_ANCHORS,
        "externalObservation": {
            "timestampUtc": "2026-09-02T00:00:00Z",
            "acquisitionMethod": "authenticated_gh_cli_and_local_git_read_only",
            "pr52ForgeRunId": "33570351597",
            "pr52ForgeSuccessfulJobs": 29,
            "pr52ForgeFailedJobs": 0,
            "pr52ExpectedSupabaseSkips": 1,
        },
        "canonicalDigest": "",
    }
    document["canonicalDigest"] = canonical_digest(document)
    return document


def validate_starting_manifest(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    rows = _records(document.get("activeTail"))
    if len(rows) != len(ACTIVE_TAIL):
        issues.append("active_tail_denominator_invalid")
    seen: set[int] = set()
    previous_head = ""
    for index, row in enumerate(rows):
        number = _integer(row.get("pullRequest"))
        if number in seen:
            issues.append("active_tail_pr_duplicate")
        seen.add(number)
        if index and row.get("baseSha") != previous_head:
            issues.append("active_tail_parent_order_invalid")
        if row.get("mergeBaseSha") != row.get("baseSha"):
            issues.append("active_tail_merge_base_invalid")
        if not all(row.get(field) is True for field in ("open", "draft", "mergeable", "unmerged")):
            issues.append("active_tail_state_invalid")
        previous_head = str(row.get("headSha", ""))
    if previous_head != STARTING_HEAD:
        issues.append("active_tail_final_head_invalid")
    anchors = _mapping(document.get("publicationAnchors"))
    for number in (46, 47):
        row = _mapping(anchors.get(str(number)))
        if not row:
            issues.append(f"publication_anchor_missing:{number}")
            continue
        if row.get("scientificSourceSha") == row.get("publicationHeadSha"):
            issues.append(f"publication_source_conflated:{number}")
        if row.get("scientificResultSha") == row.get("publicationHeadSha"):
            issues.append(f"publication_result_conflated:{number}")
    observation = _mapping(document.get("externalObservation"))
    if observation.get("acquisitionMethod") != "authenticated_gh_cli_and_local_git_read_only":
        issues.append("external_observation_method_invalid")
    if observation.get("pr52ForgeSuccessfulJobs") != 29:
        issues.append("external_rollup_success_invalid")
    if observation.get("pr52ForgeFailedJobs") != 0:
        issues.append("external_rollup_failure_invalid")
    if canonical_digest(document) != document.get("canonicalDigest"):
        issues.append("starting_manifest_digest_invalid")
    return sorted(set(issues))


def build_external_attestation() -> dict[str, Any]:
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "attestationVersion": "closy.external_pr_workflow_attestation.v1",
        "repository": "jake-the-jake/Closy",
        "repositoryUrl": "https://github.com/jake-the-jake/Closy",
        "pullRequest": 52,
        "pullRequestUrl": "https://github.com/jake-the-jake/Closy/pull/52",
        "baseBranch": "codex/closy-forge-d0-strict-c3-confirmation-v5",
        "baseSha": STARTING_BASE,
        "headBranch": "codex/closy-forge-phy1-topology-strategy3-diagnosis-v1",
        "headSha": STARTING_HEAD,
        "mergeBaseSha": STARTING_BASE,
        "state": {"open": True, "draft": True, "mergeable": True, "unmerged": True},
        "workflow": {
            "name": "Closy Forge",
            "runId": "33570351597",
            "runUrl": "https://github.com/jake-the-jake/Closy/actions/runs/33570351597",
            "headSha": STARTING_HEAD,
            "requiredJobId": "100068410403",
            "requiredCheckName": "Forge required",
            "requiredConclusion": "success",
            "successfulChecks": 29,
            "failedChecks": 0,
            "skipClassifications": ["supabase_preview_expected_not_applicable"],
        },
        "observedAtUtc": "2026-09-02T00:00:00Z",
        "acquisitionMethod": "authenticated_gh_cli_read_only",
        "scientificEvidenceAnchorSha": "83d5b2a263cf34670370d2c187fe26c0e204475d",
        "canonicalDigest": "",
    }
    document["canonicalDigest"] = canonical_digest(document)
    return document


def validate_external_attestation(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    required = (
        "repository",
        "repositoryUrl",
        "pullRequest",
        "pullRequestUrl",
        "baseBranch",
        "baseSha",
        "headBranch",
        "headSha",
        "mergeBaseSha",
        "observedAtUtc",
        "acquisitionMethod",
        "scientificEvidenceAnchorSha",
    )
    for field in required:
        if document.get(field) in (None, ""):
            issues.append(f"external_attestation_field_missing:{field}")
    if document.get("mergeBaseSha") != document.get("baseSha"):
        issues.append("external_attestation_merge_base_invalid")
    if document.get("scientificEvidenceAnchorSha") == document.get("headSha"):
        issues.append("external_attestation_scientific_anchor_conflated")
    state = _mapping(document.get("state"))
    if not all(state.get(field) is True for field in ("open", "draft", "mergeable", "unmerged")):
        issues.append("external_attestation_state_invalid")
    workflow = _mapping(document.get("workflow"))
    if workflow.get("headSha") != document.get("headSha"):
        issues.append("external_attestation_workflow_head_invalid")
    if workflow.get("requiredConclusion") != "success":
        issues.append("external_attestation_required_workflow_not_success")
    if workflow.get("failedChecks") != 0:
        issues.append("external_attestation_failed_rollup_hidden")
    if not _records_or_strings(workflow.get("skipClassifications")):
        issues.append("external_attestation_skip_classification_missing")
    if canonical_digest(document) != document.get("canonicalDigest"):
        issues.append("external_attestation_digest_invalid")
    return sorted(set(issues))


def validate_result_record(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    result = document.get("result")
    attempt = document.get("attemptState")
    if result not in RESULTS:
        issues.append("result_state_unknown")
    if attempt not in ATTEMPT_STATES:
        issues.append("attempt_state_unknown")
    denominators = _mapping(document.get("denominators"))
    counts = _mapping(document.get("counts"))
    for field, denominator in denominators.items():
        if not isinstance(denominator, int) or isinstance(denominator, bool) or denominator < 0:
            issues.append(f"denominator_invalid:{field}")
            continue
        count = counts.get(field)
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or count > denominator
        ):
            issues.append(f"count_invalid:{field}")
        if result == "pass" and count != denominator:
            issues.append(f"pass_denominator_incomplete:{field}")
    if result == "pass" and attempt != "completed":
        issues.append("pass_attempt_state_invalid")
    if attempt == "not_attempted" and result != "not_run":
        issues.append("not_attempted_result_invalid")
    rows = _records(document.get("rows"))
    keys = [(str(row.get("identity")), str(row.get("route"))) for row in rows]
    if len(keys) != len(set(keys)):
        issues.append("evaluator_identity_route_duplicate")
    required_rows = _strings(document.get("requiredRequirementIds"))
    actual_rows = _strings(document.get("requirementIds"))
    if len(actual_rows) != len(set(actual_rows)):
        issues.append("requirement_id_duplicate")
    if set(actual_rows) != set(required_rows):
        issues.append("requirement_inventory_incomplete")
    if document.get("repeatReserveDefined") is not True:
        issues.append("repeat_reserve_missing")
    return sorted(set(issues))


def build_budget_event_ledger() -> dict[str, Any]:
    specifications: list[tuple[BudgetCategory, str, str, str]] = [
        (
            "seam_model",
            "PHY1-V2-SEAM-EXPLICIT-ENDPOINT-EQUIVALENCE",
            "docs/evidence/phy1_topology_v2/phy1_experiment.json",
            "42b451ab5942fada516f0b70fafa0cc495a5fb61fb6383b6e86fe09a4d441502",
        ),
        (
            "topology_strategy",
            "PHY1-V2-S1-CONSTRAINED-INTERIOR-REFINEMENT",
            "docs/evidence/phy1_topology_v2/phy1_experiment.json",
            "42b451ab5942fada516f0b70fafa0cc495a5fb61fb6383b6e86fe09a4d441502",
        ),
        (
            "seam_model",
            "PHY1-V3-SEAM-SUPPORT",
            "docs/evidence/phy1_seam_support_v3/outcome.json",
            "315213f252cc76ce78fcc5250c88057490fa6779e9af29401a6be6196fa263dc",
        ),
        (
            "topology_strategy",
            "PHY1-V4-S2-QUOTIENT-SEAM-DOF",
            "docs/evidence/phy1_topology_strategy2_v4/physical_attempt_registry.json",
            "48b0d7aa91e9a6b7617506eebe35b735703460d5720633eb1e987dbd63f33c3e",
        ),
    ]
    events: list[dict[str, Any]] = []
    previous_hash = ""
    for ordinal, (category, event_id, source_path, source_digest) in enumerate(
        specifications, start=1
    ):
        event = _budget_event(
            ordinal,
            category,
            event_id,
            source_path,
            source_digest,
            previous_hash,
        )
        events.append(event)
        previous_hash = str(event["eventHash"])
    engineering = [
        {
            "revision": 1,
            "strategyClass": "local_longest_edge_bisection",
            "sourcePath": "docs/evidence/phy1_topology_strategy3_diagnosis_v1/revision_1.json",
            "scientificBudgetConsumed": False,
        },
        {
            "revision": 2,
            "strategyClass": "closure_longest_edge_bisection",
            "sourcePath": "docs/evidence/phy1_topology_strategy3_diagnosis_v1/revision_2.json",
            "scientificBudgetConsumed": False,
        },
    ]
    derived = derive_budgets(events)
    document: dict[str, Any] = {
        "schemaVersion": 2,
        "ledgerVersion": "closy.physical_budget_event_ledger.v2",
        "maxima": dict(BUDGET_MAXIMA),
        "events": events,
        "engineeringRevisions": engineering,
        "derived": derived,
        "unitOV1Outcome": "diagnosis_integrity_error",
        "canonicalDigest": "",
    }
    document["canonicalDigest"] = canonical_digest(document)
    return document


def derive_budgets(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    consumed: dict[str, int] = {category: 0 for category in BUDGET_MAXIMA}
    seen_ids: set[str] = set()
    previous_ordinal = 0
    previous_hash = ""
    for row in events:
        ordinal = _integer(row.get("ordinal"))
        if ordinal != previous_ordinal + 1:
            raise ValueError("budget_event_order_invalid")
        event_id = str(row.get("eventId", ""))
        if not event_id or event_id in seen_ids:
            raise ValueError("budget_event_id_duplicate_or_missing")
        seen_ids.add(event_id)
        category = str(row.get("category", ""))
        if category not in BUDGET_MAXIMA:
            raise ValueError(f"budget_event_category_invalid:{category}")
        if row.get("consumed") is not True:
            raise ValueError("budget_event_non_consuming_scientific_event")
        if row.get("previousEventHash") != previous_hash:
            raise ValueError("budget_event_chain_invalid")
        expected_hash = _event_digest(row)
        if row.get("eventHash") != expected_hash:
            raise ValueError("budget_event_hash_invalid")
        consumed[category] += 1
        previous_ordinal = ordinal
        previous_hash = expected_hash
    remaining = {
        category: maximum - consumed[category]
        for category, maximum in BUDGET_MAXIMA.items()
    }
    if any(value < 0 for value in remaining.values()):
        raise ValueError("budget_overconsumed")
    return {"consumed": consumed, "remaining": remaining, "headEventHash": previous_hash}


def validate_budget_event_ledger(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    try:
        derived = derive_budgets(_records(document.get("events")))
    except ValueError as error:
        issues.append(str(error))
        derived = {}
    if derived != _mapping(document.get("derived")):
        issues.append("budget_derived_state_invalid")
    engineering = _records(document.get("engineeringRevisions"))
    if len(engineering) != 2 or any(
        row.get("scientificBudgetConsumed") is not False for row in engineering
    ):
        issues.append("unit_o_engineering_revisions_misclassified")
    if document.get("unitOV1Outcome") != "diagnosis_integrity_error":
        issues.append("unit_o_integrity_outcome_not_preserved")
    if canonical_digest(document) != document.get("canonicalDigest"):
        issues.append("budget_ledger_digest_invalid")
    return sorted(set(issues))


def _budget_event(
    ordinal: int,
    category: BudgetCategory,
    event_id: str,
    source_path: str,
    source_digest: str,
    previous_hash: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "ordinal": ordinal,
        "category": category,
        "eventId": event_id,
        "sourcePath": source_path,
        "sourceDigest": source_digest,
        "consumed": True,
        "previousEventHash": previous_hash,
        "eventHash": "",
    }
    row["eventHash"] = _event_digest(row)
    return row


def _event_digest(row: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(row))
    payload["eventHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: object) -> list[dict[str, Any]]:
    return [_mapping(item) for item in value] if isinstance(value, list | tuple) else []


def _strings(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list | tuple) else []


def _records_or_strings(value: object) -> bool:
    return isinstance(value, list | tuple) and bool(value)


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else -1
