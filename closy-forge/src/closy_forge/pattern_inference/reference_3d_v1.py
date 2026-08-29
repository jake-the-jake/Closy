from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from closy_forge.binding.builder import build_binding
from closy_forge.garments.button_shirt.assembly import (
    build_simulation_mesh as build_button_shirt_mesh,
)
from closy_forge.garments.jacket_outerwear.assembly import (
    build_simulation_mesh as build_jacket_mesh,
)
from closy_forge.garments.layered_asymmetric.assembly import (
    build_simulation_mesh as build_layered_mesh,
)
from closy_forge.garments.long_sleeved_top.assembly import (
    build_simulation_mesh as build_long_sleeved_mesh,
)
from closy_forge.garments.simple_dress.assembly import (
    build_simulation_mesh as build_dress_mesh,
)
from closy_forge.garments.simple_skirt.assembly import (
    build_simulation_mesh as build_skirt_mesh,
)
from closy_forge.garments.simple_trousers.assembly import (
    build_simulation_mesh as build_trousers_mesh,
)
from closy_forge.garments.sleeveless_top.assembly import (
    build_simulation_mesh as build_sleeveless_mesh,
)
from closy_forge.geometry.mesh_model import MeshSet, finite_mesh, mesh_bounds
from closy_forge.geometry.subdivision import subdivide_for_render
from closy_forge.package_io.hashing import geometry_content_hash, topology_hash

REFERENCE_3D_VERSION = "closy.pattern_reference_mesh_evaluation.synthetic_d0.v1"

_ASSEMBLERS: dict[str, Callable[[dict[str, Any]], tuple[MeshSet, Any]]] = {
    "sleeveless_top": build_sleeveless_mesh,
    "long_sleeved_top": build_long_sleeved_mesh,
    "simple_skirt": build_skirt_mesh,
    "simple_trousers": build_trousers_mesh,
    "simple_dress": build_dress_mesh,
    "button_shirt": build_button_shirt_mesh,
    "jacket_outerwear": build_jacket_mesh,
    "layered_asymmetric": build_layered_mesh,
}


def build_reference_geometry(family: str, pattern: dict[str, Any]) -> dict[str, Any]:
    """Build the actual 3D assembly, dense render mesh and binding contract.

    This is a deterministic reference-deformation path, not a PHY1 cloth-settle claim.
    """

    try:
        assembler = _ASSEMBLERS[family]
    except KeyError as error:
        raise ValueError(f"reference_3d_family_unsupported:{family}") from error
    simulation, _edge_maps = assembler(pattern)
    render, seeds = subdivide_for_render(simulation)
    binding, binding_manifest = build_binding(simulation, render, seeds)
    if not finite_mesh(simulation) or not finite_mesh(render):
        raise ValueError("reference_3d_nonfinite_mesh")
    if len(binding.records) != render.vertex_count:
        raise ValueError("reference_3d_binding_incomplete")
    return {
        "version": REFERENCE_3D_VERSION,
        "family": family,
        "simulation": simulation,
        "render": render,
        "audit": {
            "simulationVertexCount": simulation.vertex_count,
            "simulationTriangleCount": simulation.triangle_count,
            "renderVertexCount": render.vertex_count,
            "renderTriangleCount": render.triangle_count,
            "simulationTopologyHash": topology_hash(simulation),
            "simulationContentHash": geometry_content_hash(simulation),
            "renderTopologyHash": topology_hash(render),
            "renderContentHash": geometry_content_hash(render),
            "bounds": mesh_bounds(render),
            "bindingRecordCount": len(binding.records),
            "maximumReconstructionError": binding_manifest["maximumReconstructionError"],
            "referencePath": "canonical_pattern_to_3d_assembly_to_dense_binding",
            "physicalSettleClaimed": False,
        },
    }


def compare_reference_geometry(candidate: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    candidate_mesh: MeshSet = candidate["render"]
    target_mesh: MeshSet = target["render"]
    candidate_points = _sample_points(candidate_mesh, 128)
    target_points = _sample_points(target_mesh, 128)
    views = [
        _projected_metric(candidate_points, target_points, yaw)
        for yaw in (0.0, math.pi, math.pi / 4.0, -math.pi / 4.0)
    ]
    candidate_bounds = mesh_bounds(candidate_mesh)
    target_bounds = mesh_bounds(target_mesh)
    return {
        "version": REFERENCE_3D_VERSION,
        "viewCount": len(views),
        "views": views,
        "meanProjectedChamferMeters": round(
            sum(float(item["symmetricChamferMeters"]) for item in views) / len(views), 9
        ),
        "meanBoundsRelativeError": round(
            sum(
                abs(float(left) - float(right)) / max(abs(float(right)), 1e-6)
                for left, right in zip(candidate_bounds["size"], target_bounds["size"], strict=True)
            )
            / 3.0,
            9,
        ),
        "candidate": candidate["audit"],
        "target": target["audit"],
        "targetUsedOnlyForHiddenEvaluation": True,
    }


def _sample_points(meshset: MeshSet, maximum: int) -> list[tuple[float, float, float]]:
    points = [vertex for mesh in meshset.meshes for vertex in mesh.vertices]
    if len(points) <= maximum:
        return points
    return [points[(index * len(points)) // maximum] for index in range(maximum)]


def _projected_metric(
    candidate: list[tuple[float, float, float]],
    target: list[tuple[float, float, float]],
    yaw: float,
) -> dict[str, Any]:
    cosine = math.cos(yaw)
    sine = math.sin(yaw)

    def project(point: tuple[float, float, float]) -> tuple[float, float]:
        return (point[0] * cosine + point[2] * sine, point[1])

    left = [project(point) for point in candidate]
    right = [project(point) for point in target]

    def one_way(source: list[tuple[float, float]], destination: list[tuple[float, float]]) -> float:
        return sum(
            min(math.hypot(x - tx, y - ty) for tx, ty in destination) for x, y in source
        ) / max(len(source), 1)

    chamfer = (one_way(left, right) + one_way(right, left)) / 2.0
    return {"yawRadians": round(yaw, 9), "symmetricChamferMeters": round(chamfer, 9)}
