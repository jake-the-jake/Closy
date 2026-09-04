from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .common import canonical_digest

HEX256 = re.compile(r"^[0-9a-f]{64}$")
HEX_GIT = re.compile(r"^[0-9a-f]{40,64}$")
REQUIRED_BINDINGS = (
    "protocolDigest",
    "candidateDigest",
    "generatorImplementationDigest",
    "evaluatorImplementationDigest",
    "corpusPartitionDigest",
    "modelCheckpointDigest",
    "authorityIdentity",
    "seedIdentity",
    "gitCommit",
    "gitTree",
)


def verify_evidence_eligibility(
    artifact: Mapping[str, Any],
    registry_record: Mapping[str, Any],
    *,
    observation_sequence: int,
) -> dict[str, Any]:
    failures: list[str] = []
    for field in REQUIRED_BINDINGS:
        expected = registry_record.get(field)
        observed = artifact.get(field)
        if expected in (None, ""):
            failures.append(f"registry_{field}_missing")
        elif observed != expected:
            failures.append(f"evidence_{field}_mismatch")
        elif field.endswith("Digest") and not HEX256.fullmatch(str(observed)):
            failures.append(f"evidence_{field}_invalid")
    if not HEX_GIT.fullmatch(str(artifact.get("gitCommit", ""))):
        failures.append("evidence_gitCommit_invalid")
    if not HEX_GIT.fullmatch(str(artifact.get("gitTree", ""))):
        failures.append("evidence_gitTree_invalid")
    fixture_kind = str(artifact.get("fixtureKind", ""))
    registered_fixture_kinds = {
        str(value) for value in registry_record.get("registeredFixtureKinds", [])
    }
    if not fixture_kind or fixture_kind not in registered_fixture_kinds:
        failures.append("unregistered_fixture_kind_rejected")
    allowed_claims = set(str(value) for value in registry_record.get("allowedClaims", []))
    requested_claims = set(str(value) for value in artifact.get("requestedClaims", []))
    if not requested_claims.issubset(allowed_claims):
        failures.append("producer_claim_elevation_rejected")
    evidence_class = str(registry_record.get("evidenceClass", ""))
    if not evidence_class:
        failures.append("registry_evidence_class_missing")
    if artifact.get("evidenceClass") not in (None, evidence_class):
        failures.append("producer_evidence_class_substitution_rejected")
    freeze_sequence = int(registry_record.get("freezeSequence", -1))
    result_sequence = int(registry_record.get("resultSequence", -1))
    if freeze_sequence < 0 or result_sequence <= freeze_sequence:
        failures.append("registry_freeze_sequence_invalid")
    if observation_sequence < freeze_sequence:
        failures.append("observation_precedes_freeze")
    if observation_sequence > result_sequence:
        disclosure_exception = (
            fixture_kind == "commitment_matching_synthetic_truth_disclosure"
            and not requested_claims
            and artifact.get("canonicalResultDigest")
            == registry_record.get("canonicalResultDigest")
        )
        if not disclosure_exception:
            failures.append("post_result_claim_elevation_rejected")
    seed_consumed = bool(registry_record.get("seedConsumed", False))
    if bool(artifact.get("seedConsumed", False)) != seed_consumed:
        failures.append("seed_consumption_state_mismatch")
    verified: dict[str, Any] = {
        "schemaVersion": 1,
        "verifierVersion": "closy.verifier_owned_evidence_eligibility.v1",
        "eligible": not failures,
        "evidenceClass": evidence_class if not failures else "ineligible",
        "allowedClaims": sorted(allowed_claims) if not failures else [],
        "reasonCodes": sorted(set(failures)),
        "producerEligibilityFieldsIgnored": [
            "fixtureKind",
            "qualificationEligible",
            "scientificEvidenceEligible",
            "pass",
            "status",
        ],
    }
    verified["verificationDigest"] = canonical_digest(verified)
    return verified
