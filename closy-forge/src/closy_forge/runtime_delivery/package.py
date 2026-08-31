from __future__ import annotations

import json
import os
import re
import stat
import zlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.package_io.managed_output import (
    MARKER_NAME,
    cleanup_managed_staging,
    create_managed_staging,
    publish_managed_staging,
)
from closy_forge.package_io.paths import validate_package_relpath

RUNTIME_PACKAGE_VERSION = "closy.runtime_package.static_prep.v1"
RUNTIME_CAPABILITY_VERSION = "closy.runtime_capabilities.static_prep.v1"
_MANIFEST_MAX_BYTES = 1_048_576
_PAGE_BYTES = 65_536
_RAW_DIGEST_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")


class RuntimePackageError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RuntimeLimits:
    max_file_count: int = 32
    max_total_bytes: int = 134_217_728
    max_file_bytes: int = 67_108_864
    max_depth: int = 8
    max_decoded_bytes: int = 134_217_728
    max_decompression_ratio: float = 128.0


@dataclass(frozen=True)
class RuntimePackageInputs:
    conventional_fallback_glb: Path
    source_link: dict[str, Any]
    platform_profile: str = "portable-static-reference"
    zeroone_static_artifact: Path | None = None
    zeroone_dynamic_metadata: Path | None = None
    pose_id: str = "pose.neutral.prebaked_v1"
    pose_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class LoadedRuntimePackage:
    selected_source: Literal["zeroone_dynamic", "zeroone_static", "conventional_glb"]
    selected_bytes: bytes
    pose_id: str
    pose_payload: dict[str, Any]
    package_digest: str
    offline: bool
    fallback_reason: str | None = None


def build_runtime_package(
    target: Path,
    *,
    inputs: RuntimePackageInputs,
    force: bool = False,
    limits: RuntimeLimits | None = None,
) -> Path:
    active_limits = limits or RuntimeLimits()
    if target.suffix != ".closyruntime":
        raise RuntimePackageError("runtime_package_suffix_required")
    _validate_source_link(inputs.source_link)
    staging = create_managed_staging(
        target,
        allowed_root=target.parent,
        purpose="runtime-package",
    )
    try:
        fallback = _read_stable_file(inputs.conventional_fallback_glb, active_limits.max_file_bytes)
        if len(fallback) < 20 or fallback[:4] != b"glTF":
            raise RuntimePackageError("conventional_fallback_not_glb")
        _write_bytes(staging / "assets" / "conventional_fallback.glb", fallback)

        artifacts: dict[str, str | None] = {
            "zeroOneDynamic": None,
            "zeroOneStatic": None,
            "conventionalGlb": "assets/conventional_fallback.glb",
        }
        if inputs.zeroone_static_artifact is not None:
            static_bytes = _read_stable_file(
                inputs.zeroone_static_artifact, active_limits.max_file_bytes
            )
            artifacts["zeroOneStatic"] = "assets/zeroone_static.bin"
            _write_bytes(staging / "assets" / "zeroone_static.bin", static_bytes)
        if inputs.zeroone_dynamic_metadata is not None:
            dynamic_bytes = _read_stable_file(
                inputs.zeroone_dynamic_metadata, active_limits.max_file_bytes
            )
            artifacts["zeroOneDynamic"] = "assets/zeroone_dynamic_metadata.json"
            _write_bytes(staging / "assets" / "zeroone_dynamic_metadata.json", dynamic_bytes)

        pose_payload = inputs.pose_payload or {
            "frame": 0,
            "positionsSource": "conventional_glb_bind_pose",
            "dynamicDeformationExecuted": False,
        }
        pose_document = {
            "schemaVersion": 1,
            "poseId": inputs.pose_id,
            "payload": pose_payload,
        }
        write_canonical_json(staging / "motion" / "prebaked_pose.json", pose_document)
        pages = _write_pages(staging, fallback)
        inventory = _inventory(staging, active_limits)
        package_digest = _inventory_digest(inventory)
        manifest = {
            "schemaVersion": 1,
            "packageVersion": RUNTIME_PACKAGE_VERSION,
            "capabilityVersion": RUNTIME_CAPABILITY_VERSION,
            "candidatePreparatoryOnly": True,
            "platformProfile": inputs.platform_profile,
            "sourceLink": inputs.source_link,
            "artifacts": artifacts,
            "fallbackOrder": [
                "zeroone_dynamic",
                "zeroone_static",
                "conventional_glb",
                "failure",
            ],
            "motion": {
                "prebakedOptions": [
                    {"poseId": inputs.pose_id, "path": "motion/prebaked_pose.json"}
                ],
                "actualZeroOneDynamicDeformationExecuted": False,
            },
            "pages": {
                "compression": "zlib",
                "decodedAggregateSha256": sha256_bytes(fallback),
                "decodedBytes": len(fallback),
                "records": pages,
            },
            "inventory": inventory,
            "packageDigest": package_digest,
            "evidenceTruth": {
                "deviceRun": False,
                "gpuRun": False,
                "mobileRuntimeRun": False,
                "remoteStreamingServiceRun": False,
                "staticPackageConsumerExecuted": True,
            },
        }
        write_canonical_json(staging / "manifest.json", manifest)
        _validate_manifest_shape(manifest)
        publish_managed_staging(
            staging,
            target,
            allowed_root=target.parent,
            purpose="runtime-package",
            force=force,
        )
    except BaseException:
        cleanup_managed_staging(
            staging,
            allowed_root=target.parent,
            purpose="runtime-package",
        )
        raise
    return target


