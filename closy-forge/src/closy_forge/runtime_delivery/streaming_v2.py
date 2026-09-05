from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.package_io.managed_output import (
    MARKER_NAME,
    cleanup_managed_staging,
    create_managed_staging,
    publish_managed_staging,
)
from closy_forge.package_io.paths import validate_package_relpath

from .package_v2 import LoadedRuntimePackageV2, RuntimeV2Limits, load_runtime_package_v2
from .streaming import TransferError, TransferLimits, TransferReceiver, build_chunk_inventory

STREAM_V2 = "closy.runtime.stream.local_transport.v2"
_ARCHIVE_MAGIC = b"CLSRTP2\0"


@dataclass(frozen=True)
class RuntimeStreamV2:
    manifest: dict[str, Any]
    payload: bytes
    chunks: tuple[bytes, ...]


class RuntimeStreamReceiverV2:
    """Deterministic local transport simulator; it makes no networking claim."""

    def __init__(
        self,
        cache_root: Path,
        stream: RuntimeStreamV2,
        *,
        session_id: str,
        limits: TransferLimits | None = None,
    ) -> None:
        if stream.manifest.get("streamVersion") != STREAM_V2:
            raise TransferError("transfer_v2_version_unsupported")
        inventory = stream.manifest.get("transportInventory")
        if not isinstance(inventory, dict):
            raise TransferError("transfer_v2_inventory_missing")
        self._stream = stream
        self._cancelled = False
        self._receiver = TransferReceiver(
            cache_root,
            inventory,
            session_id=session_id,
            limits=limits,
        )

    @property
    def missing_indices(self) -> tuple[int, ...]:
        return self._receiver.missing_indices

    @property
    def received_indices(self) -> tuple[int, ...]:
        return self._receiver.received_indices

    @property
    def resume_bytes_saved(self) -> int:
        records = self._stream.manifest["transportInventory"]["chunks"]
        return sum(int(records[index]["byteSize"]) for index in self.received_indices)

    def cancel(self) -> None:
        self._cancelled = True

    def receive(self, index: int, payload: bytes) -> None:
        if self._cancelled:
            raise TransferError("transfer_cancelled")
        self._receiver.receive(index, payload)

    def finalize_archive(self, destination: Path) -> Path:
        if self._cancelled:
            raise TransferError("transfer_cancelled")
        return self._receiver.finalize(destination)


def build_runtime_stream_v2(
    package: Path,
    *,
    chunk_size: int,
    limits: TransferLimits | None = None,
) -> RuntimeStreamV2:
    loaded = load_runtime_package_v2(package)
    ordered_files = _ordered_package_files(package)
    payload = _encode_archive(package, ordered_files)
    inventory = build_chunk_inventory(payload, chunk_size=chunk_size, limits=limits)
    chunks = tuple(
        payload[offset : offset + chunk_size] for offset in range(0, len(payload), chunk_size)
    )
    fallback_paths = _fallback_dependency_paths(package)
    fallback_end = max(
        _archive_end_offset(package, ordered_files, relative) for relative in fallback_paths
    )
    fallback_ready_chunks = (fallback_end + chunk_size - 1) // chunk_size
    manifest = {
        "schemaVersion": 2,
        "streamVersion": STREAM_V2,
        "transportKind": "deterministic_local_fixture_not_network_service",
        "packageDigest": loaded.package_digest,
        "dependencyOrder": ordered_files,
        "fallbackDependencies": fallback_paths,
        "fallbackReadyChunkCount": fallback_ready_chunks,
        "aggregateSha256": sha256_bytes(payload),
        "transportInventory": inventory,
    }
    return RuntimeStreamV2(manifest=manifest, payload=payload, chunks=chunks)


