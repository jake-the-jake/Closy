from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes

from .grammar_v2 import compile_program, default_parameters, program_from_parameters
from .model_v2 import decode_prediction
from .raster_evaluation_v4 import predict_unassisted
from .raster_execution_v3 import _BUILD_SPECS
from .reference_3d_v1 import build_reference_geometry, compare_reference_geometry

EXECUTION_VERSION_V4 = "closy.raster_pattern_downstream_execution.synthetic_d0.v2"


def execute_raster_downstream_v4(
    bundle: dict[str, Any], thresholds: dict[str, Any]
) -> dict[str, Any]:
    """Execute one hidden representative per family without oracle repair."""

    records = []
    test_ids = set(bundle["split"]["samples"]["test"])
    with tempfile.TemporaryDirectory(prefix="closy-raster-v4-downstream-") as temporary:
        root = Path(temporary)
        for family_index, target_family in enumerate(bundle["model"]["families"]):
            sample = next(
                item
                for item in bundle["dataset"]["samples"]
                if item["sampleId"] in test_ids and item["target"]["garmentFamily"] == target_family
            )
            records.append(_execute_sample(bundle, sample, family_index, root))
    accepted = [record for record in records if record["candidateStatus"] == "accepted"]
    learned_successes = [record for record in records if record["learnedSuccess"]]
    execution_rate = (
        sum(record["threeDimensionalExecution"]["status"] == "passed" for record in accepted)
        / len(accepted)
        if accepted
        else 0.0
    )
    gate = thresholds["e1"]
    checks = dict(bundle["evaluationV4"]["acceptance"]["checks"])
    checks["acceptedThreeDimensionalExecution"] = execution_rate >= float(
        gate["minimumAcceptedThreeDimensionalExecutionRate"]
    )
    return {
        "schemaVersion": 1,
        "executionVersion": EXECUTION_VERSION_V4,
        "scope": "eight_family_hidden_representatives_project_authored_synthetic_host_cpu",
        "records": records,
        "unassisted": {
            "representativeCount": len(records),
            "acceptedCount": len(accepted),
            "learnedSuccessCount": len(learned_successes),
            "acceptedThreeDimensionalExecutionRate": round(execution_rate, 9),
            "fallbackSuccessCountedInLearnedMetrics": False,
        },
        "E1": {
            "status": "pass" if all(checks.values()) else "partial",
            "checks": checks,
            "failedChecks": sorted(name for name, passed in checks.items() if not passed),
        },
        "claims": {
            "physicalSettleAcceptance": False,
            "realPhotoGeneralisation": False,
            "privateUserGeneralisation": False,
            "globalPhase9Complete": False,
        },
    }


def build_unassisted_candidate(
    model: dict[str, Any], observation: dict[str, Any], *, candidate_id: str, seed: int
) -> dict[str, Any]:
    """Construct a proposal from observable input only; no target arguments exist."""

    prediction = predict_unassisted(model, observation)
    if prediction["status"] != "predicted":
        return {"status": "deferred", "prediction": prediction}
    try:
        program, pattern = decode_prediction(prediction, program_id=candidate_id, base_seed=seed)
    except ValueError as error:
        return {
            "status": "rejected",
            "prediction": prediction,
            "reason": "constrained_decode_rejected",
            "exceptionType": type(error).__name__,
        }
    return {
        "status": "accepted",
        "prediction": prediction,
        "program": program,
        "pattern": pattern,
    }


def _execute_sample(
    bundle: dict[str, Any], sample: dict[str, Any], index: int, root: Path
) -> dict[str, Any]:
    candidate = build_unassisted_candidate(
        bundle["model"],
        sample["input"],
        candidate_id=f"learned.e1.v4.{index:02d}",
        seed=81_000 + index,
    )
    target_family = str(sample["target"]["garmentFamily"])
    target_program = next(
        item
        for item in bundle["dataset"]["programs"]
        if item["programId"] == sample["sourceProgramId"]
    )
    target_pattern = compile_program(target_program)
    target_geometry = build_reference_geometry(target_family, target_pattern)
    fallback = program_from_parameters(
        target_family,
        default_parameters(target_family),
        program_id=f"fallback.availability.{target_family}",
        base_seed=82_000 + index,
    )
    record: dict[str, Any] = {
        "heldOutSampleId": sample["sampleId"],
        "targetFamily": target_family,
        "candidateStatus": candidate["status"],
        "prediction": candidate["prediction"],
        "fallback": {
            "available": bool(compile_program(fallback)),
            "usedForLearnedMetrics": False,
            "programHash": _hash(fallback),
        },
        "targetUsedDuringCandidateConstruction": False,
        "learnedSuccess": False,
        "threeDimensionalExecution": {"status": "not_run_candidate_not_accepted"},
    }
    if candidate["status"] != "accepted":
        return record
    predicted_family = str(candidate["prediction"]["family"])
    candidate_geometry = build_reference_geometry(predicted_family, candidate["pattern"])
    package_root = root / f"candidate-{index:02d}.closygarment"
    spec = _BUILD_SPECS[predicted_family]
    wall_start = time.perf_counter_ns()
    try:
        result = spec.builder(
            package_root,
            params=spec.parameter_type(**candidate["program"]["parameters"]),
            seed=83_000 + index,
        )
        package_status = result.validation["status"]
        settled = read_json(package_root / "simulation" / "settled_state.json")
        settled_hash = settled["meshContentHash"]
        rejection = None
    except (RuntimeError, ValueError) as error:
        package_status = "rejected"
        settled_hash = None
        rejection = {"reason": "candidate_package_build_rejected", "type": type(error).__name__}
    comparison = compare_reference_geometry(candidate_geometry, target_geometry)
    correct = predicted_family == target_family
    learned_success = bool(correct and package_status == "passed")
    record.update(
        {
            "predictedFamily": predicted_family,
            "candidateProgramHash": _hash(candidate["program"]),
            "candidatePatternHash": _hash(candidate["pattern"]),
            "learnedSuccess": learned_success,
            "package": {
                "validation": package_status,
                "settledStateHash": settled_hash,
                "rejection": rejection,
            },
            "threeDimensionalExecution": {
                "status": "passed" if package_status == "passed" else "rejected",
                "referenceGeometry": candidate_geometry["audit"],
                "hiddenTargetComparison": comparison,
                "physicalSettleClaimed": False,
            },
            "runtime": {
                "wallMilliseconds": round((time.perf_counter_ns() - wall_start) / 1_000_000, 6)
            },
        }
    )
    return record


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
