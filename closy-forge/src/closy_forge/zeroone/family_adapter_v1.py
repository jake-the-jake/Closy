"""Read-only family-package copy view for the frozen static request contract."""

from __future__ import annotations

import re
import stat
from pathlib import Path
from typing import Any

from closy_forge.family_integration_v1.compiler import PROFILE, validate_family
from closy_forge.geometry.glb_io import _read_glb
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.package_io.paths import validate_package_relpath
from closy_forge.security.strict_json import load_strict_json_object

ADAPTER_VERSION = "closy.zeroone.family_adapter.v1"
MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_BYTES = 256 * 1024 * 1024
FAMILY_NAMES = (
    "tshirt",
    "sleeveless_top",
    "long_sleeved_top",
    "simple_skirt",
    "simple_trousers",
    "simple_dress",
    "button_shirt",
    "jacket_outerwear",
    "layered_asymmetric",
)


def is_link(path: Path) -> bool:
    """Reject Windows junctions as well as symlinks on Python 3.11."""
    return path.is_symlink() or bool(
        path.exists()
        and getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def safe_file(root: Path, relative: str) -> Path:
    validate_package_relpath(relative)
    candidate = root / relative
    if any(is_link(p) for p in (candidate, *candidate.parents)):
        raise ValueError("family_adapter_link_forbidden")
    if not candidate.resolve().is_relative_to(root.resolve()) or not candidate.is_file():
        raise ValueError("family_adapter_asset_missing_or_escaped")
    if candidate.stat().st_size > MAX_ASSET_BYTES:
        raise ValueError("family_adapter_asset_limit")
    return candidate


def snapshot_family(source: Path) -> dict[str, Any]:
    """Verify identities and bounded inventory before any copy or geometry decode."""
    manifest_path = safe_file(source, "manifest.json")
    manifest = load_strict_json_object(manifest_path)
    identity = dict(manifest)
    claimed = identity.pop("packageIdentity", None)
    if sha256_bytes(canonical_dumps(identity).encode()) != claimed:
        raise ValueError("family_adapter_source_identity_mismatch")
    if (
        manifest.get("profile") != PROFILE
        or manifest.get("family") not in FAMILY_NAMES
        or manifest.get("units") != "metres"
        or manifest.get("coordinates") != "right_handed_y_up"
        or not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("renderTopology", "")))
    ):
        raise ValueError("family_adapter_source_profile_invalid")
    files = {"manifest.json": sha256_file(manifest_path)}
    total = manifest_path.stat().st_size
    inventory = manifest.get("inventory")
    if not isinstance(inventory, list) or not 1 <= len(inventory) <= 256:
        raise ValueError("family_adapter_inventory_invalid")
    for row in inventory:
        relative = row["path"]
        if relative in files or relative.startswith(("source/", "appearance/")):
            raise ValueError("family_adapter_duplicate_or_reserved_path")
        path = safe_file(source, relative)
        digest = sha256_file(path)
        if digest != row["sha256"] or path.stat().st_size != row["byteSize"]:
            raise ValueError("family_adapter_source_asset_mismatch")
        files[relative] = digest
        total += path.stat().st_size
    if total > MAX_PACKAGE_BYTES:
        raise ValueError("family_adapter_package_limit")
    return {"manifest": manifest, "files": files, "packageIdentity": claimed}


