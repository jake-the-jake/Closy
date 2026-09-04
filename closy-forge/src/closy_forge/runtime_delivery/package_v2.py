from __future__ import annotations

import json
import math
import re
import stat
import struct
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.package_io.managed_output import (
    MARKER_NAME,
    cleanup_managed_staging,
    create_managed_staging,
    publish_managed_staging,
)
from closy_forge.package_io.paths import validate_package_relpath

RUNTIME_PACKAGE_V2 = "closy.runtime.conventional.v2"
RUNTIME_CAPABILITY_V2 = "closy.runtime.capabilities.conventional.v2"
POSE_PAYLOAD_V2 = "closy.runtime.pose_positions.f32.v2"
_POSE_MAGIC = b"CLSPV2\0\0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RuntimePackageV2Error(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RuntimeV2Limits:
    max_file_count: int = 4096
    max_file_bytes: int = 67_108_864
    max_total_bytes: int = 134_217_728
    max_decoded_page_bytes: int = 65_536
    max_decoded_working_set_bytes: int = 134_217_728
    max_decompression_ratio: float = 128.0


@dataclass(frozen=True)
class RuntimeV2Profile:
    profile_id: str
    source_page_bytes: int
    transport_chunk_bytes: int

    def validate(self, limits: RuntimeV2Limits) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", self.profile_id):
            raise RuntimePackageV2Error("runtime_v2_profile_id_invalid")
        if not 1 <= self.source_page_bytes <= limits.max_decoded_page_bytes:
            raise RuntimePackageV2Error("runtime_v2_page_size_invalid")
        if not 1 <= self.transport_chunk_bytes <= limits.max_decoded_page_bytes:
            raise RuntimePackageV2Error("runtime_v2_transport_chunk_size_invalid")


@dataclass(frozen=True)
class RuntimeV2Inputs:
    garment_id: str
    canonical_package_digest: str
    conventional_fallback_glb: Path
    material_set: Mapping[str, Any]
    thumbnail_png: bytes
    pose_positions: Mapping[str, Sequence[Sequence[float]]]
    zeroone_derivative_digest: str | None = None


@dataclass(frozen=True)
class LoadedRuntimePackageV2:
    package_digest: str
    garment_id: str
    profile_id: str
    conventional_fallback_glb: bytes
    pose_positions: dict[str, tuple[tuple[float, float, float], ...]]
    fallback_reason: str | None = None


