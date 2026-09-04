from __future__ import annotations

import hashlib
import math
import struct
import zlib
from pathlib import Path
from typing import Any

from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.geometry.glb_io import audit_glb, audit_glb_geometry, write_indexed_glb
from closy_forge.geometry.mesh_model import MeshSet, cross, sub
from closy_forge.package_io.hashing import topology_hash

from .binding import build_hybrid_binding
from .common import digest_file, digest_value, write_json
from .corpus import LockedSource
from .deformation import deform_simulation
from .reference_deformation import independently_deform_dense_reference
from .states import MOTION_STATES
from .topology import clean_and_retopologize, semantic_receipt


def _flatten(meshset: MeshSet) -> list[tuple[float, float, float]]:
    return [vertex for mesh in meshset.meshes for vertex in mesh.vertices]


def _encode_positions(states: list[list[tuple[float, float, float]]]) -> tuple[bytes, str]:
    raw = b"".join(
        struct.pack("<fff", *vertex) for state_vertices in states for vertex in state_vertices
    )
    return zlib.compress(raw, level=9), hashlib.sha256(raw).hexdigest()


def decode_positions(
    path: Path, state_count: int, vertex_count: int
) -> list[list[tuple[float, float, float]]]:
    raw = zlib.decompress(path.read_bytes())
    expected = state_count * vertex_count * 12
    if len(raw) != expected:
        raise ValueError("motion_state_payload_size_mismatch")
    values = struct.iter_unpack("<fff", raw)
    flat = [(float(row[0]), float(row[1]), float(row[2])) for row in values]
    return [flat[index * vertex_count : (index + 1) * vertex_count] for index in range(state_count)]


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1)]


def _inverted_triangle_count(
    rest: MeshSet, deformed_vertices: list[tuple[float, float, float]]
) -> int:
    offset = 0
    inverted = 0
    for mesh in rest.meshes:
        moved = deformed_vertices[offset : offset + len(mesh.vertices)]
        for tri in mesh.triangles:
            rest_normal = cross(
                sub(mesh.vertices[tri[1]], mesh.vertices[tri[0]]),
                sub(mesh.vertices[tri[2]], mesh.vertices[tri[0]]),
            )
            moved_normal = cross(
                sub(moved[tri[1]], moved[tri[0]]),
                sub(moved[tri[2]], moved[tri[0]]),
            )
            if sum(a * b for a, b in zip(rest_normal, moved_normal, strict=True)) <= 0.0:
                inverted += 1
        offset += len(mesh.vertices)
    return inverted


def _inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest_file(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    ]


