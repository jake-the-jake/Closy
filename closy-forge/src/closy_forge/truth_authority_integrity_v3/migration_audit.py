from __future__ import annotations

import ast
import hashlib
import io
import subprocess
import tokenize
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .common import canonical_digest, load_mapping, records

V2_LOCK_COMMIT = "d76916461d3e96b037fbc31b646319effef7a264"
LOCK_PATH = Path("closy-forge/fixtures/final_strategy3_v2/final_implementation_lock.json")
PUBLIC_PROOF_PATH = Path("closy-forge/docs/evidence/final_strategy3_v2/public_conformance.json")
EXPECTED_CRLF_PATHS = frozenset(
    {
        "src/closy_forge/recovery_foundation_v2/topology_holdout.py",
        "src/closy_forge/recovery_foundation_v2/topology_holdout_oracle.py",
        "src/closy_forge/simulation/reference_cloth_solver.py",
        "src/closy_forge/simulation/self_collision.py",
    }
)


def audit_v2_lock(repo_root: Path, *, commit: str = V2_LOCK_COMMIT) -> dict[str, Any]:
    lock = load_mapping(repo_root / LOCK_PATH)
    tree = _git(repo_root, "rev-parse", f"{commit}^{{tree}}", text=True).strip()
    rows: list[dict[str, Any]] = []
    for ordinal, item in enumerate(records(lock.get("implementationFiles"))):
        lock_relative = _normalise_lock_path(str(item.get("path", "")))
        repository_path = _repository_path(lock_relative)
        mode, object_type, oid = _tree_entry(repo_root, commit, repository_path)
        raw = _git(repo_root, "cat-file", "blob", oid)
        raw_sha = hashlib.sha256(raw).hexdigest()
        locked_sha = str(item.get("sha256", ""))
        locked_length = int(item.get("byteLength", -1))
        crlf = raw.replace(b"\n", b"\r\n")
        if raw_sha == locked_sha and len(raw) == locked_length:
            materialization = "raw_git_blob_exact"
            equivalent = True
        elif hashlib.sha256(crlf).hexdigest() == locked_sha and len(crlf) == locked_length:
            materialization = "lf_to_crlf_only"
            equivalent = _semantic_equivalence(repository_path, raw, crlf)
        else:
            materialization = "unexplained_mismatch"
            equivalent = False
        rows.append(
            {
                "ordinal": ordinal,
                "lockPath": lock_relative,
                "repositoryPath": repository_path,
                "gitMode": mode,
                "objectType": object_type,
                "rawBlobOid": oid,
                "rawBlobByteLength": len(raw),
                "rawBlobSha256": raw_sha,
                "lockedByteLength": locked_length,
                "lockedSha256": locked_sha,
                "materialization": materialization,
                "crlfRoundTripExact": (
                    crlf.replace(b"\r\n", b"\n") == raw
                    if materialization == "lf_to_crlf_only"
                    else None
                ),
                "astAndTokenEquivalent": equivalent,
            }
        )
    proof = load_mapping(repo_root / PUBLIC_PROOF_PATH)
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "auditVersion": "closy.strategy3_v2.repository_blob_migration_audit.v1",
        "repository": "jake-the-jake/Closy",
        "lockCommit": commit,
        "rootTreeObjectId": tree,
        "lockedPathCount": len(rows),
        "rawBlobExactCount": sum(row["materialization"] == "raw_git_blob_exact" for row in rows),
        "lfToCrlfOnlyCount": sum(row["materialization"] == "lf_to_crlf_only" for row in rows),
        "unexplainedMismatchCount": sum(
            row["materialization"] == "unexplained_mismatch" for row in rows
        ),
        "rows": rows,
        "publicConformance": {
            "proofHash": proof.get("proofHash"),
            "fixtureCount": proof.get("fixtureCount"),
            "fixturePassCount": proof.get("fixturePassCount"),
            "decisionsUnchanged": (
                proof.get("fixtureCount") == 8
                and proof.get("fixturePassCount") == 8
                and all(not row.get("issues") for row in records(proof.get("rows")))
            ),
        },
        "pass": False,
        "auditDigest": "",
    }
    document["pass"] = validate_migration_audit(document) == []
    document["auditDigest"] = canonical_digest(document, "auditDigest")
    return document


