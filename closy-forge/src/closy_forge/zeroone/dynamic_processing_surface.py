from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import audit_glb_geometry, read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet, Vec3, cross, sub
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    package_digest,
    sha256_bytes,
    sha256_file,
    topology_hash,
)

DYNAMIC_PROCESSING_ROOT = "zeroone/input-z2-v1"
DYNAMIC_PROCESSING_SURFACE_PATH = f"{DYNAMIC_PROCESSING_ROOT}/processing_surface.glb"
DYNAMIC_PROCESSING_MANIFEST_PATH = f"{DYNAMIC_PROCESSING_ROOT}/surface_manifest.json"
DYNAMIC_PROCESSING_REMAP_PATH = f"{DYNAMIC_PROCESSING_ROOT}/dense_to_processing_remap.json"
DYNAMIC_PROCESSING_INFLUENCE_PATH = f"{DYNAMIC_PROCESSING_ROOT}/canonical_influence.json"
DYNAMIC_PROCESSING_REPORT_PATH = f"{DYNAMIC_PROCESSING_ROOT}/surface_equivalence_report.json"

DYNAMIC_PROCESSING_VERSION = "closy.zeroone.dynamic_safe_processing_surface.z2.v1"
DYNAMIC_PROCESSING_PROFILE = "closy.dynamic_safe_triangle_filter.z2.v1"
# ZeroOne Dynamic rejects face cross-product squared <= 1e-16, which is triangle area <= 5e-9 m2.
MINIMUM_DYNAMIC_TRIANGLE_AREA_METERS2 = 5.0e-9
MAXIMUM_REMOVED_TRIANGLE_COUNT = 32
MAXIMUM_REMOVED_AREA_METERS2 = 2.0e-8
MAXIMUM_SOURCE_VERTEX_DISTANCE_METERS = 2.0e-7


