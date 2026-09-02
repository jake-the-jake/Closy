from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from closy_forge.disjoint_benchmark_v1.compiler import compile_structural_candidate
from closy_forge.disjoint_benchmark_v1.corpus import (
    RealizedIdentity,
    default_prior,
    realize_identities,
    verify_target_commitment,
)
from closy_forge.disjoint_benchmark_v1.development import build_source_evidence
from closy_forge.disjoint_benchmark_v1.protocol import normalized_distance
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, sha256_file

from .evaluator import execute_evaluator, validate_result
from .isolation import execute_route, run_canary
from .protocol import (
    PRIMARY_ROUTE,
    ROUTES,
    SEED_NAMESPACE,
    UNIT_S_HEAD,
    load_protocol,
    validate_implementation,
)

BRANCH = "codex/closy-forge-d0-disjoint-tshirt-confirmation-v3"
MODEL_PATH = Path("models/d0_v3/public_pixel_fitted_tshirt_v1.json")
TYPED_INVENTORY_PATH = Path(
    "docs/evidence/evidence_authority_recovery_v2/typed_prior_inventory.json"
)
LEGACY_INVENTORY_PATH = Path("fixtures/d0_disjoint_tshirt_confirmation_v2/prior_inventory.json")
SOURCE_ROLE_SCHEDULE = {
    ordinal: (["front_png"] if ordinal in {6, 14} else ["front_png", "rear_png"])
    for ordinal in range(16)
}


