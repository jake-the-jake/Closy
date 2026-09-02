from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from closy_forge.blueprint.status import (  # type: ignore[import-untyped]
    build_status_model,
    render_status_summary,
)
from closy_forge.package_io.canonical_json import canonical_dumps  # type: ignore[import-untyped]
from closy_forge.package_io.hashing import sha256_file  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[2]
FORGE_ROOT = REPO_ROOT / "closy-forge"
DOCS_ROOT = FORGE_ROOT / "docs"
EVIDENCE_ROOT = DOCS_ROOT / "evidence" / "final_strategy3_v2"
LOCK_PATH = FORGE_ROOT / "fixtures" / "final_strategy3_v2" / "final_implementation_lock.json"
UNIT_T_HEAD = "0c45587371165f1c5f3e33934ee2cbf5156f9e02"
UNIT_U_LOCK_HEAD = "d76916461d3e96b037fbc31b646319effef7a264"
UNIT_T_AUTHORITY_HEAD = "7aae56b050e72e51916b592423f63d859f166117"
UNIT_U_PUBLICATION_HEAD = "28b4dd93f0c6634f9ad7833f890d12000628e1b2"
AUTHORITY_RUN = "33630862367"
AUTHORITY_WORKFLOW_ID = 348397321
OUTCOME = "dependency_blocked_before_official_seed_v2"
MISMATCHES = [
    {
        "path": "src/closy_forge/recovery_foundation_v2/topology_holdout.py",
        "gitBlobOidSha1": "c1360db65edc6b73735a6c6027495f47eacc49d1",
        "lockedByteLength": 6761,
        "lockedSha256": "372ecba0d34527411d5e184767e399a9225dc49fa3ac21997e2a450e80e09692",
        "repositoryByteLength": 6605,
        "repositorySha256": "3f595f60c5da54df3f9da901738de0000177de251f81e7994a85984823308f6e",
    },
    {
        "path": "src/closy_forge/recovery_foundation_v2/topology_holdout_oracle.py",
        "gitBlobOidSha1": "e77fc707bd943b9b9469250e2f49f7949ec03ecd",
        "lockedByteLength": 3326,
        "lockedSha256": "c0cf79f42ea70ec3ac54ba426a726d65247e57d00759d615797ccd861e573878",
        "repositoryByteLength": 3252,
        "repositorySha256": "ffc96bde5658e59c16373c7cca2f044c8a64db38476942659449fd51e47e88a8",
    },
    {
        "path": "src/closy_forge/simulation/reference_cloth_solver.py",
        "gitBlobOidSha1": "a6c92eb704f6a627d937ebc4faa631a07033107e",
        "lockedByteLength": 49669,
        "lockedSha256": "cfa7ea16dfe952e66adce856cd7cb5700cc0b1074b882cddc76a2f480d38edb9",
        "repositoryByteLength": 48477,
        "repositorySha256": "928069f98f049e0aace9625473c77a93caebc0bda9a7b0afa38b5587086b4f41",
    },
    {
        "path": "src/closy_forge/simulation/self_collision.py",
        "gitBlobOidSha1": "59de2deff7bec9527b474624754bbf6fbb76a233",
        "lockedByteLength": 58989,
        "lockedSha256": "92980ead1dcfc4329a1ef6c6b72847923ffaeae556ee873092d3a9a7fa8f9187",
        "repositoryByteLength": 57533,
        "repositorySha256": "0ddbcb2ff69b878030da91ef9bc9502a1efd5c74da0d8451a52ee3e8b477f5a9",
    },
]


def _digest(document: dict[str, Any], field: str) -> str:
    payload = deepcopy(document)
    payload[field] = ""
    return hashlib.sha256(canonical_dumps(payload).encode("utf-8")).hexdigest()


def _json_bytes(document: object) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _append_unique(values: object, additions: list[Any]) -> list[Any]:
    result = list(values) if isinstance(values, list) else []
    for item in additions:
        if item not in result:
            result.append(item)
    return result


def _event_digest(event: dict[str, Any]) -> str:
    return _digest(event, "eventHash")


