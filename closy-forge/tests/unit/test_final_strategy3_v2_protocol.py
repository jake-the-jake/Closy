from __future__ import annotations

import hashlib
import json
from pathlib import Path

from closy_forge.final_strategy3_v2.authority import write_public_failure
from closy_forge.final_strategy3_v2.protocol import (
    LOCK_PATH,
    OUTCOMES,
    STRATEGY_ID,
    build_protocol,
    load_protocol,
    validate_implementation,
    validate_protocol,
)

ROOT = Path(__file__).resolve().parents[2]


def test_design_reservation_precedes_implementation_and_fixes_the_only_strategy() -> None:
    reservation = json.loads(
        (ROOT / "fixtures/final_strategy3_v2/strategy_design_reservation.json").read_text(
            encoding="utf-8"
        )
    )
    assert reservation["strategyId"] == STRATEGY_ID
    assert reservation["strategyClass"] == (
        "seam-sequence-preserving conforming panel remesh with duplicated seam degrees of "
        "freedom and rebuilt transfer/binding ancestry"
    )
    assert reservation["budget"]["topologyStrategies"] == {
        "available": 0,
        "reserved": 1,
        "consumed": 2,
        "remaining": 0,
    }
    assert reservation["candidatePolicy"]["canonicalSourceExecutionAllowedInUnitU"] is False


def test_protocol_freezes_future_c3_and_z2_before_candidate() -> None:
    protocol = build_protocol(
        ROOT,
        implementation_files=[{"path": "synthetic", "sha256": "0" * 64}],
        preflight_run_id="public-preflight",
        preflight_image_id="sha256:" + "0" * 64,
    )
    assert validate_protocol(ROOT, protocol) == []
    assert protocol["officialSeedCreated"] is False
    assert protocol["candidatePolicy"]["canonicalCandidateCreatedInUnitU"] is False
    assert protocol["futurePostTopologyC3"]["denominator"] == 12
    assert protocol["futurePostTopologyC3"]["selectionRule"] == (
        "all_prescribed_states_and_final_solver_frame"
    )
    assert protocol["futureGateZ2Core"]["kinematicSelectionRule"] == "all_prescribed_states"
    assert protocol["budgetTransition"]["topologyStrategies"]["remaining"] == 0
    assert protocol["budgetTransition"]["candidateAttempts"]["remaining"] == 1


def test_contestant_image_does_not_contain_generator_or_oracle() -> None:
    dockerfile = (ROOT / "docker/final_strategy3_v2/Dockerfile").read_text(encoding="utf-8")
    runner = (ROOT / "docker/final_strategy3_v2/runner.py").read_text(encoding="utf-8")
    assert "recovery_foundation_v2" not in dockerfile
    assert "topology_holdout" not in runner
    assert "oracle" not in runner.lower()
    assert "fixture.json" in runner


def test_failure_diagnostics_remove_private_material_and_fail_closed(tmp_path: Path) -> None:
    private = tmp_path / ".authority_private_until_output_freeze"
    private.mkdir()
    (private / "secret").write_text("not public", encoding="utf-8")
    failure = write_public_failure(
        tmp_path,
        failure_type="SyntheticFailure",
        stage="preflight",
        seed_created=True,
        workflow_run_id="test",
        workflow_job_id="test",
    )
    assert failure["outcome"] == OUTCOMES[2]
    assert failure["qualificationRetryAllowed"] is False
    assert failure["privateArtifactsRemoved"] is True
    assert not private.exists()


def test_pr52_raw_and_integrity_authorities_remain_byte_identical() -> None:
    expected = {
        "docs/evidence/phy1_topology_strategy3_diagnosis_v1/unit_o_outcome.json": (
            "fd9af53158b6e3a8f1951367751ed5ad912351d10f0e21e836f5b3db3e2cbf79"
        ),
        "docs/evidence/phy1_topology_strategy3_diagnosis_v1/integrity_attestation.json": (
            "c8bc078c42e3c827cc537562a100c7279cd48c61320fcfa8ed5c15b2e54813fc"
        ),
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


def test_final_lock_is_self_consistent_when_present() -> None:
    if not (ROOT / LOCK_PATH).is_file():
        return
    protocol = load_protocol(ROOT)
    assert validate_protocol(ROOT, protocol) == []
    assert validate_implementation(ROOT, protocol) == []
