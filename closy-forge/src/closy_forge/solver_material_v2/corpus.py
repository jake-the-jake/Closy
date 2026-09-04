from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from closy_forge.capture_reconstruction_v2.safe_private_io import SafePrivateRoot

from .common import canonical_bytes, canonical_digest, read_json, write_json
from .protocol import FAMILIES, build_protocol, validate_protocol
from .specimens import default_specimen, run_garment_motion, run_specimen
from .units import FIELD_ORDER, denormalize_fields

CORPUS_VERSION = "closy.solver_material_source_guarded_corpus.v2"


def deterministic_fields(secret: str, tuple_id: str) -> dict[str, float]:
    fields: dict[str, float] = {}
    for index, field in enumerate(FIELD_ORDER):
        payload = hashlib.sha256(f"{secret}|{tuple_id}|{field}|{index}".encode()).digest()
        fraction = int.from_bytes(payload[:8], "big") / float((1 << 64) - 1)
        fields[field] = round(0.08 + 0.84 * fraction, 8)
    return fields


def generate_partition(
    protocol: dict[str, Any],
    *,
    partition: str,
    secret: str,
    public_root: Path,
    private_root: Path,
    source_commit: str,
    source_tree: str,
) -> dict[str, Any]:
    failures = validate_protocol(protocol)
    if failures:
        raise ValueError(";".join(failures))
    if partition not in {"development", "locked"}:
        raise ValueError("partition_invalid")
    tuples = [row for row in protocol["tuplePlan"] if row["partition"] == partition]
    public_rows: list[dict[str, Any]] = []
    commitments: list[dict[str, Any]] = []
    private_truth: list[dict[str, Any]] = []
    config = protocol["solverConfigurations"]["highResolutionTruth"]
    for row in tuples:
        tuple_id = str(row["tupleId"])
        fields = deterministic_fields(secret, tuple_id)
        material = denormalize_fields(fields)
        inference: list[dict[str, Any]] = []
        for index, specimen_id in enumerate(row["inferenceSpecimens"]):
            specimen = default_specimen(
                specimen_id,
                load_scale=0.82 + 0.06 * (index % 3),
                mesh=tuple(config["mesh"]),
                time_step_s=float(config["timeStepSeconds"]),
                step_count=int(config["stepCount"]),
                solver_iterations=int(config["solverIterations"]),
            )
            executed = run_specimen(
                specimen_id,
                material,
                specimen,
                tuple_id=tuple_id,
                observation_id=f"{tuple_id}-inference-{index:02d}",
                canonical_digits=int(config["canonicalPositionDigits"]),
            )
            inference.append(_public_observation(executed))
        withheld: list[dict[str, Any]] = []
        for index, specimen_id in enumerate(row["predictionSpecimens"]):
            load = float(row["withheldLoads"][index % 2])
            specimen = default_specimen(
                specimen_id,
                load_scale=load,
                mesh=tuple(config["mesh"]),
                time_step_s=float(config["timeStepSeconds"]),
                step_count=int(config["stepCount"]),
                solver_iterations=int(config["solverIterations"]),
                geometry=str(row["withheldGeometry"]),
            )
            withheld.append(
                run_specimen(
                    specimen_id,
                    material,
                    specimen,
                    tuple_id=tuple_id,
                    observation_id=f"{tuple_id}-withheld-{index:02d}",
                    canonical_digits=int(config["canonicalPositionDigits"]),
                )
            )
        motions = [
            run_garment_motion(
                family,
                motion_id,
                material,
                tuple_id=tuple_id,
                canonical_digits=int(config["canonicalPositionDigits"]),
            )
            for family in FAMILIES
            for motion_id in row["unseenMotions"][family]
        ]
        public = {
            "schemaVersion": 2,
            "corpusVersion": CORPUS_VERSION,
            "tupleId": tuple_id,
            "partition": partition,
            "materialFamily": row["materialFamily"],
            "garmentFamily": row["garmentFamily"],
            "regime": row["regime"],
            "sourceIdentity": row["sourceIdentity"],
            "solverVersion": protocol["canonicalSolverRoute"],
            "inferenceObservations": inference,
            "withheldStimuli": [
                {
                    "observationId": item["observationId"],
                    "specimenId": item["specimenId"],
                    "specimenSI": item["specimenSI"],
                }
                for item in withheld
            ],
            "unseenGarmentMotions": [
                {"family": item["family"], "motionId": item["motionId"]} for item in motions
            ],
            "frozenSourceCommit": source_commit,
            "frozenSourceTree": source_tree,
        }
        public["publicObservationDigest"] = canonical_digest(public)
        relative = f"observations/{tuple_id}.json"
        write_json(public_root / relative, public)
        public_rows.append(
            {
                "tupleId": tuple_id,
                "path": relative,
                "sha256": canonical_digest(public),
                "inferenceObservationCount": len(inference),
                "withheldPredictionCount": len(withheld),
                "garmentMotionCount": len(motions),
            }
        )
        truth = {
            "tupleId": tuple_id,
            "normalizedFields": fields,
            "withheldPredictions": withheld,
            "garmentMotions": motions,
        }
        truth_digest = canonical_digest(truth)
        commitments.append({"tupleId": tuple_id, "truthCommitment": truth_digest})
        private_truth.append(truth)
    manifest: dict[str, Any] = {
        "schemaVersion": 2,
        "corpusVersion": CORPUS_VERSION,
        "partition": partition,
        "protocolId": protocol["protocolId"],
        "protocolDigest": protocol["protocolDigest"],
        "frozenSourceCommit": source_commit,
        "frozenSourceTree": source_tree,
        "tupleCount": len(public_rows),
        "inferenceObservationCount": len(public_rows) * 6,
        "withheldLoadCount": len(public_rows) * 2,
        "withheldGeometryCount": len(public_rows),
        "withheldPredictionCount": len(public_rows) * 4,
        "garmentMotionCount": len(public_rows) * 24,
        "rows": public_rows,
    }
    manifest["manifestDigest"] = canonical_digest(manifest)
    commitment_document: dict[str, Any] = {
        "schemaVersion": 2,
        "partition": partition,
        "protocolDigest": protocol["protocolDigest"],
        "commitmentCount": len(commitments),
        "commitments": commitments,
    }
    commitment_document["commitmentDigest"] = canonical_digest(commitment_document)
    write_json(public_root / "manifest.json", manifest)
    write_json(public_root / "truth_commitments.json", commitment_document)
    private_root.mkdir(parents=True, exist_ok=True)
    with SafePrivateRoot(private_root) as private:
        private.write_atomic(
            "truth.json",
            canonical_bytes(
                {
                    "schemaVersion": 2,
                    "partition": partition,
                    "protocolDigest": protocol["protocolDigest"],
                    "rows": private_truth,
                }
            ),
        )
    return {"manifest": manifest, "commitments": commitment_document}


