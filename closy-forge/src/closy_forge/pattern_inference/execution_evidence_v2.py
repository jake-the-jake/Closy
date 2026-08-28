from __future__ import annotations

import ctypes
import math
import os
import platform
import statistics
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

from closy_forge.garments.simple_skirt.parameters import SimpleSkirtParameters
from closy_forge.garments.sleeveless_top.parameters import SleevelessTopParameters
from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.pattern_inference.model_v2 import decode_prediction, predict_v2
from closy_forge.pipeline.build_simple_skirt_demo import build_demo_simple_skirt_package
from closy_forge.pipeline.build_sleeveless_demo import build_demo_sleeveless_package

EVIDENCE_VERSION = "closy.pattern_inference.execution_evidence.d0.v1"


def write_execution_evidence_v2(
    output: Path,
    bundle: dict[str, Any],
    *,
    training_pipeline_wall_ns: int,
    training_pipeline_cpu_ns: int,
    training_pipeline_memory: dict[str, Any],
    commit_sha: str | None,
) -> dict[str, Any]:
    inference = _benchmark_inference(bundle)
    settle = _post_settle_package_evidence(bundle)
    report = {
        "schemaVersion": 1,
        "evidenceVersion": EVIDENCE_VERSION,
        "scope": "host_cpu_project_authored_synthetic_d0_not_mobile",
        "commitSha": commit_sha,
        "host": {
            "platform": platform.platform(),
            "processor": platform.processor() or "unreported",
            "python": platform.python_version(),
            "logicalCpuCount": os.cpu_count(),
        },
        "training": {
            "actualOptimizerExecuted": True,
            "includesTwoRunReproducibilityAndEvaluation": True,
            "wallMilliseconds": round(training_pipeline_wall_ns / 1_000_000, 6),
            "cpuMilliseconds": round(training_pipeline_cpu_ns / 1_000_000, 6),
            "memory": training_pipeline_memory,
            "modelHash": bundle["model"]["integrity"]["modelHash"],
            "weightsHash": bundle["model"]["integrity"]["weightsHash"],
        },
        "inference": inference,
        "postSettle": settle,
        "claims": {
            "realOrPublicCaptureGeneralisation": False,
            "mobilePerformance": False,
            "humanReviewed": False,
            "globalPhase9Complete": False,
        },
    }
    write_canonical_json(output, report)
    return report


def _benchmark_inference(bundle: dict[str, Any]) -> dict[str, Any]:
    test_ids = set(bundle["split"]["samples"]["test"])
    samples = [sample for sample in bundle["dataset"]["samples"] if sample["sampleId"] in test_ids]
    timings: list[int] = []
    tracemalloc.start()
    for _ in range(4):
        for sample in samples:
            start = time.perf_counter_ns()
            predict_v2(bundle["model"], sample["input"])
            timings.append(time.perf_counter_ns() - start)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    timings.sort()
    return {
        "sampleInvocationCount": len(timings),
        "warmupPolicy": "first full held-out pass retained",
        "medianMilliseconds": round(statistics.median(timings) / 1_000_000, 6),
        "p95Milliseconds": round(_percentile(timings, 0.95) / 1_000_000, 6),
        "peakTracedBytes": peak,
    }


def _post_settle_package_evidence(bundle: dict[str, Any]) -> dict[str, Any]:
    records = []
    with tempfile.TemporaryDirectory(prefix="closy-phase9-settle-") as temporary:
        root = Path(temporary)
        records.append(
            _build_family_evidence(
                bundle,
                family="sleeveless_top",
                output=root / "sleeveless.closygarment",
                parameter_type=SleevelessTopParameters,
                builder=build_demo_sleeveless_package,
                fit_path="fitting/sleeveless_fit.json",
                quality_path="reports/sleeveless_quality.json",
            )
        )
        records.append(
            _build_family_evidence(
                bundle,
                family="simple_skirt",
                output=root / "skirt.closygarment",
                parameter_type=SimpleSkirtParameters,
                builder=build_demo_simple_skirt_package,
                fit_path="fitting/simple_skirt_fit.json",
                quality_path="reports/simple_skirt_quality.json",
            )
        )
    return {
        "status": "actual_downstream_package_settle_executed",
        "profile": "two_family_project_authored_synthetic_host_cpu_d0",
        "familyCount": len(records),
        "allPackagesValidated": all(record["packageValidation"] == "passed" for record in records),
        "allFitsAccepted": all(record["fit"]["accepted"] is True for record in records),
        "allDecodedSilhouetteComparisonsAccepted": all(
            record["settledSilhouette"]["decodedComparisonAccepted"] is True for record in records
        ),
        "records": records,
    }


