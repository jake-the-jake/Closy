from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image

from closy_forge.disjoint_benchmark_v1.compiler import compile_structural_candidate
from closy_forge.disjoint_benchmark_v1.metrics import paired_bootstrap
from closy_forge.disjoint_benchmark_v1.protocol import (
    OBSERVABLE_PARAMETERS,
    PARAMETER_RANGES,
)
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .appearance import recover_source_to_uv, rerender_from_persisted_atlas
from .container_entry import CONTAINER_ENTRY_VERSION, execute_route
from .corpus import load_partition, render_tshirt_capture
from .model import load_model, metadata_only_baseline
from .protocol import LIFECYCLE_STATES, load_engineering_protocol

EVALUATOR_VERSION = "closy.d0_v4.independent_engineering_evaluator.v1"


def evaluate_partition(
    root: Path,
    *,
    partition: str,
    model_path: Path,
    allow_public_test: bool = False,
    workers: int = 1,
) -> dict[str, Any]:
    protocol = load_engineering_protocol(root)
    model = load_model(model_path)
    records = load_partition(root, partition, allow_public_test=allow_public_test)
    tasks = [(model, record) for record in records]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            evaluated = list(executor.map(_evaluate_record_task, tasks, chunksize=1))
        with ProcessPoolExecutor(max_workers=workers) as executor:
            repeats = list(executor.map(_prediction_digest_task, tasks, chunksize=1))
    else:
        evaluated = [_evaluate_record_task(task) for task in tasks]
        repeats = [_prediction_digest_task(task) for task in tasks]
    original_digests = [str(row["predictionDigest"]) for row in evaluated]
    deterministic = original_digests == repeats
    result = _aggregate(
        protocol,
        partition=partition,
        records=evaluated,
        deterministic=deterministic,
        model=model,
    )
    return result