def load_fallback_from_archive_prefix_v2(
    archive_prefix: bytes,
    *,
    limits: RuntimeV2Limits | None = None,
) -> bytes:
    """Validate and decode the conventional GLB before the complete archive arrives."""

    active = limits or RuntimeV2Limits()
    files = _archive_prefix_entries(archive_prefix, active)
    manifest_bytes = files.get("manifest.json")
    if manifest_bytes is None:
        raise TransferError("transfer_v2_fallback_manifest_pending")
    try:
        import json

        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise TransferError("transfer_v2_fallback_manifest_invalid") from error
    if not isinstance(manifest, dict) or manifest.get("packageVersion") != (
        "closy.runtime.conventional.v2"
    ):
        raise TransferError("transfer_v2_fallback_manifest_invalid")
    inventory = manifest.get("inventory")
    assets = manifest.get("assets")
    blobs = manifest.get("blobs")
    if (
        not isinstance(inventory, list)
        or not isinstance(assets, dict)
        or not isinstance(blobs, dict)
    ):
        raise TransferError("transfer_v2_fallback_manifest_invalid")
    inventory_by_path = {str(row.get("path")): row for row in inventory if isinstance(row, dict)}
    fallback = assets.get("conventionalFallback")
    if not isinstance(fallback, dict) or not isinstance(fallback.get("pages"), list):
        raise TransferError("transfer_v2_fallback_manifest_invalid")
    output = bytearray()
    expected_offset = 0
    for expected_index, page in enumerate(fallback["pages"]):
        if (
            not isinstance(page, dict)
            or page.get("index") != expected_index
            or page.get("sourceOffset") != expected_offset
        ):
            raise TransferError("transfer_v2_fallback_page_order_invalid")
        digest = page.get("blob")
        blob = blobs.get(digest) if isinstance(digest, str) else None
        if not isinstance(blob, dict) or not isinstance(blob.get("path"), str):
            raise TransferError("transfer_v2_fallback_blob_invalid")
        path = str(blob["path"])
        payload = files.get(path)
        if payload is None:
            raise TransferError("transfer_v2_fallback_pending")
        inventory_row = inventory_by_path.get(path)
        if (
            not isinstance(inventory_row, dict)
            or inventory_row.get("byteSize") != len(payload)
            or inventory_row.get("sha256") != sha256_bytes(payload)
            or blob.get("compressedBytes") != len(payload)
            or blob.get("compressedSha256") != sha256_bytes(payload)
        ):
            raise TransferError("transfer_v2_fallback_blob_corrupt")
        decoded_size = blob.get("decodedBytes")
        if (
            not isinstance(decoded_size, int)
            or isinstance(decoded_size, bool)
            or decoded_size < 1
            or decoded_size > active.max_decoded_page_bytes
            or len(payload) == 0
            or decoded_size / len(payload) > active.max_decompression_ratio
        ):
            raise TransferError("transfer_v2_fallback_decompression_limit")
        decoder = zlib.decompressobj()
        try:
            decoded = decoder.decompress(payload, decoded_size + 1)
        except zlib.error as error:
            raise TransferError("transfer_v2_fallback_decompression_failed") from error
        if (
            len(decoded) != decoded_size
            or not decoder.eof
            or decoder.unused_data
            or decoder.unconsumed_tail
            or sha256_bytes(decoded) != digest
            or page.get("decodedBytes") != len(decoded)
        ):
            raise TransferError("transfer_v2_fallback_decoded_mismatch")
        output.extend(decoded)
        expected_offset += len(decoded)
        if expected_offset > active.max_decoded_working_set_bytes:
            raise TransferError("transfer_v2_fallback_working_set_exceeded")
    result = bytes(output)
    if (
        len(result) != fallback.get("decodedBytes")
        or sha256_bytes(result) != fallback.get("decodedSha256")
        or len(result) < 20
        or result[:4] != b"glTF"
    ):
        raise TransferError("transfer_v2_fallback_identity_mismatch")
    for dependency in ("capabilities.json", "materials.json"):
        payload = files.get(dependency)
        row = inventory_by_path.get(dependency)
        if (
            payload is None
            or not isinstance(row, dict)
            or row.get("byteSize") != len(payload)
            or row.get("sha256") != sha256_bytes(payload)
        ):
            raise TransferError("transfer_v2_fallback_dependency_pending")
    return result