def run_official_attempt(
    root: Path,
    *,
    output: Path,
    lock_sha: str,
    workflow_run_id: str,
    workflow_job_id: str,
    image_reference: str,
) -> dict[str, Any]:
    if output.exists():
        raise ValueError("d0_v3_output_must_not_preexist")
    protocol = load_protocol(root)
    if lock_sha == UNIT_S_HEAD:
        raise ValueError("d0_v3_lock_must_be_dedicated_commit")
    implementation_issues = validate_implementation(root, protocol)
    if implementation_issues:
        raise ValueError(";".join(implementation_issues))
    output.mkdir(parents=True)
    private_store = output / ".authority_private_until_prediction_freeze"
    private_store.mkdir()

    raw_entropy = secrets.token_bytes(32)
    seed_hex = hmac.new(raw_entropy, SEED_NAMESPACE, hashlib.sha256).hexdigest()
    environment = {
        "schemaVersion": 1,
        "authorityEnvironment": "github_actions_ubuntu_trusted_evaluator_workspace",
        "platform": platform.platform(),
        "python": sys.version,
        "entropyApi": "python.secrets.token_bytes_backed_by_os_csprng",
        "entropyBits": 256,
        "rawEntropyDigest": sha256_bytes(raw_entropy),
        "domainSeparationUtf8Hex": SEED_NAMESPACE.hex(),
        "derivedSeedDigest": sha256_bytes(bytes.fromhex(seed_hex)),
        "workflowRunId": workflow_run_id,
        "workflowJobId": workflow_job_id,
        "lockSha": lock_sha,
        "authorityClaim": "procedural_freeze_and_container_isolation_not_cryptographic_secrecy",
    }
    _durable_json(output / "environment_attestation.json", environment, freeze=True)

    legacy_inventory = _mapping(read_json(root / LEGACY_INVENTORY_PATH))
    references = [_mapping(row) for row in _records(legacy_inventory.get("parameterRecords"))]
    realized, transcript = realize_identities(
        seed_hex=seed_hex,
        count=16,
        role="evaluator_v3",
        minimum_prior_distance=0.18,
        references=references,
        maximum_attempts=65_536,
    )
    identities = [_augment_identity(identity, seed_hex) for identity in realized]
    targets: dict[str, Any] = {
        "schemaVersion": 1,
        "targetVersion": "closy.d0_disjoint_tshirt_confirmation.targets.v3",
        "identities": [
            {**identity.target_record(), "ordinal": identity.ordinal, "stratum": identity.stratum}
            for identity in identities
        ],
    }
    if not all(verify_target_commitment(row) for row in targets["identities"]):
        raise ValueError("d0_v3_target_commitment_invalid")
    _durable_json(private_store / "targets.json", targets)
    _durable_json(private_store / "raw_draw_rejection_transcript.json", transcript)
    _durable_bytes(private_store / "raw_seed.txt", seed_hex.encode("ascii") + b"\n")

    sources, source_files = _build_sources(output, identities)
    disjointness = _audit_disjointness(
        identities=identities,
        source_files=source_files,
        prior_inventory=legacy_inventory,
        typed_inventory=_mapping(read_json(root / TYPED_INVENTORY_PATH)),
    )
    if disjointness["overallRecoverableInventoryPass"] is not True:
        raise ValueError("d0_v3_recoverable_inventory_disjointness_failed")
    transcript_digest = _hash(transcript)
    commitments = {
        "schemaVersion": 1,
        "authorityVersion": "closy.d0_disjoint_tshirt_confirmation.authority.v3",
        "eventOrdinal": 1,
        "event": (
            "truth_sources_and_private_targets_created_public_commitments_"
            "fsynced_before_prediction"
        ),
        "lockSha": lock_sha,
        "protocolLockHash": protocol["lockHash"],
        "implementationDigest": protocol["implementationDigest"],
        "workflowRunId": workflow_run_id,
        "workflowJobId": workflow_job_id,
        "seedDigest": environment["derivedSeedDigest"],
        "rawSeedPublishedBeforePredictionFreeze": False,
        "rawTranscriptDigest": transcript_digest,
        "acceptedIdentityCount": 16,
        "acceptedDenominatorImmutable": True,
        "cohortCommitments": [
            {
                "ordinal": identity.ordinal,
                "opaqueId": identity.opaque_id,
                "stratum": identity.stratum,
                "targetCommitment": identity.target_commitment,
                "sourceEvidenceHash": _hash(sources[identity.opaque_id]),
                "availableSourceRoles": SOURCE_ROLE_SCHEDULE[identity.ordinal],
            }
            for identity in identities
        ],
        "disjointness": disjointness,
        "targetStoreMountedToContestant": False,
        "commitmentGuarantee": "procedural_ordering_inside_single_job_uploaded_after_job",
        "externallyImmutablePreEvaluationClaimed": False,
        "authorityClaim": "procedural_freeze_and_container_isolation_not_cryptographic_secrecy",
        "authorityHash": "",
    }
    commitments["authorityHash"] = _hash({**commitments, "authorityHash": ""})
    _durable_json(output / "authority_commitments.json", commitments, freeze=True)

    canary = run_canary(image_reference=image_reference)
    if canary.get("pass") is not True:
        raise ValueError("d0_v3_official_container_canary_failed")
    predictions, attempt_rows, isolation_records, repeats = _freeze_predictions(
        root=root,
        output=output,
        identities=identities,
        image_reference=image_reference,
        source_files=source_files,
    )
    prediction_document = {
        "schemaVersion": 1,
        "predictionVersion": "closy.d0_disjoint_tshirt_confirmation.predictions.v3",
        "predictionCount": 64,
        "attemptRows": attempt_rows,
        "predictions": predictions,
    }
    freeze = {
        "schemaVersion": 1,
        "freezeVersion": "closy.d0_disjoint_tshirt_confirmation.prediction_freeze.v3",
        "eventOrdinal": 2,
        "event": "all_64_attempt_rows_and_16_primary_repeats_frozen_before_target_reveal",
        "authorityHash": commitments["authorityHash"],
        "attemptDenominator": 64,
        "attemptRowCount": len(attempt_rows),
        "successfulPredictionArtifactCount": sum(row["status"] == "pass" for row in attempt_rows),
        "routeCounts": {
            route: sum(row["routeId"] == route for row in attempt_rows) for route in ROUTES
        },
        "primaryRepeatDenominator": 16,
        "primaryRepeatCount": len(repeats),
        "predictionSetHash": _hash(prediction_document),
        "repeatSetHash": _hash(repeats),
        "targetStoreMountedToContestant": False,
        "contestantAccessTerminated": True,
        "contestantWorkspacesDestroyed": True,
        "predictionsEditedAfterFreeze": False,
        "freezeHash": "",
    }
    freeze["freezeHash"] = _hash({**freeze, "freezeHash": ""})
    _durable_json(output / "predictions.json", prediction_document, freeze=True)
    _durable_json(output / "prediction_freeze.json", freeze, freeze=True)
    isolation_summary = {
        "schemaVersion": 1,
        "canary": canary,
        "attemptExecutions": isolation_records,
        "executionDenominator": 80,
        "executionCount": len(isolation_records),
        "allExecutionsContainerEnforced": len(isolation_records) == 80
        and all(
            row.get("isolationClass") == "pinned_nonroot_networkless_readonly_container"
            for row in isolation_records
        ),
        "allWorkspacesDestroyed": all(
            row.get("workspaceDestroyedAfterReturn") is True for row in isolation_records
        ),
        "qualifiesD0Rp04": canary.get("pass") is True
        and len(isolation_records) == 80
        and all(row.get("targetStoreMounted") is False for row in isolation_records),
    }
    _durable_json(output / "isolation_report.json", isolation_summary, freeze=True)

    targets = _mapping(read_json(private_store / "targets.json"))
    revealed_transcript = read_json(private_store / "raw_draw_rejection_transcript.json")
    revealed_seed = (private_store / "raw_seed.txt").read_text(encoding="ascii").strip()
    reveal = {
        **targets,
        "revealVersion": "closy.d0_disjoint_tshirt_confirmation.target_reveal.v3",
        "eventOrdinal": 3,
        "event": "preexisting_targets_seed_nonces_and_transcript_revealed_after_prediction_freeze",
        "predictionFreezeHash": freeze["freezeHash"],
        "rawSeedHex": revealed_seed,
        "rawDrawRejectionTranscript": revealed_transcript,
        "rawTranscriptDigest": _hash(revealed_transcript),
        "replacementTargetsGenerated": False,
        "revealHash": "",
    }
    reveal["revealHash"] = _hash({**reveal, "revealHash": ""})
    _durable_json(output / "target_reveal.json", reveal, freeze=True)
    shutil.rmtree(private_store)

    post_freeze_issues = validate_implementation(root, protocol)
    changed_path_audit = _changed_path_audit(root, lock_sha, protocol)
    _durable_json(output / "changed_path_audit.json", changed_path_audit, freeze=True)
    integrity_pass = not post_freeze_issues and changed_path_audit["pass"] is True
    result = execute_evaluator(
        root,
        protocol=protocol,
        predictions=prediction_document,
        targets=targets,
        isolation_summary=isolation_summary,
        contestant_repeats=repeats,
        integrity_pass=integrity_pass,
    )
    result_issues = validate_result(result)
    if result_issues:
        raise ValueError(";".join(result_issues))
    _durable_json(output / "benchmark_result.json", result, freeze=True)
    manifest = _attempt_manifest(
        output=output,
        lock_sha=lock_sha,
        workflow_run_id=workflow_run_id,
        workflow_job_id=workflow_job_id,
        protocol=protocol,
        result=result,
    )
    _durable_json(output / "attempt_manifest.json", manifest, freeze=True)
    return result


