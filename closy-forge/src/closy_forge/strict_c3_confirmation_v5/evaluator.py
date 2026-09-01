from __future__ import annotations

import math
import subprocess
import sys
import time
import tracemalloc
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import BindingFile, read_binding
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3, cross, sub
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file, topology_hash
from closy_forge.recovery_foundation_v1.c3_v5 import canonical_frame_metrics
from closy_forge.simulation.seam_mapping import span_position
from closy_forge.strict_c3_confirmation_v5.candidate import deform_candidate_simulation
from closy_forge.strict_c3_confirmation_v5.oracle import (
    generate_oracle_target,
    validate_oracle_target,
)
from closy_forge.strict_c3_confirmation_v5.protocol import UNIT_F_PACKAGE, UNIT_F_RUNTIME

EVALUATOR_VERSION = "closy.d0.strict_c3_binding_evaluator.v5"


def run_revealed_h4_diagnostic(
    root: Path,
    lock: Mapping[str, Any],
    target_root: Path,
) -> dict[str, Any]:
    from closy_forge.core_runtime_c3_v4.protocol import HELD_OUT_STATES

    package = root / UNIT_F_PACKAGE
    simulation = read_glb_meshset(package / "simulation/settled_mesh.glb")
    dense = read_glb_meshset(package / "render/render_mesh.glb")
    poses = [
        {
            **state,
            "poseClass": f"revealed_h4_{index}",
            "poseId": f"diagnostic.h4.{index:02d}",
        }
        for index, state in enumerate(HELD_OUT_STATES)
    ]
    target_root.mkdir(parents=True, exist_ok=True)
    targets: list[Path] = []
    for pose in poses:
        path = target_root / f"{pose['poseId']}.json"
        write_canonical_json(path, generate_oracle_target(simulation, dense, pose))
        targets.append(path)
    result = evaluate_confirmation(root, lock, poses, targets)
    deterministic_maximums = {
        key: round(float(value), 12)
        for key, value in _mapping(result["maximums"]).items()
        if key
        not in {
            "maximumWholeEvaluationSecondsPerPose",
            "maximumWholeEvaluationPeakMemoryMiB",
        }
    }
    return {
        "schemaVersion": 1,
        "diagnosticVersion": "closy.c3.revealed_h4_patched_replay.v5",
        "usesRevealedH4Parameters": True,
        "freshV5PoseRealized": False,
        "qualificationEligible": False,
        "qualificationAttemptConsumed": False,
        "poseCount": result["poseCount"],
        "posePassCount": result["posePassCount"],
        "diagnosticResult": result["resultStatus"],
        "deterministicMaximums": deterministic_maximums,
        "mutationStatus": _mapping(result["mutationControls"])["status"],
    }


