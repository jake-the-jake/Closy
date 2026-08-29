from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

STATUS_MODEL_VERSION = "closy.blueprint_status_model.v3"
PHASE_IDS = tuple(f"BP-17-PHASE-{index:02d}" for index in range(15))
MATURITY_IDS = (
    "BP-20-RESEARCH-PROTOTYPE",
    "BP-20-ALPHA",
    "BP-20-BETA",
    "BP-20-PRODUCTION",
)
A1_HEAD = "5d080caad354bcecff94a7eadf16d080d68a606c"
C3_EVIDENCE_SHA = "5538d8ca41ad86412d2a2ef5f0a0daa9984c0b72"
ZEROONE_CANDIDATE_SHA = "13a844d240f4bbb2cafde105c4a0bdca8d89a06b"
ZEROONE_EXECUTABLE_SHA256 = "59bb051455ae2878a30edd353bdb451271107bb5df3e3570b89b955379cf2065"

_COMMON_UNSUPPORTED = ["D1", "D2", "D3", "GPU", "mobile", "private_user"]
GATE_RECORDS: dict[str, dict[str, Any]] = {
    "C1": {
        "gateId": "C1",
        "globalStatus": "partial",
        "scopedStatus": "pass",
        "evidenceTier": "committed_deterministic_fixture_reports",
        "platform": ["ubuntu", "windows"],
        "toolchain": ["CPython 3.11", "CPython 3.12"],
        "sourceSha": A1_HEAD,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU",
        "gateScope": "capture_contract",
        "evidenceDurability": "committed_reports_plus_exact_head_ci",
        "workflowRun": "33183367784",
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
        "sourceSha": A1_HEAD,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU",
        "gateScope": "canonical_generation_contract",
        "evidenceDurability": "committed_reports_plus_exact_head_ci",
        "workflowRun": "33183367784",
        "unsupportedTiers": _COMMON_UNSUPPORTED,
        "blockers": ["independent_provider_breadth", "human_visual_review"],
    },
    "C3-Binding-D0": {
        "gateId": "C3-Binding-D0",
        "globalStatus": "partial",
        "scopedStatus": "pass",
        "evidenceTier": "committed_executed_candidate_profile",
        "platform": ["windows"],
        "toolchain": ["CPython 3.11"],
        "sourceSha": C3_EVIDENCE_SHA,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU",
        "gateScope": "binding",
        "evidenceDurability": "committed_report_plus_external_exact_head_check_attestation",
        "workflowRun": None,
        "unsupportedTiers": _COMMON_UNSUPPORTED,
        "blockers": ["broader_avatar_garment_platform_and_private_user_profiles"],
    },
    "PHY1-SingleLayer-D0": {
        "gateId": "PHY1-SingleLayer-D0",
        "globalStatus": "partial",
        "scopedStatus": "failed",
        "evidenceTier": "committed_failure_witnesses",
        "platform": ["windows"],
        "toolchain": ["CPython 3.11"],
        "sourceSha": C3_EVIDENCE_SHA,
        "executableSha": None,
        "garmentFamilies": ["tshirt"],
        "avatarProfile": "fixed_reference_avatar_v1",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU",
        "gateScope": "physical",
        "evidenceDurability": "committed_failure_reports",
        "workflowRun": None,
        "unsupportedTiers": _COMMON_UNSUPPORTED + ["multilayer"],
        "blockers": [
            "timestamped_states_passed_0_of_11",
            "unresolved_contacts_9",
            "residual_depth_0.001878992_exceeds_0.000160000",
            "minimum_body_clearance_negative_0.009084014",
            "maximum_seam_crack_0.109609688",
            "rest_referenced_inversions_or_degeneracies_68",
        ],
    },
    "Z1": {
        "gateId": "Z1",
        "globalStatus": "partial",
        "scopedStatus": "candidate_default_all_family_and_representative_pass",
        "historicalProfileStatus": "pass",
        "candidateAllFamilyStatus": "pass",
        "representativeStaticStatus": "pass",
        "originalDeclaredParameterRangeStatus": "partial",
        "currentMasterRequalified": False,
        "phase10Status": "partial",
        "evidenceTier": "durable_candidate_binary_plus_committed_all_family_reports",
        "platform": ["windows"],
        "toolchain": ["MSVC 19.36 Release"],
        "sourceSha": ZEROONE_CANDIDATE_SHA,
        "currentMasterSha": None,
        "executableSha": ZEROONE_EXECUTABLE_SHA256,
        "garmentFamilies": [
            "tshirt",
            "sleeveless_top",
            "long_sleeved_top",
            "simple_skirt",
            "simple_trousers",
            "simple_dress",
            "button_shirt",
            "jacket_outerwear",
            "layered_asymmetric",
        ],
        "avatarProfile": "not_applicable_static_cook",
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionKind": "CPU/headless/static",
        "gateScope": "static ZeroOne",
        "evidenceDurability": "durable_zeroone_build_artifact_plus_local_paired_reports",
        "workflowRun": "33187775880",
        "allFamilyAttemptCount": 9,
        "successfulFamilyCount": 9,
        "rejectedFamilyCount": 0,
        "unsupportedTiers": ["current_master", "GPU", "mobile", "dynamic", "human_review"],
        "blockers": [
            "original_declared_parameter_range_partial",
            "candidate_static_not_merged_to_master",
            "paired_closy_workflow_not_durable",
            "human_visual_review_not_performed",
        ],
    },
    "Z2": {
        "gateId": "Z2",
        "globalStatus": "discovery_pending",
        "scopedStatus": "not_run",
        "evidenceTier": "none",
        "platform": [],
        "toolchain": [],
        "sourceSha": ZEROONE_CANDIDATE_SHA,
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
        "blockers": [
            "compiled_dynamic_execution",
        ],
    },
    "P1": {
        "gateId": "P1",
        "globalStatus": "discovery_pending",
        "scopedStatus": "not_run",
        "evidenceTier": "none",
        "platform": [],
        "toolchain": [],
        "sourceSha": A1_HEAD,
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
                    "sourceSha": ZEROONE_CANDIDATE_SHA,
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
        "schemaVersion": 3,
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
            "pullRequestCount": len(stack["pullRequests"]),
            "crossRepositoryNodeCount": len(stack["nodes"]),
            "latestPullRequest": max(
                int(row["pullRequest"])
                for row in stack["nodes"]
                if row["repository"] == "jake-the-jake/Closy"
            ),
            "topology": "explicit_dag",
            "acyclic": bool(stack["validation"]["acyclic"]),
            "exactMergeBases": bool(stack["validation"]["exactMergeBases"]),
            "businessPatchMappingsComplete": bool(
                stack["validation"]["businessPatchMappingsComplete"]
            ),
            "exactHeadForgeExceptions": [
                int(row["pullRequest"])
                for row in stack["nodes"]
                if row["repository"] == "jake-the-jake/Closy"
                and not row["latestExactHeadWorkflows"]
            ],
        },
        "truth": {
            "phase8EvidenceScope": "deterministic_fixture_family_verticals",
            "phases10To14EvidenceScope": (
                "candidate_default_all_family_static_pass_parameter_range_partial_"
                "phase11_not_run_phase12_to14_external_sources"
            ),
            "actualZeroOneStaticCookExecutedThisInvocation": True,
            "actualZeroOneStaticArtifactLoaded": True,
            "zeroOneStaticFamilyAttemptCount": 9,
            "zeroOneStaticSuccessfulFamilyCount": 9,
            "zeroOneStaticRejectedFamilyCount": 0,
            "cacheValidated": True,
            "historicalZeroOneStaticCookEvidencePresent": True,
            "actualZeroOneDynamicDeformationExecuted": False,
            "actualZeroOneGpuRuntimeExecuted": False,
            "actualZeroOneMobileRuntimeExecuted": False,
            "actualPhase9TrainingExecuted": True,
            "currentRasterPhase9SourceIntegrated": False,
            "currentRasterPhase9SourcePullRequest": 26,
            "phase12To14SourceBranchesIntegrated": False,
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
    if 10 not in model.get("stack", {}).get("exactHeadForgeExceptions", []):
        issues.append("stack_exception_set_invalid")
    z1 = model.get("gates", {}).get("Z1", {})
    if z1.get("globalStatus") != "partial" or z1.get("scopedStatus") != (
        "candidate_default_all_family_and_representative_pass"
    ):
        issues.append("zeroone_z1_scope_inflated")
    truth = model.get("truth", {})
    if truth.get("actualZeroOneStaticCookExecutedThisInvocation") is not True:
        issues.append("status_reconciliation_missing_candidate_static_cook")
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
        "axes. C3-Binding-D0 passes only for its fixed-avatar D0 T-shirt profile; "
        "PHY1-SingleLayer-D0 and refreshed paired Z1 fail their declared scopes. No dynamic, "
        "GPU, mobile, private-user, or human-review execution is claimed.\n"
    )
