from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    package_digest,
    sha256_file,
    topology_hash,
)
from closy_forge.zeroone.intersection_manifest import SurfaceRepresentation, audit_surface

MECHANICAL_REFERENCE_ROOT = "zeroone/input-mt1-v2"
MECHANICAL_REFERENCE_SURFACE_PATH = f"{MECHANICAL_REFERENCE_ROOT}/rest_reference.glb"
MECHANICAL_REFERENCE_MANIFEST_PATH = f"{MECHANICAL_REFERENCE_ROOT}/surface_manifest.json"
MECHANICAL_REFERENCE_CORNER_MAP_PATH = f"{MECHANICAL_REFERENCE_ROOT}/corner_to_logical.json"
MECHANICAL_REFERENCE_LINEAGE_PATH = f"{MECHANICAL_REFERENCE_ROOT}/binding_lineage.json"
MECHANICAL_REFERENCE_AUDIT_PATH = f"{MECHANICAL_REFERENCE_ROOT}/surface_audit.json"
MECHANICAL_REFERENCE_PROFILE = "MT1-D0-single-LOD-mechanical-rest-reference-v2"
MECHANICAL_REFERENCE_VERSION = "closy.zeroone.mechanical-rest-reference.v2"


def prepare_mechanical_reference_surface(
    package_dir: Path, *, replace_existing: bool = False
) -> dict[str, Any]:
    package = package_dir.resolve(strict=True)
    target = package / MECHANICAL_REFERENCE_ROOT
    if target.exists() and not replace_existing:
        return inspect_mechanical_reference_surface(package)

    authority_before = _canonical_authority_hashes(package)
    package_manifest = _object(package / "manifest.json")
    canonical_digest = package_manifest.get("canonicalPackageDigest")
    simulation_manifest = _object(package / "simulation" / "mesh_manifest.json")
    render_manifest = _object(package / "render" / "mesh_manifest.json")
    rest_state = _object(package / "simulation" / "rest_state.json")
    binding = _object(package / "binding" / "production_binding_contract.json")
    simulation_rest = [
        _vec3(position)
        for mesh in _rows(rest_state, "meshes")
        for position in mesh.get("positions", [])
    ]
    if len(simulation_rest) != int(simulation_manifest.get("vertexCount", -1)):
        raise ValueError("mechanical_reference_simulation_rest_inventory_mismatch")
    logical_positions, influence_counts, settled_deltas = _reconstruct_logical_positions(
        simulation_rest, binding
    )
    logical, dense, corner_rows, lineage = _build_surfaces(
        logical_positions, render_manifest, binding
    )
    logical_audit = audit_surface(logical)
    dense_audit = audit_surface(dense)
    _assert_clean(logical_audit, "logical")
    _assert_clean(dense_audit, "dense")

    target.mkdir(parents=True, exist_ok=True)
    surface_path = package / MECHANICAL_REFERENCE_SURFACE_PATH
    write_indexed_glb(
        surface_path,
        _surface_meshset(dense, render_manifest),
        "material.mt1_mechanical_reference_v2",
        (0.62, 0.67, 0.72, 1.0),
    )
    decoded = read_glb_meshset(surface_path)
    decoded_positions, decoded_triangles = _flatten_meshset(decoded)
    rest_reconstruction_errors = [
        math.dist(expected, actual)
        for expected, actual in zip(dense.positions, decoded_positions, strict=True)
    ]
    decoded_surface = SurfaceRepresentation(
        "mt1_dense_glb_roundtrip",
        decoded_positions,
        decoded_triangles,
        dense.logical_vertex_ids,
        dense.triangle_lineage,
    )
    decoded_audit = audit_surface(decoded_surface)
    _assert_clean(decoded_audit, "glb_roundtrip")
    if topology_hash(decoded) != topology_hash(_surface_meshset(dense, render_manifest)):
        raise ValueError("mechanical_reference_glb_topology_roundtrip_mismatch")

    write_canonical_json(
        package / MECHANICAL_REFERENCE_CORNER_MAP_PATH,
        {
            "schemaVersion": 1,
            "mapVersion": "closy.mt1.corner-to-logical.v2",
            "complete": True,
            "cornerCount": len(corner_rows),
            "logicalDestinationCount": len(logical_positions),
            "rows": corner_rows,
        },
    )
    binding_hash = str(binding.get("integrity", {}).get("productionBindingContractHash"))
    lineage_record = {
        "schemaVersion": 1,
        "lineageVersion": "closy.mt1.binding-lineage.v2",
        "authority": "unchanged_production_binding_contract",
        "canonicalSimulationRestSha256": sha256_file(package / "simulation" / "rest_state.json"),
        "sourceFallbackSha256": sha256_file(package / "render" / "fallback.glb"),
        "sourceRenderManifestSha256": sha256_file(package / "render" / "mesh_manifest.json"),
        "productionBindingContractSha256": sha256_file(
            package / "binding" / "production_binding_contract.json"
        ),
        "productionBindingAuthorityHash": binding_hash,
        "influenceCountDistribution": {
            str(count): influence_counts.count(count) for count in sorted(set(influence_counts))
        },
        "maximumRestReconstructionErrorMeters": max(rest_reconstruction_errors, default=0.0),
        "p95RestReconstructionErrorMeters": _percentile(rest_reconstruction_errors, 0.95),
        "maximumSettledRenderDivergenceMeters": max(settled_deltas, default=0.0),
        "p95SettledRenderDivergenceMeters": _percentile(settled_deltas, 0.95),
        "destinationCount": len(logical_positions),
        "destinationCoverage": 1.0,
        "bidirectionalSurfaceCoverage": {
            "logicalToDenseMissingCount": 0,
            "denseToLogicalMissingCount": 0,
            "maximumCoincidenceErrorMeters": max(rest_reconstruction_errors, default=0.0),
        },
        "rows": lineage,
    }
    write_canonical_json(package / MECHANICAL_REFERENCE_LINEAGE_PATH, lineage_record)
    audit_record = {
        "schemaVersion": 1,
        "profile": MECHANICAL_REFERENCE_PROFILE,
        "settled": False,
        "physicalTruth": False,
        "purpose": "mechanical_reference_only",
        "canonicalAuthorityPromoted": False,
        "phy1Implied": False,
        "logicalSurface": logical_audit,
        "denseSurface": dense_audit,
        "glbRoundTripSurface": decoded_audit,
    }
    write_canonical_json(package / MECHANICAL_REFERENCE_AUDIT_PATH, audit_record)
    _declare_optional_surface(package, surface_path)
    package_manifest_after = _object(package / "manifest.json")
    authority_after = _canonical_authority_hashes(package)
    if authority_before != authority_after:
        raise ValueError("mechanical_reference_canonical_authority_mutated")
    if (
        package_manifest_after.get("canonicalPackageDigest") != canonical_digest
        or package_digest(package_manifest_after.get("inventory", [])) != canonical_digest
    ):
        raise ValueError("mechanical_reference_changed_canonical_package_digest")
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "profile": MECHANICAL_REFERENCE_PROFILE,
        "surfaceVersion": MECHANICAL_REFERENCE_VERSION,
        "surfacePath": MECHANICAL_REFERENCE_SURFACE_PATH,
        "topologyHash": topology_hash(decoded),
        "settled": False,
        "physicalTruth": False,
        "canonicalAuthorityChanged": False,
        "counts": {
            "canonicalSimulationVertexCount": len(simulation_rest),
            "logicalDestinationCount": len(logical_positions),
            "denseCornerCount": len(dense.positions),
            "triangleCount": len(dense.triangles),
            "deletedTriangleCount": 0,
        },
        "hashes": {
            "surfaceSha256": sha256_file(surface_path),
            "surfaceTopologyHash": topology_hash(decoded),
            "surfaceContentHash": geometry_content_hash(decoded),
            "canonicalSimulationRestSha256": lineage_record["canonicalSimulationRestSha256"],
            "sourceFallbackSha256": lineage_record["sourceFallbackSha256"],
            "sourceRenderManifestSha256": lineage_record["sourceRenderManifestSha256"],
            "productionBindingContractSha256": lineage_record["productionBindingContractSha256"],
        },
        "files": {},
    }
    for relative in (
        MECHANICAL_REFERENCE_SURFACE_PATH,
        MECHANICAL_REFERENCE_CORNER_MAP_PATH,
        MECHANICAL_REFERENCE_LINEAGE_PATH,
        MECHANICAL_REFERENCE_AUDIT_PATH,
    ):
        manifest["files"][relative] = sha256_file(package / relative)
    manifest["integrity"] = {"manifestHash": _integrity_hash(manifest)}
    write_canonical_json(package / MECHANICAL_REFERENCE_MANIFEST_PATH, manifest)
    return inspect_mechanical_reference_surface(package)


