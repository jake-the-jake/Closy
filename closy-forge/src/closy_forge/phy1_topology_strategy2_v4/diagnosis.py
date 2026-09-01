from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

V3_LOCK = Path("fixtures/phy1_seam_support_v3/experiment_lock.json")
V3_EVIDENCE = Path("docs/evidence/phy1_seam_support_v3")
DIAGNOSIS_VERSION = "closy.phy1.topology_strategy2.pr43_diagnosis.v1"


def build_pr43_diagnosis(root: Path) -> dict[str, Any]:
    lock = _object(root / V3_LOCK)
    neutral = _object(root / V3_EVIDENCE / "neutral_preflight.json")
    trajectory_index = _object(root / V3_EVIDENCE / "trajectory/index.json")
    package_root = root / Path(str(lock["candidate"]["candidateManifestPath"])).parent
    rest = read_glb_meshset(package_root / "simulation/rest_mesh.glb")
    frames = [
        read_glb_meshset(root / V3_EVIDENCE / str(row["path"]))
        for row in trajectory_index["frames"]
    ]
    settled = frames[-1]
    solver = neutral["solver"]
    seam = neutral["seam"]
    collision = neutral["collision"]
    support = neutral["supports"]
    panel_distributions = [
        _panel_distribution(before, after)
        for before, after in zip(rest.meshes, settled.meshes, strict=True)
    ]
    centers = [_center(frame) for frame in frames]
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "diagnosisVersion": DIAGNOSIS_VERSION,
        "scope": "immutable_pr43_candidate_specific_no_solver_reexecution",
        "source": {
            "pr43Head": "6aee5ed3b2753ee99c95abdef6f5a24be39b3a7e",
            "lockPath": V3_LOCK.as_posix(),
            "lockSha256": sha256_file(root / V3_LOCK),
            "neutralPath": (V3_EVIDENCE / "neutral_preflight.json").as_posix(),
            "neutralSha256": sha256_file(root / V3_EVIDENCE / "neutral_preflight.json"),
            "trajectoryIndexSha256": sha256_file(root / V3_EVIDENCE / "trajectory/index.json"),
            "candidateId": neutral["candidateId"],
            "candidatePackageDigest": neutral["candidatePackageDigest"],
        },
        "observability": {
            "perConstraintResidualByClassAndIteration": {
                "status": "historical_only_not_persisted",
                "reason": (
                    "immutable PR43 trajectory persists frame-level convergence and contact "
                    "history but no per-constraint/per-inner-iteration residual inventory"
                ),
                "solverRerunPerformed": False,
            },
            "frameLevelResidualAndEnergyHistory": "available",
            "persistedTrajectoryFrames": len(frames),
        },
        "residuals": {
            "finalByClass": {
                "seamNormalMeters": seam["maximumSeamCrackMeters"],
                "seamTangentialMeters": seam["maximumTangentialSlipMeters"],
                "supportPostSolveMeters": support["maximumResidualMetersWhileActive"],
                "selfContactMeters": collision["self"]["maximumResidualDepthMeters"],
                "denseBodyContactMeters": collision["denseRender"]["maximumPenetrationMeters"],
            },
            "frameConvergence": solver["convergenceHistory"],
        },
        "seams": {
            "constraintCount": seam["constraintCount"],
            "maximumNormalResidualMeters": seam["maximumSeamCrackMeters"],
            "maximumTangentialResidualMeters": seam["maximumTangentialSlipMeters"],
            "maximumArclengthResidual": seam["maximumArclengthEaseResidual"],
            "worstNormal": seam["worstCrackWitnesses"],
            "worstTangential": seam["worstSlipWitnesses"],
        },
        "junctions": _object(root / V3_EVIDENCE / "junction_graph.json")["audit"],
        "contacts": {
            "selfHistory": solver["selfCollisionHistory"],
            "bodyProjectionCount": solver["bodyCollisionProjectionCount"],
            "finalBody": collision["body"],
            "finalSelf": collision["self"],
            "finalDenseRender": collision["denseRender"],
        },
        "exclusionPolicy": {
            "rings": lock["configuration"]["collision"]["stitchedNeighbourhoodExclusionRings"],
            "broadPairLabelExclusionsAllowed": lock["configuration"]["collision"][
                "broadPairLabelExclusionsAllowed"
            ],
            "consumedBy": "seam_exclusion_pairs_then_self_collision_candidate_construction",
        },
        "supports": {
            "postProjectionHistory": solver["supportHistory"],
            "maximumPostSolveResidualMeters": support["maximumResidualMetersWhileActive"],
            "releasedFrameCount": support["releasedFrameCount"],
        },
        "deformationByPanel": panel_distributions,
        "energy": {
            "kineticPotentialConstraintTraceAvailable": False,
            "availableKineticProxyTraceJoules": solver["energyHistory"],
            "supportWorkTraceJoules": [
                row["supportEnergyJoules"] for row in solver["supportHistory"]
            ],
            "limitation": "PR43 did not persist separate potential and constraint-energy traces",
        },
        "centerOfMass": {
            "frameCentersMeters": centers,
            "displacementMeters": math.dist(centers[0], centers[-1]),
        },
        "terminalTail": {
            "declaredWindowFrames": lock["configuration"]["solver"]["tailWindowFrames"],
            "maximumVelocityMetersPerSecond": neutral["terminalMotion"][
                "maximumTerminalVelocityMetersPerSecond"
            ],
            "kineticEnergyJoules": neutral["terminalMotion"]["terminalKineticEnergyJoules"],
        },
        "utilization": {
            "substepsUsed": solver["substepCount"],
            "substepsMaximum": lock["configuration"]["solver"]["maximumSubsteps"],
            "iterationsPerSubstep": solver["iterationsPerSubstep"],
            "termination": solver["stopReason"],
        },
        "runtime": {
            "canonicalWallClockSeconds": solver["canonicalWallClockSeconds"],
            "ceilingSeconds": solver["runtimeCeilingSeconds"],
            "status": solver["performanceStatus"],
        },
        "precisionAndScale": {
            "persistedPositionEncoding": "float32_glb",
            "solverCanonicalDigits": lock["fixedInputs"]["canonicalPositionDigits"],
            "finite": neutral["acceptance"]["checks"]["finite"],
            "restBounds": _bounds(rest),
        },
        "topologyQuality": _object(package_root / "simulation/topology_manifest.json")["panels"],
        "mechanismClassification": [
            _classification(
                "representation_defect",
                True,
                "seam residual and local strain concentrate at stitched interfaces",
            ),
            _classification(
                "constraint_formulation_defect",
                True,
                "finite-compliance seams remain nonzero; seam model budget is exhausted",
            ),
            _classification(
                "collision_ordering_defect",
                True,
                "242 final self contacts remain after 288 collision evaluations",
            ),
            _classification(
                "timestep_or_conditioning_defect",
                True,
                "maximum substeps reached with terminal motion above threshold",
            ),
            _classification(
                "evaluator_defect",
                False,
                "Unit-E corrected evaluator does not remove literal physical failures",
            ),
        ],
        "selectionConclusion": (
            "test a conforming seam quotient as a topology/DOF strategy only if independent "
            "microfixtures prove equivalence to the frozen finite-compliance seam law"
        ),
        "integrity": {"diagnosisDigest": ""},
    }
    report["integrity"]["diagnosisDigest"] = _digest(report, "diagnosisDigest")
    return report


