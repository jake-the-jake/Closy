"""Saved-clean-shell packages for the exposed V2 development lane only."""

from __future__ import annotations

import math
import struct
import zlib
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import (
    audit_glb,
    audit_glb_geometry,
    read_glb_meshset,
    write_indexed_glb,
)
from closy_forge.geometry.mesh_model import MeshSet, Vec3, cross, sub
from closy_forge.manual_provider_c3_v1.deformation import deform_simulation
from closy_forge.manual_provider_c3_v1.reference_deformation import (
    independently_deform_dense_reference,
)
from closy_forge.manual_provider_c3_v1.states import MOTION_STATES, MotionState
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.package_io.paths import assert_safe_child, validate_package_relpath

from .binding import (
    MAX_VERTICES,
    build_binding_v2,
    read_binding_v2,
    reconstruct_v2,
    write_binding_v2,
)
from .checker import FLOAT32_COMPARISON_TOLERANCE, _decode_glb, check_rest

PACKAGE_VERSION = "closy.manual_provider_binding_v2.package.v2"
PACKAGE_BYTE_LIMIT = 2097152
MOTION_LIMIT_METERS = 0.02
P95_LIMIT_METERS = 0.006
UV_EDGE_LIMIT_METERS = 0.012
RUNTIME_PATHS = {
    "cage": "render/fallback.glb",
    "render": "render/clean.glb",
    "binding": "binding/local_frame_v2.bin",
    "codec": "closy.manual_provider.local_frame.v2",
    "reconstruction": "closy_forge.manual_provider_binding_v2.reconstruct_v2",
}


def digest_json(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


def flat_positions(meshset: MeshSet) -> list[Vec3]:
    return [v for mesh in meshset.meshes for v in mesh.vertices]


def with_positions(meshset: MeshSet, positions: list[Vec3]) -> MeshSet:
    if len(positions) != meshset.vertex_count:
        raise ValueError("package_v2_position_count_mismatch")
    meshes, offset = [], 0
    for mesh in meshset.meshes:
        meshes.append(replace(mesh, vertices=positions[offset : offset + len(mesh.vertices)]))
        offset += len(mesh.vertices)
    return MeshSet(meshes)


def _f32_positions(positions: list[Vec3]) -> list[Vec3]:
    data = b"".join(struct.pack("<fff", *p) for p in positions)
    return [(x, y, z) for x, y, z in struct.iter_unpack("<fff", data)]


def write_positions(path: Path, states: list[list[Vec3]]) -> dict[str, Any]:
    if not states or not 1 <= len(states) <= 11 or not 1 <= len(states[0]) <= MAX_VERTICES:
        raise ValueError("package_v2_motion_budget")
    if any(len(s) != len(states[0]) for s in states):
        raise ValueError("package_v2_motion_count_mismatch")
    raw = b"".join(struct.pack("<fff", *p) for state in states for p in state)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zlib.compress(raw, level=9))
    return {
        "stateCount": len(states),
        "vertexCount": len(states[0]),
        "rawBytes": len(raw),
        "rawSha256": sha256_bytes(raw),
    }


def read_positions(path: Path, receipt: dict[str, Any]) -> list[list[Vec3]]:
    count, vertices = receipt["stateCount"], receipt["vertexCount"]
    if (
        type(count) is not int
        or type(vertices) is not int
        or not (1 <= count <= 11 and 1 <= vertices <= MAX_VERTICES)
    ):
        raise ValueError("package_v2_motion_budget")
    expected = count * vertices * 12
    with path.open("rb") as handle:
        compressed = handle.read(PACKAGE_BYTE_LIMIT + 1)
    if len(compressed) > PACKAGE_BYTE_LIMIT:
        raise ValueError("package_v2_motion_byte_budget")
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(compressed, expected + 1)
    except zlib.error as exc:
        raise ValueError("package_v2_motion_compression_invalid") from exc
    if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("package_v2_motion_payload_size_mismatch")
    if receipt["rawBytes"] != expected or receipt["rawSha256"] != sha256_bytes(raw):
        raise ValueError("package_v2_motion_raw_receipt_mismatch")
    flat = [(x, y, z) for x, y, z in struct.iter_unpack("<fff", raw)]
    if any(not math.isfinite(x) for point in flat for x in point):
        raise ValueError("package_v2_motion_nonfinite")
    return [flat[i * vertices : (i + 1) * vertices] for i in range(count)]


