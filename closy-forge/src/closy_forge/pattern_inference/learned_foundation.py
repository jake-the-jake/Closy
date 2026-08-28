from __future__ import annotations

import platform
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes

from .correction_session_v2 import (
    record_correction,
    start_correction_session,
    validate_correction_session,
)
from .dataset_v2 import build_synthetic_dataset_v2, validate_dataset_v2
from .evaluation_v2 import evaluate_model_v2
from .grammar_v2 import (
    FAMILY_SPECS,
    GRAMMAR_VERSION_V2,
    compile_program,
    validate_compiled_pattern,
    validate_program,
)
from .model_v2 import (
    canonical_model_bytes,
    train_model_v2,
    validate_model_v2,
)

FOUNDATION_VERSION = "closy.learned_pattern_inference.d0.v1"


def build_learned_pattern_inference_foundation(*, seed: int = 2901) -> dict[str, Any]:
    dataset, split = build_synthetic_dataset_v2(seed=seed)
    model = train_model_v2(dataset, split)
    repeated_model = train_model_v2(dataset, split)
    model_bytes = canonical_model_bytes(model)
    repeated_bytes = canonical_model_bytes(repeated_model)
    evaluation = evaluate_model_v2(model, dataset, split)
    correction = start_correction_session(
        model,
        dataset["samples"][-1]["input"],
        session_id="correction.learned_d0.simulated.001",
        seed=seed + 71,
    )
    correction = record_correction(
        correction,
        field="easeNormalized",
        value=0.25,
        accepted=False,
        reason_code="simulated_reject_excess_drape",
    )
    correction = record_correction(
        correction,
        field="widthScale",
        value=1.02,
        accepted=True,
        reason_code="simulated_accept_width_adjustment",
    )
    compiler_audit = _compiler_audit(dataset)
    config = _training_config(seed, model)
    bundle: dict[str, Any] = {
        "schemaVersion": 1,
        "foundationVersion": FOUNDATION_VERSION,
        "grammar": _grammar_contract(),
        "dataset": dataset,
        "split": split,
        "model": model,
        "evaluation": evaluation,
        "correctionSession": correction,
        "compilerAudit": compiler_audit,
        "datasetCard": _dataset_card(dataset, split),
        "modelCard": _model_card(model, evaluation),
        "licenceProvenance": _licence_provenance(),
        "reproducibility": {
            "twoRunTrainingExecuted": True,
            "firstModelHash": sha256_bytes(model_bytes),
            "secondModelHash": sha256_bytes(repeated_bytes),
            "canonicalModelBytesIdentical": model_bytes == repeated_bytes,
            "fixedSeeds": [seed, 9102],
        },
        "rollback": {
            "available": True,
            "strategy": "nearest_training_centroid_plus_default_parameters",
            "activation": "prediction_rejected_or_deferred",
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "supportedPython": ">=3.11,<3.13",
            "numericalDependencies": [],
            "standardLibraryOptimizer": True,
            "platformRecordedForThisBuild": sys.platform,
        },
        "hashes": {
            "dataset": sha256_bytes(canonical_dumps(dataset).encode("utf-8")),
            "split": sha256_bytes(canonical_dumps(split).encode("utf-8")),
            "config": sha256_bytes(canonical_dumps(config).encode("utf-8")),
            "weights": model["integrity"]["weightsHash"],
            "code": _code_hash(),
        },
        "evidenceTier": {
            "scope": "project_authored_synthetic_d0",
            "actualTrainingExecuted": True,
            "identityDisjointHeldOutEvaluationExecuted": True,
            "realOrPublicCaptureEvidence": False,
            "privateDatasetUsed": False,
            "humanCorrectionEvidence": False,
            "humanReviewStatus": "not_run",
            "globalPhase9Status": "partial",
        },
        "integrity": {"bundleHash": ""},
    }
    bundle["integrity"]["bundleHash"] = _bundle_hash(bundle)
    issues = validate_learned_pattern_inference_foundation(bundle)
    if issues:
        raise ValueError("invalid_learned_pattern_inference_foundation:" + ";".join(issues))
    return bundle