def create_family_adapter(source: Path, destination: Path) -> dict[str, Any]:
    """Create a fresh adapter, never rewrite A or claim an old packageVersion."""
    source = source.absolute()
    destination = destination.absolute()
    if (
        destination.exists()
        or destination.resolve().is_relative_to(source.resolve())
        or source.resolve().is_relative_to(destination.resolve())
        or any(is_link(p) for p in (destination, *destination.parents))
    ):
        raise ValueError("family_adapter_destination_must_be_fresh_and_disjoint")
    before = snapshot_family(source)
    audit = validate_family(source)  # Read-only validation, not compilation or settling.
    if audit.get("validConventionalGeometry") is not True:
        raise ValueError("family_adapter_source_geometry_invalid")
    original = before["manifest"]
    gltf, _ = _read_glb(safe_file(source, "render/fallback.glb"))
    appearance = {
        "schemaVersion": 1,
        "profile": "closy.family_adapter.appearance.v1",
        "authority": "render_fallback_glb_material_table_not_simulation_material",
        "sourcePath": "render/fallback.glb",
        "sourceSha256": before["files"]["render/fallback.glb"],
        "materials": gltf.get("materials", []),
        "estimatedFromCapture": False,
    }
    if not appearance["materials"]:
        raise ValueError("family_adapter_appearance_materials_missing")
    source_record = {
        "schemaVersion": 1,
        "profile": "closy.family_adapter.source_record.v1",
        "originalManifestPath": "source/family_manifest.json",
        "originalManifestSha256": before["files"]["manifest.json"],
        "originalPackageIdentity": before["packageIdentity"],
        "originalProfile": original["profile"],
        "family": original["family"],
        "parameterSource": original["parameterSource"],
        "authority": "original_family_package_remains_authority",
        "captureEstimation": False,
    }
    # All bytes are pinned before creating a destination; a race fails closed.
    assets = {p: safe_file(source, p).read_bytes() for p in before["files"]}
    if any(sha256_bytes(data) != before["files"][p] for p, data in assets.items()):
        raise ValueError("family_adapter_source_changed_before_copy")
    assets["source/family_manifest.json"] = assets.pop("manifest.json")
    for path, doc in (
        ("source/family_source_record.json", source_record),
        ("source/family_validation_receipt.json", audit),
        ("appearance/material.json", appearance),
    ):
        assets[path] = canonical_dumps(doc).encode()
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "adapterVersion": ADAPTER_VERSION,
        "profile": ADAPTER_VERSION,
        "garmentId": original["garmentId"],
        "avatarId": original["avatarId"],
        "family": original["family"],
        "originalFamilyPackageIdentity": before["packageIdentity"],
        "originalFamilyProfile": original["profile"],
        "coordinateConvention": {"id": "closy-rh-yup-plus-z-v1"},
        "units": "metres",
        "hashes": {"renderTopology": original["renderTopology"]},
        "canonicalPaths": {
            "renderFallback": "render/fallback.glb",
            "semanticGraph": "semantic/garment_graph.json",
            "pattern": "pattern/pattern.json",
            "simulation": "simulation/constraints.json",
            "binding": "binding/sim_to_render.bin",
            "bindingManifest": "binding/binding_manifest.json",
            "sourceCaptureRecord": "source/family_source_record.json",
            "pbrMaterialMaps": "appearance/material.json",
        },
        "authority": "explicit_adapter_copy_view_not_replacement_family_package",
        "physicalQualification": False,
        "inventory": [
            {"path": p, "sha256": sha256_bytes(data), "byteSize": len(data)}
            for p, data in sorted(assets.items())
        ],
    }
    manifest["adapterIdentity"] = sha256_bytes(canonical_dumps(manifest).encode())
    assets["manifest.json"] = canonical_dumps(manifest).encode()
    if snapshot_family(source) != before:
        raise ValueError("family_adapter_source_changed_before_copy")
    destination.mkdir(parents=True, exist_ok=False)
    for relative, data in sorted(assets.items()):
        asset_path = destination / relative
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        with asset_path.open("xb") as stream:
            stream.write(data)
        if asset_path.read_bytes() != data:
            raise ValueError("family_adapter_copy_verification_failed")
    if snapshot_family(source) != before:
        raise ValueError("family_adapter_source_changed_during_copy")
    verify_family_adapter(destination)
    return {
        "adapterVersion": ADAPTER_VERSION,
        "adapterIdentity": manifest["adapterIdentity"],
        "adapterManifestSha256": sha256_file(destination / "manifest.json"),
        "source": before,
        "assetBytesIdentical": True,
        "sourceUnchanged": True,
        "copiedAssetCount": len(before["files"]) - 1,
        "sourceValidation": audit,
    }


def verify_family_adapter(package: Path) -> dict[str, Any]:
    """Check the explicit envelope and its byte-identical original asset lineage."""
    manifest = load_strict_json_object(safe_file(package, "manifest.json"))
    identity = dict(manifest)
    claimed = identity.pop("adapterIdentity", None)
    if (
        manifest.get("adapterVersion") != ADAPTER_VERSION
        or manifest.get("profile") != ADAPTER_VERSION
        or manifest.get("schemaVersion") != 1
        or "packageVersion" in manifest
        or sha256_bytes(canonical_dumps(identity).encode()) != claimed
    ):
        raise ValueError("family_adapter_envelope_identity_invalid")
    observed: dict[str, str] = {}
    if not 1 <= len(manifest["inventory"]) <= 256:
        raise ValueError("family_adapter_inventory_limit")
    total = 0
    for row in manifest["inventory"]:
        path = safe_file(package, row["path"])
        if (
            row["path"] in observed
            or path.stat().st_size != row["byteSize"]
            or sha256_file(path) != row["sha256"]
        ):
            raise ValueError("family_adapter_inventory_changed")
        observed[row["path"]] = row["sha256"]
        total += path.stat().st_size
    if total > MAX_PACKAGE_BYTES:
        raise ValueError("family_adapter_package_limit")
    original = load_strict_json_object(safe_file(package, "source/family_manifest.json"))
    original_identity = dict(original)
    original_claim = original_identity.pop("packageIdentity", None)
    if (
        original_claim != manifest["originalFamilyPackageIdentity"]
        or sha256_bytes(canonical_dumps(original_identity).encode()) != original_claim
        or original.get("profile") != PROFILE
    ):
        raise ValueError("family_adapter_original_identity_invalid")
    for row in original["inventory"]:
        if observed.get(row["path"]) != row["sha256"]:
            raise ValueError("family_adapter_asset_not_original_bytes")
    if (
        manifest["garmentId"] != original["garmentId"]
        or manifest["avatarId"] != original["avatarId"]
        or manifest["family"] != original["family"]
        or manifest["originalFamilyProfile"] != original["profile"]
        or manifest["hashes"]["renderTopology"] != original["renderTopology"]
        or manifest["coordinateConvention"]["id"] != "closy-rh-yup-plus-z-v1"
    ):
        raise ValueError("family_adapter_metadata_not_original")
    record = load_strict_json_object(safe_file(package, "source/family_source_record.json"))
    appearance = load_strict_json_object(safe_file(package, "appearance/material.json"))
    gltf, _ = _read_glb(safe_file(package, "render/fallback.glb"))
    if (
        record.get("originalManifestSha256") != observed.get("source/family_manifest.json")
        or record.get("originalPackageIdentity") != original_claim
        or appearance.get("sourceSha256") != observed.get("render/fallback.glb")
        or appearance.get("materials") != gltf.get("materials")
    ):
        raise ValueError("family_adapter_source_or_appearance_lineage_invalid")
    return manifest
