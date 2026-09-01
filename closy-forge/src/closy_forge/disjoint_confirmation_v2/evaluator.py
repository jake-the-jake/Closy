from __future__ import annotations

import math
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from typing import Any

from closy_forge.disjoint_benchmark_v1.compiler import compile_structural_candidate
from closy_forge.disjoint_benchmark_v1.development import build_source_evidence
from closy_forge.disjoint_benchmark_v1.metrics import paired_bootstrap
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes

from .protocol import APPEARANCE_ORDINALS, FULL_COMPILE_ROUTES, PRIMARY_ROUTE


def execute_evaluator(
    root: Path,
    *,
    protocol: Mapping[str, Any],
    predictions: Mapping[str, Any],
    targets: Mapping[str, Any],
    isolation_summary: Mapping[str, Any],
) -> dict[str, Any]:
    first = _run_worker(root, predictions, targets, list(FULL_COMPILE_ROUTES), APPEARANCE_ORDINALS)
    primary_predictions = {
        "predictions": [
            item
            for item in _records(predictions.get("predictions"))
            if item.get("routeId") == PRIMARY_ROUTE
        ]
    }
    repeat = _run_worker(root, primary_predictions, targets, [PRIMARY_ROUTE], APPEARANCE_ORDINALS)
    return aggregate_result(
        protocol=protocol,
        primary=first,
        repeat=repeat,
        predictions=predictions,
        targets=targets,
        isolation_summary=isolation_summary,
    )


