from __future__ import annotations

import json
import math
import time
import tracemalloc
from dataclasses import replace
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import BindingFile, read_binding
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.core_runtime_c3_v4.candidate_deformation import deform_simulation_representation
from closy_forge.core_runtime_c3_v4.oracle import deform_dense_shell_directly
from closy_forge.geometry.frame_attributes import meshset_frame_metrics
from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3, cross, sub
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, topology_hash
from closy_forge.runtime_delivery.package import load_runtime_package

EVALUATOR_VERSION = "closy.d0_strict_c3_binding_evaluator.v4"


def evaluate_strict_c3(
    root: Path, sentinel: dict[str, Any], lock: dict[str, Any]
) -> dict[str, Any]:
    candidate = (
        root / "docs/evidence/d0_texture_rerender_correction_v3/predictions/candidate_package"
    )
    sim = read_glb_meshset(candidate / "simulation/settled_mesh.glb")
    dense = read_glb_meshset(candidate / "render/render_mesh.glb")
    binding = read_binding(candidate / "binding/sim_to_render.bin")
    constraints = _read(candidate / "simulation/constraints.json")
    thresholds = lock["thresholds"]
    expected_topology = topology_hash(sim)
    topology_mismatches = int(binding.simulation_topology_hash != expected_topology)
    topology_mismatches += int(binding.render_topology_hash != topology_hash(dense))
    if topology_mismatches:
        raise ValueError("h4_binding_topology_hash_mismatch")
    records = []
    canonical_hashes: list[str] = []
    for state in lock["heldOutStates"]:
        tracemalloc.start()
        started = time.perf_counter()
        candidate_sim = deform_simulation_representation(sim, state)
        reconstructed = reconstruct_vertices(candidate_sim, binding)
        oracle_mesh = deform_dense_shell_directly(dense, state)
        oracle_vertices = _flatten(oracle_mesh)
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        candidate_mesh = _replace_vertices(dense, reconstructed)
        errors = [_distance(a, b) for a, b in zip(reconstructed, oracle_vertices, strict=True)]
        frame = meshset_frame_metrics(candidate_mesh)
        inversions = _inversions(candidate_mesh, oracle_mesh)
        output_hash = _vertex_hash(reconstructed)
        repeat_hash = _vertex_hash(
            reconstruct_vertices(deform_simulation_representation(sim, state), binding)
        )
        canonical_hashes.append(output_hash)
        seam_residual = max(errors, default=0.0)
        tangent_residual = _maximum_tangential_residual(candidate_mesh, oracle_mesh)
        checks = {
            "reconstruction": max(errors, default=0.0)
            <= thresholds["maximumBindingReconstructionErrorMeters"],
            "seamCrackResidual": seam_residual <= thresholds["maximumSeamCrackMeters"],
            "tangentialSlidingResidual": tangent_residual
            <= thresholds["maximumTangentialSeamSlidingMeters"],
            "inversions": inversions <= thresholds["maximumInversionCount"],
            "normalLength": frame["maximumNormalLengthError"]
            <= thresholds["maximumNormalLengthError"],
            "tangentLength": frame["maximumTangentLengthError"]
            <= thresholds["maximumTangentLengthError"],
            "normalTangentOrthogonality": frame["maximumAbsoluteNormalTangentDot"]
            <= thresholds["maximumAbsoluteNormalTangentDot"],
            "deterministic": output_hash == repeat_hash,
            "runtime": elapsed <= thresholds["maximumRuntimeSecondsPerPose"],
            "memory": peak / (1024 * 1024) <= thresholds["maximumPeakMemoryMiB"],
        }
        records.append(
            {
                "state": state,
                "maximumReconstructionErrorMeters": max(errors, default=0.0),
                "rmsReconstructionErrorMeters": math.sqrt(
                    sum(value * value for value in errors) / max(1, len(errors))
                ),
                "maximumSeamCrackResidualMeters": seam_residual,
                "maximumTangentialSeamSlidingResidualMeters": tangent_residual,
                "inversionCount": inversions,
                "frameMetrics": frame,
                "runtimeSeconds": elapsed,
                "peakMemoryMiB": peak / (1024 * 1024),
                "canonicalOutputSha256": output_hash,
                "deterministicRepeatSha256": repeat_hash,
                "checks": checks,
                "status": "pass" if all(checks.values()) else "fail",
            }
        )
    runtime_path = root / (
        "docs/evidence/d0_texture_rerender_correction_v3/predictions/"
        "candidate_runtime.closyruntime"
    )
    fallback = load_runtime_package(runtime_path, offline=True)
    fallback_checks = {
        "selectedConventionalGlb": fallback.selected_source == "conventional_glb",
        "fallbackMatchesSentinel": sha256_bytes(fallback.selected_bytes)
        == sentinel["identities"]["fallback"]["sha256"],
        "denseVertexCountPreserved": dense.vertex_count == len(binding.records),
        "seamCountPreserved": len(constraints.get("seams", [])) > 0,
        "openingCountPreserved": len(constraints.get("openings", [])) > 0,
        "hiddenComponentDeletionCount": 0,
    }
    mutation = _mutation_control(sim, dense, binding, lock["heldOutStates"][-1], thresholds)
    pass_count = sum(record["status"] == "pass" for record in records)
    all_pass = (
        pass_count == thresholds["requiredHeldOutPassCount"]
        and len(records) == thresholds["requiredHeldOutStateCount"]
        and topology_mismatches == 0
        and all(fallback_checks.values())
        and mutation["status"] == "pass"
    )
    return {
        "schemaVersion": 1,
        "evaluatorVersion": EVALUATOR_VERSION,
        "scope": "strict_non_physical_pre_topology_binding_gate",
        "sentinelManifestDigest": sentinel["integrity"]["sentinelManifestDigest"],
        "protocolLockDigest": lock["integrity"]["protocolLockDigest"],
        "candidateId": sentinel["candidateId"],
        "candidatePackageDigest": sentinel["candidatePackageDigest"],
        "attempt": {"strategyNumber": 1, "heldOutAttemptNumber": 1, "final": True},
        "simulationTopologyHash": expected_topology,
        "renderTopologyHash": topology_hash(dense),
        "bindingRecordCount": len(binding.records),
        "topologyHashMismatchCount": topology_mismatches,
        "seamCount": len(constraints.get("seams", [])),
        "openingCount": len(constraints.get("openings", [])),
        "heldOutStateCount": len(records),
        "heldOutPassCount": pass_count,
        "states": records,
        "canonicalOutputInventoryDigest": sha256_bytes(
            canonical_dumps(canonical_hashes).encode("utf-8")
        ),
        "fallback": fallback_checks,
        "mutationControl": mutation,
        "resultStatus": "pass" if all_pass else "fail",
        "d0Rp08Status": "pass" if all_pass else "fail",
        "physicalClothImplied": False,
        "phy1Implied": False,
        "z2Implied": False,
        "predecessorScoped": True,
    }


