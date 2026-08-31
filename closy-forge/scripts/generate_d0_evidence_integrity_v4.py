from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.evidence_integrity_v4 import (
    append_attempt,
    audit_candidate_package,
    audit_raster_semantics_v4,
    evaluate_phy1_trajectory_diagnostic_v4,
    evaluate_research_matrix_v3,
)
from closy_forge.evidence_integrity_v4.matrix_v3 import (
    ATTEMPT_REGISTRY_VERSION,
    canonical_artifact_sha256,
    document_hash,
)
from closy_forge.evidence_integrity_v4.phy_evaluator_v4 import evaluate_phy_microfixtures_v4
from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_file

SOURCE_ANCHOR = "fe8f6d8a6d08e4c1b75a838728d66fea5d2c92c0"
PR43_HEAD = "6aee5ed3b2753ee99c95abdef6f5a24be39b3a7e"
OUTPUT = "docs/evidence/d0_evidence_integrity_v4"
PROFILE = "docs/capability-profiles/d0-research-matrix-v3.json"


def generate(root: Path) -> dict[str, Path]:
    output = root / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    contribution_output = output / "contribution"
    package = root / ("docs/evidence/d0_fitting_pbr_fidelity_v2/predictions/candidate_package")
    manifest = _object(package / "candidate_manifest.json")
    identity = _mapping(manifest["identityGraph"])
    source = _mapping(identity["source"])
    context = {
        "candidateId": str(manifest["candidateId"]),
        "packageDigest": str(manifest["packageDigest"]),
        "avatarContractHash": str(source["avatarContractHash"]),
        "garmentId": str(source["garmentId"]),
        "patternHash": str(identity["patternHash"]),
        "simulationTopologyHash": str(identity["simulationTopologyHash"]),
        "renderTopologyHash": str(identity["renderTopologyHash"]),
        "bindingHash": sha256_file(package / "binding/sim_to_render.bin"),
    }
    context_hash = document_hash(context)
    profile = _profile()
    write_canonical_json(root / PROFILE, profile)
    write_canonical_json(output / "external_exact_head_authority.json", _external_authority())
    write_canonical_json(output / "unit_c_truth_audit.json", _unit_c_audit(root, context))
    package_audit = audit_candidate_package(package)
    package_audit["selectedCandidateContext"] = context
    package_audit["selectedCandidateContextHash"] = context_hash
    write_canonical_json(output / "candidate_package_authority.json", package_audit)
    raster = audit_raster_semantics_v4(
        package,
        exact_texture_evaluation=root
        / "docs/evidence/d0_fitting_pbr_fidelity_v2/evaluation"
        / "exact_texture_rerender_evaluation.json",
        exact_reference_evaluation=root
        / "docs/evidence/d0_fitting_pbr_fidelity_v2/evaluation/exact_reference_3d_evaluation.json",
        contribution_output=contribution_output,
    )
    write_canonical_json(output / "raster_semantics_v4.json", raster)
    write_canonical_json(
        output / "phy_evaluator_v4_microfixtures.json", evaluate_phy_microfixtures_v4()
    )
    write_canonical_json(
        output / "pr43_phy_diagnostic_rescore_v4.json",
        evaluate_phy1_trajectory_diagnostic_v4(root),
    )
    execution = {
        "schemaVersion": 1,
        "classification": "capability_conditional_external_execution_authority",
        "status": "not_run",
        "attemptState": "dependency_blocked",
        "reason": "authenticated_execution_not_supplied",
        "corePackageAuthorityValidWithoutZeroOne": True,
        "requiredWhenSupplied": [
            "platform",
            "architecture",
            "zeroOneCommit",
            "processorContractSha256",
            "executableSha256",
            "requestInventorySha256",
            "outputInventorySha256",
            "executionAttestationSha256",
            "candidatePackageDigest",
        ],
        "trustedAuthorityMustBeExternal": True,
        "descriptorOnlyStateLegal": True,
        "runtimeV1RemainsSelected": True,
    }
    write_canonical_json(output / "conditional_execution_authority.json", execution)
    scoped = _scoped_authorities(context, context_hash)
    write_canonical_json(output / "scoped_candidate_authorities.json", scoped)
    registry = _attempt_registry(context_hash)
    write_canonical_json(output / "attempt_registry_v3.json", registry)
    bindings = _bindings(root, output, context)
    write_canonical_json(output / "matrix_evidence_bindings_v3.json", bindings)
    matrix = evaluate_research_matrix_v3(
        root,
        profile=profile,
        bindings=bindings["evidenceBindings"],
        attempt_registry=registry,
        selected_context=context,
        evidence_source_anchor_sha=SOURCE_ANCHOR,
        externally_attested_head_sha=PR43_HEAD,
    )
    write_canonical_json(output / "final_d0_research_prototype_matrix_v3.json", matrix)
    manifest_value = _evidence_manifest(output)
    write_canonical_json(output / "evidence_manifest.json", manifest_value)
    return {
        "profile": root / PROFILE,
        "matrix": output / "final_d0_research_prototype_matrix_v3.json",
        "attemptRegistry": output / "attempt_registry_v3.json",
        "manifest": output / "evidence_manifest.json",
    }


