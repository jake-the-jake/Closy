from __future__ import annotations

import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.geometry.mesh_model import mesh_bounds
from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_io.paths import validate_package_relpath
from closy_forge.security.strict_json import load_strict_json_object
from closy_forge.zeroone.derivative_inspection import decode_v3_page_packs

STATIC_STAGE_AUDIT_V2 = "closy.zeroone.static_stage_audit.v2"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class StaticStageAuditError(ValueError):
    pass


def audit_static_zeroone_stages(
    derivative_root: Path,
    *,
    canonical_package: Path | None = None,
) -> dict[str, Any]:
    root = derivative_root.resolve(strict=True)
    derivative = load_strict_json_object(root / "derivative.json")
    lod = load_strict_json_object(root / "lod.json")
    materials = load_strict_json_object(root / "materials.json")
    stitches = load_strict_json_object(root / "garment" / "stitch_rows.json")
    page_root = root / "native" / "page_packs"
    page_manifest = load_strict_json_object(page_root / "manifest.json")
    decoded = decode_v3_page_packs(page_root)
    inventory = _validate_derivative_inventory(root, derivative)
    source_identity = _audit_source_identity(derivative, canonical_package)
    source_geometry = _audit_source_geometry(derivative, decoded.meshset, canonical_package)
    semantics = _audit_semantics(stitches, materials, canonical_package)
    hierarchy = _audit_hierarchy(page_manifest)
    lod_audit = _audit_lod(lod)
    semantic_counts = {
        "materialCount": len(_rows(materials, "materials")),
        "stitchRowCount": len(_rows(stitches, "rows")),
    }
    nanite = _mapping(derivative.get("nanite"), "static_derivative_nanite_missing")
    counts_match = (
        int(nanite.get("clusterCount", -1)) == decoded.audit["leafClusterCount"]
        and int(nanite.get("hierarchyNodeCount", -1)) == len(page_manifest["packs"])
        and int(nanite.get("pagePackCount", -1)) == len(page_manifest["packs"])
        and source_geometry["triangleCoverageExact"] is not False
    )
    stages = {
        "Z3": {
            "status": "not_run",
            "reason": ("frozen_processor_emits_no_per_detail_classification_or_detail_stream"),
            "actualBytesDecoded": False,
        },
        "Z4": {
            "status": "passed" if counts_match else "failed",
            "reason": "actual_leaf_cluster_payloads_independently_decoded",
            "actualBytesDecoded": True,
            "clusterCount": decoded.audit["decodedLeafClusterCount"],
            "triangleCount": decoded.audit["decodedTriangleCount"],
            "sourceGeometry": source_geometry,
        },
        "Z5": {
            "status": "passed" if hierarchy["passed"] and lod_audit["passed"] else "failed",
            "reason": "actual_parent_links_and_lod_report_independently_checked",
            "actualBytesDecoded": True,
            "hierarchy": hierarchy,
            "lod": lod_audit,
        },
        "Z6": {
            "status": "passed" if hierarchy["passed"] else "failed",
            "reason": "actual_page_ranges_checksums_roots_and_dependency_closure_checked",
            "actualBytesDecoded": True,
            "pagePackCount": decoded.audit["pagePackCount"],
            "residentRootCount": hierarchy["rootCount"],
            "dependencyClosure": hierarchy["dependencyClosure"],
        },
        "Z7": {
            "status": "not_run",
            "reason": "frozen_processor_emits_no_recorded_bake_or_procedural_detail_payload",
            "actualBytesDecoded": False,
        },
        "Z8": {
            "status": "passed" if source_identity["passed"] and semantics["passed"] else "failed",
            "reason": "actual_derivative_inventory_hashes_and_compatibility_contract_checked",
            "actualBytesDecoded": True,
            "canonicalDerivativeHash": derivative.get("canonicalDerivativeHash"),
            "sourceIdentity": source_identity,
            "semantics": semantics,
        },
    }
    return {
        "schemaVersion": 2,
        "auditVersion": STATIC_STAGE_AUDIT_V2,
        "classification": "optional_static_derivative_not_canonical_authority",
        "derivativeDigest": sha256_file(root / "derivative.json"),
        "pageManifestDigest": sha256_file(page_root / "manifest.json"),
        "pageBinaryDigest": sha256_file(page_root / "packs.bin"),
        "decoded": decoded.audit,
        "semanticCounts": semantic_counts,
        "inventory": inventory,
        "sourceIdentity": source_identity,
        "sourceGeometry": source_geometry,
        "semantics": semantics,
        "stages": stages,
        "passedStageIds": [key for key, value in stages.items() if value["status"] == "passed"],
        "notRunStageIds": [key for key, value in stages.items() if value["status"] == "not_run"],
        "failedStageIds": [key for key, value in stages.items() if value["status"] == "failed"],
        "claims": {
            "dynamicZ2": False,
            "mobile": False,
            "gpu": False,
            "canonicalAuthorityChanged": False,
        },
    }


