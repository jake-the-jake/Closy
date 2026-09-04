from __future__ import annotations

import hashlib
import math
import struct
import zlib
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import read_binding
from closy_forge.geometry.glb_io import audit_glb, audit_glb_geometry, read_glb_meshset

from .common import digest_file, digest_value, read_json, validate_embedded_digest

FLOAT32_SERIALIZATION_TOLERANCE = 5e-8


def _inversion_count(meshset: Any, positions: list[tuple[float, float, float]]) -> int:
    offset = 0
    total = 0
    for mesh in meshset.meshes:
        moved = positions[offset : offset + len(mesh.vertices)]
        for first, second, third in mesh.triangles:
            rest_ab = tuple(
                mesh.vertices[second][axis] - mesh.vertices[first][axis] for axis in range(3)
            )
            rest_ac = tuple(
                mesh.vertices[third][axis] - mesh.vertices[first][axis] for axis in range(3)
            )
            moved_ab = tuple(moved[second][axis] - moved[first][axis] for axis in range(3))
            moved_ac = tuple(moved[third][axis] - moved[first][axis] for axis in range(3))
            rest_normal = (
                rest_ab[1] * rest_ac[2] - rest_ab[2] * rest_ac[1],
                rest_ab[2] * rest_ac[0] - rest_ab[0] * rest_ac[2],
                rest_ab[0] * rest_ac[1] - rest_ab[1] * rest_ac[0],
            )
            moved_normal = (
                moved_ab[1] * moved_ac[2] - moved_ab[2] * moved_ac[1],
                moved_ab[2] * moved_ac[0] - moved_ab[0] * moved_ac[2],
                moved_ab[0] * moved_ac[1] - moved_ab[1] * moved_ac[0],
            )
            if sum(a * b for a, b in zip(rest_normal, moved_normal, strict=True)) <= 0.0:
                total += 1
        offset += len(mesh.vertices)
    return total


def _decode(
    path: Path, state_count: int, vertex_count: int
) -> tuple[list[list[tuple[float, float, float]]], str]:
    raw = zlib.decompress(path.read_bytes())
    if len(raw) != state_count * vertex_count * 12:
        raise ValueError("checker_motion_payload_size_mismatch")
    flat = [
        (float(row[0]), float(row[1]), float(row[2])) for row in struct.iter_unpack("<fff", raw)
    ]
    states = [
        flat[index * vertex_count : (index + 1) * vertex_count] for index in range(state_count)
    ]
    return states, hashlib.sha256(raw).hexdigest()


