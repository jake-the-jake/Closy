from __future__ import annotations

from pathlib import Path

from closy_forge.package_io.hashing import sha256_file
from closy_forge.simulation_topology_v2.phy1_seam_support_v3 import (
    float32_roundtrip_identity_microfixture,
    load_phy1_v3_inputs,
    run_analytic_microfixtures,
)
from closy_forge.simulation_topology_v2.seam_support_v3 import (
    LOCK_PATH,
    LOCK_RAW_SHA256,
    audit_support_inventory,
    load_experiment_lock,
    support_strength,
)

ROOT = Path(__file__).resolve().parents[2]


def test_phy1_v3_lock_and_candidate_identity_are_immutable() -> None:
    assert sha256_file(ROOT / LOCK_PATH) == LOCK_RAW_SHA256
    lock = load_experiment_lock(ROOT)
    inputs = load_phy1_v3_inputs(ROOT, lock)

    assert lock["integrity"]["physicalCandidateId"] == (
        "physical.candidate.phy1_seam_support_v3.1152728eaf2588b4f674339f"
    )
    assert inputs.junction_graph["audit"]["status"] == "pass"
    assert len(inputs.junction_graph["classes"]) == 6
    assert all(
        item["constraintRank"] == item["solverParticleCount"] - 1
        for item in inputs.junction_graph["classes"]
    )
    assert all(
        item["restNormalGapMeters"] == 0.0 and item["restBinormalGapMeters"] == 0.0
        for item in inputs.seam_records
    )


def test_phy1_v3_temporary_supports_are_bounded_and_fully_release() -> None:
    lock = load_experiment_lock(ROOT)
    inputs = load_phy1_v3_inputs(ROOT, lock)
    audit = audit_support_inventory(inputs.supports, lock)

    assert audit["status"] == "pass"
    assert 0 < audit["supportCount"] <= 8
    assert {item["bodyRegion"] for item in audit["supports"]} == {
        "left_shoulder",
        "right_shoulder",
    }
    assert support_strength(7, lock) == 1.0
    assert 0.0 < support_strength(12, lock) < 1.0
    assert support_strength(16, lock) == 0.0


def test_phy1_v3_analytic_microfixtures_and_corruption_controls_pass() -> None:
    lock = load_experiment_lock(ROOT)
    inputs = load_phy1_v3_inputs(ROOT, lock)
    report = run_analytic_microfixtures(ROOT, lock, inputs)

    assert report["status"] == "pass"
    assert report["failedChecks"] == []
    assert len(report["corruptionControls"]) == len(lock["corruptionControls"])
    assert all(item["detected"] for item in report["corruptionControls"])
    cases = {item["caseId"]: item for item in report["seamCases"]}
    assert cases["seam.normal_only"]["measured"] == {
        "crackMeters": 0.003,
        "tangentialSlipMeters": 0.0,
        "euclideanGapMeters": 0.003,
    }
    assert cases["seam.tangent_only"]["measured"] == {
        "crackMeters": 0.0,
        "tangentialSlipMeters": 0.004,
        "euclideanGapMeters": 0.004,
    }


def test_phy1_v3_float32_reporting_repair_has_independent_microfixture() -> None:
    report = float32_roundtrip_identity_microfixture()

    assert report["status"] == "pass"
    assert all(report["checks"].values())
    assert report["originalValues"] != report["persistedValues"]
    assert report["firstByteSha256"] == report["secondByteSha256"]