def _validate_derivative_inventory(root: Path, derivative: Mapping[str, Any]) -> dict[str, Any]:
    if derivative.get("schemaVersion") != "zeroone.closy.static-derivative.v1":
        raise StaticStageAuditError("static_derivative_version_unsupported")
    compatibility = _mapping(
        derivative.get("compatibility"), "static_derivative_compatibility_missing"
    )
    if compatibility != {
        "canonicalAuthority": "Closy package",
        "conventionalFallbackRequired": True,
        "optionalDerivative": True,
        "safeToDeleteAndRebuild": True,
    }:
        raise StaticStageAuditError("static_derivative_authority_invalid")
    files = _rows(derivative, "files")
    observed: list[dict[str, str]] = []
    for row in files:
        path = row.get("path")
        digest = row.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise StaticStageAuditError("static_derivative_inventory_invalid")
        try:
            validate_package_relpath(path)
        except ValueError as error:
            raise StaticStageAuditError("static_derivative_inventory_path_invalid") from error
        if not _SHA256_RE.fullmatch(digest):
            raise StaticStageAuditError("static_derivative_inventory_digest_invalid")
        candidate = root / path
        if candidate.is_symlink() or not candidate.is_file() or sha256_file(candidate) != digest:
            raise StaticStageAuditError("static_derivative_file_identity_mismatch")
        observed.append({"path": path, "sha256": digest})
    if len(observed) != 7 or len({row["path"] for row in observed}) != 7:
        raise StaticStageAuditError("static_derivative_inventory_denominator_invalid")
    return {"declaredFileCount": 7, "allDeclaredHashesMatch": True, "files": observed}


