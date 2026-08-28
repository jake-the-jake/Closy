from __future__ import annotations

import json
import math
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import Mesh, MeshSet, mesh_bounds
from closy_forge.inspection.cpu_raster import CpuRasterResult, rasterize_settled_garment
from closy_forge.package_io.hashing import sha256_file
from closy_forge.raster import encode_png_rgba
from closy_forge.security.strict_json import load_strict_json_object

DERIVATIVE_DECODER_VERSION = "closy.zeroone.page_pack_decoder.v1"
REVIEW_VERSION = "closy.zeroone.static_review.d0.v1"
_FNV_OFFSET = 1469598103934665603
_FNV_PRIME = 1099511628211
_VIEWS = (
    ("front", 0.0),
    ("right", 90.0),
    ("back", 180.0),
    ("left", -90.0),
)


class DerivativeDecodeError(ValueError):
    pass


@dataclass(frozen=True)
class DecodedPageGeometry:
    meshset: MeshSet
    audit: dict[str, Any]


def decode_v3_page_packs(page_pack_root: Path) -> DecodedPageGeometry:
    root = page_pack_root.resolve(strict=True)
    manifest_path = root / "manifest.json"
    binary_path = root / "packs.bin"
    manifest = load_strict_json_object(manifest_path)
    if manifest.get("schemaVersion") != 3:
        raise DerivativeDecodeError("page_pack_schema_unsupported")
    packs = manifest.get("packs")
    if not isinstance(packs, list) or not packs:
        raise DerivativeDecodeError("page_pack_inventory_empty")
    if not binary_path.is_file():
        raise DerivativeDecodeError("page_pack_binary_missing")
    ids = [int(pack.get("packId", -1)) for pack in packs if isinstance(pack, dict)]
    if len(ids) != len(packs) or ids != list(range(len(packs))):
        raise DerivativeDecodeError("page_pack_id_inventory_or_order_invalid")
    parent_ids = [int(pack.get("parentPackId", -2)) for pack in packs]
    if any(parent >= len(packs) or parent < -1 for parent in parent_ids):
        raise DerivativeDecodeError("page_pack_parent_out_of_range")
    internal_ids = {parent for parent in parent_ids if parent >= 0}
    leaf_ids = [pack_id for pack_id in ids if pack_id not in internal_ids]
    if not leaf_ids:
        raise DerivativeDecodeError("page_pack_leaf_inventory_empty")

    binary = binary_path.read_bytes()
    expected_offset = 0
    meshes: list[Mesh] = []
    consumed: list[dict[str, Any]] = []
    for pack in packs:
        pack_id = int(pack["packId"])
        offset = int(pack.get("offset", -1))
        size = int(pack.get("size", -1))
        if offset != expected_offset or size <= 0 or offset + size > len(binary):
            raise DerivativeDecodeError("page_pack_byte_range_invalid")
        payload = binary[offset : offset + size]
        if _fnv1a64(payload) != int(pack.get("checksum", -1)):
            raise DerivativeDecodeError("page_pack_checksum_mismatch")
        expected_offset += size
        consumed.append(
            {
                "packId": pack_id,
                "offset": offset,
                "size": size,
                "checksum": int(pack["checksum"]),
                "leaf": pack_id in leaf_ids,
            }
        )
        if pack_id in leaf_ids:
            meshes.append(_decode_leaf_payload(payload, pack_id, pack))
    if expected_offset != len(binary):
        raise DerivativeDecodeError("page_pack_binary_has_unclaimed_bytes")

    meshset = MeshSet(meshes)
    if meshset.vertex_count <= 0 or meshset.triangle_count <= 0:
        raise DerivativeDecodeError("page_pack_decoded_geometry_empty")
    return DecodedPageGeometry(
        meshset=meshset,
        audit={
            "schemaVersion": 1,
            "decoderVersion": DERIVATIVE_DECODER_VERSION,
            "candidateGeometryAuthority": "native/page_packs/packs.bin",
            "usesConventionalFallbackGeometry": False,
            "usesSourceVerticesOutsideDerivative": False,
            "usesReportMetadataAsGeometry": False,
            "manifestSha256": sha256_file(manifest_path),
            "binarySha256": sha256_file(binary_path),
            "binaryBytes": len(binary),
            "pagePackCount": len(packs),
            "consumedPagePackCount": len(consumed),
            "leafClusterCount": len(leaf_ids),
            "decodedLeafClusterCount": len(meshes),
            "decodedVertexCount": meshset.vertex_count,
            "decodedTriangleCount": meshset.triangle_count,
            "materialSectionIds": sorted(
                {
                    int(material_id)
                    for mesh in meshes
                    for material_id in mesh.material_id.removeprefix("material.sections.").split(
                        ","
                    )
                    if material_id
                }
            ),
            "bounds": mesh_bounds(meshset),
            "packs": consumed,
        },
    )