def _profile() -> dict[str, Any]:
    definitions = [
        (
            1,
            "decoded front/rear raster ingestion and source identity",
            "front_rear_source.v3",
            ["source_lineage"],
            "core",
            True,
        ),
        (
            2,
            "pixel-derived masks, landmarks, and correction provenance",
            "observation_lineage.v3",
            ["observation_lineage"],
            "core",
            True,
        ),
        (
            3,
            "image-conditioned comparative template ranking and fit",
            "identity_disjoint_fit.v3",
            ["exact_fit", "unit_c_audit"],
            "core",
            True,
        ),
        (
            4,
            "isolated permissioned contenders and comparative acceptance",
            "isolated_baselines.v3",
            ["exact_baselines", "unit_c_audit"],
            "core",
            True,
        ),
        (
            5,
            "persisted pattern, seams, openings, simulation/render topology, and binding",
            "canonical_garment.v3",
            ["package_authority"],
            "core",
            True,
        ),
        (
            6,
            "source-conditioned reference-3D fidelity",
            "reference_3d.v3",
            ["exact_reference", "unit_c_audit"],
            "core",
            True,
        ),
        (
            7,
            "contribution-aware bitmap projection and rerender fidelity",
            "visible_texture.v3",
            ["exact_texture", "raster_semantics"],
            "core",
            True,
        ),
        (
            8,
            "dense shell follows the exact simulation mesh",
            "C3-Binding-D0-v3",
            ["strict_c3"],
            "core",
            True,
        ),
        (
            9,
            "conventional garment fallback without ZeroOne",
            "runtime.offline_fallback.v3",
            ["runtime_qualification", "package_authority"],
            "supplemental",
            False,
        ),
        (
            10,
            "exact-candidate ZeroOne static execution",
            "Z1-exact-candidate-v3",
            [],
            "supplemental",
            False,
        ),
        (
            11,
            "exact-candidate MT1 mechanical reference",
            "MT1-exact-candidate-v3",
            [],
            "supplemental",
            False,
        ),
        (
            12,
            "core Forge fresh/delete-rebuild reproducibility",
            "forge.reproducibility.v3",
            ["delete_rebuild"],
            "core",
            True,
        ),
        (
            13,
            "artifact-derived exact reporting integrity",
            "reporting.integrity.v3",
            ["package_authority", "external_authority"],
            "core",
            True,
        ),
        (
            14,
            "unsupported evidence classes remain false",
            "unsupported.claims.v3",
            ["phy_diagnostic"],
            "supplemental",
            False,
        ),
        (
            15,
            "deterministic fixed-avatar neutral pattern and simulation execution",
            "neutral.simulation.v3",
            ["neutral_simulation", "phy_diagnostic"],
            "core",
            True,
        ),
    ]
    rows = []
    for number, requirement, threshold, evidence, summary, required in definitions:
        rows.append(
            {
                "rowId": f"D0-RP-{number:02d}",
                "scope": "exact_fixture_candidate",
                "requirement": requirement,
                "decisionGroup": "research_prototype_core"
                if summary == "core"
                else "supplemental_runtime_governance",
                "summaryClass": summary,
                "requiredForResearchPrototype": required,
                "thresholdRegistryRef": threshold,
                "requiredEvidenceIds": evidence,
            }
        )
    return {
        "schemaVersion": 3,
        "registryId": "closy.d0_research_matrix.thresholds.v3",
        "rows": rows,
        "scopedAuthorities": [
            {"scope": "exact_fixture_candidate", "authority": "selectedCandidateContext"},
            {
                "scope": "aggregate_identity_disjoint_cohort",
                "authority": "separate_never_attempted_unit_e",
            },
            {"scope": "per_cohort_identity", "authority": "separate_never_attempted_unit_e"},
            {
                "scope": "post_topology_physical_candidate",
                "authority": "separate_never_attempted_unit_e",
            },
        ],
        "summaryPolicy": {
            "coreRowIds": [f"D0-RP-{value:02d}" for value in (*range(1, 9), 12, 13, 15)],
            "supplementalRowIds": ["D0-RP-09", "D0-RP-10", "D0-RP-11", "D0-RP-14"],
            "blendedHeadlineCountForbidden": True,
        },
    }


