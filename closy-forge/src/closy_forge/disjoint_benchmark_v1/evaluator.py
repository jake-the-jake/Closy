from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

from .contender_cli import ROUTES
from .corpus import default_prior, realize_identities, verify_target_commitment
from .development import build_source_evidence, contestant_input
from .isolation import execute_isolated_contender
from .metrics import paired_bootstrap
from .protocol import FIXTURE_ROOT, validate_frozen_implementation

EVALUATOR_ROOT = FIXTURE_ROOT / "evaluator"


def derive_evaluator_seed(lock_sha: str, run_id: int, job_id: int) -> str:
    if len(lock_sha) != 40 or run_id <= 0 or job_id <= 0:
        raise ValueError("d0_disjoint_seed_authority_invalid")
    return hashlib.sha256(
        f"closy-d0-disjoint-v1:{lock_sha}:{run_id}:{job_id}".encode("ascii")
    ).hexdigest()


def realize_evaluator_commitments(
    root: Path,
    *,
    lock_sha: str,
    run_id: int,
    job_id: int,
    output: Path | None = None,
) -> dict[str, Any]:
    fixture = root / FIXTURE_ROOT
    lock = _load_json(fixture / "development_lock.json")
    validate_frozen_implementation(root, lock)
    seed = derive_evaluator_seed(lock_sha, run_id, job_id)
    references = [default_prior()]
    references.extend(
        _load_json(fixture / "development" / item["opaqueId"] / "target.json")["parameters"]
        for item in lock["developmentIdentities"]
    )
    identities, transcript = realize_identities(
        seed_hex=seed,
        count=16,
        role="evaluator",
        minimum_prior_distance=0.15,
        references=references,
        maximum_attempts=4096,
    )
    target = output or root / EVALUATOR_ROOT
    source_records: list[dict[str, Any]] = []
    for identity in identities:
        source = build_source_evidence(identity)
        identity_root = target / "sources" / identity.opaque_id
        png_records = []
        for role, payload in source["png"].items():
            path = identity_root / f"{role}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            png_records.append(
                {
                    "role": role,
                    "path": path.relative_to(target).as_posix(),
                    "sha256": sha256_file(path),
                }
            )
        source_evidence = {key: value for key, value in source.items() if key != "png"}
        write_canonical_json(identity_root / "source_evidence.json", source_evidence)
        source_records.append(
            {
                **identity.public_source_record(),
                "sourceFiles": png_records,
                "sourceEvidencePath": (identity_root / "source_evidence.json")
                .relative_to(target)
                .as_posix(),
                "sourceEvidenceHash": sha256_file(identity_root / "source_evidence.json"),
            }
        )
    authority = {
        "schemaVersion": 1,
        "authorityVersion": "closy.d0_disjoint.seed_authority.v1",
        "lockCommitSha": lock_sha,
        "firstNonRerunRunId": run_id,
        "firstNonRerunJobId": job_id,
        "rerunAttempt": 1,
        "derivedSeed": seed,
        "replacementHeadsAreAuthorities": False,
        "laterRerunsAreAuthorities": False,
    }
    commitments = {
        "schemaVersion": 1,
        "identityCount": 16,
        "identities": source_records,
        "targetsPresent": False,
        "noncesPresent": False,
        "targetParametersPresent": False,
        "allOpaque": all("garment_" in item["opaqueId"] for item in source_records),
    }
    write_canonical_json(target / "seed_authority.json", authority)
    write_canonical_json(target / "raw_draw_rejection_transcript.json", transcript)
    write_canonical_json(target / "commitments.json", commitments)
    return {"authority": authority, "commitments": commitments, "transcript": transcript}


