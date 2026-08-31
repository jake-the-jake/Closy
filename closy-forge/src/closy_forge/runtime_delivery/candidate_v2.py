from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.integrated_runtime.contracts import PackageAuthority
from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.package_io.managed_output import (
    MARKER_NAME,
    cleanup_managed_staging,
    create_managed_staging,
    publish_managed_staging,
)
from closy_forge.package_io.paths import validate_package_relpath
from closy_forge.runtime_delivery.package import RuntimeLimits, RuntimePackageError

RUNTIME_CANDIDATE_PACKAGE_VERSION = "closy.runtime_package.research_candidate.v2"
RUNTIME_CANDIDATE_CAPABILITY_VERSION = "closy.runtime_capabilities.research_candidate.v2"


@dataclass(frozen=True)
class RuntimeCandidateInputs:
    garment_package: Path
    source_link: dict[str, Any]
    zeroone_static_descriptor: Path | None = None
    zeroone_dynamic_descriptor: Path | None = None
    avatar_asset: Path | None = None


@dataclass(frozen=True)
class LoadedRuntimeCandidate:
    selected_source: str
    selected_bytes: bytes
    package_authority: PackageAuthority
    descriptor_only: bool
    actual_zeroone_payload_loaded: bool
    package_digest: str


def build_runtime_candidate_v2(
    target: Path,
    *,
    inputs: RuntimeCandidateInputs,
    force: bool = False,
    limits: RuntimeLimits | None = None,
) -> Path:
    active_limits = limits or RuntimeLimits()
    if target.suffix != ".closyruntime":
        raise RuntimePackageError("runtime_package_suffix_required")
    source = _inspect_garment_package(inputs.garment_package, active_limits)
    _validate_source_link(inputs.source_link)
    staging = create_managed_staging(target, allowed_root=target.parent, purpose="runtime-v2")
    try:
        fallback_bytes = _bounded_read(source["fallbackPath"], active_limits.max_file_bytes)
        _write_bytes(staging / "assets" / "conventional_garment.glb", fallback_bytes)
        canonical_artifacts = {
            "avatarContract": "canonical/avatar_contract.json",
            "pattern": "canonical/pattern.json",
            "seamOpeningGraph": "canonical/garment_graph.json",
            "simulationManifest": "canonical/simulation_manifest.json",
            "renderManifest": "canonical/render_manifest.json",
            "bindingContract": "canonical/binding_contract.json",
            "sourceFidelity": "canonical/source_fidelity.json",
            "pbrMaterials": "canonical/pbr_materials.json",
        }
        source_keys = {
            "avatarContract": "avatarPath",
            "pattern": "patternPath",
            "seamOpeningGraph": "seamPath",
            "simulationManifest": "simulationPath",
            "renderManifest": "renderPath",
            "bindingContract": "bindingPath",
            "sourceFidelity": "fidelityPath",
            "pbrMaterials": "materialPath",
        }
        for authority_name, destination in canonical_artifacts.items():
            raw = _bounded_read(source[source_keys[authority_name]], active_limits.max_file_bytes)
            _write_bytes(staging / destination, raw)
        avatar_path: str | None = None
        if inputs.avatar_asset is not None:
            avatar = _bounded_read(inputs.avatar_asset, active_limits.max_file_bytes)
            if len(avatar) < 20 or avatar[:4] != b"glTF":
                raise RuntimePackageError("runtime_avatar_not_glb")
            avatar_path = "assets/avatar.glb"
            _write_bytes(staging / avatar_path, avatar)

        descriptors: dict[str, str | None] = {
            "zeroOneStaticDescriptor": None,
            "zeroOneDynamicDescriptor": None,
        }
        descriptor_identities: dict[str, str | None] = {"static": None, "dynamic": None}
        descriptor_authority: dict[str, str | None] = {
            "binary": None,
            "staticInputSurface": None,
            "mechanicalReferenceSurface": None,
        }
        if inputs.zeroone_static_descriptor is not None:
            raw = _validate_descriptor(inputs.zeroone_static_descriptor, "static", active_limits)
            path = "descriptors/zeroone_static_descriptor.json"
            _write_bytes(staging / path, raw)
            descriptors["zeroOneStaticDescriptor"] = path
            descriptor_identities["static"] = sha256_bytes(raw)
            static_value = json.loads(raw.decode("utf-8"))
            descriptor_authority["staticInputSurface"] = _descriptor_sha(
                static_value, "staticInputSurfaceIdentity"
            )
        if inputs.zeroone_dynamic_descriptor is not None:
            raw = _validate_descriptor(inputs.zeroone_dynamic_descriptor, "dynamic", active_limits)
            path = "descriptors/zeroone_dynamic_descriptor.json"
            _write_bytes(staging / path, raw)
            descriptors["zeroOneDynamicDescriptor"] = path
            descriptor_identities["dynamic"] = sha256_bytes(raw)
            dynamic_value = json.loads(raw.decode("utf-8"))
            descriptor_authority["binary"] = _descriptor_sha(dynamic_value, "zeroOneBinaryIdentity")
            descriptor_authority["mechanicalReferenceSurface"] = _descriptor_sha(
                dynamic_value, "mechanicalReferenceSurfaceIdentity"
            )

        claims = {
            "garmentPackageDigest": source["garmentPackageDigest"],
            "garmentId": source["garmentId"],
            "avatarContractHash": source["avatarContractHash"],
            "patternHash": source["patternHash"],
            "seamOpeningHash": source["seamOpeningHash"],
            "simulationTopologyHash": source["simulationTopologyHash"],
            "renderTopologyHash": source["renderTopologyHash"],
            "bindingHash": source["bindingHash"],
            "conventionalGarmentFallbackSha256": sha256_bytes(fallback_bytes),
            "sourceFidelityIdentity": source["sourceFidelityIdentity"],
            "materialIdentity": source["materialIdentity"],
            "zeroOneStaticDescriptorIdentity": descriptor_identities["static"],
            "zeroOneDynamicDescriptorIdentity": descriptor_identities["dynamic"],
            "expectedZeroOneBinaryIdentity": descriptor_authority["binary"],
            "staticInputSurfaceIdentity": descriptor_authority["staticInputSurface"],
            "mechanicalReferenceSurfaceIdentity": descriptor_authority[
                "mechanicalReferenceSurface"
            ],
        }
        write_canonical_json(
            staging / "authority" / "package_authority.json",
            {
                "schemaVersion": 1,
                "authorityVersion": "closy.runtime.package_authority.v2",
                "claims": claims,
                "parsedFromSelectedBytes": True,
            },
        )
        inventory = _inventory(staging, active_limits)
        package_digest = _inventory_digest(inventory)
        manifest = {
            "schemaVersion": 2,
            "packageVersion": RUNTIME_CANDIDATE_PACKAGE_VERSION,
            "capabilityVersion": RUNTIME_CANDIDATE_CAPABILITY_VERSION,
            "classification": "research_candidate_not_product_selected",
            "sourceLink": inputs.source_link,
            "garment": {
                "garmentId": source["garmentId"],
                "coordinateConvention": source["coordinateConvention"],
                "conventionalFallback": "assets/conventional_garment.glb",
                "avatarAsset": avatar_path,
            },
            "descriptors": descriptors,
            "canonicalAuthorityArtifacts": canonical_artifacts,
            "actualPayloads": {
                "zeroOneStatic": None,
                "zeroOneDynamic": None,
                "actualPayloadCapability": False,
            },
            "packageAuthority": "authority/package_authority.json",
            "selection": {
                "defaultRenderSource": "conventional_garment_glb",
                "productRuntimeV1Unchanged": True,
            },
            "inventory": inventory,
            "packageDigest": package_digest,
        }
        write_canonical_json(staging / "manifest.json", manifest)
        publish_managed_staging(
            staging,
            target,
            allowed_root=target.parent,
            purpose="runtime-v2",
            force=force,
        )
    except BaseException:
        cleanup_managed_staging(staging, allowed_root=target.parent, purpose="runtime-v2")
        raise
    return target