def semantic_summary(meshset: MeshSet, document: dict[str, Any]) -> dict[str, Any]:
    panels = {m.panel_id for m in meshset.meshes}
    if "labels" in document:
        accepted = [x for x in document["labels"] if x.get("status") == "accepted"]
        ids = {x["semanticId"] for x in accepted}
        openings = document.get("openingIds", [])
        confidence = min((float(x["confidence"]) for x in accepted), default=0.0)
        if not panels <= ids or not set(openings) <= ids:
            raise ValueError("package_v2_semantic_membership_mismatch")
    elif "panelMapping" in document:
        if panels != set(document["panelMapping"]):
            raise ValueError("package_v2_semantic_membership_mismatch")
        openings = [item["id"] for item in document.get("openings", [])]
        confidence = float(document.get("source", {}).get("confidence", 0))
    else:
        raise ValueError("package_v2_semantic_document_unsupported")
    if (
        not openings
        or len(set(openings)) != len(openings)
        or not math.isfinite(confidence)
        or not (0 <= confidence <= 1)
    ):
        raise ValueError("package_v2_opening_or_confidence_invalid")
    pairs = _seam_pairs(meshset, document)
    return {
        "status": "pass" if confidence >= 0.9 else "fail",
        "panelIds": sorted(panels),
        "openingIds": sorted(openings),
        "minimumAcceptedConfidence": confidence,
        "pairedSeamCount": len(pairs),
        "pairedSeamAvailability": "explicit_vertex_pairs" if pairs else "not_available",
        "namedOpeningGeometry": "not_available_without_boundary_vertex_mapping",
        "physicalSeamMeasurementFromUvEdges": False,
    }


def _seam_pairs(meshset: MeshSet, document: dict[str, Any]) -> list[tuple[str, int, int]]:
    offsets, offset = {}, 0
    for mesh in meshset.meshes:
        offsets[mesh.panel_id] = (offset, len(mesh.vertices))
        offset += len(mesh.vertices)
    result = []
    for pair in document.get("seamPairs", []):
        indices = []
        for key in ("a", "b"):
            endpoint = pair[key]
            panel, index = endpoint["panelId"], endpoint["vertexIndex"]
            if panel not in offsets or type(index) is not int or not 0 <= index < offsets[panel][1]:
                raise ValueError("package_v2_seam_endpoint_invalid")
            indices.append(offsets[panel][0] + index)
        if indices[0] == indices[1] or not isinstance(pair["seamId"], str):
            raise ValueError("package_v2_seam_pair_invalid")
        result.append((pair["seamId"], indices[0], indices[1]))
    if len(result) != len(set(result)):
        raise ValueError("package_v2_duplicate_seam_pair")
    return result


def _boundary_edges(meshset: MeshSet) -> list[tuple[int, int]]:
    boundary: list[tuple[int, int]] = []
    offset = 0
    for mesh in meshset.meshes:
        counts: Counter[tuple[int, int]] = Counter()
        for a, b, c in mesh.triangles:
            for i, j in ((a, b), (b, c), (c, a)):
                counts[min(i, j), max(i, j)] += 1
        boundary.extend((a + offset, b + offset) for (a, b), n in counts.items() if n == 1)
        offset += len(mesh.vertices)
    return boundary


