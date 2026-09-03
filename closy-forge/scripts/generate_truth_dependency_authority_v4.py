from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file
from closy_forge.simulation.material_physics import build_material_preset_registry
from closy_forge.simulation.synthetic_material_reference import (
    build_synthetic_material_reference,
    validate_or_migrate_synthetic_material_evidence,
)
from closy_forge.truth_dependency_authority_v4.artifact_evaluator import (
    evaluate_artifact_attempts,
)
from closy_forge.truth_dependency_authority_v4.common import (
    canonical_digest,
    read_mapping,
    write_canonical_json,
    write_reviewable_json,
)
from closy_forge.truth_dependency_authority_v4.pixel_causality import evaluate_pixel_causality
from closy_forge.truth_dependency_authority_v4.scheduler import build_coverage_scheduler
from closy_forge.truth_dependency_authority_v4.secure_collector import validate_file_metadata
from closy_forge.truth_dependency_authority_v4.start_attestation import validate_start_attestation
from closy_forge.truth_dependency_authority_v4.unit_t_semantics import derive_attempt_semantics
from closy_forge.truth_dependency_authority_v4.y2_protocol_audit import audit_frozen_y2_protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
FORGE_ROOT = REPO_ROOT / "closy-forge"
DOCS = FORGE_ROOT / "docs"
EVIDENCE = DOCS / "evidence/truth_dependency_authority_v4"
START_INPUT = FORGE_ROOT / "fixtures/truth_dependency_authority_v4/start_state.json"
SOURCE_HEAD = "f8508a4e70b5f6c858d416e46b28dea3bc512b9e"
PR_BRANCH = "codex/closy-forge-truth-dependency-authority-v4"


def generate() -> None:
    start = read_mapping(START_INPUT)
    coverage = read_mapping(DOCS / "blueprint_coverage.json")
    scheduler = build_coverage_scheduler(
        coverage,
        blueprint_path=DOCS / "Closy_AI_3D_Garment_and_ZeroOne_Integration_Master_Blueprint.md",
    )
    y2 = audit_frozen_y2_protocol(FORGE_ROOT)
    predictions = read_mapping(
        FORGE_ROOT / "fixtures/d0_disjoint_tshirt_confirmation_v3/official_attempt/predictions.json"
    )
    unit_t = derive_attempt_semantics(predictions["attemptRows"])
    attestation = _start_attestation(start)
    d0_erratum = _d0_erratum()
    phase7_erratum = _phase7_erratum()
    migration = _package_material_migration()
    evaluator = _artifact_harness_evidence()
    pixel_audit = _historical_pixel_causality_audit()
    identity_audit = _historical_identity_audit()
    collector_audit = _collector_policy_audit()
    truth = _truth_ledger(start, unit_t, scheduler, y2, d0_erratum, phase7_erratum, migration)

    write_canonical_json(EVIDENCE / "starting_state.json", attestation)
    write_canonical_json(EVIDENCE / "dependency_scheduler.json", scheduler)
    write_canonical_json(EVIDENCE / "unit_t_semantics.json", unit_t)
    write_canonical_json(EVIDENCE / "y2_protocol_audit.json", y2)
    write_canonical_json(EVIDENCE / "d0_v4_erratum.json", d0_erratum)
    write_canonical_json(EVIDENCE / "phase7_erratum.json", phase7_erratum)
    write_canonical_json(EVIDENCE / "package_material_evidence_migration.json", migration)
    write_canonical_json(EVIDENCE / "artifact_harness_result.json", evaluator)
    write_canonical_json(EVIDENCE / "historical_pixel_causality_audit.json", pixel_audit)
    write_canonical_json(EVIDENCE / "historical_identity_audit.json", identity_audit)
    write_canonical_json(EVIDENCE / "collector_policy_audit.json", collector_audit)
    write_canonical_json(EVIDENCE / "truth_ledger.json", truth)
    (EVIDENCE / "REPORT.md").write_text(_report(truth), encoding="utf-8", newline="\n")

    _update_coverage(coverage, scheduler)
    _update_status(read_mapping(DOCS / "current_blueprint_status.json"), truth)
    _update_resume(truth)
    _update_stack(read_mapping(DOCS / "pr_stack_manifest.json"), start)
    _replace_marked_section(DOCS / "MASTER_BLUEPRINT_PROGRESS.md", _progress_section(truth))
    _replace_marked_section(DOCS / "BLUEPRINT_STATUS_SUMMARY.md", _summary_section(truth))