def inspect_static_derivative(
    package: Path,
    *,
    review_output: Path,
    review_path_label: str | None = None,
    fault_work_root: Path,
) -> dict[str, Any]:
    package_root = package.resolve(strict=True)
    derivative_root = package_root / "zeroone" / "static-d0" / "derivative"
    page_root = derivative_root / "native" / "page_packs"
    decoded = decode_v3_page_packs(page_root)
    fallback_path = package_root / "render" / "fallback.glb"
    fallback = _review_mesh(read_glb_meshset(fallback_path))
    candidate = _review_mesh(decoded.meshset)
    review = _render_review(
        candidate,
        fallback,
        review_output,
        review_path_label=review_path_label,
    )
    semantics = _semantic_audit(package_root, derivative_root)
    faults = probe_page_pack_failures(page_root, fault_work_root)
    bounds_delta = _bounds_delta(mesh_bounds(candidate), mesh_bounds(fallback))
    triangle_match = candidate.triangle_count == fallback.triangle_count
    status = (
        "pass"
        if (
            triangle_match
            and bounds_delta <= 1e-6
            and semantics["status"] == "pass"
            and faults["status"] == "pass"
            and review["machineStatus"] == "pass"
        )
        else "fail"
    )
    return {
        "schemaVersion": 1,
        "inspectionVersion": REVIEW_VERSION,
        "status": status,
        "candidatePath": "zeroone/static-d0/derivative/native/page_packs/packs.bin",
        "fallbackPath": "render/fallback.glb",
        "candidateDecode": decoded.audit,
        "fallback": {
            "sha256": sha256_file(fallback_path),
            "vertexCount": fallback.vertex_count,
            "triangleCount": fallback.triangle_count,
            "bounds": mesh_bounds(fallback),
        },
        "geometryComparison": {
            "triangleCountMatch": triangle_match,
            "boundsMaximumAbsoluteDeltaMeters": round(bounds_delta, 9),
            "missingOrDuplicatedGeometryDetected": not triangle_match,
            "cullingHolesDetected": any(
                int(view["candidateForegroundPixels"]) == 0 for view in review["views"]
            ),
        },
        "semanticBoundaryAudit": semantics,
        "faultProbes": faults,
        "review": review,
        "humanReview": {
            "status": "not_run",
            "reason": "requires_person_review_of_persisted_contact_sheet",
        },
    }


def probe_page_pack_failures(page_pack_root: Path, work_root: Path) -> dict[str, Any]:
    source = page_pack_root.resolve(strict=True)
    root = work_root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any]] = {}
    for case in ("missing", "corrupt", "reordered"):
        target = root / case
        if target.exists():
            raise DerivativeDecodeError(f"fault_probe_target_exists:{case}")
        shutil.copytree(source, target)
        manifest_path = target / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if case == "missing":
            manifest["packs"].pop()
            manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        elif case == "reordered":
            if len(manifest["packs"]) == 1:
                manifest["packs"][0]["packId"] = 1
            else:
                manifest["packs"] = list(reversed(manifest["packs"]))
            manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        else:
            binary_path = target / "packs.bin"
            payload = bytearray(binary_path.read_bytes())
            payload[0] ^= 0x01
            binary_path.write_bytes(payload)
        try:
            decode_v3_page_packs(target)
        except (DerivativeDecodeError, OSError, ValueError) as exc:
            results[case] = {"status": "pass", "failureReason": str(exc)}
        else:
            results[case] = {"status": "fail", "failureReason": None}
    return {
        "status": "pass" if all(row["status"] == "pass" for row in results.values()) else "fail",
        "missingPage": results["missing"],
        "corruptPage": results["corrupt"],
        "reorderedPage": results["reordered"],
    }


