from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.recovery_foundation_v2.pixel_routes import build_public_training_inventory

from .common import canonical_digest, load_mapping, records


def build_typed_record_inventory(forge_root: Path) -> dict[str, Any]:
    training = build_public_training_inventory()
    development_path = Path("fixtures/d0_disjoint_tshirt_benchmark_v1/development_lock.json")
    phase9_path = Path("docs/evidence/phase9_raster_synthetic_d0/corpus_manifest.json")
    prior_path = Path("docs/evidence/evidence_authority_recovery_v2/typed_prior_inventory.json")
    qualification_path = Path(
        "fixtures/d0_disjoint_tshirt_confirmation_v3/official_attempt/authority_commitments.json"
    )
    development = load_mapping(forge_root / development_path)
    phase9 = load_mapping(forge_root / phase9_path)
    prior = load_mapping(forge_root / prior_path)
    qualification = load_mapping(forge_root / qualification_path)
    groups = [
        _group(
            "public_pixel_training",
            "training",
            "generated:recovery_foundation_v2.build_public_training_inventory",
            str(training["inventoryDigest"]),
            records(training.get("records")),
        ),
        _group(
            "v1_public_development",
            "development",
            development_path.as_posix(),
            sha256_file(forge_root / development_path),
            records(development.get("developmentIdentities")),
        ),
        _group(
            "phase9_train_validation_test",
            "prior",
            phase9_path.as_posix(),
            sha256_file(forge_root / phase9_path),
            records(phase9.get("captureRecords")),
        ),
        _group(
            "recoverable_prior_source_registry",
            "prior",
            prior_path.as_posix(),
            sha256_file(forge_root / prior_path),
            records(prior.get("sources")),
        ),
        _group(
            "d0_v3_official_qualification",
            "qualification_contaminated_after_reveal",
            qualification_path.as_posix(),
            sha256_file(forge_root / qualification_path),
            records(qualification.get("cohortCommitments")),
        ),
    ]
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "inventoryVersion": "closy.typed_record_inventory.successor.v2",
        "groups": groups,
        "groupCount": len(groups),
        "nominalRecordCount": sum(int(group["nominalRecordCount"]) for group in groups),
        "uniqueRecordCount": sum(int(group["uniqueRecordCount"]) for group in groups),
        "unrecoverableV2OpaqueCohort": {
            "availability": "unrecoverable",
            "recordIdentityAvailable": False,
            "disjointnessClaim": "unverified",
        },
        "inventoryDigest": "",
    }
    document["inventoryDigest"] = canonical_digest(document, "inventoryDigest")
    return document


def validate_typed_record_inventory(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    groups = records(document.get("groups"))
    if not groups or document.get("groupCount") != len(groups):
        issues.append("typed_inventory_group_denominator_invalid")
    for group in groups:
        rows = records(group.get("records"))
        if group.get("nominalRecordCount") != len(rows):
            issues.append(f"typed_inventory_nominal_count_invalid:{group.get('groupId')}")
        digests = [str(row.get("identityDigest", "")) for row in rows]
        if any(len(value) != 64 for value in digests):
            issues.append(f"typed_inventory_record_digest_invalid:{group.get('groupId')}")
        if group.get("uniqueRecordCount") != len(set(digests)):
            issues.append(f"typed_inventory_unique_count_invalid:{group.get('groupId')}")
        if group.get("recordsDigest") != sha256_bytes(canonical_dumps(rows).encode("utf-8")):
            issues.append(f"typed_inventory_records_digest_invalid:{group.get('groupId')}")
    if document.get("nominalRecordCount") != sum(
        int(group.get("nominalRecordCount", -1)) for group in groups
    ):
        issues.append("typed_inventory_total_nominal_invalid")
    if document.get("uniqueRecordCount") != sum(
        int(group.get("uniqueRecordCount", -1)) for group in groups
    ):
        issues.append("typed_inventory_total_unique_invalid")
    if document.get("inventoryDigest") != canonical_digest(document, "inventoryDigest"):
        issues.append("typed_inventory_digest_invalid")
    return sorted(set(issues))


def _group(
    group_id: str,
    evidence_class: str,
    source_path: str,
    source_digest: str,
    source_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    materialized: list[dict[str, Any]] = []
    for ordinal, source in enumerate(source_records):
        payload = _identity_payload(source)
        identity_digest = sha256_bytes(canonical_dumps(payload).encode("utf-8"))
        record_digest = sha256_bytes(canonical_dumps(dict(source)).encode("utf-8"))
        materialized.append(
            {
                "ordinal": ordinal,
                "identityDigest": identity_digest,
                "recordDigest": record_digest,
            }
        )
    return {
        "groupId": group_id,
        "evidenceClass": evidence_class,
        "sourcePath": source_path,
        "sourceDigest": source_digest,
        "nominalRecordCount": len(materialized),
        "uniqueRecordCount": len({row["identityDigest"] for row in materialized}),
        "records": materialized,
        "recordsDigest": sha256_bytes(canonical_dumps(materialized).encode("utf-8")),
    }


def _identity_payload(source: Mapping[str, Any]) -> dict[str, Any]:
    payload = deepcopy(dict(source))
    for key in ("ordinal", "recordOrdinal", "captureOrdinal", "sampleOrdinal"):
        payload.pop(key, None)
    return payload
