from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from closy_forge.garments.tshirt.assembly import TRANSFORMS
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.geometry.mesh_model import MeshSet, finite_mesh
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, topology_hash
from closy_forge.simulation_topology_v2 import (
    build_panel_meshes_v2,
    build_seam_constraints_v2,
    build_topology_v2_render_binding,
)

STRUCTURAL_COMPILER_VERSION = "closy.d0_disjoint.structural_compiler.v1"


@dataclass(frozen=True)
class StructuralCompile:
    pattern: dict[str, Any]
    rest_mesh: MeshSet
    render_mesh: MeshSet
    report: dict[str, Any]


def compile_structural_candidate(parameters: Mapping[str, Any]) -> StructuralCompile:
    params = TShirtParameters(**{key: float(value) for key, value in parameters.items()})
    params.validate()
    pattern = build_tshirt_pattern(params)
    rest_mesh, edge_maps, topology_manifest = build_panel_meshes_v2(pattern, TRANSFORMS)
    constraints, seam_audit = build_seam_constraints_v2(pattern, edge_maps, rest_mesh)
    render_mesh, _seeds, binding, binding_manifest, binding_audit = (
        build_topology_v2_render_binding(rest_mesh)
    )
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "compilerVersion": STRUCTURAL_COMPILER_VERSION,
        "solverExecuted": False,
        "physicsClaimed": False,
        "patternHash": _hash(pattern),
        "panelCount": len(pattern["panels"]),
        "seamCount": len(pattern["seams"]),
        "openingIds": sorted(str(item["id"]) for item in pattern["openings"]),
        "restTopologyHash": topology_hash(rest_mesh),
        "restContentHash": geometry_content_hash(rest_mesh),
        "renderTopologyHash": topology_hash(render_mesh),
        "renderContentHash": geometry_content_hash(render_mesh),
        "bindingRecordCount": len(binding.records),
        "bindingManifestHash": _hash(binding_manifest),
        "bindingStatus": binding_audit["status"],
        "seamStatus": seam_audit["status"],
        "constraintCount": len(constraints["constraints"]),
        "simulationTopologyVersion": topology_manifest["simulationTopologyVersion"],
        "finite": finite_mesh(rest_mesh) and finite_mesh(render_mesh),
        "vertexCount": rest_mesh.vertex_count,
        "triangleCount": rest_mesh.triangle_count,
    }
    report["compileHash"] = _hash(report)
    return StructuralCompile(
        pattern=pattern, rest_mesh=rest_mesh, render_mesh=render_mesh, report=report
    )


def reference_mesh_metrics(candidate: MeshSet, target: MeshSet) -> dict[str, float | int]:
    candidate_vertices = [vertex for mesh in candidate.meshes for vertex in mesh.vertices]
    target_vertices = [vertex for mesh in target.meshes for vertex in mesh.vertices]
    if len(candidate_vertices) != len(target_vertices):
        return {
            "vertexCountDelta": abs(len(candidate_vertices) - len(target_vertices)),
            "rmsVertexErrorMeters": 1.0,
            "maximumVertexErrorMeters": 1.0,
        }
    distances = [
        math.dist(left, right)
        for left, right in zip(candidate_vertices, target_vertices, strict=True)
    ]
    return {
        "vertexCountDelta": 0,
        "rmsVertexErrorMeters": round(
            math.sqrt(math.fsum(value * value for value in distances) / max(1, len(distances))),
            9,
        ),
        "maximumVertexErrorMeters": round(max(distances, default=0.0), 9),
    }


def _hash(value: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(dict(value)).encode("utf-8"))