def load_runtime_candidate_v2(
    package_dir: Path, *, limits: RuntimeLimits | None = None
) -> LoadedRuntimeCandidate:
    active_limits = limits or RuntimeLimits()
    root = package_dir.resolve(strict=True)
    manifest = _read_object(root / "manifest.json", 1_048_576)
    _validate_manifest(manifest)
    files = _validate_inventory(root, manifest, active_limits)
    authority_path = _declared(files, str(manifest["packageAuthority"]))
    authority_document = _read_object(authority_path, 1_048_576)
    if (
        authority_document.get("schemaVersion") != 1
        or authority_document.get("authorityVersion") != "closy.runtime.package_authority.v2"
        or authority_document.get("parsedFromSelectedBytes") is not True
        or not isinstance(authority_document.get("claims"), dict)
    ):
        raise RuntimePackageError("runtime_package_authority_document_invalid")
    claims = authority_document["claims"]
    package_authority = _parse_authority(claims, str(manifest["packageDigest"]))
    _validate_canonical_authority(manifest, files, package_authority, active_limits)
    fallback_rel = str(manifest["garment"]["conventionalFallback"])
    fallback = _bounded_read(_declared(files, fallback_rel), active_limits.max_file_bytes)
    if len(fallback) < 20 or fallback[:4] != b"glTF":
        raise RuntimePackageError("conventional_garment_fallback_not_glb")
    if sha256_bytes(fallback) != package_authority.conventional_garment_fallback_sha256:
        raise RuntimePackageError("runtime_candidate_fallback_authority_mismatch")
    _validate_descriptor_inventory(manifest, files, package_authority, active_limits)
    return LoadedRuntimeCandidate(
        selected_source="conventional_garment_glb",
        selected_bytes=fallback,
        package_authority=package_authority,
        descriptor_only=True,
        actual_zeroone_payload_loaded=False,
        package_digest=str(manifest["packageDigest"]),
    )


