from __future__ import annotations

import platform
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes

from .grammar_v2 import FAMILY_SPECS, compile_program, validate_compiled_pattern, validate_program
from .model_v2 import canonical_model_bytes, train_model_v2, validate_model_v2
from .raster_dataset_v3 import build_raster_dataset_v3, validate_raster_dataset_v3
from .raster_evaluation_v3 import evaluate_raster_model_v3

FOUNDATION_VERSION_V3 = "closy.raster_learned_pattern_foundation.synthetic_d0.v3"


def build_raster_foundation_v3(*, seed: int = 3901) -> dict[str, Any]:
    dataset, split, _private_provenance = build_raster_dataset_v3(seed=seed)
    model = train_model_v2(dataset, split, seed=9102)
    repeated = train_model_v2(dataset, split, seed=9102)
    evaluation = evaluate_raster_model_v3(model, dataset, split)
    config = _training_config(dataset, model)
    bundle: dict[str, Any] = {
        "schemaVersion": 1,
        "foundationVersion": FOUNDATION_VERSION_V3,
        "dataset": dataset,
        "split": split,
        "model": model,
        "evaluation": evaluation,
        "compilerAudit": _compiler_audit(dataset),
        "corpusManifest": _corpus_manifest(dataset),
        "datasetCard": _dataset_card(dataset, split),
        "modelCard": _model_card(model, evaluation),
        "trainingConfig": config,
        "reproducibility": {
            "twoCleanRunsExecuted": True,
            "canonicalModelBytesIdentical": canonical_model_bytes(model)
            == canonical_model_bytes(repeated),
            "firstModelHash": model["integrity"]["modelHash"],
            "secondModelHash": repeated["integrity"]["modelHash"],
            "canonicalReferenceLane": "python_binary64_host_cpu",
        },
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": sys.platform,
            "computeProfile": "D0_CPU",
            "networkUsed": False,
        },
        "licenceProvenance": {
            "recordVersion": "closy.raster_training_provenance.synthetic_d0.v1",
            "datasetSource": "project-authored Phase 8 programs rendered by project CPU code",
            "externalDatasets": [],
            "privateData": False,
            "humanReviewStatus": "not_run",
        },
        "gates": {
            "E1": {
                "status": "candidate_pending_downstream_execution",
                "scope": "project_authored_synthetic_rasters_eight_predeclared_families",
            },
            "E2": {
                "status": "not_run",
                "reason": (
                    "fixed_template_classifier_regressor_is_not_structured_program_generation"
                ),
            },
            "globalPhase9": "partial",
        },
        "hashes": {
            "dataset": sha256_bytes(canonical_dumps(dataset).encode("utf-8")),
            "split": sha256_bytes(canonical_dumps(split).encode("utf-8")),
            "trainingConfig": sha256_bytes(canonical_dumps(config).encode("utf-8")),
            "model": model["integrity"]["modelHash"],
            "code": _code_hash(),
        },
        "integrity": {"bundleHash": ""},
    }
    bundle["integrity"]["bundleHash"] = _bundle_hash(bundle)
    issues = validate_raster_foundation_v3(bundle)
    if issues:
        raise ValueError("invalid_raster_foundation_v3:" + ";".join(issues))
    return bundle


def write_raster_foundation_v3(output: Path, *, seed: int = 3901) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    bundle = build_raster_foundation_v3(seed=seed)
    documents = {
        "foundation.json": bundle,
        "raster_dataset.json": bundle["dataset"],
        "split.json": bundle["split"],
        "corpus_manifest.json": bundle["corpusManifest"],
        "model.json": bundle["model"],
        "evaluation.json": bundle["evaluation"],
        "dataset_card.json": bundle["datasetCard"],
        "model_card.json": bundle["modelCard"],
        "training_config.json": bundle["trainingConfig"],
        "training_curve.json": bundle["model"]["trainingCurve"],
        "reproducibility.json": bundle["reproducibility"],
        "licence_provenance.json": bundle["licenceProvenance"],
    }
    for name, document in documents.items():
        write_canonical_json(output / name, document)
    return bundle