def _build_outcome(lock: dict[str, Any]) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "unit": "U",
        "protocolVersion": lock["protocolVersion"],
        "strategyId": lock["strategyId"],
        "strategyClass": lock["strategyClass"],
        "literalOutcome": OUTCOME,
        "firstUnmetPredicate": "locked_implementation_byte_identity_portable_on_authority_checkout",
        "base": {
            "branch": "codex/closy-forge-d0-disjoint-tshirt-confirmation-v3",
            "sha": UNIT_T_HEAD,
        },
        "branch": "codex/closy-forge-phy1-final-strategy3-v2",
        "pullRequest": 55,
        "lock": {
            "headSha": UNIT_U_LOCK_HEAD,
            "lockHash": lock["lockHash"],
            "fileSha256": sha256_file(LOCK_PATH),
            "implementationDigest": lock["implementationDigest"],
            "postLockScientificSurfaceChanged": False,
            "relockPermitted": False,
        },
        "publicConformance": {
            "executedCycles": 2,
            "maximumCycles": 2,
            "cycleResults": ["failed_implementation_conformance", "pass"],
            "finalPassed": 8,
            "finalDenominator": 8,
            "allFixturesUseProductionAssembly": True,
        },
        "portablePreflight": {
            "runId": "33630652037",
            "result": "pass",
            "containerImageId": (
                "sha256:07f54a27f9bce38c5be7c6e26ac906eee2cbaa19c83b68a2354064c80f695247"
            ),
            "ubuntuVerifier": "pass",
            "windowsVerifier": "pass",
            "genericContainerCanary": "pass",
        },
        "officialAuthority": {
            "runId": AUTHORITY_RUN,
            "headSha": UNIT_U_LOCK_HEAD,
            "workflowId": AUTHORITY_WORKFLOW_ID,
            "workflowConclusion": "failure",
            "preflightContainerJobId": "100249654433",
            "preflightContainerJobResult": "failure",
            "ubuntuVerifierJobId": "100249654471",
            "ubuntuVerifierJobResult": "success",
            "windowsVerifierJobId": "100249653848",
            "windowsVerifierJobResult": "success",
            "authorityJobId": "100250251482",
            "authorityJobResult": "skipped",
            "officialSeedCreated": False,
            "officialFixtureCount": 0,
            "strategyContainerExecutions": 0,
            "attemptConsumed": False,
            "rerunPerformed": False,
            "qualificationRetryAllowed": False,
            "artifactUploaded": False,
            "workflowSeal": {
                "mechanism": "github_actions_workflow_disabled_without_changing_locked_bytes",
                "state": "disabled_manually",
                "observedAtUtc": "2026-09-02T12:47:44Z",
            },
        },
        "failure": {
            "class": "pre_seed_portable_lock_byte_identity_failure",
            "cause": "windows_autocrlf_worktree_bytes_were_hashed_instead_of_repository_blob_bytes",
            "publicProofPassedBeforeFailure": True,
            "mismatchCount": len(MISMATCHES),
            "mismatches": MISMATCHES,
            "scientificInterpretation": (
                "dependency block before official seed; not a Strategy-3 scientific result"
            ),
        },
        "admission": {
            "confirmationExecuted": False,
            "admitted": False,
            "unitVEligible": False,
            "unitWEligible": False,
            "unitXEligible": False,
        },
        "budgetsAfter": {
            "seamModels": 0,
            "topologyStrategies": 0,
            "candidateAttempts": 1,
            "untouchedConfirmationAttemptConsumed": False,
        },
        "runtime": {
            "selectedRuntime": "closy.integrated_runtime.headless_d0.v1",
            "packageDigest": "836abc564a79c0f38ae8bdad3d4a418b0fb05a550193059c1cece8130203c20a",
            "fallbackDigest": "8eccea814251f8974f5349548038be73a4d00cec73df7a7bfb787aede58385c6",
            "changed": False,
        },
        "outcomeDigest": "",
    }
    document["outcomeDigest"] = _digest(document, "outcomeDigest")
    return document


def _build_attestation(outcome: dict[str, Any]) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "attestationVersion": "closy.final_strategy3_v2.external_preseed_failure.v1",
        "repository": "jake-the-jake/Closy",
        "branch": outcome["branch"],
        "pullRequest": 55,
        "headSha": UNIT_U_LOCK_HEAD,
        "acquisitionMethod": "authenticated_gh_cli_and_local_git_read_only",
        "authorityClaim": "procedural_freeze_and_container_isolation_not_cryptographic_secrecy",
        "workflow": outcome["officialAuthority"],
        "lockHash": outcome["lock"]["lockHash"],
        "outcome": OUTCOME,
        "outcomeDigest": outcome["outcomeDigest"],
        "seedLifecycle": {
            "officialSeedCreated": False,
            "attemptConsumed": False,
            "rawSeedOrNonceExisted": False,
            "commitmentExisted": False,
            "officialFixtureOrOracleRevealed": False,
        },
        "limitations": [
            "no official holdout was generated or executed",
            "no strategy admission conclusion can be drawn",
            "the prompt forbids relocking the failed locked path",
            "workflow artifacts are absent because the authority job was skipped",
        ],
        "attestationDigest": "",
    }
    document["attestationDigest"] = _digest(document, "attestationDigest")
    return document


