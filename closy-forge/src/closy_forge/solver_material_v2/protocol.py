from __future__ import annotations

from collections import Counter
from typing import Any

from . import EVIDENCE_CLASS, PROTOCOL_ID, SOLVER_ROUTE
from .common import canonical_digest
from .units import FIELD_ORDER, SIX_FIELD_ORDER, unit_registry

FAMILIES = ("tshirt", "sleeveless_top", "simple_skirt")
SPECIMENS = (
    "warp_extension",
    "weft_extension",
    "bias_shear",
    "cantilever_bend",
    "free_decay",
    "inclined_friction",
    "impact_rebound",
    "contact_control",
)
CONTROL_NAMES = (
    "shuffled_observations",
    "wrong_orientation",
    "wrong_units",
    "wrong_family",
    "time_shuffled_damping",
    "contact_disabled_friction_restitution",
    "duplicated_observations",
    "missing_inference_load",
    "lineage_substitution",
    "target_leakage_import",
)
MOTION_IDS = tuple(f"motion-{index:02d}" for index in range(8))


def build_protocol() -> dict[str, Any]:
    tuples = _tuple_plan()
    thresholds = _thresholds()
    protocol: dict[str, Any] = {
        "schemaVersion": 2,
        "protocolId": PROTOCOL_ID,
        "protocolVersion": "closy.solver_material_geometric_source_guarded.v2",
        "evidenceClass": EVIDENCE_CLASS,
        "canonicalSolverRoute": SOLVER_ROUTE,
        "legacyV1": {
            "result": "source_guarded_synthetic_capture_reconstruction_v2_failed"
            if False
            else "source_guarded_synthetic_solver_material_v1_failed",
            "preserved": True,
            "limitations": "correlated_scalar_toy_chains_without_2d_or_3d_xpbd_specimens",
        },
        "fieldOrder": list(FIELD_ORDER),
        "sixFieldMetricOrder": list(SIX_FIELD_ORDER),
        "specimenFamilies": list(SPECIMENS),
        "garmentFamilies": list(FAMILIES),
        "tuplePlan": tuples,
        "units": unit_registry(),
        "splitPolicy": {
            "developmentTuples": 48,
            "lockedTuples": 24,
            "inferenceObservationsPerLockedTuple": 6,
            "withheldLoadsPerLockedTuple": 2,
            "withheldGeometryPerLockedTuple": 1,
            "withheldPredictionsPerLockedTuple": 4,
            "unseenMotionsPerFamilyPerLockedTuple": 8,
            "identityDisjoint": True,
            "seedDisjoint": True,
            "heldOutCombinationDisjoint": True,
            "interpolationAndExtrapolationReportedSeparately": True,
        },
        "solverConfigurations": {
            "highResolutionTruth": {
                "mesh": [7, 7],
                "timeStepSeconds": 0.011111111111111112,
                "stepCount": 18,
                "solverIterations": 9,
                "canonicalPositionDigits": 9,
            },
            "productionInverse": {
                "mesh": [5, 5],
                "timeStepSeconds": 0.016666666666666666,
                "stepCount": 12,
                "solverIterations": 6,
                "canonicalPositionDigits": 8,
            },
        },
        "optimizerBudget": {
            "proposalCountMaximum": 145,
            "evaluationCountMaximum": 145,
            "coordinatePassesMaximum": 4,
            "wallSecondsPerTupleMaximum": 24,
            "canonicalGeometryCandidateBudgetConsumed": False,
        },
        "convergence": {
            "meshLevels": [[3, 3], [5, 5], [7, 7]],
            "timeStepSecondsLevels": [
                0.022222222222222223,
                0.016666666666666666,
                0.011111111111111112,
            ],
            "iterationLevels": [3, 6, 9],
            "primaryRelativeErrorMaximum": 0.10,
            "worstRelativeErrorMaximum": 0.15,
            "requiredNorms": [
                "position_trajectory_m",
                "displacement_m",
                "force_n",
                "energy_j_proxy",
                "contact_penetration_m",
                "contact_impulse_n_s",
                "final_shape_m",
                "motion_landmarks_m",
                "constraint_residual_m",
            ],
        },
        "identifiability": {
            "singularValueTolerance": 1e-5,
            "conditionNumberMaximum": 2500.0,
            "intervalLevel": 0.90,
            "coverageMinimum": 0.80,
            "medianNormalizedWidthMaximum": 0.50,
            "allBoundsIntervalMayPass": False,
            "minimumCausalRelativeEffect": 0.005,
        },
        "controls": [
            {
                "name": name,
                "expectation": "categorical_reject"
                if name
                in {
                    "wrong_units",
                    "duplicated_observations",
                    "missing_inference_load",
                    "lineage_substitution",
                    "target_leakage_import",
                }
                else "numeric_degradation",
                "minimumRelativeDegradation": None
                if name
                in {
                    "wrong_units",
                    "duplicated_observations",
                    "missing_inference_load",
                    "lineage_substitution",
                    "target_leakage_import",
                }
                else 0.20,
            }
            for name in CONTROL_NAMES
        ],
        "thresholdRegistry": thresholds,
        "acceptance": {
            "firstUnmetPredicateOrder": [row["id"] for row in thresholds],
            "unusedOrUnboundMetricFails": True,
            "everyActiveFieldMustBeObservable": True,
            "allRowsRemainInDenominator": True,
        },
        "failureTaxonomy": [
            "passed",
            "failed",
            "abstained",
            "timeout",
            "diverged",
            "non_finite",
            "invalid_input",
            "integrity_error",
            "unsupported",
            "not_run",
        ],
        "seedCeremony": {
            "domainSeparator": "CLOSY_SOLVER_MATERIAL_V2_LOCKED_TEST_SEED_V1",
            "derivationInputs": ["frozen_git_tree", "first_successful_exact_head_run_id"],
            "allowedDerivedSeedCount": 1,
            "alternateTriedCount": 0,
            "alternateDiscardedCount": 0,
            "governedScientificSeed": False,
            "y2Seed": False,
        },
        "contestantSandbox": {
            "network": "denied",
            "filesystem": "read_only_allowlisted_observation_payload_only",
            "truthGeneratorImport": "denied",
            "seedAccess": "denied",
            "outputRoot": "separate_bounded_root",
        },
        "artifactBudget": {
            "maximumOwnLayerBytes": 64 * 1024 * 1024,
            "maximumRetainedFiles": 1400,
            "maximumTupleSeconds": 24,
            "maximumEvaluationSeconds": 900,
        },
        "realCouponCount": 0,
        "realFabricCalibration": "not_run",
        "physicalValidation": "not_run",
        "phase7": "partial",
        "singleCanonicalEvaluation": True,
        "postResultState": "consumed_exposed_ineligible_for_successor_selection",
    }
    protocol["protocolDigest"] = canonical_digest(protocol)
    return protocol


