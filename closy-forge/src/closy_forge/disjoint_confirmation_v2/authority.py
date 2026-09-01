from __future__ import annotations

import hashlib
import hmac
import json
import platform
import secrets
import shutil
import sys
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from closy_forge.disjoint_benchmark_v1.compiler import compile_structural_candidate
from closy_forge.disjoint_benchmark_v1.corpus import (
    RealizedIdentity,
    realize_identities,
    verify_target_commitment,
)
from closy_forge.disjoint_benchmark_v1.development import (
    build_source_evidence,
    contestant_input,
)
from closy_forge.disjoint_benchmark_v1.protocol import normalized_distance
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, sha256_file

from .evaluator import execute_evaluator
from .isolation import execute_contestant, run_container_negative_controls
from .protocol import FIXTURE_ROOT, ROUTES, load_protocol, validate_implementation


def run_official_attempt(
    root: Path,
    *,
    output: Path,
    lock_sha: str,
    workflow_run_id: str,
    workflow_job_id: str,
    require_container: bool = True,
) -> dict[str, Any]:
    if output.exists():
        raise ValueError("confirmation_v2_output_must_not_preexist")
    protocol = load_protocol(root)
    implementation_issues = validate_implementation(root, protocol)
    if implementation_issues:
        raise ValueError(";".join(implementation_issues))
    lifecycle = _mapping(protocol["seedAuthorityLifecycle"])
    workflow = root.parent / ".github/workflows/closy-forge-unit-m-authority.yml"
    if sha256_file(workflow) != lifecycle.get("initialWorkflowSha256"):
        raise ValueError("confirmation_v2_initial_authority_workflow_hash_mismatch")
    output.mkdir(parents=True)
    private_store = output / ".authority_private_until_prediction_freeze"
    private_store.mkdir()
    raw_seed = secrets.token_hex(32)
    seed_digest = sha256_bytes(bytes.fromhex(raw_seed))
    prior_inventory = _mapping(read_json(root / FIXTURE_ROOT / "prior_inventory.json"))
    references = [_mapping(item) for item in _records(prior_inventory.get("parameterRecords", []))]
    realized, transcript = realize_identities(
        seed_hex=raw_seed,
        count=16,
        role="evaluator_v2",
        minimum_prior_distance=0.18,
        references=references,
        maximum_attempts=65_536,
    )
    identities = [_augment_identity(identity, raw_seed) for identity in realized]
    targets: dict[str, Any] = {
        "schemaVersion": 1,
        "targetVersion": "closy.d0_disjoint_tshirt_confirmation.targets.v2",
        "identities": [
            {**identity.target_record(), "ordinal": identity.ordinal, "stratum": identity.stratum}
            for identity in identities
        ],
    }
    if not all(verify_target_commitment(item) for item in targets["identities"]):
        raise ValueError("confirmation_v2_target_commitment_invalid")
    write_canonical_json(private_store / "targets.json", targets)
    write_canonical_json(private_store / "raw_draw_rejection_transcript.json", transcript)
    (private_store / "raw_seed.txt").write_text(raw_seed + "\n", encoding="ascii")

    sources, source_files = _build_sources(output, identities)
    disjointness = _audit_fresh_disjointness(
        identities=identities,
        source_files=source_files,
        prior_inventory=prior_inventory,
    )
    if not disjointness["allDisjoint"]:
        raise ValueError("confirmation_v2_fresh_cohort_not_disjoint")
    transcript_digest = _hash(transcript)
    commitments = {
        "schemaVersion": 1,
        "authorityVersion": "closy.d0_disjoint_tshirt_confirmation.authority.v2",
        "eventOrdinal": 1,
        "event": "cohort_truth_and_source_observations_committed_private_targets_unmounted",
        "sourceLockSha": lock_sha,
        "protocolLockHash": protocol["lockHash"],
        "implementationDigest": protocol["implementationDigest"],
        "workflowRunId": workflow_run_id,
        "workflowJobId": workflow_job_id,
        "authorityInput": {
            "repository": "jake-the-jake/Closy",
            "branch": "codex/closy-forge-d0-disjoint-tshirt-confirmation-v2",
            "seedBits": 256,
            "seedGeneratedBy": "python_secrets_token_hex_in_trusted_authority_job",
        },
        "seedDigest": seed_digest,
        "rawSeedPublishedBeforePredictionFreeze": False,
        "rawTranscriptDigest": transcript_digest,
        "acceptedIdentityCount": 16,
        "firstAcceptedDrawImmutable": True,
        "cohortCommitments": [
            {
                "ordinal": identity.ordinal,
                "opaqueId": identity.opaque_id,
                "stratum": identity.stratum,
                "targetCommitment": identity.target_commitment,
                "sourceEvidenceHash": _hash(sources[identity.opaque_id]),
            }
            for identity in identities
        ],
        "disjointness": disjointness,
        "targetStoreMountedToContestant": False,
        "proceduralIsolationClaimOnly": True,
        "authorityHash": "",
    }
    commitments["authorityHash"] = _hash({**commitments, "authorityHash": ""})
    write_canonical_json(output / "authority_commitments.json", commitments)

    boundary = run_container_negative_controls()
    if require_container and boundary.get("qualifiesD0Rp04") is not True:
        raise ValueError("confirmation_v2_required_container_boundary_failed")
    predictions, isolation_records = _freeze_predictions(
        root=root,
        identities=identities,
        sources=sources,
        require_container=require_container,
    )
    prediction_freeze = {
        "schemaVersion": 1,
        "freezeVersion": "closy.d0_disjoint_tshirt_confirmation.prediction_freeze.v2",
        "eventOrdinal": 2,
        "event": "all_route_predictions_frozen_before_private_target_mount",
        "authorityHash": commitments["authorityHash"],
        "predictionCount": len(predictions["predictions"]),
        "predictionDenominator": 64,
        "routeCounts": {
            route: sum(item["routeId"] == route for item in predictions["predictions"])
            for route in ROUTES
        },
        "predictionSetHash": _hash(predictions),
        "targetStoreMountedToContestant": False,
        "contestantWorkspacesDestroyed": True,
        "networkAccessOccurred": False,
        "predictionEditedAfterFreeze": False,
        "freezeHash": "",
    }
    prediction_freeze["freezeHash"] = _hash({**prediction_freeze, "freezeHash": ""})
    write_canonical_json(output / "predictions.json", predictions)
    write_canonical_json(output / "prediction_freeze.json", prediction_freeze)
    write_canonical_json(
        output / "isolation_report.json",
        {
            "schemaVersion": 1,
            "boundaryNegativeControls": boundary,
            "predictionExecutions": isolation_records,
            "allPredictionExecutionsContainerEnforced": all(
                item["isolationClass"] == "docker_container_enforced_filesystem_and_network_denial"
                for item in isolation_records
            ),
            "qualifiesD0Rp04": boundary.get("qualifiesD0Rp04") is True
            and all(item.get("allOpenedPathsAllowed") is True for item in isolation_records),
        },
    )

    reveal = {
        "schemaVersion": 1,
        "revealVersion": "closy.d0_disjoint_tshirt_confirmation.target_reveal.v2",
        "eventOrdinal": 3,
        "event": "existing_private_targets_seed_nonces_and_transcript_revealed_after_freeze",
        "predictionFreezeHash": prediction_freeze["freezeHash"],
        "targetsGeneratedAtReveal": False,
        "targetsReplacedAtReveal": False,
        "rawSeed": raw_seed,
        "rawSeedDigest": seed_digest,
        "rawDrawRejectionTranscript": transcript,
        "rawTranscriptDigest": transcript_digest,
        "targets": targets,
        "allCommitmentsVerified": all(
            verify_target_commitment(item) for item in targets["identities"]
        ),
        "revealHash": "",
    }
    reveal["revealHash"] = _hash({**reveal, "revealHash": ""})
    write_canonical_json(output / "target_reveal.json", reveal)
    shutil.rmtree(private_store)

    isolation_summary = _mapping(read_json(output / "isolation_report.json"))
    result = execute_evaluator(
        root,
        protocol=protocol,
        predictions=predictions,
        targets=targets,
        isolation_summary=isolation_summary,
    )
    write_canonical_json(output / "benchmark_result.json", result)
    manifest = _attempt_manifest(
        output=output,
        lock_sha=lock_sha,
        workflow_run_id=workflow_run_id,
        workflow_job_id=workflow_job_id,
        protocol=protocol,
        result=result,
    )
    write_canonical_json(output / "attempt_manifest.json", manifest)
    return result