def _build_budget_ledger(outcome: dict[str, Any]) -> dict[str, Any]:
    source = json.loads(
        (
            DOCS_ROOT
            / "evidence"
            / "evidence_authority_recovery_v2"
            / "physical_budget_event_ledger.json"
        ).read_text(encoding="utf-8")
    )
    previous = source["derived"]["headEventHash"]
    event: dict[str, Any] = {
        "ordinal": 5,
        "category": "topology_strategy",
        "eventId": "PHY1-V5-S3-SEAM-SEQUENCE-CONFORMING-REMESH-V2",
        "sourcePath": "fixtures/final_strategy3_v2/final_implementation_lock.json",
        "sourceDigest": sha256_file(LOCK_PATH),
        "consumed": True,
        "previousEventHash": previous,
        "eventHash": "",
    }
    event["eventHash"] = _event_digest(event)
    document: dict[str, Any] = {
        "schemaVersion": 3,
        "ledgerVersion": "closy.physical_budget_event_ledger.after_unit_u.v3",
        "extendsLedgerPath": (
            "docs/evidence/evidence_authority_recovery_v2/physical_budget_event_ledger.json"
        ),
        "extendsLedgerDigest": source["canonicalDigest"],
        "maxima": source["maxima"],
        "events": [*source["events"], event],
        "engineeringRevisions": source["engineeringRevisions"],
        "derived": {
            "consumed": {
                "canonical_candidate": 0,
                "seam_model": 2,
                "topology_strategy": 3,
            },
            "remaining": {
                "canonical_candidate": 1,
                "seam_model": 0,
                "topology_strategy": 0,
            },
            "headEventHash": event["eventHash"],
        },
        "unitOV1Outcome": source["unitOV1Outcome"],
        "unitUV2Outcome": outcome["literalOutcome"],
        "untouchedConfirmationAttemptConsumed": False,
        "candidateAttemptConsumed": False,
        "canonicalDigest": "",
    }
    document["canonicalDigest"] = _digest(document, "canonicalDigest")
    return document


def _build_report(outcome: dict[str, Any]) -> str:
    mismatches = "\n".join(
        f"- `{row['path']}`: locked CRLF `{row['lockedSha256']}`; repository LF "
        f"`{row['repositorySha256']}`."
        for row in MISMATCHES
    )
    return f"""# Unit U Final Strategy-3 Confirmation v2

## Literal Outcome

`{OUTCOME}`

The final strategy was reserved and locked as
`PHY1-V5-S3-SEAM-SEQUENCE-CONFORMING-REMESH-V2`. Two bounded public conformance cycles were
used: the first failed implementation conformance and the corrected second cycle passed all
`8/8` fixtures through the production assembly path. The exact generic preflight run
`33630652037` passed its Ubuntu verifier, Windows verifier, container build, and networkless
non-root canary with image
`sha256:07f54a27f9bce38c5be7c6e26ac906eee2cbaa19c83b68a2354064c80f695247`.

## Pre-seed Block

Official run `{AUTHORITY_RUN}` targeted exact lock head `{UNIT_U_LOCK_HEAD}`. Both portable
decision-verifier jobs passed, and the public proof again passed `8/8`. The pinned-container
preflight then failed the lock self-consistency test before image creation because four inherited
files had been hashed from a Windows `core.autocrlf=true` worktree. Their committed repository
blobs are LF, so the Linux authority checkout correctly produced different byte hashes:

{mismatches}

The authority job was skipped. No official seed, nonce, commitment, fixture, oracle value,
strategy execution, or authority artifact existed. The untouched confirmation attempt therefore
was not consumed. This is a locked-path portability/dependency block, not evidence that Strategy
3 passed or failed its scientific gates.

The prompt forbids relocking after the final lock. No locked byte was changed and the authority
was not rerun. GitHub Actions workflow `{AUTHORITY_WORKFLOW_ID}` was disabled in repository
control as `disabled_manually`, sealing dispatch without modifying its locked file bytes.

## Consequences

- Strategy admission: `false`; confirmation was `not_run`.
- Unit V: ineligible because literal Unit-U admission is absent.
- Units W and X: transitively ineligible.
- Topology-strategy budget: `0` remaining; the final reservation/lock consumed the third slot.
- Canonical-candidate budget: `1` remaining; no canonical T-shirt transformation occurred.
- Seam-model budget: `0` remaining.
- Runtime v1 package and conventional fallback remain unchanged.

The locked Strategy-3 implementation and its public `8/8` conformance are preserved as
non-qualifying engineering evidence. A future attempt requires explicit user-authorised successor
methodology and a new portable repository-blob-based lock; this prompt authorises neither a relock
nor another official authority event.
"""


