from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import replace
from hashlib import sha256
from math import acos, degrees, sqrt
from typing import cast

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .model import (
    Binding,
    Face,
    Garment,
    Panel,
    RebuiltData,
    Seam,
    SeamSide,
    Vertex,
    with_vertex_mass,
)
from .semantic_transfer import build_correspondence

STRATEGY_ID = "PHY1-V5-S3-SEAM-SEQUENCE-CONFORMING-REMESH-V2"


def build_generic_garment(
    *, seam_count: int, sample_count: int, opening_count: int, target_mass_kg: float
) -> Garment:
    panels = (_panel("panel.front", -0.012), _panel("panel.back", 0.012))
    seams = tuple(
        Seam(
            seam_id=f"seam.{ordinal}",
            sides=(
                SeamSide(
                    f"seam.{ordinal}.front",
                    "panel.front",
                    ("panel.front.v0", "panel.front.v1"),
                    1,
                    ("endpoint.waist", "endpoint.shoulder"),
                ),
                SeamSide(
                    f"seam.{ordinal}.back",
                    "panel.back",
                    ("panel.back.v1", "panel.back.v0"),
                    -1,
                    ("endpoint.shoulder", "endpoint.waist"),
                ),
            ),
            ease_profile=((0.0, 0.0), (0.35, 0.30), (0.72, 0.76), (1.0, 1.0)),
            sample_count=sample_count,
            junction_id="junction.shoulder" if seam_count == 3 else None,
        )
        for ordinal in range(seam_count)
    )
    openings = tuple(
        tuple(f"opening.{ordinal}.edge.{edge}" for edge in range(4))
        for ordinal in range(opening_count)
    )
    provisional = Garment(
        garment_id="public.generic.panelised",
        panels=panels,
        seams=seams,
        opening_cycles=openings,
        expected_quotient_components=1,
        target_mass_kg=target_mass_kg,
        source_topology_hash="",
        topology_hash="",
    )
    topology = topology_digest(provisional)
    return replace(
        _recompute_mass(provisional, target_mass_kg),
        source_topology_hash=topology,
        topology_hash=topology,
    )


def remesh_garment(source: Garment, *, refinement_levels: int) -> tuple[Garment, RebuiltData]:
    if refinement_levels < 1:
        raise ValueError("strategy3_refinement_level_invalid")
    panels = source.panels
    seams = source.seams
    for _ in range(refinement_levels):
        refinements = tuple(_refine_once(panel) for panel in panels)
        panels = tuple(item[0] for item in refinements)
        for _, split_edge, inserted in refinements:
            seams = tuple(_update_seam(seam, split_edge, inserted) for seam in seams)
    target = replace(
        source,
        panels=panels,
        seams=seams,
        source_topology_hash=source.topology_hash,
    )
    target = _recompute_mass(target, source.target_mass_kg)
    target_hash = topology_digest(target)
    target = replace(target, topology_hash=target_hash)
    return target, rebuild_derived_data(source, target)


def rebuild_derived_data(source: Garment, target: Garment) -> RebuiltData:
    edges: set[tuple[str, str]] = set()
    face_edges: dict[tuple[str, str], list[str]] = defaultdict(list)
    collision_faces: list[str] = []
    for panel in target.panels:
        for face in panel.faces:
            collision_faces.append(face.face_id)
            for edge in _face_edges(face.vertices):
                ordered = _ordered_edge(*edge)
                edges.add(ordered)
                face_edges[ordered].append(face.face_id)
    shear = tuple(edge for edge in sorted(edges) if _is_diagonal(target, edge))
    bend = tuple(
        _ordered_edge(faces[0], faces[1]) for faces in face_edges.values() if len(faces) == 2
    )
    seam_ids: list[str] = []
    stitched: set[tuple[str, str]] = set()
    for seam in target.seams:
        for sample in build_correspondence(seam, target.panels):
            seam_ids.append(sample.sample_id)
            stitched.add(_ordered_edge(sample.side_a.vertex_id, sample.side_b.vertex_id))
            stitched.add(_ordered_edge(sample.side_a.next_vertex_id, sample.side_b.next_vertex_id))
    adjacency = tuple(sorted(edges))
    support = tuple(
        sorted(
            vertex.vertex_id
            for panel in target.panels
            for vertex in panel.vertices
            if vertex.position[1] >= 1.34
        )
    )
    bindings = _rebuild_bindings(source, target)
    return RebuiltData(
        structural_edges=tuple(sorted(edges)),
        shear_edges=shear,
        bend_pairs=tuple(sorted(bend)),
        seam_constraint_ids=tuple(seam_ids),
        support_vertex_ids=support,
        collision_faces=tuple(sorted(collision_faces)),
        self_collision_adjacency=adjacency,
        stitched_exclusions=tuple(sorted(stitched)),
        bindings=bindings,
    )


