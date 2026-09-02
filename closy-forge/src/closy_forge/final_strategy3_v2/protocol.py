from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.recovery_foundation_v2.topology_holdout import FIXTURE_TYPES, generator_lock

FIXTURE_ROOT = Path("fixtures/final_strategy3_v2")
EVIDENCE_ROOT = Path("docs/evidence/final_strategy3_v2")
LOCK_PATH = FIXTURE_ROOT / "final_implementation_lock.json"
RESERVATION_PATH = FIXTURE_ROOT / "strategy_design_reservation.json"
OFFICIAL_PATH = FIXTURE_ROOT / "official_attempt"
WORKFLOW_PATH = Path("../.github/workflows/forge-unit-u-final-strategy3-v2.yml")
STRATEGY_ID = "PHY1-V5-S3-SEAM-SEQUENCE-CONFORMING-REMESH-V2"
UNIT_T_HEAD = "0c45587371165f1c5f3e33934ee2cbf5156f9e02"
OUTCOMES = (
    "final_strategy3_admitted_on_untouched_confirmation_v2",
    "final_strategy3_failed_numeric_or_semantic_gates_v2",
    "final_strategy3_confirmation_integrity_error_v2",
    "dependency_blocked_before_official_seed_v2",
)


def build_protocol(
    root: Path,
    *,
    implementation_files: Sequence[Mapping[str, str]],
    preflight_run_id: str,
    preflight_image_id: str,
) -> dict[str, Any]:
    reservation = _mapping(read_json(root / RESERVATION_PATH))
    starting = _mapping(
        read_json(
            root / "docs/evidence/phy1_topology_strategy3_diagnosis_v1/starting_authority.json"
        )
    )
    topology_generator = generator_lock()
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "protocolVersion": "closy.phy1.final_strategy3_confirmation.v2",
        "strategyId": STRATEGY_ID,
        "strategyClass": reservation["strategyClass"],
        "unitTParentHead": UNIT_T_HEAD,
        "reservationSha256": sha256_file(root / RESERVATION_PATH),
        "implementationFiles": [dict(row) for row in implementation_files],
        "implementationDigest": _hash([dict(row) for row in implementation_files]),
        "publicConformance": {
            "maximumRepairCycles": 2,
            "executedCycles": 2,
            "cycleResults": ["failed_implementation_conformance", "pass"],
            "finalFixturePassCount": 8,
            "finalFixtureDenominator": 8,
            "qualificationEligible": False,
        },
        "numericPolicy": {
            "geometryIdentity": "signed_integer_nanometers",
            "rawExecution": "binary64_hex_terms_retained",
            "portableDecision": "metric_specific_fixed_point_round_half_even",
            "decisionAmbiguityBand": "one_fixed_point_unit_at_each_threshold_fails",
            "massIntegerScalePerKg": 1_000_000_000_000,
            "lengthIntegerScalePerMeter": 1_000_000_000,
            "energyIntegerScalePerJoule": 1_000_000_000_000,
        },
        "generator": topology_generator,
        "fixtureStrata": list(FIXTURE_TYPES),
        "fixtureDenominator": 8,
        "metrics": _metrics(),
        "mutations": _mutations(),
        "resourceBudgets": {
            "maximumWallSecondsPerFixture": 30,
            "maximumProcessRssBytes": 536_870_912,
            "maximumContainerCpus": 2,
            "maximumContainerMemoryBytes": 805_306_368,
            "maximumOutputBytesPerFixture": 2_000_000,
        },
        "authorityLifecycle": {
            "authority": "github_actions_external_event",
            "claim": "procedural_freeze_and_container_isolation_not_cryptographic_secrecy",
            "seedEntropy": "python_secrets_token_bytes_32",
            "seedDomain": "closy.phy1.final_strategy3.confirmation.v2",
            "commitmentsBeforeExecution": True,
            "privateUntilOutputFreeze": [
                "raw_seed",
                "nonces",
                "fixture_parameters",
                "oracle_outputs",
                "evaluator_state",
            ],
            "contestantReceivesOnlyFixture": True,
            "changedPathAuditAfterOutputFreeze": True,
            "rerollAllowed": False,
            "replacementAllowed": False,
            "downloadableCommitmentLimitation": (
                "workflow_artifacts_are_downloadable_only_after_the_job_finishes"
            ),
        },
        "startingAuthority": {
            "authorityDigest": _mapping(starting["integrity"])["authorityDigest"],
            "candidatePackageTreeDigest": starting["candidatePackageTreeDigest"],
            "globalPhysicalChainHead": starting["globalPhysicalChainHead"],
            "finiteComplianceAuthority": starting["finiteComplianceAuthority"],
            "solverAuthority": starting["solverAuthority"],
            "supportAuthority": starting["supportAuthority"],
            "actualBlobIdentities": starting["actualBlobIdentities"],
        },
        "budgetTransition": {
            "seamModels": {"available": 0, "reserved": 0, "consumed": 2, "remaining": 0},
            "topologyStrategies": {
                "available": 0,
                "reserved": 0,
                "consumed": 3,
                "remaining": 0,
                "currentStrategyConsumed": 1,
            },
            "candidateAttempts": {
                "available": 1,
                "reserved": 0,
                "consumed": 0,
                "remaining": 1,
            },
        },
        "candidatePolicy": {
            "canonicalSourceMountedInUnitU": False,
            "canonicalCandidateCreatedInUnitU": False,
            "firstCanonicalTransformationConsumesAttempt": True,
            "maximumCandidateAttempts": 1,
            "unitVRequiresLiteralAdmission": True,
        },
        "futurePostTopologyC3": _future_c3_protocol(),
        "futureGateZ2Core": _future_z2_protocol(),
        "preflight": {
            "externalRunId": preflight_run_id,
            "containerImageId": preflight_image_id,
            "genericCanaryPassed": True,
            "supportedDecisionVerifierPlatforms": ["ubuntu-latest", "windows-latest"],
        },
        "officialSeedCreated": False,
        "officialFixturePresent": False,
        "officialResultPresent": False,
        "outcomeVocabulary": list(OUTCOMES),
        "lockHash": "",
    }
    document["lockHash"] = _hash({**document, "lockHash": ""})
    return document


