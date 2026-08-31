from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Any

from closy_forge.fitting.exact_d0_candidate import inventory_digest, package_inventory
from closy_forge.geometry.mesh_model import MeshSet, Vec3
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.simulation.reference_cloth_solver import flatten_mesh

LOCK_PATH = Path("fixtures/phy1_seam_support_v3/experiment_lock.json")
LOCK_RAW_SHA256 = "0f943fc60b5a36796e7db800c425d31b586fb2a55a95d0df47ee9cff0a9adc37"
JUNCTION_GRAPH_VERSION = "closy.authored_pattern_corner_junction_graph.v3"
SEAM_METRIC_VERSION = "closy.zero_gap_eased_seam_frame_metrics.v3"
SUPPORT_MODEL_VERSION = "closy.pose_driven_temporary_supports.v3"


@dataclass(frozen=True)
class SpanPoint:
    first: int
    second: int
    second_weight: float
    panel_id: str
    boundary_id: str


@dataclass(frozen=True)
class TemporarySupport:
    support_id: str
    vertex_index: int
    body_region: str
    rest_target: Vec3
    body_local_offset: Vec3


def load_experiment_lock(root: Path) -> dict[str, Any]:
    path = root / LOCK_PATH
    if sha256_file(path) != LOCK_RAW_SHA256:
        raise ValueError("phy1_v3_lock_raw_hash_mismatch")
    lock = read_json(path)
    if lock.get("lockId") != "closy.phy1.seam_support_v3.experiment_lock.v1":
        raise ValueError("phy1_v3_lock_id_invalid")
    integrity = _mapping(lock.get("integrity"))
    expected = {
        "configurationHash": _hash(lock["configuration"]),
        "thresholdHash": _hash(lock["thresholds"]),
        "junctionInventoryHash": _hash(lock["expectedJunctionInventory"]),
    }
    for field, digest in expected.items():
        if integrity.get(field) != digest:
            raise ValueError(f"phy1_v3_lock_{field}_mismatch")
    lock_copy = deepcopy(lock)
    lock_copy["integrity"]["lockHash"] = ""
    if _hash(lock_copy) != integrity.get("lockHash"):
        raise ValueError("phy1_v3_lock_integrity_mismatch")
    payload = {
        "candidateId": lock["candidate"]["candidateId"],
        "candidatePackageDigest": lock["candidate"]["candidatePackageDigest"],
        "patternHash": lock["candidate"]["patternHash"],
        "seamConstraintHash": lock["candidate"]["seamConstraintHash"],
        "simulationTopologyHash": lock["candidate"]["simulationTopologyHash"],
        "simulationRestContentHash": lock["candidate"]["simulationRestContentHash"],
        **expected,
        "avatarContractHash": lock["fixedInputs"]["avatarContractHash"],
        "materialPayloadHash": lock["fixedInputs"]["materialPayloadHash"],
    }
    physical_id = f"physical.candidate.phy1_seam_support_v3.{_hash(payload)[:24]}"
    if integrity.get("physicalCandidateId") != physical_id:
        raise ValueError("phy1_v3_physical_candidate_id_mismatch")
    return dict(lock)


def validate_candidate_package(root: Path, lock: Mapping[str, Any]) -> dict[str, Any]:
    candidate = _mapping(lock.get("candidate"))
    manifest_path = root / str(candidate["candidateManifestPath"])
    package_root = manifest_path.parent
    manifest = read_json(manifest_path)
    inventory = package_inventory(package_root, exclude={"candidate_manifest.json"})
    digest = inventory_digest(inventory)
    checks = {
        "candidateId": manifest.get("candidateId") == candidate.get("candidateId"),
        "packageDigest": digest == candidate.get("candidatePackageDigest"),
        "patternHash": _mapping(manifest.get("identityGraph")).get("patternHash")
        == candidate.get("patternHash"),
        "simulationTopologyHash": _mapping(manifest.get("identityGraph")).get(
            "simulationTopologyHash"
        )
        == candidate.get("simulationTopologyHash"),
        "renderTopologyHash": _mapping(manifest.get("identityGraph")).get("renderTopologyHash")
        == candidate.get("renderTopologyHash"),
        "constraintsFile": sha256_file(package_root / "simulation/constraints.json")
        == candidate.get("seamConstraintHash"),
        "bindingFile": sha256_file(package_root / "binding/sim_to_render.bin")
        == candidate.get("bindingSha256"),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"phy1_v3_candidate_identity_mismatch:{','.join(failed)}")
    return {
        "status": "pass",
        "checks": checks,
        "candidateId": manifest["candidateId"],
        "candidatePackageDigest": digest,
        "inventoryCount": len(inventory),
    }