def validate_transfer(source: Garment, target: Garment, rebuilt: RebuiltData) -> list[str]:
    issues: list[str] = []
    if abs(_total_mass(target) - _total_mass(source)) > 1e-12:
        issues.append("mass_not_conserved")
    if (
        target.source_topology_hash != source.topology_hash
        or target.topology_hash == source.topology_hash
    ):
        issues.append("topology_version_chain_invalid")
    expected_classes = {
        "mass",
        "uv",
        "material",
        "source_coordinates",
        "semantic_ids",
        "binding_ancestry",
    }
    for panel in target.panels:
        if not panel.faces or not panel.vertices:
            issues.append("empty_panel")
        if _panel_topology_issues(panel):
            issues.extend(_panel_topology_issues(panel))
        for vertex in panel.vertices:
            if not vertex.ancestry or not vertex.material_id or not vertex.semantic_ids:
                issues.append("vertex_attribute_or_ancestry_missing")
        for face in panel.faces:
            if not face.ancestry or not face.material_region or not face.body_region:
                issues.append("face_attribute_or_ancestry_missing")
    if len(rebuilt.bindings) != sum(len(panel.vertices) for panel in source.panels):
        issues.append("binding_count_invalid")
    if any(binding.target_topology_hash != target.topology_hash for binding in rebuilt.bindings):
        issues.append("stale_binding_topology_hash")
    if any(abs(sum(binding.weights) - 1.0) > 1e-12 for binding in rebuilt.bindings):
        issues.append("binding_partition_invalid")
    all_vertices = {vertex.vertex_id for panel in target.panels for vertex in panel.vertices}
    if any(
        left not in all_vertices or right not in all_vertices
        for left, right in rebuilt.structural_edges
    ):
        issues.append("stale_constraint_vertex")
    if expected_classes != transferred_attribute_classes(target, rebuilt):
        issues.append("transferred_attribute_classes_invalid")
    if quotient_component_count(target) != target.expected_quotient_components:
        issues.append("semantic_quotient_component_count_invalid")
    if any(len(cycle) != len(set(cycle)) for cycle in target.opening_cycles):
        issues.append("semantic_opening_branched_or_repeated")
    return sorted(set(issues))


def transferred_attribute_classes(target: Garment, rebuilt: RebuiltData) -> set[str]:
    if not target.panels or not rebuilt.bindings:
        return set()
    return {"mass", "uv", "material", "source_coordinates", "semantic_ids", "binding_ancestry"}


def quotient_component_count(garment: Garment) -> int:
    panel_ids = {panel.panel_id for panel in garment.panels}
    graph: dict[str, set[str]] = {panel_id: set() for panel_id in panel_ids}
    for seam in garment.seams:
        side_panels = {side.panel_id for side in seam.sides}
        for left in side_panels:
            graph[left].update(side_panels - {left})
    count = 0
    unvisited = set(panel_ids)
    while unvisited:
        count += 1
        queue = deque([unvisited.pop()])
        while queue:
            for neighbor in graph[queue.popleft()] & unvisited:
                unvisited.remove(neighbor)
                queue.append(neighbor)
    return count