def _augment_identity(identity: RealizedIdentity, raw_seed: str) -> RealizedIdentity:
    pbr_bytes = hmac.new(
        bytes.fromhex(raw_seed), f"pbr:{identity.ordinal}".encode(), hashlib.sha512
    ).digest()
    seam_bytes = hmac.new(
        bytes.fromhex(raw_seed), f"seam:{identity.ordinal}".encode(), hashlib.sha256
    ).digest()
    parameters = dict(identity.parameters)
    parameters["neckband_length_ease_ratio"] = round(0.88 + seam_bytes[0] / 255 * 0.08, 9)
    appearance = {
        **identity.appearance,
        "roughness": round(0.45 + pbr_bytes[0] / 255 * 0.45, 6),
        "metalness": round(pbr_bytes[1] / 255 * 0.05, 6),
        "ambientOcclusion": round(0.80 + pbr_bytes[2] / 255 * 0.20, 6),
    }
    capture = json.loads(json.dumps(identity.capture))
    capture["lighting"] = {
        "keyIntensity": round(0.85 + pbr_bytes[3] / 255 * 0.30, 6),
        "fillIntensity": round(0.30 + pbr_bytes[4] / 255 * 0.25, 6),
        "temperatureKelvin": 4600 + int(pbr_bytes[5]) * 8,
    }
    draw = {"parameters": parameters, "appearance": appearance, "capture": capture}
    draw_digest = _hash(draw)
    target_payload = {
        "opaqueId": identity.opaque_id,
        "parameters": parameters,
        "appearance": appearance,
        "capture": capture,
        "drawDigest": draw_digest,
    }
    commitment = sha256_bytes(
        identity.nonce.encode("ascii") + canonical_dumps(target_payload).encode("utf-8")
    )
    return replace(
        identity,
        parameters=parameters,
        appearance=appearance,
        capture=capture,
        target_commitment=commitment,
        draw_digest=draw_digest,
    )