def _decode_leaf_payload(payload: bytes, pack_id: int, manifest_row: dict[str, Any]) -> Mesh:
    cursor = 0

    def vector(fmt: str, width: int) -> list[tuple[float, ...] | int]:
        nonlocal cursor
        if cursor + 8 > len(payload):
            raise DerivativeDecodeError("page_pack_payload_truncated")
        count = struct.unpack_from("<Q", payload, cursor)[0]
        cursor += 8
        if count > 10_000_000:
            raise DerivativeDecodeError("page_pack_vector_count_unbounded")
        scalar_size = struct.calcsize(fmt)
        byte_count = int(count) * width * scalar_size
        if cursor + byte_count > len(payload):
            raise DerivativeDecodeError("page_pack_vector_truncated")
        values = struct.unpack_from(f"<{int(count) * width}{fmt}", payload, cursor)
        cursor += byte_count
        if width == 1:
            return [int(value) for value in values]
        return [
            tuple(float(value) for value in values[index : index + width])
            for index in range(0, len(values), width)
        ]

    positions = cast(list[tuple[float, float, float]], vector("f", 3))
    normals = cast(list[tuple[float, float, float]], vector("f", 3))
    texcoords = cast(list[tuple[float, float]], vector("f", 2))
    tangents = cast(list[tuple[float, float, float, float]], vector("f", 4))
    colors = cast(list[tuple[float, float, float, float]], vector("f", 4))
    indices = cast(list[int], vector("I", 1))
    materials = cast(list[int], vector("I", 1))
    if cursor != len(payload):
        raise DerivativeDecodeError("page_pack_leaf_payload_trailing_bytes")
    vertex_count = len(positions)
    if not vertex_count or not indices or len(indices) % 3:
        raise DerivativeDecodeError("page_pack_leaf_geometry_empty_or_unaligned")
    if not (len(normals) == len(texcoords) == len(tangents) == len(colors) == vertex_count):
        raise DerivativeDecodeError("page_pack_leaf_attribute_count_mismatch")
    if len(materials) != len(indices) // 3:
        raise DerivativeDecodeError("page_pack_leaf_material_count_mismatch")
    if any(index < 0 or index >= vertex_count for index in indices):
        raise DerivativeDecodeError("page_pack_leaf_index_out_of_range")
    scalar_values = [
        value
        for record in (*positions, *normals, *texcoords, *tangents, *colors)
        for value in record
    ]
    if not all(math.isfinite(value) for value in scalar_values):
        raise DerivativeDecodeError("page_pack_leaf_nonfinite_attribute")
    triangle_count = len(indices) // 3
    if int(manifest_row.get("triangleCount", -1)) != triangle_count:
        raise DerivativeDecodeError("page_pack_leaf_triangle_manifest_mismatch")
    material_ids = ",".join(str(value) for value in sorted(set(materials)))
    return Mesh(
        name=f"zeroone.leaf.{pack_id}",
        panel_id="panel.front",
        vertices=list(positions),
        panel_uvs=list(texcoords),
        triangles=[
            (int(indices[index]), int(indices[index + 1]), int(indices[index + 2]))
            for index in range(0, len(indices), 3)
        ],
        material_id=f"material.sections.{material_ids}",
    )


def _semantic_audit(package: Path, derivative: Path) -> dict[str, Any]:
    semantics = load_strict_json_object(package / "semantic" / "garment_graph.json")
    rows_document = load_strict_json_object(derivative / "garment" / "stitch_rows.json")
    rows = rows_document.get("rows")
    if rows_document.get("schemaVersion") != "zeroone.garment-stitch-rows.v1" or not isinstance(
        rows, list
    ):
        raise DerivativeDecodeError("stitch_row_contract_invalid")
    expected_seams = sorted(str(record["id"]) for record in semantics.get("seams", []))
    observed_seams = sorted(str(record.get("seamId")) for record in rows)
    expected_panels = sorted(str(panel_id) for panel_id in semantics.get("panelMapping", {}))
    observed_panels = sorted(
        {
            str(boundary.get("panelId"))
            for row in rows
            for boundary in (
                row.get("panelBoundaryInputA", {}),
                row.get("panelBoundaryInputB", {}),
            )
        }
    )
    expected_openings = sorted(str(record["id"]) for record in semantics.get("openings", []))
    material_map = load_strict_json_object(derivative / "materials.json")
    material_ids = sorted(
        str(record.get("materialId")) for record in material_map.get("materials", [])
    )
    checks = {
        "seamIdsExact": observed_seams == expected_seams,
        "panelIdsExact": observed_panels == expected_panels,
        "openingsPreservedInCanonicalRequest": bool(expected_openings),
        "materialIdsPresent": bool(material_ids),
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "expectedSeamIds": expected_seams,
        "observedSeamIds": observed_seams,
        "expectedPanelIds": expected_panels,
        "observedPanelIds": observed_panels,
        "canonicalOpeningIds": expected_openings,
        "materialIds": material_ids,
        "broadGarmentSemanticsClaimed": False,
    }