def validate_protocol(protocol: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    rows = protocol.get("tuplePlan", [])
    if len(rows) != 72:
        failures.append("tuple_plan_denominator_invalid")
    counts = Counter(str(row.get("partition")) for row in rows)
    if counts != Counter({"development": 48, "locked": 24}):
        failures.append("tuple_partition_denominator_invalid")
    ids = [str(row.get("tupleId", "")) for row in rows]
    if len(ids) != len(set(ids)) or "" in ids:
        failures.append("tuple_identity_invalid")
    dev = {str(row.get("sourceIdentity")) for row in rows if row.get("partition") == "development"}
    locked = {str(row.get("sourceIdentity")) for row in rows if row.get("partition") == "locked"}
    if dev & locked:
        failures.append("source_identity_overlap")
    threshold_ids = [str(row.get("id", "")) for row in protocol.get("thresholdRegistry", [])]
    if threshold_ids != list(protocol.get("acceptance", {}).get("firstUnmetPredicateOrder", [])):
        failures.append("threshold_order_unbound")
    if tuple(protocol.get("fieldOrder", [])) != FIELD_ORDER:
        failures.append("field_order_invalid")
    if protocol.get("protocolDigest") != canonical_digest(protocol, "protocolDigest"):
        failures.append("protocol_digest_invalid")
    return sorted(set(failures))


def _tuple_plan() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ordinal = 0
    for partition, count in (("development", 48), ("locked", 24)):
        for index in range(count):
            family = FAMILIES[index % len(FAMILIES)]
            regime = "interpolation" if index % 2 == 0 else "extrapolation"
            rows.append(
                {
                    "tupleId": f"smv2-{partition[:3]}-{index:03d}",
                    "partition": partition,
                    "planOrdinal": ordinal,
                    "materialFamily": f"synthetic_family_{index % 8:02d}",
                    "garmentFamily": family,
                    "regime": regime,
                    "sourceIdentity": f"smv2-{partition}-source-{index:03d}",
                    "inferenceSpecimens": [
                        "warp_extension",
                        "weft_extension",
                        "bias_shear",
                        "cantilever_bend",
                        "free_decay",
                        "contact_control",
                    ],
                    "withheldLoads": [0.72 + 0.04 * (index % 3), 1.08 + 0.04 * (index % 4)],
                    "withheldGeometry": "wide_coupon" if index % 2 == 0 else "long_coupon",
                    "predictionSpecimens": [
                        "warp_extension",
                        "bias_shear",
                        "impact_rebound",
                        "inclined_friction",
                    ],
                    "unseenMotions": {garment: list(MOTION_IDS) for garment in FAMILIES},
                }
            )
            ordinal += 1
    return rows


def _thresholds() -> list[dict[str, Any]]:
    definitions = (
        ("SMV2-01", "meanNormalizedActiveFieldError", "maximum", 0.18),
        ("SMV2-02", "withheldPredictiveNrmse", "maximum", 0.16),
        ("SMV2-03", "perActiveFieldMeanMaximum", "maximum", 0.25),
        ("SMV2-04", "perActiveFieldP95Maximum", "maximum", 0.35),
        ("SMV2-05", "worstRowSixFieldNormalizedError", "maximum", 0.40),
        ("SMV2-06", "intervalCoverageOverall", "minimum", 0.80),
        ("SMV2-07", "intervalCoveragePerFieldMinimum", "minimum", 0.80),
        ("SMV2-08", "medianNormalizedIntervalWidth", "maximum", 0.50),
        ("SMV2-09", "identifiableFieldRate", "minimum", 1.0),
        ("SMV2-10", "negativeControlPassRate", "minimum", 1.0),
        ("SMV2-11", "convergencePrimaryMaximum", "maximum", 0.10),
        ("SMV2-12", "convergenceWorstMaximum", "maximum", 0.15),
        ("SMV2-13", "motionTransferNrmse", "maximum", 0.20),
        ("SMV2-14", "motionPhysicalValidityRate", "minimum", 1.0),
        ("SMV2-15", "constantPriorImprovement", "minimum", 0.01),
        ("SMV2-16", "lookupBaselineImprovement", "minimum", 0.01),
        ("SMV2-17", "wrongModelImprovement", "minimum", 0.01),
        ("SMV2-18", "terminalConservation", "minimum", 1.0),
    )
    return [
        {
            "id": identity,
            "metric": metric,
            "direction": direction,
            "limit": limit,
            "evaluatorFunction": f"evaluate_{metric}",
            "source": "development_frozen_with_non_weakenable_prompt_ceiling",
        }
        for identity, metric, direction, limit in definitions
    ]