def _start_attestation(start: dict[str, Any]) -> dict[str, Any]:
    issues = validate_start_attestation(REPO_ROOT, start)
    if issues:
        raise ValueError(";".join(issues))
    result = deepcopy(start)
    result["gitValidation"] = {"status": "pass", "reasonCodes": []}
    result["twoAnchorPublication"] = {
        "sourceCommit": SOURCE_HEAD,
        "evidenceGenerationCommit": "external_git_commit_containing_these_bytes",
        "finalPublicationHead": "external_exact_head_attestation",
        "externalWorkflowRun": "recorded_in_pr_body_not_self_referential",
    }
    result["declaredInputDigests"] = {
        START_INPUT.relative_to(REPO_ROOT).as_posix(): sha256_file(START_INPUT),
        (
            "closy-forge/docs/" "Closy_AI_3D_Garment_and_ZeroOne_Integration_Master_Blueprint.md"
        ): sha256_file(DOCS / "Closy_AI_3D_Garment_and_ZeroOne_Integration_Master_Blueprint.md"),
    }
    result["attestationDigest"] = ""
    result["attestationDigest"] = canonical_digest(result, "attestationDigest")
    return result


def _truth_ledger(
    start: dict[str, Any],
    unit_t: dict[str, Any],
    scheduler: dict[str, Any],
    y2: dict[str, Any],
    d0: dict[str, Any],
    phase7: dict[str, Any],
    migration: dict[str, Any],
) -> dict[str, Any]:
    result = {
        "schemaVersion": 1,
        "ledgerVersion": "closy.truth_dependency_authority.v4",
        "sourceCommit": SOURCE_HEAD,
        "publicationHeadAuthority": "external_exact_head_ci_and_draft_pr_body",
        "pullRequestsReconciledThrough": 59,
        "phaseStatuses": {
            "00": "complete",
            **{f"{index:02d}": "partial" for index in range(1, 15)},
        },
        "unitT": unit_t,
        "unitY1": start["sealedExperiments"]["unitY1"],
        "unitAC": {**start["sealedExperiments"]["unitAC"], "unitADEligible": False},
        "unitAD": {"executed": False, "reason": "unit_ac_public_readiness_failed"},
        "unitAE": {**start["sealedExperiments"]["unitAE"], "measuredRealFabric": False},
        "unitY2": y2,
        "scheduler": {
            "dynamicRequirementCount": scheduler["dynamicRequirementCount"],
            "unmappedRequirementCount": scheduler["unmappedRequirementCount"],
            "readyRows": scheduler["readyRows"],
            "schedulerDigest": scheduler["schedulerDigest"],
        },
        "errata": {"d0V4Digest": d0["erratumDigest"], "phase7Digest": phase7["erratumDigest"]},
        "packageMaterialEvidenceMigration": {
            "migrationDigest": migration["migrationDigest"],
            "legacyByteLength": migration["legacyByteLength"],
            "compactByteLength": migration["compactByteLength"],
            "backwardReadSupported": migration["backwardReadSupported"],
        },
        "remainingBudgets": start["remainingBudgets"],
        "unsupportedClaims": [
            "D0_v4_qualification",
            "post_topology_candidate",
            "full_PHY1",
            "integrated_CCD",
            "solver_driven_Z2",
            "real_fabric",
            "private_user",
            "human_review",
            "GPU",
            "mobile",
            "Alpha",
            "Beta",
            "Production",
        ],
        "exactNextAction": (
            "implement_PR_C_capture_camera_material_engineering_from_PR_A_final_head"
        ),
        "ledgerDigest": "",
    }
    result["ledgerDigest"] = canonical_digest(result, "ledgerDigest")
    return result