def prepare_dynamic_processing_surface(
    package_dir: Path, *, replace_existing: bool = False
) -> dict[str, Any]:
    """Create an optional dynamic-safe derivative input without changing canonical authorities."""

    package = package_dir.resolve(strict=True)
    target = package / DYNAMIC_PROCESSING_ROOT
    if target.exists() and not replace_existing:
        audit = inspect_dynamic_processing_surface(package)
        if audit.get("status") != "valid":
            raise ValueError(f"dynamic_processing_surface_exists_invalid:{audit.get('reason')}")
        return audit

    package_manifest = _object(package / "manifest.json")
    canonical_digest_before = package_manifest.get("canonicalPackageDigest")
    source_path = package / "render" / "fallback.glb"
    source = read_glb_meshset(source_path)
    render_manifest = _object(package / "render" / "mesh_manifest.json")
    binding_contract = _object(package / "binding" / "production_binding_contract.json")
    authority_before = _canonical_authority_hashes(package)
    processing, remap, removed = _filter_surface(source)
    influence = _build_canonical_influence(
        source=source,
        processing=processing,
        render_manifest=render_manifest,
        binding_contract=binding_contract,
        remap=remap,
    )
    report = _equivalence_report(source, processing, removed, remap)
    if report["status"] != "pass":
        raise ValueError(
            f"dynamic_processing_surface_equivalence_failed:{report['failureReasons']}"
        )

    target.mkdir(parents=True, exist_ok=True)
    surface_path = package / DYNAMIC_PROCESSING_SURFACE_PATH
    write_indexed_glb(
        surface_path,
        processing,
        "material.dynamic_processing_reference",
        (0.62, 0.67, 0.72, 1.0),
    )
    decoded = read_glb_meshset(surface_path)
    if topology_hash(decoded) != topology_hash(processing):
        raise ValueError("dynamic_processing_surface_glb_topology_roundtrip_mismatch")
    if geometry_content_hash(decoded) != geometry_content_hash(processing):
        raise ValueError("dynamic_processing_surface_glb_content_roundtrip_mismatch")
    glb_audit = audit_glb_geometry(
        surface_path,
        minimum_triangle_area=MINIMUM_DYNAMIC_TRIANGLE_AREA_METERS2,
    )
    if glb_audit.get("status") != "pass":
        raise ValueError("dynamic_processing_surface_glb_invalid")
    _declare_optional_processor_input(package, surface_path)
    package_manifest = _object(package / "manifest.json")
    if (
        package_manifest.get("canonicalPackageDigest") != canonical_digest_before
        or package_digest(package_manifest.get("inventory", [])) != canonical_digest_before
    ):
        raise ValueError("dynamic_processing_surface_changed_canonical_package_digest")

    write_canonical_json(package / DYNAMIC_PROCESSING_REMAP_PATH, remap)
    write_canonical_json(package / DYNAMIC_PROCESSING_INFLUENCE_PATH, influence)
    report["glbRoundTrip"] = {"audit": glb_audit, "status": "pass"}
    report["canonicalAuthority"] = {
        "hashesBefore": authority_before,
        "hashesAfter": _canonical_authority_hashes(package),
        "allCanonicalFilesPreserved": authority_before == _canonical_authority_hashes(package),
        "canonicalPackageDigestBefore": canonical_digest_before,
        "canonicalPackageDigestAfter": package_manifest.get("canonicalPackageDigest"),
    }
    if not report["canonicalAuthority"]["allCanonicalFilesPreserved"]:
        raise ValueError("dynamic_processing_surface_canonical_authority_mutated")
    report["integrity"] = {"reportHash": _integrity_hash(report, "reportHash")}
    write_canonical_json(package / DYNAMIC_PROCESSING_REPORT_PATH, report)
    manifest = {
        "schemaVersion": 1,
        "processingVersion": DYNAMIC_PROCESSING_VERSION,
        "profile": DYNAMIC_PROCESSING_PROFILE,
        "surfacePath": DYNAMIC_PROCESSING_SURFACE_PATH,
        "sourceDensePath": "render/fallback.glb",
        "sourceDenseSha256": sha256_file(source_path),
        "sourceDenseTopologyHash": topology_hash(source),
        "sourceDenseContentHash": geometry_content_hash(source),
        "processingTopologyHash": topology_hash(decoded),
        "processingContentHash": geometry_content_hash(decoded),
        "topologyHash": topology_hash(decoded),
        "canonicalAuthorityChanged": False,
        "counts": {
            "sourceVertexCount": source.vertex_count,
            "sourceTriangleCount": source.triangle_count,
            "processingVertexCount": decoded.vertex_count,
            "processingTriangleCount": decoded.triangle_count,
            "removedTriangleCount": len(removed),
        },
        "thresholds": {
            "minimumDynamicTriangleAreaMeters2Exclusive": MINIMUM_DYNAMIC_TRIANGLE_AREA_METERS2,
            "maximumRemovedTriangleCount": MAXIMUM_REMOVED_TRIANGLE_COUNT,
            "maximumRemovedAreaMeters2": MAXIMUM_REMOVED_AREA_METERS2,
            "maximumSourceVertexDistanceMeters": MAXIMUM_SOURCE_VERTEX_DISTANCE_METERS,
        },
        "files": {
            DYNAMIC_PROCESSING_SURFACE_PATH: sha256_file(surface_path),
            DYNAMIC_PROCESSING_REMAP_PATH: sha256_file(package / DYNAMIC_PROCESSING_REMAP_PATH),
            DYNAMIC_PROCESSING_INFLUENCE_PATH: sha256_file(
                package / DYNAMIC_PROCESSING_INFLUENCE_PATH
            ),
            DYNAMIC_PROCESSING_REPORT_PATH: sha256_file(package / DYNAMIC_PROCESSING_REPORT_PATH),
        },
    }
    write_canonical_json(package / DYNAMIC_PROCESSING_MANIFEST_PATH, manifest)
    return inspect_dynamic_processing_surface(package)