def validate_evaluation(result: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    records = _records(result.get("records"))
    if result.get("evaluatorVersion") != EVALUATOR_VERSION:
        issues.append("evaluator_version_invalid")
    if result.get("containerEntryVersion") != CONTAINER_ENTRY_VERSION:
        issues.append("container_entry_version_invalid")
    if len(records) != 128:
        issues.append("evaluation_denominator_invalid")
    for record in records:
        lifecycle = _mapping(record.get("lifecycle"))
        # Canonical JSON sorts object keys, so validate the frozen lifecycle axis
        # by exact membership rather than relying on mapping insertion order.
        if set(lifecycle) != set(LIFECYCLE_STATES):
            issues.append("lifecycle_axis_invalid")
        if lifecycle.get("compile_valid") is True and lifecycle.get("compiler_entered") is not True:
            issues.append("compile_without_compiler_entry")
        if record.get("predictionDigest") is None:
            issues.append("prediction_lineage_missing")
    if result.get("failuresRetainedInDenominator") is not True:
        issues.append("failure_denominator_not_retained")
    if result.get("resultDigest") != _digest(result, "resultDigest"):
        issues.append("evaluation_digest_invalid")
    return sorted(set(issues))


def _evaluate_record_task(task: tuple[dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    model, record = task
    prediction = _primary_route_prediction(model, record)
    baseline = metadata_only_baseline()
    lifecycle = {state: False for state in LIFECYCLE_STATES}
    lifecycle["scheduled"] = True
    lifecycle["container_returned"] = True
    if prediction.get("status") != "predicted":
        lifecycle["abstained"] = True
        return _failed_record(record, prediction, baseline, lifecycle)
    lifecycle["candidate_complete"] = _candidate_complete(prediction)
    if not lifecycle["candidate_complete"]:
        lifecycle["abstained"] = True
        return _failed_record(record, prediction, baseline, lifecycle)
    lifecycle["compiler_entered"] = True
    parameters = _mapping(prediction["parameters"])
    try:
        candidate_compile = compile_structural_candidate(parameters)
        target_compile = compile_structural_candidate(_mapping(record["parameters"]))
    except (KeyError, TypeError, ValueError) as exc:
        prediction = {**prediction, "compileFailure": f"{type(exc).__name__}:{exc}"}
        return _failed_record(record, prediction, baseline, lifecycle)
    compile_report = candidate_compile.report
    lifecycle["compile_valid"] = (
        compile_report.get("finite") is True
        and compile_report.get("bindingStatus") == "pass"
        and compile_report.get("seamStatus") == "pass"
    )
    if not lifecycle["compile_valid"]:
        return _failed_record(record, prediction, baseline, lifecycle)
    observed_parameters = [
        name
        for name in OBSERVABLE_PARAMETERS
        if not (record.get("rearPng") is None and name == "back_neckline_depth")
    ]
    parameter_metrics = _parameter_metrics(
        parameters, _mapping(record["parameters"]), observed_parameters
    )
    baseline_metrics = _parameter_metrics(
        baseline, _mapping(record["parameters"]), observed_parameters
    )
    candidate_rasters = _candidate_rasters(record, parameters)
    baseline_rasters = _candidate_rasters(record, baseline)
    target_rasters = _target_rasters(record)
    raster_metrics = _raster_metrics(candidate_rasters, target_rasters)
    baseline_raster_metrics = _raster_metrics(baseline_rasters, target_rasters)
    appearance = recover_source_to_uv(record["frontPng"], record.get("rearPng"))
    appearance_metrics = _appearance_metrics(
        appearance,
        candidate_rasters,
        target_rasters,
        _mapping(record["appearance"]),
        _background(record),
    )
    lifecycle["appearance_evaluated"] = True
    lifecycle["appearance_pass"] = appearance_metrics["pass"]
    reference = _reference_surface_metrics(candidate_compile.rest_mesh, target_compile.rest_mesh)
    semantic = _semantic_audit(candidate_compile.pattern, target_compile.pattern)
    prediction_digest = _prediction_digest(prediction, appearance.manifest)
    row_gates = {
        "finiteAndSafe": parameter_metrics["finiteAndSafe"],
        "canonicalCompile": lifecycle["compile_valid"],
        "panelCount": compile_report.get("panelCount") == 5,
        "seamSemantics": semantic["seamsExact"],
        "openingSemantics": semantic["openingsExact"],
        "appearance": appearance_metrics["pass"],
    }
    lifecycle["all_gate_pass"] = all(row_gates.values())
    return {
        "identityHash": record["identityHash"],
        "ordinal": record["ordinal"],
        "partition": record["partition"],
        "status": "pass" if lifecycle["all_gate_pass"] else "fail",
        "lifecycle": lifecycle,
        "rowGates": row_gates,
        "prediction": _compact_prediction(prediction),
        "predictionDigest": prediction_digest,
        "parameterMetrics": parameter_metrics,
        "baselineParameterMetrics": baseline_metrics,
        "rasterMetrics": raster_metrics,
        "baselineRasterMetrics": baseline_raster_metrics,
        "appearanceMetrics": appearance_metrics,
        "reference3dMetrics": reference,
        "semanticAudit": semantic,
        "compileReport": compile_report,
        "appearanceAtlasManifest": appearance.manifest,
    }


def _prediction_digest_task(task: tuple[dict[str, Any], dict[str, Any]]) -> str:
    model, record = task
    prediction = _primary_route_prediction(model, record)
    if prediction.get("status") != "predicted":
        return _digest(prediction, None)
    appearance = recover_source_to_uv(record["frontPng"], record.get("rearPng"))
    return _prediction_digest(prediction, appearance.manifest)


def _aggregate(
    protocol: Mapping[str, Any],
    *,
    partition: str,
    records: Sequence[Mapping[str, Any]],
    deterministic: bool,
    model: Mapping[str, Any],
) -> dict[str, Any]:
    thresholds = _mapping(protocol["readinessThresholds"])
    macros = [float(_mapping(row.get("parameterMetrics")).get("macro", 1.0)) for row in records]
    worst = [float(_mapping(row.get("parameterMetrics")).get("worst", 1.0)) for row in records]
    silhouettes = [
        float(_mapping(row.get("rasterMetrics")).get("silhouetteIoU", 0.0)) for row in records
    ]
    landmark_errors = [
        float(_mapping(row.get("rasterMetrics")).get("landmarkProxyError", 1.0)) for row in records
    ]
    baseline_macros = [
        float(_mapping(row.get("baselineParameterMetrics")).get("macro", 1.0)) for row in records
    ]
    baseline_silhouettes = [
        float(_mapping(row.get("baselineRasterMetrics")).get("silhouetteIoU", 0.0))
        for row in records
    ]
    compile_count = sum(
        _mapping(row.get("lifecycle")).get("compile_valid") is True for row in records
    )
    appearance_rows = [
        _mapping(row.get("appearanceMetrics"))
        for row in records
        if _mapping(row.get("lifecycle")).get("appearance_evaluated") is True
    ]
    relative_parameter = (_mean(baseline_macros) - _mean(macros)) / max(
        _mean(baseline_macros), 1e-12
    )
    silhouette_improvement = _mean(silhouettes) - _mean(baseline_silhouettes)
    parameter_bootstrap = paired_bootstrap(
        macros,
        baseline_macros,
        lower_is_better=True,
        seed=94001,
        resamples=int(thresholds["bootstrapResamples"]),
    )
    silhouette_bootstrap = paired_bootstrap(
        silhouettes,
        baseline_silhouettes,
        lower_is_better=False,
        seed=94002,
        resamples=int(thresholds["bootstrapResamples"]),
    )
    summary: dict[str, Any] = {
        "denominator": 128,
        "predictionCount": len(records),
        "finitePredictionRate": sum(
            _mapping(row.get("parameterMetrics")).get("finiteAndSafe") is True for row in records
        )
        / 128.0,
        "safeDomainRate": sum(
            _mapping(row.get("parameterMetrics")).get("finiteAndSafe") is True for row in records
        )
        / 128.0,
        "canonicalCompileSuccess": compile_count,
        "coverageRate": compile_count / 128.0,
        "medianMacroNormalizedObservableError": median(macros),
        "meanMacroNormalizedObservableError": _mean(macros),
        "worstNormalizedObservableError": max(worst),
        "meanEvaluatorViewSilhouetteIoU": _mean(silhouettes),
        "maximumBoundaryProxyError": max(1.0 - value for value in silhouettes),
        "maximumLandmarkProxyError": max(landmark_errors),
        "maximumReferenceRmsVertexErrorMeters": max(
            float(_mapping(row.get("reference3dMetrics")).get("rmsVertexErrorMeters", 1.0))
            for row in records
        ),
        "maximumForegroundSrgbMae": max(
            float(row.get("foregroundSrgbMae", 1.0)) for row in appearance_rows
        ),
        "minimumLogoIoUWhenApplicable": min(
            (float(row["logoIoU"]) for row in appearance_rows if row.get("logoIoU") is not None),
            default=1.0,
        ),
        "maximumLogoDisplacementNormalized": max(
            (
                float(row["logoDisplacementNormalized"])
                for row in appearance_rows
                if row.get("logoDisplacementNormalized") is not None
            ),
            default=0.0,
        ),
        "maximumLogoFalsePositiveFraction": max(
            (
                float(row["logoFalsePositiveFraction"])
                for row in appearance_rows
                if row.get("logoFalsePositiveFraction") is not None
            ),
            default=0.0,
        ),
        "relativeParameterImprovement": relative_parameter,
        "silhouetteIoUImprovement": silhouette_improvement,
        "parameterBootstrap": parameter_bootstrap,
        "silhouetteBootstrap": silhouette_bootstrap,
        "freshProcessDeterministic": deterministic,
    }
    gates = {
        "finitePredictions": summary["finitePredictionRate"] == 1.0,
        "safeDomains": summary["safeDomainRate"] == 1.0,
        "compileSuccess": compile_count >= int(thresholds["minimumPrimaryCanonicalCompileSuccess"]),
        "seamOpeningSemantics": all(
            _mapping(row.get("semanticAudit")).get("seamsExact") is True
            and _mapping(row.get("semanticAudit")).get("openingsExact") is True
            for row in records
            if _mapping(row.get("lifecycle")).get("compile_valid") is True
        ),
        "medianParameter": float(summary["medianMacroNormalizedObservableError"])
        <= float(thresholds["maximumMedianMacroNormalizedObservableError"]),
        "worstParameter": float(summary["worstNormalizedObservableError"])
        <= float(thresholds["maximumWorstNormalizedObservableError"]),
        "silhouette": float(summary["meanEvaluatorViewSilhouetteIoU"])
        >= float(thresholds["minimumMeanEvaluatorViewSilhouetteIoU"]),
        "boundary": float(summary["maximumBoundaryProxyError"])
        <= float(thresholds["maximumBoundaryProxyError"]),
        "landmark": float(summary["maximumLandmarkProxyError"])
        <= float(thresholds["maximumLandmarkProxyError"]),
        "reference3d": float(summary["maximumReferenceRmsVertexErrorMeters"])
        <= float(thresholds["maximumReferenceRmsVertexErrorMeters"]),
        "appearanceColour": float(summary["maximumForegroundSrgbMae"])
        <= float(thresholds["maximumForegroundSrgbMae"]),
        "appearanceLogo": float(summary["minimumLogoIoUWhenApplicable"])
        >= float(thresholds["minimumLogoIoUWhenApplicable"])
        and float(summary["maximumLogoDisplacementNormalized"])
        <= float(thresholds["maximumLogoDisplacementNormalized"])
        and float(summary["maximumLogoFalsePositiveFraction"])
        <= float(thresholds["maximumLogoFalsePositiveFraction"]),
        "coverage": float(summary["coverageRate"])
        >= float(thresholds["minimumEvaluationCoverageRate"]),
        "relativeParameter": relative_parameter
        >= float(thresholds["minimumRelativeParameterImprovement"]),
        "silhouetteImprovement": silhouette_improvement
        >= float(thresholds["minimumSilhouetteIoUImprovement"]),
        "learnedWinner": relative_parameter
        >= float(thresholds["learnedWinnerParameterRelativeImprovementMinimum"])
        and silhouette_improvement
        >= float(thresholds["learnedWinnerSilhouetteAbsoluteImprovementMinimum"]),
        "bootstrap": float(parameter_bootstrap["lower95"]) > 0.0
        and float(silhouette_bootstrap["lower95"]) > 0.0,
        "deterministicFreshProcess": deterministic,
    }
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "evaluatorVersion": EVALUATOR_VERSION,
        "containerEntryVersion": CONTAINER_ENTRY_VERSION,
        "primaryRoute": "learned_refined_structured",
        "partition": partition,
        "modelSha256": _mapping(model["integrity"])["modelSha256"],
        "records": list(records),
        "summary": summary,
        "gates": gates,
        "readinessPass": all(gates.values()),
        "failuresRetainedInDenominator": True,
        "publicTestGuidedDevelopment": False,
        "qualificationCohortCreated": False,
        "physicalMaterialAccuracyClaimed": False,
        "resultDigest": "",
    }
    result["resultDigest"] = _digest(result, "resultDigest")
    return result


def _candidate_rasters(
    record: Mapping[str, Any], parameters: Mapping[str, Any]
) -> dict[str, bytes]:
    capture = _mapping(record["capture"])
    background = _background(record)
    rasters = {}
    for role in ("front", "rear"):
        if role == "rear" and record.get("rearPng") is None:
            continue
        raw = render_tshirt_capture(
            parameters,
            {
                "baseColorSrgb": [42, 96, 155],
                "logoShape": "none",
                "logoColorSrgb": [238, 231, 214],
                "logoCenterNormalized": [0.5, 0.5],
                "logoScaleNormalized": 0.1,
            },
            background=background,
            variation={**capture, "occlusionFraction": 0.0},
            role=role,
            renderer_family=str(record["rendererFamily"]),
        )
        from .observation import apply_crop_and_padding

        transformed, _ = apply_crop_and_padding(
            raw,
            crop_fraction=float(capture["cropFraction"]),
            padding_fraction=float(capture["paddingFraction"]),
            background_rgb=background,
        )
        rasters[role] = _resize_official(transformed)
    return rasters


def _primary_route_prediction(
    model: Mapping[str, Any], record: Mapping[str, Any]
) -> dict[str, Any]:
    front = record.get("frontPng")
    rear = record.get("rearPng")
    if not isinstance(front, bytes) or (rear is not None and not isinstance(rear, bytes)):
        return {
            "status": "rejected",
            "reason": "capture_bytes_missing",
            "parameters": None,
            "targetParametersRead": False,
        }
    capture = _mapping(record.get("capture"))
    metadata = {
        "front": {
            "camera": _mapping(capture.get("frontCamera")),
            "observationToOriginalTransform": capture.get("frontTransform"),
        },
        "rear": {
            "camera": _mapping(capture.get("rearCamera")),
            "observationToOriginalTransform": capture.get("rearTransform"),
        },
    }
    return execute_route(
        "learned_refined_structured",
        model=model,
        front_png=front,
        rear_png=rear,
        metadata=metadata,
    )


def _target_rasters(record: Mapping[str, Any]) -> dict[str, bytes]:
    return {
        role: _resize_official(record[field])
        for role, field in (("front", "frontPng"), ("rear", "rearPng"))
        if isinstance(record.get(field), bytes)
    }


def _appearance_metrics(
    appearance: Any,
    geometry_rasters: Mapping[str, bytes],
    target_rasters: Mapping[str, bytes],
    target_appearance: Mapping[str, Any],
    background: tuple[int, int, int],
) -> dict[str, Any]:
    comparisons = []
    candidate_front = b""
    for role, geometry in geometry_rasters.items():
        candidate = rerender_from_persisted_atlas(
            appearance,
            geometry,
            role=role,
            output_background=background,
        )
        if role == "front":
            candidate_front = candidate
        comparisons.append(_pixel_metrics(candidate, target_rasters[role]))
    colour = max(float(item["foregroundSrgbMae"]) for item in comparisons)
    logo = _logo_metrics(candidate_front, target_rasters["front"], target_appearance)
    passed = (
        colour <= 0.10
        and (logo["logoIoU"] is None or float(logo["logoIoU"]) >= 0.05)
        and (
            logo["logoDisplacementNormalized"] is None
            or float(logo["logoDisplacementNormalized"]) <= 0.14
        )
        and (
            logo["logoFalsePositiveFraction"] is None
            or float(logo["logoFalsePositiveFraction"]) <= 0.002
        )
    )
    return {
        "pass": passed,
        "foregroundSrgbMae": colour,
        **logo,
        "observedRegionOnlyScored": True,
        "generatedFillExcludedFromObservedScore": True,
    }


def _pixel_metrics(candidate_png: bytes, target_png: bytes) -> dict[str, float]:
    candidate = _decode_pixels(candidate_png)
    target = _decode_pixels(target_png)
    background = target[0][0]
    target_mask = _rgb_mask(target[0], background)
    candidate_background = candidate[0][0]
    candidate_mask = _rgb_mask(candidate[0], candidate_background)
    union = target_mask | candidate_mask
    intersection = target_mask & candidate_mask
    errors = [
        math.fsum(
            abs(candidate[0][index][channel] - target[0][index][channel]) for channel in range(3)
        )
        / (3.0 * 255.0)
        for index in target_mask & candidate_mask
    ]
    return {
        "silhouetteIoU": len(intersection) / max(1, len(union)),
        "foregroundSrgbMae": _mean(errors) if errors else 1.0,
        "landmarkProxyError": _mask_landmark_error(
            candidate_mask,
            target_mask,
            width=candidate[1],
            height=candidate[2],
        ),
    }


def _raster_metrics(
    candidates: Mapping[str, bytes], targets: Mapping[str, bytes]
) -> dict[str, float]:
    rows = [_pixel_metrics(candidates[role], target) for role, target in targets.items()]
    return {
        "silhouetteIoU": _mean([float(row["silhouetteIoU"]) for row in rows]),
        "foregroundSrgbMae": _mean([float(row["foregroundSrgbMae"]) for row in rows]),
        "landmarkProxyError": max(float(row["landmarkProxyError"]) for row in rows),
    }


def _logo_metrics(
    candidate_png: bytes, target_png: bytes, appearance: Mapping[str, Any]
) -> dict[str, float | None]:
    candidate_pixels, width, height = _decode_pixels(candidate_png)
    target_pixels, _, _ = _decode_pixels(target_png)
    colour = tuple(int(value) for value in appearance["logoColorSrgb"])
    candidate = _colour_mask(candidate_pixels, colour)
    target = _colour_mask(target_pixels, colour)
    present = appearance.get("logoShape") != "none"
    if not present:
        return {
            "logoIoU": None,
            "logoDisplacementNormalized": None,
            "logoFalsePositiveFraction": len(candidate) / (width * height),
        }
    union = candidate | target
    return {
        "logoIoU": len(candidate & target) / max(1, len(union)),
        "logoDisplacementNormalized": math.dist(
            _centroid(candidate, width), _centroid(target, width)
        )
        / math.hypot(width, height),
        "logoFalsePositiveFraction": None,
    }


def _parameter_metrics(
    prediction: Mapping[str, Any],
    target: Mapping[str, Any],
    observed_parameters: Sequence[str] = OBSERVABLE_PARAMETERS,
) -> dict[str, Any]:
    errors = {
        name: abs(float(prediction[name]) - float(target[name]))
        / (PARAMETER_RANGES[name][1] - PARAMETER_RANGES[name][0])
        for name in observed_parameters
    }
    finite_safe = all(
        math.isfinite(float(prediction[name]))
        and PARAMETER_RANGES[name][0] <= float(prediction[name]) <= PARAMETER_RANGES[name][1]
        for name in OBSERVABLE_PARAMETERS
    )
    return {
        "byParameter": errors,
        "observedParameterCount": len(observed_parameters),
        "unobservedParameters": sorted(set(OBSERVABLE_PARAMETERS) - set(observed_parameters)),
        "macro": _mean(list(errors.values())),
        "worst": max(errors.values()),
        "finiteAndSafe": finite_safe,
    }


def _semantic_audit(candidate: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "seamsExact": _semantic_inventory(candidate.get("seams"))
        == _semantic_inventory(target.get("seams")),
        "openingsExact": _semantic_inventory(candidate.get("openings"))
        == _semantic_inventory(target.get("openings")),
    }


def _reference_surface_metrics(candidate: Any, target: Any) -> dict[str, float | int | str]:
    candidate_vertices = [vertex for mesh in candidate.meshes for vertex in mesh.vertices]
    target_vertices = [vertex for mesh in target.meshes for vertex in mesh.vertices]
    candidate_sample = _even_sample(candidate_vertices, 160)
    target_sample = _even_sample(target_vertices, 160)
    distances = [
        min(math.dist(vertex, other) for other in target_sample) for vertex in candidate_sample
    ]
    distances.extend(
        min(math.dist(vertex, other) for other in candidate_sample) for vertex in target_sample
    )
    return {
        "vertexCountDelta": abs(len(candidate_vertices) - len(target_vertices)),
        "sampleCountPerSurfaceMaximum": 160,
        "rmsVertexErrorMeters": math.sqrt(_mean([value * value for value in distances])),
        "maximumVertexErrorMeters": max(distances, default=1.0),
        "metric": "symmetric_deterministic_sampled_surface_nearest_vertex_distance",
    }


def _even_sample(values: Sequence[Any], maximum: int) -> list[Any]:
    if len(values) <= maximum:
        return list(values)
    return [values[round(index * (len(values) - 1) / (maximum - 1))] for index in range(maximum)]


def _semantic_inventory(value: Any) -> list[str]:
    return sorted(canonical_dumps(item) for item in value) if isinstance(value, list) else []


def _candidate_complete(prediction: Mapping[str, Any]) -> bool:
    parameters = prediction.get("parameters")
    return isinstance(parameters, Mapping) and all(
        name in parameters for name in OBSERVABLE_PARAMETERS
    )


def _failed_record(
    record: Mapping[str, Any],
    prediction: Mapping[str, Any],
    baseline: Mapping[str, Any],
    lifecycle: Mapping[str, bool],
) -> dict[str, Any]:
    return {
        "identityHash": record["identityHash"],
        "ordinal": record["ordinal"],
        "partition": record["partition"],
        "status": "fail",
        "lifecycle": dict(lifecycle),
        "prediction": _compact_prediction(prediction),
        "predictionDigest": _digest(prediction, None),
        "parameterMetrics": {"macro": 1.0, "worst": 1.0, "finiteAndSafe": False},
        "baselineParameterMetrics": _parameter_metrics(baseline, _mapping(record["parameters"])),
        "rasterMetrics": {
            "silhouetteIoU": 0.0,
            "foregroundSrgbMae": 1.0,
            "landmarkProxyError": 1.0,
        },
        "baselineRasterMetrics": {
            "silhouetteIoU": 0.0,
            "foregroundSrgbMae": 1.0,
            "landmarkProxyError": 1.0,
        },
        "appearanceMetrics": {"pass": False, "foregroundSrgbMae": 1.0},
        "reference3dMetrics": {"rmsVertexErrorMeters": 1.0},
        "semanticAudit": {"seamsExact": False, "openingsExact": False},
        "compileReport": None,
        "appearanceAtlasManifest": None,
    }


def _compact_prediction(prediction: Mapping[str, Any]) -> dict[str, Any]:
    keep = (
        "status",
        "reason",
        "parameters",
        "rawLogits",
        "constraintSaturation",
        "uncertainty95",
        "confidence",
        "evidenceClass",
        "targetParametersRead",
        "fittingVersion",
        "fit",
    )
    return {key: deepcopy(prediction[key]) for key in keep if key in prediction}


def _prediction_digest(
    prediction: Mapping[str, Any], appearance_manifest: Mapping[str, Any]
) -> str:
    return sha256_bytes(
        canonical_dumps(
            {
                "prediction": _compact_prediction(prediction),
                "appearanceManifestDigest": appearance_manifest["manifestDigest"],
            }
        ).encode("utf-8")
    )


def _resize_official(png: bytes) -> bytes:
    with Image.open(BytesIO(png)) as image:
        rgba = image.convert("RGBA")
        if rgba.size != (128, 160):
            rgba = rgba.resize((128, 160), Image.Resampling.BILINEAR)
        output = BytesIO()
        rgba.save(output, format="PNG", optimize=False, compress_level=9)
        return output.getvalue()


def _decode_pixels(png: bytes) -> tuple[list[tuple[int, int, int, int]], int, int]:
    with Image.open(BytesIO(png)) as image:
        rgba = image.convert("RGBA")
        return list(rgba.getdata()), rgba.width, rgba.height


def _rgb_mask(pixels: Sequence[tuple[int, int, int, int]], background: Sequence[int]) -> set[int]:
    return {
        index
        for index, pixel in enumerate(pixels)
        if max(abs(pixel[channel] - int(background[channel])) for channel in range(3)) >= 24
    }


def _colour_mask(pixels: Sequence[tuple[int, int, int, int]], colour: Sequence[int]) -> set[int]:
    return {
        index
        for index, pixel in enumerate(pixels)
        if max(abs(pixel[channel] - int(colour[channel])) for channel in range(3)) <= 4
    }


def _centroid(indices: set[int], width: int) -> tuple[float, float]:
    if not indices:
        return (0.0, 0.0)
    return (
        math.fsum(index % width for index in indices) / len(indices),
        math.fsum(index // width for index in indices) / len(indices),
    )


def _mask_landmark_error(
    candidate: set[int], target: set[int], *, width: int, height: int
) -> float:
    """Compare observable silhouette landmarks in normalized image coordinates."""
    if not candidate or not target or width <= 1 or height <= 1:
        return 1.0

    def landmarks(indices: set[int]) -> tuple[float, ...]:
        xs = [index % width for index in indices]
        ys = [index // width for index in indices]
        centroid_x, centroid_y = _centroid(indices, width)
        return (
            min(xs) / (width - 1),
            max(xs) / (width - 1),
            min(ys) / (height - 1),
            max(ys) / (height - 1),
            centroid_x / (width - 1),
            centroid_y / (height - 1),
        )

    return max(
        abs(left - right)
        for left, right in zip(landmarks(candidate), landmarks(target), strict=True)
    )


def _background(record: Mapping[str, Any]) -> tuple[int, int, int]:
    values = _mapping(record["capture"])["backgroundSrgb"]
    return (int(values[0]), int(values[1]), int(values[2]))


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / max(1, len(values))


def _digest(value: Mapping[str, Any], field: str | None) -> str:
    payload = deepcopy(dict(value))
    if field is not None:
        payload[field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _records(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
