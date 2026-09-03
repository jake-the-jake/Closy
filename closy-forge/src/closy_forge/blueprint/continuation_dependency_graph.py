from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

CONTINUATION_GRAPH_VERSION = "closy.blueprint_continuation.bloblock_d0v4_phy1.v1"


def build_continuation_dependency_graph(
    *,
    strategy3_outcome: dict[str, Any],
    d0_v4_outcome: dict[str, Any],
    synthetic_calibration_report: dict[str, Any],
    coverage_counts: dict[str, int],
    phase_statuses: dict[str, str],
) -> dict[str, Any]:
    if strategy3_outcome.get("literalOutcome") != ("strategy3_dependency_blocked_before_seed_v3"):
        raise ValueError("unexpected_strategy3_outcome")
    if d0_v4_outcome.get("literalOutcome") != ("completed_public_test_failed_ac_readiness_margins"):
        raise ValueError("unexpected_d0_v4_outcome")
    if (
        synthetic_calibration_report.get("readiness", {}).get(
            "acceptedForProjectAuthoredSyntheticCalibration"
        )
        is not True
    ):
        raise ValueError("synthetic_calibration_not_accepted")

    nodes = [
        _node(
            "Z",
            ["Y1"],
            "ineligible",
            "unit_y1_admission_absent_after_preseed_dependency_block",
        ),
        _node("AA", ["Z"], "ineligible", "no_canonical_candidate"),
        _node("AB", ["AA"], "ineligible", "no_exact_candidate_c3_z1_lineage"),
        _node(
            "AD",
            ["AC"],
            "ineligible",
            "unit_ac_public_test_failed_frozen_worst_parameter_margin",
        ),
        _node(
            "AE-01-D0-RP-15",
            ["Z"],
            "ineligible",
            "no_unit_z_solver_candidate_evidence",
        ),
        _node(
            "AE-02-D0-RP-10-11",
            ["Z", "AA"],
            "ineligible",
            "no_exact_candidate_z1_or_mt1_evidence",
        ),
        _node(
            "AE-03-sleeveless-image-conditioned-development",
            ["AC"],
            "ineligible",
            "d0_v4_public_readiness_failed",
        ),
        _node(
            "AE-04-phase7-synthetic-mechanical-calibration",
            [],
            "implemented",
            "dependency_ready_independent_nonqualification_engineering",
        ),
        _node(
            "AE-05-qualified-additional-family-physics",
            ["Z", "AE-04-phase7-synthetic-mechanical-calibration"],
            "ineligible",
            "qualified_topology_candidate_absent",
        ),
        _node(
            "AE-06-phase12-mobile-runtime",
            ["AB"],
            "dependency_and_external_blocked",
            "scoped_z2_absent_and_measured_mobile_device_runtime_unavailable",
        ),
        _node(
            "AE-07-phase13-avatar-layer-collision",
            ["AB", "AE-06-phase12-mobile-runtime"],
            "dependency_and_external_blocked",
            "post_z2_runtime_lineage_licensed_avatar_and_real_layer_collision_unavailable",
        ),
        _node(
            "AE-08-phase14-trained-models",
            [],
            "dependency_blocked",
            "dataset_and_evaluation_maturity_prerequisites_not_met",
        ),
        _node(
            "AE-09-real-private-captures",
            ["P1"],
            "externally_blocked",
            "gate_p1_private_capture_authority_and_controls_not_available",
        ),
    ]
    graph: dict[str, Any] = {
        "schemaVersion": 1,
        "graphVersion": CONTINUATION_GRAPH_VERSION,
        "sourceOutcomes": {
            "unitY1": strategy3_outcome["literalOutcome"],
            "unitY1OutcomeDigest": strategy3_outcome["outcomeDigest"],
            "unitAC": d0_v4_outcome["literalOutcome"],
            "unitACResultDigest": d0_v4_outcome["resultDigest"],
            "unitAD": "not_run_ineligible",
        },
        "nodes": nodes,
        "selectedRunnableUnit": "AE-04-phase7-synthetic-mechanical-calibration",
        "selectedUnitOutcome": ("implemented_project_authored_synthetic_mechanical_calibration_v2"),
        "coverageSnapshot": {
            "total": sum(coverage_counts.values()),
            "counts": dict(sorted(coverage_counts.items())),
            "phaseStatuses": dict(sorted(phase_statuses.items())),
            "phase7StatusAfterUnitAE": "partial",
            "coveragePromotionFromUnitAE": False,
            "reason": (
                "synthetic_coupon_calibration_advances_engineering_evidence_but_does_not_"
                "satisfy_real_fabric_or_production_motion_requirements"
            ),
        },
        "remainingDependencyGraph": {
            "dependencyReadyImplementationUnits": [],
            "ineligibleOrBlockedUnits": [
                node["nodeId"] for node in nodes if node["status"] != "implemented"
            ],
            "exactNextAction": (
                "obtain_authorized_measured_real_fabric_coupon_data_and_preregister_a_"
                "separate_calibration_validation_protocol"
            ),
        },
        "unsupportedEvidence": list(synthetic_calibration_report["unsupportedEvidence"]),
        "integrity": {"graphHash": ""},
    }
    graph["integrity"]["graphHash"] = hash_continuation_dependency_graph(graph)
    return graph


def validate_continuation_dependency_graph(graph: dict[str, Any]) -> None:
    if graph.get("graphVersion") != CONTINUATION_GRAPH_VERSION:
        raise ValueError("continuation_graph_version_invalid")
    if graph.get("integrity", {}).get("graphHash") != (hash_continuation_dependency_graph(graph)):
        raise ValueError("continuation_graph_hash_mismatch")
    implemented = [node for node in graph.get("nodes", []) if node.get("status") == "implemented"]
    if [node.get("nodeId") for node in implemented] != [
        "AE-04-phase7-synthetic-mechanical-calibration"
    ]:
        raise ValueError("continuation_graph_implemented_set_invalid")
    if graph.get("remainingDependencyGraph", {}).get("dependencyReadyImplementationUnits") != []:
        raise ValueError("continuation_graph_has_unexecuted_ready_unit")


def hash_continuation_dependency_graph(graph: dict[str, Any]) -> str:
    payload = deepcopy(graph)
    payload["integrity"]["graphHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _node(node_id: str, dependencies: list[str], status: str, reason: str) -> dict[str, Any]:
    return {
        "nodeId": node_id,
        "dependencies": dependencies,
        "status": status,
        "reason": reason,
    }