def inspect_mechanical_reference_surface(package_dir: Path) -> dict[str, Any]:
    package = package_dir.resolve(strict=True)
    manifest_path = package / MECHANICAL_REFERENCE_MANIFEST_PATH
    if not manifest_path.is_file():
        return {"status": "not_present", "reason": "mechanical_reference_absent"}
    try:
        manifest = _object(manifest_path)
        if (
            manifest.get("profile") != MECHANICAL_REFERENCE_PROFILE
            or manifest.get("surfaceVersion") != MECHANICAL_REFERENCE_VERSION
            or manifest.get("settled") is not False
            or manifest.get("physicalTruth") is not False
            or manifest.get("canonicalAuthorityChanged") is not False
        ):
            raise ValueError("mechanical_reference_version_or_authority_mismatch")
        if manifest.get("integrity", {}).get("manifestHash") != _integrity_hash(manifest):
            raise ValueError("mechanical_reference_manifest_forged")
        for relative, expected in manifest.get("files", {}).items():
            if sha256_file(package / relative) != expected:
                raise ValueError(f"mechanical_reference_file_hash_mismatch:{relative}")
        surface = read_glb_meshset(package / MECHANICAL_REFERENCE_SURFACE_PATH)
        if surface.vertex_count != 2496 or surface.triangle_count != 832:
            raise ValueError("mechanical_reference_surface_inventory_mismatch")
        if topology_hash(surface) != manifest.get("hashes", {}).get("surfaceTopologyHash"):
            raise ValueError("mechanical_reference_topology_hash_mismatch")
        package_manifest = _object(package / "manifest.json")
        if package_digest(package_manifest.get("inventory", [])) != package_manifest.get(
            "canonicalPackageDigest"
        ):
            raise ValueError("mechanical_reference_canonical_digest_invalid")
        return {
            "status": "valid",
            "reason": "mechanical_reference_valid",
            "profile": manifest["profile"],
            **manifest["counts"],
            "surfaceSha256": manifest["hashes"]["surfaceSha256"],
            "surfaceTopologyHash": manifest["hashes"]["surfaceTopologyHash"],
        }
    except (KeyError, OSError, TypeError, ValueError) as exc:
        return {"status": "invalid", "reason": str(exc)}


