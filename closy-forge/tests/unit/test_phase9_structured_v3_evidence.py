from __future__ import annotations

from pathlib import Path

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.pattern_inference.e1_kernel_v3 import validate_e1_model_v3
from closy_forge.pattern_inference.structured_decoder_v2 import validate_structured_model_v2

EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "phase9_structured_v3"


def test_full_v3_corpus_and_models_are_compact_valid_and_honestly_losing() -> None:
    corpus = read_json(EVIDENCE / "corpus_manifest.json")
    e1_model = read_json(EVIDENCE / "e1_model.json")
    e1 = read_json(EVIDENCE / "e1_evaluation.json")
    e2_model = read_json(EVIDENCE / "e2_model.json")
    e2 = read_json(EVIDENCE / "e2_evaluation.json")

    assert corpus["counts"] == {
        "programmeIdentities": 512,
        "captureSets": 2048,
        "decodedImages": 8192,
        "families": 8,
        "captureVariantsPerProgramme": 4,
        "viewsPerCapture": 4,
    }
    assert corpus["sourceRepresentation"] == "assembled_reference_3d_simulation_mesh"
    assert corpus["physicalSettleClaimed"] is False
    assert corpus["rawRastersPersisted"] is False
    assert validate_e1_model_v3(e1_model) == []
    assert validate_structured_model_v2(e2_model) == []
    assert e1["acceptance"]["promotionClass"] == "losing_experiment"
    assert e1["acceptance"]["learnedRouteDefault"] is False
    assert e1["leakageAudit"]["candidateApiAcceptsTarget"] is False
    assert e2["acceptance"]["status"] == "failed"
    assert e2["acceptance"]["learnedRouteDefault"] is False
    assert e2["metrics"]["compileTopologyValidityWithoutRepair"] == 1.0
    assert e2["metrics"]["reference3dExecutionWithoutRepair"] == 1.0
    assert e2["baselines"]["frozenE1Adaptation"]["frozenE1ActuallyExecuted"] is True
    assert e2["pairedBootstrap"]["unit"] == "source_program_identity"


def test_phase14_v3_evidence_retains_corrected_context_and_weak_targets() -> None:
    phase14 = read_json(EVIDENCE / "phase14_integrated_evaluation.json")

    assert phase14["dataset"]["currentExecutablePathSources"]["z1"]["defaultFamilies"] == {
        "passed": 9,
        "total": 9,
    }
    assert phase14["dataset"]["currentExecutablePathSources"]["z1"]["parameterBreadth"] == {
        "passed": 6,
        "total": 25,
    }
    assert phase14["confidenceIntervals"]["clusterKey"] == "scenarioId"
    assert phase14["evaluationCorrections"]["formerAcceptedFilterBugPresent"] is False
    assert all(item["predictedCount"] > 0 for item in phase14["ablations"].values())
    per_target = phase14["evaluation"]["failureAndQuality"]["perTarget"]
    assert per_target["excessiveStrain"]["f1"] == 0.4
    assert per_target["seamContinuityRisk"]["f1"] == 0.4
    assert phase14["acceptance"]["status"] == "partial"
    assert phase14["authority"]["deterministicValidatorsFinal"] is True


def test_v3_attestation_hashes_every_committed_document_without_runtime_fields() -> None:
    attestation = read_json(EVIDENCE / "attestation.json")
    for name, expected in attestation["documentHashesWithoutRuntime"].items():
        document = _without_runtime(read_json(EVIDENCE / name))
        assert sha256_bytes(canonical_dumps(document).encode("utf-8")) == expected
    forbidden_suffixes = {".png", ".jpg", ".jpeg", ".npy", ".npz", ".pkl", ".bin"}
    assert not any(path.suffix.lower() in forbidden_suffixes for path in EVIDENCE.rglob("*"))
    assert sum(path.stat().st_size for path in EVIDENCE.rglob("*") if path.is_file()) < 25_000_000


def _without_runtime(value: object) -> object:
    if isinstance(value, dict):
        return {key: _without_runtime(child) for key, child in value.items() if key != "runtime"}
    if isinstance(value, list):
        return [_without_runtime(item) for item in value]
    return value