def inspect_dynamic_processing_surface(package_dir: Path) -> dict[str, Any]:
    package = package_dir.resolve(strict=True)
    manifest_path = package / DYNAMIC_PROCESSING_MANIFEST_PATH
    if not manifest_path.is_file():
        return {"status": "not_present", "reason": "dynamic_processing_surface_absent"}
    try:
        manifest = _object(manifest_path)
        if (
            manifest.get("processingVersion") != DYNAMIC_PROCESSING_VERSION
            or manifest.get("profile") != DYNAMIC_PROCESSING_PROFILE
            or manifest.get("canonicalAuthorityChanged") is not False
        ):
            raise ValueError("dynamic_processing_surface_version_mismatch")
        for relative, digest in manifest.get("files", {}).items():
            path = package / str(relative)
            if not path.is_file() or sha256_file(path) != digest:
                raise ValueError(f"dynamic_processing_surface_hash_mismatch:{relative}")
        source = read_glb_meshset(package / "render" / "fallback.glb")
        processing = read_glb_meshset(package / DYNAMIC_PROCESSING_SURFACE_PATH)
        if sha256_file(package / "render" / "fallback.glb") != manifest.get("sourceDenseSha256"):
            raise ValueError("dynamic_processing_surface_source_hash_stale")
        package_manifest = _object(package / "manifest.json")
        inventory = {
            str(row.get("path")): row
            for row in package_manifest.get("inventory", [])
            if isinstance(row, dict)
        }
        declared_surface = inventory.get(DYNAMIC_PROCESSING_SURFACE_PATH)
        if (
            not isinstance(declared_surface, dict)
            or declared_surface.get("sha256")
            != sha256_file(package / DYNAMIC_PROCESSING_SURFACE_PATH)
            or declared_surface.get("canonical") is not False
            or declared_surface.get("role") != "optional_zeroone_processor_input"
            or package_digest(package_manifest.get("inventory", []))
            != package_manifest.get("canonicalPackageDigest")
        ):
            raise ValueError("dynamic_processing_surface_optional_inventory_invalid")
        if topology_hash(source) != manifest.get(
            "sourceDenseTopologyHash"
        ) or geometry_content_hash(source) != manifest.get("sourceDenseContentHash"):
            raise ValueError("dynamic_processing_surface_source_identity_stale")
        if topology_hash(processing) != manifest.get(
            "processingTopologyHash"
        ) or geometry_content_hash(processing) != manifest.get("processingContentHash"):
            raise ValueError("dynamic_processing_surface_identity_mismatch")
        remap = _object(package / DYNAMIC_PROCESSING_REMAP_PATH)
        influence = _object(package / DYNAMIC_PROCESSING_INFLUENCE_PATH)
        report = _object(package / DYNAMIC_PROCESSING_REPORT_PATH)
        if report.get("integrity", {}).get("reportHash") != _integrity_hash(report, "reportHash"):
            raise ValueError("dynamic_processing_surface_report_forged")
        if report.get("status") != "pass" or not _valid_remap(remap, source, processing):
            raise ValueError("dynamic_processing_surface_report_or_remap_invalid")
        if not _valid_influence(influence, processing):
            raise ValueError("dynamic_processing_surface_influence_invalid")
        minimum_area = _minimum_area(processing)
        if minimum_area <= MINIMUM_DYNAMIC_TRIANGLE_AREA_METERS2:
            raise ValueError("dynamic_processing_surface_triangle_below_dynamic_floor")
        authority = report.get("canonicalAuthority", {})
        if (
            authority.get("allCanonicalFilesPreserved") is not True
            or authority.get("hashesBefore") != authority.get("hashesAfter")
            or authority.get("hashesAfter") != _canonical_authority_hashes(package)
            or authority.get("canonicalPackageDigestBefore")
            != package_manifest.get("canonicalPackageDigest")
            or authority.get("canonicalPackageDigestAfter")
            != package_manifest.get("canonicalPackageDigest")
        ):
            raise ValueError("dynamic_processing_surface_canonical_authority_stale")
        return {
            "status": "valid",
            "reason": "dynamic_safe_processing_surface_valid",
            "profile": DYNAMIC_PROCESSING_PROFILE,
            "surfacePath": DYNAMIC_PROCESSING_SURFACE_PATH,
            "processingVertexCount": processing.vertex_count,
            "processingTriangleCount": processing.triangle_count,
            "removedTriangleCount": manifest["counts"]["removedTriangleCount"],
            "minimumTriangleAreaMeters2": minimum_area,
            "topologyHash": topology_hash(processing),
            "contentHash": geometry_content_hash(processing),
        }
    except Exception as exc:
        return {"status": "invalid", "reason": str(exc)}