def write_learned_pattern_inference_foundation(output: Path, *, seed: int = 2901) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    bundle = build_learned_pattern_inference_foundation(seed=seed)
    documents = {
        "foundation.json": bundle,
        "grammar.json": bundle["grammar"],
        "synthetic_dataset.json": bundle["dataset"],
        "split.json": bundle["split"],
        "model.json": bundle["model"],
        "evaluation.json": bundle["evaluation"],
        "correction_session.json": bundle["correctionSession"],
        "dataset_card.json": bundle["datasetCard"],
        "model_card.json": bundle["modelCard"],
        "licence_provenance.json": bundle["licenceProvenance"],
        "reproducibility.json": bundle["reproducibility"],
    }
    for name, document in documents.items():
        write_canonical_json(output / name, document)
    return bundle


def validate_learned_pattern_inference_foundation(bundle: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if bundle.get("foundationVersion") != FOUNDATION_VERSION:
        issues.append("learned_foundation_version_invalid")
    issues.extend(validate_dataset_v2(bundle.get("dataset", {}), bundle.get("split", {})))
    issues.extend(validate_model_v2(bundle.get("model", {})))
    issues.extend(validate_correction_session(bundle.get("correctionSession", {})))
    dataset = bundle.get("dataset", {})
    split = bundle.get("split", {})
    model = bundle.get("model", {})
    hashes = bundle.get("hashes", {})
    if hashes.get("dataset") != sha256_bytes(canonical_dumps(dataset).encode("utf-8")):
        issues.append("learned_dataset_hash_mismatch")
    if hashes.get("split") != sha256_bytes(canonical_dumps(split).encode("utf-8")):
        issues.append("learned_split_hash_mismatch")
    if hashes.get("config") != sha256_bytes(
        canonical_dumps(_training_config(int(dataset.get("seed", -1)), model)).encode("utf-8")
    ):
        issues.append("learned_config_hash_mismatch")
    if hashes.get("weights") != model.get("integrity", {}).get("weightsHash"):
        issues.append("learned_weights_hash_mismatch")
    if hashes.get("code") != _code_hash():
        issues.append("learned_code_hash_mismatch")
    if any(validate_program(program) for program in dataset.get("programs", [])):
        issues.append("learned_dataset_program_invalid")
    if canonical_dumps(bundle.get("evaluation", {})) != canonical_dumps(
        evaluate_model_v2(model, dataset, split)
    ):
        issues.append("learned_evaluation_recompute_mismatch")
    reproducibility = bundle.get("reproducibility", {})
    if (
        reproducibility.get("twoRunTrainingExecuted") is not True
        or reproducibility.get("canonicalModelBytesIdentical") is not True
        or reproducibility.get("firstModelHash") != reproducibility.get("secondModelHash")
    ):
        issues.append("two_run_training_reproducibility_invalid")
    evaluation = bundle.get("evaluation", {})
    if evaluation.get("heldOutProgramGroupCount", 0) < 16:
        issues.append("identity_disjoint_evaluation_scale_invalid")
    if evaluation.get("grammarValidity", {}).get("rate") != 1.0:
        issues.append("learned_decode_grammar_validity_invalid")
    compiler = bundle.get("compilerAudit", {})
    if compiler.get("familyCount") != len(FAMILY_SPECS) or compiler.get("failedFamilyCount") != 0:
        issues.append("real_family_compiler_audit_invalid")
    tier = bundle.get("evidenceTier", {})
    if (
        tier.get("actualTrainingExecuted") is not True
        or tier.get("privateDatasetUsed") is not False
        or tier.get("humanCorrectionEvidence") is not False
        or tier.get("globalPhase9Status") != "partial"
    ):
        issues.append("learned_evidence_tier_overclaim")
    if bundle.get("integrity", {}).get("bundleHash") != _bundle_hash(bundle):
        issues.append("learned_foundation_bundle_hash_mismatch")
    return sorted(set(issues))


def _compiler_audit(dataset: dict[str, Any]) -> dict[str, Any]:
    records = []
    programs = {program["garmentFamily"]: program for program in dataset["programs"]}
    for family in FAMILY_SPECS:
        program = programs[family]
        program_issues = validate_program(program)
        pattern = compile_program(program)
        pattern_issues = validate_compiled_pattern(pattern)
        records.append(
            {
                "family": family,
                "programValid": not program_issues,
                "compiledPatternValid": not pattern_issues,
                "panelCount": len(pattern["panels"]),
                "seamCount": len(pattern["seams"]),
                "openingCount": len(pattern["openings"]),
                "patternVersion": pattern["patternVersion"],
            }
        )
    return {
        "familyCount": len(records),
        "failedFamilyCount": sum(
            not record["programValid"] or not record["compiledPatternValid"] for record in records
        ),
        "actualClosyFamilyGeneratorsExecuted": True,
        "records": records,
    }


def _grammar_contract() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "grammarVersion": GRAMMAR_VERSION_V2,
        "domain": "human_avatar_garments_only",
        "families": list(FAMILY_SPECS),
        "constructs": [
            "panel_nodes",
            "boundary_curves",
            "seam_spans_and_pairing",
            "ease",
            "openings",
            "supported_shaping",
            "material_regions",
            "layer_order",
            "fastenings",
            "measurements_and_confidence",
            "correction_operations",
            "version_and_provenance",
        ],
        "failClosedChecks": [
            "missing_spans",
            "duplicate_semantic_ids",
            "impossible_seam_cycles",
            "invalid_openings",
            "non_simple_panels",
            "inconsistent_ease",
            "layer_cycles",
            "unsupported_features",
            "out_of_range_parameters",
        ],
    }


