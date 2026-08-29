from __future__ import annotations

import json
from pathlib import Path
from typing import Any


EVIDENCE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "evidence"
    / "phase9_structured_v2"
)
SOURCE_TREE_HASH = "6c6471f3244f2ef8ebf2ca6c82643e275471f6c4010a7c262be54b5a376baddb"


def _load(name: str) -> dict[str, Any]:
    return json.loads((EVIDENCE_ROOT / name).read_text(encoding="utf-8"))


def test_generated_evidence_preserves_scoped_partial_truth() -> None:
    marker = _load(".closy-forge-owned.json")
    attestation = _load("attestation.json")
    summary = _load("execution_summary.json")
    e1 = _load("e1_evaluation.json")
    e1_execution = _load("e1_execution.json")
    e2 = _load("e2_evaluation.json")
    e2_dataset = _load("e2_dataset_manifest.json")

    assert marker["owner"] == "closy-forge"
    assert marker["purpose"] == "phase9-structured-v2"
    assert attestation["sourceTree"]["hash"] == SOURCE_TREE_HASH
    assert summary["sourceTreeHash"] == SOURCE_TREE_HASH
    assert summary["globalPhase9"] == "partial"
    assert summary["humanReviewStatus"] == "not_run"
    assert summary["privateUserEvidence"] is False

    assert e1["acceptance"]["status"] == "partial"
    assert e1["acceptance"]["failedChecks"] == [
        "calibration",
        "equalInputBaseline",
        "familyTop1",
    ]
    assert e1_execution["unassisted"]["acceptedCount"] == 5
    assert e1_execution["unassisted"]["learnedSuccessCount"] == 4
    assert e1_execution["unassisted"]["fallbackSuccessCountedInLearnedMetrics"] is False

    assert e2_dataset["counts"] == {"test": 48, "train": 128, "validation": 32}
    assert e2["acceptance"]["status"] == "executed_feasibility_partial"
    assert e2["acceptance"]["failedChecks"] == [
        "equalInputBaseline",
        "parseTypeSemantic",
        "primaryStructuralMetric",
        "programValidity",
    ]
    assert e2["metrics"]["acceptedCount"] == 24
    assert e2["metrics"]["macroStructureTokenF1"] == 0.25


def test_phase14_and_correction_evidence_keep_authority_bounded() -> None:
    phase14 = _load("phase14_integrated_evaluation.json")
    correction = _load("correction_surface.json")
    replay = _load("source_replay_map.json")

    assert phase14["evaluation"]["material"]["topOneAccuracy"] == 0.555555555556
    assert phase14["evaluation"]["failureAndQuality"]["macroF1"] == 0.704125286478
    assert phase14["evaluation"]["ood"]["challengeRejectionRate"] == 1.0
    assert phase14["authority"]["deterministicValidatorsFinal"] is True
    assert phase14["largeModelBoundary"]["execution"] == "not_run"
    assert phase14["claims"]["globalPhase14Complete"] is False

    assert correction["humanReviewStatus"] == "not_run"
    assert correction["networkUsed"] is False
    assert correction["containsRawImagePath"] is False
    assert replay["duplicateBusinessPatches"] == 0
    assert replay["phase14Replay"]["disposition"] == "replayed"
    assert replay["sharedWorkflowPatch"]["disposition"] == "skipped_with_reason"