def _build_family_evidence(
    bundle: dict[str, Any],
    *,
    family: str,
    output: Path,
    parameter_type: type[Any],
    builder: Callable[..., Any],
    fit_path: str,
    quality_path: str,
) -> dict[str, Any]:
    sample = next(
        sample
        for sample in bundle["dataset"]["samples"]
        if sample["target"]["garmentFamily"] == family
        and sample["sampleId"] in set(bundle["split"]["samples"]["test"])
    )
    prediction = predict_v2(bundle["model"], sample["input"])
    if prediction["status"] != "predicted" or prediction["family"] != family:
        raise RuntimeError(f"held_out_prediction_not_buildable:{family}")
    program, _ = decode_prediction(
        prediction,
        program_id=f"settle.evidence.{family}",
        base_seed=47_000,
    )
    params = parameter_type(**program["parameters"])
    wall_start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    result = builder(output, params=params, seed=47_000)
    cpu_ns = time.process_time_ns() - cpu_start
    wall_ns = time.perf_counter_ns() - wall_start
    fit = read_json(output / fit_path)
    quality = read_json(output / quality_path)
    fidelity = read_json(output / "reports/fidelity/source_render_fidelity.json")
    settled = read_json(output / "simulation/settled_state.json")
    acceptance_key = {
        "sleeveless_top": "acceptedForD0SleevelessFixture",
        "simple_skirt": "acceptedForD0SimpleSkirtFixture",
    }[family]
    decoded_accepted = bool(quality.get("appearance", {}).get(acceptance_key, False))
    return {
        "family": family,
        "heldOutSampleId": sample["sampleId"],
        "predictedFamily": prediction["family"],
        "packageValidation": result.validation["status"],
        "canonicalPackageDigest": result.manifest["packageDigest"],
        "manifestHash": sha256_file(output / "manifest.json"),
        "settledStateContentHash": settled["meshContentHash"],
        "fit": {
            "accepted": fit["accepted"],
            "weightedObjective": fit["winnerLosses"]["weightedObjective"],
            "losses": fit["winnerLosses"],
            "learnedFitRun": fit["learnedFitRun"],
        },
        "settledSilhouette": {
            "decodedComparisonAccepted": decoded_accepted,
            "decodedPixelComparisonRun": fidelity.get("decodedPixelComparisonRun"),
            "metrics": _fidelity_metrics(fidelity),
            "finiteBounds": quality["topology"]["finiteBounds"],
        },
        "runtime": {
            "wallMilliseconds": round(wall_ns / 1_000_000, 6),
            "cpuMilliseconds": round(cpu_ns / 1_000_000, 6),
        },
    }


def _fidelity_metrics(fidelity: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for key, value in fidelity.items():
        lowered = key.lower()
        if isinstance(value, int | float | bool) and any(
            token in lowered for token in ("error", "iou", "silhouette", "coverage", "accepted")
        ):
            metrics[key] = value
    return metrics


def _percentile(values: list[int], quantile: float) -> int:
    index = min(len(values) - 1, max(0, int(math.ceil(quantile * len(values))) - 1))
    return values[index]


def process_memory_snapshot() -> dict[str, Any]:
    if os.name == "nt":

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        win_dll_factory = getattr(ctypes, "WinDLL", None)
        if win_dll_factory is None:
            return {"measurement": "windows_process_memory_unavailable"}
        kernel32 = win_dll_factory("kernel32", use_last_error=True)
        psapi = win_dll_factory("psapi", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.argtypes = []
        get_current_process.restype = ctypes.c_void_p
        get_process_memory_info = psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ProcessMemoryCounters),
            ctypes.c_ulong,
        ]
        get_process_memory_info.restype = ctypes.c_int
        if not get_process_memory_info(get_current_process(), ctypes.byref(counters), counters.cb):
            return {"measurement": "windows_process_memory_unavailable"}
        return {
            "measurement": "windows_process_memory_counters",
            "workingSetBytes": int(counters.WorkingSetSize),
            "peakWorkingSetBytes": int(counters.PeakWorkingSetSize),
        }
    return {
        "measurement": "portable_memory_not_available_on_this_host",
        "workingSetBytes": None,
        "peakWorkingSetBytes": None,
    }