def _inspect_garment_package(root: Path, limits: RuntimeLimits) -> dict[str, Any]:
    package = root.resolve(strict=True)
    manifest = _read_object(package / "manifest.json", 4_194_304)
    paths = manifest.get("canonicalPaths")
    hashes = manifest.get("hashes")
    if not isinstance(paths, dict) or not isinstance(hashes, dict):
        raise RuntimePackageError("runtime_source_garment_manifest_invalid")
    required_paths = {
        "fallbackPath": "renderFallback",
        "patternPath": "pattern",
        "seamPath": "semanticGraph",
        "simulationPath": "simulationMeshManifest",
        "renderPath": "renderMeshManifest",
        "bindingPath": "productionBindingContract",
        "materialPath": "pbrMaterialMaps",
        "fidelityPath": "sourceRenderFidelity",
    }
    resolved: dict[str, Path] = {}
    for key, canonical_key in required_paths.items():
        relative = paths.get(canonical_key)
        if not isinstance(relative, str):
            raise RuntimePackageError(f"runtime_source_garment_path_missing:{canonical_key}")
        try:
            validate_package_relpath(relative)
        except ValueError as error:
            raise RuntimePackageError("runtime_source_garment_path_invalid") from error
        path = package / relative
        if not path.is_file() or path.stat().st_size > limits.max_file_bytes:
            raise RuntimePackageError(f"runtime_source_garment_file_missing:{canonical_key}")
        resolved[key] = path
    avatar = manifest.get("avatar")
    if (
        not isinstance(avatar, dict)
        or not isinstance(avatar.get("contentHash"), str)
        or not isinstance(avatar.get("path"), str)
    ):
        raise RuntimePackageError("runtime_source_avatar_contract_missing")
    avatar_relative = str(avatar["path"])
    try:
        validate_package_relpath(avatar_relative)
    except ValueError as error:
        raise RuntimePackageError("runtime_source_avatar_contract_invalid") from error
    avatar_path = package / avatar_relative
    if not avatar_path.is_file():
        raise RuntimePackageError("runtime_source_avatar_contract_missing")
    simulation = _read_object(resolved["simulationPath"], limits.max_file_bytes)
    render = _read_object(resolved["renderPath"], limits.max_file_bytes)
    coordinate = manifest.get("coordinateConvention")
    if coordinate != render.get("coordinateConvention") or coordinate != simulation.get(
        "coordinateConvention"
    ):
        raise RuntimePackageError("runtime_source_coordinate_convention_mismatch")
    meshset = read_glb_meshset(resolved["fallbackPath"])
    if not meshset.meshes or any(
        not mesh.panel_id.startswith("panel.")
        or mesh.material_id.startswith("material.synthetic_avatar")
        for mesh in meshset.meshes
    ):
        raise RuntimePackageError("runtime_fallback_not_canonical_garment")
    garment_id = manifest.get("garmentId")
    garment_digest = manifest.get("canonicalPackageDigest")
    if not isinstance(garment_id, str) or not garment_id.startswith("garment."):
        raise RuntimePackageError("runtime_source_garment_id_invalid")
    if not _is_sha256(garment_digest):
        raise RuntimePackageError("runtime_source_garment_digest_invalid")
    return {
        **resolved,
        "avatarPath": avatar_path,
        "garmentPackageDigest": garment_digest,
        "garmentId": garment_id,
        "coordinateConvention": coordinate,
        "avatarContractHash": sha256_file(avatar_path),
        "patternHash": sha256_file(resolved["patternPath"]),
        "seamOpeningHash": sha256_file(resolved["seamPath"]),
        "simulationTopologyHash": _required_sha(simulation, "topologyHash"),
        "renderTopologyHash": _required_sha(render, "topologyHash"),
        "bindingHash": sha256_file(resolved["bindingPath"]),
        "sourceFidelityIdentity": sha256_file(resolved["fidelityPath"]),
        "materialIdentity": sha256_file(resolved["materialPath"]),
    }