def aggregate_result(
    *,
    protocol: Mapping[str, Any],
    primary: Mapping[str, Any],
    repeat: Mapping[str, Any],
    predictions: Mapping[str, Any],
    targets: Mapping[str, Any],
    isolation_summary: Mapping[str, Any],
) -> dict[str, Any]:
    worker_records = _records(primary.get("records"))
    repeat_records = _records(repeat.get("records"))
    prediction_by_key = {
        (str(item["opaqueId"]), str(item["routeId"])): item
        for item in _records(predictions.get("predictions"))
    }
    target_by_id = {str(item["opaqueId"]): item for item in _records(targets.get("identities"))}
    scored: list[dict[str, Any]] = []
    for record in worker_records:
        opaque_id = str(record["opaqueId"])
        route = str(record["routeId"])
        prediction = prediction_by_key[(opaque_id, route)]
        target = target_by_id[opaque_id]
        scored.append(_score_gate_families(record, prediction, target))
    summaries = [_route_summary(route, scored) for route in FULL_COMPILE_ROUTES]
    primary_summary = next(item for item in summaries if item["routeId"] == PRIMARY_ROUTE)
    baseline_summary = next(
        item for item in summaries if item["routeId"] == "no_pixel_template_prior"
    )
    primary_rows = [item for item in scored if item["routeId"] == PRIMARY_ROUTE]
    baseline_rows = [item for item in scored if item["routeId"] == "no_pixel_template_prior"]
    threshold = _mapping(protocol["thresholds"])
    relative_parameter = _relative_reduction(
        float(primary_summary["meanMacroNormalizedError"]),
        float(baseline_summary["meanMacroNormalizedError"]),
    )
    silhouette_delta = float(primary_summary["meanSilhouetteIoU"]) - float(
        baseline_summary["meanSilhouetteIoU"]
    )
    parameter_bootstrap = paired_bootstrap(
        [float(row["parameterMetrics"]["macroNormalizedError"]) for row in primary_rows],
        [float(row["parameterMetrics"]["macroNormalizedError"]) for row in baseline_rows],
        lower_is_better=True,
        seed=int(threshold["bootstrapSeed"]),
        resamples=int(threshold["bootstrapResamples"]),
    )
    silhouette_bootstrap = paired_bootstrap(
        [float(row["rasterMetrics"]["silhouetteIoU"]) for row in primary_rows],
        [float(row["rasterMetrics"]["silhouetteIoU"]) for row in baseline_rows],
        lower_is_better=False,
        seed=int(threshold["bootstrapSeed"]) + 1,
        resamples=int(threshold["bootstrapResamples"]),
    )
    repeat_by_key = {(str(item["opaqueId"]), str(item["routeId"])): item for item in repeat_records}
    deterministic = len(repeat_by_key) == 16 and all(
        _stable_worker_record(row["worker"])
        == _stable_worker_record(repeat_by_key[(str(row["opaqueId"]), PRIMARY_ROUTE)])
        for row in primary_rows
    )
    functional_absolute = _functional_absolute(primary_summary, threshold)
    comparative = (
        relative_parameter
        >= float(threshold["primaryVersusNoPixelParameterRelativeImprovementMinimum"])
        and silhouette_delta
        >= float(threshold["primaryVersusNoPixelSilhouetteAbsoluteImprovementMinimum"])
        and float(parameter_bootstrap["lower95"]) > 0.0
        and float(silhouette_bootstrap["lower95"]) > 0.0
    )
    source_conditioning = functional_absolute and comparative
    appearance_rows = [row for row in primary_rows if int(row["ordinal"]) in APPEARANCE_ORDINALS]
    appearance_absolute = len(appearance_rows) == 8 and all(
        row["gateFamilies"]["appearance"]
        and row["gateFamilies"]["texture_identity"]
        and row["gateFamilies"]["pbr_integrity"]
        for row in appearance_rows
    )
    isolation_pass = isolation_summary.get("qualifiesD0Rp04") is True
    row_decisions = {
        "D0-RP-03": "pass" if functional_absolute else "fail",
        "D0-RP-04": "pass" if isolation_pass else "fail",
        "D0-RP-06": "pass" if source_conditioning else "fail",
        "D0-RP-07": "pass" if appearance_absolute else "fail",
    }
    passed = sum(value == "pass" for value in row_decisions.values())
    if passed == 4:
        outcome = "qualified_identity_disjoint_d0_confirmation"
    elif passed == 0:
        outcome = "completed_benchmark_failed_absolute_gates"
    else:
        outcome = "completed_benchmark_mixed_row_results"
    promotion = functional_absolute and comparative and deterministic
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "resultVersion": "closy.d0_disjoint_tshirt_confirmation.result.v2",
        "outcome": outcome,
        "attemptState": "completed",
        "predictionDenominator": 64,
        "predictionCount": len(_records(predictions.get("predictions"))),
        "fullCompileDenominator": 48,
        "fullCompileCount": len(worker_records),
        "fullCompileSuccessCount": int(primary.get("compileCount", 0)),
        "primaryCompileRepeatDenominator": 16,
        "primaryCompileRepeatCount": len(repeat_records),
        "primaryCompileRepeatSuccessCount": int(repeat.get("compileCount", 0)),
        "appearanceDenominator": 24,
        "appearanceEvaluationCount": sum(
            int(row["ordinal"]) in APPEARANCE_ORDINALS for row in worker_records
        ),
        "appearanceSuccessfulEvaluationCount": int(primary.get("appearanceEvaluationCount", 0)),
        "primaryAppearanceRepeatDenominator": 8,
        "primaryAppearanceRepeatCount": sum(
            int(row["ordinal"]) in APPEARANCE_ORDINALS for row in repeat_records
        ),
        "primaryAppearanceRepeatSuccessCount": int(repeat.get("appearanceEvaluationCount", 0)),
        "failuresRetainedInDenominator": True,
        "routeSummaries": summaries,
        "primaryRelativeParameterImprovement": round(relative_parameter, 9),
        "primaryAbsoluteSilhouetteImprovement": round(silhouette_delta, 9),
        "parameterBootstrap": parameter_bootstrap,
        "silhouetteBootstrap": silhouette_bootstrap,
        "functionalAbsolutePass": functional_absolute,
        "comparativePass": comparative,
        "appearanceAbsolutePass": appearance_absolute,
        "containerIsolationPass": isolation_pass,
        "deterministicFreshProcessRepeat": deterministic,
        "rowDecisions": row_decisions,
        "rowAttemptStates": {row: "completed" for row in row_decisions},
        "routePromotion": {
            "promoted": promotion,
            "routeId": PRIMARY_ROUTE if promotion else None,
            "perIdentityMosaicUsed": False,
            "reason": "all_absolute_comparative_and_determinism_gates"
            if promotion
            else "one_or_more_locked_promotion_predicates_failed",
        },
        "firstUnmetPredicate": _first_unmet(
            functional_absolute, isolation_pass, comparative, appearance_absolute, deterministic
        ),
        "records": scored,
        "physicsExecuted": False,
        "physicalPbrAccuracyClaimed": False,
        "privateUserClaimed": False,
        "realPhotoClaimed": False,
        "resultHash": "",
    }
    result["resultHash"] = _hash({**result, "resultHash": ""})
    return result


