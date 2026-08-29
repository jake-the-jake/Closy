from __future__ import annotations

import json
import re
import struct
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_io.paths import validate_package_relpath
from closy_forge.zeroone.tool import PROFILE, REQUEST_SCHEMA_VERSION

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def build_zeroone_request(
    *,
    invocation_root: Path,
    package: Path,
    output: Path,
    closy_sha: str,
    request_label: str,
    closy_dirty: bool = False,
    deadline_ms: int = 120_000,
) -> dict[str, Any]:
    root = invocation_root.resolve(strict=True)
    package_root = package.resolve(strict=True)
    output_root = output.resolve(strict=False)
    package_relative = _relative_inside(package_root, root, "package")
    output_relative = _relative_inside(output_root, root, "output")
    if (
        package_root == output_root
        or package_root in output_root.parents
        or output_root in package_root.parents
    ):
        raise ValueError("package and ZeroOne output roots must be disjoint")
    if not GIT_SHA_RE.fullmatch(closy_sha):
        raise ValueError("Closy SHA must be a full lowercase Git SHA")
    if deadline_ms <= 1 or deadline_ms > 3_600_000:
        raise ValueError("ZeroOne deadline must be between 2 and 3600000 milliseconds")

    manifest_path = package_root / "manifest.json"
    manifest = _read_object(manifest_path)
    inventory = _inventory_map(manifest)
    canonical = manifest.get("canonicalPaths", {})
    if not isinstance(canonical, dict):
        canonical = {}

    fallback_relative = _choose_existing(
        inventory,
        canonical.get("renderFallback"),
        canonical.get("denseRender"),
        "render/fallback.glb",
    )
    processing_relative = canonical.get("zeroOneProcessingSurface")
    input_relative = (
        processing_relative
        if isinstance(processing_relative, str) and processing_relative in inventory
        else fallback_relative
    )
    semantic_relative = _choose_existing(
        inventory,
        canonical.get("semanticGraph"),
        canonical.get("semantic"),
        "semantic/garment_graph.json",
    )
    processing_manifest = canonical.get("zeroOneProcessingSurfaceManifest")
    topology_relative = (
        processing_manifest
        if input_relative != fallback_relative
        and isinstance(processing_manifest, str)
        and processing_manifest in inventory
        else _choose_existing(
            inventory,
            canonical.get("renderMeshManifest"),
            "render/mesh_manifest.json",
            "manifest.json",
        )
    )
    topology = _read_object(package_root / topology_relative)
    topology_hash = topology.get("topologyHash")
    if not isinstance(topology_hash, str):
        hashes = topology.get("hashes", {})
        topology_hash = hashes.get("renderTopology") if isinstance(hashes, dict) else None
    if not isinstance(topology_hash, str) or not SHA256_RE.fullmatch(topology_hash):
        raise ValueError("package does not declare a valid render topology hash")

    semantics = _read_object(package_root / semantic_relative)
    panel_mapping = semantics.get("panelMapping")
    if not isinstance(panel_mapping, dict) or not panel_mapping:
        raise ValueError("semantic graph has no panel mapping")
    panel_ids = sorted(str(value) for value in panel_mapping)
    seam_ids = _semantic_ids(semantics, "seams")
    opening_ids = _semantic_ids(semantics, "openings")
    if not seam_ids or not opening_ids:
        raise ValueError("semantic graph must declare seams and openings")

    materials = _glb_materials(package_root / input_relative)
    material_table = [
        {
            "id": _material_id(str(material.get("name", f"material_{index}")), index),
            "sourceMaterialIndex": index,
            "sourceName": str(material.get("name", f"material_{index}")),
        }
        for index, material in enumerate(materials)
    ]

    authority_paths = {
        "pattern": _choose_existing(inventory, canonical.get("pattern"), "pattern/pattern.json"),
        "simulation": _choose_existing(
            inventory, "simulation/constraints.json", canonical.get("simulation")
        ),
        "binding": _choose_existing(
            inventory, canonical.get("binding"), "binding/sim_to_render.bin"
        ),
        "source": _choose_existing(
            inventory,
            canonical.get("sourceCaptureRecord"),
            canonical.get("source"),
            "source/capture_record.json",
        ),
        "appearance": _choose_existing(
            inventory,
            canonical.get("pbrMaterialMaps"),
            canonical.get("generatedTextureAtlas"),
            "textures/layered_asymmetric_pbr_report.json",
            "textures/atlas/base_color.png",
        ),
        "conventional_fallback": fallback_relative,
    }
    if len(set(authority_paths.values())) != len(authority_paths):
        raise ValueError("canonical authority roles must resolve to distinct package assets")
    authority = [
        {"path": path, "sha256": _inventory_hash(package_root, inventory, path), "role": role}
        for role, path in authority_paths.items()
    ]

    coordinate = manifest.get("coordinateConvention", {})
    coordinate_id = coordinate.get("id") if isinstance(coordinate, dict) else None
    if coordinate_id != "closy-rh-yup-plus-z-v1":
        raise ValueError("package coordinate convention is unsupported")
    package_schema = manifest.get("schemaVersion")
    garment_id = manifest.get("garmentId")
    if not isinstance(package_schema, int) or package_schema <= 0:
        raise ValueError("package schema version is invalid")
    if not isinstance(garment_id, str) or not garment_id:
        raise ValueError("package garment ID is missing")

    binding_path = canonical.get("bindingManifest")
    binding_metadata = None
    if isinstance(binding_path, str) and binding_path in inventory:
        binding_metadata = {
            "path": binding_path,
            "sha256": _inventory_hash(package_root, inventory, binding_path),
        }
    return {
        "schemaVersion": REQUEST_SCHEMA_VERSION,
        "packageSchemaVersion": package_schema,
        "packageRoot": package_relative,
        "manifestPath": "manifest.json",
        "manifestSha256": sha256_file(manifest_path),
        "inputAssetPath": input_relative,
        "inputContentSha256": _inventory_hash(package_root, inventory, input_relative),
        "inputRole": (
            "versioned_zeroone_processing_surface"
            if input_relative != fallback_relative
            else "canonical_conventional_fallback"
        ),
        "garmentId": garment_id,
        "topologyHash": topology_hash,
        "topologyMetadataPath": topology_relative,
        "topologyMetadataSha256": sha256_file(package_root / topology_relative),
        "coordinateConventionId": coordinate_id,
        "unitScaleMetres": 1.0,
        "materialTable": material_table,
        "semanticIds": {"panels": panel_ids, "seams": seam_ids, "openings": opening_ids},
        "semanticGraphPath": semantic_relative,
        "semanticGraphSha256": _inventory_hash(package_root, inventory, semantic_relative),
        "bindingMetadata": binding_metadata,
        "canonicalAuthority": authority,
        "profile": PROFILE,
        "resourceLimits": {
            "maximumInputBytes": 268_435_456,
            "maximumVertices": 4_000_000,
            "maximumTriangles": 8_000_000,
            "maximumWorkingBytes": 536_870_912,
            "maximumOperationUnits": 200_000_000,
            "deadlineMs": deadline_ms,
        },
        "outputRoot": output_relative,
        "cancellationTokenRelativePath": "cancel.requested",
        "producer": {"closyGitSha": closy_sha, "closyDirty": closy_dirty},
        "requestLabel": request_label,
    }