def build_provider_package(source: LockedSource, package_root: Path) -> dict[str, Any]:
    package_root.mkdir(parents=True, exist_ok=False)
    clean, cleanup = clean_and_retopologize(source)
    semantic = semantic_receipt(source, cleanup)
    bound = build_hybrid_binding(clean, package_root / "binding" / "hybrid_binding.bin")
    write_indexed_glb(
        package_root / "render" / "clean.glb",
        clean,
        f"manual-provider-{source.family}",
        (0.58, 0.37, 0.26, 1.0),
        normalize_signed_zero=True,
    )
    write_indexed_glb(
        package_root / "render" / "fallback.glb",
        bound.simulation,
        f"manual-provider-{source.family}-fallback",
        (0.48, 0.31, 0.22, 1.0),
        normalize_signed_zero=True,
    )

    production_states: list[list[tuple[float, float, float]]] = []
    reference_states: list[list[tuple[float, float, float]]] = []
    rows: list[dict[str, Any]] = []
    side_seam_indices: list[int] = []
    vertex_offset = 0
    for mesh in clean.meshes:
        side_seam_indices.extend(
            vertex_offset + index
            for index, uv in enumerate(mesh.panel_uvs)
            if uv[0] <= 1e-9 or uv[0] >= 1.0 - 1e-9
        )
        vertex_offset += len(mesh.vertices)
    for state in MOTION_STATES:
        simulation_state = deform_simulation(bound.simulation, state)
        production = reconstruct_vertices(simulation_state, bound.binding)
        reference = _flatten(independently_deform_dense_reference(clean, state))
        errors = [math.dist(a, b) for a, b in zip(production, reference, strict=True)]
        seam_errors = [errors[index] for index in side_seam_indices]
        inverted_triangle_count = _inverted_triangle_count(clean, production)
        openings_preserved = len(
            production
        ) == clean.vertex_count and bound.binding.render_topology_hash == topology_hash(clean)
        production_states.append(production)
        reference_states.append(reference)
        rows.append(
            {
                "sourceId": source.source_id,
                "family": source.family,
                "stateId": state.state_id,
                "vertexCount": len(reference),
                "coverage": bound.report["coverage"],
                "outOfDomainCount": bound.report["outOfDomainCount"],
                "invertedTriangleCount": inverted_triangle_count,
                "maximumErrorMeters": round(max(errors, default=0.0), 8),
                "rmsErrorMeters": round(
                    math.sqrt(math.fsum(error * error for error in errors) / max(1, len(errors))),
                    8,
                ),
                "p95ErrorMeters": round(_percentile(errors, 0.95), 8),
                "maximumSeamCrackDeltaMeters": round(max(seam_errors, default=0.0), 8),
                "openingsPreserved": openings_preserved,
                "referenceImplementation": "independent_dense_coordinate_deformation_v1",
                "productionImplementation": "low_resolution_solver_plus_hybrid_binding_v1",
            }
        )

    production_bytes, production_raw_receipt = _encode_positions(production_states)
    reference_bytes, reference_raw_receipt = _encode_positions(reference_states)
    motion_root = package_root / "motion"
    motion_root.mkdir(parents=True, exist_ok=True)
    (motion_root / "production_states.f32.zlib").write_bytes(production_bytes)
    (motion_root / "reference_states.f32.zlib").write_bytes(reference_bytes)
    motion_manifest = {
        "schemaVersion": 1,
        "format": "little_endian_float32_xyz_zlib9",
        "stateIds": [state.state_id for state in MOTION_STATES],
        "stateCount": len(MOTION_STATES),
        "vertexCountPerState": len(production_states[0]),
        "productionUncompressedReceipt": production_raw_receipt,
        "referenceUncompressedReceipt": reference_raw_receipt,
        "rows": rows,
    }
    write_json(motion_root / "manifest.json", motion_manifest)
    write_json(package_root / "reports" / "cleanup.json", cleanup)
    write_json(package_root / "reports" / "semantics.json", semantic)
    write_json(package_root / "reports" / "binding.json", bound.report)
    clean_glb_audit = audit_glb(package_root / "render" / "clean.glb")
    clean_geometry_audit = audit_glb_geometry(package_root / "render" / "clean.glb")
    fallback_glb_audit = audit_glb(package_root / "render" / "fallback.glb")
    write_json(
        package_root / "reports" / "render_audit.json",
        {
            "clean": clean_glb_audit,
            "cleanGeometry": clean_geometry_audit,
            "fallback": fallback_glb_audit,
            "independentDecode": True,
            "status": "pass"
            if clean_glb_audit["hasVec4Tangents"]
            and clean_geometry_audit["status"] == "pass"
            and fallback_glb_audit["hasVec4Tangents"]
            else "fail",
        },
    )
    inventory = _inventory(package_root)
    package_id = f"package:{source.source_id}:manual-provider-c3-v1"
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "packageVersion": "closy.manual_provider_c3_v1.package.v1",
        "packageId": package_id,
        "family": source.family,
        "scope": "manual_provider_scoped_C3_development",
        "authority": {
            "canonicalGarment": False,
            "globalC3Complete": False,
            "phase5Complete": False,
            "phase6Complete": False,
            "mobileEvidence": False,
        },
        "lineage": {
            "rawAssetId": source.raw_asset_id,
            "analyzedAssetId": cleanup["analyzedAssetId"],
            "proposedAssetId": cleanup["proposedAssetId"],
            "cleanAssetId": cleanup["cleanAssetId"],
            "boundAssetId": bound.report["boundAssetId"],
            "packageId": package_id,
        },
        "licence": source.document["licence"],
        "inventory": inventory,
        "inventoryDigest": digest_value(inventory),
    }
    manifest["packageDigest"] = digest_value(manifest)
    write_json(package_root / "manifest.json", manifest)
    return {
        "sourceId": source.source_id,
        "family": source.family,
        "packageId": package_id,
        "packageDigest": manifest["packageDigest"],
        "packageBytes": sum(item["bytes"] for item in inventory)
        + (package_root / "manifest.json").stat().st_size,
        "cleanup": cleanup,
        "semantics": semantic,
        "binding": bound.report,
        "renderAudit": read_render_audit(package_root),
        "rows": rows,
    }


def read_render_audit(package_root: Path) -> dict[str, Any]:
    from .common import read_json

    return read_json(package_root / "reports" / "render_audit.json")