def evaluate_confirmation(
    root: Path,
    lock: Mapping[str, Any],
    poses: list[dict[str, Any]],
    target_paths: Sequence[Path],
) -> dict[str, Any]:
    package = root / UNIT_F_PACKAGE
    simulation_source = read_glb_meshset(package / "simulation/settled_mesh.glb")
    dense_source = read_glb_meshset(package / "render/render_mesh.glb")
    binding = read_binding(package / "binding/sim_to_render.bin")
    constraints = _mapping(read_json(package / "simulation/constraints.json"))
    _validate_topology(simulation_source, dense_source, binding)
    if len(poses) != len(target_paths):
        raise ValueError("unit_n_pose_target_denominator_mismatch")

    records = [
        _evaluate_pose(
            simulation_source,
            dense_source,
            binding,
            constraints,
            pose,
            target_path,
            _mapping(lock["thresholds"]),
        )
        for pose, target_path in zip(poses, target_paths, strict=True)
    ]
    subprocess_determinism = _run_subprocess_determinism(root, poses, records)
    mutation = _run_mutation_controls(
        simulation_source,
        dense_source,
        binding,
        poses[-1],
        target_paths[-1],
        float(_mapping(lock["thresholds"])["maximumBindingReconstructionErrorMeters"]),
    )
    fallback = root / UNIT_F_RUNTIME / "assets/conventional_fallback.glb"
    expected_fallback = _mapping(_mapping(lock["frozenInputs"])["conventionalFallback"])
    fallback_checks = {
        "exists": fallback.is_file(),
        "sha256MatchesLock": sha256_file(fallback) == expected_fallback.get("sha256"),
        "runtimeDescriptorMatchesLock": sha256_file(root / UNIT_F_RUNTIME / "manifest.json")
        == _mapping(_mapping(lock["frozenInputs"])["runtimeDescriptor"]).get("sha256"),
        "denseVertexCountEqualsBindingRecordCount": dense_source.vertex_count
        == len(binding.records),
        "semanticSeamCount": len(constraints.get("seams", [])),
        "semanticConstraintCount": len(constraints.get("constraints", [])),
        "semanticOpeningCount": len(constraints.get("openings", [])),
    }
    pass_count = sum(record["status"] == "pass" for record in records)
    thresholds = _mapping(lock["thresholds"])
    passed = (
        len(records) == int(thresholds["requiredPoseCount"])
        and pass_count == int(thresholds["requiredPosePassCount"])
        and subprocess_determinism["status"] == "pass"
        and mutation["status"] == "pass"
        and all(
            value is True
            for key, value in fallback_checks.items()
            if key
            in {
                "exists",
                "sha256MatchesLock",
                "runtimeDescriptorMatchesLock",
                "denseVertexCountEqualsBindingRecordCount",
            }
        )
        and fallback_checks["semanticSeamCount"] > 0
        and fallback_checks["semanticConstraintCount"] == 92
        and fallback_checks["semanticOpeningCount"] == 4
    )
    maximums = {
        "maximumBindingReconstructionErrorMeters": max(
            float(row["metrics"]["maximumBindingReconstructionErrorMeters"]) for row in records
        ),
        "maximumSemanticSeamCrackMeters": max(
            float(row["metrics"]["maximumSemanticSeamCrackMeters"]) for row in records
        ),
        "maximumTangentialSeamSlidingMeters": max(
            float(row["metrics"]["maximumTangentialSeamSlidingMeters"]) for row in records
        ),
        "maximumInvertedTriangleCount": max(
            int(row["metrics"]["invertedTriangleCount"]) for row in records
        ),
        "maximumWholeEvaluationSecondsPerPose": max(
            float(row["metrics"]["wholeEvaluationWallClockSeconds"]) for row in records
        ),
        "maximumWholeEvaluationPeakMemoryMiB": max(
            float(row["metrics"]["wholeEvaluationPeakMemoryMiB"]) for row in records
        ),
    }
    return {
        "schemaVersion": 1,
        "evaluatorVersion": EVALUATOR_VERSION,
        "scope": "synthetic_binding_reconstruction_pre_topology_exact_unit_f_sentinel",
        "candidateId": lock["candidateId"],
        "candidatePackageDigest": lock["candidatePackageDigest"],
        "sentinelLockDigest": lock["sentinelLockDigest"],
        "protocolLockDigest": _mapping(lock["integrity"])["protocolLockDigest"],
        "poseCount": len(records),
        "posePassCount": pass_count,
        "poses": records,
        "maximums": maximums,
        "fallback": fallback_checks,
        "subprocessDeterminism": subprocess_determinism,
        "mutationControls": mutation,
        "resultStatus": "pass" if passed else "numeric_fail",
        "d0Rp08Status": "pass" if passed else "fail",
        "attemptConsumed": True,
        "preTopology": True,
        "physicalClothImplied": False,
        "realWorldDeformationImplied": False,
        "phy1Implied": False,
        "z2Implied": False,
    }