def _reconstruct_logical_positions(
    simulation_rest: list[Vec3], binding: dict[str, Any]
) -> tuple[list[Vec3], list[int], list[float]]:
    records = _rows(binding, "records")
    positions: list[Vec3] = []
    influence_counts: list[int] = []
    errors: list[float] = []
    for expected, record in enumerate(records):
        if int(record.get("globalRenderVertexIndex", -1)) != expected:
            raise ValueError("mechanical_reference_binding_order_invalid")
        source = record.get("sourceTriangle", {})
        indices = source.get("globalVertexIndices") if isinstance(source, dict) else None
        binding_row = record.get("binding", {})
        weights = binding_row.get("weights") if isinstance(binding_row, dict) else None
        if not isinstance(indices, list) or not isinstance(weights, list):
            raise ValueError("mechanical_reference_binding_record_invalid")
        if len(indices) != 3 or len(weights) != 3:
            raise ValueError("mechanical_reference_binding_arity_invalid")
        values = [float(value) for value in weights]
        if (
            any(not math.isfinite(value) or value < 0.0 for value in values)
            or abs(sum(values) - 1.0) > 1.0e-6
        ):
            raise ValueError("mechanical_reference_binding_weight_invalid")
        if any(int(index) < 0 or int(index) >= len(simulation_rest) for index in indices):
            raise ValueError("mechanical_reference_binding_source_out_of_range")
        position = tuple(
            sum(simulation_rest[int(indices[item])][axis] * values[item] for item in range(3))
            for axis in range(3)
        )
        positions.append(position)  # type: ignore[arg-type]
        influence_counts.append(sum(value > 1.0e-9 for value in values))
        declared = record.get("renderPosition")
        if isinstance(declared, list) and len(declared) == 3:
            errors.append(math.dist(position, _vec3(declared)))
    return positions, influence_counts, errors


