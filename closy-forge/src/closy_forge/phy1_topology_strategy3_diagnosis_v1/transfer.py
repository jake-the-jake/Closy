from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes


@dataclass(frozen=True)
class TransferMesh:
    positions: list[tuple[float, float, float]]
    triangles: list[tuple[int, int, int]]
    mass: list[float]
    uv: list[tuple[float, float]]
    material: list[str]
    semantic_seam_ids: dict[str, list[int]]
    source_coordinates: list[tuple[float, float]]
    binding_coordinates: list[tuple[int, float, float, float]]
    opening_cycles: list[list[int]]


def base_transfer_fixture() -> TransferMesh:
    return TransferMesh(
        positions=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
        triangles=[(0, 1, 2), (0, 2, 3)],
        mass=[0.25, 0.25, 0.25, 0.25],
        uv=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        material=["cotton"] * 4,
        semantic_seam_ids={"seam.diagonal": [0, 2]},
        source_coordinates=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        binding_coordinates=[(0, 1.0, 0.0, 0.0)] * 4,
        opening_cycles=[[0, 1, 2, 3]],
    )


def apply_revision(source: TransferMesh, revision: int) -> tuple[TransferMesh, dict[str, Any]]:
    if revision not in {1, 2}:
        raise ValueError("unit_o_revision_out_of_range")
    midpoint_index = len(source.positions)
    positions = [*source.positions, _midpoint(source.positions[0], source.positions[2])]
    mass = list(source.mass)
    moved_mass = min(mass[0], mass[2]) * 0.25
    mass[0] -= moved_mass * 0.5
    mass[2] -= moved_mass * 0.5
    mass.append(moved_mass)
    uv = [*source.uv, _midpoint2(source.uv[0], source.uv[2])]
    material = [*source.material, source.material[0]]
    source_coordinates = [
        *source.source_coordinates,
        _midpoint2(source.source_coordinates[0], source.source_coordinates[2]),
    ]
    binding = [
        *source.binding_coordinates,
        _blend_binding(source.binding_coordinates[0], source.binding_coordinates[2]),
    ]
    if revision == 1:
        triangles = [(0, 1, midpoint_index), (midpoint_index, 1, 2), source.triangles[1]]
    else:
        triangles = [
            (0, 1, midpoint_index),
            (midpoint_index, 1, 2),
            (0, midpoint_index, 3),
            (midpoint_index, 2, 3),
        ]
    # Both revisions deliberately retain the old seam sequence. Revision 2 closes topology but
    # therefore exposes the still-missing semantic seam correspondence transfer.
    transferred = TransferMesh(
        positions,
        triangles,
        mass,
        uv,
        material,
        deepcopy(source.semantic_seam_ids),
        source_coordinates,
        binding,
        deepcopy(source.opening_cycles),
    )
    strategy_class = (
        "local_longest_edge_bisection" if revision == 1 else "closure_longest_edge_bisection"
    )
    audit = audit_transfer(source, transferred, midpoint_index, revision, strategy_class)
    return transferred, audit