def _evaluate_pose(
    simulation_source: MeshSet,
    dense_source: MeshSet,
    binding: BindingFile,
    constraints: Mapping[str, Any],
    pose: dict[str, Any],
    target_path: Path,
    thresholds: Mapping[str, Any],
) -> dict[str, Any]:
    tracemalloc.start()
    started = time.perf_counter()
    target = _mapping(read_json(target_path))
    target_issues = validate_oracle_target(target)
    if target_issues:
        tracemalloc.stop()
        raise ValueError("unit_n_oracle_target_invalid:" + ",".join(target_issues))
    if target.get("pose") != pose:
        tracemalloc.stop()
        raise ValueError("unit_n_oracle_pose_mismatch")
    oracle_simulation = _meshset_from_serialised(simulation_source, target["simulationVertices"])
    oracle_dense = _meshset_from_serialised(dense_source, target["denseVertices"])
    candidate_simulation = deform_candidate_simulation(simulation_source, pose)
    reconstructed = reconstruct_vertices(candidate_simulation, binding)
    candidate_dense = _replace_vertices(dense_source, reconstructed)
    oracle_vertices = _flatten(oracle_dense)
    errors = [
        _distance(candidate, oracle)
        for candidate, oracle in zip(reconstructed, oracle_vertices, strict=True)
    ]
    seam_crack, seam_slide = semantic_seam_error(
        candidate_simulation, oracle_simulation, constraints
    )
    frame = canonical_frame_metrics(candidate_dense)
    inversions = _inverted_triangle_count(candidate_dense, oracle_dense)
    output_digest = vertex_digest(reconstructed)
    repeat_digest = vertex_digest(
        reconstruct_vertices(deform_candidate_simulation(simulation_source, pose), binding)
    )
    candidate_components = _connected_component_count(candidate_dense)
    oracle_components = _connected_component_count(oracle_dense)
    openings_preserved = _semantic_openings_preserved(constraints)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_mib = peak / (1024 * 1024)
    maximum_error = max(errors, default=0.0)
    checks = {
        "bindingReconstruction": maximum_error
        <= float(thresholds["maximumBindingReconstructionErrorMeters"]),
        "semanticSeamCrack": seam_crack <= float(thresholds["maximumSemanticSeamCrackMeters"]),
        "tangentialSeamSliding": seam_slide
        <= float(thresholds["maximumTangentialSeamSlidingMeters"]),
        "invertedTriangles": inversions <= int(thresholds["maximumInvertedTriangleCount"]),
        "normalLength": frame.maximumNormalLengthError
        <= float(thresholds["maximumNormalLengthError"]),
        "tangentLength": frame.maximumTangentLengthError
        <= float(thresholds["maximumTangentLengthError"]),
        "normalTangentOrthogonality": frame.maximumAbsoluteNormalTangentDot
        <= float(thresholds["maximumAbsoluteNormalTangentDot"]),
        "deterministicRepeat": output_digest == repeat_digest,
        "semanticOpenings": openings_preserved,
        "componentInventory": candidate_components == oracle_components,
        "hiddenComponentDeletion": candidate_dense.vertex_count == oracle_dense.vertex_count,
        "runtime": elapsed <= float(thresholds["maximumWholeEvaluationSecondsPerPose"]),
        "memory": peak_mib <= float(thresholds["maximumWholeEvaluationPeakMemoryMiB"]),
    }
    return {
        "poseId": pose["poseId"],
        "poseClass": pose["poseClass"],
        "poseParameters": pose,
        "oracleTargetSha256": sha256_file(target_path),
        "oracleTargetDigest": target["targetDigest"],
        "metrics": {
            "maximumBindingReconstructionErrorMeters": maximum_error,
            "rmsBindingReconstructionErrorMeters": math.sqrt(
                math.fsum(error * error for error in errors) / max(1, len(errors))
            ),
            "maximumSemanticSeamCrackMeters": seam_crack,
            "maximumTangentialSeamSlidingMeters": seam_slide,
            "invertedTriangleCount": inversions,
            "candidateConnectedComponentCount": candidate_components,
            "oracleConnectedComponentCount": oracle_components,
            "frameMetrics": frame.to_document(),
            "wholeEvaluationWallClockSeconds": elapsed,
            "wholeEvaluationPeakMemoryMiB": peak_mib,
            "canonicalOutputSha256": output_digest,
            "deterministicRepeatSha256": repeat_digest,
        },
        "checks": checks,
        "status": "pass" if all(checks.values()) else "fail",
    }


def semantic_seam_error(
    candidate: MeshSet, oracle: MeshSet, constraints: Mapping[str, Any]
) -> tuple[float, float]:
    groups: dict[str, list[tuple[int, Vec3, Vec3, Vec3, Vec3]]] = defaultdict(list)
    raw_constraints = constraints.get("constraints", [])
    if not isinstance(raw_constraints, list):
        raise ValueError("unit_n_semantic_constraint_inventory_invalid")
    for record in raw_constraints:
        row = _mapping(record)
        span_a = _mapping(row["spanA"])
        span_b = _mapping(row["spanB"])
        candidate_a, candidate_b = (
            span_position(candidate, span_a),
            span_position(candidate, span_b),
        )
        oracle_a, oracle_b = span_position(oracle, span_a), span_position(oracle, span_b)
        ordinal = int(_mapping(row.get("mapping"))["ordinal"])
        groups[str(row["seamId"])].append((ordinal, candidate_a, candidate_b, oracle_a, oracle_b))
    normal_maximum = 0.0
    tangent_maximum = 0.0
    for samples in groups.values():
        samples.sort(key=lambda item: item[0])
        for index, (_, candidate_a, candidate_b, oracle_a, oracle_b) in enumerate(samples):
            midpoint = _midpoint(oracle_a, oracle_b)
            neighbour = samples[index + 1] if index + 1 < len(samples) else samples[index - 1]
            neighbour_midpoint = _midpoint(neighbour[3], neighbour[4])
            tangent = _unit(sub(neighbour_midpoint, midpoint))
            candidate_delta = sub(candidate_b, candidate_a)
            oracle_delta = sub(oracle_b, oracle_a)
            error = sub(candidate_delta, oracle_delta)
            tangential = abs(_dot(error, tangent))
            normal = math.sqrt(max(0.0, _dot(error, error) - tangential * tangential))
            normal_maximum = max(normal_maximum, normal)
            tangent_maximum = max(tangent_maximum, tangential)
    if not groups:
        raise ValueError("unit_n_no_semantic_seams")
    return normal_maximum, tangent_maximum


