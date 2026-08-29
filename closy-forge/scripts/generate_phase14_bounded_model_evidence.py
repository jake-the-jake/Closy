from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from closy_forge.bounded_models.dataset import build_phase14_dataset
from closy_forge.bounded_models.evaluation import evaluate_phase14_model
from closy_forge.bounded_models.model import train_phase14_model
from closy_forge.package_io.canonical_json import canonical_dumps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    dataset = build_phase14_dataset()
    model = train_phase14_model(dataset)
    evaluation = evaluate_phase14_model(dataset, model)
    evidence = _evidence(dataset, model, evaluation)
    _write(root / "models/phase14/material_ranker_d0_v1.json", _material_artifact(model))
    _write(root / "models/phase14/failure_quality_d0_v1.json", _failure_artifact(model))
    _write(root / "docs/evidence/phase14_solver_fixture_dataset_v1.json", dataset)
    _write(root / "docs/evidence/phase14_bounded_models_v1.json", evidence)
    print(
        json.dumps(
            {
                "datasetHash": dataset["integrity"]["datasetHash"],
                "modelHash": model["integrity"]["modelHash"],
                "evaluationHash": evaluation["integrity"]["evaluationHash"],
                "testMaterial": evaluation["material"],
                "testFailure": {
                    "macroF1": evaluation["failureAndQuality"]["macroF1"],
                    "macroBrier": evaluation["failureAndQuality"]["macroBrierScore"],
                },
            },
            sort_keys=True,
        )
    )
    return 0


def _evidence(
    dataset: dict[str, Any], model: dict[str, Any], evaluation: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "evidenceVersion": "closy.phase14.bounded_models_evidence.d0.v1",
        "scope": "source_only_project_authored_cpu_fixture_models",
        "phaseStatus": "partial",
        "dataset": {
            "hash": dataset["integrity"]["datasetHash"],
            "rows": dataset["rowCount"],
            "scenarios": dataset["scenarioCounts"],
            "presetCandidates": dataset["candidatePresetCount"],
            "card": "docs/dataset_cards/phase14_project_authored_solver_fixtures_v1.md",
        },
        "model": {
            "hash": model["integrity"]["modelHash"],
            "weightsHash": model["integrity"]["weightsHash"],
            "card": "docs/model_cards/phase14_bounded_models_v1.md",
            "selectedTrial": model["training"]["selectedTrialId"],
        },
        "evaluation": evaluation,
        "licences": [
            {
                "component": "project-authored numerical solver fixtures and generated rows",
                "licence": "repository project-owned source licence",
                "external": False,
            }
        ],
        "provenance": {
            "externalDatasetUsed": False,
            "privateUserDataUsed": False,
            "licensedBodyOrGarmentDataUsed": False,
            "syntheticGenerator": "closy_forge.bounded_models.dataset",
            "numericalOutcomeSource": "closy_forge.bounded_models.solver_fixtures",
        },
        "resourceUse": {
            "profile": "CPU-only pure Python deterministic training",
            "trialCount": model["training"]["trialCount"],
            "epochsPerTrial": model["training"]["epochsPerTrial"],
            "maximumWallSeconds": 3600,
            "maximumCpuSeconds": 3600,
            "maximumMemoryBytes": 2147483648,
            "canonicalWallClockExcludedBecauseNondeterministic": True,
        },
        "rollback": {
            "trigger": "OOD, low confidence, model error, or deterministic validator rejection",
            "action": "use versioned deterministic material preset and validator-only result",
        },
        "knownFailures": [
            "project-authored scalar fixture is not the production cloth solver",
            "no real-fabric measurements or private-user outcomes",
            "no mobile, GPU, thermal, battery, human-review, or provider evidence",
            "broader visual-geometry-model fine-tuning not started",
            "predictions cannot override deterministic validators",
        ],
        "integrationTruth": {
            "globalPhase14Complete": False,
            "phase11DynamicExecuted": False,
            "z2Executed": False,
            "phy1Passed": False,
            "structuredPatternModelExtended": False,
        },
    }


def _material_artifact(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "modelVersion": model["modelVersion"],
        "featureNames": model["featureNames"],
        "normalization": model["normalization"],
        "oodEnvelope": model["oodEnvelope"],
        "materialRanker": model["materialRanker"],
        "fallbackPolicy": model["fallbackPolicy"],
        "training": model["training"],
        "integrity": model["integrity"],
        "authority": model["authority"],
    }


def _failure_artifact(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "modelVersion": model["modelVersion"],
        "featureNames": model["featureNames"],
        "failureTargets": model["failureTargets"],
        "normalization": model["normalization"],
        "oodEnvelope": model["oodEnvelope"],
        "failurePredictor": model["failurePredictor"],
        "fallbackPolicy": model["fallbackPolicy"],
        "training": model["training"],
        "integrity": model["integrity"],
        "authority": model["authority"],
    }


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_dumps(value).rstrip("\n") + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