def _build_surfaces(
    positions: list[Vec3], render_manifest: dict[str, Any], binding: dict[str, Any]
) -> tuple[
    SurfaceRepresentation,
    SurfaceRepresentation,
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    logical_triangles: list[tuple[int, int, int]] = []
    logical_lineage: list[dict[str, Any]] = []
    dense_positions: list[Vec3] = []
    dense_triangles: list[tuple[int, int, int]] = []
    dense_ids: list[int] = []
    dense_lineage: list[dict[str, Any]] = []
    corner_rows: list[dict[str, Any]] = []
    logical_offset = 0
    triangle_index = 0
    for mesh_index, mesh in enumerate(_rows(render_manifest, "meshes")):
        material = str(mesh.get("materialId"))
        panel = str(mesh.get("panelId"))
        local_vertices = mesh.get("vertices", [])
        for local_triangle, row in enumerate(mesh.get("triangles", [])):
            triangle = tuple(logical_offset + int(index) for index in row)
            logical_triangles.append(triangle)  # type: ignore[arg-type]
            lineage = {
                "panelId": panel,
                "materialId": material,
                "renderMeshIndex": mesh_index,
                "localTriangleIndex": local_triangle,
                "sourceTriangleIds": sorted(
                    {
                        int(binding["records"][index]["sourceTriangle"]["globalTriangleIndex"])
                        for index in triangle
                    }
                ),
                "seamIds": [],
                "openingIds": sorted(
                    {
                        str(opening)
                        for index in triangle
                        for opening in binding["records"][index]
                        .get("ownership", {})
                        .get("openingIds", [])
                    }
                ),
            }
            logical_lineage.append(lineage)
            dense_triangle = []
            for corner, logical_index in enumerate(triangle):
                dense_index = len(dense_positions)
                dense_positions.append(positions[logical_index])
                dense_ids.append(logical_index)
                dense_triangle.append(dense_index)
                corner_rows.append(
                    {
                        "cornerId": f"mt1.corner.{dense_index:06d}",
                        "denseCornerIndex": dense_index,
                        "logicalDestinationIndex": logical_index,
                        "triangleIndex": triangle_index,
                        "corner": corner,
                    }
                )
            dense_triangles.append(tuple(dense_triangle))  # type: ignore[arg-type]
            dense_lineage.append(lineage)
            triangle_index += 1
        logical_offset += len(local_vertices)
    if logical_offset != len(positions):
        raise ValueError("mechanical_reference_render_inventory_mismatch")
    logical = SurfaceRepresentation(
        "mt1_logical_rest_reference",
        positions,
        logical_triangles,
        list(range(len(positions))),
        logical_lineage,
    )
    dense = SurfaceRepresentation(
        "mt1_dense_rest_reference",
        dense_positions,
        dense_triangles,
        dense_ids,
        dense_lineage,
    )
    return logical, dense, corner_rows, logical_lineage


def _surface_meshset(surface: SurfaceRepresentation, render_manifest: dict[str, Any]) -> MeshSet:
    meshes: list[Mesh] = []
    position_offset = 0
    triangle_offset = 0
    for mesh in _rows(render_manifest, "meshes"):
        triangle_count = len(mesh.get("triangles", []))
        vertex_count = triangle_count * 3
        vertices = surface.positions[position_offset : position_offset + vertex_count]
        triangles = [(index * 3, index * 3 + 1, index * 3 + 2) for index in range(triangle_count)]
        uvs: list[tuple[float, float]] = []
        panel_uvs = mesh.get("panelUvs", [])
        for triangle in mesh.get("triangles", []):
            for index in triangle:
                uv = panel_uvs[int(index)]
                uvs.append((float(uv[0]), float(uv[1])))
        meshes.append(
            Mesh(
                name=f"{mesh.get('name')}.mt1.v2",
                panel_id=str(mesh.get("panelId")),
                vertices=vertices,
                panel_uvs=uvs,
                triangles=triangles,
                material_id=str(mesh.get("materialId")),
            )
        )
        position_offset += vertex_count
        triangle_offset += triangle_count
    if position_offset != len(surface.positions) or triangle_offset != len(surface.triangles):
        raise ValueError("mechanical_reference_meshset_partition_mismatch")
    return MeshSet(meshes)


def _flatten_meshset(meshset: MeshSet) -> tuple[list[Vec3], list[tuple[int, int, int]]]:
    positions: list[Vec3] = []
    triangles: list[tuple[int, int, int]] = []
    offset = 0
    for mesh in meshset.meshes:
        positions.extend(mesh.vertices)
        triangles.extend(
            (offset + triangle[0], offset + triangle[1], offset + triangle[2])
            for triangle in mesh.triangles
        )
        offset += len(mesh.vertices)
    return positions, triangles


def _assert_clean(audit: dict[str, Any], label: str) -> None:
    topology = audit["topology"]
    failures = {
        "intersections": audit["intersectingPairCount"],
        "duplicates": topology["duplicateFaceCount"],
        "nonManifold": topology["nonManifoldEdgeCount"],
        "tJunctions": topology["tJunctionCount"],
        "degenerates": topology["degenerateTriangleCount"],
    }
    if any(failures.values()):
        raise ValueError(f"mechanical_reference_{label}_not_clean:{failures}")


def _declare_optional_surface(package: Path, surface: Path) -> None:
    manifest_path = package / "manifest.json"
    manifest = _object(manifest_path)
    rows = manifest.get("inventory")
    if not isinstance(rows, list):
        raise ValueError("mechanical_reference_package_inventory_invalid")
    filtered = [dict(row) for row in rows if row.get("path") != MECHANICAL_REFERENCE_SURFACE_PATH]
    filtered.append(
        {
            "path": MECHANICAL_REFERENCE_SURFACE_PATH,
            "role": "optional_zeroone_mechanical_reference_input",
            "canonical": False,
            "required": True,
            "mediaType": "model/gltf-binary",
            "byteSize": surface.stat().st_size,
            "sha256": sha256_file(surface),
        }
    )
    manifest["inventory"] = sorted(filtered, key=lambda row: str(row["path"]))
    write_canonical_json(manifest_path, manifest)


def _canonical_authority_hashes(package: Path) -> dict[str, str]:
    manifest = _object(package / "manifest.json")
    return {
        str(row["path"]): sha256_file(package / str(row["path"]))
        for row in manifest.get("inventory", [])
        if isinstance(row, dict)
        and not str(row.get("path", "")).startswith("zeroone/")
        and (package / str(row.get("path"))).is_file()
    }


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))]


def _integrity_hash(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload["integrity"] = {}
    return hashlib.sha256(canonical_dumps(payload).encode("utf-8")).hexdigest()


def _rows(value: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = value.get(key)
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"mechanical_reference_rows_invalid:{key}")
    return rows


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"mechanical_reference_object_required:{path.name}")
    return value


def _vec3(value: Any) -> Vec3:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("mechanical_reference_vec3_invalid")
    result = tuple(float(component) for component in value)
    if not all(math.isfinite(component) for component in result):
        raise ValueError("mechanical_reference_vec3_nonfinite")
    return result  # type: ignore[return-value]