def topology_digest(garment: Garment) -> str:
    payload = {
        "panels": [
            {
                "id": panel.panel_id,
                "vertices": [vertex.vertex_id for vertex in panel.vertices],
                "faces": [[face.face_id, *face.vertices] for face in panel.faces],
                "boundaries": panel.boundary_cycles,
            }
            for panel in garment.panels
        ],
        "seamSides": [
            [seam.seam_id, [[side.side_id, *side.vertices] for side in seam.sides]]
            for seam in garment.seams
        ],
        "openings": garment.opening_cycles,
    }
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _panel(panel_id: str, z: float) -> Panel:
    points = ((-0.2, 1.0, z), (-0.2, 1.4, z), (0.2, 1.4, z), (0.2, 1.0, z), (0.0, 1.2, z))
    vertices = tuple(
        Vertex(
            f"{panel_id}.v{index}",
            point,
            ((point[0] + 0.2) / 0.4, (point[1] - 1.0) / 0.4),
            (point[0], point[1]),
            0.0,
            "material.public_cotton",
            (f"semantic.{panel_id}",),
            (f"{panel_id}.v{index}",),
        )
        for index, point in enumerate(points)
    )
    faces = tuple(
        Face(
            f"{panel_id}.f{index}",
            panel_id,
            triangle,
            (0.0, 1.0),
            "material.public_cotton",
            "body.torso",
            (f"{panel_id}.f{index}",),
        )
        for index, triangle in enumerate(
            (
                (f"{panel_id}.v0", f"{panel_id}.v4", f"{panel_id}.v1"),
                (f"{panel_id}.v1", f"{panel_id}.v4", f"{panel_id}.v2"),
                (f"{panel_id}.v2", f"{panel_id}.v4", f"{panel_id}.v3"),
                (f"{panel_id}.v3", f"{panel_id}.v4", f"{panel_id}.v0"),
            )
        )
    )
    boundary = (
        f"{panel_id}.v0",
        f"{panel_id}.v1",
        f"{panel_id}.v2",
        f"{panel_id}.v3",
    )
    return Panel(panel_id, vertices, faces, (boundary,))


def _refine_once(panel: Panel) -> tuple[Panel, tuple[str, str], str]:
    vertices = panel.vertex_map()
    edge_faces: dict[tuple[str, str], list[Face]] = defaultdict(list)
    for face in panel.faces:
        for edge in _face_edges(face.vertices):
            edge_faces[_ordered_edge(*edge)].append(face)
    ranked = sorted(
        edge_faces,
        key=lambda edge: (
            -_squared_distance(vertices[edge[0]].position, vertices[edge[1]].position),
            panel.panel_id,
            tuple(sorted((*vertices[edge[0]].ancestry, *vertices[edge[1]].ancestry))),
            min(face.face_id for face in edge_faces[edge]),
        ),
    )
    edge = ranked[0]
    left, right = vertices[edge[0]], vertices[edge[1]]
    vertex_id = _stable_id("vertex", panel.panel_id, left.ancestry, right.ancestry, "1/2")
    inserted = Vertex(
        vertex_id,
        _midpoint3(left.position, right.position),
        _midpoint2(left.panel_uv, right.panel_uv),
        _midpoint2(left.source_coordinate, right.source_coordinate),
        0.0,
        min(left.material_id, right.material_id),
        tuple(sorted(set(left.semantic_ids) | set(right.semantic_ids))),
        tuple(sorted(set(left.ancestry) | set(right.ancestry))),
    )
    new_faces: list[Face] = []
    for face in panel.faces:
        if face not in edge_faces[edge]:
            new_faces.append(face)
            continue
        split = _split_face(face, edge, inserted.vertex_id)
        new_faces.extend(split)
    boundaries = tuple(
        _insert_in_cycle(cycle, edge, inserted.vertex_id) for cycle in panel.boundary_cycles
    )
    refined = Panel(
        panel.panel_id,
        (*panel.vertices, inserted),
        tuple(new_faces),
        boundaries,
    )
    return refined, edge, inserted.vertex_id


def _split_face(face: Face, edge: tuple[str, str], inserted: str) -> tuple[Face, Face]:
    values = face.vertices
    for index in range(3):
        left = values[index]
        right = values[(index + 1) % 3]
        if {left, right} == set(edge):
            opposite = values[(index + 2) % 3]
            first = replace(
                face,
                face_id=_stable_id("face", face.panel_id, face.ancestry, (left,), inserted),
                vertices=(left, inserted, opposite),
            )
            second = replace(
                face,
                face_id=_stable_id("face", face.panel_id, face.ancestry, (right,), inserted),
                vertices=(inserted, right, opposite),
            )
            return first, second
    raise ValueError("strategy3_split_edge_not_incident")


