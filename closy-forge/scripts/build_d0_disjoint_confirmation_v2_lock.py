from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.disjoint_confirmation_v2.evaluator import execute_evaluator
from closy_forge.disjoint_confirmation_v2.protocol import (
    FIXTURE_ROOT,
    protocol_document,
    validate_protocol,
)
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.recovery_foundation_v1.contestant_boundary import run_boundary_fixtures
from closy_forge.recovery_foundation_v1.evaluator_v2 import run_generic_mutation_fixtures

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ANCHOR = "a72f45955abbe65ce14b7142668447d0477db71c"


def build() -> dict[str, Any]:
    target = ROOT / FIXTURE_ROOT
    target.mkdir(parents=True, exist_ok=True)
    inventory = _prior_inventory()
    write_canonical_json(target / "prior_inventory.json", inventory)
    implementation = _implementation_inventory()
    authority_workflow = ROOT.parent / ".github/workflows/closy-forge-unit-m-authority.yml"
    protocol = protocol_document(
        source_anchor_sha=SOURCE_ANCHOR,
        implementation_files=implementation,
        initial_authority_workflow_sha256=sha256_file(authority_workflow),
    )
    issues = validate_protocol(protocol)
    if issues:
        raise ValueError(";".join(issues))
    write_canonical_json(target / "protocol_lock.json", protocol)
    development = _development_proof(protocol)
    write_canonical_json(target / "development_proof.json", development)
    report = {
        "schemaVersion": 1,
        "reportVersion": "closy.d0_disjoint_tshirt_confirmation.lock_report.v2",
        "sourceAnchorSha": SOURCE_ANCHOR,
        "protocolLockHash": protocol["lockHash"],
        "implementationDigest": protocol["implementationDigest"],
        "priorInventoryDigest": inventory["inventoryDigest"],
        "developmentProofHash": development["proofHash"],
        "freshEvaluatorIdentitiesRealized": False,
        "freshEvaluatorTargetsRealized": False,
        "officialAttemptState": "not_started",
        "nextAction": "external_seed_authority_once_at_exact_lock_commit",
    }
    write_canonical_json(target / "lock_report.json", report)
    return report


def check() -> list[str]:
    target = ROOT / FIXTURE_ROOT
    before = {
        path.name: path.read_bytes()
        for path in target.glob("*.json")
        if path.name
        in {
            "prior_inventory.json",
            "protocol_lock.json",
            "development_proof.json",
            "lock_report.json",
        }
    }
    build()
    after = {path.name: path.read_bytes() for path in target.glob("*.json") if path.name in before}
    return sorted(name for name in before if before[name] != after.get(name))


def _development_proof(protocol: Mapping[str, Any]) -> dict[str, Any]:
    v1_root = ROOT / "fixtures/d0_disjoint_tshirt_benchmark_v1/evaluator"
    predictions = _mapping(read_json(v1_root / "predictions.json"))
    targets = _mapping(read_json(v1_root / "target_reveal.json"))
    result = execute_evaluator(
        ROOT,
        protocol=protocol,
        predictions=predictions,
        targets=targets,
        isolation_summary={"qualifiesD0Rp04": False},
    )
    proof: dict[str, Any] = {
        "schemaVersion": 1,
        "proofVersion": "closy.d0_disjoint_tshirt_confirmation.development_proof.v2",
        "classification": "revealed_unit_g_v1_contaminated_harness_diagnostic_only",
        "mayCloseResearchPrototypeRows": False,
        "listTranscriptLoaded": isinstance(
            read_json(v1_root / "raw_draw_rejection_transcript.json"), list
        ),
        "mappingArtifactsLoaded": isinstance(predictions, dict) and isinstance(targets, dict),
        "predictionCount": len(_records(predictions["predictions"])),
        "fullCompileCount": result["fullCompileCount"],
        "fullCompileSuccessCount": result["fullCompileSuccessCount"],
        "primaryCompileRepeatCount": result["primaryCompileRepeatCount"],
        "primaryCompileRepeatSuccessCount": result["primaryCompileRepeatSuccessCount"],
        "appearanceEvaluationCount": result["appearanceEvaluationCount"],
        "appearanceSuccessfulEvaluationCount": result["appearanceSuccessfulEvaluationCount"],
        "primaryAppearanceRepeatCount": result["primaryAppearanceRepeatCount"],
        "primaryAppearanceRepeatSuccessCount": result["primaryAppearanceRepeatSuccessCount"],
        "allGateFamiliesExecuted": all(
            set(record["gateFamilies"])
            == {
                "pattern",
                "seam",
                "opening",
                "topology",
                "simulation",
                "binding",
                "source_silhouette",
                "landmark",
                "appearance",
                "texture_identity",
                "pbr_integrity",
                "reproducibility",
            }
            for record in result["records"]
        ),
        "contributionDerived": all(
            record["sourceContribution"]["derivedFromLineage"] is True
            for record in result["records"]
        ),
        "promotionDeterministic": isinstance(result["routePromotion"]["promoted"], bool),
        "genericEvaluatorFixtures": run_generic_mutation_fixtures(),
        "applicationBoundaryFixtures": run_boundary_fixtures(),
        "officialResultHashNotDonated": result["resultHash"],
        "proofHash": "",
    }
    proof["proofHash"] = _hash({**proof, "proofHash": ""})
    return proof