def _validate_descriptor(path: Path, kind: str, limits: RuntimeLimits) -> bytes:
    raw = _bounded_read(path, limits.max_file_bytes)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise RuntimePackageError(f"runtime_{kind}_descriptor_invalid") from error
    expected = {
        "static": "qualified_static_identity_descriptor_not_render_blob",
        "dynamic": "qualified_mt1_identity_descriptor_not_dynamic_vertex_blob",
    }[kind]
    if not isinstance(value, dict) or value.get("payloadKind") != expected:
        raise RuntimePackageError(f"runtime_{kind}_descriptor_not_descriptor")
    return raw


def _validate_descriptor_inventory(
    manifest: dict[str, Any],
    files: dict[str, Path],
    authority: PackageAuthority,
    limits: RuntimeLimits,
) -> None:
    descriptors = manifest["descriptors"]
    for key, kind, expected in (
        (
            "zeroOneStaticDescriptor",
            "static",
            authority.zeroone_static_descriptor_identity,
        ),
        (
            "zeroOneDynamicDescriptor",
            "dynamic",
            authority.zeroone_dynamic_descriptor_identity,
        ),
    ):
        relative = descriptors[key]
        if relative is None:
            if expected is not None:
                raise RuntimePackageError("runtime_descriptor_authority_mismatch")
            continue
        raw = _validate_descriptor(_declared(files, str(relative)), kind, limits)
        if expected != sha256_bytes(raw):
            raise RuntimePackageError("runtime_descriptor_authority_mismatch")


def _validate_canonical_authority(
    manifest: dict[str, Any],
    files: dict[str, Path],
    authority: PackageAuthority,
    limits: RuntimeLimits,
) -> None:
    artifacts = manifest.get("canonicalAuthorityArtifacts")
    expected_keys = {
        "avatarContract",
        "pattern",
        "seamOpeningGraph",
        "simulationManifest",
        "renderManifest",
        "bindingContract",
        "sourceFidelity",
        "pbrMaterials",
    }
    if not isinstance(artifacts, dict) or set(artifacts) != expected_keys:
        raise RuntimePackageError("runtime_canonical_authority_inventory_invalid")
    paths = {
        key: _declared(files, str(relative))
        for key, relative in artifacts.items()
        if isinstance(relative, str)
    }
    if set(paths) != expected_keys:
        raise RuntimePackageError("runtime_canonical_authority_inventory_invalid")
    simulation = _read_object(paths["simulationManifest"], limits.max_file_bytes)
    render = _read_object(paths["renderManifest"], limits.max_file_bytes)
    observed = {
        "avatar_contract_hash": sha256_file(paths["avatarContract"]),
        "pattern_hash": sha256_file(paths["pattern"]),
        "seam_opening_hash": sha256_file(paths["seamOpeningGraph"]),
        "simulation_topology_hash": _required_sha(simulation, "topologyHash"),
        "render_topology_hash": _required_sha(render, "topologyHash"),
        "binding_hash": sha256_file(paths["bindingContract"]),
        "source_fidelity_identity": sha256_file(paths["sourceFidelity"]),
        "material_identity": sha256_file(paths["pbrMaterials"]),
    }
    for field, value in observed.items():
        if getattr(authority, field) != value:
            raise RuntimePackageError(f"runtime_canonical_authority_mismatch:{field}")


