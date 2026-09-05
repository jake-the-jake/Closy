"""Trusted V3 envelope over the frozen CLSRTP2 archive and TransferReceiver."""

from __future__ import annotations

import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.security.strict_json import loads_strict_json_object

from .package_v2 import RuntimeV2Limits
from .package_v3 import (
    MAX_MANIFEST_BYTES,
    LoadedRuntimePackageV3,
    RuntimeIdentityV3,
    RuntimeV3Error,
    decode_glb_v3,
    load_runtime_package_v3,
    read_bounded_v3,
    reject_links_v3,
    safe_relative_v3,
    trusted_manifest_v3,
    validate_nested_v3,
)
from .streaming import TransferError, TransferLimits, TransferReceiver, build_chunk_inventory
from .streaming_v2 import load_fallback_from_archive_prefix_v2

STREAM_V3 = "closy.runtime.stream.v3"


@dataclass(frozen=True)
class RuntimeStreamV3:
    manifest: dict[str, Any]
    payload: bytes
    chunks: tuple[bytes, ...]


def transfer_identity_v3(manifest: dict[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(manifest).encode())


def build_runtime_stream_v3(
    package: Path,
    *,
    expected: RuntimeIdentityV3,
    trusted_manifest_hash: str,
    chunk_size: int,
    limits: TransferLimits | None = None,
) -> RuntimeStreamV3:
    load_runtime_package_v3(package, expected=expected, trusted_manifest_hash=trusted_manifest_hash)
    manifest_bytes = read_bounded_v3(package / "manifest.json", MAX_MANIFEST_BYTES)
    _, rows = trusted_manifest_v3(
        manifest_bytes, expected=expected, trusted_manifest_hash=trusted_manifest_hash
    )
    files = {"manifest.json": manifest_bytes}
    for relative, row in rows.items():
        files[relative] = read_bounded_v3(package / relative, row["byteSize"])
    _verify_files(
        files,
        expected=expected,
        trusted_manifest_hash=trusted_manifest_hash,
        limits=RuntimeV2Limits(),
        complete=True,
    )
    nested = "payload.closyruntime/"
    doc = loads_strict_json_object(files[nested + "manifest.json"].decode())
    dependencies = ["manifest.json", "capabilities.json", "materials.json"]
    dependencies.extend(
        doc["blobs"][page["blob"]]["path"]
        for page in doc["assets"]["conventionalFallback"]["pages"]
    )
    fallback = list(dict.fromkeys(["manifest.json", *(nested + p for p in dependencies)]))
    ordered = list(dict.fromkeys([*fallback, *sorted(rows)]))
    archive = bytearray(b"CLSRTP2\0" + struct.pack("<I", len(ordered)))
    end = 0
    for relative in ordered:
        name, content = relative.encode(), files[relative]
        archive.extend(struct.pack("<HQ", len(name), len(content)) + name + content)
        if relative in fallback:
            end = len(archive)
    payload = bytes(archive)
    inventory = build_chunk_inventory(payload, chunk_size=chunk_size, limits=limits)
    manifest = {
        "streamVersion": STREAM_V3,
        "archiveCodec": "CLSRTP2",
        "trustedPackageManifestSha256": trusted_manifest_hash,
        "expected": expected.json(),
        "fallbackReadyChunkCount": (end + chunk_size - 1) // chunk_size,
        "dependencyOrder": ordered,
        "fallbackDependencies": fallback,
        "transportInventory": inventory,
        "aggregateSha256": sha256_bytes(payload),
        "transportKind": "local_fixture_not_network_or_mobile",
    }
    return RuntimeStreamV3(
        manifest,
        payload,
        tuple(payload[o : o + chunk_size] for o in range(0, len(payload), chunk_size)),
    )


class RuntimeStreamReceiverV3:
    def __init__(
        self,
        cache: Path,
        stream: RuntimeStreamV3,
        *,
        session_id: str,
        expected: RuntimeIdentityV3,
        trusted_transfer_hash: str,
        limits: TransferLimits | None = None,
    ) -> None:
        # Pin a copy so the caller cannot mutate metadata after trust verification.
        doc = loads_strict_json_object(canonical_dumps(stream.manifest))
        if doc.get("streamVersion") != STREAM_V3:
            raise RuntimeV3Error("runtime_v3_transfer_version_unsupported")
        if transfer_identity_v3(doc) != trusted_transfer_hash:
            raise RuntimeV3Error("runtime_v3_untrusted_transfer")
        if doc.get("expected") != expected.json() or doc.get("archiveCodec") != "CLSRTP2":
            raise RuntimeV3Error("runtime_v3_transfer_identity_mismatch")
        inventory = doc.get("transportInventory")
        if not isinstance(inventory, dict) or doc.get("aggregateSha256") != inventory.get(
            "aggregateSha256"
        ):
            raise RuntimeV3Error("runtime_v3_transfer_inventory_mismatch")
        ready = doc.get("fallbackReadyChunkCount")
        if type(ready) is not int or not 1 <= ready <= len(inventory.get("chunks", [])):
            raise RuntimeV3Error("runtime_v3_transfer_prefix_invalid")
        reject_links_v3(cache)
        self.manifest = doc
        self.expected = expected
        self._cancelled = False
        self._receiver = TransferReceiver(cache, inventory, session_id=session_id, limits=limits)

    @property
    def missing_indices(self) -> tuple[int, ...]:
        return self._receiver.missing_indices

    @property
    def received_indices(self) -> tuple[int, ...]:
        return self._receiver.received_indices

    @property
    def resume_bytes_saved(self) -> int:
        return sum(
            self.manifest["transportInventory"]["chunks"][i]["byteSize"]
            for i in self.received_indices
        )

    def cancel(self) -> None:
        self._cancelled = True

    def receive(self, index: int, payload: bytes) -> None:
        if self._cancelled:
            raise TransferError("transfer_cancelled")
        self._receiver.receive(index, payload)

    def finalize(self, destination: Path) -> Path:
        if self._cancelled:
            raise TransferError("transfer_cancelled")
        return self._receiver.finalize(destination)

    def verified_prefix(self) -> bytes:
        if self._cancelled:
            raise TransferError("transfer_cancelled")
        chunks = []
        present = set(self.received_indices)
        for i, row in enumerate(self.manifest["transportInventory"]["chunks"]):
            if i not in present:
                break
            data = read_bounded_v3(self._receiver.chunk_dir / f"{i:06d}.chunk", row["byteSize"])
            if len(data) != row["byteSize"] or sha256_bytes(data) != row["sha256"]:
                raise TransferError("transfer_cached_chunk_corrupt")
            chunks.append(data)
        return load_prefix_v3(
            b"".join(chunks),
            expected=self.expected,
            trusted_manifest_hash=self.manifest["trustedPackageManifestSha256"],
        )


def receive_v3(
    cache: Path,
    stream: RuntimeStreamV3,
    *,
    session_id: str,
    expected: RuntimeIdentityV3,
    trusted_transfer_hash: str,
    limits: TransferLimits | None = None,
) -> RuntimeStreamReceiverV3:
    return RuntimeStreamReceiverV3(
        cache,
        stream,
        session_id=session_id,
        expected=expected,
        trusted_transfer_hash=trusted_transfer_hash,
        limits=limits,
    )


def _entries(payload: bytes, limits: RuntimeV2Limits, *, complete: bool) -> dict[str, bytes]:
    if len(payload) > limits.max_total_bytes or payload[:8] != b"CLSRTP2\0":
        raise RuntimeV3Error("runtime_v3_archive_invalid")
    if len(payload) < 12:
        raise RuntimeV3Error("runtime_v3_archive_truncated")
    count = struct.unpack_from("<I", payload, 8)[0]
    if not 0 < count <= limits.max_file_count:
        raise RuntimeV3Error("runtime_v3_archive_count_invalid")
    cursor = 12
    files: dict[str, bytes] = {}
    aliases: set[str] = set()
    for _ in range(count):
        if cursor + 10 > len(payload):
            break
        name_size, size = struct.unpack_from("<HQ", payload, cursor)
        if not 0 < name_size <= 512 or size > limits.max_file_bytes:
            raise RuntimeV3Error("runtime_v3_archive_entry_invalid")
        end = cursor + 10 + name_size + size
        if end > len(payload):
            break
        cursor += 10
        name = safe_relative_v3(payload[cursor : cursor + name_size].decode("utf-8"))
        if name.casefold() in aliases:
            raise RuntimeV3Error("runtime_v3_archive_duplicate_path")
        aliases.add(name.casefold())
        cursor += name_size
        files[name] = payload[cursor:end]
        cursor = end
    if len(files) == count and cursor != len(payload):
        raise RuntimeV3Error("runtime_v3_archive_trailing_bytes")
    if complete and len(files) != count:
        raise RuntimeV3Error("runtime_v3_archive_truncated")
    return files


def _verify_files(
    files: dict[str, bytes],
    *,
    expected: RuntimeIdentityV3,
    trusted_manifest_hash: str,
    limits: RuntimeV2Limits,
    complete: bool,
) -> None:
    if "manifest.json" not in files:
        raise RuntimeV3Error("runtime_v3_manifest_pending")
    _, rows = trusted_manifest_v3(
        files["manifest.json"],
        expected=expected,
        trusted_manifest_hash=trusted_manifest_hash,
        limits=limits,
    )
    if complete and set(files) != rows.keys() | {"manifest.json"}:
        raise RuntimeV3Error("runtime_v3_exact_inventory_mismatch")
    for name, payload in files.items():
        if name == "manifest.json":
            continue
        row = rows.get(name)
        if row is None or row["byteSize"] != len(payload) or row["sha256"] != sha256_bytes(payload):
            raise RuntimeV3Error("runtime_v3_prefix_file_identity_mismatch")
    nested = files.get("payload.closyruntime/manifest.json")
    if nested is None:
        raise RuntimeV3Error("runtime_v3_nested_manifest_pending")
    if len(nested) > MAX_MANIFEST_BYTES:
        raise RuntimeV3Error("runtime_v3_nested_manifest_limit")
    validate_nested_v3(loads_strict_json_object(nested.decode()), expected, limits)


def load_prefix_v3(
    prefix: bytes,
    *,
    expected: RuntimeIdentityV3,
    trusted_manifest_hash: str,
    limits: RuntimeV2Limits | None = None,
) -> bytes:
    active = limits or RuntimeV2Limits()
    try:
        files = _entries(prefix, active, complete=False)
        _verify_files(
            files,
            expected=expected,
            trusted_manifest_hash=trusted_manifest_hash,
            limits=active,
            complete=False,
        )
        nested = {
            p.removeprefix("payload.closyruntime/"): b
            for p, b in files.items()
            if p.startswith("payload.closyruntime/")
        }
        # Explicit codec adaptation after V3 trust verification, never a version bypass.
        archive = bytearray(b"CLSRTP2\0" + struct.pack("<I", len(nested)))
        for path, payload in nested.items():
            name = path.encode()
            archive.extend(struct.pack("<HQ", len(name), len(payload)) + name + payload)
        fallback = load_fallback_from_archive_prefix_v2(bytes(archive), limits=active)
        decode_glb_v3(fallback, active)
        return fallback
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, struct.error) as error:
        raise RuntimeV3Error(f"runtime_v3_prefix_rejected:{error}") from error


def materialize_v3(
    payload: bytes,
    destination: Path,
    *,
    expected: RuntimeIdentityV3,
    trusted_manifest_hash: str,
    trusted_archive_hash: str,
    limits: RuntimeV2Limits | None = None,
) -> LoadedRuntimePackageV3:
    active = limits or RuntimeV2Limits()
    # The actual trusted transport contract rejects truncation at the aggregate hash first.
    if len(payload) > active.max_total_bytes or sha256_bytes(payload) != trusted_archive_hash:
        raise RuntimeV3Error("runtime_v3_archive_integrity_mismatch")
    reject_links_v3(destination)
    if destination.exists():
        raise RuntimeV3Error("runtime_v3_destination_must_be_fresh")
    files = _entries(payload, active, complete=True)
    _verify_files(
        files,
        expected=expected,
        trusted_manifest_hash=trusted_manifest_hash,
        limits=active,
        complete=True,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".runtime-v3-unpack-", dir=destination.parent) as temp:
        stage = Path(temp) / "package"
        stage.mkdir()
        for relative, content in files.items():
            path = stage / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        loaded = load_runtime_package_v3(
            stage, expected=expected, trusted_manifest_hash=trusted_manifest_hash, limits=active
        )
        stage.rename(destination)
    return loaded
