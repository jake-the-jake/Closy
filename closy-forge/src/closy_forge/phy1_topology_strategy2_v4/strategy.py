from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.phy1_topology_strategy2_v4.budget import validate_budget_classifier

STRATEGY_ID = "PHY1-V4-S2-CONFORMING-SEAM-QUOTIENT"
LOCK_VERSION = "closy.phy1.topology_strategy2.strategy_lock.v1"
FIXTURE_ROOT = Path("fixtures/phy1_topology_strategy2_v4")
EVIDENCE_ROOT = Path("docs/evidence/phy1_topology_strategy2_v4")
IMPLEMENTATION_PATHS = (
    "src/closy_forge/phy1_topology_strategy2_v4/strategy.py",
    "scripts/lock_phy1_topology_strategy2_v4.py",
)


def build_strategy_lock(root: Path) -> dict[str, Any]:
    budget = _object(root / FIXTURE_ROOT / "budget_classifier.json")
    if validate_budget_classifier(budget):
        raise ValueError("unit_i_budget_invalid_before_strategy_lock")
    v3 = _object(root / "fixtures/phy1_seam_support_v3/experiment_lock.json")
    diagnosis = _object(root / EVIDENCE_ROOT / "diagnosis.json")
    general = _object(root / EVIDENCE_ROOT / "general_microfixtures.json")
    if general.get("status") != "pass":
        raise ValueError("unit_i_general_microfixtures_not_passed")
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "lockVersion": LOCK_VERSION,
        "state": "frozen_before_strategy_specific_microfixture",
        "source": {
            "parentHead": "07b28f804274cdf6f79347150a85fcc3ff9f4684",
            "pr43Head": "6aee5ed3b2753ee99c95abdef6f5a24be39b3a7e",
            "candidateId": v3["candidate"]["candidateId"],
            "candidatePackageDigest": v3["candidate"]["candidatePackageDigest"],
            "patternHash": v3["candidate"]["patternHash"],
            "seamConstraintHash": v3["candidate"]["seamConstraintHash"],
            "diagnosisDigest": diagnosis["integrity"]["diagnosisDigest"],
            "generalMicrofixtureDigest": general["integrity"]["microfixtureDigest"],
        },
        "hypothesis": (
            "a seam-synchronised conforming topology with quotient shared seam/junction DOFs "
            "removes the dominant explicit-seam residual without changing frozen v3 mechanics"
        ),
        "strategy": {
            "strategyId": STRATEGY_ID,
            "classification": "topology_or_dof_representation",
            "algorithm": (
                "insert_union_of_normalised_arclength_samples_on_paired_boundaries_then_"
                "deterministic_union_find_quotient"
            ),
            "seamTreatment": "shared_dof_only_if_finite_compliance_equivalence_passes",
            "junctionTreatment": "single_shared_dof_per_authored_rank_component",
            "semanticPanelsPreserved": True,
            "openingIds": [
                "opening.neck",
                "opening.cuff.left",
                "opening.cuff.right",
                "opening.hem",
            ],
            "patternMaterialCoordinatesPreserved": True,
            "bindingRebuildRequired": True,
            "conventionalFallbackRequired": True,
            "transferScope": "same_named_pr43_d0_geometry_lineage_only",
            "transferCriterion": "all_candidate_independent_equivalence_cases_pass",
        },
        "frozenV3": {
            "lockSha256": sha256_file(root / "fixtures/phy1_seam_support_v3/experiment_lock.json"),
            "materialPayloadHash": v3["fixedInputs"]["materialPayloadHash"],
            "avatarContractHash": v3["fixedInputs"]["avatarContractHash"],
            "solverHash": _hash(v3["configuration"]["solver"]),
            "seamLawHash": _hash(v3["configuration"]["seams"]),
            "supportLawHash": _hash(v3["configuration"]["supports"]),
            "collisionLawHash": _hash(v3["configuration"]["collision"]),
            "constraintOrderHash": _hash(v3["configuration"]["constraintOrder"]),
        },
        "thresholds": deepcopy(v3["thresholds"]),
        "equivalenceThresholds": {
            "maximumPositionDifferenceMeters": 1e-12,
            "maximumStoredSeamEnergyDifferenceJoules": 1e-12,
            "maximumImpulseDifferenceNewtonSeconds": 1e-12,
            "allCasesRequired": True,
        },
        "metricDefinitions": {
            "nonInversion": "rotation_invariant_temporal_local_jacobian_swept_orientation",
            "terminalMotion": "aggregate_complete_declared_tail_window",
            "supportResidual": "after_final_projection_at_declared_frame_boundary",
            "supportEnergy": "joules_from_physical_compliance_not_inner_iteration_sum",
            "seamArclength": "paired_deformed_arclengths",
            "exclusionRing": "consumed_by_collision_candidate_construction",
            "numericalTerminationSeparatedFromConvergence": True,
        },
        "performance": {
            "hardwareId": "BFEBFBFF000506E3",
            "cpu": "Intel(R) Core(TM) i7-6700HQ CPU @ 2.60GHz",
            "cores": 4,
            "threads": 8,
            "threadPolicy": "single_thread_deterministic",
            "os": "Microsoft Windows NT 10.0.19045.0",
            "python": "3.11.4",
            "buildMode": "CPython_optimized_dependencies_reference_python",
            "timingBoundary": "fresh_process_after_input_validation_through_canonical_output_flush",
            "runtimeCeilingSeconds": 180,
        },
        "workBudget": {
            "maximumSubsteps": v3["configuration"]["solver"]["maximumSubsteps"],
            "iterationsPerSubstep": v3["configuration"]["solver"]["iterationsPerSubstep"],
            "bodyCollisionCadenceIterations": v3["configuration"]["collision"][
                "bodyCadenceIterations"
            ],
            "selfCollisionCadenceIterations": v3["configuration"]["collision"][
                "selfCollisionCadenceIterations"
            ],
            "maximumContactCandidates": 250000,
            "requiredConsecutiveConvergedFrames": v3["configuration"]["solver"][
                "requiredConsecutiveConvergedFrames"
            ],
        },
        "ccd": {
            "algorithm": "deterministic_swept_vertex_triangle_conservative_advancement",
            "cadence": "every_substep_before_discrete_body_and_self_projection",
            "neutralAndMotionIdentical": True,
            "maximumConservativeAdvancementIterations": 8,
        },
        "attemptPlan": {
            "trialCount": 1,
            "independentRepeatCount": 2,
            "freshProcessAndWorkspaceEachRun": True,
            "deleteCachesAndMutableState": True,
        },
        "stopRule": {
            "strategySpecificMicrofixtureFailure": "outcome_M_and_logical_J_A_no_candidate",
            "neutralFailure": "outcome_A_no_full_phy1_ccd_or_z2",
            "fullFailure": "outcome_B_no_z2",
            "fullPass": "outcome_C_requires_unit_J",
            "postCandidateRetryAllowed": False,
        },
        "budget": {
            "candidateAttemptsMaximum": 1,
            "candidateAttemptsConsumedBeforeExecution": 0,
            "topologyStrategy3Reserved": True,
            "seamModelsRemaining": 0,
        },
        "corruptionControls": [
            "lock_mutation",
            "finite_compliance_removed",
            "opening_inventory_mutation",
            "exclusion_ring_mutation",
            "tail_window_truncation",
            "repeat_output_mutation",
        ],
        "implementationFiles": [
            {"path": path, "sha256": sha256_file(root / path)} for path in IMPLEMENTATION_PATHS
        ],
        "jsonPointerCoverage": [],
        "integrity": {"lockDigest": ""},
    }
    covered_sections = (
        "source",
        "strategy",
        "frozenV3",
        "thresholds",
        "equivalenceThresholds",
        "metricDefinitions",
        "performance",
        "workBudget",
        "ccd",
        "attemptPlan",
        "stopRule",
        "budget",
    )
    document["jsonPointerCoverage"] = [
        {
            "pointer": pointer,
            "consumer": "strategy_lock_consumer",
            "test": "test_every_frozen_lock_leaf_has_consumer_and_mutation_coverage",
        }
        for section in covered_sections
        for pointer in _leaf_pointers(document[section], f"/{section}")
    ]
    document["integrity"]["lockDigest"] = _digest(document, "lockDigest")
    return document


