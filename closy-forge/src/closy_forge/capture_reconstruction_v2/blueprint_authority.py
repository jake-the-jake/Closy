from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .blueprint_parser import build_requirement_inventory
from .common import canonical_digest, sha256_bytes

BLUEPRINT_REPOSITORY = "jake-the-jake/Closy"
BLUEPRINT_PATH = "closy-forge/docs/Closy_AI_3D_Garment_and_ZeroOne_Integration_Master_Blueprint.md"
APPROVED_COMMIT = "9fc0b1023becd1dcd5f8c10c517e6c349c46c270"
APPROVED_TREE = "87f865668c7077f6a9ff546fa7229947411b31e8"
HISTORICAL_CRLF_WORKTREE_SHA256 = "1c8157f5d2111e72eb75195d93ea71412591316e58b71db27f3d8aca1c2f9ffa"


def read_git_blob(repository: Path, commit: str = APPROVED_COMMIT) -> tuple[str, bytes]:
    blob_oid = _git(repository, "rev-parse", f"{commit}:{BLUEPRINT_PATH}").decode().strip()
    payload = _git(repository, "cat-file", "blob", blob_oid)
    return blob_oid, payload


def build_blueprint_authority(repository: Path) -> dict[str, Any]:
    blob_oid, payload = read_git_blob(repository)
    if payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError("blueprint_utf8_bom_forbidden")
    text = payload.decode("utf-8")
    inventory = build_requirement_inventory(text, source_blob_oid=blob_oid)
    newline_observation = "crlf" if b"\r\n" in payload else "lf"
    authority: dict[str, Any] = {
        "schemaVersion": 1,
        "authorityVersion": "closy.blueprint_git_blob_authority.v1",
        "repository": BLUEPRINT_REPOSITORY,
        "path": BLUEPRINT_PATH,
        "commit": APPROVED_COMMIT,
        "tree": APPROVED_TREE,
        "gitBlobOid": blob_oid,
        "byteLength": len(payload),
        "gitBlobSha256": sha256_bytes(payload),
        "textEncoding": "UTF-8-no-BOM",
        "newlineObservationInformationalOnly": newline_observation,
        "parserVersion": inventory["parserVersion"],
        "normalizedRequirementSetDigest": inventory["requirementSetDigest"],
        "historicalDiagnosedWorkingTree": {
            "newline": "crlf",
            "sha256": HISTORICAL_CRLF_WORKTREE_SHA256,
            "canonical": False,
        },
    }
    authority["authorityDigest"] = canonical_digest(authority)
    return authority


def verify_blueprint_authority(repository: Path, authority: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    try:
        rebuilt = build_blueprint_authority(repository)
    except (OSError, UnicodeDecodeError, subprocess.CalledProcessError, ValueError):
        return ["blueprint_git_blob_unreadable"]
    for field in (
        "repository",
        "path",
        "commit",
        "tree",
        "gitBlobOid",
        "byteLength",
        "gitBlobSha256",
        "textEncoding",
        "parserVersion",
        "normalizedRequirementSetDigest",
    ):
        if authority.get(field) != rebuilt.get(field):
            failures.append(f"blueprint_authority_{field}_mismatch")
    if authority.get("authorityDigest") != canonical_digest(authority, "authorityDigest"):
        failures.append("blueprint_authority_digest_invalid")
    return failures


def _git(repository: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=repository)
