from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from closy_forge.package_io.canonical_json import read_json
from closy_forge.phy1_topology_strategy2_v4.strategy import (
    build_strategy_lock,
    validate_strategy_lock,
)

ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "fixtures/phy1_topology_strategy2_v4/strategy_lock.json"


def test_strategy_two_lock_is_fresh_and_preserves_v3_laws() -> None:
    lock = dict(read_json(LOCK_PATH))
    assert lock == build_strategy_lock(ROOT)
    assert validate_strategy_lock(ROOT, lock) == []
    assert lock["strategy"]["classification"] == "topology_or_dof_representation"
    assert lock["frozenV3"]["seamLawHash"] == (
        "e7456d10f1f9648b26cd6710d3b6af932945482ab2d1afd57b46c13784e3f155"
    )
    assert lock["budget"] == {
        "candidateAttemptsMaximum": 1,
        "candidateAttemptsConsumedBeforeExecution": 0,
        "topologyStrategy3Reserved": True,
        "seamModelsRemaining": 0,
    }


def test_every_frozen_lock_leaf_has_consumer_and_mutation_coverage() -> None:
    lock = dict(read_json(LOCK_PATH))
    coverage = lock["jsonPointerCoverage"]
    assert len(coverage) == len({row["pointer"] for row in coverage})
    assert all(row["consumer"] == "strategy_lock_consumer" for row in coverage)
    assert all(row["test"].startswith("test_every_frozen_lock_leaf") for row in coverage)
    mutated = deepcopy(lock)
    mutated["thresholds"]["maximumSeamCrackMeters"] = 1.0
    assert set(validate_strategy_lock(ROOT, mutated)) == {
        "lock_digest_mismatch",
        "lock_not_fresh",
    }
