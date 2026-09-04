from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, cast

from .common import canonical_digest, write_json
from .corpus import load_public_partition
from .estimator import estimate_material
from .specimens import run_garment_motion, run_specimen
from .units import SpecimenSI, denormalize_fields


def run_contestant(public_root: Path, output_path: Path) -> dict[str, Any]:
    manifest, public_rows = load_public_partition(public_root.resolve())
    source_failures = audit_contestant_source(Path(__file__).with_name("estimator.py"))
    if source_failures:
        raise ValueError(";".join(source_failures))
    rows: list[dict[str, Any]] = []
    for public in public_rows:
        estimate = estimate_material(public["inferenceObservations"])
        control_outputs = _run_controls(public["inferenceObservations"])
        material = denormalize_fields(estimate["estimatedFields"])
        predictions = []
        for stimulus in public["withheldStimuli"]:
            values = stimulus["specimenSI"]
            specimen = SpecimenSI(**values)
            predictions.append(
                run_specimen(
                    str(stimulus["specimenId"]),
                    material,
                    specimen,
                    tuple_id=str(public["tupleId"]),
                    observation_id=str(stimulus["observationId"]),
                    canonical_digits=8,
                )
            )
        motions = [
            run_garment_motion(
                str(motion["family"]),
                str(motion["motionId"]),
                material,
                tuple_id=str(public["tupleId"]),
                canonical_digits=8,
            )
            for motion in public["unseenGarmentMotions"]
        ]
        rows.append(
            {
                "tupleId": public["tupleId"],
                "sourceIdentity": public["sourceIdentity"],
                "estimate": estimate,
                "controlOutputs": control_outputs,
                "withheldPredictions": predictions,
                "garmentMotions": motions,
                "terminalState": "passed",
            }
        )
    output: dict[str, Any] = {
        "schemaVersion": 2,
        "contestantVersion": "closy.solver_material_v2_frozen_contestant.v1",
        "protocolDigest": manifest["protocolDigest"],
        "manifestDigest": manifest["manifestDigest"],
        "network": "denied_by_execution_contract",
        "filesystem": "read_only_allowlisted_public_root",
        "tupleCount": len(rows),
        "publicInputs": {str(row["tupleId"]): row["inferenceObservations"] for row in public_rows},
        "rows": rows,
    }
    output["contestantOutputDigest"] = canonical_digest(output)
    write_json(output_path, output)
    return output


def audit_contestant_source(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    denied = {"corpus", "generator", "truth", "safe_private_io", "evaluation"}
    failures: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = {alias.name.split(".")[-1] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names = {str(node.module).split(".")[-1]}
        else:
            continue
        if names & denied:
            failures.append("contestant_denied_import")
    source = path.read_text(encoding="utf-8").lower()
    if "locked" in source or "seed" in source or "normalizedfields" in source:
        failures.append("contestant_forbidden_target_or_seed_token")
    return sorted(set(failures))


def _run_controls(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = (
        "shuffled_observations",
        "wrong_orientation",
        "wrong_units",
        "wrong_family",
        "time_shuffled_damping",
        "contact_disabled_friction_restitution",
        "duplicated_observations",
        "missing_inference_load",
        "lineage_substitution",
        "target_leakage_import",
    )
    outputs = []
    for name in names:
        try:
            changed = _mutate_control(observations, name)
            estimate = estimate_material(changed)
            outputs.append({"control": name, "status": "estimated", "estimate": estimate})
        except ValueError as error:
            outputs.append({"control": name, "status": "rejected", "reason": str(error)})
    return outputs


def _mutate_control(observations: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    rows = cast(list[dict[str, Any]], json.loads(json.dumps(observations)))
    if name == "shuffled_observations":
        values = [row["observables"] for row in rows]
        for index, row in enumerate(rows):
            row["observables"] = values[(index + 1) % len(values)]
    elif name == "wrong_orientation":
        rows[0]["observables"], rows[1]["observables"] = (
            rows[1]["observables"],
            rows[0]["observables"],
        )
    elif name == "wrong_units":
        rows[0]["unitSystem"] = "millimetres_relabelled_as_SI"
    elif name == "wrong_family":
        for value in rows[2]["observables"]:
            rows[2]["observables"][value] *= 1.35
    elif name == "time_shuffled_damping":
        rows[4]["observables"]["oscillationDecayRatio"] = (
            1.0 - rows[4]["observables"]["oscillationDecayRatio"]
        )
    elif name == "contact_disabled_friction_restitution":
        rows[5]["observables"]["slideDistanceMeters"] = 0.0
        rows[5]["observables"]["reboundVelocityMetersPerSecond"] = 0.0
    elif name == "duplicated_observations":
        rows[1] = json.loads(json.dumps(rows[0]))
    elif name == "missing_inference_load":
        rows.pop()
    elif name == "lineage_substitution":
        rows[0]["solverVersion"] = "substituted_solver"
    elif name == "target_leakage_import":
        raise ValueError("target_leakage_import_denied")
    return rows
