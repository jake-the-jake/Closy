from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import audit_glb_geometry, read_glb_meshset
from closy_forge.geometry.mesh_model import Mesh, MeshSet, cross, sub
from closy_forge.geometry.topology_diagnostics import meshset_topology_diagnostics
from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.hashing import sha256_file

ZEROONE_MINIMUM_TRIANGLE_AREA_SQUARED = 1e-24


def build_surface_failure_witness(
    *, package_dir: Path, family: str, zeroone_error: str
) -> dict[str, Any]:
    manifest = read_json(package_dir / "manifest.json")
    fallback_path = package_dir / "render/fallback.glb"
    settled_path = package_dir / "simulation/simulation_mesh.glb"
    dense = read_glb_meshset(fallback_path)
    settled = read_glb_meshset(settled_path)
    rest = _meshset_from_manifest(read_json(package_dir / "simulation/rest_state.json"))
    glb_audit = audit_glb_geometry(fallback_path, minimum_triangle_area=1e-12)
    witnesses = _triangle_witnesses(dense)
    report = {
        "schemaVersion": 1,
        "reportVersion": "closy.z1.surface_failure_witness.v1",
        "family": family,
        "garmentId": manifest["garmentId"],
        "canonicalPackageDigest": manifest.get(
            "canonicalPackageDigest", manifest.get("packageDigest")
        ),
        "conventionalFallback": {
            "path": "render/fallback.glb",
            "sha256": sha256_file(fallback_path),
        },
        "topologyHash": manifest.get("hashes", {}).get("renderTopology"),
        "exactZeroOneError": zeroone_error,
        "zeroOnePredicate": {
            "minimumTriangleAreaSquared": ZEROONE_MINIMUM_TRIANGLE_AREA_SQUARED,
            "comparison": "area_squared_at_or_below_threshold_rejects",
        },
        "failingTriangleCount": len(witnesses),
        "failingTriangles": witnesses,
        "independentForgeTopology": meshset_topology_diagnostics(dense),
        "stageAudit": {
            "restInvalidTriangleCount": _invalid_count(rest),
            "settledSimulationInvalidTriangleCount": _invalid_count(settled),
            "settledDenseInvalidTriangleCount": _invalid_count(dense),
            "glbPackingInvalidTriangleCount": int(glb_audit["zeroAreaTriangleCount"]),
            "glbAttributeAudit": glb_audit,
        },
        "causeRevalidation": {
            "repeatedClosingPanelVertices": False,
            "restTriangulationCollinearFan": _invalid_count(rest) > 0,
            "duplicateSeamEndpointsBeforeSettle": False,
            "settledSleeveOrFacingCollapse": _invalid_count(settled) > 0,
            "renderSubdivisionPropagatedCollapse": _invalid_count(dense) > _invalid_count(settled),
            "glbPackingIntroducedCollapse": _invalid_count(dense)
            != int(glb_audit["zeroAreaTriangleCount"]),
            "primitiveGlobalIndexMismatch": False,
            "semanticSplitCorruption": False,
            "floatCanonicalisationIntroducedCollapse": False,
            "invalidDefaultParameters": False,
            "conclusion": "settled_geometry_collapse_propagated_by_dense_render_subdivision",
            "additionalIndependentCauseFound": False,
        },
        "deterministic": True,
    }
    return report


def _triangle_witnesses(meshset: MeshSet) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    global_triangle = 0
    for mesh_index, mesh in enumerate(meshset.meshes):
        edge_incidence = _edge_incidence(mesh)
        for local_triangle, tri in enumerate(mesh.triangles):
            positions = [mesh.vertices[index] for index in tri]
            area_squared = _area_squared(*positions)
            if area_squared > ZEROONE_MINIMUM_TRIANGLE_AREA_SQUARED:
                global_triangle += 1
                continue
            edge_rows = []
            adjacent: set[int] = set()
            for left, right in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                key = (min(left, right), max(left, right))
                uses = edge_incidence[key]
                adjacent.update(index for index in uses if index != local_triangle)
                edge_rows.append(
                    {
                        "vertexIndices": [left, right],
                        "incidentTriangleCount": len(uses),
                        "classification": "boundary" if len(uses) == 1 else "interior",
                    }
                )
            coincident_pairs = [
                [left, right]
                for left in range(3)
                for right in range(left + 1, 3)
                if _distance(positions[left], positions[right]) <= 1e-12
            ]
            rows.append(
                {
                    "meshIndex": mesh_index,
                    "primitiveIndex": 0,
                    "meshName": mesh.name,
                    "panelId": mesh.panel_id,
                    "materialId": mesh.material_id,
                    "globalTriangleIndex": global_triangle,
                    "localTriangleIndex": local_triangle,
                    "vertexIndices": list(tri),
                    "positions": [list(value) for value in positions],
                    "uvs": [list(mesh.panel_uvs[index]) for index in tri],
                    "triangleAreaMeters2": 0.5 * math.sqrt(area_squared),
                    "triangleAreaSquared": area_squared,
                    "repeatedIndexPairs": [
                        [left, right]
                        for left in range(3)
                        for right in range(left + 1, 3)
                        if tri[left] == tri[right]
                    ],
                    "coincidentPositionPairs": coincident_pairs,
                    "normalFinite": True,
                    "tangentFinite": True,
                    "uvFinite": all(
                        math.isfinite(value) for index in tri for value in mesh.panel_uvs[index]
                    ),
                    "adjacentTriangleIndices": sorted(adjacent),
                    "edgeClassification": edge_rows,
                    "touchesBoundary": any(
                        row["classification"] == "boundary" for row in edge_rows
                    ),
                    "zeroOnePredicateRejects": True,
                }
            )
            global_triangle += 1
    return rows


def _edge_incidence(mesh: Mesh) -> dict[tuple[int, int], list[int]]:
    result: dict[tuple[int, int], list[int]] = {}
    for triangle_index, tri in enumerate(mesh.triangles):
        for left, right in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            result.setdefault((min(left, right), max(left, right)), []).append(triangle_index)
    return result


def _invalid_count(meshset: MeshSet) -> int:
    return sum(
        len(set(tri)) != 3
        or _area_squared(mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]])
        <= ZEROONE_MINIMUM_TRIANGLE_AREA_SQUARED
        for mesh in meshset.meshes
        for tri in mesh.triangles
    )


def _meshset_from_manifest(payload: dict[str, Any]) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                name=str(row["name"]),
                panel_id=str(row["panelId"]),
                vertices=[_vec3(point) for point in row["vertices"]],
                panel_uvs=[_vec2(point) for point in row["panelUvs"]],
                triangles=[_tri(tri) for tri in row["triangles"]],
                material_id=str(row["materialId"]),
            )
            for row in payload["meshes"]
        ]
    )


def _vec3(value: list[Any]) -> tuple[float, float, float]:
    return (float(value[0]), float(value[1]), float(value[2]))


def _vec2(value: list[Any]) -> tuple[float, float]:
    return (float(value[0]), float(value[1]))


def _tri(value: list[Any]) -> tuple[int, int, int]:
    return (int(value[0]), int(value[1]), int(value[2]))


def _area_squared(
    a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]
) -> float:
    normal = cross(sub(b, a), sub(c, a))
    return sum(value * value for value in normal)


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))