def _update_coverage(coverage: dict[str, Any]) -> dict[str, Any]:
    coverage = deepcopy(coverage)
    coverage["version"] = "closy.blueprint_coverage.final_strategy3_v2_closeout.v22"
    row = next(row for row in coverage["rows"] if row["id"] == "BP-20-RESEARCH-PROTOTYPE")
    row["commitSha"] = _append_unique(
        row.get("commitSha"), [UNIT_T_AUTHORITY_HEAD, UNIT_U_LOCK_HEAD]
    )
    row["implementationPaths"] = _append_unique(
        row.get("implementationPaths"),
        [
            "closy-forge/fixtures/d0_disjoint_tshirt_confirmation_v3",
            "closy-forge/docs/evidence/d0_disjoint_tshirt_confirmation_v3",
            "closy-forge/src/closy_forge/final_strategy3_v2",
            "closy-forge/fixtures/final_strategy3_v2",
            "closy-forge/docs/evidence/final_strategy3_v2",
        ],
    )
    row["executableEvidence"] = _append_unique(
        row.get("executableEvidence"),
        [
            (
                "Unit T completed 64/64 route attempts, 48/48 compiles, and 24/24 appearance "
                "evaluations over 16 recoverable-inventory-disjoint identities"
            ),
            (
                "Unit T leaves D0-RP-03, D0-RP-06, and D0-RP-07 failed while D0-RP-04 "
                "passes; no route was promoted"
            ),
            (
                "Unit U reserved and locked the final seam-sequence-preserving conforming-remesh "
                "topology strategy after two bounded public conformance cycles"
            ),
            (
                "Unit U final public conformance passed 8/8 production-assembly fixtures with "
                "mutation detection and portable decision verifiers"
            ),
            (
                "official Unit U run 33630862367 stopped before seed creation on four "
                "CRLF-versus-LF implementation-lock mismatches"
            ),
            (
                "no Unit U holdout, candidate, PHY1, CCD, post-topology C3, Z1, or Gate-Z2 "
                "execution occurred"
            ),
        ],
    )
    row["tests"] = _append_unique(
        row.get("tests"),
        [
            "closy-forge/tests/unit/test_final_strategy3_v2.py",
            "closy-forge/tests/unit/test_final_strategy3_v2_protocol.py",
            "closy-forge/tests/unit/test_final_strategy3_v2_publication.py",
        ],
    )
    row["summary"] = (
        "Unit T completed but failed its locked absolute D0 gates. Unit U exhausted the final "
        "topology-strategy slot and passed public conformance, but its immutable lock was not "
        "portable to the Linux authority checkout; no official seed or candidate was created."
    )
    row["limitations"] = (
        "D0-RP-03, D0-RP-06, D0-RP-07, and D0-RP-15 remain failed. Strategy-3 admission was "
        "not run because the locked pre-seed path was byte-inconsistent across line-ending "
        "checkouts. No post-topology candidate, PHY1, integrated CCD, solver-driven Z2, private, "
        "device, human, Alpha, Beta, or Production evidence exists."
    )
    row["nextAction"] = (
        "No unit in this finite prompt is dependency-ready; preserve the exhausted topology lane "
        "until separately authorised successor methodology exists."
    )
    provenance = coverage["generatedBy"]
    provenance["generatorVersion"] = "closy.blueprint_publication.final_strategy3_v2.v19"
    additions = [
        "closy-forge/fixtures/final_strategy3_v2/strategy_design_reservation.json",
        "closy-forge/fixtures/final_strategy3_v2/final_implementation_lock.json",
        "closy-forge/docs/evidence/final_strategy3_v2/public_conformance.json",
    ]
    provenance["declaredInputPaths"] = _append_unique(provenance["declaredInputPaths"], additions)
    digest = hashlib.sha256()
    for relative in sorted(provenance["declaredInputPaths"]):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((REPO_ROOT / relative).read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    provenance["sourceTreeHash"] = digest.hexdigest()
    return coverage


def _topological_order(nodes: list[dict[str, Any]], edges: list[dict[str, str]]) -> list[str]:
    declared = [str(node["id"]) for node in nodes]
    position = {node_id: index for index, node_id in enumerate(declared)}
    incoming = {node_id: set[str]() for node_id in declared}
    outgoing = {node_id: set[str]() for node_id in declared}
    for edge in edges:
        incoming[edge["to"]].add(edge["from"])
        outgoing[edge["from"]].add(edge["to"])
    ready = [node_id for node_id in declared if not incoming[node_id]]
    result: list[str] = []
    while ready:
        ready.sort(key=position.__getitem__)
        node_id = ready.pop(0)
        result.append(node_id)
        for target in sorted(outgoing[node_id], key=position.__getitem__):
            incoming[target].discard(node_id)
            if not incoming[target] and target not in result and target not in ready:
                ready.append(target)
    if len(result) != len(declared):
        raise ValueError("unit_u_publication_pr_dag_cycle")
    return result


def _update_stack(stack: dict[str, Any]) -> dict[str, Any]:
    stack = deepcopy(stack)
    rows = [row for row in stack["pullRequests"] if int(row["number"]) not in {54, 55}]
    rows.extend(
        [
            {
                "baseBranch": "codex/closy-forge-evidence-authority-recovery-v2",
                "baseSha": "b8d222dadbe092e25604b838e7ad219d6a1c114b",
                "branch": "codex/closy-forge-d0-disjoint-tshirt-confirmation-v3",
                "changedFileCount": 80,
                "directParentMergeBaseVerified": True,
                "draft": True,
                "headSha": UNIT_T_HEAD,
                "knownException": None,
                "latestExactHeadForgeRun": {
                    "exactHead": True,
                    "runId": "33624168164",
                    "workflow": "Closy Forge",
                    "conclusion": "SUCCESS",
                    "forgeJobCount": 29,
                    "successfulForgeJobCount": 29,
                    "forgeJobCountSemantics": (
                        "all jobs in the Closy Forge workflow; unrelated skipped checks are "
                        "excluded"
                    ),
                },
                "layerAhead": 6,
                "layerBehind": 0,
                "layerCommitCount": 6,
                "mergeBase": "b8d222dadbe092e25604b838e7ad219d6a1c114b",
                "mergeability": "MERGEABLE",
                "number": 54,
                "repository": "jake-the-jake/Closy",
                "role": "d0_disjoint_tshirt_confirmation_v3_failed_absolute_gates",
                "state": "OPEN",
                "title": "Forge Unit T: untouched D0 T-shirt confirmation v3",
                "url": "https://github.com/jake-the-jake/Closy/pull/54",
            },
            {
                "baseBranch": "codex/closy-forge-d0-disjoint-tshirt-confirmation-v3",
                "baseSha": UNIT_T_HEAD,
                "branch": "codex/closy-forge-phy1-final-strategy3-v2",
                "changedFileCount": 38,
                "directParentMergeBaseVerified": True,
                "draft": True,
                "headSha": UNIT_U_PUBLICATION_HEAD,
                "knownException": {
                    "code": "exact_head_ci_recorded_outside_generated_evidence",
                    "descendantEvidenceIsExactHead": False,
                    "reason": (
                        "PR #55 final exact-head CI is recorded in the draft PR body because "
                        "this generated report is anchored to its immutable publication source"
                    ),
                },
                "latestExactHeadForgeRun": None,
                "layerAhead": 8,
                "layerBehind": 0,
                "layerCommitCount": 8,
                "mergeBase": UNIT_T_HEAD,
                "mergeability": "MERGEABLE",
                "number": 55,
                "repository": "jake-the-jake/Closy",
                "role": "final_strategy3_v2_dependency_blocked_before_official_seed",
                "state": "OPEN",
                "title": "Forge Unit U: final Strategy 3 confirmation v2",
                "url": "https://github.com/jake-the-jake/Closy/pull/55",
            },
        ]
    )
    rows.sort(key=lambda row: int(row["number"]))
    stack["pullRequests"] = rows

    nodes = [
        node
        for node in stack["nodes"]
        if not (
            node["repository"] == "jake-the-jake/Closy" and int(node["pullRequest"]) in {54, 55}
        )
    ]
    external_index = next(
        (index for index, node in enumerate(nodes) if node["repository"] != "jake-the-jake/Closy"),
        len(nodes),
    )
    new_nodes = [
        {
            "ahead": 6,
            "baseRef": "codex/closy-forge-evidence-authority-recovery-v2",
            "baseSha": "b8d222dadbe092e25604b838e7ad219d6a1c114b",
            "behind": 0,
            "branch": "codex/closy-forge-d0-disjoint-tshirt-confirmation-v3",
            "capabilityRole": "forge_unit_t_untouched_d0_t_shirt_confirmation_v3",
            "changedFileCount": 80,
            "dependencyIds": [],
            "headSha": UNIT_T_HEAD,
            "id": "github:jake-the-jake/Closy:pr/54",
            "integrationMappings": [],
            "latestExactHeadWorkflows": [
                {
                    "workflow": "Closy Forge",
                    "runId": "33624168164",
                    "exactHead": True,
                    "conclusion": "SUCCESS",
                    "jobCount": 29,
                },
                {
                    "workflow": "Forge Unit T D0 v3 authority",
                    "runId": "33624168111",
                    "exactHead": True,
                    "conclusion": "SUCCESS",
                    "jobCount": 1,
                },
            ],
            "mergeBase": "b8d222dadbe092e25604b838e7ad219d6a1c114b",
            "mergeEligible": True,
            "neverMergeWith": [],
            "parentIds": [],
            "pullRequest": 54,
            "repository": "jake-the-jake/Closy",
            "role": "d0_disjoint_tshirt_confirmation_v3_failed_absolute_gates",
            "sourceOnly": False,
            "state": "OPEN",
            "superseded": False,
            "uniqueCommitRange": (
                "b8d222dadbe092e25604b838e7ad219d6a1c114b.."
                "0c45587371165f1c5f3e33934ee2cbf5156f9e02"
            ),
        },
        {
            "ahead": 8,
            "baseRef": "codex/closy-forge-d0-disjoint-tshirt-confirmation-v3",
            "baseSha": UNIT_T_HEAD,
            "behind": 0,
            "branch": "codex/closy-forge-phy1-final-strategy3-v2",
            "capabilityRole": "forge_unit_u_final_strategy_3_confirmation_v2",
            "changedFileCount": 38,
            "dependencyIds": ["github:jake-the-jake/Closy:pr/54"],
            "headSha": UNIT_U_PUBLICATION_HEAD,
            "id": "github:jake-the-jake/Closy:pr/55",
            "integrationMappings": [],
            "latestExactHeadWorkflows": [],
            "mergeBase": UNIT_T_HEAD,
            "mergeEligible": True,
            "neverMergeWith": [],
            "parentIds": ["github:jake-the-jake/Closy:pr/54"],
            "pullRequest": 55,
            "repository": "jake-the-jake/Closy",
            "role": "final_strategy3_v2_dependency_blocked_before_official_seed",
            "sourceOnly": False,
            "state": "OPEN",
            "superseded": False,
            "uniqueCommitRange": f"{UNIT_T_HEAD}..{UNIT_U_PUBLICATION_HEAD}",
        },
    ]
    nodes[external_index:external_index] = new_nodes
    stack["nodes"] = nodes
    edges = [
        edge
        for edge in stack["edges"]
        if not any(
            f"pr/{number}" in edge[endpoint] for number in (54, 55) for endpoint in ("from", "to")
        )
    ]
    edges.extend(
        [
            {
                "from": "github:jake-the-jake/Closy:pr/54",
                "kind": "parent",
                "to": "github:jake-the-jake/Closy:pr/55",
            },
            {
                "from": "github:jake-the-jake/Closy:pr/54",
                "kind": "dependency",
                "to": "github:jake-the-jake/Closy:pr/55",
            },
        ]
    )
    stack["edges"] = edges
    stack["topologicalOrder"] = _topological_order(nodes, edges)
    stack["graphCounts"] = {
        "closyPullRequests": len(rows),
        "externalPullRequests": len(stack["externalPullRequests"]),
        "nodes": len(nodes),
        "edges": len(edges),
    }
    return stack


def _update_status(coverage: dict[str, Any], stack: dict[str, Any]) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        build_status_model(coverage, stack, evidence_anchor_sha=UNIT_U_LOCK_HEAD),
    )


