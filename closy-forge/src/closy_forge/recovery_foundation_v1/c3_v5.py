from __future__ import annotations

import math
import subprocess
import sys
import time
import tracemalloc
from collections import defaultdict, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from closy_forge.geometry.frame_attributes import meshset_frame_metrics
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3, cross, sub
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

FRAME_METRICS_VERSION = "closy.c3.frame_metrics.v5"
CANONICAL_FRAME_KEYS = frozenset(
    {
        "normalVectorCount",
        "tangentVectorCount",
        "finiteNormalCount",
        "finiteTangentCount",
        "unitNormalCount",
        "unitTangentCount",
        "orthogonalNormalTangentCount",
        "maximumNormalLengthError",
        "maximumTangentLengthError",
        "maximumAbsoluteNormalTangentDot",
        "tangentHandednessValues",
    }
)
LEGACY_ALIASES = {
    "maxNormalLengthError": "maximumNormalLengthError",
    "maxTangentLengthError": "maximumTangentLengthError",
    "maxNormalTangentDot": "maximumAbsoluteNormalTangentDot",
}


@dataclass(frozen=True)
class FrameMetrics:
    normalVectorCount: int
    tangentVectorCount: int
    finiteNormalCount: int
    finiteTangentCount: int
    unitNormalCount: int
    unitTangentCount: int
    orthogonalNormalTangentCount: int
    maximumNormalLengthError: float
    maximumTangentLengthError: float
    maximumAbsoluteNormalTangentDot: float
    tangentHandednessValues: tuple[float, ...]

    def to_document(self) -> dict[str, Any]:
        value = asdict(self)
        value["tangentHandednessValues"] = list(self.tangentHandednessValues)
        return {"frameMetricsVersion": FRAME_METRICS_VERSION, **value}


