from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.disjoint_confirmation_v3.protocol import (
    FIXTURE_ROOT,
    UNIT_S_HEAD,
    WORKFLOW_PATH,
    build_protocol,
    canonical_source_sha256,
    validate_implementation,
    validate_protocol,
)
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.recovery_foundation_v2.evaluator_v3 import mutation_report
from closy_forge.recovery_foundation_v2.pixel_routes import build_pixel_causal_controls

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models/d0_v3/public_pixel_fitted_tshirt_v1.json"
INVENTORY_PATH = ROOT / "docs/evidence/evidence_authority_recovery_v2/typed_prior_inventory.json"


def build() -> dict[str, Any]:
    target = ROOT / FIXTURE_ROOT
    target.mkdir(parents=True, exist_ok=True)
    model = _mapping(read_json(MODEL_PATH))
    inventory = _mapping(read_json(INVENTORY_PATH))
    implementation = _implementation_inventory()
    workflow = ROOT / WORKFLOW_PATH
    protocol = build_protocol(
        implementation_files=implementation,
        workflow_sha256=canonical_source_sha256(workflow),
        model_sha256=canonical_source_sha256(MODEL_PATH),
        model_digest=str(model["modelDigest"]),
        typed_inventory_digest=str(inventory["inventoryDigest"]),
    )
    issues = validate_protocol(protocol)
    if issues:
        raise ValueError(";".join(issues))
    write_canonical_json(target / "protocol_lock.json", protocol)
    causal = build_pixel_causal_controls(model)
    causal_pass = all(
        causal[field] is True
        for field in (
            "missingPixelsRejected",
            "pixelMutationChangesObservation",
            "cropAndOcclusionChangeBytes",
            "negativeModelChangesPrediction",
            "learnedAndMaskRoutesDistinct",
        )
    ) and (
        causal["metadataControlConsumesPixels"] is False
        and causal["sourceObservedPbrFraction"] == 0.0
    )
    mutations = mutation_report()
    development = {
        "schemaVersion": 1,
        "proofVersion": "closy.d0_disjoint_tshirt_confirmation.development_proof.v3",
        "classification": "public_pre_v3_and_revealed_contaminated_fixtures_only",
        "qualificationEligible": False,
        "officialSeedCreated": False,
        "officialIdentityCreated": False,
        "evaluatorMutationReport": mutations,
        "pixelCausalControls": causal,
        "allEvaluatorMutationsDetected": all(mutations.values()),
        "allPixelCausalControlsPass": causal_pass,
        "proofHash": "",
    }
    development["proofHash"] = _hash({**development, "proofHash": ""})
    write_canonical_json(target / "development_proof.json", development)
    report = {
        "schemaVersion": 1,
        "reportVersion": "closy.d0_disjoint_tshirt_confirmation.lock_report.v3",
        "unitSHead": UNIT_S_HEAD,
        "protocolLockHash": protocol["lockHash"],
        "implementationDigest": protocol["implementationDigest"],
        "typedPriorInventoryDigest": inventory["inventoryDigest"],
        "modelDigest": model["modelDigest"],
        "officialSeedCreated": False,
        "officialCohortCreated": False,
        "officialAttemptState": "not_started",
        "nextAction": "exact_lock_head_external_preflight_before_one_authority_trigger",
    }
    write_canonical_json(target / "lock_report.json", report)
    implementation_issues = validate_implementation(ROOT, protocol)
    if implementation_issues:
        raise ValueError(";".join(implementation_issues))
    return report


def check() -> list[str]:
    names = ("protocol_lock.json", "development_proof.json", "lock_report.json")
    before = {name: (ROOT / FIXTURE_ROOT / name).read_bytes() for name in names}
    build()
    return [
        name for name, data in before.items() if (ROOT / FIXTURE_ROOT / name).read_bytes() != data
    ]


def _implementation_inventory() -> list[dict[str, Any]]:
    paths = [
        *sorted((ROOT / "src/closy_forge/disjoint_confirmation_v3").glob("*.py")),
        *sorted((ROOT / "src/closy_forge/disjoint_benchmark_v1").glob("*.py")),
        *sorted((ROOT / "src/closy_forge/recovery_foundation_v2").glob("*.py")),
        *sorted((ROOT / "src/closy_forge/garments/tshirt").rglob("*.py")),
        *sorted((ROOT / "src/closy_forge/package_io").glob("*.py")),
        ROOT / "docker/d0_v3/Dockerfile",
        ROOT / "docker/d0_v3/entrypoint.sh",
        ROOT / "docker/d0_v3/runner.py",
        ROOT / "docker/d0_v3_confirmation/Dockerfile",
        ROOT / "docker/d0_v3_confirmation/entrypoint.sh",
        ROOT / "docker/d0_v3_confirmation/runner_v3.py",
        ROOT / "scripts/build_d0_disjoint_confirmation_v3_lock.py",
        ROOT / "scripts/run_d0_disjoint_confirmation_v3_authority.py",
        ROOT / "scripts/import_d0_disjoint_confirmation_v3_attempt.py",
        ROOT / WORKFLOW_PATH,
    ]
    unique = sorted({path.resolve() for path in paths}, key=lambda path: path.as_posix())
    return [
        {"path": _relative(path), "sha256": canonical_source_sha256(path)}
        for path in unique
        if path.is_file()
    ]


def _relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return "../" + path.relative_to(ROOT.parent).as_posix()


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("d0_v3_mapping_required")
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