def _filter_surface(
    source: MeshSet,
) -> tuple[MeshSet, dict[str, Any], list[dict[str, Any]]]:
    meshes: list[Mesh] = []
    source_vertex_rows: list[dict[str, Any]] = []
    source_triangle_rows: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    source_vertex_offset = 0
    source_triangle_offset = 0
    processing_vertex_offset = 0
    processing_triangle_offset = 0
    for mesh_index, mesh in enumerate(source.meshes):
        vertices: list[Vec3] = []
        uvs: list[tuple[float, float]] = []
        triangles: list[tuple[int, int, int]] = []
        for local_triangle, triangle in enumerate(mesh.triangles):
            area = _triangle_area(*(mesh.vertices[index] for index in triangle))
            source_triangle = source_triangle_offset + local_triangle
            if area <= MINIMUM_DYNAMIC_TRIANGLE_AREA_METERS2:
                removed.append(
                    {
                        "sourceTriangle": source_triangle,
                        "meshIndex": mesh_index,
                        "panelId": mesh.panel_id,
                        "localTriangle": local_triangle,
                        "areaMeters2": area,
                        "reason": "at_or_below_zeroone_dynamic_triangle_floor",
                    }
                )
                source_triangle_rows.append(
                    {
                        "sourceTriangle": source_triangle,
                        "processingTriangles": [],
                        "classification": "declared_dynamic_subthreshold_sliver_removed",
                    }
                )
                for source_local in triangle:
                    source_vertex_rows.append(
                        {
                            "sourceDenseVertex": source_vertex_offset + source_local,
                            "processingVertices": [],
                            "classification": "removed_with_subthreshold_sliver",
                        }
                    )
                continue
            new_triangle: list[int] = []
            for source_local in triangle:
                processing_local = len(vertices)
                processing_global = processing_vertex_offset + processing_local
                vertices.append(mesh.vertices[source_local])
                uvs.append(mesh.panel_uvs[source_local])
                new_triangle.append(processing_local)
                source_vertex_rows.append(
                    {
                        "sourceDenseVertex": source_vertex_offset + source_local,
                        "processingVertices": [processing_global],
                        "classification": "identity_retained",
                    }
                )
            processing_triangle = processing_triangle_offset + len(triangles)
            triangles.append(tuple(new_triangle))  # type: ignore[arg-type]
            source_triangle_rows.append(
                {
                    "sourceTriangle": source_triangle,
                    "processingTriangles": [processing_triangle],
                    "classification": "identity_retained",
                }
            )
        meshes.append(Mesh(mesh.name, mesh.panel_id, vertices, uvs, triangles, mesh.material_id))
        source_vertex_offset += len(mesh.vertices)
        source_triangle_offset += len(mesh.triangles)
        processing_vertex_offset += len(vertices)
        processing_triangle_offset += len(triangles)
    processing = MeshSet(meshes)
    if not removed or len(removed) > MAXIMUM_REMOVED_TRIANGLE_COUNT:
        raise ValueError("dynamic_processing_surface_removed_triangle_budget_invalid")
    if sum(float(row["areaMeters2"]) for row in removed) > MAXIMUM_REMOVED_AREA_METERS2:
        raise ValueError("dynamic_processing_surface_removed_area_budget_exceeded")
    return (
        processing,
        {
            "schemaVersion": 1,
            "remapVersion": "closy.dense_to_dynamic_processing_remap.v1",
            "sourceTopologyHash": topology_hash(source),
            "processingTopologyHash": topology_hash(processing),
            "sourceVertexCount": source.vertex_count,
            "processingVertexCount": processing.vertex_count,
            "sourceTriangleCount": source.triangle_count,
            "processingTriangleCount": processing.triangle_count,
            "sourceVertexRows": source_vertex_rows,
            "sourceTriangleRows": source_triangle_rows,
            "complete": True,
        },
        removed,
    )