def _verify_package(package_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = read_json(package_root / "manifest.json")
    validate_embedded_digest(manifest, "packageDigest")
    inventory = [
        {
            "path": path.relative_to(package_root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest_file(path),
        }
        for path in sorted(package_root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    ]
    if inventory != manifest["inventory"] or digest_value(inventory) != manifest["inventoryDigest"]:
        raise ValueError("checker_package_inventory_mismatch")
    clean = audit_glb(package_root / "render" / "clean.glb")
    clean_geometry = audit_glb_geometry(package_root / "render" / "clean.glb")
    clean_meshset = read_glb_meshset(package_root / "render" / "clean.glb")
    fallback = audit_glb(package_root / "render" / "fallback.glb")
    if not clean["hasVec4Tangents"] or not fallback["hasVec4Tangents"]:
        raise ValueError("checker_tangent_vec4_missing")
    if clean_geometry["status"] != "pass":
        raise ValueError("checker_clean_glb_geometry_failed")
    binding = read_binding(package_root / "binding" / "hybrid_binding.bin")
    if manifest["lineage"]["boundAssetId"] != f"bound:{binding.render_topology_hash[:20]}":
        raise ValueError("checker_bound_identity_invalid")
    motion = read_json(package_root / "motion" / "manifest.json")
    state_count = int(motion["stateCount"])
    vertex_count = int(motion["vertexCountPerState"])
    production, production_sha = _decode(
        package_root / "motion" / "production_states.f32.zlib", state_count, vertex_count
    )
    reference, reference_sha = _decode(
        package_root / "motion" / "reference_states.f32.zlib", state_count, vertex_count
    )
    if production_sha != motion["productionUncompressedReceipt"]:
        raise ValueError("checker_production_motion_receipt_mismatch")
    if reference_sha != motion["referenceUncompressedReceipt"]:
        raise ValueError("checker_reference_motion_receipt_mismatch")
    rows = []
    side_seam_indices: list[int] = []
    vertex_offset = 0
    for mesh in clean_meshset.meshes:
        side_seam_indices.extend(
            vertex_offset + index
            for index, uv in enumerate(mesh.panel_uvs)
            if uv[0] <= 1e-7 or uv[0] >= 1.0 - 1e-7
        )
        vertex_offset += len(mesh.vertices)
    for state_id, produced, expected, declared in zip(
        motion["stateIds"], production, reference, motion["rows"], strict=True
    ):
        errors = [math.dist(a, b) for a, b in zip(produced, expected, strict=True)]
        seam_errors = [errors[index] for index in side_seam_indices]
        inverted = _inversion_count(clean_meshset, produced)
        ordered = sorted(errors)
        p95 = ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]
        recomputed = {
            **declared,
            "stateId": state_id,
            "maximumErrorMeters": round(max(errors, default=0.0), 8),
            "rmsErrorMeters": round(
                math.sqrt(math.fsum(error * error for error in errors) / max(1, len(errors))), 8
            ),
            "p95ErrorMeters": round(p95, 8),
            "maximumSeamCrackDeltaMeters": round(max(seam_errors, default=0.0), 8),
            "invertedTriangleCount": inverted,
        }
        for metric in (
            "maximumErrorMeters",
            "rmsErrorMeters",
            "p95ErrorMeters",
            "maximumSeamCrackDeltaMeters",
        ):
            if (
                abs(float(recomputed[metric]) - float(declared[metric]))
                > FLOAT32_SERIALIZATION_TOLERANCE
            ):
                raise ValueError(f"checker_motion_row_mismatch:{metric}")
        if recomputed["invertedTriangleCount"] != declared["invertedTriangleCount"]:
            raise ValueError("checker_motion_row_mismatch:invertedTriangleCount")
        rows.append(recomputed)
    return manifest, rows


def check_publication(publication_root: Path, result_path: Path) -> dict[str, Any]:
    result = read_json(result_path)
    validate_embedded_digest(result, "resultDigest")
    protocol = read_json(
        publication_root.parents[2] / "fixtures" / "manual_provider_c3_v1" / "protocol.json"
    )
    validate_embedded_digest(protocol, "protocolDigest")
    package_records = sorted(result["packageRecords"], key=lambda item: item["sourceId"])
    checked_packages = []
    all_rows = []
    for record in package_records:
        package_root = publication_root / "packages" / record["sourceId"]
        manifest, rows = _verify_package(package_root)
        if manifest["packageDigest"] != record["packageDigest"]:
            raise ValueError("checker_result_package_digest_mismatch")
        checked_packages.append(manifest)
        all_rows.extend(rows)
    if len(checked_packages) != 9 or len(all_rows) != 99:
        raise ValueError("checker_denominator_mismatch")
    observed = result["metrics"]
    recomputed = {
        "sourceCount": len(checked_packages),
        "familyCount": len({manifest["family"] for manifest in checked_packages}),
        "evaluationRowCount": len(all_rows),
        "motionStateCount": len({row["stateId"] for row in all_rows}),
        "maximumMotionErrorMeters": max(float(row["maximumErrorMeters"]) for row in all_rows),
        "maximumP95MotionErrorMeters": max(float(row["p95ErrorMeters"]) for row in all_rows),
        "maximumSeamCrackDeltaMeters": max(
            float(row["maximumSeamCrackDeltaMeters"]) for row in all_rows
        ),
        "totalInvertedTriangleCount": sum(int(row["invertedTriangleCount"]) for row in all_rows),
        "openingsPreservedRate": math.fsum(bool(row["openingsPreserved"]) for row in all_rows)
        / len(all_rows),
    }
    for key, value in recomputed.items():
        if isinstance(value, float):
            matches = abs(float(observed[key]) - value) <= FLOAT32_SERIALIZATION_TOLERANCE
        else:
            matches = observed[key] == value
        if not matches:
            raise ValueError(f"checker_result_metric_mismatch:{key}")
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "checkerVersion": "closy.manual_provider_c3_v1.independent_checker.v1",
        "status": "pass",
        "resultDigest": result["resultDigest"],
        "protocolDigest": protocol["protocolDigest"],
        "packageCount": len(checked_packages),
        "evaluationRowCount": len(all_rows),
        "decodedGlbCount": len(checked_packages) * 2,
        "decodedBindingCount": len(checked_packages),
        "decodedMotionPayloadCount": len(checked_packages) * 2,
        "float32SerializationTolerance": FLOAT32_SERIALIZATION_TOLERANCE,
        "recomputedMetrics": recomputed,
    }
    report["checkerDigest"] = digest_value(report)
    return report
