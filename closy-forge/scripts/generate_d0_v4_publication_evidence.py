from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.d0_v4_engineering.appearance import (
    persist_recovered_appearance,
    recover_source_to_uv,
    rerender_from_persisted_atlas,
)
from closy_forge.d0_v4_engineering.corpus import load_partition
from closy_forge.d0_v4_engineering.protocol import load_budget_ledger
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes

EVIDENCE_ROOT = Path("docs/evidence/d0_v4_engineering")
CORPUS_ROOT = Path("fixtures/d0_v4_engineering_corpus_v5")
MODEL_PATH = Path("models/d0_v4_engineering/trial-006.json")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    evidence = root / EVIDENCE_ROOT
    manifest = _mapping(read_json(root / CORPUS_ROOT / "manifest.json"))
    model = _mapping(read_json(root / MODEL_PATH))
    validation = _mapping(read_json(evidence / "validation_trial_006_final.json"))
    controls = _mapping(read_json(evidence / "negative_controls.json"))
    ledger = load_budget_ledger(root)

    data_card = _with_digest(
        {
            "schemaVersion": 1,
            "evidenceClass": "project_authored_public_synthetic_engineering_corpus",
            "corpusVersion": manifest["corpusVersion"],
            "generatorVersion": manifest["generatorVersion"],
            "license": manifest["license"],
            "developmentPartitionCounts": manifest["partitionCounts"],
            "guardedPublicTestCount": manifest["allPartitionCounts"]["public_test"],
            "developmentArchiveSha256": manifest["archiveSha256"],
            "officialFormat": manifest["officialFormat"],
            "rendererFamilies": manifest["rendererFamilies"],
            "variationAxes": manifest["variationAxes"],
            "observableParameters": manifest["observableParameters"],
            "separation": manifest["separation"],
            "publicTestTargetsReadWhileBuildingCard": False,
            "publicTestStorage": "separate_guarded_manifest_and_archive",
            "qualificationEligible": False,
            "lostOpaqueV2Relation": "unverified",
            "unsupportedEvidence": [
                "real_photo_generalization",
                "real_fabric_inference",
                "private_user_capture_readiness",
                "qualification_or_production_promotion",
            ],
        }
    )
    model_card = _with_digest(
        {
            "schemaVersion": 1,
            "evidenceClass": "trained_structured_rgb_tshirt_engineering_model",
            "trialId": model["trialId"],
            "modelVersion": model["modelVersion"],
            "modelSha256": model["integrity"]["modelSha256"],
            "weightsSha256": model["integrity"]["weightsSha256"],
            "architecture": model["architecture"],
            "inputEvidence": model["inputEvidence"],
            "featureCount": len(model["featureNames"]),
            "features": model["featureNames"],
            "targetCount": len(model["targetNames"]),
            "targets": model["targetNames"],
            "preprocessing": model["preprocessing"],
            "optimizer": model["optimizer"],
            "outputConstraint": model["outputConstraint"],
            "trainingSampleCount": model["trainingSampleCount"],
            "validationSampleCount": model["validationSampleCount"],
            "trainingMetrics": model["trainingMetrics"],
            "rawUnboundedDiagnosticsRetained": True,
            "confidenceAndAlternativesEmitted": True,
            "targetParametersReadAtInference": False,
            "cpuReproductionPolicy": "canonical_binary64_exact_digest_and_fresh_process_repeat",
            "primaryInference": "learned_initialization_plus_bounded_source_conditioned_fitting",
            "physicalMaterialAccuracyClaimed": False,
        }
    )
    trials = [
        deepcopy(event)
        for event in ledger["events"]
        if event["event"] == "model_training_trial_completed"
    ]
    trial_inventory = _with_digest(
        {
            "schemaVersion": 1,
            "evidenceClass": "immutable_complete_model_trial_inventory",
            "consumed": ledger["modelTrainingTrialsConsumed"],
            "maximum": 12,
            "failedTrialsRetained": True,
            "trials": trials,
            "publicTestExecutionsConsumed": ledger["publicTestExecutionsConsumed"],
            "budgetLedgerDigest": ledger["ledgerDigest"],
        }
    )
    readiness = _with_digest(
        {
            "schemaVersion": 1,
            "evidenceClass": "unit_ac_development_validation",
            "literalOutcome": "passed_complete_ac_development_and_validation_gates",
            "createsQualificationCohort": False,
            "modelSha256": validation["modelSha256"],
            "validationResultDigest": validation["resultDigest"],
            "primaryRoute": validation["primaryRoute"],
            "readinessPass": validation["readinessPass"],
            "summary": validation["summary"],
            "gates": validation["gates"],
            "negativeControlsDigest": controls["resultDigest"],
            "negativeControlsAllPass": controls["allPass"],
            "negativeControlNames": sorted(controls["controls"]),
            "publicTestExecuted": False,
            "publicTestMayGuideDevelopment": False,
            "selectionPolicy": "silhouette_45_contour_45_learned_10_bounded_blend",
            "appearanceRecovery": "source_to_panel_uv_atlas_v2_with_per_texel_lineage",
            "unsupportedEvidence": [
                "D0_v4_scientific_qualification",
                "real_photo_or_real_fabric_capability",
                "physical_material_accuracy_from_RGB",
                "mobile_GPU_or_runtime_performance",
                "Alpha_Beta_or_Production_readiness",
            ],
        }
    )
    source_inventory = _source_inventory(root)
    representative = _representative_appearance(root)

    outputs = {
        "data_card.json": data_card,
        "model_card.json": model_card,
        "trial_inventory.json": trial_inventory,
        "development_readiness.json": readiness,
        "source_inventory.json": source_inventory,
        "appearance/representative_091/evidence.json": representative,
    }
    for relative, value in outputs.items():
        write_canonical_json(evidence / relative, value)
    for relative, value in outputs.items():
        print(relative, value["resultDigest"])
    return 0