def _audit_hierarchy(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if manifest.get("schemaVersion") != 3:
        raise StaticStageAuditError("static_page_manifest_version_unsupported")
    packs = _rows(manifest, "packs")
    ids = [int(row.get("packId", -1)) for row in packs]
    if ids != list(range(len(packs))):
        raise StaticStageAuditError("static_page_ids_invalid")
    parents = {int(row["packId"]): int(row.get("parentPackId", -2)) for row in packs}
    if any(parent < -1 or parent >= len(packs) for parent in parents.values()):
        raise StaticStageAuditError("static_page_parent_invalid")
    roots = [pack_id for pack_id, parent in parents.items() if parent == -1]
    if not roots:
        raise StaticStageAuditError("static_page_root_missing")
    closure: dict[int, tuple[int, ...]] = {}
    for pack_id in ids:
        path: list[int] = []
        current = pack_id
        while current != -1:
            if current in path:
                raise StaticStageAuditError("static_page_hierarchy_cycle")
            path.append(current)
            current = parents[current]
        closure[pack_id] = tuple(path)
    return {
        "passed": True,
        "nodeCount": len(packs),
        "rootCount": len(roots),
        "rootIds": roots,
        "dependencyClosure": all(path[-1] in roots for path in closure.values()),
        "maximumDepth": max(len(path) for path in closure.values()),
    }


def _audit_lod(lod: Mapping[str, Any]) -> dict[str, Any]:
    numeric_errors = _collect_named_numbers(lod, "error")
    finite = all(math.isfinite(value) for value in numeric_errors)
    nonnegative = all(value >= 0.0 for value in numeric_errors)
    levels = _rows(lod, "levels")
    measured = [float(row["measuredError"]) for row in levels if "measuredError" in row]
    monotonic = all(left <= right for left, right in zip(measured, measured[1:], strict=False))
    return {
        "passed": finite and nonnegative and monotonic,
        "reportedErrorValueCount": len(numeric_errors),
        "allReportedErrorsFiniteNonnegative": finite and nonnegative,
        "measuredErrorMonotonicNondecreasing": monotonic,
        "lod0Only": not levels,
        "selectedSourceTriangleCount": lod.get("selectedSourceTriangleCount"),
        "selectedLodTriangleCount": lod.get("selectedLodTriangleCount"),
        "selectedLodTriangleRatio": lod.get("selectedLodTriangleRatio"),
    }


def _collect_named_numbers(value: Any, name_fragment: str) -> list[float]:
    output: list[float] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if name_fragment in str(key).lower() and isinstance(child, int | float):
                output.append(float(child))
            output.extend(_collect_named_numbers(child, name_fragment))
    elif isinstance(value, list):
        for child in value:
            output.extend(_collect_named_numbers(child, name_fragment))
    return output


def _mapping(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StaticStageAuditError(code)
    return value


def _rows(value: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    rows = value.get(key)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise StaticStageAuditError(f"static_{key}_invalid")
    return rows


def _audit_source_identity(
    derivative: Mapping[str, Any], canonical_package: Path | None
) -> dict[str, Any]:
    source = _mapping(derivative.get("source"), "static_derivative_source_missing")
    required_digests = ("manifestSha256", "inputContentSha256", "topologyHash")
    declared_valid = all(
        isinstance(source.get(key), str) and _SHA256_RE.fullmatch(str(source[key]))
        for key in required_digests
    )
    if not declared_valid:
        raise StaticStageAuditError("static_derivative_source_identity_invalid")
    if canonical_package is None:
        return {
            "passed": True,
            "declaredIdentityValid": True,
            "canonicalBytesCompared": False,
            "reason": "canonical_package_not_supplied",
        }
    package = canonical_package.resolve(strict=True)
    relative = source.get("inputAssetRelativePath")
    if not isinstance(relative, str):
        raise StaticStageAuditError("static_derivative_source_path_invalid")
    try:
        validate_package_relpath(relative)
    except ValueError as error:
        raise StaticStageAuditError("static_derivative_source_path_invalid") from error
    manifest = package / "manifest.json"
    asset = package / relative
    passed = (
        not manifest.is_symlink()
        and not asset.is_symlink()
        and manifest.is_file()
        and asset.is_file()
        and sha256_file(manifest) == source["manifestSha256"]
        and sha256_file(asset) == source["inputContentSha256"]
    )
    return {
        "passed": passed,
        "declaredIdentityValid": True,
        "canonicalBytesCompared": True,
        "manifestHashMatch": manifest.is_file()
        and sha256_file(manifest) == source["manifestSha256"],
        "inputAssetHashMatch": asset.is_file()
        and sha256_file(asset) == source["inputContentSha256"],
    }


def _audit_source_geometry(
    derivative: Mapping[str, Any], decoded: Any, canonical_package: Path | None
) -> dict[str, Any]:
    if canonical_package is None:
        return {
            "sourceBytesDecoded": False,
            "triangleCoverageExact": None,
            "boundsMaximumAbsoluteDeltaMeters": None,
        }
    source = _mapping(derivative.get("source"), "static_derivative_source_missing")
    relative = str(source["inputAssetRelativePath"])
    original = read_glb_meshset(canonical_package.resolve(strict=True) / relative)
    original_bounds = mesh_bounds(original)
    decoded_bounds = mesh_bounds(decoded)
    bounds_delta = max(
        abs(left - right)
        for key in ("min", "max", "size")
        for left, right in zip(original_bounds[key], decoded_bounds[key], strict=True)
    )
    return {
        "sourceBytesDecoded": True,
        "sourceTriangleCount": original.triangle_count,
        "decodedTriangleCount": decoded.triangle_count,
        "triangleCoverageExact": original.triangle_count == decoded.triangle_count,
        "boundsMaximumAbsoluteDeltaMeters": round(bounds_delta, 9),
        "boundsExactWithinOneMicrometre": bounds_delta <= 1e-6,
    }


def _audit_semantics(
    stitches: Mapping[str, Any],
    materials: Mapping[str, Any],
    canonical_package: Path | None,
) -> dict[str, Any]:
    rows = _rows(stitches, "rows")
    material_rows = _rows(materials, "materials")
    material_ids = sorted(str(row.get("materialId")) for row in material_rows)
    observed_seams = sorted(str(row.get("seamId")) for row in rows)
    observed_panels = sorted(
        {
            str(boundary.get("panelId"))
            for row in rows
            for boundary in (
                row.get("panelBoundaryInputA", {}),
                row.get("panelBoundaryInputB", {}),
            )
            if isinstance(boundary, dict)
        }
    )
    if canonical_package is None:
        passed = bool(material_ids)
        return {
            "passed": passed,
            "canonicalSemanticsCompared": False,
            "observedSeamIds": observed_seams,
            "observedPanelIds": observed_panels,
            "materialIds": material_ids,
        }
    graph = load_strict_json_object(
        canonical_package.resolve(strict=True) / "semantic" / "garment_graph.json"
    )
    expected_seams = sorted(str(row["id"]) for row in graph.get("seams", []))
    expected_panels = sorted(str(key) for key in graph.get("panelMapping", {}))
    checks = {
        "seamIdsExact": observed_seams == expected_seams,
        "panelIdsExact": observed_panels == expected_panels,
        "materialIdsPresent": bool(material_ids),
        "openingsDeclaredByCanonical": bool(graph.get("openings", [])),
    }
    return {
        "passed": all(checks.values()),
        "canonicalSemanticsCompared": True,
        "checks": checks,
        "expectedSeamIds": expected_seams,
        "observedSeamIds": observed_seams,
        "expectedPanelIds": expected_panels,
        "observedPanelIds": observed_panels,
        "materialIds": material_ids,
    }
