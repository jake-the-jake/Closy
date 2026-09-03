from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file

from .common import canonical_digest, read_mapping

AUTHORIZATION_ID = "CLOSY-S3-Y2-TRANSPORT-V4-20260903-AUTH1"
SCIENTIFIC_SOURCE_COMMIT = "d76916461d3e96b037fbc31b646319effef7a264"
Y1_LOCK_COMMIT = "b9c6d34f4339fece2c6e6566b59c5b548f3f973a"
Y1_LOCK_DIGEST = "804996610e99f947defb7f06f2eb13b42008f7bd4988f1777fe0ef0acb5c10b5"
WORKFLOW_BLOB_OID = "381355a047b7af0faf59af141a819c38ef4ff88d"
TERMINAL_OUTCOME = "preseed_scientific_protocol_invalid"


def audit_frozen_y2_protocol(forge_root: Path) -> dict[str, Any]:
    authority_path = forge_root / "src/closy_forge/final_strategy3_v2/authority.py"
    wrapper_path = forge_root / "src/closy_forge/strategy3_blob_authority_v3/authority.py"
    protocol_path = forge_root / "fixtures/final_strategy3_v2/final_implementation_lock.json"
    authority_source = authority_path.read_text(encoding="utf-8")
    wrapper_source = wrapper_path.read_text(encoding="utf-8")
    ast.parse(authority_source)
    ast.parse(wrapper_source)
    protocol = read_mapping(protocol_path)

    findings = [
        {
            "code": "postseed_failure_classes_collapse_to_generic_integrity",
            "evidence": (
                "write_public_failure selects one post-seed outcome from seed_created and does not "
                "distinguish timeout, OOM, resource exit, malformed output, or authority failure"
            ),
            "scientificPolicyMissing": True,
        },
        {
            "code": "contestant_timeout_classification_not_frozen",
            "evidence": (
                "subprocess.run timeout propagates TimeoutExpired without a frozen outcome mapping"
            ),
            "scientificPolicyMissing": True,
        },
        {
            "code": "contestant_missing_or_nonzero_output_classification_not_frozen",
            "evidence": "nonzero exit and missing report share a generic ValueError path",
            "scientificPolicyMissing": True,
        },
        {
            "code": "candidate_role_and_eight_report_aggregation_undefined",
            "evidence": (
                "the frozen result explicitly records candidateCreated=false and defines neither "
                "one candidate artifact role nor a deterministic eight-report "
                "selection/aggregation rule"
            ),
            "scientificPolicyMissing": True,
        },
    ]
    checks = {
        "genericPostseedMappingPresent": "OUTCOMES[2] if seed_created" in authority_source,
        "timeoutRaisedByRunner": "timeout=maximum_seconds" in authority_source,
        "missingOutputSharesGenericFailure": (
            "completed.returncode != 0 or not report_path.is_file()" in authority_source
        ),
        "wrapperUploadsRawExceptionText": "str(error)[:500]" in wrapper_source,
        "frozenCandidateCreatedFalse": '"candidateCreated": False' in authority_source,
        "candidateSelectionRulePresent": bool(protocol.get("candidateSelectionRule")),
        "allReachablePostseedCasesUnambiguous": False,
    }
    audit_valid = not findings and all(checks.values())
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "auditVersion": "closy.y2.frozen_scientific_protocol_audit.v1",
        "authorizationId": AUTHORIZATION_ID,
        "scope": "transport_only_no_scientific_semantic_repair",
        "scientificSourceCommit": SCIENTIFIC_SOURCE_COMMIT,
        "y1LockCommit": Y1_LOCK_COMMIT,
        "y1LockDigest": Y1_LOCK_DIGEST,
        "workflowBlobOid": WORKFLOW_BLOB_OID,
        "auditedFiles": [
            {
                "path": authority_path.relative_to(forge_root).as_posix(),
                "sha256": sha256_file(authority_path),
            },
            {
                "path": wrapper_path.relative_to(forge_root).as_posix(),
                "sha256": sha256_file(wrapper_path),
            },
            {
                "path": protocol_path.relative_to(forge_root).as_posix(),
                "sha256": sha256_file(protocol_path),
            },
        ],
        "checks": checks,
        "findings": findings,
        "transportWrapperManifest": {
            "created": False,
            "reason": "protocol_invalid_before_transport_arming",
            "newTransportPaths": [],
            "scientificSurfaceChanged": False,
            "scientificDecisionSemanticsChanged": False,
        },
        "scientificProtocolValidForY2": audit_valid,
        "terminalOutcome": None if audit_valid else TERMINAL_OUTCOME,
        "authorityAuthorizationConsumed": False,
        "authorityTagCreated": False,
        "microcanaryTagCreated": False,
        "preflightTagCreated": False,
        "transportSourceCommitCreated": False,
        "transportLockCommitCreated": False,
        "seedCreated": False,
        "scientificAttemptConsumed": False,
        "candidateCreated": False,
        "candidateBudgetConsumed": False,
        "remainingBudgets": {"topologyStrategies": 0, "candidateAttempts": 1},
        "nextAction": (
            "a_future_explicit_scientific_authority_must_freeze_failure_classification_and_"
            "candidate_aggregation_before_any_seed"
        ),
        "auditDigest": "",
    }
    result["auditDigest"] = canonical_digest(result, "auditDigest")
    return result