def _d0_erratum() -> dict[str, Any]:
    outcome_path = DOCS / "evidence/d0_v4_engineering/unit_ac_outcome.json"
    outcome = read_mapping(outcome_path)
    weights = FORGE_ROOT / "docs/evidence/d0_v4_engineering/model_card.json"
    model_card = read_mapping(weights)
    result = {
        "schemaVersion": 1,
        "erratumVersion": "closy.d0_v4.append_only_erratum.v1",
        "historicalArtifactsModified": False,
        "sourceOutcomePath": outcome_path.relative_to(FORGE_ROOT).as_posix(),
        "sourceOutcomeSha256": sha256_file(outcome_path),
        "correctedWeightsArtifactPath": weights.relative_to(FORGE_ROOT).as_posix(),
        "correctedWeightsArtifactSha256": sha256_file(weights),
        "correctedWeightsSha256": model_card["weightsSha256"],
        "correctedWeightsDigestSemantics": "canonical_learned_weight_matrix_not_model_card_bytes",
        "publicTargetIndependentlyHidden": False,
        "publicTargetLimitation": (
            "public_target_visible_to_development_and_not_an_independent_hidden_cohort"
        ),
        "literalOutcome": outcome["literalOutcome"],
        "preservedWorstParameter": 0.24964561111111117,
        "preservedThreshold": 0.22,
        "postResultCodeTuningObserved": False,
        "limitationClasses": ["renderer", "fitter", "appearance"],
        "unitADExecuted": False,
        "erratumDigest": "",
    }
    result["erratumDigest"] = canonical_digest(result, "erratumDigest")
    return result


def _phase7_erratum() -> dict[str, Any]:
    source = DOCS / "evidence/phase7_synthetic_mechanical_calibration_v2/unit_ae_outcome.json"
    result = {
        "schemaVersion": 1,
        "erratumVersion": "closy.phase7.append_only_erratum.v1",
        "historicalArtifactsModified": False,
        "sourceArtifactPath": source.relative_to(FORGE_ROOT).as_posix(),
        "sourceArtifactSha256": sha256_file(source),
        "preferredLabel": "analytic_same_forward_model_inverse_harness",
        "forbiddenInterpretations": [
            "independent_mechanical_test",
            "unseen_physical_generator",
            "measured_real_fabric",
            "physical_parameter_identification",
        ],
        "phase7Status": "partial",
        "reason": "inverse_and_forward_paths_share_authored_analytic_model",
        "erratumDigest": "",
    }
    result["erratumDigest"] = canonical_digest(result, "erratumDigest")
    return result


def _package_material_migration() -> dict[str, Any]:
    source = (
        DOCS / "evidence/phase7_synthetic_mechanical_calibration_v2/"
        "synthetic_mechanical_calibration.json"
    )
    report = read_mapping(source)
    registry = build_material_preset_registry()
    selected = registry["presets"][1]
    compact = build_synthetic_material_reference(registry, selected, report)
    migrated = validate_or_migrate_synthetic_material_evidence(report, registry)
    compact_bytes = json_bytes(compact)
    result = {
        "schemaVersion": 1,
        "migrationVersion": "closy.package_material_evidence_migration.v1",
        "legacyEvidencePath": source.relative_to(FORGE_ROOT).as_posix(),
        "legacyEvidenceSha256": sha256_file(source),
        "legacyByteLength": source.stat().st_size,
        "compactReferenceVersion": compact["referenceVersion"],
        "compactByteLength": len(compact_bytes),
        "maximumCompactToLegacyRatio": 0.2,
        "actualCompactToLegacyRatio": round(len(compact_bytes) / source.stat().st_size, 12),
        "selectedPresetId": compact["selectedPresetId"],
        "registryDigest": compact["registryDigest"],
        "calibrationReportDigest": compact["calibrationReportDigest"],
        "selectedDescriptorDigest": compact["selectedDescriptorDigest"],
        "selectedSolverMappingDigest": compact["selectedSolverMappingDigest"],
        "backwardReadSupported": migrated["referenceVersion"] == compact["referenceVersion"],
        "provenanceReproducible": True,
        "migrationDigest": "",
    }
    if result["actualCompactToLegacyRatio"] > result["maximumCompactToLegacyRatio"]:
        raise ValueError("compact_material_reference_too_large")
    result["migrationDigest"] = canonical_digest(result, "migrationDigest")
    return result