def build_runtime_package_v2(
    target: Path,
    *,
    inputs: RuntimeV2Inputs,
    profile: RuntimeV2Profile,
    force: bool = False,
    limits: RuntimeV2Limits | None = None,
) -> Path:
    active = limits or RuntimeV2Limits()
    profile.validate(active)
    _validate_inputs(inputs)
    if target.suffix != ".closyruntime":
        raise RuntimePackageV2Error("runtime_v2_package_suffix_required")
    staging = create_managed_staging(
        target,
        allowed_root=target.parent,
        purpose="runtime-package-v2",
    )
    try:
        fallback = _read_regular(inputs.conventional_fallback_glb, active.max_file_bytes)
        if len(fallback) < 20 or fallback[:4] != b"glTF":
            raise RuntimePackageV2Error("runtime_v2_fallback_not_glb")
        poses = {
            pose_id: encode_pose_positions(positions)
            for pose_id, positions in sorted(inputs.pose_positions.items())
        }
        assets = {
            "conventionalFallback": fallback,
            **{f"pose:{key}": value for key, value in poses.items()},
        }
        blob_records: dict[str, dict[str, Any]] = {}
        asset_records: dict[str, dict[str, Any]] = {}
        equivalent_v1_duplicate_bytes = 0
        for asset_id, payload in assets.items():
            pages: list[dict[str, Any]] = []
            for index, offset in enumerate(range(0, len(payload), profile.source_page_bytes)):
                raw = payload[offset : offset + profile.source_page_bytes]
                encoded = _bounded_zlib_encode(raw, active.max_decompression_ratio)
                raw_digest = sha256_bytes(raw)
                blob_path = f"blobs/{raw_digest}.zlib"
                existing = blob_records.get(raw_digest)
                record = {
                    "path": blob_path,
                    "compressedBytes": len(encoded),
                    "compressedSha256": sha256_bytes(encoded),
                    "decodedBytes": len(raw),
                    "decodedSha256": raw_digest,
                }
                if existing is not None and existing != record:
                    raise RuntimePackageV2Error("runtime_v2_blob_identity_collision")
                if existing is None:
                    _write_bytes(staging / blob_path, encoded)
                    blob_records[raw_digest] = record
                pages.append(
                    {
                        "index": index,
                        "sourceOffset": offset,
                        "blob": raw_digest,
                        "decodedBytes": len(raw),
                    }
                )
                equivalent_v1_duplicate_bytes += len(raw) + len(encoded)
            asset_records[asset_id] = {
                "decodedBytes": len(payload),
                "decodedSha256": sha256_bytes(payload),
                "pages": pages,
            }

        capabilities = {
            "schemaVersion": 1,
            "capabilityVersion": RUNTIME_CAPABILITY_V2,
            "selection": "conventional_glb_fallback_first",
            "optionalZeroOneStatic": inputs.zeroone_derivative_digest is not None,
            "zeroOneDynamic": False,
            "productRuntimeDefaultChanged": False,
        }
        materials = {"schemaVersion": 1, "materials": dict(inputs.material_set)}
        write_canonical_json(staging / "capabilities.json", capabilities)
        write_canonical_json(staging / "materials.json", materials)
        _write_bytes(staging / "thumbnails" / "preview.png", inputs.thumbnail_png)
        compressed_payload_bytes = sum(
            int(record["compressedBytes"]) for record in blob_records.values()
        )
        build_report = {
            "schemaVersion": 1,
            "reportVersion": "closy.runtime.conventional_build.v2",
            "profileId": profile.profile_id,
            "assetCount": len(asset_records),
            "uniqueCompressedBlobCount": len(blob_records),
            "compressedPayloadBytes": compressed_payload_bytes,
            "equivalentPayloadV1DuplicateBytes": equivalent_v1_duplicate_bytes,
            "smallerThanEquivalentDuplicateStorageV1": (
                compressed_payload_bytes < equivalent_v1_duplicate_bytes
            ),
            "deterministic": True,
        }
        write_canonical_json(staging / "build_report.json", build_report)
        inventory = _inventory(staging, active)
        package_digest = _inventory_digest(inventory)
        manifest = {
            "schemaVersion": 2,
            "packageVersion": RUNTIME_PACKAGE_V2,
            "capabilityVersion": RUNTIME_CAPABILITY_V2,
            "classification": "derivative_runtime_profile_not_canonical_garment",
            "garmentId": inputs.garment_id,
            "canonicalPackageDigest": inputs.canonical_package_digest,
            "profile": {
                "id": profile.profile_id,
                "sourcePageBytes": profile.source_page_bytes,
                "transportChunkBytes": profile.transport_chunk_bytes,
            },
            "selection": {
                "fallbackFirst": True,
                "defaultAsset": "conventionalFallback",
                "productRuntimeV1Unchanged": True,
            },
            "assets": asset_records,
            "blobs": {key: blob_records[key] for key in sorted(blob_records)},
            "poseEncoding": POSE_PAYLOAD_V2,
            "zeroOneStaticDerivativeDigest": inputs.zeroone_derivative_digest,
            "inventory": inventory,
            "packageDigest": package_digest,
            "evidenceTruth": {
                "hostCpu": True,
                "mobileDevice": False,
                "gpu": False,
                "battery": False,
                "thermal": False,
                "productionNetwork": False,
            },
        }
        _validate_manifest(manifest)
        write_canonical_json(staging / "manifest.json", manifest)
        publish_managed_staging(
            staging,
            target,
            allowed_root=target.parent,
            purpose="runtime-package-v2",
            force=force,
        )
    except BaseException:
        cleanup_managed_staging(
            staging,
            allowed_root=target.parent,
            purpose="runtime-package-v2",
        )
        raise
    return target


def load_runtime_package_v2(
    package: Path,
    *,
    limits: RuntimeV2Limits | None = None,
    last_good_package: Path | None = None,
) -> LoadedRuntimePackageV2:
    active = limits or RuntimeV2Limits()
    try:
        return _load_runtime_package_v2(package, active)
    except RuntimePackageV2Error as error:
        if last_good_package is None or last_good_package.resolve(strict=False) == package.resolve(
            strict=False
        ):
            raise
        loaded = _load_runtime_package_v2(last_good_package, active)
        return replace(loaded, fallback_reason=f"last_good_after:{error.code}")