def _attempt_registry(context_hash: str) -> dict[str, Any]:
    registry: dict[str, Any] = {
        "schemaVersion": 3,
        "registryVersion": ATTEMPT_REGISTRY_VERSION,
        "appendOnly": True,
        "records": [],
        "recordCount": 0,
        "headHash": "0" * 64,
    }
    states = {
        1: ("attempted_pass", "exact_source_lineage_valid"),
        2: ("attempted_pass", "exact_observation_lineage_valid"),
        3: (
            "attempted_fail",
            "degenerate_fit_did_not_establish_image_conditioned_comparative_gain",
        ),
        4: (
            "attempted_integrity_error",
            "contender_subprocess_isolation_and_comparative_acceptance_not_established",
        ),
        5: ("attempted_pass", "canonical_candidate_package_reopened_and_valid"),
        6: ("attempted_pass", "exact_fixture_replay_only"),
        7: ("attempted_fail", "front_logo_iou_and_displacement_failed"),
        8: ("attempted_fail", "strict_c3_neutral_blocked_and_pose_suite_not_run"),
        9: ("attempted_pass", "conventional_garment_fallback_reopened"),
        10: ("never_attempted", "exact_candidate_z1_not_executed"),
        11: ("never_attempted", "exact_candidate_mt1_not_executed"),
        12: ("attempted_pass", "forge_delete_rebuild_digest_identical"),
        13: ("attempted_pass", "exact_reporting_and_external_head_authority_valid"),
        14: ("attempted_pass", "unsupported_claims_remain_false"),
        15: ("attempted_fail", "neutral_preflight_failed"),
    }
    profile = _profile()
    evidence_by_row = {
        int(row["rowId"][-2:]): row["requiredEvidenceIds"] for row in profile["rows"]
    }
    for number in range(1, 16):
        state, reason = states[number]
        append_attempt(
            registry,
            attempt_id=f"attempt.unit_e.exact.D0-RP-{number:02d}.001",
            lineage_id=f"lineage.exact.{context_hash[:16]}.D0-RP-{number:02d}",
            row_id=f"D0-RP-{number:02d}",
            scope="exact_fixture_candidate",
            candidate_identity_hash=context_hash,
            attempt_state=state,  # type: ignore[arg-type]
            reason_code=reason,
            evidence_ids=list(evidence_by_row[number]),
        )
    return registry