def _insert_in_cycle(
    cycle: tuple[str, ...], edge: tuple[str, str], inserted: str
) -> tuple[str, ...]:
    result: list[str] = []
    for index, value in enumerate(cycle):
        result.append(value)
        following = cycle[(index + 1) % len(cycle)]
        if {value, following} == set(edge):
            result.append(inserted)
    return tuple(result)


def _update_seam(seam: Seam, edge: tuple[str, str], inserted: str) -> Seam:
    sides = tuple(
        replace(side, vertices=_insert_in_chain(side.vertices, edge, inserted))
        for side in seam.sides
    )
    return replace(seam, sides=sides)


def _insert_in_chain(
    chain: tuple[str, ...], edge: tuple[str, str], inserted: str
) -> tuple[str, ...]:
    result: list[str] = []
    for left, right in zip(chain, chain[1:], strict=False):
        result.append(left)
        if {left, right} == set(edge):
            result.append(inserted)
    result.append(chain[-1])
    return tuple(result)


def _recompute_mass(garment: Garment, target_mass: float) -> Garment:
    face_areas: dict[str, float] = {}
    total_area = 0.0
    for panel in garment.panels:
        vertices = panel.vertex_map()
        for face in panel.faces:
            area = _triangle_area(*(vertices[value].position for value in face.vertices))
            face_areas[face.face_id] = area
            total_area += area
    if total_area <= 1e-15:
        raise ValueError("strategy3_zero_area_garment")
    vertex_masses: dict[str, float] = defaultdict(float)
    for panel in garment.panels:
        for face in panel.faces:
            share = target_mass * face_areas[face.face_id] / total_area / 3.0
            for vertex_id in face.vertices:
                vertex_masses[vertex_id] += share
    correction_id = min(vertex_masses)
    vertex_masses[correction_id] += target_mass - sum(vertex_masses.values())
    panels = tuple(
        replace(
            panel,
            vertices=tuple(
                with_vertex_mass(vertex, vertex_masses[vertex.vertex_id])
                for vertex in panel.vertices
            ),
        )
        for panel in garment.panels
    )
    return replace(garment, panels=panels, target_mass_kg=target_mass)


def _rebuild_bindings(source: Garment, target: Garment) -> tuple[Binding, ...]:
    target_panels = {panel.panel_id: panel for panel in target.panels}
    records: list[Binding] = []
    for source_panel in source.panels:
        target_panel = target_panels[source_panel.panel_id]
        target_vertices = target_panel.vertex_map()
        for vertex in source_panel.vertices:
            candidates: list[tuple[float, str, tuple[float, float, float]]] = []
            for face in target_panel.faces:
                weights = _barycentric_2d(
                    vertex.source_coordinate,
                    *(target_vertices[item].source_coordinate for item in face.vertices),
                )
                outside = sum(max(0.0, -weight) for weight in weights)
                candidates.append((outside, face.face_id, weights))
            _, face_id, weights = min(candidates, key=lambda item: (item[0], item[1]))
            clamped = tuple(max(0.0, min(1.0, value)) for value in weights)
            total = sum(clamped)
            normalized = cast(tuple[float, float, float], tuple(value / total for value in clamped))
            records.append(
                Binding(
                    vertex.vertex_id,
                    target_panel.panel_id,
                    face_id,
                    normalized,
                    target.topology_hash,
                )
            )
    return tuple(records)