def validate_raster_foundation_v3(bundle: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if bundle.get("foundationVersion") != FOUNDATION_VERSION_V3:
        issues.append("raster_foundation_version_invalid")
    dataset = bundle.get("dataset", {})
    split = bundle.get("split", {})
    model = bundle.get("model", {})
    issues.extend(validate_raster_dataset_v3(dataset, split))
    issues.extend(validate_model_v2(model))
    hashes = bundle.get("hashes", {})
    if hashes.get("dataset") != sha256_bytes(canonical_dumps(dataset).encode("utf-8")):
        issues.append("raster_foundation_dataset_hash_mismatch")
    if hashes.get("split") != sha256_bytes(canonical_dumps(split).encode("utf-8")):
        issues.append("raster_foundation_split_hash_mismatch")
    if hashes.get("code") != _code_hash():
        issues.append("raster_foundation_code_hash_mismatch")
    reproducibility = bundle.get("reproducibility", {})
    if (
        reproducibility.get("twoCleanRunsExecuted") is not True
        or reproducibility.get("canonicalModelBytesIdentical") is not True
        or reproducibility.get("firstModelHash") != reproducibility.get("secondModelHash")
    ):
        issues.append("raster_foundation_reproducibility_invalid")
    controls = bundle.get("evaluation", {}).get("controlThresholds", {})
    if not all(
        controls.get(name) is True
        for name in ("labelPermutationPass", "pixelsDestroyedPass", "metadataOnlyPass")
    ):
        issues.append("raster_foundation_control_threshold_failed")
    compiler = bundle.get("compilerAudit", {})
    if compiler.get("failedFamilyCount") != 0 or compiler.get("familyCount") != len(FAMILY_SPECS):
        issues.append("raster_foundation_compiler_audit_invalid")
    if bundle.get("gates", {}).get("globalPhase9") != "partial":
        issues.append("raster_foundation_global_overclaim")
    if bundle.get("integrity", {}).get("bundleHash") != _bundle_hash(bundle):
        issues.append("raster_foundation_bundle_hash_mismatch")
    return sorted(set(issues))


def _compiler_audit(dataset: dict[str, Any]) -> dict[str, Any]:
    records = []
    for family in FAMILY_SPECS:
        program = next(item for item in dataset["programs"] if item["garmentFamily"] == family)
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
            }
        )
    return {
        "actualPhase8GeneratorsExecuted": True,
        "familyCount": len(records),
        "failedFamilyCount": sum(
            not record["programValid"] or not record["compiledPatternValid"] for record in records
        ),
        "records": records,
    }


def _corpus_manifest(dataset: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "manifestVersion": "closy.raster_pattern_corpus_manifest.synthetic_d0.v1",
        "datasetVersion": dataset["datasetVersion"],
        "programCount": len(dataset["programs"]),
        "captureCount": len(dataset["samples"]),
        "viewCount": sum(
            len(sample["captureAudit"]["pixelHashes"]) for sample in dataset["samples"]
        ),
        "viewLabels": dataset["samples"][0]["captureAudit"]["viewLabels"],
        "captureRecords": [
            {
                "sampleId": sample["sampleId"],
                "sourceProgramDigest": sample["sourceProgramDigest"],
                "combinedPixelHash": sample["captureAudit"]["combinedPixelHash"],
            }
            for sample in dataset["samples"]
        ],
        "rawRasterBytesCommitted": False,
        "privateSeedProvenanceCommitted": False,
    }


def _dataset_card(dataset: dict[str, Any], split: dict[str, Any]) -> dict[str, Any]:
    return {
        "cardVersion": "closy.raster_pattern_dataset_card.synthetic_d0.v1",
        "name": "Closy Phase 8 raster-derived synthetic garment captures",
        "intendedUse": "bounded D0 E1 retrieval/adaptation experiment",
        "sampleCount": len(dataset["samples"]),
        "programCount": len(dataset["programs"]),
        "viewCount": len(dataset["samples"]) * 4,
        "splitUnit": split["groupKey"],
        "unassistedTrack": True,
        "assistedTrack": False,
        "projectAuthoredSynthetic": True,
        "privateData": False,
        "realCaptureData": False,
        "limitations": [
            "single project-authored polygon renderer",
            "no real-camera or private-user evidence",
            "fixed eight-family grammar",
        ],
    }


def _model_card(model: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        "cardVersion": "closy.raster_pattern_model_card.synthetic_d0.v1",
        "modelVersion": model["modelVersion"],
        "intendedUse": "raster-conditioned template retrieval and continuous adaptation E1",
        "outOfScope": ["E2 structured generation", "production vision", "real-photo claims"],
        "heldOutTop1Accuracy": evaluation["primary"]["familyTemplate"]["top1Accuracy"],
        "superiorityClaim": evaluation["comparison"]["claim"],
        "fallback": "deterministic validated template",
        "globalPhase9Status": "partial",
    }


def _training_config(dataset: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    return {
        "configVersion": "closy.raster_pattern_training_config.synthetic_d0.v1",
        "corpusHash": sha256_bytes(canonical_dumps(dataset).encode("utf-8")),
        "modelSeed": model["seed"],
        "sourceIdentitiesPerFamily": 12,
        "capturesPerSource": 4,
        "epochs": model["optimizer"]["epochs"],
        "trials": 1,
        "maximumEpochs": 80,
        "maximumTrials": 4,
        "maximumCpuSeconds": 3600,
        "maximumWallSeconds": 3600,
        "maximumMemoryBytes": 2_147_483_648,
        "numericPolicy": model["numericPolicy"],
        "selectionUsesValidationOnly": True,
    }


def _code_hash() -> str:
    root = Path(__file__).parent
    names = (
        "grammar_v2.py",
        "model_v2.py",
        "raster_dataset_v3.py",
        "raster_evaluation_v3.py",
        "raster_foundation_v3.py",
    )
    payload = b"".join(name.encode("utf-8") + b"\0" + (root / name).read_bytes() for name in names)
    return sha256_bytes(payload)


def _bundle_hash(bundle: dict[str, Any]) -> str:
    payload = deepcopy(bundle)
    payload.setdefault("integrity", {})["bundleHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