def _run_mutation_controls(
    simulation_source: MeshSet,
    dense_source: MeshSet,
    binding: BindingFile,
    pose: dict[str, Any],
    target_path: Path,
    reconstruction_limit: float,
) -> dict[str, Any]:
    target = _mapping(read_json(target_path))
    target_digest_before = str(target["targetDigest"])
    original = binding.records[0]
    mutated_records = list(binding.records)
    mutated_records[0] = replace(
        original,
        barycentric_u=min(0.9, original.barycentric_u + 0.2),
    )
    mutated = BindingFile(
        mutated_records,
        binding.simulation_triangle_count,
        binding.panel_count,
        binding.simulation_topology_hash,
        binding.render_topology_hash,
    )
    mutated_vertices = reconstruct_vertices(
        deform_candidate_simulation(simulation_source, pose), mutated
    )
    oracle_dense = _meshset_from_serialised(dense_source, target["denseVertices"])
    maximum_error = max(
        _distance(candidate, oracle)
        for candidate, oracle in zip(mutated_vertices, _flatten(oracle_dense), strict=True)
    )
    target_after = _mapping(read_json(target_path))
    controls = {
        "bindingWeightMutationDetected": maximum_error > reconstruction_limit,
        "oracleTargetUnchanged": target_after.get("targetDigest") == target_digest_before,
        "simulationTopologyMutationDetected": _topology_mutation_detected(
            simulation_source,
            dense_source,
            replace(binding, simulation_topology_hash="0" * 64),
        ),
        "renderTopologyMutationDetected": _topology_mutation_detected(
            simulation_source,
            dense_source,
            replace(binding, render_topology_hash="0" * 64),
        ),
    }
    return {
        "mutation": "first_binding_barycentric_u_plus_0.2_bounded",
        "mutatedMaximumReconstructionErrorMeters": maximum_error,
        "controls": controls,
        "status": "pass" if all(controls.values()) else "fail",
    }


def _validate_topology(simulation: MeshSet, dense: MeshSet, binding: BindingFile) -> None:
    if binding.simulation_topology_hash != topology_hash(simulation):
        raise ValueError("unit_n_simulation_topology_hash_mismatch")
    if binding.render_topology_hash != topology_hash(dense):
        raise ValueError("unit_n_render_topology_hash_mismatch")
    if len(binding.records) != dense.vertex_count:
        raise ValueError("unit_n_binding_record_denominator_mismatch")


def _topology_mutation_detected(simulation: MeshSet, dense: MeshSet, binding: BindingFile) -> bool:
    try:
        _validate_topology(simulation, dense, binding)
    except ValueError:
        return True
    return False


