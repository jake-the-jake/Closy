from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

STREAM_SCHEMA_VERSION = "closy.runtime_stream.static_prep.v1"


class TransferError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TransferLimits:
    max_chunk_bytes: int = 1_048_576
    max_chunks: int = 4096
    max_total_bytes: int = 134_217_728
    max_cache_entries: int = 4


def build_chunk_inventory(
    payload: bytes,
    *,
    chunk_size: int = 262_144,
    limits: TransferLimits | None = None,
) -> dict[str, Any]:
    active = limits or TransferLimits()
    if not payload:
        raise TransferError("transfer_empty_payload")
    if chunk_size < 1 or chunk_size > active.max_chunk_bytes:
        raise TransferError("transfer_chunk_size_invalid")
    if len(payload) > active.max_total_bytes:
        raise TransferError("transfer_total_limit_exceeded")
    chunks = [
        {
            "index": index,
            "byteSize": len(chunk),
            "sha256": sha256_bytes(chunk),
        }
        for index, offset in enumerate(range(0, len(payload), chunk_size))
        if (chunk := payload[offset : offset + chunk_size])
    ]
    if len(chunks) > active.max_chunks:
        raise TransferError("transfer_chunk_count_exceeded")
    identity_payload = {
        "schemaVersion": 1,
        "streamVersion": STREAM_SCHEMA_VERSION,
        "aggregateSha256": sha256_bytes(payload),
        "totalBytes": len(payload),
        "chunks": chunks,
    }
    return {
        **identity_payload,
        "transferId": "transfer_" + sha256_bytes(canonical_dumps(identity_payload).encode())[:24],
    }