def validate_migration_audit(document: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    rows = records(document.get("rows"))
    if len(rows) != 24 or document.get("lockedPathCount") != 24:
        issues.append("v2_locked_path_denominator_invalid")
    classifications = [str(row.get("materialization", "")) for row in rows]
    if classifications.count("raw_git_blob_exact") != 20:
        issues.append("v2_raw_blob_exact_count_invalid")
    if classifications.count("lf_to_crlf_only") != 4:
        issues.append("v2_crlf_materialization_count_invalid")
    if any(value not in {"raw_git_blob_exact", "lf_to_crlf_only"} for value in classifications):
        issues.append("v2_unexplained_byte_difference")
    crlf_paths = {
        str(row.get("lockPath")) for row in rows if row.get("materialization") == "lf_to_crlf_only"
    }
    if crlf_paths != EXPECTED_CRLF_PATHS:
        issues.append("v2_crlf_path_signature_invalid")
    if any(
        row.get("materialization") == "lf_to_crlf_only"
        and (
            row.get("crlfRoundTripExact") is not True
            or row.get("astAndTokenEquivalent") is not True
        )
        for row in rows
    ):
        issues.append("v2_crlf_semantic_equivalence_invalid")
    if document.get("publicConformance") != {
        **dict(document.get("publicConformance", {})),
        "decisionsUnchanged": True,
    }:
        issues.append("v2_public_conformance_decision_changed")
    return sorted(set(issues))


def validate_audit_digest(document: Mapping[str, Any]) -> list[str]:
    return (
        []
        if document.get("auditDigest") == canonical_digest(document, "auditDigest")
        else ["v2_migration_audit_digest_invalid"]
    )


def _normalise_lock_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or "\\" in value:
        raise ValueError(f"v2_lock_path_invalid:{value}")
    if value.startswith("../.github/workflows/"):
        return value
    if ".." in path.parts:
        raise ValueError(f"v2_lock_path_traversal:{value}")
    return path.as_posix()


def _repository_path(lock_path: str) -> str:
    if lock_path.startswith("../"):
        return lock_path.removeprefix("../")
    return f"closy-forge/{lock_path}"


def _tree_entry(repo_root: Path, commit: str, path: str) -> tuple[str, str, str]:
    raw = _git(repo_root, "ls-tree", commit, "--", path, text=True).strip()
    if not raw:
        raise ValueError(f"v2_lock_blob_missing:{path}")
    metadata, actual_path = raw.split("\t", 1)
    mode, object_type, oid = metadata.split(" ", 2)
    if actual_path != path or object_type != "blob":
        raise ValueError(f"v2_lock_non_blob:{path}")
    return mode, object_type, oid


def _semantic_equivalence(path: str, raw: bytes, materialized: bytes) -> bool:
    if materialized.replace(b"\r\n", b"\n") != raw:
        return False
    if not path.endswith(".py"):
        return True
    raw_text = raw.decode("utf-8")
    materialized_text = materialized.decode("utf-8")
    if ast.dump(ast.parse(raw_text), include_attributes=False) != ast.dump(
        ast.parse(materialized_text), include_attributes=False
    ):
        return False
    return _tokens(raw) == _tokens(materialized)


def _tokens(data: bytes) -> list[tuple[int, str]]:
    ignored = {tokenize.ENCODING, tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER}
    return [
        (token.type, token.string.replace("\r\n", "\n"))
        for token in tokenize.tokenize(io.BytesIO(data).readline)
        if token.type not in ignored
    ]


def _git(repo_root: Path, *args: str, text: bool = False) -> Any:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=text)