def _update_resume(resume: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    resume = deepcopy(resume)
    resume.update(
        {
            "machineResumeVersion": "closy.active_blueprint_resume.final_strategy3_v2.v13",
            "activeLane": "finite sequence complete after Unit U pre-seed dependency block",
            "branch": "codex/closy-forge-phy1-final-strategy3-v2",
            "pullRequest": 55,
            "evidenceHead": UNIT_U_LOCK_HEAD,
            "latestFinishedParentPublicationHead": UNIT_T_HEAD,
            "localHeadAtResumeSource": "pending_final_publication_commit",
            "remoteHeadAtResumeSource": "pending_final_publication_commit",
            "pendingCIAtEvidenceHead": True,
            "parent": {
                "branch": "codex/closy-forge-d0-disjoint-tshirt-confirmation-v3",
                "pullRequest": 54,
                "sha": UNIT_T_HEAD,
                "exactHeadWorkflow": "33624168164",
                "forgeJobsPassed": 29,
                "forgeJobsTotal": 29,
            },
            "remainingBudgets": {
                "candidateAttempts": 1,
                "seamModels": 0,
                "topologyStrategies": 0,
            },
            "conditionalUnits": {
                "T": "complete_failed_absolute_gates",
                "U": "complete_dependency_blocked_before_official_seed_v2",
                "V": "ineligible_unit_u_not_admitted",
                "W": "ineligible_no_unit_v_candidate",
                "X": "ineligible_no_unit_w_core_prerequisites",
            },
            "stopReason": "unit_u_locked_path_dependency_blocked_before_official_seed_v2",
            "exactNextAction": (
                "No further unit is authorised or dependency-ready; preserve the locked failure "
                "and await separately authorised successor methodology."
            ),
            "nextHandoff": {
                "selection": "none_dependency_ready",
                "firstUnmetPrerequisite": "unit_u_literal_untouched_admission_pass",
                "safestEvidenceAction": "preserve_locked_preseed_failure_without_relock_or_rerun",
            },
            "unitUResult": {
                "outcome": outcome["literalOutcome"],
                "strategyId": outcome["strategyId"],
                "strategyClass": outcome["strategyClass"],
                "lockHead": UNIT_U_LOCK_HEAD,
                "lockHash": outcome["lock"]["lockHash"],
                "publicConformancePassCount": 8,
                "publicConformanceDenominator": 8,
                "preflightRun": "33630652037",
                "preflightImageId": outcome["portablePreflight"]["containerImageId"],
                "authorityRun": AUTHORITY_RUN,
                "authorityJob": "100250251482",
                "authorityJobResult": "skipped",
                "officialSeedCreated": False,
                "confirmationAttemptConsumed": False,
                "candidateAttemptConsumed": False,
                "candidateCreated": False,
                "mismatchCount": 4,
                "relockAllowed": False,
                "rerunPerformed": False,
                "authorityWorkflowState": "disabled_manually",
                "unitVEligible": False,
            },
        }
    )
    resume["gates"]["PHY1-Topology-Strategy3-Confirmation-D0-v2"] = OUTCOME
    resume["matrixScopes"]["postTopologyCandidate"] = {
        "candidateExists": False,
        "matrixNotRunReason": "unit_u_dependency_blocked_before_official_seed_v2",
    }
    return resume


def _resume_markdown(outcome: dict[str, Any]) -> str:
    return f"""# Active Blueprint Resume

## Current Lane

- Unit: `U` closed; Units `V`, `W`, and `X` are ineligible.
- Branch: `codex/closy-forge-phy1-final-strategy3-v2`
- Draft PR: `#55`
- Exact parent: `{UNIT_T_HEAD}` (PR #54)
- Exact scientific lock: `{UNIT_U_LOCK_HEAD}`
- Official authority workflow: `{AUTHORITY_RUN}`
- Authority job: `100250251482` (`skipped` before seed)

## Literal State

- Unit U outcome: `{OUTCOME}`.
- Public conformance: `8/8` after exactly two bounded cycles.
- Exact generic preflight: run `33630652037`, including both portable verifiers and pinned
  networkless/non-root container canary, passed.
- Official authority: both portable verifiers passed, but the pinned-container lock check found
  four CRLF-versus-LF implementation hash mismatches before image creation.
- Official seed, commitment, fixture, oracle, and strategy execution: none.
- Confirmation attempt consumed: `false`; relock and rerun: not authorised.
- Strategy admission: `false`; Unit V eligibility: `false`.
- Unit T rows: D0-RP-03 `fail`, D0-RP-04: `pass`, D0-RP-06 `fail`, D0-RP-07 `fail`.
- Current Research Prototype core: `7 pass / 4 fail / 0 not-run`.
- Current supplemental: `2 pass / 0 fail / 2 not-run`.
- Runtime remains `closy.integrated_runtime.headless_d0.v1`.
- Package remains `836abc564a79c0f38ae8bdad3d4a418b0fb05a550193059c1cece8130203c20a`.
- Fallback remains `8eccea814251f8974f5349548038be73a4d00cec73df7a7bfb787aede58385c6`.
- Remaining budgets: seam models `0`, topology strategies `0`, candidate attempts `1`.

## Next Action

No further review unit in this finite prompt is dependency-ready. Preserve the immutable lock and
pre-seed failure. Do not relock, rerun the authority, create Unit V, transform the canonical
T-shirt, or claim Strategy-3 admission. A successor requires separate user authorisation.
"""


def _update_master_progress(current: str) -> str:
    marker = "## Final Strategy-3 Semantic-Remesh Confirmation v2 Outcome"
    prefix = current.split(marker, 1)[0].rstrip()
    return (
        prefix
        + f"""

{marker}

Unit U reserved the last topology strategy as
`PHY1-V5-S3-SEAM-SEQUENCE-CONFORMING-REMESH-V2`, implemented ordered semantic seam transfer,
rebuilt transferred attributes and bindings, exercised coupled production assembly and independent
CCD controls, and used exactly two public conformance cycles. The corrected second cycle passed all
`8/8` public production-path fixtures. Exact external preflight run `33630652037` passed both
portable verifiers and its pinned, networkless, non-root container canary.

The immutable lock was committed at `{UNIT_U_LOCK_HEAD}`. Official authority run `{AUTHORITY_RUN}`
then stopped before seed creation: its public proof passed `8/8` and both portable verifiers passed,
but the Linux pinned-container job found four implementation hash mismatches. The lock builder had
hashed CRLF-expanded Windows worktree bytes for four inherited files while Git stores LF blobs.
The authority job was skipped, no official fixture or expected value was revealed, no confirmation
attempt was consumed, and no scientific admission result exists.

The locked path cannot be relocked under this prompt, so the literal outcome is `{OUTCOME}`. The
third topology strategy is consumed; the one canonical-candidate attempt remains unspent. Units V,
W, and X are ineligible. Runtime v1 package
`836abc564a79c0f38ae8bdad3d4a418b0fb05a550193059c1cece8130203c20a` and fallback
`8eccea814251f8974f5349548038be73a4d00cec73df7a7bfb787aede58385c6` remain selected.
"""
    )


def build_documents() -> dict[Path, bytes]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    outcome = _build_outcome(lock)
    attestation = _build_attestation(outcome)
    ledger = _build_budget_ledger(outcome)
    coverage = _update_coverage(
        json.loads((DOCS_ROOT / "blueprint_coverage.json").read_text(encoding="utf-8"))
    )
    stack = _update_stack(
        json.loads((DOCS_ROOT / "pr_stack_manifest.json").read_text(encoding="utf-8"))
    )
    status = _update_status(coverage, stack)
    resume = _update_resume(
        json.loads((DOCS_ROOT / "ACTIVE_BLUEPRINT_RESUME.json").read_text(encoding="utf-8")),
        outcome,
    )
    documents = {
        EVIDENCE_ROOT / "outcome_report.json": _json_bytes(outcome),
        EVIDENCE_ROOT / "external_authority_attestation.json": _json_bytes(attestation),
        EVIDENCE_ROOT / "physical_budget_event_ledger_after_unit_u.json": _json_bytes(ledger),
        EVIDENCE_ROOT / "REPORT.md": _build_report(outcome).encode("utf-8"),
        DOCS_ROOT / "blueprint_coverage.json": _json_bytes(coverage),
        DOCS_ROOT / "pr_stack_manifest.json": _json_bytes(stack),
        DOCS_ROOT / "current_blueprint_status.json": _json_bytes(status),
        DOCS_ROOT / "BLUEPRINT_STATUS_SUMMARY.md": render_status_summary(status).encode("utf-8"),
        DOCS_ROOT / "ACTIVE_BLUEPRINT_RESUME.json": _json_bytes(resume),
        DOCS_ROOT / "ACTIVE_BLUEPRINT_RESUME.md": _resume_markdown(outcome).encode("utf-8"),
        DOCS_ROOT / "MASTER_BLUEPRINT_PROGRESS.md": _update_master_progress(
            (DOCS_ROOT / "MASTER_BLUEPRINT_PROGRESS.md").read_text(encoding="utf-8")
        ).encode("utf-8"),
    }
    return documents


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the immutable Unit-U publication record.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    documents = build_documents()
    stale: list[str] = []
    for path, expected in documents.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != expected:
                stale.append(path.relative_to(REPO_ROOT).as_posix())
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(expected)
    if stale:
        raise SystemExit("stale final Strategy-3 v2 publication: " + ", ".join(stale))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