def load_runtime_package(
    package_dir: Path,
    *,
    limits: RuntimeLimits | None = None,
    support_zeroone_dynamic: bool = False,
    support_zeroone_static: bool = True,
    offline: bool = False,
    last_good_package: Path | None = None,
) -> LoadedRuntimePackage:
    active_limits = limits or RuntimeLimits()
    try:
        return _load_validated_package(
            package_dir,
            limits=active_limits,
            support_zeroone_dynamic=support_zeroone_dynamic,
            support_zeroone_static=support_zeroone_static,
            offline=offline,
        )
    except RuntimePackageError as primary_error:
        if last_good_package is None or last_good_package.resolve(
            strict=False
        ) == package_dir.resolve(strict=False):
            raise
        loaded = _load_validated_package(
            last_good_package,
            limits=active_limits,
            support_zeroone_dynamic=False if offline else support_zeroone_dynamic,
            support_zeroone_static=support_zeroone_static,
            offline=True,
        )
        return replace(loaded, fallback_reason=f"last_good_after:{primary_error.code}")


def _load_validated_package(
    package_dir: Path,
    *,
    limits: RuntimeLimits,
    support_zeroone_dynamic: bool,
    support_zeroone_static: bool,
    offline: bool,
) -> LoadedRuntimePackage:
    _validate_real_directory(package_dir)
    manifest_path = package_dir / "manifest.json"
    manifest_bytes = _read_stable_file(manifest_path, _MANIFEST_MAX_BYTES)
    try:
        parsed = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise RuntimePackageError("runtime_manifest_invalid") from error
    if not manifest_bytes or not isinstance(parsed, dict):
        raise RuntimePackageError("runtime_manifest_invalid")
    manifest: dict[str, Any] = parsed
    _validate_manifest_shape(manifest)
    files = _validate_exact_inventory(package_dir, manifest, limits)
    reconstructed = _decode_pages(manifest, files, limits)
    fallback_path = _artifact_path(manifest, "conventionalGlb")
    fallback_file = _declared_file(files, fallback_path)
    if reconstructed != _read_stable_file(fallback_file, limits.max_file_bytes):
        raise RuntimePackageError("runtime_page_asset_mismatch")

    artifacts = manifest["artifacts"]
    selected: Literal["zeroone_dynamic", "zeroone_static", "conventional_glb"]
    selected_path: str
    if not offline and support_zeroone_dynamic and isinstance(artifacts.get("zeroOneDynamic"), str):
        selected = "zeroone_dynamic"
        selected_path = str(artifacts["zeroOneDynamic"])
    elif support_zeroone_static and isinstance(artifacts.get("zeroOneStatic"), str):
        selected = "zeroone_static"
        selected_path = str(artifacts["zeroOneStatic"])
    elif isinstance(artifacts.get("conventionalGlb"), str):
        selected = "conventional_glb"
        selected_path = str(artifacts["conventionalGlb"])
    else:
        raise RuntimePackageError("runtime_no_supported_fallback")

    motion = manifest["motion"]["prebakedOptions"]
    pose = motion[0]
    pose_path = str(pose["path"])
    try:
        pose_parsed = json.loads(
            _read_stable_file(_declared_file(files, pose_path), _MANIFEST_MAX_BYTES).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimePackageError("runtime_prebaked_pose_invalid") from error
    if not isinstance(pose_parsed, dict):
        raise RuntimePackageError("runtime_prebaked_pose_invalid")
    pose_document: dict[str, Any] = pose_parsed
    if (
        pose_document.get("schemaVersion") != 1
        or pose_document.get("poseId") != pose.get("poseId")
        or not isinstance(pose_document.get("payload"), dict)
    ):
        raise RuntimePackageError("runtime_prebaked_pose_identity_mismatch")
    selected_bytes = _read_stable_file(_declared_file(files, selected_path), limits.max_file_bytes)
    return LoadedRuntimePackage(
        selected_source=selected,
        selected_bytes=selected_bytes,
        pose_id=str(pose_document["poseId"]),
        pose_payload=dict(pose_document["payload"]),
        package_digest=str(manifest["packageDigest"]),
        offline=offline,
    )


def _write_pages(staging: Path, source: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, offset in enumerate(range(0, len(source), _PAGE_BYTES)):
        raw = source[offset : offset + _PAGE_BYTES]
        compressed = zlib.compress(raw, level=9)
        path = f"pages/{index:05d}.zlib"
        _write_bytes(staging / path, compressed)
        records.append(
            {
                "index": index,
                "path": path,
                "sourceOffset": offset,
                "sourceLength": len(raw),
                "compressedLength": len(compressed),
                "compressedSha256": sha256_bytes(compressed),
                "decodedSha256": sha256_bytes(raw),
            }
        )
    if not records:
        raise RuntimePackageError("runtime_empty_fallback")
    return records


def _decode_pages(
    manifest: dict[str, Any],
    files: dict[str, Path],
    limits: RuntimeLimits,
) -> bytes:
    pages = manifest["pages"]
    records = pages["records"]
    expected_offset = 0
    decoded_total = 0
    for expected_index, record in enumerate(records):
        if record.get("index") != expected_index or record.get("sourceOffset") != expected_offset:
            raise RuntimePackageError("runtime_page_order_invalid")
        source_length = _bounded_int(record.get("sourceLength"), "runtime_page_length_invalid")
        compressed_length = _bounded_int(
            record.get("compressedLength"), "runtime_page_length_invalid"
        )
        if source_length > limits.max_file_bytes or compressed_length > limits.max_file_bytes:
            raise RuntimePackageError("runtime_page_limit_exceeded")
        if (
            compressed_length == 0
            or source_length / compressed_length > limits.max_decompression_ratio
        ):
            raise RuntimePackageError("runtime_decompression_ratio_exceeded")
        decoded_total += source_length
        if decoded_total > limits.max_decoded_bytes:
            raise RuntimePackageError("runtime_decoded_memory_limit_exceeded")
        expected_offset += source_length
    if decoded_total != pages.get("decodedBytes"):
        raise RuntimePackageError("runtime_decoded_size_mismatch")

    output = bytearray()
    for record in records:
        rel = str(record["path"])
        compressed = _read_stable_file(_declared_file(files, rel), limits.max_file_bytes)
        if (
            len(compressed) != record["compressedLength"]
            or sha256_bytes(compressed) != record["compressedSha256"]
        ):
            raise RuntimePackageError("runtime_chunk_corrupt")
        decompressor = zlib.decompressobj()
        source_length = int(record["sourceLength"])
        try:
            decoded = decompressor.decompress(compressed, source_length + 1)
        except zlib.error as error:
            raise RuntimePackageError("runtime_chunk_decode_failed") from error
        if (
            len(decoded) != source_length
            or not decompressor.eof
            or decompressor.unused_data
            or decompressor.unconsumed_tail
            or sha256_bytes(decoded) != record["decodedSha256"]
        ):
            raise RuntimePackageError("runtime_chunk_decoded_mismatch")
        output.extend(decoded)
    result = bytes(output)
    if sha256_bytes(result) != pages.get("decodedAggregateSha256"):
        raise RuntimePackageError("runtime_page_aggregate_mismatch")
    return result


def _validate_manifest_shape(manifest: dict[str, Any]) -> None:
    if (
        manifest.get("schemaVersion") != 1
        or manifest.get("packageVersion") != RUNTIME_PACKAGE_VERSION
        or manifest.get("capabilityVersion") != RUNTIME_CAPABILITY_VERSION
        or manifest.get("candidatePreparatoryOnly") is not True
    ):
        raise RuntimePackageError("runtime_manifest_version_unsupported")
    if manifest.get("fallbackOrder") != [
        "zeroone_dynamic",
        "zeroone_static",
        "conventional_glb",
        "failure",
    ]:
        raise RuntimePackageError("runtime_fallback_order_invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RuntimePackageError("runtime_artifacts_invalid")
    if set(artifacts) != {"zeroOneDynamic", "zeroOneStatic", "conventionalGlb"}:
        raise RuntimePackageError("runtime_artifacts_invalid")
    artifact_paths = [value for value in artifacts.values() if isinstance(value, str)]
    if any(value is not None and not isinstance(value, str) for value in artifacts.values()):
        raise RuntimePackageError("runtime_artifacts_invalid")
    for path in artifact_paths:
        _validate_reference_path(path)
    if len(artifact_paths) != len(set(artifact_paths)):
        raise RuntimePackageError("runtime_duplicate_authority")
    motion = manifest.get("motion")
    if not isinstance(motion, dict) or not isinstance(motion.get("prebakedOptions"), list):
        raise RuntimePackageError("runtime_prebaked_pose_missing")
    options = motion["prebakedOptions"]
    if len(options) < 1 or any(
        not isinstance(option, dict)
        or not isinstance(option.get("poseId"), str)
        or not isinstance(option.get("path"), str)
        for option in options
    ):
        raise RuntimePackageError("runtime_prebaked_pose_missing")
    for option in options:
        _validate_reference_path(str(option["path"]))
    if motion.get("actualZeroOneDynamicDeformationExecuted") is not False:
        raise RuntimePackageError("runtime_dynamic_overclaim")
    pages = manifest.get("pages")
    if not isinstance(pages, dict) or pages.get("compression") != "zlib":
        raise RuntimePackageError("runtime_pages_invalid")
    if not isinstance(pages.get("records"), list) or not pages["records"]:
        raise RuntimePackageError("runtime_pages_invalid")
    page_paths: list[str] = []
    for record in pages["records"]:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise RuntimePackageError("runtime_pages_invalid")
        page_path = str(record["path"])
        _validate_reference_path(page_path)
        page_paths.append(page_path)
    motion_paths = [str(option["path"]) for option in options]
    all_authorities = [*artifact_paths, *motion_paths, *page_paths]
    if len(all_authorities) != len(set(all_authorities)):
        raise RuntimePackageError("runtime_duplicate_authority")
    if not isinstance(manifest.get("inventory"), list):
        raise RuntimePackageError("runtime_inventory_invalid")
    _validate_source_link(manifest.get("sourceLink"))


def _validate_exact_inventory(
    root: Path, manifest: dict[str, Any], limits: RuntimeLimits
) -> dict[str, Path]:
    declared: dict[str, dict[str, Any]] = {}
    total_declared = 0
    for entry in manifest["inventory"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise RuntimePackageError("runtime_inventory_invalid")
        rel = str(entry["path"])
        try:
            validate_package_relpath(rel)
        except ValueError as error:
            raise RuntimePackageError("runtime_inventory_path_invalid") from error
        if len(Path(rel).parts) > limits.max_depth:
            raise RuntimePackageError("runtime_nesting_limit_exceeded")
        if rel in declared:
            raise RuntimePackageError("runtime_inventory_duplicate")
        size = _bounded_int(entry.get("byteSize"), "runtime_inventory_size_invalid")
        if size > limits.max_file_bytes:
            raise RuntimePackageError("runtime_file_limit_exceeded")
        total_declared += size
        declared[rel] = entry
    if len(declared) > limits.max_file_count or total_declared > limits.max_total_bytes:
        raise RuntimePackageError("runtime_inventory_limit_exceeded")
    if _inventory_digest(list(declared.values())) != manifest.get("packageDigest"):
        raise RuntimePackageError("runtime_package_digest_mismatch")

    actual = _walk_real_files(root, limits)
    expected_paths = set(declared) | {"manifest.json", MARKER_NAME}
    if set(actual) != expected_paths:
        raise RuntimePackageError("runtime_exact_inventory_mismatch")
    for rel, entry in declared.items():
        path = actual[rel]
        metadata = path.stat(follow_symlinks=False)
        if metadata.st_size != entry["byteSize"] or sha256_file(path) != entry.get("sha256"):
            raise RuntimePackageError("runtime_inventory_hash_mismatch")
    return actual


def _inventory(root: Path, limits: RuntimeLimits) -> list[dict[str, Any]]:
    files = _walk_real_files(root, limits)
    records = []
    for rel, path in sorted(files.items()):
        if rel in {MARKER_NAME, "manifest.json"}:
            continue
        records.append(
            {
                "path": rel,
                "byteSize": path.stat(follow_symlinks=False).st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def _walk_real_files(root: Path, limits: RuntimeLimits) -> dict[str, Path]:
    found: dict[str, Path] = {}
    total = 0
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as children:
            for child in children:
                path = Path(child.path)
                metadata = path.stat(follow_symlinks=False)
                if _is_link_like(metadata):
                    raise RuntimePackageError("runtime_link_rejected")
                rel = path.relative_to(root).as_posix()
                if len(Path(rel).parts) > limits.max_depth:
                    raise RuntimePackageError("runtime_nesting_limit_exceeded")
                if stat.S_ISDIR(metadata.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(metadata.st_mode):
                    if metadata.st_nlink != 1:
                        raise RuntimePackageError("runtime_hardlink_rejected")
                    total += metadata.st_size
                    if metadata.st_size > max(limits.max_file_bytes, _MANIFEST_MAX_BYTES):
                        raise RuntimePackageError("runtime_file_limit_exceeded")
                    found[rel] = path
                else:
                    raise RuntimePackageError("runtime_special_file_rejected")
    if (
        len(found) > limits.max_file_count + 2
        or total > limits.max_total_bytes + _MANIFEST_MAX_BYTES
    ):
        raise RuntimePackageError("runtime_tree_limit_exceeded")
    return found


def _validate_source_link(value: object) -> None:
    if not isinstance(value, dict):
        raise RuntimePackageError("runtime_source_link_invalid")
    required = {
        "opaqueId",
        "consentScope",
        "retentionPolicy",
        "deletionPolicy",
        "derivationPolicy",
        "withdrawalStatus",
    }
    if set(value) != required or value.get("withdrawalStatus") not in {"active", "withdrawn"}:
        raise RuntimePackageError("runtime_source_link_invalid")
    opaque = value.get("opaqueId")
    if not isinstance(opaque, str) or not opaque.startswith("src_") or len(opaque) > 80:
        raise RuntimePackageError("runtime_source_link_invalid")
    for item in value.values():
        if isinstance(item, str) and _contains_raw_digest(item):
            raise RuntimePackageError("runtime_private_digest_linkage_rejected")


def _contains_raw_digest(value: str) -> bool:
    return _RAW_DIGEST_RE.search(value) is not None


def _artifact_path(manifest: dict[str, Any], key: str) -> str:
    value = manifest["artifacts"].get(key)
    if not isinstance(value, str):
        raise RuntimePackageError("runtime_required_artifact_missing")
    return value


def _declared_file(files: dict[str, Path], relative: str) -> Path:
    if relative in {MARKER_NAME, "manifest.json"}:
        raise RuntimePackageError("runtime_reference_not_in_inventory")
    try:
        return files[relative]
    except KeyError as error:
        raise RuntimePackageError("runtime_reference_not_in_inventory") from error


def _validate_reference_path(relative: str) -> None:
    try:
        validate_package_relpath(relative)
    except ValueError as error:
        raise RuntimePackageError("runtime_reference_path_invalid") from error
    if relative in {MARKER_NAME, "manifest.json"}:
        raise RuntimePackageError("runtime_reference_path_invalid")


def _inventory_digest(inventory: list[dict[str, Any]]) -> str:
    payload = "\n".join(
        f"{entry['path']}\0{entry['byteSize']}\0{entry['sha256']}"
        for entry in sorted(inventory, key=lambda item: str(item["path"]))
    )
    return sha256_bytes(payload.encode("utf-8"))


def _read_stable_file(path: Path, maximum_bytes: int) -> bytes:
    try:
        before = path.stat(follow_symlinks=False)
    except OSError as error:
        raise RuntimePackageError("runtime_source_file_missing") from error
    if _is_link_like(before) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise RuntimePackageError("runtime_source_file_unsafe")
    if before.st_size > maximum_bytes:
        raise RuntimePackageError("runtime_file_limit_exceeded")
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        data = handle.read(maximum_bytes + 1)
        after = os.fstat(handle.fileno())
    if (
        len(data) > maximum_bytes
        or opened.st_size != before.st_size
        or after.st_size != before.st_size
        or getattr(opened, "st_ino", 0) != getattr(after, "st_ino", 0)
    ):
        raise RuntimePackageError("runtime_source_file_changed")
    return data


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _validate_real_directory(path: Path) -> None:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as error:
        raise RuntimePackageError("runtime_package_missing") from error
    if _is_link_like(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimePackageError("runtime_package_not_real_directory")


def _is_link_like(metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & reparse_flag
    )


def _bounded_int(value: object, code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RuntimePackageError(code)
    return value
