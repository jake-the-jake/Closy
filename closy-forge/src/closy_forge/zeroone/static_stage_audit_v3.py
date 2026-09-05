"""Actual oriented float32 triangle coverage, not triangle-count equivalence."""

from __future__ import annotations

import math
import struct
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import _read_glb, read_glb_meshset
from closy_forge.geometry.mesh_model import MeshSet, mesh_bounds
from closy_forge.package_io.hashing import sha256_file
from closy_forge.security.strict_json import load_strict_json_object
from closy_forge.zeroone.derivative_inspection import decode_v3_page_packs
from closy_forge.zeroone.family_adapter_v1 import safe_file, verify_family_adapter
from closy_forge.zeroone.request import _material_id
from closy_forge.zeroone.static_stage_audit_v2 import audit_static_zeroone_stages

AUDIT_VERSION = "closy.zeroone.static_stage_audit.v3"
TOLERANCE = 1e-6
Vertex = tuple[float, ...]  # POSITION.xyz followed by TEXCOORD_0.uv.
Key = tuple[int, tuple[Vertex, ...]]


@dataclass(frozen=True)
class Triangle:
    vertices: tuple[Vertex, ...]
    material: int
    panel: str = ""

    def key(self) -> Key:
        if len(self.vertices) != 3 or self.material < 0:
            raise ValueError("static_v3_triangle_or_material_invalid")
        vertices = tuple(
            tuple(float(struct.unpack("<f", struct.pack("<f", x))[0]) for x in v)
            for v in self.vertices
        )
        if any(len(v) != 5 or not all(math.isfinite(x) for x in v) for v in vertices):
            raise ValueError("static_v3_nonfinite_or_missing_position_uv")
        # Cyclic rotation preserves orientation; sorting vertices would hide reversals.
        return self.material, min(vertices[i:] + vertices[:i] for i in range(3))


def mesh_triangles(meshset: MeshSet, materials: list[list[int]]) -> list[Triangle]:
    result = []
    for mesh, sections in zip(meshset.meshes, materials, strict=True):
        for indices, material in zip(mesh.triangles, sections, strict=True):
            result.append(
                Triangle(
                    tuple((*mesh.vertices[i], *mesh.panel_uvs[i]) for i in indices),
                    material,
                    mesh.panel_id,
                )
            )
    return result


def _near(left: Key, right: Key) -> bool:
    if left[0] != right[0]:
        return False
    a, b = left[1], right[1]
    return any(
        all(
            abs(x - y) <= TOLERANCE
            for i in range(3)
            for x, y in zip(a[i], b[(i + offset) % 3], strict=True)
        )
        for offset in range(3)
    )


def _bounds(keys: list[Key]) -> dict[str, list[float]]:
    points = [v[:3] for _, vertices in keys for v in vertices]
    if not points:
        raise ValueError("static_v3_empty_geometry")
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    return {"min": low, "max": high, "size": [b - a for a, b in zip(low, high, strict=True)]}