def write_public_failure(
    output: Path,
    *,
    stage: str,
    failure_type: str,
    seed_created: bool,
    workflow_run_id: str,
    workflow_job_id: str,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    private = output / ".authority_private_until_prediction_freeze"
    if private.exists():
        shutil.rmtree(private)
    outcome = (
        "attempted_integrity_error" if seed_created else "dependency_blocked_before_official_seed"
    )
    document = {
        "schemaVersion": 1,
        "failureVersion": "closy.d0_disjoint_tshirt_confirmation.public_failure.v3",
        "outcome": outcome,
        "stage": stage,
        "failureType": failure_type,
        "officialSeedCreated": seed_created,
        "qualificationRetryAllowed": not seed_created,
        "workflowRunId": workflow_run_id,
        "workflowJobId": workflow_job_id,
        "privateArtifactsRemoved": True,
        "rawSeedIncluded": False,
        "nonceIncluded": False,
        "targetIncluded": False,
        "failureHash": "",
    }
    document["failureHash"] = _hash({**document, "failureHash": ""})
    _durable_json(output / "public_failure.json", document, freeze=True)
    return document


def _augment_identity(identity: RealizedIdentity, seed_hex: str) -> RealizedIdentity:
    pbr = hmac.new(
        bytes.fromhex(seed_hex), f"pbr:{identity.ordinal}".encode(), hashlib.sha512
    ).digest()
    seam = hmac.new(
        bytes.fromhex(seed_hex), f"seam:{identity.ordinal}".encode(), hashlib.sha256
    ).digest()
    parameters = dict(identity.parameters)
    parameters["neckband_length_ease_ratio"] = round(0.88 + seam[0] / 255 * 0.08, 9)
    appearance = {
        **identity.appearance,
        "roughness": round(0.45 + pbr[0] / 255 * 0.45, 6),
        "metalness": round(pbr[1] / 255 * 0.05, 6),
        "ambientOcclusion": round(0.80 + pbr[2] / 255 * 0.20, 6),
        "pbrObservability": "bounded_preset_unobserved_source_fraction_zero",
    }
    capture = json.loads(json.dumps(identity.capture))
    capture["lighting"] = {
        "keyIntensity": round(0.85 + pbr[3] / 255 * 0.30, 6),
        "fillIntensity": round(0.30 + pbr[4] / 255 * 0.25, 6),
        "temperatureKelvin": 4600 + int(pbr[5]) * 8,
        "backgroundSrgb": [int(pbr[6]), int(pbr[7]), int(pbr[8])],
    }
    capture["sourceRoleAvailability"] = SOURCE_ROLE_SCHEDULE[identity.ordinal]
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
        draw_digest=draw_digest,
        target_commitment=commitment,
    )