def materialize_runtime_archive_v2(
    archive: bytes,
    destination: Path,
    *,
    limits: RuntimeV2Limits | None = None,
) -> LoadedRuntimePackageV2:
    active = limits or RuntimeV2Limits()
    if len(archive) > active.max_total_bytes or not archive.startswith(_ARCHIVE_MAGIC):
        raise TransferError("transfer_v2_archive_invalid")
    cursor = len(_ARCHIVE_MAGIC)
    if cursor + 4 > len(archive):
        raise TransferError("transfer_v2_archive_truncated")
    count = struct.unpack_from("<I", archive, cursor)[0]
    cursor += 4
    if count == 0 or count > active.max_file_count:
        raise TransferError("transfer_v2_archive_count_invalid")
    if destination.exists() or destination.is_symlink():
        raise TransferError("transfer_v2_destination_exists")
    staging = create_managed_staging(
        destination,
        allowed_root=destination.parent,
        purpose="runtime-package-v2",
    )
    try:
        for _ in range(count):
            if cursor + 10 > len(archive):
                raise TransferError("transfer_v2_archive_truncated")
            name_length, payload_length = struct.unpack_from("<HQ", archive, cursor)
            cursor += 10
            if name_length == 0 or payload_length > active.max_file_bytes:
                raise TransferError("transfer_v2_archive_entry_invalid")
            end = cursor + name_length + payload_length
            if end > len(archive):
                raise TransferError("transfer_v2_archive_truncated")
            try:
                relative = archive[cursor : cursor + name_length].decode("utf-8")
            except UnicodeDecodeError as error:
                raise TransferError("transfer_v2_archive_path_invalid") from error
            cursor += name_length
            try:
                validate_package_relpath(relative)
            except ValueError as error:
                raise TransferError("transfer_v2_archive_path_invalid") from error
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive[cursor:end])
            cursor = end
        if cursor != len(archive):
            raise TransferError("transfer_v2_archive_trailing_bytes")
        publish_managed_staging(
            staging,
            destination,
            allowed_root=destination.parent,
            purpose="runtime-package-v2",
            force=False,
        )
        return load_runtime_package_v2(destination, limits=active)
    except BaseException:
        if staging.exists():
            cleanup_managed_staging(
                staging,
                allowed_root=destination.parent,
                purpose="runtime-package-v2",
            )
        raise


def _ordered_package_files(package: Path) -> list[str]:
    manifest = package / "manifest.json"
    if not manifest.is_file():
        raise TransferError("transfer_v2_package_manifest_missing")
    relative = sorted(
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file() and path.name != MARKER_NAME
    )
    fallback_paths = set(_fallback_dependency_paths(package))
    priorities = {
        "manifest.json": 0,
        "capabilities.json": 1,
        "materials.json": 2,
        "thumbnails/preview.png": 3,
        "build_report.json": 4,
    }
    return sorted(
        relative,
        key=lambda item: (
            priorities.get(item, 5 if item in fallback_paths else 10),
            item,
        ),
    )


def _fallback_dependency_paths(package: Path) -> list[str]:
    import json

    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    fallback = manifest["assets"]["conventionalFallback"]
    paths = ["manifest.json", "capabilities.json", "materials.json"]
    paths.extend(manifest["blobs"][page["blob"]]["path"] for page in fallback["pages"])
    return list(dict.fromkeys(paths))


def _encode_archive(package: Path, ordered_files: list[str]) -> bytes:
    output = bytearray(_ARCHIVE_MAGIC + struct.pack("<I", len(ordered_files)))
    for relative in ordered_files:
        encoded_name = relative.encode("utf-8")
        payload = (package / relative).read_bytes()
        output.extend(struct.pack("<HQ", len(encoded_name), len(payload)))
        output.extend(encoded_name)
        output.extend(payload)
    return bytes(output)


def _archive_end_offset(package: Path, ordered_files: list[str], target: str) -> int:
    cursor = len(_ARCHIVE_MAGIC) + 4
    for relative in ordered_files:
        encoded = relative.encode("utf-8")
        size = (package / relative).stat().st_size
        cursor += 10 + len(encoded) + size
        if relative == target:
            return cursor
    raise TransferError("transfer_v2_dependency_missing")


def _archive_prefix_entries(prefix: bytes, limits: RuntimeV2Limits) -> dict[str, bytes]:
    if len(prefix) > limits.max_total_bytes or not prefix.startswith(_ARCHIVE_MAGIC):
        raise TransferError("transfer_v2_archive_invalid")
    cursor = len(_ARCHIVE_MAGIC)
    if cursor + 4 > len(prefix):
        raise TransferError("transfer_v2_archive_truncated")
    count = struct.unpack_from("<I", prefix, cursor)[0]
    cursor += 4
    if count == 0 or count > limits.max_file_count:
        raise TransferError("transfer_v2_archive_count_invalid")
    files: dict[str, bytes] = {}
    for _ in range(count):
        if cursor + 10 > len(prefix):
            break
        name_length, payload_length = struct.unpack_from("<HQ", prefix, cursor)
        if name_length == 0 or payload_length > limits.max_file_bytes:
            raise TransferError("transfer_v2_archive_entry_invalid")
        entry_end = cursor + 10 + name_length + payload_length
        if entry_end > len(prefix):
            break
        cursor += 10
        try:
            relative = prefix[cursor : cursor + name_length].decode("utf-8")
            validate_package_relpath(relative)
        except (UnicodeDecodeError, ValueError) as error:
            raise TransferError("transfer_v2_archive_path_invalid") from error
        cursor += name_length
        if relative in files:
            raise TransferError("transfer_v2_archive_duplicate_path")
        files[relative] = prefix[cursor : cursor + payload_length]
        cursor += payload_length
    return files