def motion_row(
    clean: MeshSet,
    produced: list[Vec3],
    reference: list[Vec3],
    semantics: dict[str, Any],
    state: MotionState,
    source_id: str,
    family: str,
) -> dict[str, Any]:
    if len(produced) != clean.vertex_count or len(reference) != clean.vertex_count:
        raise ValueError("package_v2_motion_vertex_count_mismatch")
    if any(not math.isfinite(x) for p in (*produced, *reference) for x in p):
        raise ValueError("package_v2_nonfinite_motion")
    errors = [math.dist(a, b) for a, b in zip(produced, reference, strict=True)]
    ordered = sorted(errors)
    uv_edges: list[int] = []
    inverted, collapsed, offset = 0, 0, 0
    for mesh in clean.meshes:
        uv_edges.extend(
            offset + i for i, uv in enumerate(mesh.panel_uvs) if uv[0] <= 1e-7 or uv[0] >= 1 - 1e-7
        )
        for a, b, c in mesh.triangles:
            normal = cross(
                sub(mesh.vertices[b], mesh.vertices[a]), sub(mesh.vertices[c], mesh.vertices[a])
            )
            moved = cross(
                sub(produced[b + offset], produced[a + offset]),
                sub(produced[c + offset], produced[a + offset]),
            )
            collapsed += math.sqrt(sum(x * x for x in moved)) * 0.5 <= 1e-12
            inverted += sum(x * y for x, y in zip(normal, moved, strict=True)) <= 0
        offset += len(mesh.vertices)
    rest = flat_positions(clean)
    edges = _boundary_edges(clean)
    lengths = [math.dist(produced[a], produced[b]) for a, b in edges]
    rest_lengths = [math.dist(rest[a], rest[b]) for a, b in edges]
    boundary_ok = bool(lengths) and min(lengths) > 1e-9 and not collapsed and not inverted
    seams = _seam_pairs(clean, semantics)
    paired: dict[str, Any] = {
        "status": "not_available",
        "pairCount": 0,
        "maximumGapMeters": None,
        "maximumGapDeltaMeters": None,
    }
    if seams:
        paired = {
            "status": "measured",
            "pairCount": len(seams),
            "maximumGapMeters": max(math.dist(produced[a], produced[b]) for _, a, b in seams),
            "maximumGapDeltaMeters": max(
                abs(math.dist(produced[a], produced[b]) - math.dist(rest[a], rest[b]))
                for _, a, b in seams
            ),
        }
    maximum, p95 = ordered[-1], ordered[math.ceil(0.95 * len(ordered)) - 1]
    uv_error = max((errors[i] for i in uv_edges), default=0.0)
    passed = (
        maximum <= MOTION_LIMIT_METERS
        and p95 <= P95_LIMIT_METERS
        and (uv_error <= UV_EDGE_LIMIT_METERS and not inverted and not collapsed and boundary_ok)
    )
    return {
        "sourceId": source_id,
        "family": family,
        "stateId": state.state_id,
        "vertexCount": len(produced),
        "status": "pass" if passed else "fail",
        "maximumErrorMeters": maximum,
        "p95ErrorMeters": p95,
        "rmsErrorMeters": math.sqrt(math.fsum(e * e for e in errors) / len(errors)),
        "maximumUvEdgeReconstructionErrorMeters": uv_error,
        "uvEdgeMetricScope": "legacy_V1_uv_extrema_error_not_physical_seam_gap",
        "uvEdgeVertexCount": len(uv_edges),
        "invertedTriangleCount": inverted,
        "collapsedTriangleCount": collapsed,
        "boundaryGeometry": {
            "preserved": bool(boundary_ok),
            "edgeCount": len(edges),
            "minimumEdgeLengthMeters": min(lengths, default=0.0),
            "perimeterMeters": math.fsum(lengths),
            "restPerimeterMeters": math.fsum(rest_lengths),
        },
        "namedOpeningGeometry": "not_available_without_boundary_vertex_mapping",
        "pairedSeams": paired,
        "referenceImplementation": "immutable_independent_dense_coordinate_deformation_v1",
        "productionImplementation": "serialized_cage_states_plus_local_frame_v2",
    }