def validate_protocol(root: Path, protocol: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if protocol.get("strategyId") != STRATEGY_ID:
        issues.append("final_strategy3_id_invalid")
    if (
        protocol.get("fixtureStrata") != list(FIXTURE_TYPES)
        or protocol.get("fixtureDenominator") != 8
    ):
        issues.append("final_strategy3_fixture_matrix_invalid")
    conformance = _mapping(protocol.get("publicConformance"))
    if conformance.get("executedCycles") != 2 or conformance.get("cycleResults") != [
        "failed_implementation_conformance",
        "pass",
    ]:
        issues.append("final_strategy3_conformance_history_invalid")
    budget = _mapping(_mapping(protocol.get("budgetTransition")).get("topologyStrategies"))
    if budget != {
        "available": 0,
        "reserved": 0,
        "consumed": 3,
        "remaining": 0,
        "currentStrategyConsumed": 1,
    }:
        issues.append("final_strategy3_budget_transition_invalid")
    candidate = _mapping(_mapping(protocol.get("budgetTransition")).get("candidateAttempts"))
    if candidate.get("remaining") != 1 or candidate.get("consumed") != 0:
        issues.append("final_strategy3_candidate_budget_invalid")
    if _mapping(protocol.get("candidatePolicy")).get("canonicalSourceMountedInUnitU") is not False:
        issues.append("final_strategy3_canonical_source_claim_invalid")
    if set(protocol.get("outcomeVocabulary", ())) != set(OUTCOMES):
        issues.append("final_strategy3_outcomes_invalid")
    if _hash({**dict(protocol), "lockHash": ""}) != protocol.get("lockHash"):
        issues.append("final_strategy3_lock_hash_invalid")
    files = protocol.get("implementationFiles")
    if not isinstance(files, list) or not files:
        issues.append("final_strategy3_implementation_inventory_missing")
    return sorted(set(issues))


def validate_implementation(root: Path, protocol: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    files = protocol.get("implementationFiles")
    if not isinstance(files, list):
        return ["final_strategy3_implementation_inventory_missing"]
    for item in files:
        row = _mapping(item)
        path = (root / str(row.get("path", ""))).resolve()
        if not path.is_file() or sha256_file(path) != row.get("sha256"):
            issues.append(f"final_strategy3_implementation_hash_mismatch:{row.get('path')}")
    if _hash([dict(_mapping(row)) for row in files]) != protocol.get("implementationDigest"):
        issues.append("final_strategy3_implementation_digest_invalid")
    return sorted(set(issues))


def load_protocol(root: Path) -> dict[str, Any]:
    return _mapping(read_json(root / LOCK_PATH))


def _metrics() -> dict[str, Any]:
    return {
        "fixtureAggregate": {"requiredPassed": 8, "denominator": 8},
        "semanticSequence": {"requireExactOrderedIds": True, "intervalCoverage": "[0,1]_once"},
        "semanticQuotient": {
            "componentCount": 1,
            "tshirtOpeningCountWhereDeclared": 4,
            "extraOrBranchedOpeningsAllowed": False,
        },
        "finiteCompliance": {
            "complianceMetersPerNewton": 1e-9,
            "sampleCountChangeAllowed": False,
            "maximumResidualRatio": 0.1,
        },
        "mass": {"maximumAbsoluteErrorKg": 1e-12},
        "partition": {"minimumWeight": 0.0, "maximumWeight": 1.0, "sumTolerance": 1e-12},
        "topology": {
            "duplicateFaces": 0,
            "nonManifoldRawEdges": 0,
            "tJunctions": 0,
            "windingFaults": 0,
            "hiddenComponents": 0,
        },
        "ccd": {
            "vertexFaceDetected": True,
            "edgeEdgeDetected": True,
            "maximumPostCorrectionResidualMeters": 0.0005,
        },
        "portableDecision": {"ambiguityBandEntriesAllowed": 0, "supportedJobsMustAgree": True},
    }


def _mutations() -> list[str]:
    return [
        "reversed_seam_samples",
        "duplicated_seam_sample",
        "dropped_seam_sample",
        "non_monotonic_seam_sample",
        "wrong_orientation",
        "wrong_endpoint_class",
        "wrong_junction_incidence",
        "non_partitioning_weights",
        "mass_nonconservation",
        "stale_binding_topology_hash",
        "endpoint_only_vertex_face_ccd_false_negative",
        "endpoint_only_edge_edge_ccd_false_negative",
        "broad_semantic_label_self_collision_exclusion",
    ]


def _future_c3_protocol() -> dict[str, Any]:
    return {
        "protocolVersion": "closy.post_topology.c3.frozen_pre_candidate.v1",
        "denominator": 12,
        "states": [
            "neutral_settled",
            "left_arm_raise",
            "right_arm_raise",
            "forward_bend",
            "side_bend_left",
            "side_bend_right",
            "torso_twist_left",
            "torso_twist_right",
            "opening_stress",
            "seam_stress",
            "lightweight_material_extreme",
            "stiff_material_extreme",
        ],
        "selectionRule": "all_prescribed_states_and_final_solver_frame",
        "maximumDraws": 12,
        "metrics": {
            "maximumBindingErrorMeters": 0.00025,
            "maximumAbsoluteSeamCrackMeters": 0.008,
            "maximumRestRelativeInvertedTriangles": 0,
            "maximumNormalDecodeAngularErrorDegrees": 2.0,
            "maximumTangentDecodeAngularErrorDegrees": 3.0,
            "maximumWallSecondsPerState": 30,
            "maximumRssBytes": 536_870_912,
        },
        "oracleContract": "independent_package_decoder_cannot_import_candidate_reconstruction",
        "persistedDecoderRequirements": [
            "decode_normals_from_persisted_bytes",
            "decode_tangents_from_persisted_bytes",
            "validate_binding_record_source_topology_hash",
        ],
        "mutations": [
            "binding_weight",
            "binding_triangle",
            "binding_source_topology_hash",
            "normal_bytes",
            "tangent_bytes",
            "seam_correspondence",
            "rest_orientation",
        ],
        "outcomes": ["pass", "fail_metric", "fail_integrity", "not_run_prerequisite"],
    }


def _future_z2_protocol() -> dict[str, Any]:
    return {
        "protocolVersion": "closy.gate_z2.core.frozen_pre_candidate.v1",
        "kinematicStates": [
            "neutral",
            "arm_raise_left",
            "arm_raise_right",
            "forward_bend",
            "torso_twist",
            "camera_near",
            "camera_mid",
            "camera_far",
        ],
        "kinematicSelectionRule": "all_prescribed_states",
        "solverTrajectorySelectionRule": "first_middle_last_plus_maximum_deformation_frame",
        "invariants": [
            "cluster_influence_partition",
            "deformed_bounds_containment",
            "frame_continuity",
            "no_visible_crack",
            "lod_identity_and_thresholds",
            "culling_conservative",
            "residency_bounded",
            "fallback_loadable",
        ],
        "budgets": {
            "maximumDeformationMilliseconds": 8.0,
            "maximumBoundsMilliseconds": 2.0,
            "maximumLodMilliseconds": 1.0,
            "maximumWallSeconds": 120,
            "maximumCpuSeconds": 100,
            "maximumRssBytes": 536_870_912,
        },
        "mutations": [
            "cluster_weight",
            "cluster_index",
            "bounds_underestimate",
            "frame_discontinuity",
            "crack_opening",
            "lod_threshold",
            "culling_false_negative",
            "residency_overflow",
            "fallback_hash",
        ],
        "resultVocabulary": {
            "core": ["core_pass", "core_fail", "core_integrity_error", "core_not_run"],
            "solverIntegrated": [
                "solver_integrated_pass",
                "solver_integrated_fail",
                "solver_integrated_not_run_prerequisite",
            ],
        },
    }


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("final_strategy3_mapping_required")
    return dict(value)


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
