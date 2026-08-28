from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.pattern_inference.correction_session_v2 import validate_correction_session
from closy_forge.pattern_inference.dataset_v2 import validate_dataset_v2
from closy_forge.pattern_inference.evaluation_v2 import evaluate_model_v2
from closy_forge.pattern_inference.model_v2 import validate_model_v2

EVIDENCE = Path(__file__).parents[2] / "docs" / "evidence" / "phase9_learned_d0"


def _json(name: str) -> dict[str, Any]:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def test_committed_phase9_training_data_model_and_evaluation_recompute() -> None:
    dataset = _json("synthetic_dataset.json")
    split = _json("split.json")
    model = _json("model.json")
    evaluation = _json("evaluation.json")

    assert validate_dataset_v2(dataset, split) == []
    assert validate_model_v2(model) == []
    assert sha256_bytes(canonical_dumps(dataset).encode("utf-8")) == (
        "baa6a679ef5a2ca27d45ffe5f2765db40efbe6e0c4c7ced4be1752f9050dd612"
    )
    assert canonical_dumps(evaluate_model_v2(model, dataset, split)) == canonical_dumps(evaluation)


def test_committed_phase9_execution_and_correction_scope_is_truthful() -> None:
    evidence = _json("execution_evidence.json")
    correction = _json("correction_session.json")
    dataset_card = _json("dataset_card.json")
    model_card = _json("model_card.json")

    assert evidence["commitSha"] == "de1177268cd09e6988689fa175638492757a9bed"
    assert evidence["training"]["actualOptimizerExecuted"] is True
    assert evidence["training"]["wallMilliseconds"] > 0
    assert evidence["training"]["memory"]["peakWorkingSetBytes"] > 0
    assert evidence["inference"]["medianMilliseconds"] > 0
    assert evidence["inference"]["p95Milliseconds"] >= evidence["inference"]["medianMilliseconds"]
    assert evidence["postSettle"]["allPackagesValidated"] is True
    assert evidence["postSettle"]["allFitsAccepted"] is True
    assert evidence["postSettle"]["allDecodedSilhouetteComparisonsAccepted"] is True
    assert {record["family"] for record in evidence["postSettle"]["records"]} == {
        "sleeveless_top",
        "simple_skirt",
    }
    assert evidence["claims"] == {
        "globalPhase9Complete": False,
        "humanReviewed": False,
        "mobilePerformance": False,
        "realOrPublicCaptureGeneralisation": False,
    }
    assert validate_correction_session(correction) == []
    assert dataset_card["privateData"] is False
    assert dataset_card["realCaptureData"] is False
    assert model_card["superiorityClaim"].startswith("no_superiority")