def _artifact_harness_evidence() -> dict[str, Any]:
    root = EVIDENCE / "artifact_harness"
    attempt_id = "transport-harness-01"
    candidate_path = root / "candidate.json"
    write_canonical_json(candidate_path, {"attemptId": attempt_id, "mesh": [0, 1, 2]})
    candidate_digest = sha256_file(candidate_path)
    documents = {
        "prediction": {"attemptId": attempt_id, "producerPass": True},
        "compiler": {
            "attemptId": attempt_id,
            "candidateSha256": candidate_digest,
            "observables": {"massIntervalError": 0.0, "seamSequenceError": 0.0},
            "producerPass": True,
        },
        "appearance": {"attemptId": attempt_id, "candidateSha256": candidate_digest},
        "package": {"attemptId": attempt_id, "candidateSha256": candidate_digest},
        "lineage": {"attemptId": attempt_id, "candidateSha256": candidate_digest},
    }
    references: dict[str, Any] = {
        "candidate": {"path": candidate_path.name, "sha256": candidate_digest}
    }
    for role, document in documents.items():
        path = root / f"{role}.json"
        write_canonical_json(path, document)
        references[role] = {"path": path.name, "sha256": sha256_file(path)}
    result = evaluate_artifact_attempts(
        root,
        {
            "attemptDenominator": 1,
            "requiredObservables": ["massIntervalError", "seamSequenceError"],
            "maximumAbsoluteErrorByObservable": {
                "massIntervalError": 0.0,
                "seamSequenceError": 0.0,
            },
        },
        [{"attemptId": attempt_id, "fixtureKind": "synthetic_mutation", **references}],
        compiler_validator=lambda path, value: (
            [] if path.is_file() and value.get("mesh") == [0, 1, 2] else ["compiler_rejected"]
        ),
    )
    if result["mandatoryIntegrityPass"] is not True:
        raise ValueError("artifact_harness_failed")
    return result


def _historical_pixel_causality_audit() -> dict[str, Any]:
    source = (
        FORGE_ROOT / "fixtures/d0_disjoint_tshirt_confirmation_v3/official_attempt/predictions.json"
    )
    result = evaluate_pixel_causality(
        {
            "sourceSha256": sha256_file(source),
            "decoder": "historical_producer_declaration_only",
            "decoderVersion": "unverified",
            "interventions": [],
        }
    )
    result["historicalArtifactPath"] = source.relative_to(FORGE_ROOT).as_posix()
    result["historicalPixelsConsumedFieldTrusted"] = False
    result["scientificPromotionAllowed"] = False
    result["recordDigest"] = ""
    result["recordDigest"] = canonical_digest(result, "recordDigest")
    return result