def _representative_appearance(root: Path) -> dict[str, Any]:
    record = load_partition(root, "validation")[91]
    recovered = recover_source_to_uv(record["frontPng"], record.get("rearPng"))
    artifact_id = "representative_091"
    paths = persist_recovered_appearance(root, recovered, artifact_id)
    directory = root / EVIDENCE_ROOT / "appearance" / artifact_id
    background_values = record["capture"]["backgroundSrgb"]
    background = tuple(int(value) for value in background_values)
    render_inputs = {
        "front": (record["frontPng"], "front", None),
        "rear": (record.get("rearPng") or record["frontPng"], "rear", None),
        "novel_052": (record["frontPng"], "novel", 52.0),
        "novel_128": (record["frontPng"], "novel", 128.0),
    }
    renders: dict[str, dict[str, Any]] = {}
    for name, (geometry, role, angle) in render_inputs.items():
        png = rerender_from_persisted_atlas(
            recovered,
            geometry,
            role=role,
            azimuth_degrees=angle,
            output_background=background,  # type: ignore[arg-type]
        )
        path = directory / f"rerender-{name}.png"
        path.write_bytes(png)
        renders[name] = {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_bytes(png),
            "azimuthDegrees": angle,
        }
    write_canonical_json(directory / "atlas-manifest.json", recovered.manifest)
    return _with_digest(
        {
            "schemaVersion": 1,
            "evidenceClass": "representative_source_to_uv_causal_rerender",
            "partition": "validation",
            "ordinal": 91,
            "identityHash": record["identityHash"],
            "sourceHash": record["sourceHash"],
            "atlasManifestDigest": recovered.manifest["manifestDigest"],
            "artifacts": paths,
            "rerenders": renders,
            "novelViewsDifferFromFront": all(
                item["sha256"] != renders["front"]["sha256"]
                for name, item in renders.items()
                if name.startswith("novel_")
            ),
            "lineageIsPanelUvNotCameraPlane": True,
            "physicalMaterialAccuracyClaimed": False,
        }
    )


def _source_inventory(root: Path) -> dict[str, Any]:
    candidates: set[Path] = set()
    patterns = (
        "src/closy_forge/d0_v4_engineering/*.py",
        "src/closy_forge/contracts/schema_registry.py",
        "schemas/v1/d0-v4-*.schema.json",
        "scripts/*d0_v4*.py",
        "models/d0_v4_engineering/*.json",
        "tests/unit/test_d0_v4*.py",
        "docs/evidence/d0_v4_engineering/engineering_*.json",
        "docs/evidence/d0_v4_engineering/observation_contract_v1.json",
        "docs/evidence/d0_v4_engineering/negative_controls.json",
        "docs/evidence/d0_v4_engineering/validation_trial_*.json",
        "docs/evidence/d0_v4_engineering/v3_forensics/**/*",
        "fixtures/d0_v4_engineering_corpus_v[1-5]/*",
    )
    for pattern in patterns:
        candidates.update(path for path in root.glob(pattern) if path.is_file())
    guarded = {
        root / CORPUS_ROOT / "public_test.manifest.json",
        root / CORPUS_ROOT / "public_test.captures.zip",
    }
    candidates.difference_update(guarded)
    files = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_bytes(path.read_bytes()),
        }
        for path in sorted(candidates)
    ]
    return _with_digest(
        {
            "schemaVersion": 1,
            "evidenceClass": "unit_ac_source_and_development_artifact_inventory",
            "files": files,
            "fileCount": len(files),
            "guardedArtifactsExcludedFromDevelopmentRead": [
                path.relative_to(root).as_posix() for path in sorted(guarded)
            ],
            "publicTestTargetsRead": False,
        }
    )


def _with_digest(value: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(value)
    result["resultDigest"] = ""
    result["resultDigest"] = sha256_bytes(canonical_dumps(result).encode("utf-8"))
    return result


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("d0_v4_publication_mapping_required")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