def _unit_c_audit(root: Path, context: Mapping[str, Any]) -> dict[str, Any]:
    base = root / "docs/evidence/d0_fitting_pbr_fidelity_v2"
    predictions = _object(base / "predictions/contender_predictions.json")
    records = predictions["predictions"]
    if not isinstance(records, list):
        raise ValueError("unit_c_prediction_inventory_invalid")
    parameter_hashes = {
        str(record["contenderId"]): document_hash(_mapping(record["parameters"]))
        for record in records
        if isinstance(record, dict)
    }
    fit = _object(base / "evaluation/exact_fit_evaluation.json")
    baseline = _object(base / "evaluation/exact_baseline_evaluation.json")
    reference = _object(base / "evaluation/exact_reference_3d_evaluation.json")
    texture = _object(base / "evaluation/exact_texture_rerender_evaluation.json")
    freeze = _object(base / "predictions/prediction_freeze.json")
    return {
        "auditVersion": "closy.d0.unit_c_truth_reset.v4",
        "selectedCandidateContext": dict(context),
        "selectedCandidateContextHash": document_hash(context),
        "chronology": {
            "lockCommit": freeze["lockCommitSha"],
            "predictionFreezeCommit": "0d54b7e32664eb873e1662c6ca21e46e65e5557f",
            "evaluatorImplementationCommit": "c9aaa81d1acf1aa79b20555b7ed22890a46a825f",
            "evaluatorAuthoredAfterPredictions": True,
            "prePredictionEvaluatorFreezeSatisfied": False,
        },
        "targetIdentity": {
            "classification": "public_default_regular_prior_exact_fixture_replay",
            "patternHash": reference["pattern"]["targetPatternHash"],
            "surfaceHash": reference["surface"]["targetContentHash"],
        },
        "candidateIdentity": {
            "patternHash": reference["pattern"]["candidatePatternHash"],
            "surfaceHash": reference["surface"]["candidateContentHash"],
        },
        "contenderPredictions": [
            {
                "contenderId": record["contenderId"],
                "predictionHash": record["predictionHash"],
                "parameterHash": parameter_hashes[str(record["contenderId"])],
            }
            for record in records
            if isinstance(record, dict)
        ],
        "degeneracy": {
            "metadataPriorImageConditionedAndNoPixelAll16ParametersIdentical": len(
                {
                    parameter_hashes["metadata_category_prior"],
                    parameter_hashes["no_pixel_template"],
                    parameter_hashes["image_conditioned"],
                }
            )
            == 1,
            "candidatePatternEqualsTarget": reference["pattern"]["candidatePatternHash"]
            == reference["pattern"]["targetPatternHash"],
            "candidateSurfaceEqualsTarget": reference["surface"]["candidateContentHash"]
            == reference["surface"]["targetContentHash"],
        },
        "actualCompiledRerenderMetrics": {
            "maximumParameterErrorMeters": fit["maximumParameterErrorMeters"],
            "frontLogoIoU": texture["frontLogoIdentity"]["logoIoU"],
            "frontLogoDisplacementNormalised": texture["frontLogoIdentity"][
                "logoDisplacementNormalised"
            ],
            "strongestMaskLandmarkMeanSilhouetteIoU": 0.445188,
            "imageConditionedMeanSilhouetteIoU": 0.443582,
            "strongestMaskLandmarkMaximumBoundaryError": 0.051848256,
            "imageConditionedMaximumBoundaryError": 0.05378011,
        },
        "upstreamFit": {
            "accepted": fit["upstreamFitReportAccepted"],
            "status": fit["upstreamFitReportStatus"],
        },
        "executionIsolation": {
            "freshApplicationWorkspacesDeclared": baseline["freshApplicationWorkspaces"],
            "actualSeparateSubprocessExecutionEstablished": False,
            "openedFileAuditEstablished": False,
            "osSandboxClaimed": baseline["osSandboxClaimed"],
        },
        "contributionAccountingDefect": {
            "frontRearContributionRenderPresentInOriginalEvaluation": False,
            "frontRearGeneratedRegionShareRecorded": 1.0,
            "fullForegroundColorMaeWasScored": True,
            "sourceObservedOnlyScoreEstablishedByOriginalEvaluation": False,
        },
        "honestClassifications": {
            "D0-RP-03": "attempted_fail",
            "D0-RP-04": "attempted_integrity_error",
            "D0-RP-06_exact_fixture_replay": "attempted_pass",
            "D0-RP-06_identity_disjoint": "never_attempted",
        },
    }


def _external_authority() -> dict[str, Any]:
    rows = [
        (
            39,
            "codex/closy-forge-phy1-topology-v2",
            "921ef05b61f39e6020ad12126ffac24c4728f7e0",
            "f732df267642cd55960205764e699c7fa2bb2d0f",
            "33342673147",
        ),
        (
            40,
            "codex/closy-forge-d0-truth-runtime-authority-v3",
            "f732df267642cd55960205764e699c7fa2bb2d0f",
            "dbe9b3691b6c7bfc8a8a92ceeb04a7916e34e30a",
            "33380042123",
        ),
        (
            41,
            "codex/closy-forge-d0-raster-identity-v2",
            "dbe9b3691b6c7bfc8a8a92ceeb04a7916e34e30a",
            "4b1f4d550cf6e595170f9ef7bd28384c147ca2e8",
            "33393781144",
        ),
        (
            42,
            "codex/closy-forge-d0-fitting-pbr-fidelity-v2",
            "4b1f4d550cf6e595170f9ef7bd28384c147ca2e8",
            "7922e9b6ece8fca2c3b7dec13299a39de102cbc4",
            "33409665461",
        ),
        (
            43,
            "codex/closy-forge-phy1-seam-support-v3",
            "7922e9b6ece8fca2c3b7dec13299a39de102cbc4",
            PR43_HEAD,
            "33423822705",
        ),
    ]
    return {
        "authorityVersion": "closy.external_exact_head_authority.v4",
        "evidenceSourceAnchor": SOURCE_ANCHOR,
        "finalPublishedHead": PR43_HEAD,
        "nextChildHead": "external_after_publish_not_self_recorded",
        "prDag": [
            {
                "pullRequest": number,
                "branch": branch,
                "baseSha": base,
                "headSha": head,
                "workflowRunId": run,
                "workflowUrl": f"https://github.com/jake-the-jake/Closy/actions/runs/{run}",
                "forgeJobCount": 29,
                "forgeJobCountSemantics": "all_jobs_named_Forge_excludes_skipped_Supabase_Preview",
                "exactHeadRequiredJobsPassed": True,
                "draftOpenUnmergedMergeableObserved": True,
                "mergeBaseEqualsBase": True,
                "commitsBehindParent": 0,
            }
            for number, branch, base, head, run in rows
        ],
        "pr43TestAuthority": {
            "unitAndCorruptionTests": 628,
            "integrationAndGoldenTests": 33,
            "garmentFamilyLanes": 9,
            "ubuntuAndWindows": True,
            "python311And312WhereConfigured": True,
        },
        "appendOnlyCorrections": [
            "historical jobCount fields mean Forge jobs, not all GitHub check rows",
            "29 of 29 Forge jobs passed; skipped Supabase Preview is not a Forge failure",
            "stale test-count prose is superseded by the exact PR43 workflow counts above",
            "literal line breaks in future PR bodies must be real newlines, not escaped text",
        ],
        "main": {
            "sha": "859d4ee9a8a3386e95ec8c29043aa9ecc246769a",
            "untouched": True,
            "protected": False,
        },
    }