def load_public_partition(public_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = read_json(public_root / "manifest.json")
    rows = []
    for entry in manifest["rows"]:
        path = public_root / str(entry["path"])
        row = read_json(path)
        if canonical_digest(row, "publicObservationDigest") != row.get("publicObservationDigest"):
            raise ValueError("public_observation_digest_invalid")
        if canonical_digest(row) != entry.get("sha256"):
            raise ValueError("public_observation_manifest_digest_invalid")
        rows.append(row)
    if len(rows) != int(manifest["tupleCount"]):
        raise ValueError("public_tuple_denominator_invalid")
    return manifest, rows


def _public_observation(executed: dict[str, Any]) -> dict[str, Any]:
    return {
        "observationId": executed["observationId"],
        "specimenId": executed["specimenId"],
        "solverVersion": executed["solverVersion"],
        "unitSystem": "SI",
        "specimenSI": executed["specimenSI"],
        "observables": {
            key: value
            for key, value in executed["observables"].items()
            if key != "primary" and isinstance(value, int | float)
        },
        "meshTopologyHash": executed["mesh"]["topologyHash"],
        "executionDigest": executed["executionDigest"],
    }


def build_development_corpus(root: Path) -> dict[str, Any]:
    protocol = build_protocol()
    return generate_partition(
        protocol,
        partition="development",
        secret="development-identities-exposed-not-evaluation-eligible",
        public_root=root / "public",
        private_root=root / "private",
        source_commit="development_worktree",
        source_tree="development_worktree",
    )
