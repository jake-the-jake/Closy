from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.managed_output import remove_managed_output

PRIVATE_REGISTRY_VERSION = "closy.private_source_registry.v1"


class PrivateRegistryError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PrivateDerivative:
    path: Path
    managed_purpose: str
    authorized_non_identifying: bool = False


def register_private_source(
    registry_path: Path,
    *,
    source_bytes: bytes,
    hmac_key: bytes,
    scope: str,
    consent_scope: str,
    retention_policy: str,
    deletion_policy: str,
    derivation_policy: str,
    derivatives: tuple[PrivateDerivative, ...] = (),
) -> str:
    if len(hmac_key) < 32:
        raise PrivateRegistryError("private_registry_key_too_short")
    if not source_bytes or not _safe_label(scope):
        raise PrivateRegistryError("private_registry_source_invalid")
    registry = _read_registry(registry_path)
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    opaque = (
        "src_"
        + hmac.new(
            hmac_key,
            f"{scope}\0{source_hash}".encode(),
            hashlib.sha256,
        ).hexdigest()[:32]
    )
    if opaque in registry["records"]:
        raise PrivateRegistryError("private_registry_duplicate_source")
    root = registry_path.absolute().parent
    derivative_records: list[dict[str, Any]] = []
    for derivative in derivatives:
        absolute = derivative.path.absolute()
        try:
            relative = absolute.relative_to(root).as_posix()
        except ValueError as error:
            raise PrivateRegistryError("private_derivative_outside_registry_root") from error
        if not relative or relative.startswith("../") or absolute == registry_path.absolute():
            raise PrivateRegistryError("private_derivative_path_invalid")
        derivative_records.append(
            {
                "relativePath": relative,
                "managedPurpose": derivative.managed_purpose,
                "authorizedNonIdentifying": derivative.authorized_non_identifying,
            }
        )
    registry["records"][opaque] = {
        "rawSourceSha256": source_hash,
        "scope": scope,
        "consentScope": consent_scope,
        "retentionPolicy": retention_policy,
        "deletionPolicy": deletion_policy,
        "derivationPolicy": derivation_policy,
        "withdrawalStatus": "active",
        "derivatives": derivative_records,
    }
    _write_registry(registry_path, registry)
    return opaque


def create_portable_source_link(registry_path: Path, opaque_id: str) -> dict[str, str]:
    registry = _read_registry(registry_path)
    record = registry["records"].get(opaque_id)
    if not isinstance(record, dict):
        raise PrivateRegistryError("private_registry_source_missing")
    return {
        "opaqueId": opaque_id,
        "consentScope": str(record["consentScope"]),
        "retentionPolicy": str(record["retentionPolicy"]),
        "deletionPolicy": str(record["deletionPolicy"]),
        "derivationPolicy": str(record["derivationPolicy"]),
        "withdrawalStatus": str(record["withdrawalStatus"]),
    }


def withdraw_private_source(registry_path: Path, opaque_id: str) -> dict[str, Any]:
    registry = _read_registry(registry_path)
    record = registry["records"].get(opaque_id)
    if not isinstance(record, dict):
        raise PrivateRegistryError("private_registry_source_missing")
    root = registry_path.absolute().parent
    deleted: list[str] = []
    preserved: list[str] = []
    for derivative in record.get("derivatives", []):
        relative = derivative.get("relativePath")
        purpose = derivative.get("managedPurpose")
        if not isinstance(relative, str) or not isinstance(purpose, str):
            raise PrivateRegistryError("private_registry_record_invalid")
        target = (root / relative).absolute()
        try:
            target.relative_to(root)
        except ValueError as error:
            raise PrivateRegistryError("private_derivative_outside_registry_root") from error
        if derivative.get("authorizedNonIdentifying") is True:
            preserved.append(relative)
            continue
        try:
            remove_managed_output(target, allowed_root=target.parent, purpose=purpose)
        except (OSError, ValueError) as error:
            raise PrivateRegistryError("private_derivative_delete_failed") from error
        deleted.append(relative)
    del registry["records"][opaque_id]
    registry["withdrawals"][opaque_id] = {
        "withdrawalStatus": "withdrawn",
        "deletedDerivatives": sorted(deleted),
        "preservedAuthorizedNonIdentifying": sorted(preserved),
    }
    _write_registry(registry_path, registry)
    return {
        "opaqueId": opaque_id,
        "withdrawalStatus": "withdrawn",
        "deletedDerivatives": tuple(sorted(deleted)),
        "preservedAuthorizedNonIdentifying": tuple(sorted(preserved)),
        "rawMappingRemoved": True,
    }


def _read_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schemaVersion": PRIVATE_REGISTRY_VERSION, "records": {}, "withdrawals": {}}
    if path.is_symlink() or not path.is_file():
        raise PrivateRegistryError("private_registry_path_unsafe")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PrivateRegistryError("private_registry_invalid") from error
    if (
        not isinstance(payload, dict)
        or payload.get("schemaVersion") != PRIVATE_REGISTRY_VERSION
        or not isinstance(payload.get("records"), dict)
        or not isinstance(payload.get("withdrawals"), dict)
    ):
        raise PrivateRegistryError("private_registry_invalid")
    return payload


def _write_registry(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical_dumps(payload), encoding="utf-8", newline="\n")
    temporary.replace(path)


def _safe_label(value: str) -> bool:
    return 1 <= len(value) <= 64 and all(
        character.isascii() and (character.isalnum() or character in "-_.:") for character in value
    )
