from __future__ import annotations

import json
import subprocess
from pathlib import Path

from closy_forge.blueprint.ancestry import validate_ancestry_metadata
from closy_forge.blueprint.pr_dag import validate_pr_dag
from closy_forge.blueprint.profiles import (
    validate_execution_budget,
    validate_threshold_registry,
)
from closy_forge.blueprint.status import (
    build_status_model,
    render_status_summary,
    validate_status_model,
)
from closy_forge.security.evidence_hygiene import scan_evidence_files

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS = REPO_ROOT / "closy-forge" / "docs"
STATUS_VOCABULARY = {
    "not_started",
    "scaffold",
    "partial",
    "implemented_unverified",
    "complete",
    "discovery_pending",
    "blocked_external",
    "not_applicable",
}
IMPLEMENTED_STATUSES = {"scaffold", "partial", "implemented_unverified", "complete"}


def _json(name: str) -> dict:
    return json.loads((DOCS / name).read_text(encoding="utf-8"))


def test_coverage_rows_are_unique_structured_and_truthfully_scoped() -> None:
    coverage = _json("blueprint_coverage.json")
    rows = coverage["rows"]
    ids = [row["id"] for row in rows]

    assert coverage["version"] == "closy.blueprint_coverage.z1_z2_structured_ai.v6"
    assert set(coverage["statusVocabulary"]) == STATUS_VOCABULARY
    assert len(rows) == 101
    assert len(ids) == len(set(ids))
    for row in rows:
        assert row["status"] in STATUS_VOCABULARY
        assert row["sourceSection"]
        assert row["summary"]
        assert row["limitations"]
        assert row["nextAction"]
        assert row["ancestryClass"] in {
            "in_tree",
            "external_source_pr",
            "historical_superseded",
            "not_present",
        }
        assert row["evidenceSources"]
        assert row["evidenceTier"]
        if row["status"] in IMPLEMENTED_STATUSES:
            assert row["implementationPaths"], row["id"]
            assert row["executableEvidence"], row["id"]
            assert row["tests"], row["id"]
            assert row["commitSha"], row["id"]
        else:
            assert row["implementationPaths"] is None, row["id"]
            assert row["executableEvidence"] is None, row["id"]
            assert row["tests"] is None, row["id"]
            assert row["commitSha"] is None, row["id"]
    assert validate_ancestry_metadata(coverage) == []
    assert coverage["integratedImplementationRowCount"] == sum(
        row["ancestryClass"] == "in_tree" for row in rows
    )
    assert coverage["externalSourceRowCount"] == 5


def test_coverage_in_tree_ancestry_is_real_and_external_sources_are_not_counted() -> None:
    coverage = _json("blueprint_coverage.json")
    authority = coverage["ancestryAuthority"]["headSha"]

    for row in coverage["rows"]:
        if row["ancestryClass"] == "in_tree":
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", row["incorporationCommit"], authority],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
            )
        if row["ancestryClass"] == "external_source_pr":
            assert row["incorporated"] is False
            assert row["incorporationCommit"] is None
    phase9 = next(row for row in coverage["rows"] if row["id"] == "BP-17-PHASE-09")
    assert phase9["sourcePr"] == 35
    assert phase9["ancestryClass"] == "in_tree"
    assert "E2" in phase9["summary"]
    for phase, source_pr in (("12", 29), ("13", 30)):
        row = next(row for row in coverage["rows"] if row["id"] == f"BP-17-PHASE-{phase}")
        assert row["sourcePr"] == source_pr
        assert row["incorporated"] is False
    phase14 = next(row for row in coverage["rows"] if row["id"] == "BP-17-PHASE-14")
    assert phase14["sourcePr"] == 35
    assert phase14["incorporated"] is True


def test_coverage_commit_references_resolve_without_asserting_specific_shas() -> None:
    coverage = _json("blueprint_coverage.json")
    refs = {ref for row in coverage["rows"] for ref in (row["commitSha"] or [])}

    for ref in sorted(refs):
        subprocess.run(
            ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )


def test_canonical_status_is_recomputed_from_coverage_and_stack() -> None:
    coverage = _json("blueprint_coverage.json")
    stack = _json("pr_stack_manifest.json")
    status = _json("current_blueprint_status.json")

    assert validate_status_model(status, coverage, stack) == []
    assert status == build_status_model(
        coverage, stack, evidence_anchor_sha=status["evidenceAnchorSha"]
    )
    counts: dict[str, int] = {}
    for row in coverage["rows"]:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    assert status["coverage"]["counts"] == dict(sorted(counts.items()))
    assert status["coverage"]["total"] == len(coverage["rows"])


def test_phase_gate_and_maturity_statuses_are_not_inflated() -> None:
    status = _json("current_blueprint_status.json")

    assert status["phases"]["00"] == "complete"
    assert set(status["phases"][f"{index:02d}"] for index in range(1, 15)) == {"partial"}
    assert status["gates"]["C1"]["scopedStatus"] == "pass"
    assert status["gates"]["C2"]["scopedStatus"] == "pass"
    assert status["gates"]["C3-Binding-D0"]["scopedStatus"] == "pass"
    assert status["gates"]["PHY1-SingleLayer-D0"]["scopedStatus"] == "failed"
    assert status["gates"]["Z1"]["globalStatus"] == "partial"
    assert status["gates"]["Z1"]["scopedStatus"] == (
        "candidate_default_all_family_and_representative_pass"
    )
    assert status["gates"]["Z1"]["allFamilyAttemptCount"] == 9
    assert status["gates"]["Z1"]["successfulFamilyCount"] == 9
    assert status["gates"]["Z1"]["rejectedFamilyCount"] == 0
    assert status["gates"]["Z1"]["currentMasterRequalified"] is False
    assert status["gates"]["Z2"]["scopedStatus"] == ("failed_compiled_single_lod_reference_pairing")
    assert status["gates"]["P1"]["scopedStatus"] == "not_run"
    assert {status["gates"][f"Z{index}"]["scopedStatus"] for index in range(3, 9)} == {"not_run"}
    assert status["maturity"] == {
        "ALPHA": "not_started",
        "BETA": "not_started",
        "PRODUCTION": "not_started",
        "RESEARCH-PROTOTYPE": "partial",
    }
    assert status["truth"] == {
        "actualPhase9TrainingExecuted": True,
        "currentRasterPhase9SourceIntegrated": True,
        "currentRasterPhase9SourcePullRequest": 26,
        "phase12SourceIntegrated": False,
        "phase13SourceIntegrated": False,
        "phase14SourceIntegrated": True,
        "phase9E1Status": "partial_experimental",
        "phase9E2Status": "executed_feasibility_partial",
        "actualZeroOneStaticCookExecutedThisInvocation": True,
        "actualZeroOneStaticArtifactLoaded": True,
        "zeroOneStaticFamilyAttemptCount": 9,
        "zeroOneStaticSuccessfulFamilyCount": 9,
        "zeroOneStaticRejectedFamilyCount": 0,
        "cacheValidated": True,
        "historicalZeroOneStaticCookEvidencePresent": True,
        "actualZeroOneDynamicDeformationExecuted": True,
        "actualZeroOneDynamicPairingAccepted": False,
        "actualZeroOneGpuRuntimeExecuted": False,
        "actualZeroOneMobileRuntimeExecuted": False,
        "humanReviewRun": False,
        "phase8EvidenceScope": "deterministic_fixture_family_verticals",
        "phases10To14EvidenceScope": (
            "default_all_family_static_pass_parameter_range_partial_compiled_phase11_"
            "pairing_failed_phase12_13_external_phase14_integrated_advisory"
        ),
        "physicalMobileEvidenceRun": False,
        "privateUserEvidenceRun": False,
    }