def _prior_inventory() -> dict[str, Any]:
    identities: set[str] = set()
    parameter_records: dict[str, dict[str, Any]] = {}
    target_features: set[str] = set()
    roots = [ROOT / "fixtures", ROOT / "docs/evidence"]
    for base in roots:
        for path in sorted(base.rglob("*.json")):
            if FIXTURE_ROOT.as_posix() in path.as_posix():
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            _collect_json(value, identities, parameter_records)
            if "target" in path.name.lower() or "evaluator" in path.as_posix().lower():
                target_features.add(sha256_file(path))
    pixels = {
        sha256_file(path)
        for base in roots
        for path in base.rglob("*.png")
        if FIXTURE_ROOT.as_posix() not in path.as_posix()
    }
    geometry = {
        sha256_file(path)
        for base in roots
        for suffix in ("*.glb", "*.gltf")
        for path in base.rglob(suffix)
        if FIXTURE_ROOT.as_posix() not in path.as_posix()
    }
    records = [parameter_records[key] for key in sorted(parameter_records)]
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "inventoryVersion": "closy.d0_disjoint_tshirt_confirmation.prior_inventory.v2",
        "scope": [
            "fixture",
            "development",
            "unit_g_v1_evaluator",
            "retrieval",
            "phase9_training",
            "benchmark",
            "golden_target",
        ],
        "identityValues": sorted(identities),
        "parameterRecords": records,
        "parameterHashes": sorted(parameter_records),
        "pixelHashes": sorted(pixels),
        "geometryHashes": sorted(geometry),
        "targetFeatureHashes": sorted(target_features),
        "inventoryDigest": "",
    }
    document["inventoryDigest"] = _hash({**document, "inventoryDigest": ""})
    return document


def _collect_json(
    value: Any, identities: set[str], parameter_records: dict[str, dict[str, Any]]
) -> None:
    if isinstance(value, Mapping):
        for key in ("opaqueId", "identityId", "garmentId", "candidateId"):
            if key in value and isinstance(value[key], str):
                identities.add(value[key])
        parameters = value.get("parameters")
        required = {
            "garment_body_length",
            "half_chest_width",
            "body_ease",
            "shoulder_width",
            "shoulder_slope",
            "neckline_width",
            "front_neckline_depth",
            "back_neckline_depth",
            "armhole_depth",
            "sleeve_length",
            "sleeve_opening_width",
        }
        if isinstance(parameters, Mapping) and required <= set(parameters):
            record = {str(key): item for key, item in parameters.items()}
            parameter_records[_hash(record)] = record
        for nested in value.values():
            _collect_json(nested, identities, parameter_records)
    elif isinstance(value, list):
        for nested in value:
            _collect_json(nested, identities, parameter_records)


def _implementation_inventory() -> list[dict[str, Any]]:
    paths = [
        *sorted((ROOT / "src/closy_forge/disjoint_confirmation_v2").glob("*.py")),
        *sorted((ROOT / "src/closy_forge/recovery_foundation_v1").glob("*.py")),
        *sorted((ROOT / "src/closy_forge/disjoint_benchmark_v1").glob("*.py")),
        *sorted((ROOT / "scripts").glob("*d0_disjoint_confirmation_v2*.py")),
    ]
    return [
        {"path": _implementation_path(path), "sha256": sha256_file(path)}
        for path in paths
        if path.is_file()
    ]


def _implementation_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return "../" + path.relative_to(ROOT.parent).as_posix()


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("confirmation_v2_list_required")
    return [_mapping(item) for item in value]


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("confirmation_v2_mapping_required")
    return dict(value)


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    issues = check() if args.check else []
    if not args.check:
        build()
    print(json.dumps({"status": "pass" if not issues else "fail", "issues": issues}))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