def _build_canonical_influence(
    *,
    source: MeshSet,
    processing: MeshSet,
    render_manifest: dict[str, Any],
    binding_contract: dict[str, Any],
    remap: dict[str, Any],
) -> dict[str, Any]:
    contract_records = {
        int(row["globalRenderVertexIndex"]): row for row in binding_contract.get("records", [])
    }
    expanded_to_logical = _expanded_to_logical(source, render_manifest)
    retained = [
        row for row in remap["sourceVertexRows"] if row["classification"] == "identity_retained"
    ]
    rows: list[dict[str, Any]] = []
    for row in retained:
        source_dense = int(row["sourceDenseVertex"])
        processing_vertex = int(row["processingVertices"][0])
        logical = expanded_to_logical[source_dense]
        binding = contract_records.get(logical)
        if binding is None:
            raise ValueError("dynamic_processing_surface_canonical_binding_missing")
        source_triangle = binding.get("sourceTriangle", {})
        rows.append(
            {
                "processingVertex": processing_vertex,
                "sourceDenseVertex": source_dense,
                "canonicalRenderVertex": logical,
                "canonicalSimulationVertexIndices": source_triangle.get("globalVertexIndices", []),
                "weights": binding.get("binding", {}).get("weights", []),
                "canonicalSimulationTriangle": source_triangle.get("globalTriangleIndex"),
                "composition": "canonical_binding_then_processing_identity",
            }
        )
    rows.sort(key=lambda row: int(row["processingVertex"]))
    result = {
        "schemaVersion": 1,
        "influenceVersion": "closy.canonical_to_dynamic_processing_influence.v1",
        "authority": "canonical_production_binding_contract_composed_with_declared_remap",
        "canonicalBindingContractHash": binding_contract["integrity"][
            "productionBindingContractHash"
        ],
        "processingTopologyHash": topology_hash(processing),
        "processingVertexCount": processing.vertex_count,
        "maximumCanonicalInfluencesPerProcessingVertex": 3,
        "rows": rows,
        "complete": len(rows) == processing.vertex_count,
    }
    result["integrity"] = {"influenceHash": _integrity_hash(result, "influenceHash")}
    return result


def _expanded_to_logical(source: MeshSet, render_manifest: dict[str, Any]) -> list[int]:
    result: list[int] = []
    logical_offset = 0
    meshes = render_manifest.get("meshes", [])
    if len(meshes) != len(source.meshes):
        raise ValueError("dynamic_processing_surface_render_manifest_mesh_count_mismatch")
    for expanded, logical in zip(source.meshes, meshes, strict=True):
        triangles = logical.get("triangles", [])
        if len(expanded.vertices) != len(triangles) * 3:
            raise ValueError("dynamic_processing_surface_expanded_topology_mismatch")
        for triangle in triangles:
            result.extend(logical_offset + int(index) for index in triangle)
        logical_offset += len(logical.get("vertices", []))
    return result


def _equivalence_report(
    source: MeshSet,
    processing: MeshSet,
    removed: list[dict[str, Any]],
    remap: dict[str, Any],
) -> dict[str, Any]:
    processing_positions = [position for mesh in processing.meshes for position in mesh.vertices]
    maximum_distance = max(
        min(math.dist(position, candidate) for candidate in processing_positions)
        for mesh in source.meshes
        for position in mesh.vertices
    )
    removed_area = sum(float(row["areaMeters2"]) for row in removed)
    minimum_area = _minimum_area(processing)
    checks = {
        "onlyDynamicSubthresholdTrianglesRemoved": all(
            float(row["areaMeters2"]) <= MINIMUM_DYNAMIC_TRIANGLE_AREA_METERS2 for row in removed
        ),
        "removedTriangleCountWithinBudget": len(removed) <= MAXIMUM_REMOVED_TRIANGLE_COUNT,
        "removedAreaWithinBudget": removed_area <= MAXIMUM_REMOVED_AREA_METERS2,
        "sourceVertexDistanceWithinBudget": maximum_distance
        <= MAXIMUM_SOURCE_VERTEX_DISTANCE_METERS,
        "processingTrianglesAboveDynamicFloor": minimum_area
        > MINIMUM_DYNAMIC_TRIANGLE_AREA_METERS2,
        "panelAndMaterialPartitionsPreserved": [
            (mesh.panel_id, mesh.material_id) for mesh in source.meshes
        ]
        == [(mesh.panel_id, mesh.material_id) for mesh in processing.meshes],
        "remapComplete": remap.get("complete") is True,
    }
    return {
        "schemaVersion": 1,
        "reportVersion": "closy.dynamic_processing_surface_equivalence.v1",
        "profile": DYNAMIC_PROCESSING_PROFILE,
        "status": "pass" if all(checks.values()) else "fail",
        "failureReasons": [key for key, value in checks.items() if not value],
        "checks": checks,
        "sourceTopologyHash": topology_hash(source),
        "processingTopologyHash": topology_hash(processing),
        "sourceVertexCount": source.vertex_count,
        "processingVertexCount": processing.vertex_count,
        "sourceTriangleCount": source.triangle_count,
        "processingTriangleCount": processing.triangle_count,
        "removedTriangleCount": len(removed),
        "removedAreaMeters2": removed_area,
        "maximumSourceVertexToProcessingVertexDistanceMeters": maximum_distance,
        "minimumProcessingTriangleAreaMeters2": minimum_area,
        "removedTriangles": removed,
        "canonicalAuthority": {},
        "integrity": {},
    }