def _panel_topology_issues(panel: Panel) -> list[str]:
    issues: list[str] = []
    vertices = panel.vertex_map()
    edge_count: dict[tuple[str, str], int] = defaultdict(int)
    faces = set()
    for face in panel.faces:
        canonical = tuple(sorted(face.vertices))
        if canonical in faces:
            issues.append("duplicate_face")
        faces.add(canonical)
        if len(set(face.vertices)) != 3 or any(vertex not in vertices for vertex in face.vertices):
            issues.append("invalid_face_index")
            continue
        if _signed_area(*(vertices[item].source_coordinate for item in face.vertices)) <= 1e-15:
            issues.append("winding_or_zero_area")
        for edge in _face_edges(face.vertices):
            edge_count[_ordered_edge(*edge)] += 1
    if any(count > 2 for count in edge_count.values()):
        issues.append("raw_panel_non_manifold_edge")
    for vertex_id, vertex in vertices.items():
        for edge in edge_count:
            if vertex_id not in edge and _point_on_segment_2d(
                vertex.source_coordinate,
                vertices[edge[0]].source_coordinate,
                vertices[edge[1]].source_coordinate,
            ):
                issues.append("raw_panel_t_junction")
    return sorted(set(issues))


def _is_diagonal(garment: Garment, edge: tuple[str, str]) -> bool:
    for panel in garment.panels:
        for cycle in panel.boundary_cycles:
            boundary = {
                _ordered_edge(cycle[i], cycle[(i + 1) % len(cycle)]) for i in range(len(cycle))
            }
            if edge in boundary:
                return False
    return True


def _face_edges(face: tuple[str, str, str]) -> tuple[tuple[str, str], ...]:
    return ((face[0], face[1]), (face[1], face[2]), (face[2], face[0]))


def _ordered_edge(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)


def _stable_id(kind: str, panel_id: str, *parts: object) -> str:
    payload = canonical_dumps([STRATEGY_ID, kind, panel_id, *parts]).encode("utf-8")
    return f"{panel_id}.{kind}.{sha256(payload).hexdigest()[:20]}"


def _total_mass(garment: Garment) -> float:
    return sum(vertex.mass_kg for panel in garment.panels for vertex in panel.vertices)


def _squared_distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right, strict=True))


def _midpoint3(
    left: tuple[float, float, float], right: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (
        (left[0] + right[0]) * 0.5,
        (left[1] + right[1]) * 0.5,
        (left[2] + right[2]) * 0.5,
    )


def _midpoint2(left: tuple[float, float], right: tuple[float, float]) -> tuple[float, float]:
    return ((left[0] + right[0]) * 0.5, (left[1] + right[1]) * 0.5)


def _triangle_area(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> float:
    ab = tuple(b[i] - a[i] for i in range(3))
    ac = tuple(c[i] - a[i] for i in range(3))
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return 0.5 * sqrt(sum(value * value for value in cross))


def _signed_area(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_on_segment_2d(
    point: tuple[float, float],
    left: tuple[float, float],
    right: tuple[float, float],
) -> bool:
    whole = sqrt(_squared_distance(left, right))
    first = sqrt(_squared_distance(left, point))
    second = sqrt(_squared_distance(point, right))
    return first > 1e-12 and second > 1e-12 and abs(first + second - whole) <= 1e-12


def _barycentric_2d(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> tuple[float, float, float]:
    denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(denominator) <= 1e-15:
        return (1.0, 0.0, 0.0)
    left = ((b[1] - c[1]) * (point[0] - c[0]) + (c[0] - b[0]) * (point[1] - c[1])) / denominator
    right = ((c[1] - a[1]) * (point[0] - c[0]) + (a[0] - c[0]) * (point[1] - c[1])) / denominator
    return (left, right, 1.0 - left - right)


def minimum_angle_degrees(garment: Garment) -> float:
    result = 180.0
    for panel in garment.panels:
        vertices = panel.vertex_map()
        for face in panel.faces:
            points = [vertices[item].position for item in face.vertices]
            lengths = [
                sqrt(_squared_distance(points[(i + 1) % 3], points[(i + 2) % 3])) for i in range(3)
            ]
            for index, opposite in enumerate(lengths):
                adjacent_a, adjacent_b = lengths[(index + 1) % 3], lengths[(index + 2) % 3]
                cosine = (adjacent_a**2 + adjacent_b**2 - opposite**2) / max(
                    2.0 * adjacent_a * adjacent_b, 1e-15
                )
                result = min(result, degrees(acos(max(-1.0, min(1.0, cosine)))))
    return result