def _build_sources(
    output: Path, identities: Sequence[RealizedIdentity]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    source_root = output / "source_roles"
    sources: dict[str, dict[str, Any]] = {}
    files: list[dict[str, Any]] = []
    for identity in identities:
        evidence = build_source_evidence(identity)
        public = {key: value for key, value in evidence.items() if key != "png"}
        public["availableSourceRoles"] = SOURCE_ROLE_SCHEDULE[identity.ordinal]
        sources[identity.opaque_id] = public
        identity_root = source_root / identity.opaque_id
        identity_root.mkdir(parents=True, exist_ok=True)
        _durable_json(identity_root / "source_features.json", public)
        pngs = _mapping(evidence.get("png"))
        for role in SOURCE_ROLE_SCHEDULE[identity.ordinal]:
            source_role = "front" if role == "front_png" else "rear"
            payload = pngs.get(source_role)
            if not isinstance(payload, bytes | bytearray):
                raise ValueError(f"d0_v3_source_png_missing:{identity.ordinal}:{source_role}")
            path = identity_root / f"{source_role}.png"
            _durable_bytes(path, bytes(payload))
            files.append(
                {
                    "opaqueId": identity.opaque_id,
                    "ordinal": identity.ordinal,
                    "role": role,
                    "path": path.relative_to(output).as_posix(),
                    "sha256": sha256_file(path),
                    "byteLength": path.stat().st_size,
                    "cropAppliedToBytes": float(identity.capture.get("cropFraction", 0.0)) > 0.0,
                    "occlusionAppliedToBytes": float(identity.capture.get("occlusionFraction", 0.0))
                    > 0.0,
                }
            )
    inventory = {
        "schemaVersion": 1,
        "identityCount": 16,
        "fileCount": len(files),
        "files": files,
        "sourceFeatureHashes": [
            {"opaqueId": opaque_id, "sha256": _hash(source)}
            for opaque_id, source in sorted(sources.items())
        ],
        "preObstructionPixelsExposed": False,
        "inventoryHash": "",
    }
    inventory["inventoryHash"] = _hash({**inventory, "inventoryHash": ""})
    _durable_json(output / "public_source_inventory.json", inventory, freeze=True)
    return sources, files


def _freeze_predictions(
    *,
    root: Path,
    output: Path,
    identities: Sequence[RealizedIdentity],
    image_reference: str,
    source_files: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    model_path = root / MODEL_PATH
    file_by_key = {
        (int(row["ordinal"]), str(row["role"])): output / str(row["path"]) for row in source_files
    }
    predictions: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    isolation: list[dict[str, Any]] = []
    for identity in identities:
        for route in ROUTES:
            source_paths = {
                role: file_by_key[(identity.ordinal, role)]
                for role in SOURCE_ROLE_SCHEDULE[identity.ordinal]
                if route in ROUTES[2:]
            }
            raw, report = execute_route(
                image_reference=image_reference,
                route_id=route,
                category="tshirt",
                source_paths=source_paths,
                model_path=model_path if route == PRIMARY_ROUTE else None,
            )
            prediction = _prediction_record(identity, route, raw)
            predictions.append(prediction)
            attempts.append(
                {
                    "ordinal": identity.ordinal,
                    "opaqueId": identity.opaque_id,
                    "routeId": route,
                    "status": report["status"],
                    "predictionArtifact": prediction["predictionHash"] if raw is not None else None,
                    "failurePenaltyApplies": raw is None,
                }
            )
            isolation.append(
                {"ordinal": identity.ordinal, "opaqueId": identity.opaque_id, **report}
            )
    if len(attempts) != 64 or len({(row["ordinal"], row["routeId"]) for row in attempts}) != 64:
        raise ValueError("d0_v3_attempt_denominator_or_uniqueness_invalid")
    repeats: list[dict[str, Any]] = []
    for identity in identities:
        source_paths = {
            role: file_by_key[(identity.ordinal, role)]
            for role in SOURCE_ROLE_SCHEDULE[identity.ordinal]
        }
        raw, report = execute_route(
            image_reference=image_reference,
            route_id=PRIMARY_ROUTE,
            category="tshirt",
            source_paths=source_paths,
            model_path=model_path,
        )
        repeats.append(_prediction_record(identity, PRIMARY_ROUTE, raw))
        isolation.append(
            {"ordinal": identity.ordinal, "opaqueId": identity.opaque_id, "repeat": True, **report}
        )
    return predictions, attempts, isolation, repeats


def _prediction_record(
    identity: RealizedIdentity, route: str, raw: Mapping[str, Any] | None
) -> dict[str, Any]:
    if raw is None:
        parameters: dict[str, Any] = {}
        appearance: dict[str, Any] = {}
        abstained = True
    else:
        parameters = default_prior()
        parameters.update(_mapping(raw.get("parameters")))
        appearance = _mapping(raw.get("appearance"))
        if not appearance:
            appearance = {
                "baseColorSrgb": [92, 104, 119],
                "logoCenterNormalized": [0.5, 0.5],
                "logoColorSrgb": [238, 231, 214],
                "logoScaleNormalized": 0.1,
                "logoShape": "none",
                "neckShape": "crew",
                "roughness": 0.72,
                "metalness": 0.0,
                "ambientOcclusion": 0.9,
            }
        abstained = False
    evidence_class = {
        ROUTES[0]: "metadata_category_only",
        ROUTES[1]: "development_frozen_no_pixel_prior",
        ROUTES[2]: "decoded_source_masks_landmarks_and_pixels",
        ROUTES[3]: "fitted_model_from_decoded_source_pixels",
    }[route]
    record = {
        "schemaVersion": 1,
        "opaqueId": identity.opaque_id,
        "ordinal": identity.ordinal,
        "routeId": route,
        "abstained": abstained,
        "parameters": parameters,
        "appearance": appearance,
        "evidenceClass": evidence_class,
        "targetRead": False,
        "predictionHash": "",
    }
    record["predictionHash"] = _hash({**record, "predictionHash": ""})
    return record


def _audit_disjointness(
    *,
    identities: Sequence[RealizedIdentity],
    source_files: Sequence[Mapping[str, Any]],
    prior_inventory: Mapping[str, Any],
    typed_inventory: Mapping[str, Any],
) -> dict[str, Any]:
    prior_ids = {str(value) for value in prior_inventory.get("identityValues", [])}
    prior_parameters = {str(value) for value in prior_inventory.get("parameterHashes", [])}
    prior_pixels = {str(value) for value in prior_inventory.get("pixelHashes", [])}
    prior_geometry = {str(value) for value in prior_inventory.get("geometryHashes", [])}
    prior_targets = {str(value) for value in prior_inventory.get("targetFeatureHashes", [])}
    ids = [identity.opaque_id for identity in identities]
    parameter_hashes = [_hash(identity.parameters) for identity in identities]
    pixel_hashes = [str(row["sha256"]) for row in source_files]
    geometry_hashes = [
        geometry_content_hash(compile_structural_candidate(identity.parameters).rest_mesh)
        for identity in identities
    ]
    target_hashes = [_hash(identity.target_record()) for identity in identities]
    garment_hashes = [
        _hash(
            {
                "parameters": identity.parameters,
                "program": "canonical_tshirt_v1",
                "panels": compile_structural_candidate(identity.parameters).pattern["panels"],
                "seams": compile_structural_candidate(identity.parameters).pattern["seams"],
                "openings": compile_structural_candidate(identity.parameters).pattern["openings"],
                "restGeometry": geometry_hashes[index],
                "simulationGeometry": geometry_hashes[index],
                "appearanceLogo": identity.appearance,
                "pbrPreset": {
                    key: identity.appearance[key]
                    for key in ("roughness", "metalness", "ambientOcclusion")
                },
            }
        )
        for index, identity in enumerate(identities)
    ]
    capture_hashes = [
        _hash(
            {
                "camera": identity.capture,
                "crop": identity.capture["cropFraction"],
                "occlusion": identity.capture["occlusionFraction"],
                "lighting": identity.capture["lighting"],
                "raster": [
                    row["sha256"] for row in source_files if int(row["ordinal"]) == identity.ordinal
                ],
            }
        )
        for identity in identities
    ]
    prior_records = [_mapping(row) for row in _records(prior_inventory.get("parameterRecords"))]
    distances = [
        min(
            (normalized_distance(identity.parameters, prior) for prior in prior_records),
            default=1.0,
        )
        for identity in identities
    ]
    collisions = {
        "identityOpaqueIdByteDomain": sorted(set(ids) & prior_ids),
        "parameterCanonicalJsonDomain": sorted(set(parameter_hashes) & prior_parameters),
        "sourcePngByteDomain": sorted(set(pixel_hashes) & prior_pixels),
        "restMeshSemanticGeometryDomain": sorted(set(geometry_hashes) & prior_geometry),
        "targetRecordCanonicalJsonDomain": sorted(set(target_hashes) & prior_targets),
    }
    garment_pass = (
        len(set(garment_hashes)) == 16
        and all(distance >= 0.18 for distance in distances)
        and all(not rows for rows in collisions.values())
    )
    capture_pass = len(set(capture_hashes)) == 16
    return {
        "typedPriorInventoryDigest": typed_inventory.get("inventoryDigest"),
        "legacyComparableInventoryDigest": prior_inventory.get("inventoryDigest"),
        "domainsComparedOnlyLikeForLike": True,
        "unavailableComparisonsTreatedAsDisjoint": False,
        "collisions": collisions,
        "garmentIdentityPredicate": {
            "identityCount": 16,
            "uniqueIdentityCount": len(set(garment_hashes)),
            "minimumRecoverablePriorDistance": min(distances),
            "minimumDistanceThreshold": 0.18,
            "pass": garment_pass,
        },
        "captureInstancePredicate": {
            "identityCount": 16,
            "uniqueIdentityCount": len(set(capture_hashes)),
            "pass": capture_pass,
        },
        "disjointFromUnrecoverableV2OpaqueCohort": "unverified",
        "overallRecoverableInventoryPass": garment_pass and capture_pass,
    }


def _changed_path_audit(root: Path, lock_sha: str, protocol: Mapping[str, Any]) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", lock_sha, "--"],
        cwd=root.parent,
        capture_output=True,
        text=True,
        check=True,
    )
    paths = sorted(line for line in completed.stdout.splitlines() if line)
    return {
        "schemaVersion": 1,
        "lockSha": lock_sha,
        "changedPaths": paths,
        "allowedPatterns": protocol["changedPathAllowlistAfterSeed"],
        "scientificSurfaceHashIssues": validate_implementation(root, protocol),
        "pass": not paths and not validate_implementation(root, protocol),
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
        for path in sorted(output.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file() and path.name != "attempt_manifest.json"
    ]
    document = {
        "schemaVersion": 1,
        "manifestVersion": "closy.d0_disjoint_tshirt_confirmation.attempt_manifest.v3",
        "repository": "jake-the-jake/Closy",
        "branch": BRANCH,
        "baseBranch": "codex/closy-forge-evidence-authority-recovery-v2",
        "baseSha": UNIT_S_HEAD,
        "implementationLockSha": lock_sha,
        "mergeBaseSha": UNIT_S_HEAD,
        "workflowRunId": workflow_run_id,
        "workflowJobId": workflow_job_id,
        "protocolLockHash": protocol["lockHash"],
        "implementationDigest": protocol["implementationDigest"],
        "attemptState": result["attemptState"],
        "literalResult": result["outcome"],
        "qualificationRetryAllowed": False,
        "files": files,
        "manifestHash": "",
    }
    document["manifestHash"] = _hash({**document, "manifestHash": ""})
    return document


def _durable_json(path: Path, value: Any, *, freeze: bool = False) -> None:
    _durable_bytes(path, canonical_dumps(value).encode("utf-8"), freeze=freeze)


def _durable_bytes(path: Path, value: bytes, *, freeze: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(descriptor, value)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if freeze:
        path.chmod(0o444)


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: object) -> list[dict[str, Any]]:
    return [_mapping(row) for row in value] if isinstance(value, list | tuple) else []


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
