from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import audit_glb_geometry, read_glb_meshset
from closy_forge.geometry.mesh_model import MeshSet, cross, finite_mesh, mesh_bounds, sub

MINIMUM_AREA_M2 = 1e-12


class FamilyGeometryError(ValueError):
    pass


def audit_mesh(mesh: MeshSet, *, family: str, stage: str) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    minimum = math.inf
    offset = 0
    for panel in mesh.meshes:
        for index, triangle in enumerate(panel.triangles):
            bad_index = len(set(triangle)) != 3 or any(
                i < 0 or i >= len(panel.vertices) for i in triangle
            )
            area = 0.0
            if not bad_index:
                a, b, c = (panel.vertices[i] for i in triangle)
                area = math.sqrt(sum(n * n for n in cross(sub(b, a), sub(c, a)))) / 2
            minimum = min(minimum, area)
            if bad_index or not math.isfinite(area) or area <= MINIMUM_AREA_M2:
                failures.append(
                    {
                        "family": family,
                        "panel": panel.panel_id,
                        "triangle": index,
                        "simulationTriangle": offset + index,
                        "childRenderTriangles": list(
                            range(4 * (offset + index), 4 * (offset + index + 1))
                        ),
                        "stage": stage,
                        "areaM2": area,
                    }
                )
        offset += len(panel.triangles)
    valid = finite_mesh(mesh) and mesh.triangle_count > 0 and not failures
    return {
        "valid": valid,
        "stage": stage,
        "triangleCount": mesh.triangle_count,
        "vertexCount": mesh.vertex_count,
        "minimumAreaM2": minimum,
        "invalidTriangleCount": len(failures),
        "firstFailure": next(iter(failures), None),
        "bounds": mesh_bounds(mesh),
    }


def require_mesh(mesh: MeshSet, *, family: str, stage: str) -> dict[str, Any]:
    result = audit_mesh(mesh, family=family, stage=stage)
    if not result["valid"]:
        raise FamilyGeometryError(f"invalid_geometry:{result}")
    return result


def require_glb(path: Path, *, family: str = "runtime") -> dict[str, Any]:
    audit = audit_glb_geometry(path, minimum_triangle_area=MINIMUM_AREA_M2)
    if audit["status"] != "pass":
        raise FamilyGeometryError(f"invalid_decoded_glb:{family}:{audit['witnesses'][:1]}")
    mesh = read_glb_meshset(path)
    return require_mesh(mesh, family=family, stage="float32_glb")