def _inventory(root: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("package_v2_symlink_forbidden")
        if path.is_file() and path != root / "manifest.json":
            assert_safe_child(root, path)
            if len(files) >= 64 or path.stat().st_size > PACKAGE_BYTE_LIMIT:
                raise ValueError("package_v2_inventory_budget")
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return files


def build_package_v2(
    clean_path: Path,
    semantics_path: Path,
    output_root: Path,
    *,
    source_id: str,
    family: str,
    source_identity: dict[str, Any] | None = None,
    motion_states: Sequence[MotionState] = MOTION_STATES,
) -> dict[str, Any]:
    """Build from saved clean geometry/semantics; never invoke the V1 campaign.

    The default eleven immutable motion states are mandatory for final evaluation.
    A shorter explicit sequence exists only for tiny package/control tests.
    """
    if output_root.exists():
        raise ValueError("package_v2_output_must_be_fresh")
    if (
        not motion_states
        or len(motion_states) > 11
        or any(s not in MOTION_STATES for s in motion_states)
    ):
        raise ValueError("package_v2_unsupported_motion_states")
    if len({s.state_id for s in motion_states}) != len(motion_states):
        raise ValueError("package_v2_duplicate_motion_state")
    if clean_path.stat().st_size > PACKAGE_BYTE_LIMIT or semantics_path.stat().st_size > 65536:
        raise ValueError("package_v2_input_byte_budget")
    output_root.mkdir(parents=True)
    clean_copy, semantics_copy = (
        output_root / "render/clean.glb",
        output_root / "semantic/source.json",
    )
    clean_copy.parent.mkdir(parents=True)
    semantics_copy.parent.mkdir(parents=True)
    clean_copy.write_bytes(clean_path.read_bytes())
    semantics_copy.write_bytes(semantics_path.read_bytes())
    clean, semantics = _decode_glb(clean_copy), read_json(semantics_copy)
    summary = semantic_summary(clean, semantics)
    bound = build_binding_v2(clean)
    cage_path, binding_path = (
        output_root / "render/fallback.glb",
        output_root / "binding/local_frame_v2.bin",
    )
    write_indexed_glb(
        cage_path,
        bound.cage,
        "manual-provider-binding-v2-cage",
        (0.48, 0.31, 0.22, 1.0),
        normalize_signed_zero=True,
    )
    write_binding_v2(binding_path, bound.binding)
    write_canonical_json(output_root / "reports/binding.json", bound.report)
    rest = check_rest(cage_path, clean_copy, binding_path, bound.report)
    write_canonical_json(output_root / "reports/rest.json", rest)
    write_canonical_json(output_root / "reports/semantics.json", summary)
    cage, binding = read_glb_meshset(cage_path), read_binding_v2(binding_path)
    production_states, reference_states, cage_states, rows = [], [], [], []
    for state in motion_states:
        moved_cage = _f32_positions(flat_positions(deform_simulation(cage, state)))
        production = _f32_positions(reconstruct_v2(with_positions(cage, moved_cage), binding))
        reference = _f32_positions(
            flat_positions(independently_deform_dense_reference(clean, state))
        )
        rows.append(motion_row(clean, production, reference, semantics, state, source_id, family))
        cage_states.append(moved_cage)
        production_states.append(production)
        reference_states.append(reference)
    payloads = {
        name: write_positions(output_root / f"motion/{name}_states.f32.zlib", values)
        for name, values in (
            ("cage", cage_states),
            ("production", production_states),
            ("reference", reference_states),
        )
    }
    write_canonical_json(
        output_root / "motion/manifest.json",
        {
            "format": "little_endian_float32_xyz_zlib9",
            "stateIds": [s.state_id for s in motion_states],
            "stateParameters": [asdict(s) for s in motion_states],
            "payloads": payloads,
            "rows": rows,
        },
    )
    geometry = {
        name: {"geometry": audit_glb_geometry(path), "attributes": audit_glb(path)}
        for name, path in (("render", clean_copy), ("cage", cage_path))
    }
    write_canonical_json(output_root / "reports/geometry.json", geometry)
    manifest: dict[str, Any] = {
        "schemaVersion": 2,
        "packageVersion": PACKAGE_VERSION,
        "sourceId": source_id,
        "family": family,
        "packageId": f"package:{source_id}:manual-provider-binding-v2",
        "scope": "manual_provider_binding_v2_development",
        "units": "metres",
        "sourceIdentity": source_identity or {},
        "inputCleanSha256": sha256_file(clean_copy),
        "inputSemanticsSha256": sha256_file(semantics_copy),
        "runtime": dict(RUNTIME_PATHS),
        "authority": {
            "canonicalGarment": False,
            "globalC3Complete": False,
            "scientificQualification": False,
            "physicalOrMobileEvidence": False,
        },
        "inventory": _inventory(output_root),
    }
    manifest["packageDigest"] = digest_json(manifest)
    write_canonical_json(output_root / "manifest.json", manifest)
    return check_package_v2(output_root)


def check_package_v2(root: Path) -> dict[str, Any]:
    """Verify inventory, independently reconstruct rest, and verify saved motion.

    Motion metrics reuse local geometry math, but production states are checked
    against actual serialized cage reconstruction and reference states against
    the immutable separate dense reference. Rest math is independent in checker.py.
    """
    if (root / "manifest.json").stat().st_size > PACKAGE_BYTE_LIMIT:
        raise ValueError("package_v2_manifest_byte_budget")
    manifest = read_json(root / "manifest.json")
    body = dict(manifest)
    claimed = body.pop("packageDigest", None)
    if manifest.get("packageVersion") != PACKAGE_VERSION or digest_json(body) != claimed:
        raise ValueError("package_v2_manifest_digest_mismatch")
    if manifest.get("runtime") != RUNTIME_PATHS or manifest.get("units") != "metres":
        raise ValueError("package_v2_runtime_contract_invalid")
    for entry in manifest["inventory"]:
        validate_package_relpath(entry["path"])
        assert_safe_child(root, root / entry["path"])
    actual_inventory = _inventory(root)
    if actual_inventory != manifest["inventory"]:
        raise ValueError("package_v2_inventory_mismatch")
    cage_path, render_path = root / "render/fallback.glb", root / "render/clean.glb"
    binding_path = root / "binding/local_frame_v2.bin"
    bound_report = read_json(root / "reports/binding.json")
    rest = check_rest(cage_path, render_path, binding_path, bound_report)
    declared_rest = read_json(root / "reports/rest.json")
    check_rest(cage_path, render_path, binding_path, declared_rest)
    if declared_rest["status"] != rest["status"] or any(
        declared_rest[k] != rest[k]
        for k in (
            "cageSha256",
            "renderSha256",
            "bindingSha256",
            "recordCount",
            "cageVertexCount",
            "panelCount",
        )
    ):
        raise ValueError("package_v2_declared_rest_receipt_mismatch")
    if manifest["inputCleanSha256"] != sha256_file(render_path) or manifest[
        "inputSemanticsSha256"
    ] != (sha256_file(root / "semantic/source.json")):
        raise ValueError("package_v2_input_identity_mismatch")
    clean, cage = read_glb_meshset(render_path), read_glb_meshset(cage_path)
    semantics = read_json(root / "semantic/source.json")
    summary = semantic_summary(clean, semantics)
    if read_json(root / "reports/semantics.json") != summary:
        raise ValueError("package_v2_semantic_summary_mismatch")
    binding = read_binding_v2(binding_path)
    motion = read_json(root / "motion/manifest.json")
    states_by_id = {s.state_id: s for s in MOTION_STATES}
    ids = motion["stateIds"]
    if not ids or len(ids) != len(set(ids)) or any(s not in states_by_id for s in ids):
        raise ValueError("package_v2_motion_state_ids_invalid")
    states = [states_by_id[s] for s in ids]
    if motion["stateParameters"] != [asdict(s) for s in states] or len(motion["rows"]) != len(
        states
    ):
        raise ValueError("package_v2_motion_state_manifest_mismatch")
    payloads = {
        name: read_positions(root / f"motion/{name}_states.f32.zlib", motion["payloads"][name])
        for name in ("cage", "production", "reference")
    }
    if any(len(values) != len(states) for values in payloads.values()):
        raise ValueError("package_v2_motion_state_count_mismatch")
    rows = []
    for i, state in enumerate(states):
        produced, reference, moved = (
            payloads["production"][i],
            payloads["reference"][i],
            payloads["cage"][i],
        )
        runtime = _f32_positions(reconstruct_v2(with_positions(cage, moved), binding))
        independent = _f32_positions(
            flat_positions(independently_deform_dense_reference(clean, state))
        )
        expected_cage = _f32_positions(flat_positions(deform_simulation(cage, state)))
        if any(
            len(a) != len(b)
            or any(
                math.dist(x, y) > FLOAT32_COMPARISON_TOLERANCE for x, y in zip(a, b, strict=True)
            )
            for a, b in ((runtime, produced), (independent, reference), (expected_cage, moved))
        ):
            raise ValueError("package_v2_motion_not_derived_from_serialized_geometry")
        derived = motion_row(
            clean, produced, reference, semantics, state, manifest["sourceId"], manifest["family"]
        )
        declared = motion["rows"][i]
        for key, value in derived.items():
            if isinstance(value, float):
                if (
                    type(declared.get(key)) not in (int, float)
                    or not math.isfinite(declared[key])
                    or (abs(declared[key] - value) > FLOAT32_COMPARISON_TOLERANCE)
                ):
                    raise ValueError(f"package_v2_motion_metric_mismatch:{key}")
            elif declared.get(key) != value:
                raise ValueError(f"package_v2_motion_metric_mismatch:{key}")
        rows.append(derived)
    geometry = {
        name: {"geometry": audit_glb_geometry(path), "attributes": audit_glb(path)}
        for name, path in (("render", render_path), ("cage", cage_path))
    }
    if read_json(root / "reports/geometry.json") != geometry:
        raise ValueError("package_v2_geometry_report_mismatch")
    geometry_ok = all(
        g["geometry"]["status"] == "pass" and g["attributes"]["hasVec4Tangents"]
        for g in geometry.values()
    )
    size = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    return {
        "sourceId": manifest["sourceId"],
        "family": manifest["family"],
        "packageId": manifest["packageId"],
        "packageDigest": claimed,
        "packageBytes": size,
        "status": "pass"
        if rest["status"] == summary["status"] == "pass"
        and geometry_ok
        and all(r["status"] == "pass" for r in rows)
        and size <= PACKAGE_BYTE_LIMIT
        else "fail",
        "rest": rest,
        "semantics": summary,
        "geometry": geometry,
        "rows": rows,
        "binding": {
            **bound_report,
            **rest,
            "coverage": rest["recordCount"] / rest["renderVertexCount"],
            "outOfDomainCount": 0,
        },
        "inputCleanSha256": manifest["inputCleanSha256"],
        "motionStateCount": len(states),
        "independentRestReconstruction": True,
        "motionVerification": "decoded_cage_runtime_and_immutable_dense_reference",
        "geometryValid": geometry_ok,
    }
