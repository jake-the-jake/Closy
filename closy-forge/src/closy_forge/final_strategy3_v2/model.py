from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TypeAlias

Vec2: TypeAlias = tuple[float, float]
Vec3: TypeAlias = tuple[float, float, float]
TriIds: TypeAlias = tuple[str, str, str]


@dataclass(frozen=True)
class Vertex:
    vertex_id: str
    position: Vec3
    panel_uv: Vec2
    source_coordinate: Vec2
    mass_kg: float
    material_id: str
    semantic_ids: tuple[str, ...]
    ancestry: tuple[str, ...]


@dataclass(frozen=True)
class Face:
    face_id: str
    panel_id: str
    vertices: TriIds
    grain_direction: Vec2
    material_region: str
    body_region: str
    ancestry: tuple[str, ...]


@dataclass(frozen=True)
class Panel:
    panel_id: str
    vertices: tuple[Vertex, ...]
    faces: tuple[Face, ...]
    boundary_cycles: tuple[tuple[str, ...], ...]

    def vertex_map(self) -> dict[str, Vertex]:
        return {vertex.vertex_id: vertex for vertex in self.vertices}


@dataclass(frozen=True)
class SeamSide:
    side_id: str
    panel_id: str
    vertices: tuple[str, ...]
    orientation: int
    endpoint_classes: tuple[str, str]


@dataclass(frozen=True)
class Seam:
    seam_id: str
    sides: tuple[SeamSide, ...]
    ease_profile: tuple[tuple[float, float], ...]
    sample_count: int
    junction_id: str | None = None


@dataclass(frozen=True)
class Garment:
    garment_id: str
    panels: tuple[Panel, ...]
    seams: tuple[Seam, ...]
    opening_cycles: tuple[tuple[str, ...], ...]
    expected_quotient_components: int
    target_mass_kg: float
    source_topology_hash: str
    topology_hash: str


@dataclass(frozen=True)
class Binding:
    render_vertex_id: str
    target_panel_id: str
    target_face_id: str
    weights: tuple[float, float, float]
    target_topology_hash: str


@dataclass(frozen=True)
class RebuiltData:
    structural_edges: tuple[tuple[str, str], ...]
    shear_edges: tuple[tuple[str, str], ...]
    bend_pairs: tuple[tuple[str, str], ...]
    seam_constraint_ids: tuple[str, ...]
    support_vertex_ids: tuple[str, ...]
    collision_faces: tuple[str, ...]
    self_collision_adjacency: tuple[tuple[str, str], ...]
    stitched_exclusions: tuple[tuple[str, str], ...]
    bindings: tuple[Binding, ...]


def with_vertex_mass(vertex: Vertex, mass_kg: float) -> Vertex:
    return replace(vertex, mass_kg=mass_kg)