def build_authored_junction_graph(
    pattern: Mapping[str, Any],
    constraints: Mapping[str, Any],
    topology_manifest: Mapping[str, Any],
    mesh: MeshSet,
    lock: Mapping[str, Any],
) -> dict[str, Any]:
    edge_vertices = _edge_vertex_inventory(topology_manifest)
    offsets = flatten_mesh(mesh).mesh_offsets
    opening_edges = {
        str(edge)
        for opening in pattern.get("openings", [])
        for edge in _mapping(opening).get("boundaryEdges", [])
    }
    parent: dict[str, str] = {}
    participants: dict[str, dict[str, Any]] = {}
    endpoint_pairs: list[tuple[str, str]] = []

    def find(value: str) -> str:
        parent.setdefault(value, value)
        if parent[value] != value:
            parent[value] = find(parent[value])
        return parent[value]

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for raw in constraints.get("constraints", []):
        record = _mapping(raw)
        parameter = float(_mapping(record.get("mapping")).get("parameter", -1.0))
        if parameter not in {0.0, 1.0}:
            continue
        left = _endpoint_participant(_mapping(record["spanA"]), edge_vertices, offsets)
        right = _endpoint_participant(_mapping(record["spanB"]), edge_vertices, offsets)
        for item in (left, right):
            participants[item["participantId"]] = item
            find(item["participantId"])
        endpoint_pairs.append((left["participantId"], right["participantId"]))
        union(left["participantId"], right["participantId"])

    by_authored_corner: dict[tuple[str, int], list[str]] = defaultdict(list)
    for item in participants.values():
        by_authored_corner[(item["panelId"], int(item["localVertexIndex"]))].append(
            item["participantId"]
        )
    for values in by_authored_corner.values():
        ordered = sorted(set(values))
        for value in ordered[1:]:
            union(ordered[0], value)

    groups: dict[str, set[str]] = defaultdict(set)
    for participant_id in participants:
        groups[find(participant_id)].add(participant_id)
    classes: list[dict[str, Any]] = []
    for participant_ids in groups.values():
        if len(participant_ids) <= 2:
            continue
        ordered_ids = sorted(participant_ids)
        class_id = f"junction.{sha256_bytes(chr(10).join(ordered_ids).encode())[:16]}"
        particle_indices = sorted(
            {int(participants[item]["globalVertexIndex"]) for item in ordered_ids}
        )
        spanning_constraints = [
            {
                "constraintId": f"{class_id}.rank.{index:02d}",
                "firstVertexIndex": particle_indices[0],
                "secondVertexIndex": particle,
            }
            for index, particle in enumerate(particle_indices[1:], start=1)
        ]
        classes.append(
            {
                "classId": class_id,
                "participantIds": ordered_ids,
                "participants": [participants[item] for item in ordered_ids],
                "participantIncidence": len(ordered_ids),
                "solverParticleIndices": particle_indices,
                "solverParticleCount": len(particle_indices),
                "solverConstraints": spanning_constraints,
                "constraintRank": len(spanning_constraints),
                "semanticRoles": sorted(
                    {
                        _edge_semantic_role(item["boundaryId"], opening_edges)
                        for item in (participants[value] for value in ordered_ids)
                    }
                ),
            }
        )
    classes.sort(key=lambda item: item["classId"])
    graph = {
        "schemaVersion": 1,
        "graphVersion": JUNCTION_GRAPH_VERSION,
        "authority": "authored_panel_edge_endpoint_equivalence_not_boundary_path_spelling",
        "endpointSeamPairCount": len(endpoint_pairs),
        "participantCount": len(participants),
        "classes": classes,
    }
    graph["audit"] = audit_authored_junction_graph(graph, pattern, lock)
    return graph