def _render_review(
    candidate: MeshSet,
    fallback: MeshSet,
    output: Path,
    *,
    review_path_label: str | None,
) -> dict[str, Any]:
    width = 160
    height = 160
    rendered: list[tuple[CpuRasterResult, CpuRasterResult]] = []
    rows: list[dict[str, Any]] = []
    for view_id, azimuth in _VIEWS:
        camera = {
            "projection": "orthographic",
            "azimuthDegrees": azimuth,
            "elevationDegrees": 4.0,
            "principalPointNormalized": [0.5, 0.5],
        }
        fallback_image = rasterize_settled_garment(
            fallback, label="front", width=width, height=height, camera=camera
        )
        candidate_image = rasterize_settled_garment(
            candidate, label="front", width=width, height=height, camera=camera
        )
        rendered.append((fallback_image, candidate_image))
        intersection = len(fallback_image.foreground & candidate_image.foreground)
        union = len(fallback_image.foreground | candidate_image.foreground)
        iou = intersection / union if union else 0.0
        rows.append(
            {
                "viewId": view_id,
                "azimuthDegrees": azimuth,
                "silhouetteIou": round(iou, 9),
                "fallbackForegroundPixels": len(fallback_image.foreground),
                "candidateForegroundPixels": len(candidate_image.foreground),
                "fallbackRenderedTriangles": fallback_image.rendered_triangle_count,
                "candidateRenderedTriangles": candidate_image.rendered_triangle_count,
            }
        )
    contact = _contact_sheet(rendered, width, height)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encode_png_rgba(width * len(_VIEWS), height * 2, contact))
    return {
        "renderVersion": "closy.zeroone.four_view_contact_sheet.v1",
        "machineStatus": (
            "pass"
            if all(
                float(row["silhouetteIou"]) >= 0.995 and int(row["candidateForegroundPixels"]) > 0
                for row in rows
            )
            else "fail"
        ),
        "camera": {
            "projection": "orthographic",
            "elevationDegrees": 4.0,
            "azimuthDegrees": [value for _, value in _VIEWS],
            "lighting": "deterministic_cpu_flat_material",
        },
        "contactSheetPath": review_path_label or output.name,
        "contactSheetSha256": sha256_file(output),
        "views": rows,
    }


def _contact_sheet(
    rendered: list[tuple[CpuRasterResult, CpuRasterResult]], width: int, height: int
) -> bytes:
    sheet_width = width * len(rendered)
    sheet = bytearray((246, 244, 239, 255) * (sheet_width * height * 2))
    for column, pair in enumerate(rendered):
        for row, image in enumerate(pair):
            for y in range(height):
                source_start = y * width * 4
                target_start = ((row * height + y) * sheet_width + column * width) * 4
                sheet[target_start : target_start + width * 4] = image.rgba[
                    source_start : source_start + width * 4
                ]
    return bytes(sheet)


def _review_mesh(meshset: MeshSet) -> MeshSet:
    return MeshSet(
        [
            Mesh(
                mesh.name,
                "panel.front",
                list(mesh.vertices),
                list(mesh.panel_uvs),
                list(mesh.triangles),
                mesh.material_id,
            )
            for mesh in meshset.meshes
        ]
    )


def _bounds_delta(left: dict[str, list[float]], right: dict[str, list[float]]) -> float:
    return max(
        abs(a - b)
        for key in ("min", "max", "size")
        for a, b in zip(left[key], right[key], strict=True)
    )


def _fnv1a64(payload: bytes) -> int:
    value = _FNV_OFFSET
    for byte in payload:
        value ^= byte
        value = (value * _FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
    return value