def _scoped_authorities(context: Mapping[str, Any], context_hash: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "selectedExactFixtureCandidate": {
            "scope": "exact_fixture_candidate",
            "selectedContext": dict(context),
            "selectedContextHash": context_hash,
        },
        "aggregateIdentityDisjointCohort": {
            "scope": "aggregate_identity_disjoint_cohort",
            "attemptState": "never_attempted",
            "resultStatus": "not_run",
            "nextAuthorizedUnit": "G",
        },
        "perCohortIdentityCandidates": {
            "scope": "per_cohort_identity",
            "attemptState": "never_attempted",
            "resultStatus": "not_run",
        },
        "postTopologyPhysicalCandidate": {
            "scope": "post_topology_physical_candidate",
            "attemptState": "never_attempted",
            "resultStatus": "not_run",
            "predecessorOutcome": "A_neutral_preflight_failed_v3",
        },
        "crossScopePassDonationForbidden": True,
    }


def _bindings(root: Path, output: Path, context: Mapping[str, Any]) -> dict[str, Any]:
    eval_root = root / "docs/evidence/d0_fitting_pbr_fidelity_v2/evaluation"
    pred_root = root / "docs/evidence/d0_fitting_pbr_fidelity_v2/predictions"

    def bind(path: Path, predicates: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "classification": "public_fixture",
            "path": path.relative_to(root).as_posix(),
            "sha256": canonical_artifact_sha256(path),
            "predicates": predicates,
        }

    identity_predicates = [
        _equals(f"selected_{key}", f"/selectedIdentity/{key}", value)
        for key, value in (
            ("packageDigest", context["packageDigest"]),
            ("avatarContractHash", context["avatarContractHash"]),
            ("garmentId", context["garmentId"]),
        )
    ]
    evidence = {
        "source_lineage": bind(
            eval_root / "candidate_source_lineage.json",
            identity_predicates + [_equals("status", "/status", "pass")],
        ),
        "observation_lineage": bind(
            eval_root / "candidate_observation_lineage.json",
            identity_predicates + [_equals("status", "/status", "pass")],
        ),
        "exact_fit": bind(
            eval_root / "exact_fit_evaluation.json",
            identity_predicates
            + [
                _equals("upstream_failed", "/upstreamFitReportStatus", "fail"),
                _equals("upstream_rejected", "/upstreamFitReportAccepted", False),
            ],
        ),
        "exact_baselines": bind(
            eval_root / "exact_baseline_evaluation.json",
            identity_predicates + [_equals("no_os_sandbox_overclaim", "/osSandboxClaimed", False)],
        ),
        "unit_c_audit": bind(
            output / "unit_c_truth_audit.json",
            [
                _equals("context", "/selectedCandidateContextHash", document_hash(context)),
                _equals(
                    "evaluator_after_prediction",
                    "/chronology/evaluatorAuthoredAfterPredictions",
                    True,
                ),
            ],
        ),
        "package_authority": bind(
            output / "candidate_package_authority.json",
            [
                _equals("status", "/status", "pass"),
                _equals("context", "/selectedCandidateContextHash", document_hash(context)),
                _equals("fallback_garment", "/semanticAuthorities/fallbackIsGarmentNotBody", True),
            ],
        ),
        "exact_reference": bind(
            eval_root / "exact_reference_3d_evaluation.json",
            identity_predicates
            + [
                _equals("status", "/status", "pass"),
                {
                    "predicateId": "pattern_replay",
                    "pointer": "/pattern/candidatePatternHash",
                    "operation": "identity_equals",
                    "identityPointer": "/pattern/targetPatternHash",
                },
                {
                    "predicateId": "surface_replay",
                    "pointer": "/surface/candidateContentHash",
                    "operation": "identity_equals",
                    "identityPointer": "/surface/targetContentHash",
                },
            ],
        ),
        "exact_texture": bind(
            eval_root / "exact_texture_rerender_evaluation.json",
            identity_predicates
            + [
                _equals("status", "/status", "pass"),
                _equals("logo_iou", "/frontLogoIdentity/logoIoU", 1.0),
                {
                    "predicateId": "logo_displacement",
                    "pointer": "/frontLogoIdentity/logoDisplacementNormalised",
                    "operation": "less_or_equal",
                    "expected": 0.05,
                },
            ],
        ),
        "raster_semantics": bind(
            output / "raster_semantics_v4.json",
            [
                _equals("status", "/status", "pass"),
                _equals(
                    "generated_fill_neutral",
                    "/sourceFidelityColor/generatedFillCannotImproveScore",
                    True,
                ),
                _equals("pbr_not_measured", "/physicalPbrAccuracy", "not_measured"),
            ],
        ),
        "strict_c3": bind(
            eval_root / "strict_c3_evaluation.json",
            identity_predicates + [_equals("status", "/status", "pass")],
        ),
        "runtime_qualification": bind(
            eval_root / "candidate_runtime_qualification.json",
            identity_predicates
            + [
                _equals("status", "/status", "pass"),
                _equals("fallback", "/conventionalFallbackLoaded", True),
                _equals("v1", "/productRuntimeV1Unchanged", True),
            ],
        ),
        "delete_rebuild": bind(
            pred_root / "delete_rebuild_reproducibility.json",
            [
                _equals("status", "/status", "pass"),
                _equals("identical", "/identical", True),
                {
                    "predicateId": "digest_match",
                    "pointer": "/firstDigest",
                    "operation": "identity_equals",
                    "identityPointer": "/rebuiltDigest",
                },
            ],
        ),
        "external_authority": bind(
            output / "external_exact_head_authority.json",
            [
                _equals("head", "/finalPublishedHead", PR43_HEAD),
                _equals("main_untouched", "/main/untouched", True),
            ],
        ),
        "neutral_simulation": bind(
            eval_root / "exact_neutral_simulation.json",
            identity_predicates + [_equals("status", "/status", "pass")],
        ),
        "phy_diagnostic": bind(
            output / "pr43_phy_diagnostic_rescore_v4.json",
            [
                _equals(
                    "outcome_unchanged",
                    "/historicalOutcomeAuthority/predecessorOutcomeUnchanged",
                    True,
                ),
                _equals("no_rerun", "/historicalOutcomeAuthority/physicalCandidateReran", False),
                _equals("runtime_v1", "/historicalOutcomeAuthority/runtimeV1RemainsSelected", True),
            ],
        ),
    }
    return {
        "schemaVersion": 3,
        "selectedCandidateContextHash": document_hash(context),
        "evidenceBindings": evidence,
    }


def _evidence_manifest(output: Path) -> dict[str, Any]:
    inventory = [
        {
            "path": path.relative_to(output).as_posix(),
            "byteLength": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "evidence_manifest.json"
    ]
    return {
        "schemaVersion": 1,
        "manifestVersion": "closy.d0_evidence_integrity_v4.manifest.v1",
        "inventory": inventory,
        "inventoryDigest": document_hash({"inventory": inventory}),
        "runtimeV1RemainsSelected": True,
        "newFitAppearanceOrPhysicsCandidateExecuted": False,
    }


def _equals(predicate_id: str, pointer: str, expected: Any) -> dict[str, Any]:
    return {
        "predicateId": predicate_id,
        "pointer": pointer,
        "operation": "equals",
        "expected": expected,
    }


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"object_required:{path}")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("mapping_required")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    generate(args.root.resolve())


if __name__ == "__main__":
    main()