def encode_pose_positions(positions: Sequence[Sequence[float]]) -> bytes:
    if not positions or len(positions) > 10_000_000:
        raise RuntimePackageV2Error("runtime_v2_pose_count_invalid")
    scalars: list[float] = []
    for position in positions:
        if len(position) != 3:
            raise RuntimePackageV2Error("runtime_v2_pose_width_invalid")
        values = tuple(float(value) for value in position)
        if not all(math.isfinite(value) for value in values):
            raise RuntimePackageV2Error("runtime_v2_pose_nonfinite")
        scalars.extend(values)
    return (
        _POSE_MAGIC + struct.pack("<I", len(positions)) + struct.pack(f"<{len(scalars)}f", *scalars)
    )


def decode_pose_positions(payload: bytes) -> tuple[tuple[float, float, float], ...]:
    if len(payload) < 12 or payload[:8] != _POSE_MAGIC:
        raise RuntimePackageV2Error("runtime_v2_pose_header_invalid")
    count = struct.unpack_from("<I", payload, 8)[0]
    expected = 12 + count * 12
    if count == 0 or expected != len(payload):
        raise RuntimePackageV2Error("runtime_v2_pose_length_invalid")
    values = struct.unpack_from(f"<{count * 3}f", payload, 12)
    if not all(math.isfinite(value) for value in values):
        raise RuntimePackageV2Error("runtime_v2_pose_nonfinite")
    return tuple(
        (float(values[index]), float(values[index + 1]), float(values[index + 2]))
        for index in range(0, len(values), 3)
    )


def _load_runtime_package_v2(package: Path, limits: RuntimeV2Limits) -> LoadedRuntimePackageV2:
    _validate_directory(package)
    manifest = _read_object(package / "manifest.json", 1_048_576)
    _validate_manifest(manifest)
    files = _validate_inventory(package, manifest, limits)
    blobs = manifest["blobs"]

    def decode_asset(asset_id: str) -> bytes:
        record = manifest["assets"].get(asset_id)
        if not isinstance(record, dict):
            raise RuntimePackageV2Error("runtime_v2_asset_missing")
        output = bytearray()
        expected_offset = 0
        for expected_index, page in enumerate(record.get("pages", [])):
            if page.get("index") != expected_index or page.get("sourceOffset") != expected_offset:
                raise RuntimePackageV2Error("runtime_v2_page_order_invalid")
            raw_digest = str(page.get("blob"))
            blob = blobs.get(raw_digest)
            if not isinstance(blob, dict):
                raise RuntimePackageV2Error("runtime_v2_blob_missing")
            raw = _decode_blob(blob, files, limits)
            if len(raw) != page.get("decodedBytes") or sha256_bytes(raw) != raw_digest:
                raise RuntimePackageV2Error("runtime_v2_page_identity_mismatch")
            expected_offset += len(raw)
            if expected_offset > limits.max_decoded_working_set_bytes:
                raise RuntimePackageV2Error("runtime_v2_working_set_exceeded")
            output.extend(raw)
        payload = bytes(output)
        if len(payload) != record.get("decodedBytes") or sha256_bytes(payload) != record.get(
            "decodedSha256"
        ):
            raise RuntimePackageV2Error("runtime_v2_asset_identity_mismatch")
        return payload

    fallback = decode_asset("conventionalFallback")
    if len(fallback) < 20 or fallback[:4] != b"glTF":
        raise RuntimePackageV2Error("runtime_v2_fallback_not_glb")
    poses = {
        key.removeprefix("pose:"): decode_pose_positions(decode_asset(key))
        for key in sorted(manifest["assets"])
        if key.startswith("pose:")
    }
    return LoadedRuntimePackageV2(
        package_digest=str(manifest["packageDigest"]),
        garment_id=str(manifest["garmentId"]),
        profile_id=str(manifest["profile"]["id"]),
        conventional_fallback_glb=fallback,
        pose_positions=poses,
    )