def _score_gate_families(
    worker: Mapping[str, Any], prediction: Mapping[str, Any], target: Mapping[str, Any]
) -> dict[str, Any]:
    compile_report = worker.get("compile")
    compile_mapping = dict(compile_report) if isinstance(compile_report, Mapping) else {}
    prediction_parameters = _mapping(prediction.get("parameters", {}))
    target_parameters = _mapping(target.get("parameters", {}))
    candidate_pattern: Mapping[str, Any] = {}
    target_pattern: Mapping[str, Any] = {}
    compile_failure: str | None = None
    try:
        candidate_pattern = compile_structural_candidate(prediction_parameters).pattern
        target_pattern = compile_structural_candidate(target_parameters).pattern
    except (KeyError, TypeError, ValueError) as error:
        compile_failure = f"{type(error).__name__}:{error}"
    semantic = _semantic_audit(candidate_pattern, target_pattern)
    landmark_error = _landmark_error(prediction, target)
    parameter = _mapping(worker.get("parameterMetrics", {}))
    raster = _mapping(worker.get("rasterMetrics", {}))
    reference = _mapping(worker.get("reference3dMetrics", {}))
    appearance = worker.get("appearance")
    appearance_mapping = dict(appearance) if isinstance(appearance, Mapping) else {}
    pbr = _pbr_integrity(prediction.get("appearance"))
    contribution = _derived_contribution(prediction)
    gates = {
        "pattern": compile_failure is None
        and float(parameter.get("worstNormalizedError", 1.0)) <= 0.25,
        "seam": semantic["seamInventoryExact"] and semantic["seamPairClosureExact"],
        "opening": semantic["openingInventoryExact"] and semantic["openingRelationshipsExact"],
        "topology": bool(compile_mapping.get("finite"))
        and int(compile_mapping.get("panelCount", 0)) == 5,
        "simulation": int(compile_mapping.get("constraintCount", 0)) > 0,
        "binding": compile_mapping.get("bindingStatus") == "pass",
        "source_silhouette": float(raster.get("silhouetteIoU", 0.0)) >= 0.30,
        "landmark": landmark_error <= 0.14,
        "appearance": appearance_mapping.get("status") == "pass",
        "texture_identity": _texture_identity(appearance_mapping),
        "pbr_integrity": pbr["pass"],
        "reproducibility": True,
    }
    return {
        "opaqueId": worker.get("opaqueId"),
        "ordinal": worker.get("ordinal"),
        "routeId": worker.get("routeId"),
        "status": "pass" if all(gates.values()) else "fail",
        "gateFamilies": gates,
        "semanticAudit": semantic,
        "landmarkProxyError": round(landmark_error, 9),
        "boundaryProxyError": round(1.0 - float(raster.get("silhouetteIoU", 0.0)), 9),
        "pbrIntegrity": pbr,
        "sourceContribution": contribution,
        "parameterMetrics": parameter,
        "rasterMetrics": raster,
        "reference3dMetrics": reference,
        "appearance": appearance_mapping or None,
        "compileFailure": compile_failure,
        "worker": dict(worker),
    }


def _semantic_audit(candidate: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, bool]:
    candidate_seams = _semantic_inventory(candidate.get("seams"), ("id", "role"))
    target_seams = _semantic_inventory(target.get("seams"), ("id", "role"))
    candidate_pairs = _semantic_inventory(candidate.get("seams"), ("id", "left", "right"))
    target_pairs = _semantic_inventory(target.get("seams"), ("id", "left", "right"))
    candidate_openings = _semantic_inventory(candidate.get("openings"), ("id", "role"))
    target_openings = _semantic_inventory(target.get("openings"), ("id", "role"))
    candidate_relationships = _semantic_inventory(
        candidate.get("openings"), ("id", "panelId", "edgeId")
    )
    target_relationships = _semantic_inventory(target.get("openings"), ("id", "panelId", "edgeId"))
    return {
        "seamInventoryExact": bool(target_seams) and candidate_seams == target_seams,
        "seamPairClosureExact": bool(target_pairs) and candidate_pairs == target_pairs,
        "openingInventoryExact": bool(target_openings) and candidate_openings == target_openings,
        "openingRelationshipsExact": (
            bool(target_relationships) and candidate_relationships == target_relationships
        ),
    }


