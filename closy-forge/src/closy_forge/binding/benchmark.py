from __future__ import annotations

import os
import platform
import statistics
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import read_binding
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Tri, Vec3
from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.hashing import sha256_bytes

BENCHMARK_VERSION = "closy.production_binding_benchmark.noncanonical.v1"


def benchmark_binding_c3(
    package_dir: Path, *, warmups: int = 3, repeats: int = 20, commit_sha: str | None = None
) -> dict[str, Any]:
    if warmups < 1 or repeats < 3:
        raise ValueError("binding benchmark requires at least one warmup and three repeats")
    sim_manifest = read_json(package_dir / "simulation" / "mesh_manifest.json")
    render_manifest = read_json(package_dir / "render" / "mesh_manifest.json")
    state_index = read_json(package_dir / "simulation" / "motion_states" / "index.json")
    simulation = _meshset_from_manifest(sim_manifest)
    render = _meshset_from_manifest(render_manifest)
    states = [read_json(package_dir / entry["path"]) for entry in state_index["states"]]
    state_meshes = [_meshset_from_state(state, simulation) for state in states]
    binding_path = package_dir / "binding" / "sim_to_render.bin"

    decode = _measure(lambda: read_binding(binding_path), warmups, repeats)
    binding = read_binding(binding_path)
    dense_one = _measure(lambda: reconstruct_vertices(state_meshes[0], binding), warmups, repeats)
    dense_suite = _measure(
        lambda: [reconstruct_vertices(state, binding) for state in state_meshes],
        warmups,
        repeats,
    )
    fallback_one = _measure(lambda: _fallback_positions(state_meshes[0]), warmups, repeats)
    fallback_suite = _measure(
        lambda: [_fallback_positions(state) for state in state_meshes], warmups, repeats
    )
    profile = {
        "schemaVersion": 1,
        "reportVersion": BENCHMARK_VERSION,
        "evidenceKind": "noncanonical_host_cpu_measurement",
        "commitSha": commit_sha or os.environ.get("GITHUB_SHA", "not_recorded_local_run"),
        "bindingReportVersion": "closy.production_binding_c3.d0_tshirt.integrity_v2",
        "operatingSystem": platform.platform(),
        "architecture": platform.machine() or "unknown",
        "cpuModel": platform.processor() or "not_reported_by_runtime",
        "pythonVersion": platform.python_version(),
        "workload": {
            "simulationVertices": simulation.vertex_count,
            "simulationTriangles": simulation.triangle_count,
            "renderVertices": render.vertex_count,
            "renderTriangles": render.triangle_count,
            "bindingRecords": len(binding.records),
            "motionStates": len(state_meshes),
        },
        "warmupCount": warmups,
        "repeatCount": repeats,
        "measurements": {
            "persistedBindingDecode": decode,
            "denseOneState": dense_one,
            "denseFullSuite": dense_suite,
            "fallbackOneState": fallback_one,
            "fallbackFullSuite": fallback_suite,
        },
        "measurementMethod": {
            "duration": "time.perf_counter_ns",
            "peakMemory": "tracemalloc_process_python_allocations",
            "statistics": "median_and_nearest_rank_p95",
        },
        "success": True,
        "limitations": [
            "hosted_or_local_cpu_noise_not_a_product_gate",
            "not_gpu_performance",
            "not_mobile_device_performance",
            "python_allocations_only_peak_memory",
        ],
    }
    profile["reportHash"] = sha256_bytes(repr(profile).encode("utf-8"))
    return profile


def _measure(operation: Callable[[], object], warmups: int, repeats: int) -> dict[str, Any]:
    for _ in range(warmups):
        operation()
    durations: list[float] = []
    peak = 0
    for _ in range(repeats):
        tracemalloc.start()
        start = time.perf_counter_ns()
        operation()
        elapsed = time.perf_counter_ns() - start
        _, run_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        durations.append(elapsed / 1_000_000.0)
        peak = max(peak, run_peak)
    ordered = sorted(durations)
    p95_index = min(len(ordered) - 1, max(0, int((len(ordered) * 0.95) - 1)))
    return {
        "repeatCount": repeats,
        "medianMilliseconds": round(statistics.median(ordered), 6),
        "p95Milliseconds": round(ordered[p95_index], 6),
        "minimumMilliseconds": round(ordered[0], 6),
        "maximumMilliseconds": round(ordered[-1], 6),
        "peakMemoryBytes": peak,
        "status": "measured",
    }


def _fallback_positions(meshset: MeshSet) -> list[Vec3]:
    # Deliberately independent: direct simulation positions, no binding or dense reconstruction.
    return [(point[0], point[1], point[2]) for mesh in meshset.meshes for point in mesh.vertices]


def _meshset_from_manifest(manifest: dict[str, Any]) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                str(item["name"]),
                str(item["panelId"]),
                [_vec3(point) for point in item["vertices"]],
                [(float(uv[0]), float(uv[1])) for uv in item["panelUvs"]],
                [_tri(tri) for tri in item["triangles"]],
                str(item.get("materialId", "material.cotton_jersey_reference_v1")),
            )
            for item in manifest["meshes"]
        ]
    )


def _meshset_from_state(state: dict[str, Any], reference: MeshSet) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                source.name,
                source.panel_id,
                [_vec3(point) for point in state_mesh["positions"]],
                source.panel_uvs,
                source.triangles,
                source.material_id,
            )
            for source, state_mesh in zip(reference.meshes, state["meshes"], strict=True)
        ]
    )


def _vec3(value: Any) -> Vec3:
    return (float(value[0]), float(value[1]), float(value[2]))


def _tri(value: Any) -> Tri:
    return (int(value[0]), int(value[1]), int(value[2]))