def freeze_evaluator_predictions(root: Path, *, output: Path | None = None) -> dict[str, Any]:
    fixture = root / FIXTURE_ROOT
    target = output or root / EVALUATOR_ROOT
    lock = _load_json(fixture / "development_lock.json")
    commitments = _load_json(target / "commitments.json")
    validate_frozen_implementation(root, lock)
    executable = root / "src/closy_forge/disjoint_benchmark_v1/contender_cli.py"
    predictions: list[dict[str, Any]] = []
    isolation_records: list[dict[str, Any]] = []
    for identity in commitments["identities"]:
        source = _load_json(target / identity["sourceEvidencePath"])
        for route in ROUTES:
            prediction, isolation = execute_isolated_contender(
                executable=executable,
                route=route,
                input_payload=contestant_input(identity["opaqueId"], source, route),
                config=lock["contenderConfiguration"],
            )
            predictions.append(prediction)
            isolation_records.append({"opaqueId": identity["opaqueId"], **isolation})
    prediction_set: dict[str, Any] = {
        "schemaVersion": 1,
        "predictionVersion": "closy.d0_disjoint.predictions.v1",
        "identityCount": 16,
        "routeCount": len(ROUTES),
        "predictionCount": len(predictions),
        "predictions": predictions,
        "targetsMounted": False,
        "targetParametersRead": False,
        "thirdViewsMounted": False,
        "predictionSetHash": "",
    }
    prediction_set["predictionSetHash"] = _hash({**prediction_set, "predictionSetHash": ""})
    isolation_report = {
        "schemaVersion": 1,
        "recordCount": len(isolation_records),
        "records": isolation_records,
        "allPassed": all(
            item["allOpenedPathsAllowed"]
            and item["withdrawalExecutionFailedClosed"]
            and not item["targetParametersMounted"]
            and not item["repositoryRootMounted"]
            for item in isolation_records
        ),
    }
    freeze = {
        "schemaVersion": 1,
        "freezeVersion": "closy.d0_disjoint.prediction_freeze.v1",
        "predictionSetHash": prediction_set["predictionSetHash"],
        "commitmentsHash": sha256_file(target / "commitments.json"),
        "implementationHash": _hash(lock["implementationFiles"]),
        "targetContentsMounted": False,
        "predictionIdentityCount": len(predictions),
        "freezeHash": "",
    }
    freeze["freezeHash"] = _hash({**freeze, "freezeHash": ""})
    write_canonical_json(target / "predictions.json", prediction_set)
    write_canonical_json(target / "isolation_report.json", isolation_report)
    write_canonical_json(target / "prediction_freeze.json", freeze)
    return {"predictions": prediction_set, "isolation": isolation_report, "freeze": freeze}


def reveal_and_evaluate(root: Path, *, output: Path | None = None) -> dict[str, Any]:
    fixture = root / FIXTURE_ROOT
    target = output or root / EVALUATOR_ROOT
    lock = _load_json(fixture / "development_lock.json")
    authority = _load_json(target / "seed_authority.json")
    commitments = _load_json(target / "commitments.json")
    freeze = _load_json(target / "prediction_freeze.json")
    predictions = _load_json(target / "predictions.json")
    validate_frozen_implementation(root, lock)
    if freeze["predictionSetHash"] != predictions["predictionSetHash"]:
        raise ValueError("d0_disjoint_prediction_freeze_mismatch")
    seed = derive_evaluator_seed(
        authority["lockCommitSha"], authority["firstNonRerunRunId"], authority["firstNonRerunJobId"]
    )
    references = [default_prior()]
    references.extend(
        _load_json(fixture / "development" / item["opaqueId"] / "target.json")["parameters"]
        for item in lock["developmentIdentities"]
    )
    identities, transcript = realize_identities(
        seed_hex=seed,
        count=16,
        role="evaluator",
        minimum_prior_distance=0.15,
        references=references,
        maximum_attempts=4096,
    )
    if _hash(transcript) != _hash(_load_json(target / "raw_draw_rejection_transcript.json")):
        raise ValueError("d0_disjoint_draw_transcript_mismatch")
    target_records = [
        {**identity.target_record(), "ordinal": identity.ordinal, "stratum": identity.stratum}
        for identity in identities
    ]
    if not all(verify_target_commitment(record) for record in target_records):
        raise ValueError("d0_disjoint_target_commitment_invalid")
    expected_commitments = {
        item["opaqueId"]: item["targetCommitment"] for item in commitments["identities"]
    }
    if any(
        expected_commitments.get(record["opaqueId"]) != record["targetCommitment"]
        for record in target_records
    ):
        raise ValueError("d0_disjoint_commitment_reveal_mismatch")
    targets = {
        "schemaVersion": 1,
        "revealVersion": "closy.d0_disjoint.target_reveal.v1",
        "predictionFreezeHash": freeze["freezeHash"],
        "identities": target_records,
        "allCommitmentsValid": True,
    }
    write_canonical_json(target / "target_reveal.json", targets)
    routes = list(lock["fullCompileRouteIds"])
    appearance_ordinals = list(lock["appearanceEvaluatorOrdinals"])
    primary_report = _run_worker(root, target, routes, appearance_ordinals, "all_routes")
    repeat_report = _run_worker(
        root, target, [lock["primaryGateRoute"]], appearance_ordinals, "primary_repeat"
    )
    if primary_report["compileCount"] != 48 or repeat_report["compileCount"] != 16:
        raise ValueError("d0_disjoint_full_compile_budget_inventory_invalid")
    if (
        primary_report["appearanceEvaluationCount"] != 24
        or repeat_report["appearanceEvaluationCount"] != 8
    ):
        raise ValueError("d0_disjoint_appearance_budget_inventory_invalid")
    result = _aggregate(lock, primary_report, repeat_report)
    write_canonical_json(target / "evaluation_all_routes.json", primary_report)
    write_canonical_json(target / "evaluation_primary_repeat.json", repeat_report)
    write_canonical_json(target / "benchmark_result.json", result)
    return result