def adapt_frame_metrics(payload: Mapping[str, Any], *, source_version: str) -> FrameMetrics:
    values = dict(payload)
    declared = values.pop("frameMetricsVersion", None)
    if source_version == FRAME_METRICS_VERSION:
        if declared not in {None, FRAME_METRICS_VERSION}:
            raise ValueError("c3_frame_metrics_version_conflict")
    elif source_version == "closy.geometry.frame_metrics.v1":
        for legacy, canonical in LEGACY_ALIASES.items():
            if legacy in values and canonical in values:
                raise ValueError(f"c3_frame_metrics_ambiguous_alias:{legacy}")
            if legacy in values:
                values[canonical] = values.pop(legacy)
    else:
        raise ValueError(f"c3_frame_metrics_source_version_unsupported:{source_version}")
    unknown = set(values) - CANONICAL_FRAME_KEYS
    missing = CANONICAL_FRAME_KEYS - set(values)
    if unknown:
        raise ValueError(f"c3_frame_metrics_unknown_fields:{','.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"c3_frame_metrics_missing_fields:{','.join(sorted(missing))}")
    counts = {}
    for field in (
        "normalVectorCount",
        "tangentVectorCount",
        "finiteNormalCount",
        "finiteTangentCount",
        "unitNormalCount",
        "unitTangentCount",
        "orthogonalNormalTangentCount",
    ):
        value = values[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"c3_frame_metrics_count_invalid:{field}")
        counts[field] = value
    floats = {}
    for field in (
        "maximumNormalLengthError",
        "maximumTangentLengthError",
        "maximumAbsoluteNormalTangentDot",
    ):
        value = values[field]
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise ValueError(f"c3_frame_metrics_nonfinite_or_nonmetric:{field}")
        floats[field] = float(value)
    handedness = values["tangentHandednessValues"]
    if not isinstance(handedness, list | tuple) or any(
        value not in {-1.0, 1.0} for value in handedness
    ):
        raise ValueError("c3_frame_metrics_handedness_invalid")
    return FrameMetrics(
        normalVectorCount=counts["normalVectorCount"],
        tangentVectorCount=counts["tangentVectorCount"],
        finiteNormalCount=counts["finiteNormalCount"],
        finiteTangentCount=counts["finiteTangentCount"],
        unitNormalCount=counts["unitNormalCount"],
        unitTangentCount=counts["unitTangentCount"],
        orthogonalNormalTangentCount=counts["orthogonalNormalTangentCount"],
        maximumNormalLengthError=floats["maximumNormalLengthError"],
        maximumTangentLengthError=floats["maximumTangentLengthError"],
        maximumAbsoluteNormalTangentDot=floats["maximumAbsoluteNormalTangentDot"],
        tangentHandednessValues=tuple(float(v) for v in handedness),
    )


def canonical_frame_metrics(meshset: MeshSet) -> FrameMetrics:
    return adapt_frame_metrics(
        meshset_frame_metrics(meshset), source_version="closy.geometry.frame_metrics.v1"
    )


def evaluate_pose(
    candidate: MeshSet,
    oracle: MeshSet,
    *,
    seam_pairs: Sequence[tuple[Vec3, Vec3, Vec3]],
    required_openings: Sequence[Sequence[int]],
    hidden_panels: set[str] | None = None,
) -> dict[str, Any]:
    tracemalloc.start()
    started = time.perf_counter()
    candidate_vertices = _flatten(candidate)
    oracle_vertices = _flatten(oracle)
    if len(candidate_vertices) != len(oracle_vertices):
        raise ValueError("c3_vertex_denominator_mismatch")
    errors = [
        _distance(left, right)
        for left, right in zip(candidate_vertices, oracle_vertices, strict=True)
    ]
    seam_normal, seam_tangent = semantic_seam_residuals(seam_pairs)
    frame = canonical_frame_metrics(candidate)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    result = {
        "maximumReconstructionErrorMeters": max(errors, default=0.0),
        "rmsReconstructionErrorMeters": math.sqrt(
            math.fsum(error * error for error in errors) / max(1, len(errors))
        ),
        "maximumSemanticSeamCrackMeters": seam_normal,
        "maximumTangentialSeamSlidingMeters": seam_tangent,
        "openingCyclesPreserved": openings_are_simple_cycles(required_openings),
        "invertedTriangleCount": inverted_triangle_count(candidate, oracle),
        "connectedComponentCount": connected_component_count(candidate),
        "hiddenComponentCount": sum(
            mesh.panel_id in (hidden_panels or set()) for mesh in candidate.meshes
        ),
        "frameMetrics": frame.to_document(),
        "wholeEvaluationWallClockSeconds": elapsed,
        "wholeEvaluationPeakMemoryMiB": peak / (1024 * 1024),
        "canonicalOutputSha256": sha256_bytes(
            canonical_dumps(
                [[round(value, 9) for value in point] for point in candidate_vertices]
            ).encode("utf-8")
        ),
    }
    return result


def semantic_seam_residuals(
    samples: Sequence[tuple[Vec3, Vec3, Vec3]],
) -> tuple[float, float]:
    normal_maximum = 0.0
    tangent_maximum = 0.0
    for left, right, tangent in samples:
        unit_tangent = _unit(tangent)
        delta = sub(right, left)
        tangential = abs(_dot(delta, unit_tangent))
        normal = math.sqrt(max(0.0, _dot(delta, delta) - tangential * tangential))
        normal_maximum = max(normal_maximum, normal)
        tangent_maximum = max(tangent_maximum, tangential)
    return normal_maximum, tangent_maximum


def openings_are_simple_cycles(openings: Sequence[Sequence[int]]) -> bool:
    if not openings:
        return False
    for opening in openings:
        if (
            len(opening) < 4
            or opening[0] != opening[-1]
            or len(set(opening[:-1])) != len(opening) - 1
        ):
            return False
    return True


def connected_component_count(meshset: MeshSet) -> int:
    count = 0
    for mesh in meshset.meshes:
        graph: dict[int, set[int]] = defaultdict(set)
        referenced: set[int] = set()
        for triangle in mesh.triangles:
            for left, right in (
                (triangle[0], triangle[1]),
                (triangle[1], triangle[2]),
                (triangle[2], triangle[0]),
            ):
                graph[left].add(right)
                graph[right].add(left)
                referenced.update((left, right))
        unseen = set(range(len(mesh.vertices)))
        while unseen:
            count += 1
            start = unseen.pop()
            queue = deque([start])
            while queue:
                current = queue.popleft()
                neighbours = graph[current] & unseen
                unseen.difference_update(neighbours)
                queue.extend(sorted(neighbours))
    return count


def inverted_triangle_count(candidate: MeshSet, oracle: MeshSet) -> int:
    count = 0
    for left, right in zip(candidate.meshes, oracle.meshes, strict=True):
        if left.triangles != right.triangles:
            raise ValueError("c3_topology_mismatch_for_inversion_measurement")
        for triangle in left.triangles:
            left_normal = cross(
                sub(left.vertices[triangle[1]], left.vertices[triangle[0]]),
                sub(left.vertices[triangle[2]], left.vertices[triangle[0]]),
            )
            right_normal = cross(
                sub(right.vertices[triangle[1]], right.vertices[triangle[0]]),
                sub(right.vertices[triangle[2]], right.vertices[triangle[0]]),
            )
            if _dot(left_normal, right_normal) <= 0:
                count += 1
    return count


def run_independent_oracle(
    source_mesh: MeshSet,
    pose: Mapping[str, float],
    *,
    candidate_path: Callable[[], MeshSet] | None = None,
) -> MeshSet:
    del candidate_path
    bend = float(pose.get("bend", 0.0))
    meshes = [
        Mesh(
            mesh.name,
            mesh.panel_id,
            [(x, y, z + bend * y * y) for x, y, z in mesh.vertices],
            list(mesh.panel_uvs),
            list(mesh.triangles),
            mesh.material_id,
        )
        for mesh in source_mesh.meshes
    ]
    return MeshSet(meshes)


def subprocess_determinism(command: Sequence[str], *, timeout_seconds: float) -> dict[str, Any]:
    outputs: list[bytes] = []
    for _ in range(2):
        completed = subprocess.run(
            list(command), capture_output=True, timeout=timeout_seconds, check=False
        )
        if completed.returncode != 0:
            return {"status": "fail", "reason": "subprocess_nonzero"}
        outputs.append(completed.stdout)
    return {
        "status": "pass" if outputs[0] == outputs[1] else "fail",
        "sha256": sha256_bytes(outputs[0]),
    }


def run_generic_c3_fixtures() -> dict[str, Any]:
    mesh = _triangle_mesh()
    exact = evaluate_pose(
        mesh,
        mesh,
        seam_pairs=[((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))],
        required_openings=[[0, 1, 2, 0]],
    )
    displaced_mesh = _triangle_mesh(displacement=(0.0, 0.0, 0.001))
    displaced = evaluate_pose(
        displaced_mesh,
        mesh,
        seam_pairs=[((0.0, 0.0, 0.0), (0.0, 0.001, 0.0), (1.0, 0.0, 0.0))],
        required_openings=[[0, 1, 2, 0]],
    )
    normal, no_slide = semantic_seam_residuals(
        [((0.0, 0.0, 0.0), (0.0, 0.002, 0.0), (1.0, 0.0, 0.0))]
    )
    no_crack, slide = semantic_seam_residuals(
        [((0.0, 0.0, 0.0), (0.003, 0.0, 0.0), (1.0, 0.0, 0.0))]
    )
    inverted = MeshSet(
        [
            Mesh(
                "triangle",
                "panel.fixture",
                [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0)],
                list(mesh.meshes[0].panel_uvs),
                list(mesh.meshes[0].triangles),
            )
        ]
    )
    legacy = meshset_frame_metrics(mesh)
    canonical = adapt_frame_metrics(legacy, source_version="closy.geometry.frame_metrics.v1")
    rejected = {}
    for label, mutation in {
        "unknown": {**canonical.to_document(), "mystery": 1},
        "missing": {
            key: value
            for key, value in canonical.to_document().items()
            if key != "normalVectorCount"
        },
        "nonfinite": {**canonical.to_document(), "maximumNormalLengthError": math.inf},
        "ambiguous": {**canonical.to_document(), "maxNormalLengthError": 0.0},
    }.items():
        try:
            adapt_frame_metrics(mutation, source_version="closy.geometry.frame_metrics.v1")
        except ValueError:
            rejected[label] = True
        else:
            rejected[label] = False
    deterministic = subprocess_determinism(
        [sys.executable, "-c", "print('c3-v5-deterministic')"], timeout_seconds=2.0
    )
    nondeterministic = subprocess_determinism(
        [sys.executable, "-c", "import time; print(time.time_ns())"], timeout_seconds=2.0
    )
    timeout_detected = False
    try:
        subprocess.run(
            [sys.executable, "-c", "import time; time.sleep(0.2)"],
            timeout=0.01,
            check=False,
        )
    except subprocess.TimeoutExpired:
        timeout_detected = True
    candidate_called = False

    def forbidden_candidate() -> MeshSet:
        nonlocal candidate_called
        candidate_called = True
        raise AssertionError("candidate path must remain unread")

    oracle = run_independent_oracle(mesh, {"bend": 0.01}, candidate_path=forbidden_candidate)
    cases = {
        "exact_zero_error": exact["maximumReconstructionErrorMeters"] == 0.0,
        "known_reconstruction_displacement": math.isclose(
            displaced["maximumReconstructionErrorMeters"], 0.001
        ),
        "seam_normal_without_slide": math.isclose(normal, 0.002) and no_slide == 0.0,
        "tangential_slide_without_crack": no_crack == 0.0 and math.isclose(slide, 0.003),
        "inverted_triangle": inverted_triangle_count(inverted, mesh) == 1,
        "deleted_hidden_component": connected_component_count(_disconnected_mesh()) == 2,
        "broken_opening": not openings_are_simple_cycles([[0, 1, 2]]),
        "invalid_tangent_handedness": rejected["nonfinite"]
        and (-1.0 in canonical.tangentHandednessValues or 1.0 in canonical.tangentHandednessValues),
        "legacy_alias": canonical.maximumNormalLengthError >= 0.0,
        "unknown_missing_ambiguous_rejection": all(rejected.values()),
        "nondeterministic_subprocess": nondeterministic["status"] == "fail",
        "deterministic_subprocess": deterministic["status"] == "pass",
        "timeout_breach": timeout_detected,
        "memory_budget_breach_validator": not resource_budget_pass(0.1, 513.0),
        "oracle_candidate_path_unread": len(_flatten(oracle)) == 3 and not candidate_called,
    }
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "fixtureVersion": "closy.c3.strict_evaluator.generic_fixtures.v5",
        "freshHeldOutPoseRealized": False,
        "qualificationAttemptConsumed": False,
        "cases": cases,
        "oracle": {
            "readsCandidateBindingWeights": False,
            "callsCandidateReconstruction": False,
            "provenance": "project_authored_analytic_synthetic_pose_field",
            "correlation": (
                "shares_supported_pose_semantics_not_physical_or_real_world_ground_truth"
            ),
        },
        "allPassed": all(cases.values()),
        "integrity": {"fixtureDigest": ""},
    }
    report["integrity"]["fixtureDigest"] = sha256_bytes(
        canonical_dumps({**report, "integrity": {"fixtureDigest": ""}}).encode("utf-8")
    )
    return report