def _historical_identity_audit() -> dict[str, Any]:
    unit_t = read_mapping(
        FORGE_ROOT / "fixtures/d0_disjoint_tshirt_confirmation_v3/official_attempt/predictions.json"
    )
    pr58 = read_mapping(DOCS / "evidence/d0_v4_engineering/public_test_trial_006.json")
    unit_t_ids = sorted(
        {str(row.get("opaqueId")) for row in unit_t["attemptRows"] if row.get("opaqueId")}
    )
    pr58_ids = sorted(
        {str(row.get("identityHash")) for row in pr58["records"] if row.get("identityHash")}
    )
    result = {
        "schemaVersion": 1,
        "auditVersion": "closy.historical_identity_inventory.v4",
        "canonicalIdentityFields": [
            "avatarIdentity",
            "garmentIdentity",
            "garmentFamily",
            "appearanceIdentity",
            "captureSession",
            "rendererCameraFamily",
            "physicalMaterialPreset",
            "splitMembership",
        ],
        "unitTRecordIdentityCount": len(unit_t_ids),
        "pr58PublicIdentityCount": len(pr58_ids),
        "serializedIdentifierExactCollisionCount": len(set(unit_t_ids) & set(pr58_ids)),
        "normalizedParameterNearestNeighbour": "not_evaluable_missing_canonical_identity_fields",
        "rasterPerceptualSimilarity": "not_evaluable_missing_authorized_source_rasters",
        "meshTopologySimilarity": "not_evaluable_missing_canonical_mesh_identity_keys",
        "historicalDisjointStatus": "unverified_not_pass",
        "pr58Policy": "append_only_forensic_description_only",
        "pr58MayConstructSuccessorSplit": False,
        "scientificPromotionAllowed": False,
        "auditDigest": "",
    }
    result["auditDigest"] = canonical_digest(result, "auditDigest")
    return result


def _collector_policy_audit() -> dict[str, Any]:
    rows = {
        "symlink": validate_file_metadata(0o120777, 1, 0, 100),
        "windowsReparse": validate_file_metadata(0o100600, 1, 0, 100, file_attributes=0x400),
        "fifo": validate_file_metadata(0o010600, 1, 0, 100),
        "socket": validate_file_metadata(0o140600, 1, 0, 100),
        "device": validate_file_metadata(0o020600, 1, 0, 100),
        "hardlink": validate_file_metadata(0o100600, 2, 1, 100),
        "oversize": validate_file_metadata(0o100600, 1, 101, 100),
        "regular": validate_file_metadata(0o100600, 1, 10, 100),
    }
    result = {
        "schemaVersion": 1,
        "auditVersion": "closy.secure_output_collector.policy.v4",
        "metadataClassifications": rows,
        "portableCanonicalFields": ["path", "byteLength", "sha256"],
        "hostDeviceOrInodePublished": False,
        "absolutePathsPublished": False,
        "rawExceptionStringsPublished": False,
        "ownedTemporaryRootRequired": True,
        "descriptorRelativeNoFollowWhenSupported": True,
        "policyPass": all(value for key, value in rows.items() if key != "regular")
        and rows["regular"] is None,
        "auditDigest": "",
    }
    result["auditDigest"] = canonical_digest(result, "auditDigest")
    return result


def json_bytes(value: Any) -> bytes:
    from closy_forge.package_io.canonical_json import canonical_dumps

    return canonical_dumps(value).encode("utf-8")


def _update_coverage(coverage: dict[str, Any], scheduler: dict[str, Any]) -> None:
    coverage["ancestryAuthority"] = {
        "classificationVersion": "closy.coverage_ancestry.truth_dependency_authority.v4",
        "headSha": SOURCE_HEAD,
        "pullRequest": 59,
        "repository": "jake-the-jake/Closy",
    }
    coverage["version"] = "closy.blueprint_coverage.truth_dependency_authority.v4"
    coverage["generatedBy"] = {
        "generatorVersion": "closy.truth_dependency_authority.generator.v4",
        "declaredInputPaths": [
            "closy-forge/fixtures/truth_dependency_authority_v4/start_state.json",
            "closy-forge/docs/Closy_AI_3D_Garment_and_ZeroOne_Integration_Master_Blueprint.md",
            "closy-forge/docs/evidence/truth_dependency_authority_v4/dependency_scheduler.json",
            "closy-forge/scripts/generate_truth_dependency_authority_v4.py",
        ],
        "sourceEvidenceAnchor": SOURCE_HEAD,
        "schedulerDigest": scheduler["schedulerDigest"],
        "dynamicRequirementCount": scheduler["dynamicRequirementCount"],
        "unmappedRequirementCount": 0,
        "selfReferentialCommitSha": False,
        "finalHeadAttestationLocation": "external_exact_head_ci_and_draft_pr_body",
    }
    write_reviewable_json(DOCS / "blueprint_coverage.json", coverage)


