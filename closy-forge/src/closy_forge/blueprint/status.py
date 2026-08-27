from __future__ import annotations

from collections import Counter
from typing import Any

STATUS_MODEL_VERSION = "closy.blueprint_status_model.v1"
PHASE_IDS = tuple(f"BP-17-PHASE-{index:02d}" for index in range(15))
GATE_IDS = (
    "BP-18-GATE-C1",
    "BP-18-GATE-C2",
    "BP-18-GATE-C3",
    "BP-18-GATE-Z1",
    "BP-18-GATE-Z2",
    "BP-18-GATE-P1",
)
MATURITY_IDS = (
    "BP-20-RESEARCH-PROTOTYPE",
    "BP-20-ALPHA",
    "BP-20-BETA",
    "BP-20-PRODUCTION",
)


def build_status_model(
    coverage: dict[str, Any], stack: dict[str, Any], *, evidence_anchor_sha: str
) -> dict[str, Any]:
    rows = list(coverage["rows"])
    by_id = {str(row["id"]): row for row in rows}
    counts = Counter(str(row["status"]) for row in rows)
    return {
        "schemaVersion": 1,
        "statusModelVersion": STATUS_MODEL_VERSION,
        "evidenceAnchorSha": evidence_anchor_sha,
        "coverage": {
            "total": len(rows),
            "counts": dict(sorted(counts.items())),
            "blueprintSha256": coverage["blueprintSha256"],
        },
        "phases": {
            phase_id.removeprefix("BP-17-PHASE-"): by_id[phase_id]["status"]
            for phase_id in PHASE_IDS
        },
        "gates": {
            gate_id.removeprefix("BP-18-GATE-"): by_id[gate_id]["status"] for gate_id in GATE_IDS
        },
        "maturity": {
            maturity_id.removeprefix("BP-20-"): by_id[maturity_id]["status"]
            for maturity_id in MATURITY_IDS
        },
        "stack": {
            "pullRequestCount": len(stack["pullRequests"]),
            "latestPullRequest": max(int(row["number"]) for row in stack["pullRequests"]),
            "linear": bool(stack["sequentialMergeRehearsal"]["passed"]),
            "exactHeadForgeExceptions": [
                int(row["number"])
                for row in stack["pullRequests"]
                if row["latestExactHeadForgeRun"] is None
            ],
        },
        "truth": {
            "phase8EvidenceScope": "deterministic_d0_fixture_family_verticals",
            "phases10To14EvidenceScope": "versioned_contract_fixture_foundations",
            "actualZeroOneRuntimeExecuted": False,
            "actualZeroOneComputeExecuted": False,
            "actualPhase9TrainingExecuted": False,
            "privateUserEvidenceRun": False,
            "physicalMobileEvidenceRun": False,
            "humanReviewRun": False,
        },
    }


def validate_status_model(
    model: dict[str, Any], coverage: dict[str, Any], stack: dict[str, Any]
) -> list[str]:
    issues: list[str] = []
    rebuilt = build_status_model(
        coverage, stack, evidence_anchor_sha=str(model.get("evidenceAnchorSha", ""))
    )
    if model != rebuilt:
        issues.append("status_model_not_recomputed_from_authority")
    if model.get("phases", {}).get("00") != "complete":
        issues.append("phase_zero_not_complete")
    if any(model.get("phases", {}).get(f"{index:02d}") != "partial" for index in range(1, 15)):
        issues.append("phase_completion_overclaimed")
    if model.get("stack", {}).get("exactHeadForgeExceptions") != [10]:
        issues.append("stack_exception_set_invalid")
    if model.get("truth", {}).get("actualZeroOneRuntimeExecuted") is not False:
        issues.append("zeroone_runtime_overclaimed")
    if model.get("truth", {}).get("actualPhase9TrainingExecuted") is not False:
        issues.append("phase9_training_overclaimed")
    return issues


def render_status_summary(model: dict[str, Any]) -> str:
    counts = model["coverage"]["counts"]
    phase_lines = "\n".join(
        f"- Phase {int(index)}: `{model['phases'][index]}`" for index in sorted(model["phases"])
    )
    gate_lines = "\n".join(f"- {name}: `{model['gates'][name]}`" for name in sorted(model["gates"]))
    return (
        "# Generated Blueprint Status\n\n"
        f"Authority: `{model['statusModelVersion']}` at evidence anchor "
        f"`{model['evidenceAnchorSha']}`.\n\n"
        "## Requirement Rows\n\n"
        f"- complete: {counts.get('complete', 0)}\n"
        f"- partial: {counts.get('partial', 0)}\n"
        f"- not started: {counts.get('not_started', 0)}\n"
        f"- discovery pending: {counts.get('discovery_pending', 0)}\n"
        f"- total: {model['coverage']['total']}\n\n"
        "## Phases\n\n"
        f"{phase_lines}\n\n"
        "## Gates\n\n"
        f"{gate_lines}\n\n"
        "Phase 8 evidence is limited to deterministic D0 fixture family verticals. "
        "Phase 10-14 evidence is limited to versioned contract-fixture foundations.\n"
    )
