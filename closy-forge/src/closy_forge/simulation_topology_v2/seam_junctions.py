from __future__ import annotations

import math
from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any

from closy_forge.garments.assembly import build_seam_constraints
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.simulation.reference_cloth_solver import flatten_mesh
from closy_forge.simulation.seam_mapping import span_position_flat

SEAM_JUNCTION_MODEL_VERSION = "closy.seam_junction_equivalence.v2"
MAX_SEAM_JUNCTION_VALENCE = 4


def build_seam_constraints_v2(
    pattern: dict[str, Any],
    edge_maps: dict[str, dict[str, list[int]]],
    simulation_mesh: MeshSet,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Rebuild pair constraints and make shared endpoint ownership explicit for topology v2."""

    constraints = deepcopy(build_seam_constraints(pattern, edge_maps))
    equivalence = _build_equivalence_classes(constraints)
    constraints["constraintModel"] = "full_span_seam_mapping_with_junction_equivalence_v3"
    constraints["junctionModelVersion"] = SEAM_JUNCTION_MODEL_VERSION
    constraints["junctionEquivalenceClasses"] = equivalence
    constraints["provenance"] = {
        "simulationTopologyVersion": "closy.simulation_topology.v2",
        "rebuiltForTopologyV2": True,
        "historicalToleranceInflated": False,
    }
    audit = audit_seam_constraints_v2(pattern, constraints, simulation_mesh)
    constraints["auditSummary"] = {
        "auditVersion": audit["auditVersion"],
        "status": audit["status"],
        "failedChecks": audit["failedChecks"],
    }
    if audit["status"] != "pass":
        raise ValueError(f"topology_v2_seam_audit_failed:{','.join(audit['failedChecks'])}")
    return constraints, audit


def audit_seam_constraints_v2(
    pattern: dict[str, Any], constraints: dict[str, Any], simulation_mesh: MeshSet
) -> dict[str, Any]:
    records = list(constraints.get("constraints", []))
    flat = flatten_mesh(simulation_mesh)
    pair_counts: Counter[tuple[str, str]] = Counter()
    pair_ease: dict[tuple[str, str], set[float]] = defaultdict(set)
    partners: dict[str, set[str]] = defaultdict(set)
    participant_incidence: Counter[str] = Counter()
    zero_length_ids: list[str] = []
    for record in records:
        left = _sample_id(record["spanA"])
        right = _sample_id(record["spanB"])
        pair = (left, right) if left < right else (right, left)
        pair_counts[pair] += 1
        pair_ease[pair].add(float(record["restEaseRatio"]))
        partners[left].add(right)
        partners[right].add(left)
        participant_incidence[left] += 1
        participant_incidence[right] += 1
        left_position = span_position_flat(flat.positions, flat.mesh_offsets, record["spanA"])
        right_position = span_position_flat(flat.positions, flat.mesh_offsets, record["spanB"])
        if math.dist(left_position, right_position) <= 1e-12:
            zero_length_ids.append(str(record["id"]))

    opening_edges = {
        str(edge)
        for opening in pattern.get("openings", [])
        for edge in opening.get("boundaryEdges", [])
    }
    sewn_opening_edges = sorted(
        opening_edges
        & {
            str(span["edgeId"])
            for seam in pattern.get("seams", [])
            if seam.get("simulationEnabled", True) is not False
            for span in seam.get("spans", [])
        }
    )
    seam_ease = {
        str(seam["id"]): float(seam["easeRatio"])
        for seam in pattern.get("seams", [])
        if seam.get("simulationEnabled", True) is not False
    }
    inconsistent_ease = sorted(
        str(record["id"])
        for record in records
        if float(record["restEaseRatio"]) != seam_ease.get(str(record["seamId"]))
    )
    equivalence_classes = list(constraints.get("junctionEquivalenceClasses", []))
    equivalent_samples = {
        sample
        for equivalence_class in equivalence_classes
        for sample in equivalence_class.get("sampleIds", [])
    }
    incompatible_many_to_one = sorted(
        sample
        for sample, distinct_partners in partners.items()
        if len(distinct_partners) > 1 and sample not in equivalent_samples
    )
    high_valence = sorted(
        sample
        for sample, incidence in participant_incidence.items()
        if incidence > MAX_SEAM_JUNCTION_VALENCE
    )
    duplicate_pairs = sorted(pair for pair, count in pair_counts.items() if count > 1)
    conflicting_targets = sorted(pair for pair, eases in pair_ease.items() if len(eases) > 1)
    checks = {
        "duplicatePairConstraints": not duplicate_pairs,
        "conflictingTargets": not conflicting_targets,
        "zeroLengthConstraints": not zero_length_ids,
        "incompatibleManyToOneMappings": not incompatible_many_to_one,
        "consistentEasing": not inconsistent_ease,
        "openingEndpointsRemainOpen": not sewn_opening_edges,
        "boundedJunctionValence": not high_valence,
        "explicitMultiwayEquivalence": all(
            int(record["valence"]) == len(record["sampleIds"]) and int(record["valence"]) > 2
            for record in equivalence_classes
        ),
    }
    failed = [key for key, passed in checks.items() if not passed]
    return {
        "schemaVersion": 1,
        "auditVersion": "closy.seam_junction_audit.topology_v2.v1",
        "junctionModelVersion": SEAM_JUNCTION_MODEL_VERSION,
        "constraintCount": len(records),
        "seamCount": len(constraints.get("seams", [])),
        "openingCount": len(constraints.get("openings", [])),
        "multiwayEquivalenceClassCount": len(equivalence_classes),
        "maximumParticipantIncidence": max(participant_incidence.values(), default=0),
        "checks": checks,
        "witnesses": {
            "duplicatePairs": [list(pair) for pair in duplicate_pairs[:8]],
            "conflictingTargets": [list(pair) for pair in conflicting_targets[:8]],
            "zeroLengthConstraintIds": zero_length_ids[:8],
            "incompatibleManyToOneSampleIds": incompatible_many_to_one[:8],
            "inconsistentEaseConstraintIds": inconsistent_ease[:8],
            "sewnOpeningEdgeIds": sewn_opening_edges[:8],
            "highValenceSampleIds": high_valence[:8],
        },
        "failedChecks": failed,
        "status": "pass" if not failed else "fail",
    }


def _build_equivalence_classes(constraints: dict[str, Any]) -> list[dict[str, Any]]:
    parent: dict[str, str] = {}

    def find(value: str) -> str:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    endpoint_samples: set[str] = set()
    for record in constraints.get("constraints", []):
        parameter = float(record.get("mapping", {}).get("parameter", -1.0))
        if parameter not in {0.0, 1.0}:
            continue
        left, right = _sample_id(record["spanA"]), _sample_id(record["spanB"])
        endpoint_samples.update((left, right))
        union(left, right)

    groups: dict[str, set[str]] = defaultdict(set)
    for sample in endpoint_samples:
        groups[find(sample)].add(sample)
    return [
        {
            "id": f"junction.{index:03d}",
            "sampleIds": sorted(samples),
            "valence": len(samples),
            "authority": "exact_boundary_sample_equivalence_no_tolerance_weld",
        }
        for index, samples in enumerate(
            sorted((samples for samples in groups.values() if len(samples) > 2), key=sorted)
        )
    ]


def _sample_id(span: dict[str, Any]) -> str:
    return ":".join(
        (
            str(span["panelId"]),
            str(span["boundaryId"]),
            str(int(span["vertexIndex"])),
            str(int(span["nextVertexIndex"])),
            f"{float(span['interpolationWeight']):.12f}",
        )
    )