def _parse_authority(claims: dict[str, Any], package_digest: str) -> PackageAuthority:
    try:
        authority = PackageAuthority(
            runtime_package_digest=package_digest,
            garment_package_digest=str(claims["garmentPackageDigest"]),
            garment_id=str(claims["garmentId"]),
            avatar_contract_hash=str(claims["avatarContractHash"]),
            pattern_hash=str(claims["patternHash"]),
            seam_opening_hash=str(claims["seamOpeningHash"]),
            simulation_topology_hash=str(claims["simulationTopologyHash"]),
            render_topology_hash=str(claims["renderTopologyHash"]),
            binding_hash=str(claims["bindingHash"]),
            conventional_garment_fallback_sha256=str(claims["conventionalGarmentFallbackSha256"]),
            source_fidelity_identity=str(claims["sourceFidelityIdentity"]),
            material_identity=str(claims["materialIdentity"]),
            zeroone_static_descriptor_identity=_optional_sha(
                claims.get("zeroOneStaticDescriptorIdentity")
            ),
            zeroone_dynamic_descriptor_identity=_optional_sha(
                claims.get("zeroOneDynamicDescriptorIdentity")
            ),
            expected_zeroone_binary_identity=_optional_sha(
                claims.get("expectedZeroOneBinaryIdentity")
            ),
            static_input_surface_identity=_optional_sha(claims.get("staticInputSurfaceIdentity")),
            mechanical_reference_surface_identity=_optional_sha(
                claims.get("mechanicalReferenceSurfaceIdentity")
            ),
        )
    except KeyError as error:
        raise RuntimePackageError("runtime_package_authority_missing") from error
    try:
        authority.validate()
    except ValueError as error:
        raise RuntimePackageError(str(error)) from error
    return authority


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if (
        manifest.get("schemaVersion") != 2
        or manifest.get("packageVersion") != RUNTIME_CANDIDATE_PACKAGE_VERSION
        or manifest.get("capabilityVersion") != RUNTIME_CANDIDATE_CAPABILITY_VERSION
        or manifest.get("classification") != "research_candidate_not_product_selected"
    ):
        raise RuntimePackageError("runtime_candidate_manifest_version_unsupported")
    if manifest.get("selection") != {
        "defaultRenderSource": "conventional_garment_glb",
        "productRuntimeV1Unchanged": True,
    }:
        raise RuntimePackageError("runtime_candidate_selection_invalid")
    payloads = manifest.get("actualPayloads")
    if payloads != {
        "actualPayloadCapability": False,
        "zeroOneDynamic": None,
        "zeroOneStatic": None,
    }:
        raise RuntimePackageError("runtime_descriptor_payload_overclaim")
    descriptors = manifest.get("descriptors")
    if not isinstance(descriptors, dict) or set(descriptors) != {
        "zeroOneStaticDescriptor",
        "zeroOneDynamicDescriptor",
    }:
        raise RuntimePackageError("runtime_candidate_descriptors_invalid")
    for value in descriptors.values():
        if value is not None and not isinstance(value, str):
            raise RuntimePackageError("runtime_candidate_descriptors_invalid")
    if not isinstance(manifest.get("canonicalAuthorityArtifacts"), dict):
        raise RuntimePackageError("runtime_canonical_authority_inventory_invalid")
    if not isinstance(manifest.get("inventory"), list):
        raise RuntimePackageError("runtime_inventory_invalid")