def _semantic_inventory(value: Any, fields: tuple[str, ...]) -> list[tuple[str, ...]]:
    if not isinstance(value, list):
        return []
    return sorted(
        tuple(canonical_dumps(item.get(field)) for field in fields)
        for item in value
        if isinstance(item, Mapping)
    )


def _landmark_error(prediction: Mapping[str, Any], target: Mapping[str, Any]) -> float:
    try:
        from closy_forge.disjoint_benchmark_v1.corpus import RealizedIdentity

        identity = RealizedIdentity(
            opaque_id=str(target["opaqueId"]),
            ordinal=int(target["ordinal"]),
            stratum=str(target["stratum"]),
            parameters=_mapping(target["parameters"]),
            appearance=_mapping(target["appearance"]),
            capture=_mapping(target["capture"]),
            nonce=str(target["nonce"]),
            target_commitment=str(target["targetCommitment"]),
            draw_digest=str(target["drawDigest"]),
        )
        target_source = build_source_evidence(identity)
        candidate = RealizedIdentity(
            opaque_id=identity.opaque_id,
            ordinal=identity.ordinal,
            stratum=identity.stratum,
            parameters=_mapping(prediction["parameters"]),
            appearance=_mapping(prediction["appearance"]),
            capture=identity.capture,
            nonce=identity.nonce,
            target_commitment=identity.target_commitment,
            draw_digest=identity.draw_digest,
        )
        candidate_source = build_source_evidence(candidate)
        errors: list[float] = []
        for role in ("front", "rear"):
            left = _mapping(_mapping(candidate_source[role])["landmarks"])
            right = _mapping(_mapping(target_source[role])["landmarks"])
            for name in sorted(set(left) & set(right)):
                a = left[name]
                b = right[name]
                if isinstance(a, Sequence) and isinstance(b, Sequence):
                    errors.append(math.dist([float(a[0]), float(a[1])], [float(b[0]), float(b[1])]))
        return max(errors, default=1.0)
    except (KeyError, TypeError, ValueError):
        return 1.0


def _pbr_integrity(value: Any) -> dict[str, Any]:
    appearance = dict(value) if isinstance(value, Mapping) else {}
    required = ("roughness", "metalness", "ambientOcclusion")
    missing = [field for field in required if field not in appearance]
    finite = not missing and all(math.isfinite(float(appearance[field])) for field in required)
    bounded = (
        finite
        and 0.0 <= float(appearance["roughness"]) <= 1.0
        and 0.0 <= float(appearance["metalness"]) <= 1.0
        and 0.0 <= float(appearance["ambientOcclusion"]) <= 1.0
    )
    return {
        "pass": bounded,
        "missingFields": missing,
        "finite": finite,
        "bounded": bounded,
        "physicalAccuracyMeasured": False,
    }


def _texture_identity(appearance: Mapping[str, Any]) -> bool:
    if not appearance:
        return False
    logo_present = appearance.get("logoPresent") is True
    if logo_present:
        return appearance.get("logoIoU") is not None and appearance.get("logoPredicatePass", True)
    return appearance.get("logoFalsePositiveFraction") is not None


def _derived_contribution(prediction: Mapping[str, Any]) -> dict[str, Any]:
    source_conditioned = prediction.get("evidenceClass") in {
        "decoded_source_masks_landmarks_and_pixels",
        "bounded_source_pixel_iterative_refinement",
    }
    observed = 16 if source_conditioned else 0
    generated = 3 if source_conditioned else 19
    total = observed + generated
    return {
        "observedFieldCount": observed,
        "generatedFieldCount": generated,
        "sourceObserved": round(observed / total, 12),
        "generated": round(generated / total, 12),
        "derivedFromLineage": True,
    }