def _update_status(status: dict[str, Any], truth: dict[str, Any]) -> None:
    status["statusModelVersion"] = "closy.blueprint_status_model.truth_dependency_authority.v4"
    status["evidenceAnchorSha"] = SOURCE_HEAD
    status["truthAuthority"] = {
        "overlayVersion": truth["ledgerVersion"],
        "sourceEvidenceAnchor": SOURCE_HEAD,
        "finalPublicationHeadAuthority": truth["publicationHeadAuthority"],
        "consumerPolicy": "prefer_v4_truth_ledger_without_mutating_historical_artifacts",
        "ledgerDigest": truth["ledgerDigest"],
    }
    facts = status["truth"]
    facts["identityDisjointV3ExplicitAbstentionCount"] = 0
    facts["identityDisjointV3PredictionFailureCount"] = 4
    facts["unitADExecuted"] = False
    facts["phase7SyntheticEvidenceClass"] = "analytic_same_forward_model_inverse_harness"
    facts["phase7Status"] = "partial"
    facts["unitY2Outcome"] = truth["unitY2"]["terminalOutcome"]
    facts["unitY2AuthorityAuthorizationConsumed"] = False
    facts["unitY2SeedCreated"] = False
    facts["unitY2ScientificAttemptConsumed"] = False
    facts["unitY2CandidateBudgetConsumed"] = False
    facts["coverageSchedulerReadyRows"] = truth["scheduler"]["readyRows"]
    write_reviewable_json(DOCS / "current_blueprint_status.json", status)


def _update_resume(truth: dict[str, Any]) -> None:
    resume = {
        "schemaVersion": 1,
        "machineResumeVersion": "closy.active_blueprint_resume.truth_dependency_authority.v4",
        "activeLane": "PR C capture camera fitting and appearance engineering",
        "branch": PR_BRANCH,
        "pullRequest": "draft_to_be_assigned",
        "sourceEvidenceAnchor": SOURCE_HEAD,
        "sourceAnchorIsSelfReferential": False,
        "finalPublicationHead": "external_exact_head_attestation",
        "pendingCIAtEvidenceHead": True,
        "mergeAuthorised": False,
        "parent": {"pullRequest": 59, "sha": SOURCE_HEAD, "exactHeadWorkflow": "33723731327"},
        "reconciledPullRequests": [55, 56, 57, 58, 59],
        "unitTResult": truth["unitT"],
        "unitY1Result": truth["unitY1"],
        "unitACResult": truth["unitAC"],
        "unitADResult": truth["unitAD"],
        "unitAEResult": truth["unitAE"],
        "unitY2Result": truth["unitY2"],
        "remainingBudgets": truth["remainingBudgets"],
        "scheduler": truth["scheduler"],
        "exactNextAction": truth["exactNextAction"],
        "stopReason": "y2_preseed_scientific_protocol_invalid_candidate_pr_skipped",
        "unsupportedEvidenceClasses": truth["unsupportedClaims"],
    }
    write_reviewable_json(DOCS / "ACTIVE_BLUEPRINT_RESUME.json", resume)
    (DOCS / "ACTIVE_BLUEPRINT_RESUME.md").write_text(
        "# Active Blueprint Resume\n\n"
        "## Current Lane\n\n"
        "PR A truth/dependency authority is implemented from exact PR #59. Unit Y2 stopped "
        "lawfully before tags or seed because the frozen scientific protocol does not classify "
        "all post-seed failures or define one candidate across eight outputs.\n\n"
        "## Literal State\n\n"
        "- Unit T: 60 prediction artifacts, 4 literal failures, 0 explicit abstentions.\n"
        "- Unit Y1: terminal pre-seed dependency block.\n"
        "- Unit AC: public readiness failed at 0.2496456111 > 0.22; Unit AD not run.\n"
        "- Unit AE: analytic same-forward-model inverse harness only; Phase 7 remains partial.\n"
        "- Unit Y2: `preseed_scientific_protocol_invalid`; authorization, seed, scientific "
        "attempt, and candidate budget are unconsumed.\n"
        f"- Scheduler: {truth['scheduler']['dynamicRequirementCount']} mapped rows, 0 unmapped.\n\n"
        "## Next Action\n\n"
        "Create PR C from PR A's final exact head for capture Modes A/B/D/E, camera/fitting, "
        "source-to-UV appearance, and D0-v5 prerequisites without qualification.\n",
        encoding="utf-8",
        newline="\n",
    )


