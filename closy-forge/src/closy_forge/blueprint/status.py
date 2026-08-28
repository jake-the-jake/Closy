from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

STATUS_MODEL_VERSION = "closy.blueprint_status_model.v2"
PHASE_IDS = tuple(f"BP-17-PHASE-{index:02d}" for index in range(15))
MATURITY_IDS = (
    "BP-20-RESEARCH-PROTOTYPE",
    "BP-20-ALPHA",
    "BP-20-BETA",
    "BP-20-PRODUCTION",
)
PR23_HEAD = "a481ba26a424bd91607b8c1d41b6173a2c9579d9"
ZEROONE_HISTORICAL_SHA = "c6388cbbf53ba8a47831ec25e83808e1edf32194"
ZEROONE_CURRENT_MASTER = "a17762bc1fc12fbd33f0488634635a5dcfdf8da3"
ZEROONE_EXECUTABLE_SHA256 = "7629cb8d6953887636f1863d23f17e2e79002af79eedbacb3d3e99bba830990e"

_COMMON_UNSUPPORTED = ["D1", "D2", "D3", "GPU", "mobile", "private_user"]
GATE_RECORDS: dict[str, dict[str, Any]] = {
    "C1": {
        "gateId": "C1",
        "globalStatus": "partial",
        "scopedStatus": "pass",
        "evidenceTier": "committed_deterministic_fixture_reports",
        "platform": ["ubuntu", "windows"],
        "toolchain": ["CPython 3.11", "CPython 3.12"],
        "sourceSha": PR23_HEAD,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU",
        "gateScope": "capture_contract",
        "evidenceDurability": "committed_reports_plus_exact_head_ci",
        "workflowRun": "33150483293",
        "unsupportedTiers": _COMMON_UNSUPPORTED,
        "blockers": ["authorised_capture_breadth", "private_user_evidence"],
    },
    "C2": {
        "gateId": "C2",
        "globalStatus": "partial",
        "scopedStatus": "pass",
        "evidenceTier": "committed_deterministic_fixture_reports",
        "platform": ["ubuntu", "windows"],
        "toolchain": ["CPython 3.11", "CPython 3.12"],
        "sourceSha": PR23_HEAD,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU",
        "gateScope": "canonical_generation_contract",
        "evidenceDurability": "committed_reports_plus_exact_head_ci",
        "workflowRun": "33150483293",
        "unsupportedTiers": _COMMON_UNSUPPORTED,
        "blockers": ["independent_provider_breadth", "human_visual_review"],
    },
    "C3-Binding-D0": {
        "gateId": "C3-Binding-D0",
        "globalStatus": "partial",
        "scopedStatus": "requalification_required",
        "evidenceTier": "committed_pre_requalification_reports",
        "platform": ["ubuntu", "windows"],
        "toolchain": ["CPython 3.11", "CPython 3.12"],
        "sourceSha": PR23_HEAD,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU",
        "gateScope": "binding",
        "evidenceDurability": "committed_reports_plus_exact_head_ci",
        "workflowRun": "33150483293",
        "unsupportedTiers": _COMMON_UNSUPPORTED,
        "blockers": [
            "literal_five_requirement_binding_manifest_not_yet_reconciled",
            "pose_suite_requalification_pending",
        ],
    },
    "PHY1-SingleLayer-D0": {
        "gateId": "PHY1-SingleLayer-D0",
        "globalStatus": "partial",
        "scopedStatus": "failed",
        "evidenceTier": "committed_failure_witnesses",
        "platform": ["windows"],
        "toolchain": ["CPython 3.11"],
        "sourceSha": PR23_HEAD,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU",
        "gateScope": "physical",
        "evidenceDurability": "committed_failure_reports",
        "workflowRun": "33150483293",
        "unsupportedTiers": _COMMON_UNSUPPORTED + ["multilayer"],
        "blockers": [
            "timestamped_states_passed_0_of_11",
            "unresolved_contacts_137",
            "residual_depth_0.002327721_exceeds_0.000160000",
            "minimum_body_clearance_negative_0.099391794",
            "strict_seam_crack_and_slip_not_met",
        ],
    },
    "Z1": {
        "gateId": "Z1",
        "globalStatus": "partial",
        "scopedStatus": "historical_local_pass",
        "historicalProfileStatus": "pass",
        "currentMasterRequalified": False,
        "phase10Status": "partial",
        "evidenceTier": "historical_local_binary_plus_committed_reports",
        "platform": ["windows"],
        "toolchain": ["MSVC 19.36 Release"],
        "sourceSha": ZEROONE_HISTORICAL_SHA,
        "currentMasterSha": ZEROONE_CURRENT_MASTER,
        "executableSha": ZEROONE_EXECUTABLE_SHA256,
        "garmentFamilies": ["tshirt", "layered_asymmetric"],
        "avatarProfile": "not_applicable_static_cook",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU/headless/static",
        "gateScope": "static ZeroOne",
        "evidenceDurability": "local_historical_binary_plus_committed_reports",
        "workflowRun": "33150483293",
        "unsupportedTiers": ["current_master", "GPU", "mobile", "dynamic", "human_review"],
        "blockers": ["current_master_requalification", "durable_processor_workflow"],
    },
    "Z2": {
        "gateId": "Z2",
        "globalStatus": "discovery_pending",
        "scopedStatus": "not_run",
        "evidenceTier": "none",
        "platform": [],
        "toolchain": [],
        "sourceSha": ZEROONE_CURRENT_MASTER,
        "executableSha": None,
        "garmentFamilies": [],
        "avatarProfile": "none",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "not_run",
        "gateScope": "dynamic ZeroOne",
        "evidenceDurability": "none",
        "workflowRun": None,
        "unsupportedTiers": ["mechanical_reference", "solver_driven", "GPU", "mobile"],
        "blockers": ["C3-Binding-D0", "refreshed_paired_Z1", "compiled_dynamic_execution"],
    },
    "P1": {
        "gateId": "P1",
        "globalStatus": "discovery_pending",
        "scopedStatus": "not_run",
        "evidenceTier": "none",
        "platform": [],
        "toolchain": [],
        "sourceSha": PR23_HEAD,
        "executableSha": None,
        "garmentFamilies": [],
        "avatarProfile": "none",
        "computeProfile": "not_run",
        "dataProvenance": "private user",
        "executionKind": "not_run",
        "gateScope": "product",
        "evidenceDurability": "none",
        "workflowRun": None,
        "unsupportedTiers": ["private_user", "licence", "human_review", "mobile"],
        "blockers": ["consent", "privacy_review", "licence_review", "device_evidence"],
    },
}