def _dataset_card(dataset: dict[str, Any], split: dict[str, Any]) -> dict[str, Any]:
    return {
        "cardVersion": "closy.pattern_dataset_card.d0.v1",
        "name": "Closy project-authored synthetic garment capture D0",
        "intendedUse": "bounded grammar-constrained synthetic D0 training and regression tests",
        "sampleCount": len(dataset["samples"]),
        "programCount": len(dataset["programs"]),
        "splitUnit": split["groupKey"],
        "identityDisjointnessRecomputed": True,
        "privateData": False,
        "realCaptureData": False,
        "limitations": [
            "synthetic observables do not establish real-camera generalisation",
            "eight existing Closy D0 garment families only",
            "no human-labelled corrections",
        ],
    }


def _model_card(model: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        "cardVersion": "closy.pattern_model_card.d0.v1",
        "modelVersion": model["modelVersion"],
        "intendedUse": "small offline synthetic D0 proposal model with grammar validation",
        "outOfScope": [
            "production inference",
            "private-user training",
            "broad garment recognition",
        ],
        "heldOutTop1Accuracy": evaluation["familyTemplate"]["top1Accuracy"],
        "oodRejectionAccuracy": evaluation["ood"]["rejectionAccuracy"],
        "superiorityClaim": evaluation["comparison"]["claim"],
        "requiredFallback": "deterministic template baseline",
        "knownRisks": [
            "synthetic-to-real domain gap",
            "ambiguous silhouettes can require deferral",
            "continuous parameter estimates require review",
        ],
    }


def _licence_provenance() -> dict[str, Any]:
    return {
        "recordVersion": "closy.pattern_training_provenance.d0.v1",
        "datasetSource": "project-authored deterministic generators and synthetic capture features",
        "externalDatasets": [],
        "privateData": False,
        "newRuntimeDependencies": [],
        "redistribution": "source and generated fixture metadata follow the repository licence",
        "humanReview": "not_run",
    }


def _code_hash() -> str:
    root = Path(__file__).parent
    names = (
        "grammar_v2.py",
        "dataset_v2.py",
        "model_v2.py",
        "evaluation_v2.py",
        "correction_session_v2.py",
        "learned_foundation.py",
    )
    payload = b"".join(name.encode("utf-8") + b"\0" + (root / name).read_bytes() for name in names)
    return sha256_bytes(payload)


def _training_config(seed: int, model: dict[str, Any]) -> dict[str, Any]:
    return {
        "datasetSeed": seed,
        "modelSeed": model.get("seed"),
        "groupsPerFamily": 12,
        "observationsPerGroup": 4,
        "epochs": model.get("optimizer", {}).get("epochs"),
        "declaredLoss": model.get("optimizer", {}).get("declaredLoss"),
    }


def _bundle_hash(bundle: dict[str, Any]) -> str:
    payload = deepcopy(bundle)
    payload.setdefault("integrity", {})["bundleHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