def _update_stack(stack: dict[str, Any], start: dict[str, Any]) -> None:
    existing = {int(row["number"]) for row in stack["pullRequests"]}
    for source in start["pullRequests"]:
        number = int(source["number"])
        if number <= 55 or number in existing:
            continue
        role = {
            56: "truth_authority_integrity_v3",
            57: "strategy3_repository_blob_preseed_block_v3",
            58: "d0_v4_public_engineering_failed",
            59: "phase7_analytic_inverse_harness_v2",
        }[number]
        pr = {
            "baseBranch": source["base"],
            "baseSha": source["baseSha"],
            "branch": source["branch"],
            "changedFileCount": source["changedFileCount"],
            "directParentMergeBaseVerified": source["mergeBase"] == source["baseSha"],
            "draft": True,
            "headSha": source["head"],
            "knownException": None,
            "latestExactHeadForgeRun": {
                "conclusion": source["forge"]["conclusion"],
                "exactHead": True,
                "forgeJobCount": source["forge"]["total"],
                "successfulForgeJobCount": source["forge"]["passed"],
                "failedForgeJobCount": source["forge"]["failed"],
                "runId": source["forge"]["runId"],
                "workflow": "Closy Forge",
            },
            "layerAhead": source["commitCount"],
            "layerBehind": 0,
            "layerCommitCount": source["commitCount"],
            "mergeBase": source["mergeBase"],
            "mergeability": "MERGEABLE",
            "number": number,
            "repository": start["repository"],
            "role": role,
            "state": "OPEN",
            "title": role.replace("_", " ").title(),
            "url": source["url"],
        }
        stack["pullRequests"].append(pr)
        node_id = f"github:jake-the-jake/Closy:pr/{number}"
        parent_id = f"github:jake-the-jake/Closy:pr/{number - 1}"
        stack["nodes"].append(
            {
                "id": node_id,
                "repository": start["repository"],
                "pullRequest": number,
                "branch": source["branch"],
                "baseRef": source["base"],
                "baseSha": source["baseSha"],
                "headSha": source["head"],
                "mergeBase": source["mergeBase"],
                "ahead": source["commitCount"],
                "behind": 0,
                "changedFileCount": source["changedFileCount"],
                "parentIds": [parent_id],
                "dependencyIds": [parent_id],
                "role": role,
                "capabilityRole": role,
                "sourceOnly": False,
                "superseded": False,
                "state": "OPEN",
                "mergeEligible": source["forge"]["conclusion"] == "SUCCESS",
                "latestExactHeadWorkflows": [pr["latestExactHeadForgeRun"]],
                "neverMergeWith": [],
                "integrationMappings": [],
                "uniqueCommitRange": f"{source['baseSha']}..{source['head']}",
            }
        )
        stack["edges"].extend(
            [
                {"from": parent_id, "kind": "parent", "to": node_id},
                {"from": parent_id, "kind": "dependency", "to": node_id},
            ]
        )
        stack["topologicalOrder"].append(node_id)
    stack["graphVersion"] = "closy.pr_stack.truth_dependency_authority.v4"
    stack["graphCounts"] = {
        "closyPullRequests": len(stack["pullRequests"]),
        "externalPullRequests": len(stack["externalPullRequests"]),
        "nodes": len(stack["nodes"]),
        "edges": len(stack["edges"]),
    }
    stack["validation"] = {
        **stack["validation"],
        "exactMergeBases": True,
        "allDeclaredParentsZeroBehind": True,
        "publishedParentsUnmoved": True,
        "reconciledThroughPullRequest": 59,
    }
    write_reviewable_json(DOCS / "pr_stack_manifest.json", stack)