def compare_triangle_coverage(
    source: list[Triangle],
    decoded: list[Triangle],
    *,
    source_bounds: dict[str, list[float]] | None = None,
    decoded_bounds: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    """Match multisets bijectively; fail ambiguous tolerance/panel correspondence."""
    source_keys = [t.key() for t in source]
    decoded_keys = [t.key() for t in decoded]
    counts = Counter(source_keys)
    used: Counter[Key] = Counter()
    panels: dict[Key, set[str]] = defaultdict(set)
    for triangle, key in zip(source, source_keys, strict=True):
        panels[key].add(triangle.panel)
    groups = sorted(counts, key=lambda key: min(v[0] for v in key[1]))
    xs = [min(v[0] for v in key[1]) for key in groups]
    ambiguous = 0
    missing = 0
    checks = 0
    matched_panels: Counter[str] = Counter()
    for key in decoded_keys:
        x = min(v[0] for v in key[1])
        candidates = groups[bisect_left(xs, x - TOLERANCE) : bisect_right(xs, x + TOLERANCE)]
        checks += len(candidates)
        if checks > 5_000_000:
            raise ValueError("static_v3_correspondence_work_limit")
        matches = [candidate for candidate in candidates if _near(key, candidate)]
        if len(matches) > 1 or (
            matches and (len(panels[matches[0]]) != 1 or "" in panels[matches[0]])
        ):
            ambiguous += 1
        elif not matches or used[matches[0]] >= counts[matches[0]]:
            missing += 1
        else:
            match = matches[0]
            used[match] += 1
            matched_panels[next(iter(panels[match]))] += 1
    expected_bounds = source_bounds if source_bounds is not None else _bounds(source_keys)
    actual_bounds = decoded_bounds if decoded_bounds is not None else _bounds(decoded_keys)
    deltas = [
        abs(a - b)
        for name in ("min", "max", "size")
        for a, b in zip(expected_bounds[name], actual_bounds[name], strict=True)
    ]
    bounds_pass = len(deltas) == 9 and all(math.isfinite(d) and d <= TOLERANCE for d in deltas)
    maximum = max(deltas, default=math.inf)
    coverage = used == counts and not ambiguous and not missing and bool(source)
    return {
        "passed": coverage and bounds_pass,
        "sourceBytesDecoded": True,
        "representation": "float32_position_xyz_uv_oriented_triangle_material_i32_multiset",
        "tolerancePositionMeters": TOLERANCE,
        "toleranceUV": TOLERANCE,
        "sourceTriangleCount": len(source),
        "decodedTriangleCount": len(decoded),
        "triangleMultisetExactFloat32": Counter(source_keys) == Counter(decoded_keys),
        "triangleCoverageWithinTolerance": coverage,
        "unmatchedDecodedTriangles": missing,
        "ambiguousDecodedTriangles": ambiguous,
        "unmatchedSourceTriangles": sum((counts - used).values()),
        "boundsMaximumAbsoluteDeltaMeters": maximum if math.isfinite(maximum) else None,
        "boundsWithinTolerance": bounds_pass,
        "boundsMandatory": True,
        "panelCorrespondence": {
            "passed": coverage,
            "authority": "derived_from_unique_source_triangle_correspondence",
            "embeddedPanelIdsVerified": False,
            "decoderPlaceholderPanelIdsIgnored": True,
            "matchedTriangleCounts": dict(sorted(matched_panels.items())),
        },
    }


def read_leaf_materials(page_root: Path, audit: dict[str, Any]) -> list[list[int]]:
    """Read signed per-triangle material vectors AFTER the existing bounded decoder."""
    binary = safe_file(page_root, "packs.bin").read_bytes()
    if sha256_file(page_root / "packs.bin") != audit["binarySha256"]:
        raise ValueError("static_v3_packs_changed_after_decode")
    output = []
    for row in audit["packs"]:
        if not row["leaf"]:
            continue
        payload = memoryview(binary)[row["offset"] : row["offset"] + row["size"]]
        offset = 0
        values: list[int] = []
        for field, stride in enumerate((12, 12, 8, 16, 16, 4, 4)):
            if offset + 8 > len(payload):
                raise ValueError("static_v3_material_vector_truncated")
            count = struct.unpack_from("<Q", payload, offset)[0]
            offset += 8
            end = offset + count * stride
            if count > 10_000_000 or end > len(payload):
                raise ValueError("static_v3_material_vector_limit")
            if field == 6:
                values = [item[0] for item in struct.iter_unpack("<i", payload[offset:end])]
            offset = end
        if offset != len(payload) or any(value < 0 for value in values):
            raise ValueError("static_v3_material_i32_invalid")
        output.append(values)
    return output


def audit_static_family(derivative_root: Path, *, adapter_package: Path) -> dict[str, Any]:
    """Reuse V2 real Z4/5/6/8 evidence with strict V3 geometry/material gates."""
    root = derivative_root.absolute()
    adapter = verify_family_adapter(adapter_package)
    derivative = load_strict_json_object(safe_file(root, "derivative.json"))
    if (
        derivative.get("garmentId") != adapter["garmentId"]
        or derivative["source"].get("topologyHash") != adapter["hashes"]["renderTopology"]
        or derivative["source"].get("coordinateConventionId") != "closy-rh-yup-plus-z-v1"
        or derivative["source"].get("unitScaleMetres") != 1
    ):
        raise ValueError("static_v3_derivative_adapter_identity_mismatch")
    for relative in (
        "lod.json",
        "materials.json",
        "garment/stitch_rows.json",
        "native/page_packs/manifest.json",
        "native/page_packs/packs.bin",
    ):
        safe_file(root, relative)
    for row in derivative["files"]:
        safe_file(root, row["path"])
    source_path = safe_file(adapter_package, derivative["source"]["inputAssetRelativePath"])
    gltf, _ = _read_glb(source_path)
    # The frozen importer rejects transforms. Refuse unsupported instancing rather
    # than use the diagnostic GLB reader's mesh-only interpretation as proof.
    nodes = gltf.get("nodes", [])
    if sorted(n.get("mesh", -1) for n in nodes) != list(range(len(gltf["meshes"]))) or any(
        any(key in n for key in ("matrix", "translation", "rotation", "scale", "children"))
        for n in nodes
    ):
        raise ValueError("static_v3_source_nodes_unsupported")
    material_table = gltf["materials"]
    source_materials: list[list[int]] = []
    for mesh in gltf["meshes"]:
        for primitive in mesh["primitives"]:
            material = primitive.get("material")
            if (
                not isinstance(material, int)
                or isinstance(material, bool)
                or not 0 <= material < len(material_table)
                or "TEXCOORD_0" not in primitive["attributes"]
            ):
                raise ValueError("static_v3_source_material_or_uv_invalid")
            count = gltf["accessors"][primitive["indices"]]["count"] // 3
            source_materials.append([material] * count)
    source = read_glb_meshset(source_path)
    graph = load_strict_json_object(safe_file(adapter_package, "semantic/garment_graph.json"))
    source_panels_pass = {mesh.panel_id for mesh in source.meshes} == set(graph["panelMapping"])
    legacy = audit_static_zeroone_stages(root, canonical_package=adapter_package)
    page_root = root / "native/page_packs"
    decoded = decode_v3_page_packs(page_root)
    raw_materials = read_leaf_materials(page_root, decoded.audit)
    coverage = compare_triangle_coverage(
        mesh_triangles(source, source_materials),
        mesh_triangles(decoded.meshset, raw_materials),
        source_bounds=mesh_bounds(source),
        decoded_bounds=mesh_bounds(decoded.meshset),
    )
    materials = load_strict_json_object(root / "materials.json")["materials"]
    material_map_pass = materials == [
        {"denseIndex": i, "materialId": _material_id(str(row.get("name", f"material_{i}")), i)}
        for i, row in enumerate(material_table)
    ]
    coverage["materialTableNamesAndDenseIndicesExact"] = material_map_pass
    coverage["sourcePanelIdsMatchSemanticGraph"] = source_panels_pass
    coverage["passed"] = coverage["passed"] and material_map_pass and source_panels_pass
    legacy["schemaVersion"] = 3
    legacy["auditVersion"] = AUDIT_VERSION
    legacy["legacyCountsOnlyDiagnostic"] = legacy.pop("sourceGeometry")
    legacy["sourceGeometry"] = coverage
    for stage in ("Z4", "Z8"):
        entry = legacy["stages"][stage]
        entry["status"] = (
            "passed" if entry["status"] == "passed" and coverage["passed"] else "failed"
        )
        entry["sourceGeometry"] = coverage
    legacy["claims"]["embeddedPanelIdsVerified"] = False
    legacy["claims"]["physicalQualification"] = False
    for status, key in (
        ("passed", "passedStageIds"),
        ("failed", "failedStageIds"),
        ("not_run", "notRunStageIds"),
    ):
        legacy[key] = [k for k, v in legacy["stages"].items() if v["status"] == status]
    return legacy