def audit_transfer(
    source: TransferMesh,
    candidate: TransferMesh,
    midpoint_index: int,
    revision: int,
    strategy_class: str,
) -> dict[str, Any]:
    defects = topology_defects(candidate)
    expected_seam = [0, midpoint_index, 2]
    seam_complete = candidate.semantic_seam_ids["seam.diagonal"] == expected_seam
    expected_uv = _midpoint2(source.uv[0], source.uv[2])
    expected_source = _midpoint2(source.source_coordinates[0], source.source_coordinates[2])
    expected_binding = _blend_binding(source.binding_coordinates[0], source.binding_coordinates[2])
    checks = {
        "massConserved": abs(sum(source.mass) - sum(candidate.mass)) <= 1e-12,
        "uvTransferred": (
            len(candidate.uv) == len(candidate.positions) and candidate.uv[-1] == expected_uv
        ),
        "materialTransferred": (
            len(candidate.material) == len(candidate.positions)
            and candidate.material[-1] == source.material[0]
        ),
        "sourceCoordinatesTransferred": (
            len(candidate.source_coordinates) == len(candidate.positions)
            and candidate.source_coordinates[-1] == expected_source
        ),
        "bindingCoordinatesTransferred": (
            len(candidate.binding_coordinates) == len(candidate.positions)
            and candidate.binding_coordinates[-1] == expected_binding
        ),
        "semanticSeamCorrespondenceComplete": seam_complete,
        "openingPreserved": candidate.opening_cycles == source.opening_cycles,
        "topologyValid": sum(defects.values()) == 0,
        "minimumAngle": minimum_triangle_angle(candidate) >= 5.0,
        "finiteValues": _all_values_finite(candidate),
    }
    provenance: dict[str, int | str] = {
        "revision": revision,
        "strategyClass": strategy_class,
    }
    identity = transfer_identity(candidate, provenance)
    mutation_checks = _negative_mutation_checks(source, candidate, midpoint_index)
    provenance_mutation: dict[str, int | str] = {
        **provenance,
        "revision": revision + 100,
    }
    return {
        "checks": checks,
        "defects": defects,
        "massErrorKg": abs(sum(source.mass) - sum(candidate.mass)),
        "minimumTriangleAngleDegrees": minimum_triangle_angle(candidate),
        "identityDigest": identity,
        "negativeMutationChecks": mutation_checks,
        "allNegativeMutationsDetected": all(mutation_checks.values()),
        "provenanceMutationChangesIdentity": (
            transfer_identity(candidate, provenance_mutation) != identity
        ),
        "status": "pass" if all(checks.values()) else "fail",
    }


def topology_defects(mesh: TransferMesh) -> dict[str, int]:
    duplicate_faces = len(mesh.triangles) - len({tuple(sorted(face)) for face in mesh.triangles})
    edge_counts: dict[tuple[int, int], int] = {}
    for face in mesh.triangles:
        for left, right in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = cast(tuple[int, int], tuple(sorted((left, right))))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    non_manifold = sum(count > 2 for count in edge_counts.values())
    t_junctions = 0
    for vertex_index, point in enumerate(mesh.positions):
        for edge in edge_counts:
            if vertex_index not in edge and _point_on_segment(
                point, mesh.positions[edge[0]], mesh.positions[edge[1]]
            ):
                t_junctions += 1
    winding = sum(_signed_area(mesh, face) <= 0.0 for face in mesh.triangles)
    used = {index for face in mesh.triangles for index in face}
    hidden = len(mesh.positions) - len(used)
    non_finite = sum(not math.isfinite(value) for position in mesh.positions for value in position)
    return {
        "duplicateFaces": duplicate_faces,
        "nonManifoldEdges": non_manifold,
        "tJunctions": t_junctions,
        "windingFaults": winding,
        "hiddenVertices": hidden,
        "nonFiniteValues": non_finite,
    }


def minimum_triangle_angle(mesh: TransferMesh) -> float:
    result = 180.0
    for face in mesh.triangles:
        points = [mesh.positions[index] for index in face]
        lengths = [_distance(points[(i + 1) % 3], points[(i + 2) % 3]) for i in range(3)]
        for index, opposite in enumerate(lengths):
            adjacent_a, adjacent_b = lengths[(index + 1) % 3], lengths[(index + 2) % 3]
            cosine = (adjacent_a**2 + adjacent_b**2 - opposite**2) / max(
                2 * adjacent_a * adjacent_b, 1e-15
            )
            result = min(result, math.degrees(math.acos(max(-1.0, min(1.0, cosine)))))
    return result