def audit_authored_junction_graph(
    graph: Mapping[str, Any], pattern: Mapping[str, Any], lock: Mapping[str, Any]
) -> dict[str, Any]:
    classes = [_mapping(item) for item in graph.get("classes", [])]
    expected = _mapping(lock.get("expectedJunctionInventory"))
    expected_ids = [str(item) for item in expected.get("classIds", [])]
    actual_ids = [str(item.get("classId", "")) for item in classes]
    opening_edges = {
        str(edge)
        for opening in pattern.get("openings", [])
        for edge in _mapping(opening).get("boundaryEdges", [])
    }
    constraint_ids = [
        str(constraint.get("constraintId", ""))
        for item in classes
        for constraint in item.get("solverConstraints", [])
        if isinstance(constraint, Mapping)
    ]
    checks = {
        "nonVacuousExpectedInventory": int(expected.get("requiredMultiwayClassCount", 0)) > 0,
        "expectedClassCount": len(classes) == int(expected.get("requiredMultiwayClassCount", -1)),
        "expectedClassIds": actual_ids == expected_ids,
        "uniqueClassIds": len(actual_ids) == len(set(actual_ids)),
        "participantIncidence": all(
            int(item.get("participantIncidence", 0)) == len(item.get("participants", []))
            and int(item.get("participantIncidence", 0)) > 2
            for item in classes
        ),
        "rankAwareNMinusOne": all(
            int(item.get("constraintRank", -1))
            == max(0, int(item.get("solverParticleCount", 0)) - 1)
            for item in classes
        ),
        "uniqueConstraintIds": len(constraint_ids) == len(set(constraint_ids)),
        "openingEndpointsExcluded": all(
            str(participant.get("boundaryId", "")) not in opening_edges
            for item in classes
            for participant in item.get("participants", [])
            if isinstance(participant, Mapping)
        ),
        "boundedValence": all(
            int(item.get("participantIncidence", 0)) <= int(expected.get("maximumValence", 0))
            for item in classes
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "status": "pass" if not failed else "fail",
        "checks": checks,
        "failedChecks": failed,
        "expectedClassIds": expected_ids,
        "actualClassIds": actual_ids,
        "classCount": len(classes),
        "solverConstraintCount": sum(len(item.get("solverConstraints", [])) for item in classes),
    }


def build_zero_gap_seam_records(
    constraints: Mapping[str, Any], mesh: MeshSet
) -> list[dict[str, Any]]:
    offsets = flatten_mesh(mesh).mesh_offsets
    records: list[dict[str, Any]] = []
    for raw in constraints.get("constraints", []):
        source = _mapping(raw)
        first = _span_point(_mapping(source["spanA"]), offsets)
        second = _span_point(_mapping(source["spanB"]), offsets)
        records.append(
            {
                "constraintId": str(source["id"]),
                "seamId": str(source["seamId"]),
                "first": _span_payload(first),
                "second": _span_payload(second),
                "restNormalGapMeters": 0.0,
                "restBinormalGapMeters": 0.0,
                "restEaseRatio": float(source["restEaseRatio"]),
                "easeDistribution": str(source.get("easeDistribution", "")),
                "mapping": deepcopy(source.get("mapping", {})),
                "authoredSeamAllowanceIsSimulatedGap": False,
            }
        )
    return records


def measure_seams(
    positions: Sequence[Vec3], rest_positions: Sequence[Vec3], records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    measurements: list[dict[str, Any]] = []
    for record in records:
        first = _span_from_payload(_mapping(record["first"]))
        second = _span_from_payload(_mapping(record["second"]))
        a = _weighted(positions[first.first], positions[first.second], first.second_weight)
        b = _weighted(positions[second.first], positions[second.second], second.second_weight)
        rest_a0, rest_a1 = rest_positions[first.first], rest_positions[first.second]
        rest_b0, rest_b1 = rest_positions[second.first], rest_positions[second.second]
        tangent_a = _normalise(_subtract(rest_a1, rest_a0))
        tangent_b = _normalise(_subtract(rest_b1, rest_b0))
        if _dot(tangent_a, tangent_b) < 0.0:
            tangent_b = _scale(tangent_b, -1.0)
        tangent = _normalise(_add(tangent_a, tangent_b))
        delta = _subtract(b, a)
        signed_slip = _dot(delta, tangent)
        perpendicular = _subtract(delta, _scale(tangent, signed_slip))
        crack = _length(perpendicular)
        gap = _length(delta)
        measurements.append(
            {
                "constraintId": record["constraintId"],
                "seamId": record["seamId"],
                "crackMeters": _round(crack),
                "tangentialSlipMeters": _round(abs(signed_slip)),
                "signedTangentialSlipMeters": _round(signed_slip),
                "euclideanGapMeters": _round(gap),
                "arclengthEaseResidual": _round(abs(float(record.get("restEaseRatio", 1.0)) - 1.0)),
            }
        )
    return {
        "metricVersion": SEAM_METRIC_VERSION,
        "constraintCount": len(measurements),
        "maximumSeamCrackMeters": max((item["crackMeters"] for item in measurements), default=0.0),
        "maximumTangentialSlipMeters": max(
            (item["tangentialSlipMeters"] for item in measurements), default=0.0
        ),
        "maximumEuclideanGapMeters": max(
            (item["euclideanGapMeters"] for item in measurements), default=0.0
        ),
        "maximumArclengthEaseResidual": max(
            (item["arclengthEaseResidual"] for item in measurements), default=0.0
        ),
        "authoredSeamAllowanceReportedAsSurfaceGap": False,
        "worstCrackWitnesses": sorted(
            measurements, key=lambda item: (-item["crackMeters"], item["constraintId"])
        )[:8],
        "worstSlipWitnesses": sorted(
            measurements,
            key=lambda item: (-item["tangentialSlipMeters"], item["constraintId"]),
        )[:8],
    }


def seam_frame_microfixture(normal_gap: float, tangential_offset: float) -> dict[str, float]:
    delta = (tangential_offset, normal_gap, 0.0)
    tangent = (1.0, 0.0, 0.0)
    slip = abs(_dot(delta, tangent))
    perpendicular = _subtract(delta, _scale(tangent, _dot(delta, tangent)))
    return {
        "crackMeters": _round(_length(perpendicular)),
        "tangentialSlipMeters": _round(slip),
        "euclideanGapMeters": _round(_length(delta)),
    }


def build_temporary_supports(
    constraints: Mapping[str, Any], mesh: MeshSet, avatar: Mapping[str, Any]
) -> list[TemporarySupport]:
    flat = flatten_mesh(mesh)
    candidates: dict[tuple[str, int], TemporarySupport] = {}
    region_centres = _body_region_centres(avatar)
    for raw in constraints.get("constraints", []):
        record = _mapping(raw)
        seam_id = str(record.get("seamId", ""))
        if seam_id not in {"seam.shoulder.left", "seam.shoulder.right"}:
            continue
        ordinal = int(_mapping(record.get("mapping")).get("ordinal", -1))
        mapping_count = int(_mapping(record.get("mapping")).get("mappingCount", 0))
        if ordinal not in {0, mapping_count - 1}:
            continue
        region = "left_shoulder" if seam_id.endswith("left") else "right_shoulder"
        centre = region_centres[region]
        for key in ("spanA", "spanB"):
            point = _span_point(_mapping(record[key]), flat.mesh_offsets)
            index = point.second if point.second_weight >= 0.5 else point.first
            target = flat.positions[index]
            support = TemporarySupport(
                support_id=f"support.{region}.{index:04d}",
                vertex_index=index,
                body_region=region,
                rest_target=target,
                body_local_offset=_subtract(target, centre),
            )
            candidates[(region, index)] = support
    return sorted(candidates.values(), key=lambda item: item.support_id)


def support_strength(substep: int, lock: Mapping[str, Any]) -> float:
    settings = _mapping(_mapping(lock.get("configuration")).get("supports"))
    full = int(settings["fullStrengthThroughSubstep"])
    start = int(settings["releaseStartsAtSubstep"])
    released = int(settings["fullyReleasedAtSubstep"])
    if substep <= full:
        return 1.0
    if substep < start:
        return 1.0
    if substep >= released:
        return 0.0
    return max(0.0, (released - substep) / max(1, released - start))


def support_target(support: TemporarySupport, avatar: Mapping[str, Any]) -> Vec3:
    centre = _body_region_centres(avatar)[support.body_region]
    return _add(centre, support.body_local_offset)


def audit_support_inventory(
    supports: Sequence[TemporarySupport], lock: Mapping[str, Any]
) -> dict[str, Any]:
    settings = _mapping(_mapping(lock.get("configuration")).get("supports"))
    checks = {
        "nonzero": len(supports) > 0,
        "boundedCount": len(supports) <= int(settings["maximumVertexCount"]),
        "bodyRegionAssociated": all(
            item.body_region in set(settings["bodyRegions"]) for item in supports
        ),
        "uniqueVertexAssociation": len({item.vertex_index for item in supports}) == len(supports),
        "releasedBeforeScoredMotion": int(settings["fullyReleasedAtSubstep"])
        <= int(settings["scoredMotionStartsAfterSubstep"]),
        "wholeNeckBandPinned": False,
        "blanketHighYPinned": False,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "modelVersion": SUPPORT_MODEL_VERSION,
        "status": "pass" if not failed else "fail",
        "checks": checks,
        "failedChecks": failed,
        "supportCount": len(supports),
        "supports": [
            {
                "supportId": item.support_id,
                "vertexIndex": item.vertex_index,
                "bodyRegion": item.body_region,
                "restTarget": [_round(value) for value in item.rest_target],
                "bodyLocalOffset": [_round(value) for value in item.body_local_offset],
            }
            for item in supports
        ],
        "releaseSchedule": {
            "fullStrengthThroughSubstep": settings["fullStrengthThroughSubstep"],
            "releaseStartsAtSubstep": settings["releaseStartsAtSubstep"],
            "fullyReleasedAtSubstep": settings["fullyReleasedAtSubstep"],
        },
    }


def old_support_policy_control(mesh: MeshSet) -> dict[str, Any]:
    old_indices = [
        (mesh_index, vertex_index)
        for mesh_index, panel in enumerate(mesh.meshes)
        for vertex_index, vertex in enumerate(panel.vertices)
        if panel.panel_id == "panel.neck_band" or vertex[1] >= 1.345
    ]
    neck_count = sum(
        len(panel.vertices) for panel in mesh.meshes if panel.panel_id == "panel.neck_band"
    )
    failed_reasons = []
    if neck_count:
        failed_reasons.append("whole_neck_band_support")
    if old_indices:
        failed_reasons.append("blanket_high_y_support")
    return {
        "status": "fail" if failed_reasons else "pass",
        "oldSupportCount": len(old_indices),
        "wholeNeckBandSupportCount": neck_count,
        "failedReasons": failed_reasons,
        "contractRequiresFailure": True,
    }


def _edge_vertex_inventory(
    topology_manifest: Mapping[str, Any],
) -> dict[tuple[str, str], tuple[int, list[int]]]:
    result: dict[tuple[str, str], tuple[int, list[int]]] = {}
    for mesh_index, raw in enumerate(topology_manifest.get("panels", [])):
        panel = _mapping(raw)
        panel_id = str(panel["panelId"])
        provenance = _mapping(panel.get("provenance"))
        boundary = _mapping(provenance.get("boundary"))
        for edge_id, indices in _mapping(boundary.get("edgeVertexIndices")).items():
            result[(panel_id, str(edge_id))] = (
                mesh_index,
                [int(index) for index in indices],
            )
    return result


def _endpoint_participant(
    span: Mapping[str, Any],
    edges: Mapping[tuple[str, str], tuple[int, list[int]]],
    offsets: Sequence[int],
) -> dict[str, Any]:
    panel_id = str(span["panelId"])
    boundary_id = str(span["boundaryId"])
    mesh_index, edge = edges[(panel_id, boundary_id)]
    first = int(span["vertexIndex"])
    second = int(span.get("nextVertexIndex", first))
    weight = float(span.get("interpolationWeight", 0.0))
    vertex = second if weight >= 1.0 - 1e-12 else first
    if vertex == edge[0]:
        endpoint = "start"
    elif vertex == edge[-1]:
        endpoint = "end"
    else:
        endpoint = f"vertex_{vertex}"
    participant_id = f"{panel_id}|{boundary_id}|{endpoint}"
    return {
        "participantId": participant_id,
        "panelId": panel_id,
        "edgeId": boundary_id,
        "boundaryId": boundary_id,
        "endpoint": endpoint,
        "meshIndex": mesh_index,
        "localVertexIndex": vertex,
        "globalVertexIndex": int(offsets[mesh_index]) + vertex,
        "semanticRole": "seam_endpoint",
    }


def _span_point(span: Mapping[str, Any], offsets: Sequence[int]) -> SpanPoint:
    mesh_index = int(span["meshIndex"])
    return SpanPoint(
        first=int(offsets[mesh_index]) + int(span["vertexIndex"]),
        second=int(offsets[mesh_index]) + int(span.get("nextVertexIndex", span["vertexIndex"])),
        second_weight=float(span.get("interpolationWeight", 0.0)),
        panel_id=str(span["panelId"]),
        boundary_id=str(span["boundaryId"]),
    )


def _span_payload(point: SpanPoint) -> dict[str, Any]:
    return {
        "firstVertexIndex": point.first,
        "secondVertexIndex": point.second,
        "secondWeight": point.second_weight,
        "panelId": point.panel_id,
        "boundaryId": point.boundary_id,
    }


def _span_from_payload(payload: Mapping[str, Any]) -> SpanPoint:
    return SpanPoint(
        first=int(payload["firstVertexIndex"]),
        second=int(payload["secondVertexIndex"]),
        second_weight=float(payload["secondWeight"]),
        panel_id=str(payload["panelId"]),
        boundary_id=str(payload["boundaryId"]),
    )


def _body_region_centres(avatar: Mapping[str, Any]) -> dict[str, Vec3]:
    capsules = [
        _mapping(item)
        for item in avatar.get("collisionPrimitives", [])
        if _mapping(item).get("type") == "capsule"
    ]
    fallback = {"left_shoulder": (-0.22, 1.42, 0.0), "right_shoulder": (0.22, 1.42, 0.0)}
    for side in ("left", "right"):
        selected = [item for item in capsules if side in str(item.get("id", "")).lower()]
        if not selected:
            continue
        item = selected[0]
        a = tuple(float(value) for value in item["a"])
        b = tuple(float(value) for value in item["b"])
        fallback[f"{side}_shoulder"] = _scale(_add(a, b), 0.5)  # type: ignore[arg-type]
    return fallback


def _edge_semantic_role(edge_id: str, opening_edges: set[str]) -> str:
    return "opening" if edge_id in opening_edges else "seam"


def _weighted(first: Vec3, second: Vec3, second_weight: float) -> Vec3:
    return _add(_scale(first, 1.0 - second_weight), _scale(second, second_weight))


def _hash(value: object) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _add(first: Vec3, second: Vec3) -> Vec3:
    return (first[0] + second[0], first[1] + second[1], first[2] + second[2])


def _subtract(first: Vec3, second: Vec3) -> Vec3:
    return (first[0] - second[0], first[1] - second[1], first[2] - second[2])


def _scale(value: Vec3, factor: float) -> Vec3:
    return (value[0] * factor, value[1] * factor, value[2] * factor)


def _dot(first: Vec3, second: Vec3) -> float:
    return first[0] * second[0] + first[1] * second[1] + first[2] * second[2]


def _length(value: Vec3) -> float:
    return sqrt(_dot(value, value))


def _normalise(value: Vec3) -> Vec3:
    length = _length(value)
    return (1.0, 0.0, 0.0) if length <= 1e-12 else _scale(value, 1.0 / length)


def _round(value: float) -> float:
    return round(float(value), 12)