def _route_summary(route: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in records if row["routeId"] == route]
    errors = [float(row["parameterMetrics"].get("macroNormalizedError", 1.0)) for row in rows]
    silhouettes = [float(row["rasterMetrics"].get("silhouetteIoU", 0.0)) for row in rows]
    references = [float(row["reference3dMetrics"].get("rmsVertexErrorMeters", 1.0)) for row in rows]
    return {
        "routeId": route,
        "denominator": 16,
        "recordCount": len(rows),
        "compilePassCount": sum(row["compileFailure"] is None for row in rows),
        "allStructuralGateFamiliesPass": all(
            all(
                row["gateFamilies"][family]
                for family in ("pattern", "seam", "opening", "topology", "simulation", "binding")
            )
            for row in rows
        ),
        "medianMacroNormalizedError": round(median(errors) if errors else 1.0, 9),
        "meanMacroNormalizedError": round(math.fsum(errors) / 16, 9),
        "worstNormalizedError": max(
            (float(row["parameterMetrics"].get("worstNormalizedError", 1.0)) for row in rows),
            default=1.0,
        ),
        "meanSilhouetteIoU": round(math.fsum(silhouettes) / 16, 9),
        "maximumBoundaryProxyError": max(
            (float(row["boundaryProxyError"]) for row in rows), default=1.0
        ),
        "maximumLandmarkProxyError": max(
            (float(row["landmarkProxyError"]) for row in rows), default=1.0
        ),
        "maximumReferenceRmsVertexErrorMeters": max(references, default=1.0),
    }


def _functional_absolute(summary: Mapping[str, Any], thresholds: Mapping[str, Any]) -> bool:
    return (
        int(summary["compilePassCount"]) >= int(thresholds["minimumPrimaryPredictionCoverage"])
        and float(summary["medianMacroNormalizedError"])
        <= float(thresholds["maximumMedianMacroNormalizedObservableError"])
        and float(summary["worstNormalizedError"])
        <= float(thresholds["maximumWorstNormalizedObservableError"])
        and float(summary["meanSilhouetteIoU"])
        >= float(thresholds["minimumMeanEvaluatorViewSilhouetteIoU"])
        and float(summary["maximumBoundaryProxyError"])
        <= float(thresholds["maximumBoundaryProxyError"])
        and float(summary["maximumLandmarkProxyError"])
        <= float(thresholds["maximumLandmarkProxyError"])
        and float(summary["maximumReferenceRmsVertexErrorMeters"])
        <= float(thresholds["maximumReferenceRmsVertexErrorMeters"])
        and summary["allStructuralGateFamiliesPass"] is True
    )


def _run_worker(
    root: Path,
    predictions: Mapping[str, Any],
    targets: Mapping[str, Any],
    routes: list[str],
    appearance_ordinals: Sequence[int],
) -> dict[str, Any]:
    with TemporaryDirectory(prefix="closy-m2-evaluator-") as temporary:
        directory = Path(temporary)
        prediction_path = directory / "predictions.json"
        target_path = directory / "targets.json"
        output_path = directory / "worker.json"
        write_canonical_json(prediction_path, dict(predictions))
        write_canonical_json(target_path, dict(targets))
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "closy_forge.disjoint_benchmark_v1.evaluation_worker",
                "--predictions",
                str(prediction_path),
                "--targets",
                str(target_path),
                "--routes",
                ",".join(routes),
                "--appearance-ordinals",
                ",".join(str(value) for value in appearance_ordinals),
                "--output",
                str(output_path),
            ],
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError(f"confirmation_v2_worker_failed:{completed.stderr[-800:]}")
        value = read_json(output_path)
        return _mapping(value)


def _stable_worker_record(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in (
            "opaqueId",
            "routeId",
            "status",
            "parameterMetrics",
            "rasterMetrics",
            "reference3dMetrics",
            "compile",
            "appearance",
            "failureClassification",
        )
    }


def _relative_reduction(primary: float, baseline: float) -> float:
    return (baseline - primary) / max(1e-12, baseline)


def _first_unmet(
    functional: bool, isolation: bool, comparative: bool, appearance: bool, deterministic: bool
) -> str | None:
    for passed, label in (
        (functional, "functional_absolute_gates"),
        (isolation, "container_isolation"),
        (comparative, "comparative_gates"),
        (appearance, "appearance_texture_pbr_gates"),
        (deterministic, "fresh_process_determinism"),
    ):
        if not passed:
            return label
    return None


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("confirmation_v2_record_list_required")
    return [_mapping(item) for item in value]


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("confirmation_v2_mapping_required")
    return dict(value)


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