def authority_hashes(request: dict[str, Any]) -> dict[str, str]:
    return {
        str(entry["role"]): str(entry["sha256"])
        for entry in request.get("canonicalAuthority", [])
        if isinstance(entry, dict)
    }


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path.name}")
    return value


def _inventory_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("inventory", []):
        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
            result[entry["path"]] = entry
    return result


def _choose_existing(inventory: dict[str, dict[str, Any]], *paths: object) -> str:
    for value in paths:
        if isinstance(value, str) and (value == "manifest.json" or value in inventory):
            return value
    raise ValueError(f"package has none of the required assets: {paths}")


def _inventory_hash(package: Path, inventory: dict[str, dict[str, Any]], relative: str) -> str:
    validate_package_relpath(relative)
    path = package / relative
    if not path.is_file():
        raise ValueError(f"required package asset is missing: {relative}")
    actual = sha256_file(path)
    declared = inventory.get(relative, {}).get("sha256")
    if declared is not None and declared != actual:
        raise ValueError(f"manifest hash mismatch: {relative}")
    return actual


def _relative_inside(path: Path, root: Path, label: str) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} must be contained by invocation root") from error
    value = relative.as_posix()
    validate_package_relpath(value)
    return value


def _semantic_ids(document: dict[str, Any], field: str) -> list[str]:
    return sorted(
        item["id"]
        for item in document.get(field, [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )


def _material_id(name: str, index: int) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"material.{cleaned or 'slot'}.{index}"


def _glb_materials(path: Path) -> list[dict[str, Any]]:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("input asset is not GLB 2.0")
    version, total_length = struct.unpack_from("<II", data, 4)
    json_length, json_type = struct.unpack_from("<II", data, 12)
    if version != 2 or total_length != len(data) or json_type != 0x4E4F534A:
        raise ValueError("input asset has an unsupported GLB header")
    end = 20 + json_length
    if end > len(data):
        raise ValueError("input asset has a truncated GLB JSON chunk")
    document = json.loads(data[20:end].rstrip(b" \x00").decode("utf-8"))
    materials = document.get("materials") if isinstance(document, dict) else None
    if not isinstance(materials, list) or not materials:
        raise ValueError("input GLB has no material table")
    if not all(isinstance(material, dict) for material in materials):
        raise ValueError("input GLB material entry is invalid")
    return materials