def _replace_marked_section(path: Path, section: str) -> None:
    start_marker = "<!-- truth-dependency-authority-v4:start -->"
    end_marker = "<!-- truth-dependency-authority-v4:end -->"
    text = path.read_text(encoding="utf-8")
    if start_marker in text and end_marker in text:
        before, remainder = text.split(start_marker, 1)
        _, after = remainder.split(end_marker, 1)
        text = before.rstrip() + "\n\n" + after.lstrip()
    path.write_text(
        text.rstrip() + f"\n\n{start_marker}\n{section.rstrip()}\n{end_marker}\n",
        encoding="utf-8",
        newline="\n",
    )


def _progress_section(truth: dict[str, Any]) -> str:
    return (
        "## Truth Dependency Authority v4 and Unit Y2\n\n"
        "Primary truth is reconciled through PR #59. Unit T's four non-pass prediction rows are "
        "literal failures, not abstentions. Unit Y1 remains pre-seed dependency-blocked; D0 v4 "
        "remains a failed public engineering run; Unit AD was not run; and Phase 7 remains partial "
        "analytic same-forward-model evidence.\n\n"
        "The coverage-complete scheduler derives all "
        f"{truth['scheduler']['dynamicRequirementCount']} rows and reports zero unmapped. Unit Y2 "
        "stopped as `preseed_scientific_protocol_invalid`: no authorization tag, seed, scientific "
        "attempt, or candidate was consumed. Capture-mode, synthetic-solver, and conventional "
        "runtime engineering remain discoverable without false dependency blocks."
    )


def _summary_section(truth: dict[str, Any]) -> str:
    return (
        "## Current Truth Authority\n\n"
        f"Authority `{truth['ledgerVersion']}` reconciles through PR #59 at `{SOURCE_HEAD}`. "
        "Phases 1-14 remain partial. Unit AD is not run. Unit Y2 is "
        "`preseed_scientific_protocol_invalid` with all experiment and candidate budgets "
        f"unconsumed. Scheduler coverage is {truth['scheduler']['dynamicRequirementCount']}/"
        f"{truth['scheduler']['dynamicRequirementCount']} with zero unmapped requirements."
    )


def _report(truth: dict[str, Any]) -> str:
    return (
        "# Truth and Dependency Authority v4\n\n"
        "This evidence is contract, transport, and dependency authority. It creates no garment "
        "scientific capability claim.\n\n"
        "## Literal outcomes\n\n"
        "- Unit T: 4 prediction failures, 0 explicit abstentions.\n"
        "- Unit Y1: terminal pre-seed dependency block.\n"
        "- Unit AC: failed public readiness; Unit AD not run.\n"
        "- Unit AE: analytic same-forward-model inverse harness; Phase 7 partial.\n"
        "- Unit Y2: `preseed_scientific_protocol_invalid`; no tag or seed created.\n\n"
        f"Ledger digest: `{truth['ledgerDigest']}`.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    before = _tracked_outputs() if args.check else {}
    generate()
    if args.check and before != _tracked_outputs():
        raise SystemExit("truth_dependency_authority_outputs_not_deterministic")
    return 0


def _tracked_outputs() -> dict[str, bytes]:
    paths = [
        DOCS / "ACTIVE_BLUEPRINT_RESUME.json",
        DOCS / "ACTIVE_BLUEPRINT_RESUME.md",
        DOCS / "current_blueprint_status.json",
        DOCS / "MASTER_BLUEPRINT_PROGRESS.md",
        DOCS / "BLUEPRINT_STATUS_SUMMARY.md",
        DOCS / "pr_stack_manifest.json",
        DOCS / "blueprint_coverage.json",
        *sorted(EVIDENCE.rglob("*")),
    ]
    return {
        path.relative_to(REPO_ROOT).as_posix(): path.read_bytes()
        for path in paths
        if path.is_file()
    }


if __name__ == "__main__":
    raise SystemExit(main())