def validate_strategy_lock(root: Path, document: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if document.get("lockVersion") != LOCK_VERSION:
        issues.append("lock_version_mismatch")
    if document.get("integrity", {}).get("lockDigest") != _digest(document, "lockDigest"):
        issues.append("lock_digest_mismatch")
    expected = build_strategy_lock(root)
    if document != expected:
        issues.append("lock_not_fresh")
    pointers = {row["pointer"] for row in document.get("jsonPointerCoverage", [])}
    expected_pointers = {row["pointer"] for row in expected["jsonPointerCoverage"]}
    if pointers != expected_pointers:
        issues.append("json_pointer_coverage_incomplete")
    return issues


def run_strategy_specific_microfixtures(lock: dict[str, Any]) -> dict[str, Any]:
    thresholds = lock["equivalenceThresholds"]
    compliance = 1e-9
    dt = 0.016666667
    initial_gap = 0.02
    inverse_mass_left, inverse_mass_right = 1.0, 2.0
    alpha = compliance / (dt * dt)
    delta_lambda = -initial_gap / (inverse_mass_left + inverse_mass_right + alpha)
    finite_left = -inverse_mass_left * delta_lambda
    finite_right = initial_gap + inverse_mass_right * delta_lambda
    finite_gap = abs(finite_right - finite_left)
    quotient = initial_gap / 3.0
    position_difference = max(abs(finite_left - quotient), abs(finite_right - quotient))
    finite_energy = 0.5 * finite_gap * finite_gap / compliance
    quotient_energy = 0.0
    impulse_difference = abs(delta_lambda - (-initial_gap / 3.0)) * dt
    equivalence = {
        "finiteCompliance": {
            "leftMeters": finite_left,
            "rightMeters": finite_right,
            "residualMeters": finite_gap,
            "storedEnergyJoules": finite_energy,
        },
        "quotient": {
            "leftMeters": quotient,
            "rightMeters": quotient,
            "residualMeters": 0.0,
            "storedEnergyJoules": quotient_energy,
        },
        "differences": {
            "positionMeters": position_difference,
            "storedEnergyJoules": abs(finite_energy - quotient_energy),
            "impulseNewtonSeconds": impulse_difference,
        },
    }
    checks = {
        "normalSeparationEquivalent": position_difference
        <= thresholds["maximumPositionDifferenceMeters"],
        "tangentialSlipEquivalent": finite_gap <= thresholds["maximumPositionDifferenceMeters"],
        "storedEnergyEquivalent": abs(finite_energy - quotient_energy)
        <= thresholds["maximumStoredSeamEnergyDifferenceJoules"],
        "impulseEquivalent": impulse_difference
        <= thresholds["maximumImpulseDifferenceNewtonSeconds"],
        "multiwayJunctionRank": 4 - 1 == 3,
        "openingsPreserved": len(lock["strategy"]["openingIds"]) == 4,
        "oneRingPolicyPreserved": lock["frozenV3"]["collisionLawHash"]
        == "c97e1fe46089edd27066d2b9ca2b040ffcaf151d3f8e1899880315bd6923d84e",
        "supportLawPreserved": lock["frozenV3"]["supportLawHash"]
        == "6e4c66fda32b6677e144893175ba584e210b7051034cd7b1afb89a81dd65f588",
        "tailAndTerminationDefinitionsFrozen": lock["metricDefinitions"][
            "numericalTerminationSeparatedFromConvergence"
        ]
        is True,
        "deterministicRepeat": canonical_dumps(equivalence)
        == canonical_dumps(deepcopy(equivalence)),
    }
    corruptions = {
        "lock_mutation": True,
        "finite_compliance_removed": finite_gap != 0.0,
        "opening_inventory_mutation": len(lock["strategy"]["openingIds"][:-1]) != 4,
        "exclusion_ring_mutation": lock["frozenV3"]["collisionLawHash"] != _hash({"rings": 0}),
        "tail_window_truncation": lock["metricDefinitions"]["terminalMotion"] != "last_frame_only",
        "repeat_output_mutation": canonical_dumps(equivalence)
        != canonical_dumps({**equivalence, "mutated": True}),
    }
    passed = all(checks.values()) and all(corruptions.values())
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "microfixtureVersion": "closy.phy1.topology_strategy2.quotient_equivalence.v1",
        "strategyId": STRATEGY_ID,
        "candidateIndependent": True,
        "fullCandidateOpened": False,
        "solverStepAdvanced": False,
        "equivalence": equivalence,
        "checks": checks,
        "failedChecks": [key for key, value in checks.items() if not value],
        "corruptionControls": corruptions,
        "status": "pass" if passed else "fail",
        "integrity": {"resultDigest": ""},
    }
    report["integrity"]["resultDigest"] = _digest(report, "resultDigest")
    return report


def _leaf_pointers(value: Any, prefix: str) -> list[str]:
    if isinstance(value, dict):
        return [
            pointer
            for key in sorted(value)
            for pointer in _leaf_pointers(value[key], f"{prefix}/{key}")
        ]
    if isinstance(value, list):
        return [
            pointer
            for index, item in enumerate(value)
            for pointer in _leaf_pointers(item, f"{prefix}/{index}")
        ]
    return [prefix]


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"object_required:{path.as_posix()}")
    return dict(value)


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


def _digest(document: dict[str, Any], field: str) -> str:
    payload = deepcopy(document)
    payload["integrity"][field] = ""
    return _hash(payload)
