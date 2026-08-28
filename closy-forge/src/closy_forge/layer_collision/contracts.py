from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

CAPABILITY_VERSION = "closy.layer_collision_capability.d0.v1"
SOLVER_VERSION = "closy.layer_collision.simultaneous_radial_shell_cpu.d0.v1"
EVIDENCE_VERSION = "closy.layer_collision_evidence.d0.v1"


class LayerCollisionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class LayerSpec:
    layer_id: str
    collision_order: int
    parent_layer_id: str | None
    material_id: str
    thickness_meters: float
    areal_density_kg_m2: float
    radial_stiffness: float
    initial_center_offset_meters: float


@dataclass(frozen=True)
class OutfitSpec:
    case_id: str
    zone: str
    body_radius_meters: float
    body_clearance_meters: float
    inter_layer_clearance_meters: float
    motion_amplitude: float
    opening_compatible: bool
    layers: tuple[LayerSpec, ...]


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


def rounded(value: float) -> float:
    return round(float(value), 12)