def _decode_blob(
    record: Mapping[str, Any], files: Mapping[str, Path], limits: RuntimeV2Limits
) -> bytes:
    path = str(record.get("path"))
    compressed = _read_regular(_declared(files, path), limits.max_file_bytes)
    if len(compressed) != record.get("compressedBytes") or sha256_bytes(compressed) != record.get(
        "compressedSha256"
    ):
        raise RuntimePackageV2Error("runtime_v2_compressed_blob_corrupt")
    decoded_bytes = _positive_int(record.get("decodedBytes"), "runtime_v2_blob_size_invalid")
    if decoded_bytes > limits.max_decoded_page_bytes:
        raise RuntimePackageV2Error("runtime_v2_decoded_page_exceeded")
    if len(compressed) == 0 or decoded_bytes / len(compressed) > limits.max_decompression_ratio:
        raise RuntimePackageV2Error("runtime_v2_decompression_ratio_exceeded")
    decoder = zlib.decompressobj()
    try:
        decoded = decoder.decompress(compressed, decoded_bytes + 1)
    except zlib.error as error:
        raise RuntimePackageV2Error("runtime_v2_decompression_failed") from error
    if (
        len(decoded) != decoded_bytes
        or not decoder.eof
        or decoder.unused_data
        or decoder.unconsumed_tail
        or sha256_bytes(decoded) != record.get("decodedSha256")
    ):
        raise RuntimePackageV2Error("runtime_v2_decoded_blob_mismatch")
    return decoded


def _bounded_zlib_encode(raw: bytes, maximum_ratio: float) -> bytes:
    encoded = zlib.compress(raw, level=9)
    if len(encoded) == 0 or len(raw) / len(encoded) > maximum_ratio:
        encoded = zlib.compress(raw, level=0)
    if len(encoded) == 0 or len(raw) / len(encoded) > maximum_ratio:
        raise RuntimePackageV2Error("runtime_v2_compression_ratio_unbounded")
    return encoded


def _validate_inputs(inputs: RuntimeV2Inputs) -> None:
    if not inputs.garment_id.startswith("garment."):
        raise RuntimePackageV2Error("runtime_v2_garment_id_invalid")
    if not _SHA256_RE.fullmatch(inputs.canonical_package_digest):
        raise RuntimePackageV2Error("runtime_v2_canonical_digest_invalid")
    if inputs.zeroone_derivative_digest is not None and not _SHA256_RE.fullmatch(
        inputs.zeroone_derivative_digest
    ):
        raise RuntimePackageV2Error("runtime_v2_zeroone_digest_invalid")
    if not inputs.thumbnail_png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimePackageV2Error("runtime_v2_thumbnail_not_png")
    if set(inputs.pose_positions) != {
        "pose.neutral",
        "pose.arms_up",
        "pose.torso_twist",
        "pose.walk_stride",
    }:
        raise RuntimePackageV2Error("runtime_v2_pose_denominator_invalid")


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    if (
        manifest.get("schemaVersion") != 2
        or manifest.get("packageVersion") != RUNTIME_PACKAGE_V2
        or manifest.get("capabilityVersion") != RUNTIME_CAPABILITY_V2
        or manifest.get("classification") != "derivative_runtime_profile_not_canonical_garment"
    ):
        raise RuntimePackageV2Error("runtime_v2_manifest_version_unsupported")
    selection = manifest.get("selection")
    if selection != {
        "fallbackFirst": True,
        "defaultAsset": "conventionalFallback",
        "productRuntimeV1Unchanged": True,
    }:
        raise RuntimePackageV2Error("runtime_v2_selection_invalid")
    profile = manifest.get("profile")
    if not isinstance(profile, dict):
        raise RuntimePackageV2Error("runtime_v2_profile_invalid")
    RuntimeV2Profile(
        profile_id=str(profile.get("id", "")),
        source_page_bytes=_positive_int(
            profile.get("sourcePageBytes"), "runtime_v2_profile_invalid"
        ),
        transport_chunk_bytes=_positive_int(
            profile.get("transportChunkBytes"), "runtime_v2_profile_invalid"
        ),
    ).validate(RuntimeV2Limits())
    assets = manifest.get("assets")
    blobs = manifest.get("blobs")
    inventory = manifest.get("inventory")
    if not isinstance(assets, dict) or "conventionalFallback" not in assets:
        raise RuntimePackageV2Error("runtime_v2_assets_invalid")
    if not isinstance(blobs, dict) or not blobs or not isinstance(inventory, list):
        raise RuntimePackageV2Error("runtime_v2_inventory_invalid")
    if manifest.get("evidenceTruth") != {
        "hostCpu": True,
        "mobileDevice": False,
        "gpu": False,
        "battery": False,
        "thermal": False,
        "productionNetwork": False,
    }:
        raise RuntimePackageV2Error("runtime_v2_evidence_truth_invalid")


