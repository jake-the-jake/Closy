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

    assert coverage["version"] == ("closy.blueprint_coverage.evidence_authority_recovery_v2.v21")
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
    assert coverage["externalSourceRowCount"] == 0


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
    assert phase9["sourcePr"] == 38
    assert phase9["ancestryClass"] == "in_tree"
    assert "E2" in phase9["summary"]
    assert 37 in {source["sourcePr"] for source in phase9["evidenceSources"]}
    for phase, historical_pr in (("12", 29), ("13", 30)):
        row = next(row for row in coverage["rows"] if row["id"] == f"BP-17-PHASE-{phase}")
        assert row["sourcePr"] == 38
        assert row["incorporated"] is True
        assert historical_pr in {source["sourcePr"] for source in row["evidenceSources"]}
    phase14 = next(row for row in coverage["rows"] if row["id"] == "BP-17-PHASE-14")
    assert phase14["sourcePr"] == 38
    assert phase14["incorporated"] is True
    assert 37 in {source["sourcePr"] for source in phase14["evidenceSources"]}


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
    assert status["gates"]["PHY1-SingleLayer-D0-v2"]["scopedStatus"] == "failed"
    assert status["gates"]["PHY1-SingleLayer-D0-v2"]["statePassCount"] == 0
    assert status["gates"]["PHY1-SingleLayer-D0-v2"]["runtimeCapabilityExposed"] is False
    topology_strategy = status["gates"]["PHY1-Topology-Strategy2-D0-v4"]
    assert topology_strategy["outcomeClass"] == "M"
    assert topology_strategy["candidateOpened"] is False
    assert topology_strategy["solverStepAdvanced"] is False
    assert topology_strategy["candidateAttemptConsumed"] is False
    assert topology_strategy["unitJAuthorized"] is False
    assert topology_strategy["unitKEligible"] is False
    strategy3_diagnosis = status["gates"]["PHY1-Topology-Strategy3-Diagnosis-D0-v1"]
    assert strategy3_diagnosis["scopedStatus"] == "diagnosis_integrity_error"
    assert strategy3_diagnosis["revisionFixturePassCounts"] == [7, 7]
    assert strategy3_diagnosis["admittedStrategyClass"] is None
    assert strategy3_diagnosis["candidateCreated"] is False
    assert strategy3_diagnosis["candidateAttemptConsumed"] is False
    assert strategy3_diagnosis["finalStrategyConsumed"] is False
    assert strategy3_diagnosis["unitPEligible"] is False
    assert status["gates"]["PHY1-SingleLayer-D0-v2"]["dRuntimePinnedToV1"] is True
    assert status["gates"]["PHY1-Neutral-SeamSupport-D0-v3"]["scopedStatus"] == "failed"
    assert status["gates"]["PHY1-Neutral-SeamSupport-D0-v3"]["outcomeClass"] == (
        "A_neutral_preflight_failed_v3"
    )
    assert status["gates"]["ResearchPrototype-D0-matrix-v2"]["scopedStatus"].startswith(
        "historical_superseded"
    )
    assert status["gates"]["ResearchPrototype-D0-matrix-v3-core"]["scopedStatus"] == (
        "partial_7_pass_4_fail_0_not_run"
    )
    assert status["gates"]["ResearchPrototype-D0-matrix-v3-supplemental"]["scopedStatus"] == (
        "2_pass_0_fail_2_not_run"
    )
    assert status["gates"]["TextureRerender-KnownTarget-v3"]["scopedStatus"] == (
        "known_target_regression_pass_not_qualification"
    )
    assert status["gates"]["TextureRerender-KnownTarget-v3"]["d0Rp07Promoted"] is False
    assert status["gates"]["MT1-MechanicalReference-D0"]["scopedStatus"] == "pass"
    assert status["gates"]["LayerCollision-D0"]["scopedStatus"] == "pass"
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
        "phase12SourceIntegrated": True,
        "phase13SourceIntegrated": True,
        "phase14SourceIntegrated": True,
        "layerCollisionSurfaceIntegrated": True,
        "mt1ReferenceMotionD0Available": True,
        "phy1TopologyV2ExperimentExecuted": True,
        "phy1TopologyV2Passed": False,
        "phy1TopologyV2RuntimeExposed": False,
        "phy1SeamSupportV3NeutralExecuted": True,
        "phy1SeamSupportV3Outcome": "A_neutral_preflight_failed_v3",
        "phy1SeamSupportV3TrajectoryBytesPreserved": True,
        "phy1SeamSupportV3FullSuiteExecuted": False,
        "phy1SeamSupportV3CcdExecuted": False,
        "phy1SeamSupportV3Z2Executed": False,
        "phy1TopologyStrategy2V4Executed": True,
        "phy1TopologyStrategy2V4Outcome": "M_strategy_microfixture_failed_no_candidate",
        "phy1TopologyStrategy2CandidateOpened": False,
        "phy1TopologyStrategy2SolverStepAdvanced": False,
        "phy1TopologyStrategy2CandidateAttemptConsumed": False,
        "phy1TopologyStrategy2RemainingTopologyStrategies": 1,
        "phy1TopologyStrategy2RemainingSeamModels": 0,
        "phy1TopologyStrategy3DiagnosisExecuted": True,
        "phy1TopologyStrategy3DiagnosisOutcome": ("diagnosis_integrity_error"),
        "phy1TopologyStrategy3DiagnosisRevisionCount": 2,
        "phy1TopologyStrategy3AdmittedClass": None,
        "phy1TopologyStrategy3CandidateCreated": False,
        "phy1TopologyStrategy3CandidateAttemptConsumed": False,
        "phy1TopologyStrategy3FinalStrategyConsumed": False,
        "phy1TopologyStrategy3RemainingTopologyStrategies": 1,
        "unitPEligible": False,
        "unitQEligible": False,
        "unitREligible": False,
        "unitJLogicalOutcome": "J-A_post_topology_candidate_unavailable",
        "unitJBranchAuthorized": False,
        "unitKEligible": False,
        "integratedRuntimePinnedToTopologyV1": True,
        "historicalD0ResearchMatrixStatus": "partial_superseded",
        "historicalD0ResearchMatrixVersion": "closy.final_d0_research_prototype_matrix.v2",
        "historicalD0ResearchMatrixStatusCounts": {"pass": 9, "fail": 3, "not_run": 3},
        "historicalD0ResearchMatrixFirstUnmetPredicate": "D0-RP-07",
        "currentD0ResearchMatrixStatus": "partial",
        "currentD0ResearchMatrixVersion": "closy.final_d0_research_matrix.v3",
        "currentD0ResearchMatrixCoreStatusCounts": {"pass": 7, "fail": 4, "not_run": 0},
        "currentD0ResearchMatrixSupplementalStatusCounts": {
            "pass": 2,
            "fail": 0,
            "not_run": 2,
        },
        "currentD0ResearchMatrixFirstUnmetPredicate": "D0-RP-03",
        "knownTargetTextureRegressionExecuted": True,
        "knownTargetTextureRegressionOutcome": "known_target_regression_pass",
        "knownTargetTextureRegressionTrialCount": 1,
        "knownTargetTextureRegressionPromotedD0Rp07": False,
        "identityDisjointV2AuthorityExecuted": True,
        "identityDisjointV2Outcome": "attempted_integrity_error",
        "identityDisjointV2AcceptedIdentityCount": 16,
        "identityDisjointV2PredictionCount": 0,
        "identityDisjointV2QualificationRetryAllowed": False,
        "dependencyIdentityGraphAvailable": True,
        "runtimeCandidateV2Available": True,
        "runtimeCandidateV2ProductSelected": False,
        "runtimeCandidateV2FallbackIsCanonicalGarment": True,
        "runtimeCandidateV2DescriptorPayloadCapability": False,
        "boundedRuntimeAndRasterDecompression": True,
        "packageValidityDependsOnZeroOne": False,
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
        "evidenceAuthorityRecoveryV2Executed": True,
        "evidenceAuthorityRecoveryV2Outcome": "pass",
        "evidenceAuthorityRecoveryV2ScientificAttemptCreated": False,
        "phase8EvidenceScope": "deterministic_fixture_family_verticals",
        "phases10To14EvidenceScope": (
            "default_all_family_static_pass_parameter_range_partial_compiled_phase11_"
            "pairing_failed_mt1_mechanical_pass_phase12_13_integrated_headless_"
            "phase14_integrated_advisory"
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
    assert numbers == list(range(1, 54))
    assert stack["graphCounts"] == {
        "closyPullRequests": len(rows),
        "externalPullRequests": len(stack["externalPullRequests"]),
        "nodes": len(nodes),
        "edges": len(stack["edges"]),
    }
    assert stack["externalPullRequests"][0]["repository"] == "jake-the-jake/ZeroOne"
    assert stack["externalPullRequests"][0]["number"] == 2
    assert stack["externalPullRequests"][1]["number"] == 3
    assert stack["externalPullRequests"][2]["number"] == 4
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
        if row["number"] in {10, 52, 53}:
            assert row["latestExactHeadForgeRun"] is None
            assert row["knownException"]["code"] in {
                "missing_exact_head_forge_run",
                "exact_head_ci_recorded_outside_generated_evidence",
            }
            assert row["knownException"]["descendantEvidenceIsExactHead"] is False
        else:
            run = row["latestExactHeadForgeRun"]
            assert run["exactHead"] is True
            assert run["runId"]
            if row["number"] == 25:
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
    assert by_id["github:jake-the-jake/ZeroOne:pr/4"]["headSha"] == (
        "9cbae4a8e6ef2e61c1839ecbdf8a462aaa560027"
    )
    assert by_id["github:jake-the-jake/ZeroOne:pr/4"]["parentIds"] == [
        "github:jake-the-jake/ZeroOne:pr/3"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/34"]["sourceOnly"] is True
    assert len(by_id["github:jake-the-jake/Closy:pr/35"]["integrationMappings"]) == 6
    assert by_id["github:jake-the-jake/Closy:pr/38"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/36"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/39"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/38"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/40"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/39"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/41"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/40"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/42"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/41"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/43"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/42"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/44"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/43"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/44"]["headSha"] == (
        "2f40815010cef01685a7ed873081a22f11d67c00"
    )
    assert (
        by_id["github:jake-the-jake/Closy:pr/44"]["latestExactHeadWorkflows"][0]["runId"]
        == "33452856012"
    )
    assert by_id["github:jake-the-jake/Closy:pr/45"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/44"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/45"]["headSha"] == (
        "ba54b17a0aef7518d9acac30c6b7ec6564a38d87"
    )
    assert (
        by_id["github:jake-the-jake/Closy:pr/45"]["latestExactHeadWorkflows"][0]["runId"]
        == "33464425080"
    )
    assert by_id["github:jake-the-jake/Closy:pr/46"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/45"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/46"]["headSha"] == (
        "bc4927fe6d36667b5b236d844b4eff511ef6f987"
    )
    assert (
        by_id["github:jake-the-jake/Closy:pr/46"]["latestExactHeadWorkflows"][0]["runId"]
        == "33503777760"
    )
    assert by_id["github:jake-the-jake/Closy:pr/47"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/46"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/47"]["headSha"] == (
        "e25da69d29eb1b68885b911c7354df085f4a22c0"
    )
    assert (
        by_id["github:jake-the-jake/Closy:pr/47"]["latestExactHeadWorkflows"][0]["runId"]
        == "33505903385"
    )
    assert by_id["github:jake-the-jake/Closy:pr/48"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/47"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/48"]["headSha"] == (
        "69f17e0bc0d01472eec3aaf244c158181f74febf"
    )
    assert (
        by_id["github:jake-the-jake/Closy:pr/48"]["latestExactHeadWorkflows"][0]["runId"]
        == "33511517533"
    )
    assert by_id["github:jake-the-jake/Closy:pr/49"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/48"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/49"]["headSha"] == (
        "a72f45955abbe65ce14b7142668447d0477db71c"
    )
    assert (
        by_id["github:jake-the-jake/Closy:pr/49"]["latestExactHeadWorkflows"][0]["runId"]
        == "33524394054"
    )
    assert by_id["github:jake-the-jake/Closy:pr/50"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/49"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/50"]["headSha"] == (
        "552867e96d53e9d4c728f90d12e0c1c9a344ba0d"
    )
    assert by_id["github:jake-the-jake/Closy:pr/51"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/50"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/51"]["headSha"] == (
        "e062a30ba295ed27334622916ddb449fd76e2166"
    )
    assert by_id["github:jake-the-jake/Closy:pr/52"]["parentIds"] == [
        "github:jake-the-jake/Closy:pr/51"
    ]
    assert by_id["github:jake-the-jake/Closy:pr/52"]["headSha"] == (
        "d8c8318ad346ea66ebc1956ebc0839ee3d6db109"
    )
    assert by_id["github:jake-the-jake/Closy:pr/52"]["latestExactHeadWorkflows"] == []
    assert (
        "github:jake-the-jake/Closy:pr/37"
        in (by_id["github:jake-the-jake/Closy:pr/38"]["dependencyIds"])
    )
    assert {
        workflow["workflow"]
        for workflow in by_id["github:jake-the-jake/Closy:pr/37"]["latestExactHeadWorkflows"]
    } == {
        "Closy Forge",
        "Closy Forge Phase 9 Structured v3",
    }
    assert {
        workflow["workflow"]
        for workflow in by_id["github:jake-the-jake/Closy:pr/38"]["latestExactHeadWorkflows"]
    } == {
        "Closy Forge",
        "Closy Forge Phase 9 Structured v3",
    }


def test_execution_budgets_and_precommitted_thresholds_are_complete() -> None:
    budget = _json("execution_budget_v3.json")
    thresholds = _json("threshold_registry_v1.json")

    assert validate_execution_budget(budget) == []
    assert validate_threshold_registry(thresholds) == []
    assert budget["policy"]["publishedCandidateHeadLimitPerNewPr"] == 3
    assert thresholds["thresholdMutationPolicy"] == (
        "immutable_after_heldout_execution_version_new_profile_instead"
    )
    phy1_v3 = next(lane for lane in budget["lanes"] if lane["laneId"] == "PHY1-SEAM-SUPPORT-V3")
    assert phy1_v3["outcome"] == "A_neutral_preflight_failed_v3"
    assert phy1_v3["consumption"]["seamModelsRemainingAfterV3"] == 0
    assert phy1_v3["consumption"]["topologyStrategiesRemainingAfterV3"] == 2
    assert phy1_v3["consumption"]["fullPhy1Executed"] is False
    strategy2 = next(
        lane for lane in budget["lanes"] if lane["laneId"] == "PHY1-TOPOLOGY-STRATEGY2-V4"
    )
    assert strategy2["outcome"] == "M_strategy_specific_microfixture_failed_logical_J_A"
    assert strategy2["consumption"]["candidateOpened"] is False
    assert strategy2["consumption"]["solverStepAdvanced"] is False
    assert strategy2["consumption"]["candidateAttemptConsumed"] is False
    assert strategy2["consumption"]["topologyStrategiesRemainingAfterUnitI"] == 1
    assert strategy2["consumption"]["unitJBranchAuthorized"] is False
    assert strategy2["consumption"]["unitKEligible"] is False


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
        "closy.blueprint_reconciliation.evidence_authority_recovery_v2.v18"
    )
    assert len(provenance["sourceTreeHash"]) == 64
    assert provenance["sourceTreeHashAlgorithm"] == ("sha256_path_nul_lf_normalized_content_nul_v2")
    assert provenance["selfReferentialCommitSha"] is False
    assert provenance["finalHeadAttestationLocation"] == (
        "external_exact_head_ci_check_or_draft_pr_body"
    )


def test_generated_markdown_is_exact_render_of_machine_status() -> None:
    status = _json("current_blueprint_status.json")
    summary = (DOCS / "BLUEPRINT_STATUS_SUMMARY.md").read_text(encoding="utf-8")

    assert summary == render_status_summary(status)
    assert "C3-Binding-D0 passes only for its fixed-avatar D0 T-shirt profile" in summary
    assert "Historical compiled dynamic ZeroOne pairing" in summary
    assert "topology-v2 experiment both fail" in summary


def test_active_machine_and_markdown_resumes_agree_on_unit_s_authority_boundary() -> None:
    resume = _json("ACTIVE_BLUEPRINT_RESUME.json")
    markdown = (DOCS / "ACTIVE_BLUEPRINT_RESUME.md").read_text(encoding="utf-8")

    assert resume["branch"] == "codex/closy-forge-evidence-authority-recovery-v2"
    assert resume["latestFinishedParentPublicationHead"] == (
        "8dd7a547debf038e9e27c48cf8e42009ae69ac3a"
    )
    assert resume["pendingCIAtEvidenceHead"] is True
    assert resume["evidenceHead"] in markdown
    assert str(resume["parent"]["sha"]) in markdown
    assert resume["gates"]["ResearchPrototype-D0-matrix-v2"].startswith("historical_superseded")
    assert resume["gates"]["ResearchPrototype-D0-matrix-v3-core"] == (
        "partial_7_pass_4_fail_0_not_run"
    )
    assert resume["gates"]["ResearchPrototype-D0-matrix-v3-supplemental"] == (
        "2_pass_0_fail_2_not_run"
    )
    assert resume["matrixScopes"]["identityDisjointV2"]["predictions"] == 0
    assert resume["matrixScopes"]["identityDisjointV2"]["predictionDenominator"] == 64
    assert resume["matrixScopes"]["identityDisjointV2"]["canonicalCompiles"] == 0
    assert resume["matrixScopes"]["postTopologyCandidate"]["candidateExists"] is False
    assert resume["unitMResult"]["outcome"] == "attempted_integrity_error"
    assert resume["unitMResult"]["qualificationRetryAllowed"] is False
    assert resume["unitNResult"]["outcome"] == "pass"
    assert resume["unitNResult"]["posePassCount"] == 8
    assert resume["unitOResult"]["outcome"] == "diagnosis_integrity_error"
    assert resume["unitOResult"]["rawOutcome"] == (
        "no_strategy3_class_admitted_within_bounded_diagnosis"
    )
    assert resume["unitOResult"]["replayPerformed"] is False
    assert resume["unitOResult"]["revisionCount"] == 2
    assert resume["unitOResult"]["admittedStrategyClass"] is None
    assert resume["unitOResult"]["candidateCreated"] is False
    assert resume["unitOResult"]["candidateAttemptConsumed"] is False
    assert resume["unitOResult"]["finalStrategyConsumed"] is False
    assert resume["unitOResult"]["unitPEligible"] is False
    assert resume["unitSResult"]["outcome"] == "pass"
    assert set(resume["unitSResult"]["subgates"]) == {
        "S-core-truth",
        "S-D0-authority",
        "S-PHY-authority",
    }
    assert all(row["result"] == "pass" for row in resume["unitSResult"]["subgates"].values())
    assert resume["remainingBudgets"] == {
        "candidateAttempts": 1,
        "seamModels": 0,
        "topologyStrategies": 1,
    }
    assert resume["conditionalUnits"] == {
        "T": "dependency_ready",
        "U": "dependency_ready_after_T",
        "V": "not_created_requires_unit_u_pass",
        "W": "not_created_requires_unit_v_candidate",
        "X": "not_created_requires_unit_w_core_prerequisites",
    }
    assert resume["nextHandoff"]["selection"] == "unit_t_d0_confirmation_v3"
    assert resume["nextHandoff"]["firstUnmetPrerequisite"] == "unit_t_protocol_lock"
    assert "7 pass / 4 fail" in markdown
    assert "S-D0-authority" in markdown
    assert "Create Unit T" in markdown


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
        DOCS / "ACTIVE_BLUEPRINT_RESUME.json",
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