def test_pr_stack_manifest_is_an_explicit_validated_dag() -> None:
    stack = _json("pr_stack_manifest.json")
    rows = stack["pullRequests"]
    nodes = stack["nodes"]
    assert validate_pr_dag(stack) == []
    assert stack["schemaVersion"] == 3
    assert stack["topology"] == "explicit_dag"
    numbers = [int(row["number"]) for row in rows]
    assert numbers == list(range(1, 36))
    assert len(nodes) == 37
    assert stack["externalPullRequests"][0]["repository"] == "jake-the-jake/ZeroOne"
    assert stack["externalPullRequests"][0]["number"] == 2
    assert stack["externalPullRequests"][1]["number"] == 3
    assert "sequentialMergeOrder" not in stack
    topological_position = {
        node_id: index for index, node_id in enumerate(stack["topologicalOrder"])
    }
    assert set(topological_position) == {node["id"] for node in nodes}
    assert all(
        topological_position[edge["from"]] < topological_position[edge["to"]]
        for edge in stack["edges"]
    )
    for row in rows:
        assert row["draft"] is True
        assert row["mergeability"] == "MERGEABLE"
        assert row["directParentMergeBaseVerified"] is True
        assert row["layerBehind"] == 0
        assert row["layerCommitCount"] == row["layerAhead"]
        merge_base = subprocess.run(
            ["git", "merge-base", row["baseSha"], row["headSha"]],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert merge_base == row["baseSha"]
        if row["number"] == 10:
            assert row["latestExactHeadForgeRun"] is None
            assert row["knownException"]["code"] == "missing_exact_head_forge_run"
            assert row["knownException"]["descendantEvidenceIsExactHead"] is False
        else:
            run = row["latestExactHeadForgeRun"]
            assert run["exactHead"] is True
            assert run["runId"]
            if row["number"] in {25, 35}:
                assert run["conclusion"] == "FAILURE"
            elif "conclusion" in run:
                assert run["conclusion"] == "SUCCESS"
            else:
                assert {job["conclusion"] for job in run["jobs"]} == {"SUCCESS"}
        layer_commits = subprocess.run(
            ["git", "rev-list", f'{row["baseSha"]}..{row["headSha"]}'],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        assert len(layer_commits) == row["layerCommitCount"]
    by_id = {node["id"]: node for node in nodes}
    assert by_id["github:jake-the-jake/Closy:pr/28"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/27"
    ]
    assert (
        "github:jake-the-jake/Closy:pr/25"
        in by_id["github:jake-the-jake/Closy:pr/28"]["dependencyIds"]
    )
    assert len(by_id["github:jake-the-jake/Closy:pr/28"]["integrationMappings"]) == 8
    assert by_id["github:jake-the-jake/Closy:pr/25"]["superseded"] is True
    for number in (26, 29, 30, 31, 32, 34):
        node = by_id[f"github:jake-the-jake/Closy:pr/{number}"]
        assert node["sourceOnly"] is True
        assert node["mergeEligible"] is False
    assert by_id["github:jake-the-jake/ZeroOne:pr/2"]["headSha"] == (
        "13a844d240f4bbb2cafde105c4a0bdca8d89a06b"
    )
    assert by_id["github:jake-the-jake/ZeroOne:pr/3"]["headSha"] == (
        "413aecd24434f90d89ad35c6a8f909de75df34c7"
    )
    assert by_id["github:jake-the-jake/Closy:pr/34"]["sourceOnly"] is True
    assert len(by_id["github:jake-the-jake/Closy:pr/35"]["integrationMappings"]) == 6


def test_execution_budgets_and_precommitted_thresholds_are_complete() -> None:
    budget = _json("execution_budget_v3.json")
    thresholds = _json("threshold_registry_v1.json")

    assert validate_execution_budget(budget) == []
    assert validate_threshold_registry(thresholds) == []
    assert budget["policy"]["publishedCandidateHeadLimitPerNewPr"] == 3
    assert thresholds["thresholdMutationPolicy"] == (
        "immutable_after_heldout_execution_version_new_profile_instead"
    )


def test_phy1_sanitised_failure_witness_is_exact_and_not_promoted() -> None:
    witness = _json("evidence/phy1_progression_v3/sanitised_failure_witness.json")

    assert witness["source"]["headSha"] == "d393b7185d14fe414a1eb3c4ef040c6c1ad8f780"
    assert witness["source"]["fullTemporalOracleSha256"] == (
        "f86f819a32a41213a78050d7d81eda6af3b4c1ffb3bd3fa9541796082422f80c"
    )
    assert witness["measured"]["physicalStatePassCount"] == 0
    assert witness["measured"]["qualifiedTemporalCounts"] == {
        "degenerateFrameTriangles": 198,
        "nonfiniteFrameTriangles": 0,
        "sweptDegenerateTransitions": 191,
        "trueInversions": 15,
    }
    assert witness["acceptance"]["status"] == "failed"
    assert witness["acceptance"]["globalPhy1Complete"] is False
    assert witness["source"]["dedicatedPullRequestPublished"] is False


def test_generated_reports_use_source_tree_hash_not_self_referential_commit() -> None:
    coverage = _json("blueprint_coverage.json")
    provenance = coverage["generatedBy"]

    assert provenance["generatorVersion"] == (
        "closy.blueprint_reconciliation.z1_z2_structured_ai.v3"
    )
    assert len(provenance["sourceTreeHash"]) == 64
    assert provenance["selfReferentialCommitSha"] is False
    assert provenance["finalHeadAttestationLocation"] == (
        "external_exact_head_ci_check_or_draft_pr_body"
    )


def test_generated_markdown_is_exact_render_of_machine_status() -> None:
    status = _json("current_blueprint_status.json")
    summary = (DOCS / "BLUEPRINT_STATUS_SUMMARY.md").read_text(encoding="utf-8")

    assert summary == render_status_summary(status)
    assert "C3-Binding-D0 passes only for its fixed-avatar D0 T-shirt profile" in summary
    assert "Compiled dynamic ZeroOne execution ran" in summary


def test_phase11_prerequisite_reconciliation_is_exact_and_fail_closed() -> None:
    evidence = _json("evidence/phase11_prerequisite_reconciliation_v2.json")
    base_sha = "2a4fcd8146d95d2fab9a3d39751ffdafd5196387"
    source_head = "f9f1ff86089f6b43157431bdd3ccdc83cbc8b974"
    implementation_head = "f64c4ff2225141aa3fa04405e77fef0af360e050"

    assert evidence["base"]["sha"] == base_sha
    assert evidence["source"]["headSha"] == source_head
    assert evidence["destination"]["implementationHeadSha"] == implementation_head
    assert evidence["destination"]["directParentMergeBase"] == base_sha
    assert evidence["destination"]["behindParentCommitCount"] == 0
    assert len(evidence["mappings"]) == 8

    merge_base = subprocess.run(
        ["git", "merge-base", base_sha, implementation_head],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert merge_base == base_sha

    replayed_count = subprocess.run(
        ["git", "rev-list", "--count", f"{base_sha}..{implementation_head}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert replayed_count == "8"

    for mapping in evidence["mappings"]:
        for commit in (mapping["source"], mapping["destination"]):
            subprocess.run(
                ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
            )

    assert evidence["gates"] == {
        "C3-Binding-D0": "pass",
        "PHY1-SingleLayer-D0": "fail",
        "refreshedPairedScopedZ1": "fail",
        "mechanicalReferencePhase11Eligible": False,
        "solverDrivenPhysicalPhase11Eligible": False,
        "Z2Executed": False,
    }
    assert evidence["decision"] == "phase11_blocked_by_refreshed_paired_scoped_z1"


def test_next_actions_do_not_point_to_already_completed_stack_steps() -> None:
    coverage = _json("blueprint_coverage.json")
    next_actions = "\n".join(str(row["nextAction"]) for row in coverage["rows"])

    for stale in (
        "Proceed to BP-51",
        "Push and remote-validate the Phase 6",
        "Remote-validate the Phase 7",
        "apply the shared material contract to the sleeveless",
        "Phase 9 is next",
    ):
        assert stale not in next_actions


def test_human_ledgers_are_not_machine_readiness_authorities() -> None:
    status = _json("current_blueprint_status.json")
    stack = _json("pr_stack_manifest.json")
    coverage = _json("blueprint_coverage.json")

    assert validate_status_model(status, coverage, stack) == []


def test_generated_evidence_and_changed_status_documents_are_path_and_secret_safe() -> None:
    paths = [
        DOCS / "ACTIVE_BLUEPRINT_RESUME.md",
        DOCS / "BLUEPRINT_STATUS_SUMMARY.md",
        DOCS / "MASTER_BLUEPRINT_PROGRESS.md",
        DOCS / "blueprint_coverage.json",
        DOCS / "current_blueprint_status.json",
        DOCS / "execution_budget_v2.json",
        DOCS / "execution_budget_v3.json",
        DOCS / "evidence_integrity_audit_v2.md",
        DOCS / "pr_stack_manifest.json",
        DOCS / "threshold_registry_v1.json",
        DOCS / "zeroone-static-integration-v1.md",
        *sorted((DOCS / "evidence").rglob("*.json")),
        *sorted((DOCS / "evidence").rglob("*.md")),
    ]

    assert scan_evidence_files(paths) == {}
