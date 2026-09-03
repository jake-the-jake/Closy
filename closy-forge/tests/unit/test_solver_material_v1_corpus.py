from __future__ import annotations

from pathlib import Path

from closy_forge.solver_material_v1.common import read_json
from closy_forge.solver_material_v1.corpus import CORPUS_VERSION

CORPUS = Path(__file__).resolve().parents[2] / "fixtures/solver_material_v1/locked_corpus.json"


def test_locked_corpus_preserves_every_frozen_denominator() -> None:
    corpus = read_json(CORPUS)
    assert corpus["corpusVersion"] == CORPUS_VERSION
    assert corpus["tupleCount"] == 64
    assert corpus["developmentTupleCount"] == 48
    assert corpus["lockedTestTupleCount"] == 16
    assert corpus["wholeMaterialHoldoutCount"] == 8
    assert corpus["executedCouponFamilyCount"] == 10
    assert corpus["supportedFieldCount"] == 8
    assert all(len(row["coupons"]) == 10 for row in corpus["rows"])


def test_interventions_change_executed_trajectories() -> None:
    corpus = read_json(CORPUS)
    assert len(corpus["interventions"]) == 8
    responsive = [row for row in corpus["interventions"] if row["trajectoryResponds"]]
    assert len(responsive) >= 6
    assert all(len(set(row["trajectoryDigests"])) == 3 for row in responsive)
    assert {row["field"] for row in corpus["interventions"] if not row["trajectoryResponds"]} == {
        "friction",
        "restitution",
    }


def test_unsupported_mode_stays_in_report() -> None:
    corpus = read_json(CORPUS)
    assert corpus["unsupported"] == [
        {
            "family": "compression_thickness",
            "status": "not_run",
            "reason": "reference_backend_has_no_thickness_compression_constraint",
        }
    ]