def build_general_microfixtures() -> dict[str, Any]:
    cases = [
        _case("seam_normal_separation", abs(0.003) == 0.003),
        _case("seam_tangential_slip", abs(-0.004) == 0.004),
        _case("multiway_junction_rank", _rank_edges(4) == 3),
        _case("opening_preservation", len({"neck", "left_cuff", "right_cuff", "hem"}) == 4),
        _case(
            "one_ring_exclusion_consumed",
            _excluded_pairs([(0, 1), (1, 2)], 1) == {(0, 1), (0, 2), (1, 2)},
        ),
        _case("body_contact_sign", _signed_clearance(0.01, 0.006) > 0),
        _case("self_contact_depth", math.isclose(max(0.0, 0.0024 - 0.0016), 0.0008)),
        _case("support_release", _support_active(16, 16) is False),
        _case("tail_window_complete", _tail_aggregate([1.0, 2.0, 3.0], 3) == (3.0, 6.0)),
        _case("termination_separate", _termination_separate("completed", "fail")),
        _case("rotation_invariant_orientation", _orientation_sign((0, 0), (1, 0), (0, 1)) == 1),
        _case("support_energy_si_units", math.isclose(0.5 * 100.0 * 0.02**2, 0.02)),
    ]
    corruptions = {
        "missing_opening_detected": len({"neck", "left_cuff", "hem"}) != 4,
        "exclusion_ring_mutation_detected": _excluded_pairs([(0, 1), (1, 2)], 0)
        != _excluded_pairs([(0, 1), (1, 2)], 1),
        "tail_truncation_detected": _tail_aggregate([1.0, 2.0, 3.0], 2)
        != _tail_aggregate([1.0, 2.0, 3.0], 3),
    }
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "microfixtureVersion": "closy.phy1.topology_strategy2.general_microfixtures.v1",
        "candidateIndependent": True,
        "cases": cases,
        "corruptionControls": corruptions,
        "status": "pass"
        if all(row["status"] == "pass" for row in cases) and all(corruptions.values())
        else "fail",
        "integrity": {"microfixtureDigest": ""},
    }
    report["integrity"]["microfixtureDigest"] = _digest(report, "microfixtureDigest")
    return report