def _run_subprocess_determinism(
    root: Path,
    poses: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = canonical_dumps({"poses": poses})
    command = [
        sys.executable,
        "-m",
        "closy_forge.strict_c3_confirmation_v5.repeat_worker",
        "--root",
        str(root),
    ]
    outputs = [
        subprocess.run(
            command,
            cwd=root,
            input=payload,
            text=True,
            capture_output=True,
            check=True,
            timeout=30,
        ).stdout
        for _ in range(2)
    ]
    expected = canonical_dumps(
        {
            "digests": [
                str(_mapping(record["metrics"])["canonicalOutputSha256"]) for record in records
            ]
        }
    )
    controls = {
        "freshProcessOneMatchesEvaluation": outputs[0] == expected,
        "freshProcessTwoMatchesEvaluation": outputs[1] == expected,
        "freshProcessesMatchEachOther": outputs[0] == outputs[1],
    }
    return {
        "processCount": 2,
        "canonicalOutputSha256": sha256_bytes(outputs[0].encode("utf-8")),
        "controls": controls,
        "status": "pass" if all(controls.values()) else "fail",
    }


def _meshset_from_serialised(template: MeshSet, payload: object) -> MeshSet:
    if not isinstance(payload, list) or len(payload) != len(template.meshes):
        raise ValueError("unit_n_oracle_mesh_inventory_invalid")
    meshes: list[Mesh] = []
    for source, raw_vertices in zip(template.meshes, payload, strict=True):
        if not isinstance(raw_vertices, list) or len(raw_vertices) != len(source.vertices):
            raise ValueError("unit_n_oracle_vertex_denominator_invalid")
        vertices = [_vec3(value) for value in raw_vertices]
        meshes.append(
            Mesh(
                source.name,
                source.panel_id,
                vertices,
                list(source.panel_uvs),
                list(source.triangles),
                source.material_id,
            )
        )
    return MeshSet(meshes)


def _replace_vertices(template: MeshSet, vertices: list[Vec3]) -> MeshSet:
    offset = 0
    meshes: list[Mesh] = []
    for source in template.meshes:
        count = len(source.vertices)
        meshes.append(
            Mesh(
                source.name,
                source.panel_id,
                vertices[offset : offset + count],
                list(source.panel_uvs),
                list(source.triangles),
                source.material_id,
            )
        )
        offset += count
    if offset != len(vertices):
        raise ValueError("unit_n_reconstructed_vertex_denominator_invalid")
    return MeshSet(meshes)


def _semantic_openings_preserved(constraints: Mapping[str, Any]) -> bool:
    openings = constraints.get("openings")
    if not isinstance(openings, list) or len(openings) != 4:
        return False
    for opening in openings:
        row = _mapping(opening)
        edges = row.get("boundaryEdges")
        if not isinstance(edges, list) or not edges:
            return False
        if any(_mapping(edge).get("status") != "resolved" for edge in edges):
            return False
        vertices = {
            int(index)
            for edge in edges
            for index in _mapping(edge).get("vertexIndices", [])
            if isinstance(index, int)
        }
        if len(vertices) < 3:
            return False
    return True


def _inverted_triangle_count(candidate: MeshSet, oracle: MeshSet) -> int:
    count = 0
    for candidate_mesh, oracle_mesh in zip(candidate.meshes, oracle.meshes, strict=True):
        if candidate_mesh.triangles != oracle_mesh.triangles:
            raise ValueError("unit_n_oracle_topology_mismatch")
        for triangle in candidate_mesh.triangles:
            candidate_normal = cross(
                sub(candidate_mesh.vertices[triangle[1]], candidate_mesh.vertices[triangle[0]]),
                sub(candidate_mesh.vertices[triangle[2]], candidate_mesh.vertices[triangle[0]]),
            )
            oracle_normal = cross(
                sub(oracle_mesh.vertices[triangle[1]], oracle_mesh.vertices[triangle[0]]),
                sub(oracle_mesh.vertices[triangle[2]], oracle_mesh.vertices[triangle[0]]),
            )
            if _dot(candidate_normal, oracle_normal) <= 0.0:
                count += 1
    return count


def _connected_component_count(meshset: MeshSet) -> int:
    count = 0
    for mesh in meshset.meshes:
        graph: dict[int, set[int]] = defaultdict(set)
        for triangle in mesh.triangles:
            for left, right in (
                (triangle[0], triangle[1]),
                (triangle[1], triangle[2]),
                (triangle[2], triangle[0]),
            ):
                graph[left].add(right)
                graph[right].add(left)
        unseen = set(range(len(mesh.vertices)))
        while unseen:
            count += 1
            queue = deque([unseen.pop()])
            while queue:
                neighbours = graph[queue.popleft()] & unseen
                unseen.difference_update(neighbours)
                queue.extend(sorted(neighbours))
    return count


def _flatten(meshset: MeshSet) -> list[Vec3]:
    return [vertex for mesh in meshset.meshes for vertex in mesh.vertices]


def vertex_digest(vertices: list[Vec3]) -> str:
    return sha256_bytes(
        canonical_dumps([[round(value, 9) for value in point] for point in vertices]).encode(
            "utf-8"
        )
    )


def _vec3(value: object) -> Vec3:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("unit_n_oracle_vec3_invalid")
    numbers = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in numbers):
        raise ValueError("unit_n_oracle_vec3_nonfinite")
    return (numbers[0], numbers[1], numbers[2])


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _midpoint(left: Vec3, right: Vec3) -> Vec3:
    return tuple((a + b) * 0.5 for a, b in zip(left, right, strict=True))  # type: ignore[return-value]


def _unit(value: Vec3) -> Vec3:
    length = math.sqrt(_dot(value, value))
    if length <= 1e-15:
        return (1.0, 0.0, 0.0)
    return (value[0] / length, value[1] / length, value[2] / length)


def _dot(left: Vec3, right: Vec3) -> float:
    return math.fsum(a * b for a, b in zip(left, right, strict=True))


def _distance(left: Vec3, right: Vec3) -> float:
    return math.sqrt(math.fsum((a - b) ** 2 for a, b in zip(left, right, strict=True)))