def _build_sources(
    output: Path, identities: list[RealizedIdentity]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    source_root = output / "source_roles"
    sources: dict[str, dict[str, Any]] = {}
    files: list[dict[str, Any]] = []
    for identity in identities:
        source = build_source_evidence(identity)
        public = {key: value for key, value in source.items() if key != "png"}
        sources[identity.opaque_id] = public
        identity_root = source_root / identity.opaque_id
        write_canonical_json(identity_root / "source_features.json", public)
        for role, payload in sorted(_mapping(source["png"]).items()):
            path = identity_root / f"{role}.png"
            path.write_bytes(bytes(payload))
            files.append(
                {
                    "opaqueId": identity.opaque_id,
                    "role": role,
                    "path": path.relative_to(output).as_posix(),
                    "sha256": sha256_file(path),
                }
            )
    write_canonical_json(
        output / "public_source_inventory.json",
        {
            "schemaVersion": 1,
            "identityCount": len(identities),
            "files": files,
            "sourceFeatures": [
                {"opaqueId": opaque_id, "sha256": _hash(source)}
                for opaque_id, source in sorted(sources.items())
            ],
        },
    )
    return sources, files


def _freeze_predictions(
    *,
    root: Path,
    identities: list[RealizedIdentity],
    sources: Mapping[str, Mapping[str, Any]],
    require_container: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    development = _mapping(
        read_json(root / "fixtures/d0_disjoint_tshirt_benchmark_v1/development_lock.json")
    )
    config = _mapping(development["contenderConfiguration"])
    executable = root / "src/closy_forge/disjoint_benchmark_v1/contender_cli.py"
    predictions: list[dict[str, Any]] = []
    isolation_records: list[dict[str, Any]] = []
    for identity in identities:
        for route in ROUTES:
            legacy_route = "metadata_category_prior" if route == "metadata_only_control" else route
            payload = contestant_input(
                identity.opaque_id, sources[identity.opaque_id], legacy_route
            )
            prediction, isolation = execute_contestant(
                executable=executable,
                route=route,
                input_payload=payload,
                config=config,
                require_container=require_container,
            )
            predictions.append(prediction)
            isolation_records.append(
                {
                    "opaqueId": identity.opaque_id,
                    "ordinal": identity.ordinal,
                    **isolation,
                }
            )
    if len(predictions) != 64:
        raise ValueError(f"confirmation_v2_prediction_denominator_invalid:{len(predictions)}")
    return {
        "schemaVersion": 1,
        "predictionVersion": "closy.d0_disjoint_tshirt_confirmation.predictions.v2",
        "predictions": predictions,
    }, isolation_records


def _audit_fresh_disjointness(
    *,
    identities: list[RealizedIdentity],
    source_files: list[dict[str, Any]],
    prior_inventory: Mapping[str, Any],
) -> dict[str, Any]:
    prior_ids = set(str(value) for value in prior_inventory.get("identityValues", []))
    prior_parameters = set(str(value) for value in prior_inventory.get("parameterHashes", []))
    prior_pixels = set(str(value) for value in prior_inventory.get("pixelHashes", []))
    prior_geometry = set(str(value) for value in prior_inventory.get("geometryHashes", []))
    prior_targets = set(str(value) for value in prior_inventory.get("targetFeatureHashes", []))
    identity_values = [identity.opaque_id for identity in identities]
    parameter_hashes = [_hash(identity.parameters) for identity in identities]
    pixel_hashes = [str(item["sha256"]) for item in source_files]
    geometry_hashes = [
        geometry_content_hash(compile_structural_candidate(identity.parameters).rest_mesh)
        for identity in identities
    ]
    target_hashes = [_hash(identity.target_record()) for identity in identities]
    collisions = {
        "identity": sorted(set(identity_values) & prior_ids),
        "parameters": sorted(set(parameter_hashes) & prior_parameters),
        "pixels": sorted(set(pixel_hashes) & prior_pixels),
        "geometry": sorted(set(geometry_hashes) & prior_geometry),
        "targetFeatures": sorted(set(target_hashes) & prior_targets),
    }
    within_cohort = {
        "identityUnique": len(set(identity_values)) == 16,
        "parameterUnique": len(set(parameter_hashes)) == 16,
        "geometryUnique": len(set(geometry_hashes)) == 16,
        "pixelUnique": len(set(pixel_hashes)) == len(pixel_hashes),
    }
    distances = [
        normalized_distance(left.parameters, right.parameters)
        for index, left in enumerate(identities)
        for right in identities[index + 1 :]
    ]
    return {
        "priorInventoryDigest": prior_inventory.get("inventoryDigest"),
        "collisions": collisions,
        "withinCohort": within_cohort,
        "minimumWithinCohortNormalizedParameterDistance": round(min(distances), 9),
        "allDisjoint": all(not values for values in collisions.values())
        and all(within_cohort.values()),
    }


def _attempt_manifest(
    *,
    output: Path,
    lock_sha: str,
    workflow_run_id: str,
    workflow_job_id: str,
    protocol: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    files = [
        {
            "path": path.relative_to(output).as_posix(),
            "sha256": sha256_file(path),
            "byteLength": path.stat().st_size,
        }
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "attempt_manifest.json"
    ]
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "manifestVersion": "closy.d0_disjoint_tshirt_confirmation.attempt_manifest.v2",
        "repository": "jake-the-jake/Closy",
        "branch": "codex/closy-forge-d0-disjoint-tshirt-confirmation-v2",
        "baseBranch": "codex/closy-forge-d0-recovery-foundation-v1",
        "baseSha": "a72f45955abbe65ce14b7142668447d0477db71c",
        "sourceEvidenceAnchorSha": protocol["sourceEvidenceAnchorSha"],
        "implementationLockSha": lock_sha,
        "mergeBase": "a72f45955abbe65ce14b7142668447d0477db71c",
        "workflowRunId": workflow_run_id,
        "workflowJobId": workflow_job_id,
        "platform": platform.platform(),
        "python": sys.version,
        "protocolLockHash": protocol["lockHash"],
        "implementationDigest": protocol["implementationDigest"],
        "attemptState": result["attemptState"],
        "literalResult": result["outcome"],
        "files": files,
        "manifestHash": "",
    }
    manifest["manifestHash"] = _hash({**manifest, "manifestHash": ""})
    return manifest


def _records(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("confirmation_v2_list_required")
    return value


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("confirmation_v2_mapping_required")
    return dict(value)


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