def _validate_inventory(
    root: Path, manifest: dict[str, Any], limits: RuntimeLimits
) -> dict[str, Path]:
    records: dict[str, dict[str, Any]] = {}
    total = 0
    for row in manifest["inventory"]:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise RuntimePackageError("runtime_inventory_invalid")
        relative = str(row["path"])
        try:
            validate_package_relpath(relative)
        except ValueError as error:
            raise RuntimePackageError("runtime_inventory_path_invalid") from error
        size = row.get("byteSize")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise RuntimePackageError("runtime_inventory_size_invalid")
        total += size
        if relative in records:
            raise RuntimePackageError("runtime_inventory_duplicate")
        records[relative] = row
    if len(records) > limits.max_file_count or total > limits.max_total_bytes:
        raise RuntimePackageError("runtime_inventory_limit_exceeded")
    if _inventory_digest(list(records.values())) != manifest.get("packageDigest"):
        raise RuntimePackageError("runtime_package_digest_mismatch")
    actual: dict[str, Path] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimePackageError("runtime_link_rejected")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            actual[relative] = path
    if set(actual) != set(records) | {"manifest.json", MARKER_NAME}:
        raise RuntimePackageError("runtime_exact_inventory_mismatch")
    for relative, row in records.items():
        path = actual[relative]
        if path.stat().st_size != row["byteSize"] or sha256_file(path) != row.get("sha256"):
            raise RuntimePackageError("runtime_inventory_hash_mismatch")
    return actual


def _inventory(root: Path, limits: RuntimeLimits) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimePackageError("runtime_link_rejected")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in {MARKER_NAME, "manifest.json"}:
            continue
        size = path.stat().st_size
        total += size
        records.append({"path": relative, "byteSize": size, "sha256": sha256_file(path)})
    if len(records) > limits.max_file_count or total > limits.max_total_bytes:
        raise RuntimePackageError("runtime_inventory_limit_exceeded")
    return records


def _inventory_digest(rows: list[dict[str, Any]]) -> str:
    payload = "\n".join(
        f"{row['path']}\0{row['byteSize']}\0{row['sha256']}"
        for row in sorted(rows, key=lambda item: str(item["path"]))
    )
    return sha256_bytes(payload.encode())


def _validate_source_link(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {
        "opaqueId",
        "consentScope",
        "retentionPolicy",
        "deletionPolicy",
        "derivationPolicy",
        "withdrawalStatus",
    }:
        raise RuntimePackageError("runtime_source_link_invalid")
    if any(not isinstance(item, str) or not item for item in value.values()):
        raise RuntimePackageError("runtime_source_link_invalid")


def _required_sha(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not _is_sha256(result):
        raise RuntimePackageError(f"runtime_source_identity_invalid:{key}")
    return str(result)


def _optional_sha(value: Any) -> str | None:
    if value is None:
        return None
    if not _is_sha256(value):
        raise RuntimePackageError("runtime_descriptor_identity_invalid")
    return str(value)


def _descriptor_sha(value: dict[str, Any], key: str) -> str | None:
    observed = value.get(key)
    if observed is None:
        return None
    if not _is_sha256(observed):
        raise RuntimePackageError(f"runtime_descriptor_authority_invalid:{key}")
    return str(observed)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _read_object(path: Path, maximum: int) -> dict[str, Any]:
    if path.stat().st_size > maximum:
        raise RuntimePackageError("runtime_file_limit_exceeded")
    value = read_json(path)
    if not isinstance(value, dict):
        raise RuntimePackageError("runtime_object_required")
    return value


def _bounded_read(path: Path, maximum: int) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        raise RuntimePackageError("runtime_file_limit_exceeded")
    return data


def _declared(files: dict[str, Path], relative: str) -> Path:
    try:
        validate_package_relpath(relative)
    except ValueError as error:
        raise RuntimePackageError("runtime_reference_path_invalid") from error
    path = files.get(relative)
    if path is None:
        raise RuntimePackageError("runtime_reference_not_in_inventory")
    return path


def _write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