def build_status_model(
    coverage: dict[str, Any], stack: dict[str, Any], *, evidence_anchor_sha: str
) -> dict[str, Any]:
    rows = list(coverage["rows"])
    by_id = {str(row["id"]): row for row in rows}
    counts = Counter(str(row["status"]) for row in rows)
    stages = {
        f"Z{index}": deepcopy(
            GATE_RECORDS.get(
                f"Z{index}",
                {
                    "gateId": f"Z{index}",
                    "globalStatus": by_id[f"BP-09-Z{index}"]["status"],
                    "scopedStatus": "not_run",
                    "evidenceTier": "none",
                    "platform": [],
                    "toolchain": [],
                    "sourceSha": ZEROONE_CURRENT_MASTER,
                    "executableSha": None,
                    "garmentFamilies": [],
                    "avatarProfile": "none",
                    "computeProfile": "not_run",
                    "dataProvenance": "none",
                    "executionKind": "not_run",
                    "gateScope": "dynamic ZeroOne",
                    "evidenceDurability": "none",
                    "workflowRun": None,
                    "unsupportedTiers": ["all_runtime_profiles"],
                    "blockers": ["stage_not_implemented_or_executed"],
                },
            )
        )
        for index in range(1, 9)
    }
    gates = {name: deepcopy(record) for name, record in GATE_RECORDS.items() if name != "Z2"}
    gates.update(stages)
    return {
        "schemaVersion": 2,
        "statusModelVersion": STATUS_MODEL_VERSION,
        "evidenceAnchorSha": evidence_anchor_sha,
        "coverage": {
            "total": len(rows),
            "counts": dict(sorted(counts.items())),
            "blueprintSha256": coverage["blueprintSha256"],
            "coverageVersion": coverage["version"],
        },
        "phases": {
            phase_id.removeprefix("BP-17-PHASE-"): by_id[phase_id]["status"]
            for phase_id in PHASE_IDS
        },
        "gates": gates,
        "maturity": {
            maturity_id.removeprefix("BP-20-"): by_id[maturity_id]["status"]
            for maturity_id in MATURITY_IDS
        },
        "stack": {
            "pullRequestCount": len(stack["nodes"]),
            "latestPullRequest": max(int(row["pullRequest"]) for row in stack["nodes"]),
            "topology": "explicit_dag",
            "acyclic": bool(stack["validation"]["acyclic"]),
            "exactMergeBases": bool(stack["validation"]["exactMergeBases"]),
            "replayedCommonAncestryAbsent": bool(
                stack["validation"]["replayedCommonAncestryAbsent"]
            ),
            "exactHeadForgeExceptions": [
                int(row["pullRequest"])
                for row in stack["nodes"]
                if row["latestExactHeadForgeRun"] is None
            ],
        },
        "truth": {
            "phase8EvidenceScope": "deterministic_fixture_family_verticals",
            "phases10To14EvidenceScope": (
                "historical_phase10_cpu_static_plus_phase11_to14_contract_fixtures"
            ),
            "actualZeroOneStaticCookExecutedThisInvocation": False,
            "actualZeroOneStaticArtifactLoaded": False,
            "cacheValidated": True,
            "historicalZeroOneStaticCookEvidencePresent": True,
            "actualZeroOneDynamicDeformationExecuted": False,
            "actualZeroOneGpuRuntimeExecuted": False,
            "actualZeroOneMobileRuntimeExecuted": False,
            "actualPhase9TrainingExecuted": True,
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
    z1 = model.get("gates", {}).get("Z1", {})
    if z1.get("globalStatus") != "partial" or z1.get("scopedStatus") != "historical_local_pass":
        issues.append("zeroone_z1_scope_inflated")
    truth = model.get("truth", {})
    if truth.get("actualZeroOneStaticCookExecutedThisInvocation") is not False:
        issues.append("status_reconciliation_must_not_claim_fresh_static_cook")
    if truth.get("actualZeroOneDynamicDeformationExecuted") is not False:
        issues.append("dynamic_execution_overclaimed")
    if truth.get("actualZeroOneGpuRuntimeExecuted") is not False:
        issues.append("gpu_execution_overclaimed")
    if truth.get("actualZeroOneMobileRuntimeExecuted") is not False:
        issues.append("mobile_execution_overclaimed")
    return issues


def render_status_summary(model: dict[str, Any]) -> str:
    counts = model["coverage"]["counts"]
    phase_lines = "\n".join(
        f"- Phase {int(index)}: `{model['phases'][index]}`" for index in sorted(model["phases"])
    )
    gate_lines = "\n".join(
        f"- {name}: global `{record['globalStatus']}`, scoped `{record['scopedStatus']}`"
        for name, record in sorted(model["gates"].items())
    )
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
        "## Scoped Gates\n\n"
        f"{gate_lines}\n\n"
        "Compute profile, data provenance, execution profile, and gate scope are independent "
        "axes. PR #23 is historical local static evidence only. C3-Binding-D0 and "
        "PHY1-SingleLayer-D0 are separate gates; no dynamic, GPU, mobile, private-user, or "
        "human-review execution is claimed.\n"
    )