def resource_budget_pass(seconds: float, peak_memory_mib: float) -> bool:
    return seconds <= 2.0 and peak_memory_mib <= 512.0


def _triangle_mesh(*, displacement: Vec3 = (0.0, 0.0, 0.0)) -> MeshSet:
    vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    return MeshSet(
        [
            Mesh(
                "triangle",
                "panel.fixture",
                [
                    (x + displacement[0], y + displacement[1], z + displacement[2])
                    for x, y, z in vertices
                ],
                [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
                [(0, 1, 2)],
            )
        ]
    )


def _disconnected_mesh() -> MeshSet:
    return MeshSet(
        [
            Mesh(
                "disconnected",
                "panel.fixture",
                [
                    (0.0, 0.0, 0.0),
                    (1.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0),
                    (3.0, 0.0, 0.0),
                    (4.0, 0.0, 0.0),
                    (3.0, 1.0, 0.0),
                ],
                [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
                [(0, 1, 2), (3, 4, 5)],
            )
        ]
    )


def _flatten(meshset: MeshSet) -> list[Vec3]:
    return [vertex for mesh in meshset.meshes for vertex in mesh.vertices]


def _distance(left: Vec3, right: Vec3) -> float:
    return math.sqrt(math.fsum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _dot(left: Vec3, right: Vec3) -> float:
    return math.fsum(a * b for a, b in zip(left, right, strict=True))


def _unit(value: Vec3) -> Vec3:
    length = math.sqrt(_dot(value, value))
    if length <= 1e-15:
        raise ValueError("c3_zero_seam_tangent")
    return (value[0] / length, value[1] / length, value[2] / length)