def _valid_remap(remap: dict[str, Any], source: MeshSet, processing: MeshSet) -> bool:
    vertex_rows = remap.get("sourceVertexRows", [])
    triangle_rows = remap.get("sourceTriangleRows", [])
    processing_vertices = sorted(
        int(index) for row in vertex_rows for index in row.get("processingVertices", [])
    )
    processing_triangles = sorted(
        int(index) for row in triangle_rows for index in row.get("processingTriangles", [])
    )
    return (
        remap.get("complete") is True
        and remap.get("sourceTopologyHash") == topology_hash(source)
        and remap.get("processingTopologyHash") == topology_hash(processing)
        and len(vertex_rows) == source.vertex_count
        and len(triangle_rows) == source.triangle_count
        and processing_vertices == list(range(processing.vertex_count))
        and processing_triangles == list(range(processing.triangle_count))
    )


def _valid_influence(influence: dict[str, Any], processing: MeshSet) -> bool:
    rows = influence.get("rows", [])
    return (
        influence.get("complete") is True
        and influence.get("processingTopologyHash") == topology_hash(processing)
        and influence.get("processingVertexCount") == processing.vertex_count
        and [row.get("processingVertex") for row in rows] == list(range(processing.vertex_count))
        and all(
            len(row.get("canonicalSimulationVertexIndices", [])) == 3
            and len(row.get("weights", [])) == 3
            for row in rows
        )
        and influence.get("integrity", {}).get("influenceHash")
        == _integrity_hash(influence, "influenceHash")
    )


def _canonical_authority_hashes(package: Path) -> dict[str, str]:
    return {
        path.relative_to(package).as_posix(): sha256_file(path)
        for path in sorted(package.rglob("*"))
        if path.is_file()
        and not path.is_symlink()
        and not path.relative_to(package).as_posix().startswith("zeroone/")
        and path.name != "manifest.json"
    }


def _declare_optional_processor_input(package: Path, surface_path: Path) -> None:
    manifest_path = package / "manifest.json"
    manifest = _object(manifest_path)
    rows = manifest.get("inventory")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("dynamic_processing_surface_package_inventory_invalid")
    filtered = [dict(row) for row in rows if row.get("path") != DYNAMIC_PROCESSING_SURFACE_PATH]
    filtered.append(
        {
            "path": DYNAMIC_PROCESSING_SURFACE_PATH,
            "role": "optional_zeroone_processor_input",
            "canonical": False,
            "required": True,
            "mediaType": "model/gltf-binary",
            "byteSize": surface_path.stat().st_size,
            "sha256": sha256_file(surface_path),
        }
    )
    manifest["inventory"] = sorted(filtered, key=lambda row: str(row["path"]))
    write_canonical_json(manifest_path, manifest)


def _minimum_area(meshset: MeshSet) -> float:
    return min(
        _triangle_area(*(mesh.vertices[index] for index in triangle))
        for mesh in meshset.meshes
        for triangle in mesh.triangles
    )


def _triangle_area(a: Vec3, b: Vec3, c: Vec3) -> float:
    value = cross(sub(b, a), sub(c, a))
    return 0.5 * math.sqrt(sum(component * component for component in value))


def _integrity_hash(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    integrity = dict(payload.get("integrity", {}))
    integrity.pop(field, None)
    payload["integrity"] = integrity
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"dynamic_processing_json_object_required:{path.name}")
    return value