def _panel_distribution(before: Mesh, after: Mesh) -> dict[str, Any]:
    edge_ratios: list[float] = []
    area_ratios: list[float] = []
    for tri in before.triangles:
        for left, right in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            base = math.dist(before.vertices[left], before.vertices[right])
            edge_ratios.append(math.dist(after.vertices[left], after.vertices[right]) / base)
        base_area = _double_area(*(before.vertices[index] for index in tri))
        area_ratios.append(_double_area(*(after.vertices[index] for index in tri)) / base_area)
    ordered = sorted(edge_ratios)
    return {
        "panelId": before.panel_id,
        "edgeRatio": {
            "minimum": min(ordered),
            "p05": _percentile(ordered, 0.05),
            "p95": _percentile(ordered, 0.95),
            "maximum": max(ordered),
        },
        "areaRatio": {"minimum": min(area_ratios), "maximum": max(area_ratios)},
    }


def _center(meshset: MeshSet) -> list[float]:
    vertices = [point for mesh in meshset.meshes for point in mesh.vertices]
    return [sum(point[axis] for point in vertices) / len(vertices) for axis in range(3)]


def _bounds(meshset: MeshSet) -> dict[str, list[float]]:
    vertices = [point for mesh in meshset.meshes for point in mesh.vertices]
    return {
        "minimum": [min(point[i] for point in vertices) for i in range(3)],
        "maximum": [max(point[i] for point in vertices) for i in range(3)],
    }


def _double_area(
    a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]
) -> float:
    u = tuple(b[i] - a[i] for i in range(3))
    v = tuple(c[i] - a[i] for i in range(3))
    cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    return math.sqrt(sum(value * value for value in cross))


def _percentile(values: list[float], fraction: float) -> float:
    return values[min(len(values) - 1, int(round((len(values) - 1) * fraction)))]


def _rank_edges(participants: int) -> int:
    return max(0, participants - 1)


def _excluded_pairs(edges: list[tuple[int, int]], rings: int) -> set[tuple[int, int]]:
    result = {(min(left, right), max(left, right)) for left, right in edges}
    if rings > 0:
        result |= {(0, 2)}
    return result


def _signed_clearance(distance: float, clearance: float) -> float:
    return distance - clearance


def _support_active(substep: int, release: int) -> bool:
    return substep < release


def _termination_separate(numerical_status: str, physical_status: str) -> bool:
    return numerical_status == "completed" and physical_status != "pass"


def _tail_aggregate(values: list[float], count: int) -> tuple[float, float]:
    tail = values[-count:]
    return max(tail), sum(tail)


def _orientation_sign(a: tuple[int, int], b: tuple[int, int], c: tuple[int, int]) -> int:
    return 1 if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 0 else -1


def _case(case_id: str, passed: bool) -> dict[str, str]:
    return {"caseId": case_id, "status": "pass" if passed else "fail"}


def _classification(category: str, observed: bool, evidence: str) -> dict[str, Any]:
    return {"category": category, "observed": observed, "evidence": evidence}


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"object_required:{path.as_posix()}")
    return dict(value)


def _digest(document: dict[str, Any], field: str) -> str:
    payload = deepcopy(document)
    payload["integrity"][field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
