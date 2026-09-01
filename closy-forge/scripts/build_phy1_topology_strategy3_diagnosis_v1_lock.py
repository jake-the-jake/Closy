from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.phy1_topology_strategy3_diagnosis_v1.protocol import (
    AUTHORITY_PATH,
    CONFIRMATION_GENERATOR_PATH,
    LOCK_PATH,
    LOCK_REPORT_PATH,
    build_diagnosis_lock,
    build_starting_authority,
    validate_lock,
)


def build(root: Path) -> dict[Path, dict[str, Any]]:
    authority = build_starting_authority(root)
    lock = build_diagnosis_lock(root, authority)
    issues = validate_lock(root, lock)
    if issues:
        raise ValueError(f"unit_o_lock_invalid:{','.join(issues)}")
    confirmation_generator = dict(lock["confirmationGenerator"])
    report = {
        "schemaVersion": 1,
        "unit": "O",
        "state": "frozen_before_bounded_revision_execution",
        "repository": "jake-the-jake/Closy",
        "branch": "codex/closy-forge-phy1-topology-strategy3-diagnosis-v1",
        "pullRequest": "pending_external_attestation",
        "base": {
            "branch": "codex/closy-forge-d0-strict-c3-confirmation-v5",
            "sha": "e062a30ba295ed27334622916ddb449fd76e2166",
            "mergeBase": "e062a30ba295ed27334622916ddb449fd76e2166",
        },
        "parentEvidence": {
            "unit": "N",
            "publishedHead": "e062a30ba295ed27334622916ddb449fd76e2166",
            "authorityRun": 33546821637,
            "authorityJob": 99986277154,
            "sealedEvidenceRun": 33547909364,
            "forgeRun": 33547909132,
            "forgeJobsPassed": 29,
            "forgeJobsTotal": 29,
        },
        "sourceEvidenceAnchorSha": authority["sourceEvidenceAnchorSha"],
        "authorityDigest": authority["integrity"]["authorityDigest"],
        "diagnosisLockDigest": lock["integrity"]["lockDigest"],
        "developmentFixtureCount": len(lock["developmentFixtures"]),
        "maximumPreCandidateRevisions": lock["maximumPreCandidateRevisions"],
        "confirmationGeneratorFrozen": True,
        "confirmationSeedRealized": False,
        "confirmationInstancesRealized": False,
        "candidateCreated": False,
        "candidateAttemptConsumed": False,
        "finalStrategyConsumed": False,
        "remainingBudgets": {
            "seamModels": 0,
            "topologyStrategies": 1,
            "candidateAttempts": 1,
        },
        "implementationIssues": issues,
        "externalAttestation": "pending_external_attestation",
    }
    return {
        AUTHORITY_PATH: authority,
        LOCK_PATH: lock,
        CONFIRMATION_GENERATOR_PATH: confirmation_generator,
        LOCK_REPORT_PATH: report,
    }


def write(root: Path, documents: dict[Path, dict[str, Any]]) -> None:
    for path, document in documents.items():
        write_canonical_json(root / path, document)


def check(root: Path, documents: dict[Path, dict[str, Any]]) -> None:
    for path, document in documents.items():
        if read_json(root / path) != document:
            raise ValueError(f"unit_o_lock_regeneration_drift:{path.as_posix()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze or verify the Unit O diagnosis lock.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    documents = build(root)
    if args.check:
        check(root, documents)
    else:
        write(root, documents)
    print("unit_o_lock=ok revisions_executed=0 confirmation_seed_realized=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