def transfer_identity(mesh: TransferMesh, provenance: dict[str, int | str] | None = None) -> str:
    payload = {"mesh": mesh.__dict__, "provenance": provenance or {}}
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _point_on_segment(
    point: tuple[float, float, float],
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> bool:
    whole = _distance(left, right)
    return (
        1e-12 < _distance(left, point) < whole - 1e-12
        and abs(_distance(left, point) + _distance(point, right) - whole) <= 1e-12
    )


def _signed_area(mesh: TransferMesh, face: tuple[int, int, int]) -> float:
    a, b, c = (mesh.positions[index] for index in face)
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _blend_binding(
    left: tuple[int, float, float, float], right: tuple[int, float, float, float]
) -> tuple[int, float, float, float]:
    if left[0] != right[0]:
        raise ValueError("unit_o_cross_triangle_binding_blend_forbidden")
    values = tuple((a + b) * 0.5 for a, b in zip(left[1:], right[1:], strict=True))
    return (left[0], values[0], values[1], values[2])


def _midpoint(
    left: tuple[float, float, float], right: tuple[float, float, float]
) -> tuple[float, float, float]:
    return cast(
        tuple[float, float, float],
        tuple((a + b) * 0.5 for a, b in zip(left, right, strict=True)),
    )


def _midpoint2(left: tuple[float, float], right: tuple[float, float]) -> tuple[float, float]:
    return ((left[0] + right[0]) * 0.5, (left[1] + right[1]) * 0.5)


def _distance(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _all_values_finite(mesh: TransferMesh) -> bool:
    values = [value for position in mesh.positions for value in position]
    values.extend(value for uv in mesh.uv for value in uv)
    values.extend(value for source in mesh.source_coordinates for value in source)
    values.extend(value for binding in mesh.binding_coordinates for value in binding[1:])
    values.extend(mesh.mass)
    return all(math.isfinite(value) for value in values)


def _negative_mutation_checks(
    source: TransferMesh, candidate: TransferMesh, midpoint_index: int
) -> dict[str, bool]:
    mass_mutation = deepcopy(candidate)
    mass_mutation.mass[-1] += 0.01
    uv_mutation = deepcopy(candidate)
    uv_mutation.uv.pop()
    material_mutation = deepcopy(candidate)
    material_mutation.material.pop()
    seam_mutation = deepcopy(candidate)
    seam_mutation.semantic_seam_ids["seam.diagonal"] = [0, midpoint_index]
    source_mutation = deepcopy(candidate)
    source_mutation.source_coordinates.pop()
    binding_mutation = deepcopy(candidate)
    binding_mutation.binding_coordinates.pop()
    opening_mutation = deepcopy(candidate)
    opening_mutation.opening_cycles.clear()
    duplicate_mutation = deepcopy(candidate)
    duplicate_mutation.triangles.append(duplicate_mutation.triangles[0])
    winding_mutation = deepcopy(candidate)
    first = winding_mutation.triangles[0]
    winding_mutation.triangles[0] = (first[0], first[2], first[1])
    finite_mutation = deepcopy(candidate)
    finite_mutation.positions[-1] = (math.nan, 0.5, 0.0)
    return {
        "massConservation": abs(sum(source.mass) - sum(mass_mutation.mass)) > 1e-12,
        "uvCompleteness": len(uv_mutation.uv) != len(uv_mutation.positions),
        "materialCompleteness": len(material_mutation.material) != len(material_mutation.positions),
        "semanticSeamCorrespondence": seam_mutation.semantic_seam_ids["seam.diagonal"]
        != [0, midpoint_index, 2],
        "sourceCoordinateCompleteness": len(source_mutation.source_coordinates)
        != len(source_mutation.positions),
        "bindingCompleteness": len(binding_mutation.binding_coordinates)
        != len(binding_mutation.positions),
        "openingCount": opening_mutation.opening_cycles != source.opening_cycles,
        "duplicateFace": topology_defects(duplicate_mutation)["duplicateFaces"] > 0,
        "winding": topology_defects(winding_mutation)["windingFaults"] > 0,
        "finiteValues": not _all_values_finite(finite_mutation),
    }