def _inventory(root: Path, limits: RuntimeV2Limits) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimePackageV2Error("runtime_v2_link_rejected")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in {MARKER_NAME, "manifest.json"}:
            continue
        size = path.stat().st_size
        total += size
        records.append({"path": relative, "byteSize": size, "sha256": sha256_file(path)})
    if len(records) > limits.max_file_count or total > limits.max_total_bytes:
        raise RuntimePackageV2Error("runtime_v2_inventory_limit_exceeded")
    return records


def _validate_inventory(
    root: Path, manifest: Mapping[str, Any], limits: RuntimeV2Limits
) -> dict[str, Path]:
    rows = manifest["inventory"]
    records: dict[str, Mapping[str, Any]] = {}
    total = 0
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise RuntimePackageV2Error("runtime_v2_inventory_invalid")
        relative = str(row["path"])
        try:
            validate_package_relpath(relative)
        except ValueError as error:
            raise RuntimePackageV2Error("runtime_v2_inventory_path_invalid") from error
        size = _positive_int(row.get("byteSize"), "runtime_v2_inventory_size_invalid", zero=True)
        if relative in records:
            raise RuntimePackageV2Error("runtime_v2_inventory_duplicate")
        total += size
        records[relative] = row
    if len(records) > limits.max_file_count or total > limits.max_total_bytes:
        raise RuntimePackageV2Error("runtime_v2_inventory_limit_exceeded")
    if _inventory_digest(rows) != manifest.get("packageDigest"):
        raise RuntimePackageV2Error("runtime_v2_package_digest_mismatch")
    actual: dict[str, Path] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimePackageV2Error("runtime_v2_link_rejected")
        if path.is_file():
            actual[path.relative_to(root).as_posix()] = path
    if set(actual) != set(records) | {"manifest.json", MARKER_NAME}:
        raise RuntimePackageV2Error("runtime_v2_exact_inventory_mismatch")
    for relative, row in records.items():
        path = actual[relative]
        if path.stat().st_size != row["byteSize"] or sha256_file(path) != row.get("sha256"):
            raise RuntimePackageV2Error("runtime_v2_inventory_hash_mismatch")
    return actual


def _inventory_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = "\n".join(
        f"{row['path']}\0{row['byteSize']}\0{row['sha256']}"
        for row in sorted(rows, key=lambda value: str(value["path"]))
    )
    return sha256_bytes(payload.encode())


def _validate_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise RuntimePackageV2Error("runtime_v2_package_directory_invalid")
    mode = path.stat(follow_symlinks=False).st_mode
    if not stat.S_ISDIR(mode):
        raise RuntimePackageV2Error("runtime_v2_package_directory_invalid")


def _declared(files: Mapping[str, Path], relative: str) -> Path:
    try:
        validate_package_relpath(relative)
    except ValueError as error:
        raise RuntimePackageV2Error("runtime_v2_reference_path_invalid") from error
    path = files.get(relative)
    if path is None:
        raise RuntimePackageV2Error("runtime_v2_reference_not_in_inventory")
    return path


def _read_object(path: Path, maximum: int) -> dict[str, Any]:
    try:
        value = json.loads(_read_regular(path, maximum).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimePackageV2Error("runtime_v2_json_invalid") from error
    if not isinstance(value, dict):
        raise RuntimePackageV2Error("runtime_v2_json_object_required")
    return value


def _read_regular(path: Path, maximum: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RuntimePackageV2Error("runtime_v2_regular_file_required")
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
        raise RuntimePackageV2Error("runtime_v2_file_limit_exceeded")
    with path.open("rb") as handle:
        payload = handle.read(maximum + 1)
    after = path.stat(follow_symlinks=False)
    if len(payload) > maximum or (before.st_dev, before.st_ino, before.st_size) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
    ):
        raise RuntimePackageV2Error("runtime_v2_file_changed_during_read")
    return payload


def _positive_int(value: Any, code: str, *, zero: bool = False) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < (0 if zero else 1):
        raise RuntimePackageV2Error(code)
    return value


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