class TransferReceiver:
    """Persistent local transport fixture; it does not claim a remote service."""

    def __init__(
        self,
        cache_root: Path,
        inventory: dict[str, Any],
        *,
        session_id: str = "active",
        limits: TransferLimits | None = None,
    ) -> None:
        self.limits = limits or TransferLimits()
        self.inventory = _validate_inventory(inventory, self.limits)
        if not session_id or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for character in session_id
        ):
            raise TransferError("transfer_session_id_invalid")
        self.cache_root = cache_root.absolute()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        if self.cache_root.is_symlink():
            raise TransferError("transfer_cache_link_rejected")
        self.session_dir = self.cache_root / session_id
        self.state_path = self.session_dir / "state.json"
        self.chunk_dir = self.session_dir / "chunks"
        self._inventory_digest = _inventory_digest(self.inventory)
        self._open_or_create()

    @property
    def received_indices(self) -> tuple[int, ...]:
        state = self._read_state()
        return tuple(int(value) for value in state["received"])

    @property
    def missing_indices(self) -> tuple[int, ...]:
        received = set(self.received_indices)
        return tuple(
            int(record["index"])
            for record in self.inventory["chunks"]
            if int(record["index"]) not in received
        )

    def receive(self, index: int, payload: bytes) -> None:
        records = self.inventory["chunks"]
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or index < 0
            or index >= len(records)
        ):
            raise TransferError("transfer_chunk_index_invalid")
        record = records[index]
        if len(payload) != record["byteSize"] or len(payload) > self.limits.max_chunk_bytes:
            raise TransferError("transfer_chunk_size_mismatch")
        if sha256_bytes(payload) != record["sha256"]:
            raise TransferError("transfer_chunk_hash_mismatch")
        state = self._read_state()
        received = {int(value) for value in state["received"]}
        if index in received or (self.chunk_dir / f"{index:06d}.chunk").exists():
            raise TransferError("transfer_duplicate_chunk")
        destination = self.chunk_dir / f"{index:06d}.chunk"
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, destination)
        received.add(index)
        self._write_state(sorted(received))

    def finalize(self, destination: Path) -> Path:
        if self.missing_indices:
            raise TransferError("transfer_chunks_missing")
        target = destination.absolute()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            raise TransferError("transfer_destination_exists")
        temporary = target.with_name(f".{target.name}.transfer.tmp")
        total = 0
        aggregate_digest = hashlib.sha256()
        try:
            with temporary.open("xb") as output:
                for record in self.inventory["chunks"]:
                    chunk_path = self.chunk_dir / f"{int(record['index']):06d}.chunk"
                    chunk = _read_regular_file(chunk_path, self.limits.max_chunk_bytes)
                    if len(chunk) != record["byteSize"] or sha256_bytes(chunk) != record["sha256"]:
                        raise TransferError("transfer_cached_chunk_corrupt")
                    total += len(chunk)
                    if total > self.limits.max_total_bytes:
                        raise TransferError("transfer_total_limit_exceeded")
                    output.write(chunk)
                    aggregate_digest.update(chunk)
            if total != self.inventory["totalBytes"]:
                raise TransferError("transfer_aggregate_size_mismatch")
            if aggregate_digest.hexdigest() != self.inventory["aggregateSha256"]:
                raise TransferError("transfer_aggregate_hash_mismatch")
            os.replace(temporary, target)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return target

    def _open_or_create(self) -> None:
        if self.session_dir.exists() or self.session_dir.is_symlink():
            if self.session_dir.is_symlink() or not self.session_dir.is_dir():
                raise TransferError("transfer_session_unsafe")
            state = self._read_state(check_identity=False)
            if (
                state.get("inventoryDigest") != self._inventory_digest
                or state.get("transferId") != self.inventory["transferId"]
            ):
                raise TransferError("transfer_stale_resume")
            self._validate_cached_chunks(state)
            return
        self.chunk_dir.mkdir(parents=True)
        self._write_state([])

    def _read_state(self, *, check_identity: bool = True) -> dict[str, Any]:
        try:
            payload = json.loads(_read_regular_file(self.state_path, 65_536).decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TransferError("transfer_state_invalid") from error
        if (
            not isinstance(payload, dict)
            or payload.get("schemaVersion") != 1
            or payload.get("stateVersion") != STREAM_SCHEMA_VERSION
            or not isinstance(payload.get("received"), list)
        ):
            raise TransferError("transfer_state_invalid")
        if check_identity and payload.get("transferId") != self.inventory["transferId"]:
            raise TransferError("transfer_state_invalid")
        received = payload["received"]
        if any(not isinstance(value, int) or isinstance(value, bool) for value in received):
            raise TransferError("transfer_state_invalid")
        if received != sorted(set(received)):
            raise TransferError("transfer_state_invalid")
        return payload

    def _write_state(self, received: list[int]) -> None:
        payload = {
            "schemaVersion": 1,
            "stateVersion": STREAM_SCHEMA_VERSION,
            "transferId": self.inventory["transferId"],
            "inventoryDigest": self._inventory_digest,
            "received": received,
        }
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(canonical_dumps(payload), encoding="utf-8", newline="\n")
        os.replace(temporary, self.state_path)

    def _validate_cached_chunks(self, state: dict[str, Any]) -> None:
        expected = {f"{int(index):06d}.chunk" for index in state["received"]}
        actual: set[str] = set()
        for child in self.chunk_dir.iterdir():
            if child.is_symlink() or not child.is_file():
                raise TransferError("transfer_cache_entry_unsafe")
            actual.add(child.name)
        if actual != expected:
            raise TransferError("transfer_cache_inventory_mismatch")
        records = self.inventory["chunks"]
        for index in state["received"]:
            if index < 0 or index >= len(records):
                raise TransferError("transfer_state_invalid")
            chunk = _read_regular_file(
                self.chunk_dir / f"{index:06d}.chunk", self.limits.max_chunk_bytes
            )
            if (
                len(chunk) != records[index]["byteSize"]
                or sha256_bytes(chunk) != records[index]["sha256"]
            ):
                raise TransferError("transfer_cached_chunk_corrupt")


def evict_transfer_state(
    cache_root: Path, *, keep_session_ids: set[str] | None = None
) -> tuple[str, ...]:
    root = cache_root.absolute()
    if not root.exists():
        return ()
    if root.is_symlink() or not root.is_dir():
        raise TransferError("transfer_cache_link_rejected")
    keep = keep_session_ids or set()
    removed: list[str] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if child.name in keep:
            continue
        if child.is_symlink() or not child.is_dir():
            raise TransferError("transfer_cache_entry_unsafe")
        state_path = child / "state.json"
        if not state_path.is_file() or state_path.is_symlink():
            raise TransferError("transfer_cache_entry_unsafe")
        shutil.rmtree(child)
        removed.append(child.name)
    return tuple(removed)


def _validate_inventory(inventory: dict[str, Any], limits: TransferLimits) -> dict[str, Any]:
    if (
        not isinstance(inventory, dict)
        or inventory.get("schemaVersion") != 1
        or inventory.get("streamVersion") != STREAM_SCHEMA_VERSION
    ):
        raise TransferError("transfer_inventory_version_unsupported")
    transfer_id = inventory.get("transferId")
    if not isinstance(transfer_id, str) or not transfer_id.startswith("transfer_"):
        raise TransferError("transfer_inventory_invalid")
    chunks = inventory.get("chunks")
    total = inventory.get("totalBytes")
    aggregate = inventory.get("aggregateSha256")
    if (
        not isinstance(chunks, list)
        or not chunks
        or len(chunks) > limits.max_chunks
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < 1
        or total > limits.max_total_bytes
        or not _is_digest(aggregate)
    ):
        raise TransferError("transfer_inventory_invalid")
    counted = 0
    for index, record in enumerate(chunks):
        if not isinstance(record, dict) or record.get("index") != index:
            raise TransferError("transfer_inventory_invalid")
        size = record.get("byteSize")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size < 1
            or size > limits.max_chunk_bytes
            or not _is_digest(record.get("sha256"))
        ):
            raise TransferError("transfer_inventory_invalid")
        counted += size
    if counted != total:
        raise TransferError("transfer_inventory_invalid")
    expected_id = (
        "transfer_"
        + sha256_bytes(
            canonical_dumps(
                {
                    "schemaVersion": 1,
                    "streamVersion": STREAM_SCHEMA_VERSION,
                    "aggregateSha256": aggregate,
                    "totalBytes": total,
                    "chunks": chunks,
                }
            ).encode()
        )[:24]
    )
    if transfer_id != expected_id:
        raise TransferError("transfer_inventory_identity_mismatch")
    return inventory


def _inventory_digest(inventory: dict[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(inventory).encode())


def _read_regular_file(path: Path, maximum: int) -> bytes:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as error:
        raise TransferError("transfer_file_missing") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise TransferError("transfer_file_unsafe")
    if metadata.st_size > maximum:
        raise TransferError("transfer_file_limit_exceeded")
    return path.read_bytes()


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