def _run_worker(
    root: Path,
    evaluator_root: Path,
    routes: list[str],
    appearance_ordinals: list[int],
    label: str,
) -> dict[str, Any]:
    with TemporaryDirectory(prefix=f"closy-g-evaluator-{label}-") as temporary:
        workspace = Path(temporary)
        output = workspace / "report.json"
        command = [
            sys.executable,
            "-m",
            "closy_forge.disjoint_benchmark_v1.evaluation_worker",
            "--predictions",
            str(evaluator_root / "predictions.json"),
            "--targets",
            str(evaluator_root / "target_reveal.json"),
            "--routes",
            ",".join(routes),
            "--appearance-ordinals",
            ",".join(str(value) for value in appearance_ordinals),
            "--output",
            str(output),
        ]
        environment = dict(os.environ)
        environment.update({"PYTHONDONTWRITEBYTECODE": "1", "NO_PROXY": "*"})
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError(f"d0_disjoint_evaluator_worker_failed:{label}:{completed.stderr}")
        return _load_json(output)


def _aggregate(
    lock: Mapping[str, Any], primary: Mapping[str, Any], repeat: Mapping[str, Any]
) -> dict[str, Any]:
    records = list(primary["records"])
    route_summaries: list[dict[str, Any]] = []
    for route in lock["fullCompileRouteIds"]:
        route_records = [item for item in records if item["routeId"] == route]
        parameter_errors = [
            float(item["parameterMetrics"]["macroNormalizedError"]) for item in route_records
        ]
        silhouettes = [float(item["rasterMetrics"]["silhouetteIoU"]) for item in route_records]
        route_summaries.append(
            {
                "routeId": route,
                "coverage": sum(item["status"] == "pass" for item in route_records),
                "denominator": 16,
                "medianMacroNormalizedError": round(median(parameter_errors), 9),
                "meanMacroNormalizedError": round(math.fsum(parameter_errors) / 16, 9),
                "worstNormalizedError": max(
                    float(item["parameterMetrics"]["worstNormalizedError"])
                    for item in route_records
                ),
                "meanSilhouetteIoU": round(math.fsum(silhouettes) / 16, 9),
                "allStructuralCompilesValid": all(
                    item["status"] == "pass" for item in route_records
                ),
            }
        )
    primary_id = str(lock["primaryGateRoute"])
    primary_records = [item for item in records if item["routeId"] == primary_id]
    baseline_id = min(
        (item for item in route_summaries if item["routeId"] == "no_pixel_template_prior"),
        key=lambda item: item["meanMacroNormalizedError"],
    )["routeId"]
    baseline_records = [item for item in records if item["routeId"] == baseline_id]
    parameter_bootstrap = paired_bootstrap(
        [float(item["parameterMetrics"]["macroNormalizedError"]) for item in primary_records],
        [float(item["parameterMetrics"]["macroNormalizedError"]) for item in baseline_records],
        lower_is_better=True,
        seed=int(lock["promotionThresholds"]["bootstrapSeed"]),
    )
    silhouette_bootstrap = paired_bootstrap(
        [float(item["rasterMetrics"]["silhouetteIoU"]) for item in primary_records],
        [float(item["rasterMetrics"]["silhouetteIoU"]) for item in baseline_records],
        lower_is_better=False,
        seed=int(lock["promotionThresholds"]["bootstrapSeed"]) + 1,
    )
    primary_summary = next(item for item in route_summaries if item["routeId"] == primary_id)
    baseline_summary = next(item for item in route_summaries if item["routeId"] == baseline_id)
    relative_improvement = (
        float(baseline_summary["meanMacroNormalizedError"])
        - float(primary_summary["meanMacroNormalizedError"])
    ) / max(1e-12, float(baseline_summary["meanMacroNormalizedError"]))
    silhouette_improvement = float(primary_summary["meanSilhouetteIoU"]) - float(
        baseline_summary["meanSilhouetteIoU"]
    )
    appearance_records = [item for item in primary_records if item["appearance"] is not None]
    repeat_by_key = {(item["opaqueId"], item["routeId"]): item for item in repeat["records"]}
    deterministic = all(
        _stable_record(item) == _stable_record(repeat_by_key[(item["opaqueId"], item["routeId"])])
        for item in primary_records
    )
    thresholds = lock["absoluteThresholds"]
    absolute_functional = (
        primary_summary["coverage"] >= thresholds["minimumPredictionCoverage"]
        and primary_summary["medianMacroNormalizedError"]
        <= thresholds["maximumMedianMacroNormalizedObservableError"]
        and primary_summary["worstNormalizedError"]
        <= thresholds["maximumWorstNormalizedObservableError"]
        and primary_summary["meanSilhouetteIoU"]
        >= thresholds["minimumMeanEvaluatorViewSilhouetteIoU"]
        and primary_summary["allStructuralCompilesValid"]
        and relative_improvement >= 0.10
        and silhouette_improvement >= 0.01
        and parameter_bootstrap["lower95"] > 0.0
        and silhouette_bootstrap["lower95"] > 0.0
    )
    appearance_pass = len(appearance_records) == 8 and all(
        item["appearance"]["status"] == "pass" for item in appearance_records
    )
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "resultVersion": "closy.d0_disjoint.benchmark_result.v1",
        "outcome": "cohort_pass" if absolute_functional else "cohort_functional_gate_failed",
        "primaryGateRoute": primary_id,
        "strongestNoPixelBaseline": baseline_id,
        "routeSummaries": route_summaries,
        "primaryRelativeParameterImprovement": round(relative_improvement, 9),
        "primaryAbsoluteSilhouetteImprovement": round(silhouette_improvement, 9),
        "parameterBootstrap": parameter_bootstrap,
        "silhouetteBootstrap": silhouette_bootstrap,
        "absoluteFunctionalAcceptance": absolute_functional,
        "appearanceCohortAcceptance": appearance_pass,
        "appearanceValidCount": len(appearance_records),
        "appearancePassCount": sum(
            item["appearance"]["status"] == "pass" for item in appearance_records
        ),
        "deterministicFreshProcessRepeat": deterministic,
        "fullCompileCount": int(primary["compileCount"]) + int(repeat["compileCount"]),
        "appearanceEvaluationCount": int(primary["appearanceEvaluationCount"])
        + int(repeat["appearanceEvaluationCount"]),
        "noTargetAccess": True,
        "failuresRetainedInDenominator": True,
        "physicsExecuted": False,
        "privateUserClaim": False,
        "realPhotoClaim": False,
        "productionClaim": False,
        "rowDecisions": {
            "D0-RP-03": "pass" if absolute_functional else "fail",
            "D0-RP-04": "pass" if absolute_functional else "partial",
            "D0-RP-06": "pass" if absolute_functional else "fail",
            "D0-RP-07": "pass" if appearance_pass else "fail",
        },
        "resultHash": "",
    }
    result["resultHash"] = _hash({**result, "resultHash": ""})
    return result


def _stable_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "opaqueId": record["opaqueId"],
        "routeId": record["routeId"],
        "status": record["status"],
        "parameterMetrics": record["parameterMetrics"],
        "rasterMetrics": record["rasterMetrics"],
        "reference3dMetrics": record["reference3dMetrics"],
        "compile": record["compile"],
        "appearance": record["appearance"],
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"d0_disjoint_json_mapping_required:{path}")
    return payload


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