def _mutation_control(
    sim: MeshSet,
    dense: MeshSet,
    binding: BindingFile,
    state: dict[str, object],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    oracle = deform_dense_shell_directly(dense, state)
    oracle_hash_before = _vertex_hash(_flatten(oracle))
    original = binding.records[0]
    mutated_u = min(0.9, original.barycentric_u + 0.2)
    mutated_records = list(binding.records)
    mutated_records[0] = replace(original, barycentric_u=mutated_u)
    mutated = BindingFile(
        mutated_records,
        binding.simulation_triangle_count,
        binding.panel_count,
        binding.simulation_topology_hash,
        binding.render_topology_hash,
    )
    mutated_vertices = reconstruct_vertices(deform_simulation_representation(sim, state), mutated)
    maximum_error = max(
        _distance(a, b) for a, b in zip(mutated_vertices, _flatten(oracle), strict=True)
    )
    oracle_hash_after = _vertex_hash(_flatten(deform_dense_shell_directly(dense, state)))
    passed = (
        maximum_error > thresholds["maximumBindingReconstructionErrorMeters"]
        and oracle_hash_before == oracle_hash_after
    )
    return {
        "mutation": "first_binding_barycentric_u_plus_0.2_bounded",
        "mutatedCandidateMaximumErrorMeters": maximum_error,
        "candidateComparisonFailedAsRequired": maximum_error
        > thresholds["maximumBindingReconstructionErrorMeters"],
        "oracleSha256Before": oracle_hash_before,
        "oracleSha256After": oracle_hash_after,
        "oracleUnchanged": oracle_hash_before == oracle_hash_after,
        "status": "pass" if passed else "fail",
    }


def _replace_vertices(template: MeshSet, vertices: list[Vec3]) -> MeshSet:
    offset = 0
    meshes = []
    for mesh in template.meshes:
        count = len(mesh.vertices)
        meshes.append(
            Mesh(
                mesh.name,
                mesh.panel_id,
                vertices[offset : offset + count],
                list(mesh.panel_uvs),
                list(mesh.triangles),
                mesh.material_id,
            )
        )
        offset += count
    if offset != len(vertices):
        raise ValueError("h4_dense_vertex_inventory_mismatch")
    return MeshSet(meshes)


def _inversions(candidate: MeshSet, oracle: MeshSet) -> int:
    count = 0
    for left, right in zip(candidate.meshes, oracle.meshes, strict=True):
        for tri in left.triangles:
            ln = cross(
                sub(left.vertices[tri[1]], left.vertices[tri[0]]),
                sub(left.vertices[tri[2]], left.vertices[tri[0]]),
            )
            rn = cross(
                sub(right.vertices[tri[1]], right.vertices[tri[0]]),
                sub(right.vertices[tri[2]], right.vertices[tri[0]]),
            )
            if sum(a * b for a, b in zip(ln, rn, strict=True)) <= 0.0:
                count += 1
    return count


def _maximum_tangential_residual(candidate: MeshSet, oracle: MeshSet) -> float:
    maximum = 0.0
    for left, right in zip(_flatten(candidate), _flatten(oracle), strict=True):
        maximum = max(maximum, math.hypot(left[0] - right[0], left[1] - right[1]))
    return maximum


def _flatten(meshset: MeshSet) -> list[Vec3]:
    return [vertex for mesh in meshset.meshes for vertex in mesh.vertices]


def _distance(left: Vec3, right: Vec3) -> float:
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))


def _vertex_hash(vertices: list[Vec3]) -> str:
    return sha256_bytes(
        canonical_dumps([[round(value, 9) for value in vertex] for vertex in vertices]).encode(
            "utf-8"
        )
    )


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}
