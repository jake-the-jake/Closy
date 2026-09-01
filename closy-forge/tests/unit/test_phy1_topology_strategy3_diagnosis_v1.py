from __future__ import annotations

import hashlib
from pathlib import Path

from closy_forge.package_io.canonical_json import read_json
from closy_forge.phy1_topology_strategy3_diagnosis_v1.protocol import (
    AUTHORITY_PATH,
    CONFIRMATION_GENERATOR_PATH,
    LOCK_PATH,
    OUTCOME_PATH,
    build_diagnosis_lock,
    build_starting_authority,
    validate_lock,
)

ROOT = Path(__file__).resolve().parents[2]


def test_unit_o_authority_and_pre_execution_lock_are_fresh() -> None:
    authority = build_starting_authority(ROOT)
    lock = build_diagnosis_lock(ROOT, authority)
    assert read_json(ROOT / AUTHORITY_PATH) == authority
    assert read_json(ROOT / LOCK_PATH) == lock
    assert read_json(ROOT / CONFIRMATION_GENERATOR_PATH) == lock["confirmationGenerator"]
    assert validate_lock(ROOT, lock) == []
    assert authority["semanticInventory"] == {
        "semanticSeamPairCount": 12,
        "semanticConstraintCount": 92,
        "openingCount": 4,
    }
    assert len(authority["actualBlobIdentities"]) == 15
    for record in authority["actualBlobIdentities"]:
        content = (ROOT / record["path"]).read_bytes()
        payload = f"blob {len(content)}\0".encode() + content
        assert record["gitBlobOidSha1"] == hashlib.sha1(payload, usedforsecurity=False).hexdigest()


def test_unit_o_keeps_confirmation_and_candidate_budgets_unspent() -> None:
    lock = read_json(ROOT / LOCK_PATH)
    generator = lock["confirmationGenerator"]
    assert generator["denominator"] == 8
    assert generator["seedRealized"] is False
    assert generator["instanceParametersRealized"] is False
    assert generator["qualificationInstances"] == []
    assert "seed" not in generator
    assert lock["maximumPreCandidateRevisions"] == 2
    assert lock["candidateCreationAllowed"] is False
    assert lock["finalStrategyConsumptionAllowed"] is False


def test_unit_o_committed_outcome_is_exactly_regenerable_when_present() -> None:
    if not (ROOT / OUTCOME_PATH).is_file():
        return
    from scripts.run_phy1_topology_strategy3_diagnosis_v1 import build, check

    documents, markdown = build(ROOT)
    check(ROOT, documents, markdown)
    outcome = documents[OUTCOME_PATH]
    assert outcome["outcomeClass"] in {
        "strategy3_class_admitted_pre_candidate",
        "no_strategy3_class_admitted_within_bounded_diagnosis",
        "diagnosis_integrity_error",
        "dependency_blocked",
    }
    assert outcome["revisionCount"] == 2
    assert outcome["candidateCreated"] is False
    assert outcome["candidateAttemptConsumed"] is False
    assert outcome["finalStrategyConsumed"] is False
